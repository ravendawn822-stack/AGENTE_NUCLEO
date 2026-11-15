"""Frozen empirical logical-cost model for the bounded mathematical core."""
import argparse,json,statistics,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V56"))
import restart_experiment as lab
TRAIN=tuple(10000019+30001*i for i in range(12))
TEST=tuple(11000019+30001*i for i in range(8))
CAP=lab.previous.CAP
MODES=("cap","global","context")

def features(core,i):
    n=len(core.library);retry=core.tasks[i].status=="deferred"
    bad=len(core.negative[i]) if i in core.negative else 0
    return (0 if n<=8 else 1 if n<=12 else 2,int(retry),0 if bad==0 else 1 if bad<=12000 else 2)

class Cost:
    def __init__(self):self.buckets={};self.frozen=False
    def learn(self,f,cost):
        if self.frozen:raise RuntimeError("frozen")
        if not 0<=cost<=CAP:raise ValueError("cost")
        for key in ("global",str(tuple(f))):self.buckets.setdefault(key,[]).append(cost)
    def freeze(self):self.frozen=True
    def predict(self,f,mode):
        if not self.frozen:raise RuntimeError("not frozen")
        if mode not in MODES:raise ValueError("mode")
        if mode=="cap":return CAP
        rows=self.buckets.get(str(tuple(f)) if mode=="context" else "global",self.buckets.get("global",[]))
        return statistics.median(rows) if rows else CAP

def samples(seed,estimator=None):
    parts,names,order=lab.setup(seed)
    core=lab.Core(lab.h.acquire_base(seed,*parts[:4])[0],"motif_8192")
    for i,name in enumerate(names):core.observe(i,tuple((x,lab.e.oracle(name,x)) for x in parts[4]))
    rows=[]
    for step in range(lab.previous.ATTEMPTS):
        eligible=[i for i in order if core.tasks[i].status=="deferred" and core.eligible(i)]
        i=order[step] if step<lab.previous.COMMON else (eligible[0] if eligible else None)
        if i is None:continue
        f=features(core,i)
        predictions={mode:estimator.predict(f,mode) for mode in MODES} if estimator else {}
        row=core.investigate(i,lambda p:lab.validation(names[i],parts[5],p))
        rows.append(dict(seed=seed,step=step,features=f,cost=row["pair_examined"],predictions=predictions,
                         status=row["status"]))
    return rows,core,parts

def trained():
    model=Cost();records=[]
    for seed in TRAIN:
        rows,_,_=samples(seed)
        for row in rows:model.learn(row["features"],row["cost"])
        records.extend(rows)
    model.freeze();return model,records

def metrics(rows,mode):
    errors=[r["predictions"][mode]-r["cost"] for r in rows]
    return dict(n=len(rows),mae=sum(abs(x) for x in errors)/len(errors),bias=sum(errors)/len(errors)) if errors else dict(n=0,mae=None,bias=None)

def run(out):
    out.mkdir(parents=True,exist_ok=False);model,training=trained();test=[]
    for seed in TEST:test.extend(samples(seed,model)[0])
    result=dict(protocol="V68-logical-cost-v1",train_seeds=TRAIN,test_seeds=TEST,
        aggregate=[dict(mode=m,**metrics(test,m)) for m in MODES],
        by_retry=[dict(mode=m,retry=r,**metrics([x for x in test if x["features"][1]==r],m)) for m in MODES for r in (0,1)],
        training_attempts=len(training),buckets={k:len(v) for k,v in model.buckets.items()})
    lab.write(out/"training.json",training);lab.write(out/"test.json",test);lab.write(out/"summary.json",result)
    print(json.dumps(result["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_cost(self):
        m=Cost();m.learn((0,0,0),3);m.learn((1,1,1),7);m.freeze()
        self.assertEqual(m.predict((0,0,0),"context"),3)
        self.assertEqual(m.predict((2,1,2),"context"),5)
        self.assertEqual(m.predict((2,1,2),"cap"),CAP)
        with self.assertRaises(RuntimeError):m.learn((0,0,0),3)
    def test_seeds(self):self.assertFalse(set(TRAIN)&set(TEST))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V68 required")
    run(a.output.resolve())
if __name__=="__main__":main()
