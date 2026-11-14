"""V20: finite hypothesis expansion after contradiction."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V18"))
import perception as v
SEEDS=(3120017,3150023,3180031,3210041)
POLICIES=("small","large","expand")
CAP=10
POOL=(*v.POOL,*itertools.product((-15,15),repeat=2))
RESERVED=tuple(p for p in v.RESERVED if p not in set(POOL))
FAMILIES=("linear","single","quadratic","double","interaction")
SINGLE=tuple(("linear_hinge",h) for h in v.HINGES)
SMALL=((),*((h,) for h in SINGLE))
LARGE=(*SMALL, *((("square_hinge",h),) for h in v.HINGES),
       *((a,b) for a in SINGLE for b in SINGLE if a[1][0]==0 and b[1][0]==1))

def value(h,p):
    coefs,parts=h
    a,b,c=coefs
    y=a*p[0]+b*p[1]+c
    for kind,part in parts:
        z=v.hinge(part,p)
        y+=z if kind=="linear_hinge" else z*z
    return y

def tasks(seed):
    out=v.tasks(seed)
    rng=random.Random(seed^0x2019)
    for i in range(4):
        parts=(rng.choice([h for h in v.HINGES if h[0]==0]),rng.choice([h for h in v.HINGES if h[0]==1]))
        coefs=tuple(rng.choice((-3,-2,-1,1,2,3)) for _ in range(3))
        out.append(dict(id=f"{seed}/interaction/{i}",family="interaction",coefs=coefs,parts=parts))
    rng.shuffle(out)
    return out

def target(t,p):
    if t["family"]!="interaction":return v.target(t,p)
    a,b,c=t["coefs"]
    return a*p[0]+b*p[1]+c+v.hinge(t["parts"][0],p)*v.hinge(t["parts"][1],p)

def direction(p):
    return tuple((z>0)-(z<0) for z in p)

def verify_point(remaining,trace):
    counts={direction(p):0 for p in POOL}
    for r in trace:counts[direction(r["point"])]+=1
    return min(remaining,key=lambda p:(counts[direction(p)],-sum(abs(z) for z in p),p))

def investigate(observed,ask,policy):
    obs=dict(observed);trace=[];cost=0;expanded=False
    coefs=(obs[(1,0)]-obs[(0,0)],obs[(0,1)]-obs[(0,0)],obs[(0,0)])
    def filter_all(hypotheses,evidence):
        nonlocal cost
        out=[]
        for h in hypotheses:
            match=True
            for p,y in evidence.items():
                cost+=1
                if value(h,p)!=y:
                    match=False;break
            if match:out.append(h)
        return out
    def new_set(parts):
        return filter_all(((coefs,h) for h in parts),obs)
    candidates=new_set(LARGE if policy=="large" else SMALL)
    remaining=list(POOL)
    for i in range(CAP+1):
        if not candidates and policy=="expand" and not expanded:
            candidates=new_set(LARGE);expanded=True
        if not candidates or i==CAP:break
        if len(candidates)>1:
            best=-1;point=None
            for p in remaining:
                groups={}
                for h in candidates:
                    pred=value(h,p);groups[pred]=groups.get(pred,0)+1;cost+=1
                score=len(candidates)**2-sum(n*n for n in groups.values())
                if score>best:best,point=score,p
            phase="identify"
        else:
            point=verify_point(remaining,trace);phase="refute"
        remaining.remove(point)
        response=ask(point);obs[point]=response;before=len(candidates)
        candidates=filter_all(candidates,{point:response})
        trace.append(dict(point=point,response=response,phase=phase,before=before,after=len(candidates)))
    return (candidates[0] if len(candidates)==1 else None),trace,cost,expanded,len(candidates)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in SEEDS:
        for t in tasks(seed):
            obs={p:target(t,p) for p in v.INITIAL};results={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                e,trace,cost,expanded,n=investigate(obs,lambda p:target(t,p),policy)
                results[policy]=(e,trace,cost,expanded,n,time.perf_counter_ns()-start)
            for policy,(e,trace,cost,expanded,n,elapsed) in results.items():
                ok=e is not None and all(value(e,p)==target(t,p) for p in RESERVED)
                rows.append(dict(seed=seed,task=t,policy=policy,candidate=e,emitted=e is not None,
                    success=ok,queries=len(trace),trace=trace,expanded=expanded,remaining=n,
                    hypothesis_evaluations=cost,wall_ns=elapsed))
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            queries=sum(r["queries"] for r in rr),expansions=sum(r["expanded"] for r in rr),
            hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in rr),wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V20-finite-expansion-v1",seeds=SEEDS,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in FAMILIES for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,separators=(",",":"))+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(len(set(SMALL)),25)
        self.assertEqual(len(set(LARGE)),193)
        self.assertFalse(set(RESERVED)&(set(POOL)|set(v.INITIAL)))
    def test_expansion(self):
        t=dict(family="quadratic",coefs=(1,-2,3),parts=((0,1,9,1),))
        obs={p:target(t,p) for p in v.INITIAL}
        e,trace,cost,expanded,n=investigate(obs,lambda p:target(t,p),"expand")
        self.assertTrue(expanded)
        self.assertTrue(e is None or all(value(e,p)==target(t,p) for p in [*v.INITIAL,*[r["point"] for r in trace]]))
    def test_bounds(self):
        for seed in SEEDS:self.assertEqual(len(tasks(seed)),36)
        for t in tasks(SEEDS[0]):
            obs={p:target(t,p) for p in v.INITIAL}
            for policy in POLICIES:
                e,trace,cost,expanded,n=investigate(obs,lambda p:target(t,p),policy)
                pts=[r["point"] for r in trace]
                self.assertLessEqual(len(pts),CAP)
                self.assertEqual(len(set(pts)),len(pts))
                self.assertTrue(set(pts)<=set(POOL))
                self.assertEqual(e is not None,n==1)
                self.assertFalse(expanded and policy!="expand")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V20 required")
    run(z.output)
