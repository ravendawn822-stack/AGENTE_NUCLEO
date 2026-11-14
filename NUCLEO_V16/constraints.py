"""V16: finite mathematical expression synthesis from observed constraints."""
import argparse,json,sys,time,unittest,math
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V13"))
import alternatives as a
m,v10,v9,b=a.m,a.v10,a.v9,a.b
SEEDS=(2640013,2670017,2700023,2730031)
POLICIES=("factorized","additive","additive_product")
CAP=8400
AXIS=tuple(range(-2,3))

def terms(var):
    for k,c in b.TRANSFORMS:
        e=b.transform(var,k,c);sq=(v9.MUL,e,e)
        yield from (e,(v9.ABS,e),sq,(v9.MUL,sq,e),
                    (v9.MOD,e,(v9.C,2)),(v9.MOD,e,(v9.C,3)))

def fit(var,target,offer):
    vals=tuple(target)
    if len(set(vals))==1:
        if offer():return (v9.C,vals[0])
        return None
    for e in terms(var):
        if not offer():return None
        profile=v9.apply(e,AXIS,AXIS,{})
        j=next((j for j,z in enumerate(profile) if z!=profile[0]),None)
        if j is None:continue
        k=Fraction(vals[j]-vals[0],profile[j]-profile[0])
        c=vals[0]-k*profile[0]
        if k.denominator!=1 or c.denominator!=1:continue
        if any(k*x+c!=y for x,y in zip(profile,vals)):continue
        k,c=int(k),int(c)
        if k!=1:e=(v9.MUL,(v9.C,k),e)
        if c:e=(v9.ADD,e,(v9.C,c))
        return e
    return None

def constrained(obs,answers,cap,product):
    grid=dict(zip(obs,answers))
    if any((x,y) not in grid for x in AXIS for y in AXIS):return None,0
    n=0
    def offer():
        nonlocal n
        if n>=cap:return False
        n+=1;return True
    def combine(x,y,op):
        if x is None or y is None or not offer():return None
        e=(op,x,y)
        return e if v9.check(e,obs,answers,{}) else None
    if all(grid[x,y]==grid[x,0]+grid[0,y]-grid[0,0] for x in AXIS for y in AXIS):
        x=fit(v9.X,[grid[x,0] for x in AXIS],offer)
        y=fit(v9.Y,[grid[0,y]-grid[0,0] for y in AXIS],offer)
        e=combine(x,y,v9.ADD)
        if e is not None:return e,n
    if product:
        pivot=next(((x,y) for x in AXIS for y in AXIS if grid[x,y]),None)
        if pivot:
            i,j=pivot;p=grid[i,j]
            if all(grid[x,y]*p==grid[x,j]*grid[i,y] for x in AXIS for y in AXIS):
                g=math.gcd(*(grid[x,j] for x in AXIS))
                col=[grid[x,j]//g for x in AXIS]
                row=[Fraction(grid[i,y]*g,p) for y in AXIS]
                if all(z.denominator==1 for z in row):
                    x=fit(v9.X,col,offer);y=fit(v9.Y,[int(z) for z in row],offer)
                    e=combine(x,y,v9.MUL)
                    if e is not None:return e,n
    return None,n

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];train=[]
    for seed in SEEDS:
        pool,final=v10.suite(seed);mem=v9.Registry(out/f"{seed}.sqlite3")
        for i,t in enumerate(pool):
            reg=mem.snapshot();view,held=m.task_view(t,seed+i*701)
            expected=[b.target(t,x,y) for x,y in held]
            rr=m.trial(view,reg,12000,expected,held,True)
            acquired=False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                acquired=mem.register(rr["expanded"],t["id"],held,expected)
            train.append(dict(seed=seed,task=t,acquired=acquired,**rr))
        reg=mem.snapshot();mem.close();frozen=v9.digest(reg)
        for i,t in enumerate(final):
            view,held=m.task_view(t,seed*17+i*971);obs,ans=view["observations"],view["answers"]
            first,meta=v10.solve(obs,ans,reg,3600);proposals={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                if first is not None:e,n=first,0
                elif policy=="factorized":e,n=a.alternate(obs,ans,reg,CAP,"factorized")
                else:e,n=constrained(obs,ans,CAP,policy=="additive_product")
                assert n<=CAP
                proposals[policy]=(e,n,time.perf_counter_ns()-start)
            expected=[b.target(t,x,y) for x,y in held]
            for policy,(e,n,elapsed) in proposals.items():
                rows.append(dict(seed=seed,task=t,policy=policy,initial_failed=first is None,
                    candidate=e,emitted=e is not None,success=v9.check(e,held,expected,reg),
                    candidates=meta["candidates"]+n,extra_candidates=n,extra_wall_ns=elapsed))
        assert frozen==v9.digest(reg)
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            additional_correct=sum(r["success"] and r["initial_failed"] for r in rr),
            candidates=sum(r["candidates"] for r in rr),extra_wall_ns=sum(r["extra_wall_ns"] for r in rr))
    result=dict(protocol="V16-constraints-v1",seeds=SEEDS,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=k,policy=p,**metric([r for r in rows if r["seed"]==k and r["policy"]==p])) for k in SEEDS for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in ("linked","unrelated","outside") for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",train)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(v9.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_additive(self):
        obs=list(m.GRID);held=[(7,-4),(-5,9)]
        fn=lambda x,y:(x+1)**2+abs(y-1)
        e,n=constrained(obs,[fn(x,y) for x,y in obs],CAP,False)
        self.assertTrue(v9.check(e,held,[fn(x,y) for x,y in held],{}))
        self.assertLessEqual(n,CAP)
    def test_product(self):
        obs=list(m.GRID);held=[(7,-4),(-5,9)]
        fn=lambda x,y:abs(x+1)*abs(y-1)
        e,n=constrained(obs,[fn(x,y) for x,y in obs],CAP,True)
        self.assertTrue(v9.check(e,held,[fn(x,y) for x,y in held],{}))
    def test_ambiguous_profile(self):
        obs=[*m.GRID,(0,9)]
        fn=lambda x,y:x*x+abs(y-2)
        self.assertIsNone(constrained(obs,[fn(x,y) for x,y in obs],CAP,False)[0])
    def test_budget(self):
        obs=list(m.GRID);fn=lambda x,y:(x+1)**2+abs(y-1)
        self.assertLessEqual(constrained(obs,[fn(x,y) for x,y in obs],2,True)[1],2)
    def test_seeds(self):
        for k in SEEDS:self.assertEqual(tuple(map(len,v10.suite(k))),(32,32))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V16 required")
    run(z.output)
