"""V18: active observations distinguish finite mathematical hypotheses."""
import argparse,itertools,json,random,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=(2880017,2910023,2940031,2970041)
INITIAL=tuple(itertools.product(range(-2,3),repeat=2))
POOL=tuple((z,0) for z in (-15,-12,-9,-6,6,9,12,15))+tuple((0,z) for z in (-15,-12,-9,-6,6,9,12,15))
FIXED=((15,0),(-15,0),(0,15),(0,-15))
RESERVED=tuple(p for p in itertools.product((-23,-17,-13,-10,-8,-4,0,4,8,10,13,17,23),repeat=2) if p not in set(INITIAL)|set(POOL))
HINGES=tuple(itertools.product((0,1),(-1,1),(7,9,11),(1,2)))
POLICIES=("naive","no_query","fixed","random","informative")
LIMIT=4

def hinge(h,p):
    axis,d,threshold,amp=h
    return amp*max(0,d*p[axis]-threshold)

def value(h,p):
    a,b,c,part=h
    return a*p[0]+b*p[1]+c+(hinge(part,p) if part else 0)

def tasks(seed):
    rng=random.Random(seed)
    definitions=[("linear",())]+[("single",(h,)) for h in HINGES]
    hs=list(HINGES);rng.shuffle(hs)
    definitions += [("quadratic",(h,)) for h in hs[:4]]
    definitions += [("double",(hs[i],next(h for h in hs if h[0]!=hs[i][0]))) for i in range(4,7)]
    rng.shuffle(definitions)
    out=[]
    for i,(family,parts) in enumerate(definitions):
        coefs=tuple(rng.choice((-3,-2,-1,1,2,3)) for _ in range(3))
        out.append(dict(id=f"{seed}/{i}",family=family,coefs=coefs,parts=parts))
    return out

def target(t,p):
    a,b,c=t["coefs"]
    base=a*p[0]+b*p[1]+c
    if t["family"]=="quadratic":
        return base+sum(hinge(h,p)**2 for h in t["parts"])
    return base+sum(hinge(h,p) for h in t["parts"])

def initial_hypotheses(observed):
    c=observed[(0,0)];a=observed[(1,0)]-c;b=observed[(0,1)]-c
    return [h for h in [(a,b,c,None)]+[(a,b,c,k) for k in HINGES]
            if all(value(h,p)==y for p,y in observed.items())]

def informative(candidates,remaining):
    best=None;score=-1;cost=0
    for p in remaining:
        counts={}
        for h in candidates:
            v=value(h,p);counts[v]=counts.get(v,0)+1;cost+=1
        # Splitting a pair makes at least one member inconsistent with the next observation.
        separated=len(candidates)**2-sum(n*n for n in counts.values())
        if separated>score:best,score=p,separated
    return best,cost

def investigate(observed,ask,policy,seed):
    obs=dict(observed);candidates=initial_hypotheses(obs)
    trace=[];cost=0
    if policy=="naive":return (candidates[0] if candidates else None),trace,cost,len(candidates)
    if policy!="no_query":
        rng=random.Random(seed)
        remaining=list(POOL)
        for i in range(LIMIT):
            if len(candidates)<=1:break
            if policy=="fixed":p=FIXED[i]
            elif policy=="random":p=rng.choice(remaining)
            else:
                p,n=informative(candidates,remaining);cost+=n
            assert p in remaining
            remaining.remove(p)
            y=ask(p)
            before=len(candidates)
            candidates=[h for h in candidates if value(h,p)==y]
            cost+=before
            trace.append(dict(point=p,response=y,before=before,after=len(candidates)))
    return (candidates[0] if len(candidates)==1 else None),trace,cost,len(candidates)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in SEEDS:
        for i,t in enumerate(tasks(seed)):
            obs={p:target(t,p) for p in INITIAL}
            proposals={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                e,trace,cost,remaining=investigate(obs,lambda p:target(t,p),policy,seed+i*701)
                proposals[policy]=(e,trace,cost,remaining,time.perf_counter_ns()-start)
            for policy,(e,trace,cost,remaining,elapsed) in proposals.items():
                verified=e is not None and all(value(e,p)==target(t,p) for p in RESERVED)
                rows.append(dict(seed=seed,task=t,policy=policy,success=verified,
                    emitted=e is not None,remaining=remaining,candidate=e,
                    queries=len(trace),trace=trace,initial_observations=list(obs.items()),
                    hypothesis_evaluations=cost,wall_ns=elapsed))
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            queries=sum(r["queries"] for r in rr),
            hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in rr),
            wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V18-active-observation-v1",seeds=SEEDS,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in ("linear","single","quadratic","double") for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,separators=(",",":"))+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_tasks(self):
        for s in SEEDS:
            ts=tasks(s);self.assertEqual(len(ts),32)
            self.assertEqual(len({t["id"] for t in ts}),32)
            for t in ts:
                self.assertEqual(len(initial_hypotheses({p:target(t,p) for p in INITIAL})),25)
    def test_single(self):
        t=next(t for t in tasks(SEEDS[0]) if t["family"]=="single")
        e,trace,_,remaining=investigate({p:target(t,p) for p in INITIAL},lambda p:target(t,p),"fixed",9)
        self.assertEqual(remaining,1)
        self.assertTrue(all(value(e,p)==target(t,p) for p in RESERVED))
        self.assertLessEqual(len(trace),LIMIT)
    def test_bounds(self):
        self.assertFalse(set(RESERVED)&(set(POOL)|set(INITIAL)))
        for t in tasks(SEEDS[0]):
            for policy in POLICIES:
                e,trace,cost,_=investigate({p:target(t,p) for p in INITIAL},lambda p:target(t,p),policy,1)
                pts=[row["point"] for row in trace]
                self.assertLessEqual(len(pts),LIMIT)
                self.assertEqual(len(set(pts)),len(pts))
                self.assertTrue(set(pts)<=set(POOL))
                self.assertGreaterEqual(cost,0)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V18 required")
    run(z.output)
