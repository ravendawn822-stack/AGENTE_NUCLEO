"""V31: persistent bounded agent, mathematical and list environments."""
import argparse,json,random,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V30"))
import targeted_learning as l
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V22"))
import core as c
m,v,t=l.m,l.v,l.t
SEEDS=(4440017,4470023,4500031,4530041)
POLICIES=("continuous","reopened","no_retention")

def initial_state():
    return dict(cursor=0,phase="acquisition",math=[],lists={},attempted=[],requests=0)

def check_state(state):
    assert set(state)==set(initial_state())
    assert isinstance(state["cursor"],int) and state["cursor"]>=0
    assert state["phase"] in ("acquisition","final","done")
    assert len(state["attempted"])==len(set(state["attempted"]))==state["requests"]<=l.REQUEST_CAP
    assert set(state["lists"])<=set(state["attempted"])<=set(t.NAMES)
    assert all(t.valid(p) for p in state["lists"].values())
    parts=c.mem.freeze(state["math"])
    assert len(set(parts))==len(parts)
    assert all(p in c.e.LARGE and p not in c.e.SMALL for p in parts)

class Store:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL, sha TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, sha TEXT NOT NULL)")
        if self.db.execute("SELECT COUNT(*) FROM state").fetchone()[0]==0:
            s=initial_state()
            self.db.execute("INSERT INTO state VALUES(1,?,?)",(m.enc(s),m.digest(s)))
            self.db.commit()
        self.verify()
    def load(self):
        body,sha=self.db.execute("SELECT body,sha FROM state WHERE id=1").fetchone()
        state=json.loads(body);assert m.digest(state)==sha;check_state(state)
        return state
    def verify(self):
        state=self.load();prev="genesis";n=0;last=m.digest(initial_state())
        for seq,body,sha in self.db.execute("SELECT seq,payload,sha FROM events ORDER BY seq"):
            n+=1;payload=json.loads(body)
            assert seq==n and payload["previous"]==prev and payload["before"]==last
            assert sha==m.digest(payload)
            last=payload["after"];prev=sha
        assert n==state["cursor"] and last==m.digest(state)
        return prev
    def commit(self,before,after,event):
        check_state(after)
        assert after["cursor"]==before["cursor"]+1
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current=self.load();assert current==before
            row=self.db.execute("SELECT sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            payload=dict(previous=row[0] if row else "genesis",before=m.digest(before),after=m.digest(after),event=event)
            self.db.execute("INSERT INTO events VALUES(?,?,?)",(after["cursor"],m.enc(payload),m.digest(payload)))
            self.db.execute("UPDATE state SET body=?,sha=? WHERE id=1",(m.enc(after),m.digest(after)))
    def close(self):self.db.close()

def clean(row):
    return {k:z for k,z in row.items() if k not in ("wall_ns","comparisons","hypothesis_evaluations","symbolic_candidates")}

class Agent:
    def __init__(self,store,retain=True):
        self.store=store;self.retain=retain;self.state=store.load()
    def math_attempt(self,obs,ask):
        learned=c.mem.freeze(self.state["math"])
        start=time.perf_counter_ns()
        rr=c.investigate(obs,ask,"integrated_memory",learned)
        return dict(**rr,emitted=rr["candidate"] is not None,wall_ns=time.perf_counter_ns()-start)
    def list_attempt(self,initial,observed,pool,ask,registry,seed):
        prep,cost=l.prepare(registry,initial,pool)
        rr=l.investigate(initial,observed,pool,ask,registry,prep,seed)
        return dict(**rr,preparation_executions=cost["executions"])
    def math_episode(self,task,training,feedback):
        obs={p:c.target(task,p) for p in c.v.INITIAL}
        rr=self.math_attempt(obs,lambda p:c.target(task,p))
        candidate=rr["candidate"];ok=feedback(candidate)
        if training and ok and candidate[0]=="active":
            parts=candidate[1][1]
            existing=c.mem.freeze(self.state["math"])
            if parts in c.e.LARGE and parts not in c.e.SMALL and parts not in existing:
                self.state["math"]=json.loads(m.enc((*existing,parts)))
        return dict(**rr,success=ok,requests=0)
    def list_episode(self,task,initial,pool,held,teacher,seed):
        goal=task["program"];obs=tuple(t.target(goal,x) for x in initial)
        ask=lambda x:t.target(goal,x)
        registry={k:tuple(p) for k,p in self.state["lists"].items()}
        first=self.list_attempt(initial,obs,pool,ask,registry,seed)
        last=first;request=None;lesson_trace=[]
        if teacher is not None and not first["emitted"] and self.state["requests"]<l.REQUEST_CAP:
            request=l.choose_card(obs,teacher.cards,set(self.state["attempted"]),"targeted",random.Random(seed))
            if request is not None:
                self.state["attempted"].append(request);self.state["requests"]+=1
                skill,lesson_trace=teacher.request(request)
                if skill is not None:
                    registry[request]=skill
                    self.state["lists"][request]=list(skill)
                last=self.list_attempt(initial,obs,pool,ask,registry,seed)
        return dict(program=last["program"],emitted=last["emitted"],success=l.score(last,goal,held,registry),
            queries=first["queries"]+(last["queries"] if request else 0),
            comparisons=first["comparisons"]+(last["comparisons"] if request else 0),
            preparation_executions=first["preparation_executions"]+(last["preparation_executions"] if request else 0),
            wall_ns=first["wall_ns"]+(last["wall_ns"] if request else 0),
            trace=first["trace"],retry_trace=last["trace"] if request else [],
            requests=int(request is not None),topic=request,lesson_trace=lesson_trace)
    def commit_episode(self,before,domain,task_id,rr,next_phase):
        if not self.retain:
            self.state["math"]=[];self.state["lists"]={}
        self.state["cursor"]+=1;self.state["phase"]=next_phase
        event=dict(domain=domain,task_id=task_id,decision=rr.get("candidate",rr.get("program")),
                   emitted=rr["emitted"],queries=rr["queries"],
                   requests=rr["requests"],topic=rr.get("topic"))
        self.store.commit(before,self.state,event)

def environment(seed,packet):
    math_train,math_final=c.suite(seed^0x3110)
    math_train=[dict(domain="piecewise",**z) for z in math_train]
    li,lp,lh=v.input_sets(seed)
    fi,fp,fh=l.final_inputs(seed,(*li,*lp,*lh))
    points=t.teaching_points(seed,(*li,*lp,*lh,*fi,*fp,*fh))
    names,list_train=l.acquisition(seed,(*li,*lp,*lh))
    list_final=t.suite(seed,(*fi,*fp,*fh))
    train=[("math",z) for z in math_train]+[("lists",z) for z in list_train]
    final=[("math",z) for z in math_final]+[("lists",z) for z in list_final]
    random.Random(seed^0x3120).shuffle(train);random.Random(seed^0x3130).shuffle(final)
    assert (len(train),len(final))==(24,96)
    teacher=l.Teacher(packet,li,points,seed)
    return train,final,(li,lp,lh),(fi,fp,fh),teacher

def execute_stream(out,seed,policy,packet):
    train,final,acq,offline,teacher=environment(seed,packet)
    stream=train+final
    path=out/f"{seed}_{policy}.sqlite3";store=Store(path)
    agent=Agent(store,policy!="no_retention");rows=[];restart_count=0;frozen=None
    while agent.state["cursor"]<len(stream):
        i=agent.state["cursor"];training=i<len(train)
        assert agent.state["phase"]==("acquisition" if training else "final")
        before=json.loads(m.enc(agent.state));domain,task=stream[i]
        if domain=="math":
            rr=agent.math_episode(task,training,lambda h:c.consistent(h,{p:c.target(task,p) for p in c.e.RESERVED}))
        else:
            initial,pool,held=acq if training else offline
            rr=agent.list_episode(task,initial,pool,held,teacher if training else None,seed+i*971)
        next_phase="done" if i+1==len(stream) else "final" if i+1>=len(train) else "acquisition"
        agent.commit_episode(before,domain,task["id"],rr,next_phase)
        rows.append(dict(seed=seed,policy=policy,index=i,domain=domain,phase="acquisition" if training else "final",
                         task=task,**rr))
        if i+1==len(train):
            frozen=dict(math=agent.state["math"],lists=agent.state["lists"],requests=agent.state["requests"])
            frozen=json.loads(m.enc(frozen))
            teacher=None
        if not training:
            assert frozen=={k:agent.state[k] for k in frozen}
        if policy=="reopened":
            expected=m.digest(agent.state);store.close();store=Store(path);agent=Agent(store)
            assert m.digest(agent.state)==expected;restart_count+=1
    head=store.verify();state=store.load();store.close()
    return rows,dict(seed=seed,policy=policy,restarts=restart_count,state=state,head=head,sha=m.digest(state))

def metrics(rows):
    correct=sum(r["success"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    result=dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
                queries=sum(r["queries"] for r in rows),requests=sum(r["requests"] for r in rows),
                wall_ns=sum(r["wall_ns"] for r in rows))
    for k in ("hypothesis_evaluations","symbolic_candidates","comparisons","preparation_executions"):
        result[k]=sum(r.get(k,0) for r in rows)
    return result

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text())
    rows=[];snapshots=[];equivalence=[]
    for seed in SEEDS:
        local={};ss={}
        for policy in POLICIES:
            rr,snapshot=execute_stream(out,seed,policy,packet)
            local[policy]=rr;ss[policy]=snapshot;rows.extend(rr);snapshots.append(snapshot)
        def comparable(rr):return [{k:z for k,z in r.items() if k not in ("policy","wall_ns")} for r in rr]
        same=comparable(local["continuous"])==comparable(local["reopened"])
        state_same=ss["continuous"]["sha"]==ss["reopened"]["sha"]
        chain_same=ss["continuous"]["head"]==ss["reopened"]["head"]
        equivalence.append(dict(seed=seed,decisions_and_costs_equal=same,state_equal=state_same,chain_equal=chain_same))
        assert same and state_same and chain_same
    final=[r for r in rows if r["phase"]=="final"]
    result=dict(protocol="V31-persistent-multidomain-v1",seeds=SEEDS,snapshots=snapshots,equivalence=equivalence,
        aggregate=[dict(policy=p,**metrics([r for r in final if r["policy"]==p])) for p in POLICIES],
        by_domain=[dict(domain=d,policy=p,**metrics([r for r in final if r["domain"]==d and r["policy"]==p])) for d in ("math","lists") for p in POLICIES],
        acquisition=[dict(domain=d,policy=p,**metrics([r for r in rows if r["phase"]=="acquisition" and r["domain"]==d and r["policy"]==p])) for d in ("math","lists") for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for rr in rows:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_store(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.db";store=Store(p);a=store.load()
            b=dict(a,cursor=1);store.commit(a,b,dict(decision="test"))
            head=store.verify();store.close();store=Store(p)
            self.assertEqual(store.load(),b);self.assertEqual(store.verify(),head)
            with self.assertRaises(AssertionError):store.commit(a,b,dict(decision="stale"))
            self.assertEqual(store.verify(),head);store.close()
    def test_environment(self):
        packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text())
        train,final,acq,offline,teacher=environment(SEEDS[0],packet)
        self.assertEqual((len(train),len(final)),(24,96))
        self.assertFalse({x for g in acq for x in g}&{x for g in offline for x in g})
        self.assertEqual(sum(d=="math" for d,z in final),72)
    def test_validation(self):
        bad=initial_state();bad["lists"]={"total":["unknown"]}
        with self.assertRaises(AssertionError):check_state(bad)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V31 required")
    run(z.output)
