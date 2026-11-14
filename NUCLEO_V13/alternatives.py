"""V13: alternative bounded search methods for mathematical observations."""
import argparse,itertools,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V12"))
import allocation as a
m,v10,v9,b=a.m,a.v10,a.v9,a.b
SEEDS=(2280013,2310017,2340023,2370031)
CAP=8400
POLICIES=("restart","reverse_binding","factorized")
def alternate(obs,answers,reg,cap,method):
    xs,ys=zip(*obs);target=tuple(answers)
    def terms(var):
        base=[b.transform(var,k,c) for k,c in b.TRANSFORMS]
        if method=="reverse_binding":
            return sorted(base,key=v9.nodes,reverse=True)
        pool=[]
        for e in base:
            sq=(v9.MUL,e,e)
            pool.extend((e,(v9.ABS,e),sq,(v9.MUL,sq,e)))
        return list(dict.fromkeys(pool))
    left,right=terms(v9.X),terms(v9.Y)
    values={e:v9.apply(e,xs,ys,{}) for e in left+right}
    pairs=list(itertools.product(left,right))
    if method=="factorized":
        # Prioritize simple terms while interleaving primitive and learned roots.
        pairs.sort(key=lambda ab:v9.nodes(ab[0])+v9.nodes(ab[1]))
    ops=(*sorted(reg),*v9.OPS)
    n=0
    for x,y in pairs:
        for op in ops:
            if n>=cap:return None,n
            n+=1
            try:
                value=v9.apply(reg[op],values[x],values[y],{}) if op in reg else v9.vector_op(op,values[x],values[y])
            except ZeroDivisionError:continue
            if value==target:return (op,x,y),n
    return None,n
def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    rows=[];training=[]
    for seed in SEEDS:
        pool,final=v10.suite(seed)
        mem=v9.Registry(folder/f"{seed}.sqlite3")
        for i,t in enumerate(pool):
            reg=mem.snapshot()
            view,held=m.task_view(t,seed+i*701)
            expected=[b.target(t,x,y) for x,y in held]
            rr=m.trial(view,reg,a.SHORT+a.EXTRA,expected,held,True)
            acquired=False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                acquired=mem.register(rr["expanded"],t["id"],held,expected)
            training.append(dict(seed=seed,task=t,acquired=acquired,**rr))
        reg=mem.snapshot();mem.close();frozen=v9.digest(reg)
        for i,t in enumerate(final):
            view,held=m.task_view(t,seed*17+i*971)
            obs,answers=view["observations"],view["answers"]
            first,meta=v10.solve(obs,answers,reg,a.SHORT)
            expected=[b.target(t,x,y) for x,y in held]
            for p in POLICIES:
                e=first;n=0
                if first is None:
                    if p=="restart":
                        e,d=v10.solve(obs,answers,reg,CAP);n=d["candidates"]
                    else:e,n=alternate(obs,answers,reg,CAP,p)
                assert n<=CAP
                rows.append(dict(seed=seed,task=t,policy=p,initial_failed=first is None,
                    emitted=e is not None,success=v9.check(e,held,expected,reg),
                    candidate=e,candidates=meta["candidates"]+n,extra=n))
        assert frozen==v9.digest(reg)
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            additional_correct=sum(r["success"] and r["initial_failed"] for r in rr),
            candidates=sum(r["candidates"] for r in rr))
    result=dict(protocol="V13-alternatives-v1",seeds=SEEDS,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in ("linked","unrelated","outside") for p in POLICIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (folder/(name+".jsonl")).open("w",encoding="utf-8") as out:
            for row in data:out.write(v9.enc(row)+"\n")
    print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_cap(self):
        for method in POLICIES[1:]:
            _,n=alternate([(1,2),(-3,4)],[999,999],{},17,method)
            self.assertLessEqual(n,17)
    def test_factorized(self):
        obs,held=v9.observations(22)
        e,n=alternate(obs,[x*x+y*y for x,y in obs],{},CAP,"factorized")
        self.assertTrue(v9.check(e,held,[x*x+y*y for x,y in held],{}))
    def test_seeds(self):
        self.assertTrue(set(SEEDS).isdisjoint(a.SEEDS))
        for s in SEEDS:self.assertEqual(tuple(map(len,v10.suite(s))),(32,32))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V13 required")
    run(z.output)
