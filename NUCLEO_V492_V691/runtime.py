"""Integrated runtime; environment adapter only receives a state and actions.
No world dimensions, exit, global map coverage target, or unrestricted execution."""
import json,sys,hashlib
from pathlib import Path
from collections import Counter,deque
ROOT=Path(__file__).resolve().parents[1]
for name in ("NUCLEO_V217_V330","NUCLEO_V217_V330_REFINO1","NUCLEO_V217_V330_REFINO2","NUCLEO_V331_V491","NUCLEO_V170_V215"):
    sys.path.insert(0,str(ROOT/name))
from online import Online
from interface import Registry,normalize
import list_synthesis,vm
from pipeline import solve,execute,export,Oracle
LIMIT=6000
LIB=tuple(tuple(x) for x in json.loads(Path(__file__).with_name("library.json").read_text())["library"])
def frozen(value):return json.loads(json.dumps(value,ensure_ascii=False))
class Core:
    def __init__(self,path,actions,scope="live",seed=492):
        self.registry=Registry(path,LIB);self.mem=self.registry.mem
        self.scope="v492:"+scope;self.actions=tuple(actions)
        self.mem.db.execute("CREATE TABLE IF NOT EXISTS v492_events(id INTEGER PRIMARY KEY,scope TEXT NOT NULL,event TEXT NOT NULL)")
        self.mem.db.commit()
        meta=self.mem.get(self.scope,"meta")
        expected=dict(actions=list(actions),schema=1)
        if meta is None:self.mem.put(self.scope,"meta",expected)
        elif meta!=expected:raise ValueError("context mismatch")
        self.agent=Online(self.actions,"hybrid",seed);self.total=0;self.outcomes=Counter();self.self_model={a:Counter() for a in actions};self.tools={};self.recent=deque(maxlen=3)
        saved=self.events(LIMIT+1)
        if len(saved)>LIMIT:raise ValueError("memory quota")
        for e in saved:
            self.agent.observe(tuple(e["before"]),e["action"],tuple(e["after"]),e.get("scores",{}))
            self.record(e)
        self.agent.rng.seed(seed+self.total)
    def events(self,limit=80):
        rows=self.mem.db.execute("SELECT id,event FROM v492_events WHERE scope=? ORDER BY id DESC LIMIT ?",(self.scope,limit))
        return [dict(id=r[0],**json.loads(r[1])) for r in rows][::-1]
    def record(self,e):
        self.total+=1
        a=e["action"];before=tuple(e["before"]);after=tuple(e["after"])
        c=self.self_model[a];c["attempts"]+=1;c["changed_state"]+=int(before!=after)
        c["unknown" if e["correct"] is None else "correct" if e["correct"] else "wrong"]+=1
        self.outcomes["unknown" if e["correct"] is None else "correct" if e["correct"] else "wrong"]+=1
        self.outcomes["revised"]+=int(e["revised"])
        if self.recent and tuple(self.recent[-1]["after"])!=before:self.recent.clear()
        self.recent.append(e)
        for length in (2,3):
            if len(self.recent)<length:continue
            seq=list(self.recent)[-length:];key=tuple(r["action"] for r in seq)
            if key not in self.tools and len(self.tools)>=64:continue
            d=tuple(y-x for x,y in zip(seq[0]["before"],seq[-1]["after"]))
            s=tuple(seq[0]["before"])
            t=self.tools.setdefault(key,dict(contexts={},attempts=0))
            t["attempts"]+=1;t["contexts"][s]=d
    def tool_report(self):
        result=[]
        for seq,v in self.tools.items():
            counts=Counter(v["contexts"].values())
            if len(v["contexts"])>=2 and len(counts)==1 and next(iter(counts))!=(0,)*len(next(iter(counts))):
                result.append(dict(actions=seq,effect=next(iter(counts)),distinct_starts=len(v["contexts"]),attempts=v["attempts"],status="observed_consistent_not_proven"))
        return sorted(result,key=lambda r:(-r["distinct_starts"],r["actions"]))[:24]
    def plan(self,s):
        # A local, bounded counterexample/uncertainty inquiry. Never a supplied map target.
        q=deque([(s,())]);seen={s};best=None
        while q:
            p,route=q.popleft()
            for a in self.actions:
                pred,source=self.agent.predict(p,a)
                unseen=(p,a) not in self.agent.edges
                c=self.self_model[a];error=(c["wrong"]+1)/(c["attempts"]+2)
                score=2*unseen+int(pred is None)+error+1/(1+self.agent.visits[p])-0.45*len(route)
                if best is None or score>best["value"]:
                    best=dict(question=[p,a],route=route+(a,),value=score,source=source)
                # Plans use observed transitions only; no arbitrary unverified movement.
                t=self.agent.edges.get((p,a))
                if t is not None and t not in seen and len(route)<2 and len(seen)<64:
                    seen.add(t);q.append((t,route+(a,)))
        return best
    def tick(self,env,mode="hybrid"):
        if self.total>=LIMIT:raise ValueError("event quota")
        s=tuple(env.observe());plan=None
        if mode=="inquiry":
            plan=self.plan(s);a=plan["route"][0];scores={a:plan["value"]}
        elif mode=="hybrid":a,scores=self.agent.choose(s)
        elif mode=="random":a=self.agent.rng.choice(self.actions);scores={}
        else:raise ValueError("mode")
        t=tuple(env.act(a));e=self.agent.observe(s,a,t,scores)
        e["question"]=plan;e["mode"]=mode
        e=frozen(e)
        with self.mem.db:
            cur=self.mem.db.execute("INSERT INTO v492_events(scope,event) VALUES(?,?)",(self.scope,json.dumps(e,separators=(",",":"))))
        self.record(e);return dict(id=cur.lastrowid,**e)
    def skills(self):return self.registry.respond("mostre habilidades")["skills"]
    def snapshot(self):
        e=self.agent.edges;visited=sorted({s for s,a in e}|set(e.values()))
        return dict(total=self.total,visited=visited,transitions=len(e),blocked_edges=[dict(position=s,action=a) for (s,a),t in e.items() if s==t],
            events=self.events(),models=self.agent.models,factor_models=self.agent.cache,self_model={a:dict(v) for a,v in self.self_model.items()},
            outcomes=dict(self.outcomes),tools=self.tool_report(),skills=self.skills(),
            cost=dict(base=self.agent.cost,factor=self.agent.factor_cost),memory=self.mem.counts())
    def respond(self,message):
        t=normalize(message)
        if t in ("qual e seu estado","o que voce sabe","quais sao seus limites","mostre suas hipoteses","mostre ferramentas"):
            s=self.snapshot()
            keys={"qual e seu estado":("total","outcomes","memory"),"o que voce sabe":("transitions","models","factor_models"),"quais sao seus limites":("self_model","outcomes"),"mostre suas hipoteses":("models","factor_models"),"mostre ferramentas":("tools","skills")}[t]
            return dict(status="observational",**{k:s[k] for k in keys})
        return self.registry.respond(message)
    def learn(self,document):return self.registry.learn(document)
    def learn_pipeline(self,name,doc,mode="base"):
        if type(name) is not str or not name.isidentifier() or not 1<=len(name)<=32:raise ValueError("name")
        if self.mem.get("pipeline:492",name) is not None:raise ValueError("duplicate")
        # External documentation is a bounded input/output contract, not executable text.
        if type(doc) is not dict or set(doc)!={"source","fit","pool","audit"} or type(doc["source"]) is not str or not 1<=len(doc["source"])<=200:raise ValueError("document")
        rows=[];seen=set()
        for k,lo,hi in (("fit",3,3),("pool",3,12),("audit",3,12)):
            if type(doc[k]) is not list or not lo<=len(doc[k])<=hi:raise ValueError("rows")
            part=[]
            for x,y in doc[k]:
                if type(x) not in (tuple,list) or not 1<=len(x)<=32 or any(type(v) is not int or abs(v)>10000 for v in x):raise ValueError("input")
                x=tuple(x)
                if x in seen:raise ValueError("duplicate input")
                seen.add(x)
                if type(y) in (tuple,list):
                    if len(y)>32 or any(type(v) is not int or abs(v)>1000000 for v in y):raise ValueError("output")
                    y=tuple(y)
                elif y is not None and (type(y) is not int or abs(y)>10000000):raise ValueError("output")
                part.append((x,y))
            rows.append(part)
        fit,pool,audit=rows
        r=solve(fit,Oracle(pool),LIB,(),mode);p=r["program"]
        accepted=bool(p and all(execute(p,x)==y for x,y in audit))
        result=dict(status="document-audited" if accepted else "rejected",source=doc["source"],search=r,program=p if accepted else None)
        self.mem.put("pipeline:492",name,result);return result
    def pipeline_apply(self,name,x):
        record=self.mem.get("pipeline:492",name)
        if not record or not record["program"]:raise ValueError("unvalidated")
        return execute(record["program"],x)
    def pipeline_code(self,name):
        record=self.mem.get("pipeline:492",name)
        if not record or not record["program"]:raise ValueError("unvalidated")
        return export(record["program"])
    def solve_list(self,fit,audit):
        # Existing V215 list grammar remains available, with separately audited examples.
        return list_synthesis.solve(fit,audit,"direct")
    def close(self):self.registry.close()
