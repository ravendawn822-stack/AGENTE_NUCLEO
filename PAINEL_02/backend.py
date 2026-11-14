import sys,json,sqlite3,time,threading,queue,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;EXP=ROOT.parent/'EXPERIMENTO_03'
sys.dont_write_bytecode=True
sys.path.insert(0,str(EXP))
from model import *
from engine import solve,learn,DEFAULT
from protocol import suite
from functools import lru_cache
_raw_ident=ident
@lru_cache(maxsize=4096)
def _cached_ident(e):return _raw_ident(e)
def ident(e):return _cached_ident(freeze(e))

class Cancelled(Exception):pass
class Control:
    def __init__(self):self.condition=threading.Condition();self.paused=False;self.stop=False;self.tokens=0;self.delay=0.
    def change(self,action):
        with self.condition:
            if action=='pause':self.paused=True
            if action=='resume':self.paused=False
            if action=='step':self.paused=True;self.tokens+=1
            if action=='stop':self.stop=True
            self.condition.notify_all()
    def gate(self):
        with self.condition:
            while self.paused and not self.tokens and not self.stop:self.condition.wait(.2)
            if self.stop:raise Cancelled()
            if self.tokens:self.tokens-=1
            if self.delay:self.condition.wait(self.delay)
            if self.stop:raise Cancelled()

class Recorder:
    def __init__(self,path):
        self.path=path;path.mkdir(parents=True,exist_ok=False)
        self.db=sqlite3.connect(path/'diagnostic.sqlite3');self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript('''CREATE TABLE events(seq INTEGER PRIMARY KEY,episode INTEGER,data TEXT);
        CREATE TABLE entities(id TEXT PRIMARY KEY,expression TEXT,kind TEXT,first_episode INTEGER,first_seq INTEGER);
        CREATE TABLE states(episode INTEGER,id TEXT,state TEXT,evidence TEXT,PRIMARY KEY(episode,id));
        CREATE TABLE skills(id TEXT PRIMARY KEY,data TEXT);''')
        self.log=(path/'events.jsonl').open('w',encoding='utf-8');self.count=0;self.start=time.perf_counter();self.last_commit=self.start
    def write(self,episode,event,commit=False):
        e=dict(event,episode=episode,wall_elapsed=time.perf_counter()-self.start)
        expr=e.get('expression') or e.get('expr')
        if expr:
            e.setdefault('id',ident(expr))
            # Cada nó é uma entidade persistida, inclusive os componentes.
            for node in subtrees(freeze(expr)):
                self.db.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?)',(ident(node),json.dumps(node),'expression',episode,self.count+1))
            sid=e.get('id',ident(expr))
            if 'state' in e:self.db.execute('INSERT OR REPLACE INTO states VALUES(?,?,?,?)',(episode,sid,e['state'],json.dumps(e.get('evidence',[]))))
        self.count+=1;e['seq']=self.count
        self.db.execute('INSERT INTO events VALUES(?,?,?)',(self.count,episode,json.dumps(e)))
        if e['kind']=='skill_acquired':self.db.execute('INSERT OR REPLACE INTO skills VALUES(?,?)',(e['id'],json.dumps(e)))
        self.log.write(json.dumps(e)+'\n')
        if commit or self.count%32==0 or time.perf_counter()-self.last_commit>=.2 or e['kind'] in ('episode_end','search_end'):
            self.db.commit();self.last_commit=time.perf_counter();self.log.flush()
        if self.count%100==0:self.log.flush()
        return e
    def memory(self,mem):
        for s in mem:self.db.execute('INSERT OR REPLACE INTO skills VALUES(?,?)',(s['id'],json.dumps(s)))
        self.db.commit()
    def close(self):self.db.commit();self.log.close();self.db.close()

