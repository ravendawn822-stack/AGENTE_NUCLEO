"""Bounded offline tests of confidence-driven emission and cost bounds."""
import argparse,json,math,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for version in (62,65,68):
    sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{version}"))
import cost_model as cost
from revision import Revised
from transfer import N,predict,interpolate
TRAIN=tuple(19000019+30001*i for i in range(48))
TEST=tuple(21000019+30001*i for i in range(32))
CAL=tuple(23000019+30001*i for i in range(12))
COST_TEST=tuple(24000019+30001*i for i in range(8))
STRATA=((1,0),(1,1),(1,3),(2,0),(3,0),(2,3))
MODES=("ungated","context_gate","global_gate","exact")

def case(seed,stratum):
    degree,exceptions=stratum
    rng=random.Random(seed^(0x7300+STRATA.index(stratum)))
    h=tuple(rng.randrange(N) for _ in range(degree))+(rng.randrange(1,N),)
    values=[predict(h,s) for s in range(N)]
    for s in rng.sample(range(N),exceptions):
        values[s]=(values[s]+rng.randrange(1,N))%N
    xs=rng.sample(range(N),10)
    return [(s,values[s]) for s in xs],[(s,values[s]) for s in range(N) if s not in xs]

def candidate(points):
    repair=Revised("repair");exact=Revised("exact")
    for s,t in points:
        repair.observe(0,s,t);exact.observe(0,s,t)
    old=exact.models[0];reference=None if old is None else tuple(reversed(old))
    model=repair.models[0]
    if model is not None:
        h=tuple(reversed(model));degree=1
    else:
        h=None;degree=None
        for d in (2,3):
            p=interpolate(points[:6],d)
            if p[-1] and all(predict(p,s)==t for s,t in points):
                h=p;degree=d;break
    feat=None if h is None else (degree,sum(predict(h,s)==t for s,t in points[:6]),
                               sum(predict(h,s)==t for s,t in points[6:]))
    return h,feat,reference

def evaluate(h,held):
    pairs=[(None if h is None else predict(h,s),t) for s,t in held]
    c=sum(p==t for p,t in pairs);w=sum(p is not None and p!=t for p,t in pairs)
    return dict(correct=c,wrong=w,abstained=len(pairs)-c-w,utility=c-4*w,predictions=pairs)

class Reliability:
    def __init__(self):self.counts={};self.frozen=False
    def learn(self,feat,result):
        if self.frozen:raise RuntimeError("frozen")
        if feat is None:return
        if result["correct"]+result["wrong"]!=7:raise ValueError("incomplete result")
        for key in ("global",str(feat)):
            n,c,a=self.counts.get(key,(0,0,0))
            self.counts[key]=(n+1,c+result["correct"],a+int(result["correct"]==7))
    def freeze(self):self.frozen=True
    def estimate(self,feat,context=True):
        if not self.frozen:raise RuntimeError("not frozen")
        if feat is None:return None
        n,c,a=self.counts.get(str(feat) if context else "global",self.counts.get("global",(0,0,0)))
        return ((c+1)/(7*n+2),(a+1)/(n+2))

def samples(seeds):
    for seed in seeds:
        for k in STRATA:
            points,held=case(seed,k);h,f,ref=candidate(points)
            yield dict(seed=seed,stratum=k,points=points,held=held,model=h,features=f,reference=ref)

