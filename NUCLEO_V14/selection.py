"""V14: empirical selection of bounded mathematical search methods."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V13"))
import alternatives as a
m,v10,v9,b=a.m,a.v10,a.v9,a.b
SEEDS=(2400013,2430017,2460023,2490031)
METHODS=a.POLICIES
POLICIES=(*METHODS,"random","adaptive")
SHORT,CAP=3600,8400

def extra(method,obs,answers,reg):
    if method=="restart":
        e,d=v10.solve(obs,answers,reg,CAP)
        return e,d["candidates"]
    return a.alternate(obs,answers,reg,CAP,method)

def score(f,h,method):
    rr=[r for r in h if r["method"]==method]
    weights=[1/(.12+m.distance(f,r["feature"]))**2 for r in rr]
    return (1+sum(w*r["success"] for w,r in zip(weights,rr)))/(2+sum(weights))

def select(f,h):
    return max(METHODS,key=lambda method:score(f,h,method))

def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    rows=[];training=[];acquisition=[]
    for seed in SEEDS:
        pool,final=v10.suite(seed)
        mem=v9.Registry(folder/f"{seed}.sqlite3")
        for i,t in enumerate(pool):
            reg=mem.snapshot()
            view,held=m.task_view(t,seed+i*701)
            expected=[b.target(t,x,y) for x,y in held]
            rr=m.trial(view,reg,12000,expected,held,True)
            learned=False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                learned=mem.register(rr["expanded"],t["id"],held,expected)
            acquisition.append(dict(seed=seed,task=t,learned=learned,**rr))
        reg=mem.snapshot();mem.close()
        history=[]
        for i,t in enumerate(pool):
            view,held=m.task_view(t,seed+i*701)
            obs,answers=view["observations"],view["answers"]
            first,d=v10.solve(obs,answers,reg,SHORT)
            if first is not None:continue
            expected=[b.target(t,x,y) for x,y in held]
            for method in METHODS:
                e,n=extra(method,obs,answers,reg)
                rr=dict(seed=seed,task=t,method=method,feature=view["feature"],
                        success=v9.check(e,held,expected,reg),emitted=e is not None,
                        candidates=n,candidate=e)
                history.append(rr);training.append(rr)
        frozen=v9.digest([reg,history])
        rng=random.Random(seed^0xD214)
        for i,t in enumerate(final):
            view,held=m.task_view(t,seed*17+i*971)
            obs,answers=view["observations"],view["answers"]
            first,d=v10.solve(obs,answers,reg,SHORT)
            chosen=select(view["feature"],history)
            random_method=rng.choice(METHODS)
            # All choices precede held-out validation.
            methods={p:p if p in METHODS else chosen if p=="adaptive" else random_method for p in POLICIES}
            results={method:extra(method,obs,answers,reg) for method in METHODS} if first is None else {}
            expected=[b.target(t,x,y) for x,y in held]
            for p,method in methods.items():
                e,n=results[method] if first is None else (first,0)
                assert n<=CAP
                rows.append(dict(seed=seed,task=t,policy=p,method=method if first is None else None,
                    initial_failed=first is None,candidate=e,emitted=e is not None,
                    success=v9.check(e,held,expected,reg),candidates=d["candidates"]+n))
        assert frozen==v9.digest([reg,history])
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            additional_correct=sum(r["success"] and r["initial_failed"] for r in rr),
            candidates=sum(r["candidates"] for r in rr))
    result=dict(protocol="V14-method-selection-v1",seeds=SEEDS,
        training_extra_candidates=sum(r["candidates"] for r in training),
        training_acquisition_candidates=sum(r["candidates"] for r in acquisition),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training),("acquisition",acquisition)):
        with (folder/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(v9.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_selection(self):
        f=(0.,)*11
        h=[dict(method=p,feature=f,success=p=="factorized") for p in METHODS]
        self.assertEqual(select(f,h),"factorized")
    def test_seeds(self):
        self.assertTrue(set(SEEDS).isdisjoint(a.SEEDS))
        for s in SEEDS:self.assertEqual(tuple(map(len,v10.suite(s))),(32,32))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V14 required")
    run(z.output)