def diagnose(control,notifications,agent='C',episodes=12):
    path=ROOT/'sessions'/(time.strftime('%Y%m%d_%H%M%S')+'_'+str(time.time_ns()));rec=Recorder(path)
    cfg=dict(DEFAULT,candidates=800,limit=4);mem=[];train,_=suite(104729,24)
    (path/'config.json').write_text(json.dumps(dict(cfg,agent=agent,diagnostic=True,seed=104729,episodes=episodes)))
    notifications.put(('started',str(path)))
    try:
        for i,target in enumerate(train[:episodes]):
            start=time.perf_counter()
            def emit(e):
                control.gate();rec.write(i,dict(e,episode_elapsed=time.perf_counter()-start),commit=control.paused)
            best,m=solve(lambda x:value(target,x),mem,agent,'candidates',cfg,104729+i,emit)
            learn(mem,best,m,lambda x:value(target,x),i+1,24,emit)
            if agent=='A':mem.clear()
            rec.memory(mem)
        notifications.put(('done',str(path)))
    except Cancelled:
        rec.write(i,dict(kind='session_cancelled',reason='user_control'))
        notifications.put(('cancelled',str(path)))
    except Exception as exc:
        rec.write(i,dict(kind='session_error',error=repr(exc)))
        notifications.put(('error',repr(exc)))
    finally:
        import tracemalloc
        if tracemalloc.is_tracing():tracemalloc.stop()
        rec.close()

def read_events(path,after=0,limit=1000):
    db=sqlite3.connect((Path(path)/'diagnostic.sqlite3').as_uri()+'?mode=ro',uri=True)
    rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM events WHERE seq>? ORDER BY seq LIMIT ?',(after,limit))];db.close();return rows
def read_skill(path,sid):
    db=sqlite3.connect((Path(path)/'diagnostic.sqlite3').as_uri()+'?mode=ro',uri=True)
    row=db.execute('SELECT data FROM skills WHERE id=?',(sid,)).fetchone()
    entity=db.execute('SELECT first_episode,first_seq FROM entities WHERE id=?',(sid,)).fetchone()
    evidence=[dict(episode=r[0],state=r[1],evidence=json.loads(r[2])) for r in db.execute('SELECT episode,state,evidence FROM states WHERE id=? ORDER BY episode',(sid,))]
    history=[json.loads(r[0]) for r in db.execute('SELECT data FROM events WHERE data LIKE ? ORDER BY seq DESC LIMIT 50',('%"id": "'+sid+'"%',))]
    skill=json.loads(row[0]) if row else None
    utility=None
    if skill:
        tries=sum(s['attempts'] for s in skill['contexts'].values());success=sum(s['success'] for s in skill['contexts'].values())
        utility=dict(associated_laplace_rate=(success+1)/(tries+2),attempts=tries,
            meaning='aggregate_association_not_causal_effect_or_contextual_selection_score',ablations=skill['ablations'])
    db.close();return dict(skill=skill,first_record=dict(episode=entity[0],seq=entity[1]) if entity else None,
        contextual_states=evidence,recent_events=list(reversed(history)),estimated_utility=utility)

def overhead():
    """Alterna ordem, repete consultas fixas; mede logging, sem atrasos humanos."""
    out=ROOT/'overhead';out.mkdir(exist_ok=True);train,_=suite(99117);rows=[]
    cfg=dict(DEFAULT,candidates=300)
    for repeat in range(3):
        for i,target in enumerate(train[:4]):
            results={}
            for traced in ((False,True) if repeat%2==0 else (True,False)):
                rec=Recorder(out/f'{time.time_ns()}') if traced else None
                tick=time.perf_counter()
                expr,m=solve(lambda x:value(target,x),[],'A','candidates',cfg,0,
                    (lambda e:rec.write(i,e)) if rec else None)
                if rec:rec.close()
                results[traced]=(time.perf_counter()-tick,expr,m['candidates'])
            assert results[False][1:]==results[True][1:]
            rows.append(dict(repeat=repeat,problem=i,plain_seconds=results[False][0],logged_seconds=results[True][0],
                ratio=results[True][0]/results[False][0],equivalent=True))
    (out/'measurements.json').write_text(json.dumps(rows,indent=2));return rows
