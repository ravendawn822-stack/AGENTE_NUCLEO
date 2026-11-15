"""V170–175: persistent typed agenda with explicit dependencies and scoped knowledge."""
import hashlib,json,sqlite3,sys
from pathlib import Path
from fractions import Fraction
import vm
import list_synthesis as synth
ROOT=Path(__file__).resolve().parents[1]
for v in ("NUCLEO_V133_V169","NUCLEO_V124","NUCLEO_V115"):sys.path.insert(0,str(ROOT/v))
import world
import tools_memory
import value_information as vi
import ambiguity as amb
APP=170215
KINDS=("deliver","navigate","list_solve","list_apply","stats","arithmetic")
def dump(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def digest(x):return hashlib.sha256(dump(x).encode()).hexdigest()
def stats(xs):
    xs=vm.array(vm.value(xs));n=len(xs);total=sum(xs)
    mean=Fraction(total,n) if n else None
    return dict(count=n,total=total,mean=[mean.numerator,mean.denominator] if n else None,
        frequencies={str(k):xs.count(k) for k in sorted(set(xs))})
class Memory:
    def __init__(self,path=None,resume=False):
        if path is None:self.db=sqlite3.connect(":memory:")
        else:
            p=Path(path).resolve()
            if resume:
                if not p.is_file() or p.stat().st_size>8*1024*1024:raise ValueError("memory size/path")
                with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as check:
                    if check.execute("PRAGMA application_id").fetchone()[0]!=APP:raise ValueError("not nucleus memory")
                self.db=sqlite3.connect(p.as_uri()+"?mode=rw",uri=True)
            else:
                with p.open("xb"):pass
                self.db=sqlite3.connect(p.as_uri()+"?mode=rw",uri=True)
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA trusted_schema=OFF")
        if not resume:
            self.db.executescript("""
            PRAGMA application_id=170215;
            CREATE TABLE goals(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,deps TEXT NOT NULL,status TEXT NOT NULL,result TEXT);
            CREATE TABLE evidence(id INTEGER PRIMARY KEY,goal INTEGER NOT NULL,event TEXT NOT NULL);
            CREATE TABLE knowledge(scope TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(scope,key));
            """);self.db.commit()
    def add(self,kind,payload,deps=()):
        if kind not in KINDS or type(payload) is not dict or len(dump(payload))>32768:raise ValueError("goal")
        old=self.goals()
        if len(old)>=16 or len(set(deps))!=len(deps) or not set(deps)<=set(g["id"] for g in old):raise ValueError("dependencies/quota")
        with self.db:
            cur=self.db.execute("INSERT INTO goals(kind,payload,deps,status) VALUES(?,?,?,?)",(kind,dump(payload),dump(list(deps)),"pending"))
        return cur.lastrowid
    def goals(self):
        result=[]
        for raw in self.db.execute("SELECT * FROM goals ORDER BY id LIMIT 17"):
            g=dict(raw)
            for key in ("payload","deps","result"):
                if g[key] is not None:g[key]=json.loads(g[key])
            result.append(g)
        if len(result)>16:raise ValueError("agenda quota")
        return result
    def finish(self,i,status,result):
        if status not in ("done","failed","blocked"):raise ValueError("status")
        with self.db:
            cur=self.db.execute("UPDATE goals SET status=?,result=? WHERE id=? AND status='pending'",(status,dump(result),i))
            if cur.rowcount!=1:raise ValueError("goal state")
            self.db.execute("INSERT INTO evidence(goal,event) VALUES(?,?)",(i,dump(dict(status=status,result=result))))
    def get(self,scope,key):
        row=self.db.execute("SELECT value FROM knowledge WHERE scope=? AND key=?",(scope,key)).fetchone()
        return json.loads(row[0]) if row else None
    def put(self,scope,key,value):
        serialized=dump(value)
        if len(serialized)>65536:raise ValueError("knowledge size")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO knowledge(scope,key,value) VALUES(?,?,?)",(scope,key,serialized))
    def counts(self):
        return dict(goals=self.db.execute("SELECT count(*) FROM goals").fetchone()[0],
            evidence=self.db.execute("SELECT count(*) FROM evidence").fetchone()[0],
            knowledge=self.db.execute("SELECT count(*) FROM knowledge").fetchone()[0])
    def close(self):self.db.close()
class Nucleus:
    def __init__(self,seed=118000019,memory=None,mode="direct",library=(),reuse=False,start=0,changed=False):
        if mode not in synth.MODES:raise ValueError("mode")
        self.mem=memory or Memory();self.mode=mode;self.library=library;self.reuse=reuse
        self.world=world.World(seed,start,changed);self.context=str(seed)
        saved=self.mem.get("map",self.context) if reuse else None
        edges={(s,a):t for s,a,t in saved["edges"]} if saved else {}
        stations=saved["stations"] if saved else {}
        self.agent=world.Agent(seed=seed,edges=edges,stations=stations,tools=tools_memory.acquire(edges))
        self.agent.perceive(self.world.observe())
    def add(self,kind,payload=None,deps=()):return self.mem.add(kind,payload or {},deps)
    def handle(self,g,done):
        p=g["payload"];kind=g["kind"]
        def dependency(i):
            if type(i) is not int or i not in g["deps"] or i not in done:raise ValueError("undeclared dependency")
            return done[i]
        if kind in ("deliver","navigate"):
            r=self.agent.solve(self.world,goal_room=p["room"] if kind=="navigate" else None)
            self.mem.put("map",self.context,dict(edges=[[s,a,t] for (s,a),t in sorted(self.agent.edges.items())],stations=self.agent.stations))
            return r["success"],dict(success=r["success"],actions=r["actions"],decisions=r["decisions"],
                divergences=r["divergences"],end=r["end"],events=r["events"])
        if kind=="list_solve":
            fit=synth.norm(p["fit"]);audit=synth.norm(p["audit"]);key=digest([fit,audit])
            stored=self.mem.get("list",key) if self.reuse else None
            if stored is not None and synth.matches(stored,fit+audit):
                r=dict(program=stored,candidates=0,atom_evaluations=0,audit_rejected=0,retried=0,elapsed_ns=0,memory_checks=1)
            else:
                r=synth.solve(fit,audit,self.mode,self.library);r["memory_checks"]=int(stored is not None)
            if r["program"] is not None:self.mem.put("list",key,r["program"])
            return r["program"] is not None,r
        if kind=="list_apply":
            program=dependency(p["program"])["program"]
            xs=vm.array(vm.value(p["input"]))
            if "cargo" in p:xs=xs+(dependency(p["cargo"])["end"]["cargo"],)
            result=vm.run_pipeline(program,xs)
            return True,dict(value=result)
        if kind=="stats":
            xs=dependency(p["source"])["value"]
            if type(xs) is int:xs=(xs,)
            return True,stats(xs)
        if kind=="arithmetic":
            oracle=amb.Oracle([tuple(x) for x in p["audit"]],2)
            r=vi.solve([tuple(x) for x in p["fit"]],oracle,"pool_active",int(p["seed"]))
            return r["program"] is not None,r
        raise ValueError("kind")
    def run(self,limit=16):
        if type(limit) is not int or not 0<=limit<=16:raise ValueError("limit")
        processed=[]
        for g in self.mem.goals():
            if g["status"]!="pending":continue
            if len(processed)>=limit:break
            current={x["id"]:x for x in self.mem.goals()}
            if any(current[d]["status"]!="done" for d in g["deps"]):
                status="blocked";result=dict(reason="dependency")
            else:
                try:
                    ok,result=self.handle(g,{d:current[d]["result"] for d in g["deps"]})
                    status="done" if ok else "failed"
                except (ValueError,KeyError,TypeError) as e:
                    status="failed";result=dict(reason=type(e).__name__,detail=str(e)[:200])
            self.mem.finish(g["id"],status,result);processed.append(g["id"])
        return self.mem.goals()
