"""V19: bounded falsification after identification in a finite mathematical world."""
import argparse,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V18"))
import perception as v
SEEDS=(3000017,3030023,3060031,3090041)
POLICIES=("early","random_verify","extreme_verify","fixed")
CAP=6
FIXED=(*v.FIXED,(12,0),(0,12))

def ray(p):
    return (0,1 if p[0]>0 else -1) if p[0] else (1,1 if p[1]>0 else -1)

def extreme(remaining,queried):
    counts={ray(p):0 for p in v.POOL}
    for p in queried:counts[ray(p)]+=1
    return min(remaining,key=lambda p:(counts[ray(p)],-sum(abs(x) for x in p),p))

def investigate(observed,ask,policy,seed):
    candidates=v.initial_hypotheses(observed)
    rng=random.Random(seed);remaining=list(v.POOL)
    trace=[];cost=0
    for i in range(CAP):
        if not candidates or (policy=="early" and len(candidates)==1):break
        if policy=="fixed":
            point=FIXED[i];phase="fixed"
        elif len(candidates)>1:
            point,n=v.informative(candidates,remaining)
            cost+=n;phase="identify"
        elif policy=="random_verify":
            point=rng.choice(remaining);phase="refute"
        else:
            point=extreme(remaining,[r["point"] for r in trace]);phase="refute"
        assert point in remaining
        remaining.remove(point)
        before=len(candidates);response=ask(point)
        candidates=[h for h in candidates if v.value(h,point)==response]
        cost+=before
        trace.append(dict(point=point,response=response,phase=phase,before=before,after=len(candidates)))
    return (candidates[0] if len(candidates)==1 else None),trace,cost,len(candidates)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in SEEDS:
        for i,t in enumerate(v.tasks(seed)):
            obs={p:v.target(t,p) for p in v.INITIAL};proposals={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                e,trace,cost,n=investigate(obs,lambda p:v.target(t,p),policy,seed+i*701)
                proposals[policy]=(e,trace,cost,n,time.perf_counter_ns()-start)
            for policy,(e,trace,cost,n,elapsed) in proposals.items():
                ok=e is not None and all(v.value(e,p)==v.target(t,p) for p in v.RESERVED)
                rows.append(dict(seed=seed,task=t,policy=policy,candidate=e,emitted=e is not None,
                    success=ok,queries=len(trace),trace=trace,remaining=n,
                    refutations=sum(r["before"]==1 and r["after"]==0 for r in trace),
                    hypothesis_evaluations=cost,wall_ns=elapsed))
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            queries=sum(r["queries"] for r in rr),refutations=sum(r["refutations"] for r in rr),
            hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in rr),
            wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V19-falsification-v1",seeds=SEEDS,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["family"]==f])) for f in ("linear","single","quadratic","double") for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,separators=(",",":"))+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_extreme(self):
        self.assertEqual(ray(extreme([(15,0),(0,12)],[(12,0)])),(1,1))
    def test_bounds(self):
        self.assertTrue(set(SEEDS).isdisjoint(v.SEEDS))
        for t in v.tasks(SEEDS[0]):
            obs={p:v.target(t,p) for p in v.INITIAL}
            for policy in POLICIES:
                e,trace,cost,n=investigate(obs,lambda p:v.target(t,p),policy,1)
                points=[r["point"] for r in trace]
                self.assertLessEqual(len(points),CAP)
                self.assertEqual(len(points),len(set(points)))
                self.assertTrue(set(points)<=set(v.POOL))
                self.assertFalse(set(points)&set(v.RESERVED))
                self.assertEqual(e is not None,n==1)
    def test_in_grammar(self):
        t=dict(family="single",coefs=(1,-2,3),parts=((0,1,9,1),))
        obs={p:v.target(t,p) for p in v.INITIAL}
        for policy in ("early","random_verify","extreme_verify"):
            e,_,_,_=investigate(obs,lambda p:v.target(t,p),policy,9)
            self.assertIsNotNone(e)
            self.assertTrue(all(v.value(e,p)==v.target(t,p) for p in v.RESERVED))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V19 required")
    run(z.output)