def run_reliability(out):
    model=Reliability();training=[];rows=[]
    for r in samples(TRAIN):
        result=evaluate(r["model"],r["held"]);model.learn(r["features"],result)
        training.append(dict(**r,outcome=result))
    model.freeze()
    for r in samples(TEST):
        h=r["model"];f=r["features"]
        pc=model.estimate(f);pg=model.estimate(f,False)
        selected={"ungated":h,"context_gate":h if pc and pc[0]>.8 else None,
                  "global_gate":h if pg and pg[0]>.8 else None,"exact":r["reference"]}
        rows.append(dict(**r,context=pc,global_estimate=pg,
                    results={m:evaluate(hh,r["held"]) for m,hh in selected.items()}))
    def aggregate(rs,m):
        return dict(tasks=len(rs),**{k:sum(r["results"][m][k] for r in rs)
                for k in ("correct","wrong","abstained","utility")},blocked=sum(
                r["model"] is not None and r["results"][m]["abstained"]==7 for r in rs))
    emitted=[r for r in rows if r["model"] is not None]
    def calibration(field):
        pair=[(r[field][0],int(p==t)) for r in emitted for p,t in r["results"]["ungated"]["predictions"]]
        whole=[(r[field][1],int(r["results"]["ungated"]["correct"]==7)) for r in emitted]
        def score(p):
            return sum((a-b)**2 for a,b in p)/len(p) if p else None
        return dict(n=len(emitted),transition_brier=score(pair),whole_rule_brier=score(whole))
    result=dict(counts=model.counts,aggregate=[dict(mode=m,**aggregate(rows,m)) for m in MODES],
        by_stratum=[dict(stratum=k,mode=m,**aggregate([r for r in rows if r["stratum"]==k],m))
                    for k in STRATA for m in MODES],
        calibration={f:calibration(f) for f in ("context","global_estimate")})
    cost.lab.write(out/"reliability_training.json",training);cost.lab.write(out/"reliability_test.json",rows)
    return result

def conformal(residuals,coverage=.9):
    if not residuals:raise ValueError("empty calibration")
    rank=math.ceil((len(residuals)+1)*coverage)
    return sorted(residuals)[rank-1] if rank<=len(residuals) else cost.CAP

def run_cost(out):
    model,training=cost.trained();calibration=[];test=[]
    for seed in CAL:
        rows,_,_=cost.samples(seed,model)
        if not rows:raise RuntimeError("empty session")
        calibration.append(dict(seed=seed,maximum=max(0,max(r["cost"]-r["predictions"]["context"] for r in rows)),rows=rows))
    q=conformal([r["maximum"] for r in calibration])
    for seed in COST_TEST:
        rows,_,_=cost.samples(seed,model)
        if not rows:raise RuntimeError("empty session")
        for r in rows:
            r["bounds"]={"cap":cost.CAP,"median":r["predictions"]["context"],
                         "upper":min(cost.CAP,r["predictions"]["context"]+q)}
        test.append(dict(seed=seed,rows=rows))
    def metric(m):
        rows=[r for s in test for r in s["rows"]]
        delta=[r["bounds"][m]-r["cost"] for r in rows]
        return dict(attempts=len(rows),covered=sum(d>=0 for d in delta),
            sessions=len(test),sessions_covered=sum(all(r["bounds"][m]>=r["cost"] for r in s["rows"]) for s in test),
            average_estimate=sum(r["bounds"][m] for r in rows)/len(rows),
            mean_excess=sum(max(0,d) for d in delta)/len(delta),
            mean_shortfall=sum(max(0,-d) for d in delta)/len(delta))
    cost.lab.write(out/"cost_training.json",training);cost.lab.write(out/"cost_calibration.json",calibration)
    cost.lab.write(out/"cost_test.json",test)
    return dict(q=q,calibration_sessions=len(CAL),aggregate=[dict(mode=m,**metric(m)) for m in ("cap","median","upper")])

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    result=dict(protocol="V73-operational-self-model-v1",reliability=run_reliability(out),cost=run_cost(out))
    cost.lab.write(out/"summary.json",result);print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_candidate(self):
        for h in ((2,3),(1,2,3),(1,2,3,4)):
            p=[(s,predict(h,s)) for s in range(10)]
            fit,feat,ref=candidate(p);self.assertEqual(fit,h)
            self.assertEqual(feat,(len(h)-1,6,4))
    def test_gate(self):
        m=Reliability();f=(1,5,3)
        m.learn(f,dict(correct=4,wrong=3));m.freeze()
        self.assertLessEqual(m.estimate(f)[0],.8)
        with self.assertRaises(RuntimeError):m.learn(f,dict(correct=7,wrong=0))
    def test_quantile(self):
        self.assertEqual(conformal(list(range(12))),11)
        self.assertEqual(conformal([1,2]),cost.CAP)
    def test_split(self):
        sets=[set(x) for x in (TRAIN,TEST,CAL,COST_TEST,cost.TRAIN,cost.TEST)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V73 required")
    run(a.output.resolve())
if __name__=="__main__":main()
