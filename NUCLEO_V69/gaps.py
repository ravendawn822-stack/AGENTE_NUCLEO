"""Diagnose local model incompatibility within finite polynomial families."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V65"))
from transfer import N,predict,interpolate
TRAIN=tuple(12000019+30001*i for i in range(32))
TEST=tuple(13000019+30001*i for i in range(24))
STRATA=("linear","quadratic","cubic","outside")
MODES=("limited","selective","expanded")

def case(seed,stratum):
    rng=random.Random(seed^(0x6900+STRATA.index(stratum)))
    degree={"linear":1,"quadratic":2,"cubic":3,"outside":2}[stratum]
    h=tuple(rng.randrange(N) for _ in range(degree))+(rng.randrange(1,N),)
    values=[predict(h,s) for s in range(N)]
    if stratum=="outside":
        for s in rng.sample(range(N),3):values[s]=(values[s]+rng.randrange(1,N))%N
    sample=rng.sample(range(N),10)
    return dict(points=[(s,values[s]) for s in sample],held=[(s,values[s]) for s in range(N) if s not in sample])

def inspect(points,mode):
    if mode not in MODES or len(points)!=10 or len({s for s,t in points})!=10:raise ValueError("case")
    def fit(d):
        h=interpolate(points[:6],d)
        if d>1 and h[-1]==0:return None
        return h if all(predict(h,s)==t for s,t in points) else None
    models={d:fit(d) for d in (1,2)}
    gap=not any(h is not None for h in models.values())
    if mode=="expanded" or (mode=="selective" and gap):models[3]=fit(3)
    selected=next(((d,h) for d,h in models.items() if h is not None),(None,None))
    return dict(gap=gap,degree=selected[0],model=selected[1],families=len(models),
                persistent=selected[1] is None)

def evaluate(data,result):
    h=result["model"];rows=[(predict(h,s) if h is not None else None,t) for s,t in data["held"]]
    return dict(correct=sum(p==t for p,t in rows),wrong=sum(p is not None and p!=t for p,t in rows),
                abstained=sum(p is None for p,t in rows))

def dataset(seeds):
    for seed in seeds:
        for stratum in STRATA:
            data=case(seed,stratum)
            for mode in MODES:
                result=inspect(data["points"],mode)
                yield dict(seed=seed,stratum=stratum,mode=mode,**result,**evaluate(data,result),data=data)

def run(out):
    out.mkdir(parents=True,exist_ok=False);training=list(dataset(TRAIN));testing=list(dataset(TEST))
    aggregate=[dict(stratum=s,mode=m,**{k:sum(r[k] for r in testing if r["stratum"]==s and r["mode"]==m)
      for k in ("gap","persistent","families","correct","wrong","abstained")}) for s in STRATA for m in MODES]
    for name,data in (("training",training),("test",testing),("summary",dict(protocol="V69-gaps-v1",aggregate=aggregate))):
        (out/(name+".json")).write_text(json.dumps(data,indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_cubic(self):
        points=[(s,predict((1,2,3,4),s)) for s in range(10)]
        self.assertTrue(inspect(points,"limited")["persistent"])
        self.assertEqual(inspect(points,"selective")["degree"],3)
    def test_linear(self):
        points=[(s,predict((1,2),s)) for s in range(10)]
        self.assertEqual(inspect(points,"selective")["families"],2)
        self.assertFalse(inspect(points,"selective")["gap"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V69 required")
    run(a.output.resolve())
if __name__=="__main__":main()
