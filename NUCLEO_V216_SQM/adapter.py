"""V216 SQM adapter. Only loopback observation/action API; no model calls."""
import json,random,sys,urllib.request
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V170_V215"))
from nucleus import Memory,world,dump
ACTIONS=("north","east","south","west")
MAX_EVENTS=10000
def position(x):
    if type(x) not in (list,tuple) or len(x)!=2 or any(type(n) is not int or abs(n)>1000000 for n in x):raise ValueError("invalid observation")
    return tuple(x)
class Remote:
    def __init__(self,port=8082):
        if type(port) is not int or not 1<=port<=65535:raise ValueError("port")
        self.base=f"http://127.0.0.1:{port}"
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(self,path,data=None):
        req=urllib.request.Request(self.base+path,None if data is None else json.dumps(data).encode(),{"Content-Type":"application/json"})
        with self.opener.open(req,timeout=3) as response:
            raw=response.read(4097)
        if len(raw)>4096:raise ValueError("response too large")
        return json.loads(raw)
    def observe(self):return position(self.request("/observation")["position"])
    def act(self,a,before):
        if a not in ACTIONS:raise ValueError("action")
        result=self.request("/action",{"action":a})
        after=position(result["position"])
        if result.get("requested")!=a or type(result.get("moved")) is not bool or result["moved"]!=(after!=before):raise ValueError("inconsistent result; stop and inspect world")
        return after
def open_memory(path,scope):
    mem=Memory(path,resume=Path(path).exists())
    mem.db.execute("CREATE TABLE IF NOT EXISTS sqm_events(id INTEGER PRIMARY KEY,scope TEXT,event TEXT)")
    mem.db.commit()
    return mem
class Explorer:
    def __init__(self,mem,scope,mode="directed",seed=123):
        self.mem=mem;self.scope=scope;self.mode=mode;self.rng=random.Random(seed)
        self.edges={}
        for row in mem.db.execute("SELECT key,value FROM knowledge WHERE scope=?",(scope,)):
            x,y,a=json.loads(row[0]);target=position(json.loads(row[1]))
            if a not in ACTIONS:raise ValueError("invalid stored action")
            self.edges[position([x,y]),a]=target
    def count(self):return self.mem.db.execute("SELECT count(*) FROM sqm_events WHERE scope=?",(self.scope,)).fetchone()[0]
    def events(self,limit=80):
        rows=self.mem.db.execute("SELECT id,event FROM sqm_events WHERE scope=? ORDER BY id DESC LIMIT ?",(self.scope,limit))
        return [dict(id=r[0],**json.loads(r[1])) for r in rows][::-1]
    def predict(self,p,a):
        if (p,a) in self.edges:return self.edges[p,a],"transição observada"
        offsets=Counter((t[0]-s[0],t[1]-s[1]) for (s,k),t in self.edges.items() if k==a and s!=t)
        if not offsets:return None,"sem evidência"
        ranked=offsets.most_common()
        if len(ranked)>1 and ranked[0][1]==ranked[1][1]:return None,"hipóteses em conflito"
        dx,dy=ranked[0][0];return (p[0]+dx,p[1]+dy),"hipótese por deslocamento observado"
    def choose(self,p,goal=None):
        if goal==p:return None,"objetivo alcançado",()
        if self.mode=="random":return self.rng.choice(ACTIONS),"controle aleatório",()
        if goal is not None:
            route=world.path(self.edges,p,lambda s:s==goal,ACTIONS)
            if route:return route[0],"rota conhecida ao objetivo",route
        route=world.path(self.edges,p,lambda s:any((s,a) not in self.edges for a in ACTIONS),ACTIONS)
        if route is None:return None,"nenhuma fronteira alcançável no modelo atual",()
        if route:return route[0],"deslocamento até fronteira desconhecida",route
        a=next(a for a in ACTIONS if (p,a) not in self.edges)
        return a,"testar ação ainda não observada nesta posição",(a,)
    def step(self,remote,goal=None):
        if self.count()>=MAX_EVENTS:raise ValueError("limite de registros; nova memória necessária")
        p=remote.observe();a,reason,route=self.choose(p,goal)
        if a is None:return None,reason,p
        prediction,kind=self.predict(p,a)
        t=remote.act(a,p)
        known=(p,a) in self.edges;revision=known and self.edges[p,a]!=t
        event=dict(before=p,action=a,after=t,moved=p!=t,reason=reason,route=route,prediction=prediction,prediction_kind=kind,
            prediction_correct=None if prediction is None else prediction==t,novel=not known,revision=revision)
        with self.mem.db:
            self.mem.db.execute("INSERT OR REPLACE INTO knowledge(scope,key,value) VALUES(?,?,?)",(self.scope,dump([*p,a]),dump(t)))
            cur=self.mem.db.execute("INSERT INTO sqm_events(scope,event) VALUES(?,?)",(self.scope,dump(event)))
        self.edges[p,a]=t
        return dict(id=cur.lastrowid,**event),None,t
    def snapshot(self):
        rows=self.events()
        visited=sorted(set(t for t in self.edges.values())|set(p for p,a in self.edges))
        return dict(visited=visited,transitions=len(self.edges),events=rows,total=self.count(),
            blocked_edges=[dict(position=p,action=a) for (p,a),t in self.edges.items() if p==t],
            memory_scope=self.scope)
