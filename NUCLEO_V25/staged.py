"""V25: staged program repertoire expansion and auditing in the finite list DSL."""
import argparse,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V24"))
import reuse as m
v=m.v
SEEDS=(3720017,3750023,3780031,3810041)
POLICIES=("full3","base_expand","memory_expand","memory_only","memory_audit")
CAP=v.CAP

def solve(initial,observed,pool,ask,policy,learned=()):
    evidence=dict(zip(initial,observed));remaining=list(pool)
    base=tuple(v.FULL);memory=tuple(dict.fromkeys((*base,*m.compose(learned))))
    full=tuple(m.FULL3)
    stages={"full3":[full],"base_expand":[base,full],
            "memory_expand":[memory,full],"memory_only":[memory],
            "memory_audit":[memory,full]}[policy]
    cache={};examined=set();candidates=[];trace=[];expansions=0;stage=0
    cost=dict(executions=0,primitives=0,cache_hits=0)
    def predict(p,x):
        key=(p,x)
        if key in cache:
            cost["cache_hits"]+=1
        else:
            cache[key]=v.execute(p,x);cost["executions"]+=1;cost["primitives"]+=len(p)
        return cache[key]
    def add(grammar):
        for p in grammar:
            if p in examined:continue
            examined.add(p)
            if all(predict(p,x)==y for x,y in evidence.items()):candidates.append(p)
    def groups():
        classes={}
        for p in sorted(candidates,key=lambda p:(len(p),p)):
            sig=tuple(predict(p,x) for x in remaining)
            classes.setdefault(sig,p)
        return classes
    add(stages[0])
    for i in range(CAP+1):
        if stage+1<len(stages) and (not candidates or (policy=="memory_audit" and i>=3)):
            stage+=1;expansions+=1;add(stages[stage])
        if not candidates or i==CAP:break
        classes=groups();best=-1;index=None
        for j,x in enumerate(remaining):
            counts={}
            for sig in classes:
                counts[sig[j]]=counts.get(sig[j],0)+1
            score=len(classes)**2-sum(n*n for n in counts.values())
            if score>best:best,index=score,j
        x=remaining.pop(index);y=ask(x);evidence[x]=y
        before=len(candidates)
        candidates=[p for p in candidates if predict(p,x)==y]
        trace.append(dict(input=x,output=y,before=before,after=len(candidates),stage=stage))
    classes=groups()
    p=next(iter(classes.values())) if len(classes)==1 else None
    return dict(program=p,trace=trace,queries=len(trace),expansions=expansions,
        remaining=len(classes),examined=len(examined),**cost)

def metric(rr):
    ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
    return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
        **{k:sum(r[k] for r in rr) for k in ("queries","expansions","examined","executions","primitives","cache_hits","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed)
        train,final=m.suite(seed,(*initial,*pool,*held))
        start=time.perf_counter_ns()
        prepared,prep_cost=v.prepare(v.FULL,initial,pool)
        prep_ns=time.perf_counter_ns()-start
        path=out/f"{seed}.sqlite3";store=m.Memory(path)
        for i,t in enumerate(train):
            rr=m.episode(t,initial,pool,held,prepared,seed+i*701,"train")
            added=rr["success"] and store.add(rr["program"],t["id"])
            training.append(dict(seed=seed,added=added,**rr))
        learned=store.snapshot();store.close();store=m.Memory(path)
        assert store.snapshot()==learned
        start=time.perf_counter_ns();macro=m.compose(learned)
        build_ns=time.perf_counter_ns()-start
        snapshots.append(dict(seed=seed,skills=len(learned),sha=m.digest(learned),
             programs=learned,compositions=len(macro),train_preparation_executions=prep_cost,
             train_preparation_ns=prep_ns,macro_build_ns=build_ns))
        for t in final:
            target=t["program"];observed=m.sig(target,initial)
            for policy in POLICIES:
                start=time.perf_counter_ns()
                row=solve(initial,observed,pool,lambda x:m.execute_target(target,x),policy,learned)
                elapsed=time.perf_counter_ns()-start;p=row["program"]
                ok=p is not None and m.sig(p,held)==m.sig(target,held)
                rows.append(dict(seed=seed,task=t,policy=policy,success=ok,
                    emitted=p is not None,wall_ns=elapsed,**row))
        assert store.snapshot()==learned;store.close()
    result=dict(protocol="V25-staged-programs-v1",seeds=SEEDS,snapshots=snapshots,
        training=dict(n=len(training),correct=sum(r["success"] for r in training),
                      added=sum(r["added"] for r in training),comparisons=sum(r["comparisons"] for r in training),
                      wall_ns=sum(r["wall_ns"] for r in training)),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in m.STRATA for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    baseline={(r["seed"],r["task"]["id"]):r for r in rows if r["policy"]=="full3"}
    result["paired_vs_full3"]={}
    for policy in POLICIES[1:]:
        rr=[r for r in rows if r["policy"]==policy]
        result["paired_vs_full3"][policy]=dict(
            gains=sum(r["success"] and not baseline[r["seed"],r["task"]["id"]]["success"] for r in rr),
            losses=sum(not r["success"] and baseline[r["seed"],r["task"]["id"]]["success"] for r in rr))
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for r in data:f.write(m.enc(r)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_bounds(self):
        a,b,c=v.input_sets(SEEDS[0])
        goal=("positive","sort","inc");obs=m.sig(goal,a)
        for policy in POLICIES:
            rr=solve(a,obs,b,lambda x:v.execute(goal,x),policy,(("positive","sort"),))
            points=[r["input"] for r in rr["trace"]]
            self.assertLessEqual(len(points),CAP)
            self.assertEqual(len(points),len(set(points)))
            self.assertFalse(set(points)&set(c))
            self.assertLessEqual(rr["examined"],len(m.FULL3))
            self.assertLessEqual(rr["expansions"],1)
            if rr["program"] is not None:
                self.assertTrue(all(v.execute(rr["program"],x)==v.execute(goal,x) for x in (*a,*points)))
    def test_audit(self):
        a,b,c=v.input_sets(SEEDS[0])
        rr=solve(a,m.sig((),a),b,lambda x:x,"memory_audit",())
        self.assertEqual(rr["expansions"],1)
        self.assertEqual(rr["examined"],len(m.FULL3))
    def test_refuted(self):
        a,b,c=v.input_sets(SEEDS[0])
        impossible=lambda x:(999,)
        rr=solve(a,m.sig((),a),b,impossible,"base_expand")
        self.assertIsNone(rr["program"])
        self.assertEqual(rr["expansions"],1)
    def test_seeds(self):
        for s in SEEDS:
            a,b,c=v.input_sets(s);tr,te=m.suite(s,(*a,*b,*c))
            self.assertEqual((len(tr),len(te)),(12,36))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V25 required")
    run(z.output)
