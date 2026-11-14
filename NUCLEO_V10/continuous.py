"""V10: persistent, budgeted symbolic learning over a stream of tasks."""
import argparse,itertools,json,random,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V9_1"))
import binding as b
v9=b.v9
SEEDS=(1980011,2010013,2040017)
POLICIES=("fixed","no_memory","frozen","continuous")
N=32
TOTAL=320000
BASE=600
BIND=3000
MAX_TASK=24600
EVAL_CAP=3600

def signature(t):
    return tuple(b.target(t,x,y) for x in range(-5,6) for y in range(-5,6))

def suite(seed):
    rng=random.Random(seed);order=list(v9.MOTIFS);rng.shuffle(order)
    train=[];final=[];seen=set()
    def add(f,p,q,phase):
        t=dict(id=f"{seed}/{phase}/{len(train) if phase=='train' else len(final)}",motif=f,transform=(*p,*q),family="linked" if f in v9.MOTIFS else f)
        sig=signature(t)
        if sig in seen:return False
        seen.add(sig);(train if phase=="train" else final).append(t);return True
    def variants(f,n,phase):
        pool=list(itertools.product(b.TRANSFORMS,repeat=2));rng.shuffle(pool)
        for p,q in pool:
            if add(f,p,q,phase):n-=1
            if not n:return
        raise ValueError("insufficient distinct tasks")
    for k in range(0,8,2):
        fs=order[k:k+2]
        for f in fs:assert add(f,(1,0),(1,0),"train")
        for f in fs:variants(f,3,"train")
    for f in order:variants(f,3,"final")
    for f in ("unrelated","outside"):variants(f,4,"final")
    rng.shuffle(final)
    assert len(train)==len(final)==N
    return train,final

