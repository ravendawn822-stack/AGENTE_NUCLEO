"""Integrated self-model experiment, offline; no self-modification or external actions."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for version in (67,68,69,70,62,65):
    sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{version}"))
import self_estimate as reliability
import cost_model as cost
import gaps
import strategy
from revision import Revised
from transfer import predict as polynomial
SEEDS=tuple(18000019+30001*i for i in range(12))
EXTRA_BUDGET=24
MODES=("reference","integrated")

def models(points):
    exact=Revised("exact");repair=Revised("repair");mapping=Revised("map")
    for s,t in points:
        for m in (exact,repair,mapping):m.observe(0,s,t)
    return exact,repair,mapping

def decision(points,selector,estimator,remaining):
    exact,repair,mapping=models(points)
    key=strategy.context(exact,repair,0)
    if repair.models[0] is not None:
        choice,scores=selector.choose(key)
        model={"exact":exact,"repair":repair,"map":mapping}[choice]
        h=model.models[0]
        feat=reliability.features(repair,0)
        forecast=estimator.forecast(feat,"evidence") if choice=="repair" else None
        return dict(choice=choice,key=key,model=h,kind="affine",confidence=forecast,
                    gap=False,extra=0,rechecks=0,scores=scores)
    # One repeated affine fit is counted separately; the two additional
    # polynomial families consume the fixed external budget.
    if remaining<2:
        return dict(choice="map_budget",key=key,model=None,kind="affine",confidence=None,
                    gap=True,extra=0,rechecks=0,scores=None)
    result=gaps.inspect(points,"selective")
    return dict(choice="expand" if result["model"] is not None else "map_gap",
                key=key,model=result["model"],kind="polynomial",confidence=None,
                gap=result["gap"],extra=result["families"]-1,rechecks=1,scores=None)

def evaluate(data,d):
    h=d["model"]
    def f(s):
        if h is None:return None
        return polynomial(h,s) if d["kind"]=="polynomial" else (h[0]*s+h[1])%gaps.N
    pairs=[(f(s),t) for s,t in data["held"]]
    correct=sum(p==t for p,t in pairs);wrong=sum(p is not None and p!=t for p,t in pairs)
    return dict(correct=correct,wrong=wrong,abstained=len(pairs)-correct-wrong,
                utility=correct-4*wrong,predictions=pairs)

def train():
    estimator=reliability.Estimator()
    for r in reliability.samples(reliability.TRAIN):estimator.learn(r["features"],r["outcomes"])
    estimator.freeze()
    budget,_=cost.trained();selector,_=strategy.trained()
    return estimator,budget,selector

def session(seed,estimator,cost_model,selector):
    lab=cost.lab;parts,names,order=lab.setup(seed)
    base=lab.h.acquire_base(seed,*parts[:4])[0];core=lab.Core(base,"motif_8192")
    for i,name in enumerate(names):core.observe(i,tuple((x,lab.e.oracle(name,x)) for x in parts[4]))
    env=[(s,gaps.case(seed+997*j,s)) for j in range(3) for s in gaps.STRATA]
    random.Random(seed^0x7201).shuffle(env)
    mr=[];er=[];remaining=EXTRA_BUDGET
    for step in range(lab.previous.ATTEMPTS):
        if step<len(env):
            stratum,data=env[step]
            exact=Revised("exact")
            for s,t in data["points"]:exact.observe(0,s,t)
            ref=dict(choice="exact",model=exact.models[0],kind="affine",confidence=None,gap=False,extra=0,rechecks=0)
            d=decision(data["points"],selector,estimator,remaining)
            remaining-=d["extra"]
            if remaining<0:raise RuntimeError("budget")
            er.append(dict(step=step,stratum=stratum,points=data["points"],held=data["held"],
                           reference=dict(**ref,**evaluate(data,ref)),
                           integrated=dict(**d,**evaluate(data,d))))
        eligible=[i for i in order if core.tasks[i].status=="deferred" and core.eligible(i)]
        i=order[step] if step<lab.previous.COMMON else (eligible[0] if eligible else None)
        if i is None:continue
        f=cost.features(core,i)
        predictions={m:cost_model.predict(f,m) for m in cost.MODES}
        row=core.investigate(i,lambda p:lab.validation(names[i],parts[5],p))
        mr.append(dict(step=step,features=f,predictions=predictions,cost=row["pair_examined"],status=row["status"]))
    final=lab.score(core,base,parts[6],parts[7])
    return dict(seed=seed,math=mr,math_final=lab.e.metric(final),environment=er,
                additional_family_budget=EXTRA_BUDGET,additional_family_spent=EXTRA_BUDGET-remaining)

def run(out):
    out.mkdir(parents=True,exist_ok=False);estimator,budget,selector=train()
    before=json.dumps([estimator.counts,budget.buckets,selector.history],sort_keys=True)
    sessions=[]
    for seed in SEEDS:
        s=session(seed,estimator,budget,selector);sessions.append(s)
        cost.lab.write(out/f"session_{seed}.json",s)
    if before!=json.dumps([estimator.counts,budget.buckets,selector.history],sort_keys=True):
        raise RuntimeError("test changed frozen models")
    mr=[x for s in sessions for x in s["math"]]
    er=[x for s in sessions for x in s["environment"]]
    def aggregate(rows,mode):
        return dict(tasks=len(rows),**{k:sum(r[mode][k] for r in rows) for k in
                ("correct","wrong","abstained","utility","extra","rechecks")})
    r=[x["integrated"] for x in er if x["integrated"]["confidence"] is not None]
    confidence=dict(n=len(r),transition_brier=sum((x["confidence"][0]-int(p==t))**2
        for x in r for p,t in x["predictions"])/(7*len(r)) if r else None)
    result=dict(protocol="V72-self-model-v1",seeds=SEEDS,cost=[dict(mode=m,**cost.metrics(mr,m)) for m in cost.MODES],
        math_final={k:sum(s["math_final"][k] for s in sessions) for k in ("n","correct","wrong","abstained")},
        aggregate=[dict(mode=m,**aggregate(er,m)) for m in MODES],
        by_stratum=[dict(stratum=k,mode=m,**aggregate([x for x in er if x["stratum"]==k],m))
                    for k in gaps.STRATA for m in MODES],
        decisions={k:sum(x["integrated"]["choice"]==k for x in er) for k in
                   ("exact","repair","map","expand","map_gap","map_budget")},
        confidence=confidence,spent=[s["additional_family_spent"] for s in sessions])
    cost.lab.write(out/"summary.json",result);print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_gap_budget(self):
        p=[(s,polynomial((1,2,3,4),s)) for s in range(10)]
        a=decision(p,None,None,0);self.assertEqual(a["choice"],"map_budget")
        b=decision(p,None,None,2);self.assertEqual(b["choice"],"expand");self.assertEqual(b["extra"],2)
    def test_reference(self):
        p=[(s,(2*s+1)%17) for s in range(10)]
        a,b,c=models(p);self.assertEqual(a.models[0],(2,1));self.assertEqual(a.models,b.models)
    def test_split(self):
        for train in (reliability.TRAIN,cost.TRAIN,strategy.TRAIN):
            self.assertFalse(set(train)&set(SEEDS))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V72 required")
    run(a.output.resolve())
if __name__=="__main__":main()
