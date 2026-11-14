"""V23: bounded list program synthesis from observations, not source code."""
import argparse,itertools,json,random,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=(3480017,3510023,3540031,3570041)
OPS=("abs","neg","inc","positive","even","reverse","sort","unique","take2","drop1","rotate","difference")
INITIAL=((),(1,),(-2,3,0,1),(2,2,-1))
POLICIES=("single_fixed","full_fixed","full_random","full_active")
CAP=6
SMALL=((),*((op,) for op in OPS))
FULL=(*SMALL,*itertools.product(OPS,repeat=2))

def execute(program,x):
    if len(program)>3 or any(op not in OPS for op in program):raise ValueError("invalid program")
    a=tuple(x)
    for op in program:
        if op=="abs":a=tuple(abs(z) for z in a)
        elif op=="neg":a=tuple(-z for z in a)
        elif op=="inc":a=tuple(z+1 for z in a)
        elif op=="positive":a=tuple(z for z in a if z>0)
        elif op=="even":a=tuple(z for z in a if z%2==0)
        elif op=="reverse":a=a[::-1]
        elif op=="sort":a=tuple(sorted(a))
        elif op=="unique":a=tuple(dict.fromkeys(a))
        elif op=="take2":a=a[:2]
        elif op=="drop1":a=a[1:]
        elif op=="rotate":a=a[1:]+a[:1]
        elif op=="difference":a=tuple(b-c for c,b in zip(a,a[1:]))
    return a

def input_sets(seed):
    rng=random.Random(seed)
    seen=set(INITIAL);other=[]
    while len(other)<112:
        x=tuple(rng.randint(-3,3) for _ in range(rng.randint(0,5)))
        if x not in seen:seen.add(x);other.append(x)
    return INITIAL,tuple(other[:32]),tuple(other[32:])

def signature(program,points):
    return tuple(execute(program,x) for x in points)

def tasks(seed,points):
    rng=random.Random(seed^0x2317);rows=[];seen=set()
    groups=[("single",list(SMALL[1:]),8),("composed",list(FULL[len(SMALL):]),12),
            ("outside",list(itertools.product(OPS,repeat=3)),4)]
    excluded={signature(p,points) for p in SMALL}
    full_signatures={signature(p,points) for p in FULL}
    for family,programs,n in groups:
        rng.shuffle(programs);count=0
        for p in programs:
            sig=signature(p,points)
            if sig in seen or sig==signature((),points):continue
            if family=="composed" and sig in excluded:continue
            if family=="outside" and sig in full_signatures:continue
            seen.add(sig)
            rows.append(dict(id=f"{seed}/{family}/{count}",family=family,program=p))
            count+=1
            if count==n:break
        assert count==n
    rng.shuffle(rows);return rows

def prepare(grammar,initial,pool):
    points=(*initial,*pool)
    groups={}
    # Only predictions on public inputs, never evaluator outputs.
    for p in sorted(grammar,key=lambda x:(len(x),x)):
        sig=signature(p,points)
        groups.setdefault(sig,p)
    return tuple((p,sig) for sig,p in groups.items()),len(grammar)*len(points)

def investigate(observed,pool,ask,policy,prepared,seed):
    width=len(observed);expected=tuple(observed)
    candidates=[(p,s) for p,s in prepared if s[:width]==expected]
    cost=len(prepared)*width;trace=[];remaining=list(range(len(pool)))
    rng=random.Random(seed)
    for _ in range(CAP):
        if not candidates:break
        if policy.endswith("active"):
            score=-1;index=None
            for i in remaining:
                counts={}
                for _,s in candidates:
                    pred=s[width+i];counts[pred]=counts.get(pred,0)+1;cost+=1
                new=len(candidates)**2-sum(k*k for k in counts.values())
                if new>score:score,index=new,i
        elif policy.endswith("random"):index=rng.choice(remaining)
        else:index=remaining[0]
        remaining.remove(index);x=pool[index];y=tuple(ask(x));before=len(candidates)
        candidates=[(p,s) for p,s in candidates if s[width+index]==y]
        cost+=before
        trace.append(dict(input=x,output=y,before=before,after=len(candidates)))
    p=candidates[0][0] if len(candidates)==1 else None
    return p,trace,cost,len(candidates)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];preparation=[]
    for seed in SEEDS:
        initial,pool,held=input_sets(seed)
        ts=tasks(seed,(*initial,*pool,*held))
        prepared={}
        for name,grammar in (("small",SMALL),("full",FULL)):
            start=time.perf_counter_ns()
            pr,cost=prepare(grammar,initial,pool)
            prepared[name]=pr
            preparation.append(dict(seed=seed,grammar=name,classes=len(pr),programs=len(grammar),
                program_executions=cost,wall_ns=time.perf_counter_ns()-start))
        for i,t in enumerate(ts):
            target=t["program"];observed=signature(target,initial);results={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                p,trace,cost,n=investigate(observed,pool,lambda x:execute(target,x),policy,
                      prepared["small" if policy.startswith("single") else "full"],seed+i*701)
                results[policy]=(p,trace,cost,n,time.perf_counter_ns()-start)
            for policy,(p,trace,cost,n,elapsed) in results.items():
                ok=p is not None and signature(p,held)==signature(target,held)
                rows.append(dict(seed=seed,task=t,policy=policy,program=p,emitted=p is not None,
                    success=ok,queries=len(trace),trace=trace,remaining=n,
                    initial=list(zip(initial,observed)),comparisons=cost,wall_ns=elapsed))
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
                    queries=sum(r["queries"] for r in rr),comparisons=sum(r["comparisons"] for r in rr),
                    wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V23-list-synthesis-v1",seeds=SEEDS,preparation=preparation,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in ("single","composed","outside") for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r,separators=(",",":"))+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_operations(self):
        self.assertEqual(execute(("positive","sort"),(3,-2,1,-4)),(1,3))
        self.assertEqual(execute((),(1,-1)),(1,-1))
        with self.assertRaises(ValueError):execute(("unknown",),(1,))
        with self.assertRaises(ValueError):execute(("abs",)*4,(1,))
    def test_suite(self):
        for seed in SEEDS:
            a,b,c=input_sets(seed);points=(*a,*b,*c)
            self.assertEqual((len(a),len(b),len(c)),(4,32,80))
            self.assertEqual(len(set(points)),116)
            ts=tasks(seed,points)
            self.assertEqual(len(ts),24)
            self.assertEqual(len({signature(t["program"],points) for t in ts}),24)
    def test_investigation(self):
        initial,pool,held=input_sets(SEEDS[0]);prepared,_=prepare(FULL,initial,pool)
        goal=("positive","sort")
        p,trace,cost,n=investigate(signature(goal,initial),pool,lambda x:execute(goal,x),"full_active",prepared,1)
        self.assertLessEqual(len(trace),CAP)
        pts=[x["input"] for x in trace]
        self.assertEqual(len(pts),len(set(pts)))
        self.assertFalse(set(pts)&set(held))
        self.assertEqual(p is not None,n==1)
        if p is not None:self.assertTrue(all(execute(p,r["input"])==r["output"] for r in trace))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V23 required")
    run(z.output)