def allowance(remaining,steps_left,policy):
    if steps_left<1 or remaining<BASE*steps_left:raise ValueError("invalid budget")
    if policy=="fixed":return min(EVAL_CAP,remaining-BASE*(steps_left-1))
    # Reserve at least the initial search for each future problem.
    # Early failures can draw up to 2x the current average budget.
    return min(MAX_TASK,2*(remaining//steps_left),remaining-BASE*(steps_left-1))

def solve(obs,answers,registry,cap):
    start=time.perf_counter_ns();stages=[];e=None
    def attempt(name,limit,fn):
        nonlocal e
        if limit<=0:return
        e,n=fn(limit);stages.append(dict(method=name,spent=n,limit=limit,found=e is not None))
    def left():return cap-sum(x["spent"] for x in stages)
    attempt("cold",min(BASE,cap),lambda n:v9.synthesize(obs,answers,n))
    if e is None:
        attempt("binding",min(BIND,left()),lambda n:b.bind_search(obs,answers,registry,n))
    if e is None and left()>0:
        attempt("deeper_symbolic",left(),lambda n:v9.synthesize(obs,answers,n,registry))
    used=sum(x["spent"] for x in stages)
    assert used<=cap
    return e,dict(stages=stages,candidates=used,cap=cap,search_ns=time.perf_counter_ns()-start)

def evaluate(t,seed,reg,cap):
    obs,held=v9.observations(seed)
    ys=[b.target(t,x,y) for x,y in obs]
    e,m=solve(obs,ys,reg,cap)
    answers=[b.target(t,x,y) for x,y in held]
    ok=v9.check(e,held,answers,reg)
    expanded=v9.expand(e,reg) if e is not None else None
    def opcodes(e):
        if e is None:return []
        return ([e[0]] if e[0] in reg else [])+[x for c in e[1:] if isinstance(c,tuple) for x in opcodes(c)]
    return dict(task=t,success=ok,emitted=e is not None,candidate=e,expanded=expanded,
        opcodes=opcodes(e),observations=list(zip(obs,ys)),validation=list(zip(held,answers)),**m)

def eligible(row,policy,step):
    # New entries only from independently checked, nontrivial discoveries,
    # not from a transformation that already relied on a learned opcode.
    return policy in ("continuous","frozen") and (policy!="frozen" or step<8) and row["success"] and not row["opcodes"] and v9.nodes(row["expanded"])>=4

class Agent:
    def __init__(self,path,seed,policy):
        self.path=path;self.seed=seed;self.policy=policy
        self.reg=v9.Registry(path);self.db=self.reg.db
        self.db.executescript("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS episodes(step INTEGER PRIMARY KEY,payload TEXT);")
        identity=v9.enc([seed,policy,TOTAL])
        old=self.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
        if old and old[0]!=identity:raise ValueError("identity mismatch")
        if not old:
            self.db.execute("INSERT INTO meta VALUES('identity',?)",(identity,));self.db.commit()
    def history(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM episodes ORDER BY step")]
    def state(self):
        history=self.history();return dict(step=len(history),remaining=TOTAL-sum(r["candidates"] for r in history),reg=self.reg.snapshot())
    def train(self,t,seed):
        state=self.state();step=state["step"];remain=state["remaining"]
        cap=allowance(remain,N-step,self.policy)
        start=time.perf_counter_ns()
        row=evaluate(t,seed,state["reg"],cap)
        registered=False
        if eligible(row,self.policy,step):
            pairs,answers=zip(*row["validation"])
            registered=self.reg.register(row["expanded"],t["id"],pairs,answers)
        row.update(step=step,registered=registered,remaining=remain-row["candidates"],
            skills=len(self.reg.snapshot()),total_ns=time.perf_counter_ns()-start)
        self.db.execute("INSERT INTO episodes VALUES(?,?)",(step,v9.enc(row)));self.db.commit()
        return row
    def close(self):self.reg.close()

def stats(rows):
    n=len(rows);ok=sum(r["success"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=n,correct=ok,wrong=emitted-ok,abstained=n-emitted,
        candidates=sum(r["candidates"] for r in rows),mean_candidates=sum(r["candidates"] for r in rows)/n,
        mean_search_ns=sum(r["search_ns"] for r in rows)/n,
        reused_correct=sum(r["success"] and bool(r["opcodes"]) for r in rows),
        registered=sum(r.get("registered",False) for r in rows))

def run(folder):
    folder.mkdir(parents=True,exist_ok=False);rows=[];states=[]
    for seed in SEEDS:
        train,final=suite(seed)
        for policy in POLICIES:
            p=folder/f"{seed}_{policy}.sqlite3";agent=Agent(p,seed,policy)
            for step in range(N+1):
                if step in (0,N):
                    state=agent.state();before=v9.digest(state);reg=state["reg"]
                    for i,t in enumerate(final):
                        rr=evaluate(t,seed*17+i*971,reg,EVAL_CAP)
                        rows.append(dict(seed=seed,policy=policy,phase="final",checkpoint=step,**rr))
                    assert v9.digest(agent.state())==before
                    if step==N:states.append(dict(seed=seed,policy=policy,**state,sha256=before))
                if step==N:break
                rr=agent.train(train[step],seed+step*701);rows.append(dict(seed=seed,policy=policy,phase="train",checkpoint=step+1,**rr))
                if step==15:
                    before=v9.digest(agent.state());agent.close();agent=Agent(p,seed,policy)
                    assert before==v9.digest(agent.state())
            agent.close()
    agg=[dict(policy=p,checkpoint=k,**stats([r for r in rows if r["phase"]=="final" and r["policy"]==p and r["checkpoint"]==k])) for p in POLICIES for k in (0,N)]
    train_stats=[dict(policy=p,**stats([r for r in rows if r["phase"]=="train" and r["policy"]==p])) for p in POLICIES]
    by_family=[dict(policy=p,family=f,**stats([r for r in rows if r["phase"]=="final" and r["checkpoint"]==N and r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in ("linked","unrelated","outside")]
    result=dict(protocol="V10-continuous-v1",seeds=SEEDS,episodes=len(rows),train_budget_per_agent=TOTAL,aggregate=agg,training=train_stats,by_family=by_family,
        agents=[dict(seed=s["seed"],policy=s["policy"],remaining=s["remaining"],skills=len(s["reg"]),sha256=s["sha256"]) for s in states])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"states.json").write_text(json.dumps(states,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(v9.enc(r)+"\n")
    print("SUMMARY_V10="+v9.enc(result))

class Tests(unittest.TestCase):
    def test_budget(self):
        for policy in POLICIES:
            remaining=TOTAL
            for n in range(N,0,-1):
                k=allowance(remaining,n,policy)
                self.assertGreaterEqual(k,BASE);remaining-=k
            self.assertGreaterEqual(remaining,0)
    def test_suite(self):
        for seed in SEEDS:
            a,b=suite(seed);self.assertEqual((len(a),len(b)),(N,N))
            self.assertEqual(len({signature(t) for t in a+b}),2*N)
    def test_solve(self):
        obs,held=v9.observations(2);e,m=solve(obs,[x+y for x,y in obs],{},3600)
        self.assertTrue(v9.check(e,held,[x+y for x,y in held],{}))
        self.assertLessEqual(m["candidates"],3600)
    def test_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"agent.db";a=Agent(p,1,"continuous")
            old=v9.digest(a.state());a.close();a=Agent(p,1,"continuous")
            self.assertEqual(old,v9.digest(a.state()));a.close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V10 required")
    run(a.output)
