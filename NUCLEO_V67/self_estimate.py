"""Empirical self-performance estimation within a bounded offline simulator."""
import argparse,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V62"))
from revision import N,ACTIONS,predict,world,train,write
TRAIN=tuple(8600017+30001*i for i in range(32))
TEST=tuple(9700017+30001*i for i in range(24))
STRATA=(0,1,3)
MODES=("certainty","global","status","evidence")

def features(memory,a):
    h=memory.models[a]
    if h is None:return None
    points=list(memory.observed[a].items())
    if len(points)!=10:raise ValueError("incomplete audit")
    return (memory.status[a],sum(predict(h,s)==t for s,t in points[:6]),
            sum(predict(h,s)==t for s,t in points[6:]))

def samples(seeds):
    for seed in seeds:
        for k in STRATA:
            table,_,_=world(seed,k)
            memory=train(table,seed,"repair")
            for a in ACTIONS:
                feat=features(memory,a)
                reserved=[s for s in range(N) if s not in memory.observed[a]]
                actual=[int(memory.belief(a,s)[0]==table[s,a]) for s in reserved] if feat else []
                yield dict(seed=seed,exceptions=k,action=a,features=feat,outcomes=actual)

def keys(feat):
    status,fit,audit=feat
    return ("global","status:"+status,"evidence:"+str(fit)+":"+str(audit))

class Estimator:
    def __init__(self):self.counts={};self.frozen=False
    def learn(self,feat,outcomes):
        if self.frozen:raise RuntimeError("frozen estimator")
        if feat is None:return
        if len(outcomes)!=7 or any(y not in (0,1) for y in outcomes):raise ValueError("outcomes")
        for key in keys(feat):
            n,correct,all_correct=self.counts.get(key,(0,0,0))
            self.counts[key]=(n+1,correct+sum(outcomes),all_correct+int(all(outcomes)))
    def freeze(self):self.frozen=True
    def forecast(self,feat,mode):
        if not self.frozen:raise RuntimeError("not frozen")
        if mode not in MODES:raise ValueError("mode")
        if feat is None:return None
        if mode=="certainty":return (1.,1.)
        key=keys(feat)[MODES.index(mode)-1]
        n,c,a=self.counts.get(key,self.counts.get("global",(0,0,0)))
        return ((c+1)/(7*n+2),(a+1)/(n+2))

def metrics(records,mode):
    emitted=[r for r in records if r["features"] is not None]
    p=[(r["forecast"][mode][0],y) for r in emitted for y in r["outcomes"]]
    q=[(r["forecast"][mode][1],int(all(r["outcomes"]))) for r in emitted]
    def score(pairs):
        n=len(pairs)
        if not n:return dict(n=0,brier=None,predicted=None,observed=None,calibration_gap=None)
        predicted=sum(p for p,y in pairs)/n;observed=sum(y for p,y in pairs)/n
        return dict(n=n,brier=sum((p-y)**2 for p,y in pairs)/n,predicted=predicted,
                    observed=observed,calibration_gap=predicted-observed)
    return dict(rules=len(records),emitted=len(emitted),abstained=len(records)-len(emitted),
                transition=score(p),whole_rule=score(q))

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    estimator=Estimator();training=list(samples(TRAIN))
    for r in training:estimator.learn(r["features"],r["outcomes"])
    estimator.freeze();before=dict(estimator.counts);records=[]
    for r in samples(TEST):
        feat=r["features"]
        records.append(dict(**r,forecast={mode:estimator.forecast(feat,mode) for mode in MODES}))
    if before!=estimator.counts:raise RuntimeError("evaluation changed estimator")
    agg=[dict(mode=mode,**metrics(records,mode)) for mode in MODES]
    by_stratum=[dict(exceptions=k,mode=mode,**metrics([r for r in records if r["exceptions"]==k],mode))
                for k in STRATA for mode in MODES]
    result=dict(protocol="V67-self-estimate-v1",train_seeds=TRAIN,test_seeds=TEST,
                train_rules=len(training),counts=before,aggregate=agg,by_stratum=by_stratum)
    write(out/"training.json",training);write(out/"test.json",records);write(out/"summary.json",result)
    print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_estimator(self):
        e=Estimator();feat=("revised",5,4)
        e.learn(feat,[1]*7);e.learn(feat,[1]*6+[0]);e.freeze()
        self.assertEqual(e.forecast(feat,"evidence"),(14/16,2/4))
        self.assertEqual(e.forecast(("inferred",6,4),"status"),e.forecast(feat,"global"))
        self.assertIsNone(e.forecast(None,"global"))
        with self.assertRaises(RuntimeError):e.learn(feat,[1]*7)
    def test_split(self):
        self.assertFalse(set(TRAIN)&set(TEST))
    def test_features(self):
        table,_,_=world(TRAIN[0],0);memory=train(table,TRAIN[0],"repair")
        self.assertEqual(features(memory,0),("inferred",6,4))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V67 required")
    run(a.output.resolve())
if __name__=="__main__":main()
