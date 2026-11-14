"""V15: bounded composition of symbolic search and exact polynomial fitting."""
import argparse,json,sys,time,unittest
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V14"))
import selection as s
a,m,v10,v9,b=s.a,s.m,s.v10,s.v9,s.b
SEEDS=(2520013,2550017,2580023,2610031)
POLICIES=("factorized","polynomial","composed")
CAP=8400
AXIS=(-2,-1,0,1)

def multiply(a,b):
    out=[F(0)]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):out[i+j]+=x*y
    return out

def basis(x):
    p=[F(1)]
    for z in AXIS:
        if x!=z:p=multiply(p,[F(-z,x-z),F(1,x-z)])
    return p

def polynomial(obs,answers):
    grid=dict(zip(obs,answers))
    if any((x,y) not in grid for x in AXIS for y in AXIS):return None,1
    coeff=[[F(0) for _ in AXIS] for _ in AXIS]
    for x in AXIS:
        for y in AXIS:
            bx,by=basis(x),basis(y)
            for i in range(4):
                for j in range(4):coeff[i][j]+=grid[x,y]*bx[i]*by[j]
    if any(c.denominator!=1 for row in coeff for c in row):return None,1
    def power(var,n):
        e=(v9.C,1)
        if n:
            e=(var,)
            for _ in range(n-1):e=(v9.MUL,e,(var,))
        return e
    terms=[]
    for i in range(4):
        for j in range(4):
            k=int(coeff[i][j])
            if not k:continue
            if i and j:e=(v9.MUL,power(v9.X,i),power(v9.Y,j))
            elif i or j:e=power(v9.X if i else v9.Y,i or j)
            else:e=(v9.C,k)
            if (i or j) and k!=1:e=(v9.MUL,(v9.C,k),e)
            terms.append(e)
    e=terms[0] if terms else (v9.C,0)
    for t in terms[1:]:e=(v9.ADD,e,t)
    if v9.nodes(e)>96 or not v9.check(e,obs,answers,{}):return None,1
    return e,1

def method(p,obs,answers,reg):
    start=time.perf_counter_ns()
    if p=="factorized":
        e,n=a.alternate(obs,answers,reg,CAP,"factorized")
        used=["factorized"]
    else:
        e,n=polynomial(obs,answers);used=["polynomial"]
        if p=="composed" and e is None:
            e,k=a.alternate(obs,answers,reg,CAP-n,"factorized")
            n+=k;used.append("factorized")
    assert n<=CAP
    return e,n,used,time.perf_counter_ns()-start

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];train=[]
    for seed in SEEDS:
        pool,final=v10.suite(seed)
        mem=v9.Registry(out/f"{seed}.sqlite3")
        for i,t in enumerate(pool):
            reg=mem.snapshot();view,held=m.task_view(t,seed+i*701)
            expected=[b.target(t,x,y) for x,y in held]
            rr=m.trial(view,reg,12000,expected,held,True)
            learned=False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                learned=mem.register(rr["expanded"],t["id"],held,expected)
            train.append(dict(seed=seed,task=t,learned=learned,**rr))
        reg=mem.snapshot();mem.close();frozen=v9.digest(reg)
        for i,t in enumerate(final):
            view,held=m.task_view(t,seed*17+i*971)
            obs,ans=view["observations"],view["answers"]
            first,meta=v10.solve(obs,ans,reg,3600)
            # All method proposals precede final validation.
            proposals={p:method(p,obs,ans,reg) if first is None else (first,0,[],0) for p in POLICIES}
            expected=[b.target(t,x,y) for x,y in held]
            for p,(e,n,used,elapsed) in proposals.items():
                rows.append(dict(seed=seed,task=t,policy=p,initial_failed=first is None,
                    candidate=e,emitted=e is not None,success=v9.check(e,held,expected,reg),
                    candidates=meta["candidates"]+n,extra_candidates=n,methods=used,
                    extra_wall_ns=elapsed))
        assert frozen==v9.digest(reg)
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            additional_correct=sum(r["success"] and r["initial_failed"] for r in rr),
            candidates=sum(r["candidates"] for r in rr),extra_wall_ns=sum(r["extra_wall_ns"] for r in rr))
    lookup={(r["seed"],r["task"]["id"],r["policy"]):r["success"] for r in rows}
    comp=[r for r in rows if r["policy"]=="composed"]
    contrasts={p:dict(gains=sum(r["success"] and not lookup[r["seed"],r["task"]["id"],p] for r in comp),
                      losses=sum(not r["success"] and lookup[r["seed"],r["task"]["id"],p] for r in comp)) for p in POLICIES[:2]}
    result=dict(protocol="V15-composition-v1",seeds=SEEDS,contrasts=contrasts,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=k,policy=p,**metric([r for r in rows if r["seed"]==k and r["policy"]==p])) for k in SEEDS for p in POLICIES],
        by_family=[dict(family=f,policy=p,**metric([r for r in rows if r["task"]["family"]==f and r["policy"]==p])) for f in ("linked","unrelated","outside") for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",train)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(v9.enc(row)+"\n")
    print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_polynomial(self):
        obs=list(m.GRID);held=[(7,-4),(-5,9)]
        fn=lambda x,y:3*x*y+x**3-2*y+4
        e,n=polynomial(obs,[fn(x,y) for x,y in obs])
        self.assertEqual(n,1);self.assertTrue(v9.check(e,held,[fn(x,y) for x,y in held],{}))
    def test_reject(self):
        obs=list(m.GRID)
        self.assertIsNone(polynomial(obs,[abs(x-y) for x,y in obs])[0])
    def test_seeds(self):
        self.assertTrue(set(SEEDS).isdisjoint(s.SEEDS))
        for k in SEEDS:self.assertEqual(tuple(map(len,v10.suite(k))),(32,32))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V15 required")
    run(z.output)
