"""V17: controlled structural transfer and insufficient-observation challenge."""
import argparse,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V16"))
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V15"))
import constraints as c
import composition as p
a,m,v10,v9,b=c.a,c.m,c.v10,c.v9,c.b
SEEDS=(2760013,2790017,2820023,2850031)
FAMILIES=("mixed_cubic","quartic","separable_abs","conditional","modular","nonlinear_interaction","alias_linear","alias_hidden")
POLICIES=("short","factorized","polynomial","constraints","portfolio","portfolio_probe")
PROBES=((12,0),(-12,0),(0,12),(0,-12))
CAP=8400

def suite(seed):
    rng=random.Random(seed);tasks=[]
    for family in FAMILIES[:6]:
        for i in range(6):
            k,l=rng.sample((-3,-2,-1,1,2,3),2)
            u,v=rng.sample((-2,-1,0,1,2),2)
            tasks.append(dict(id=f"{seed}/{family}/{i}",family=family,k=k,l=l,u=u,v=v))
    for i in range(6):
        k,l=rng.sample((-3,-2,-1,1,2,3),2)
        u,v=rng.sample((-2,-1,0,1,2),2)
        for family in FAMILIES[-2:]:
            tasks.append(dict(id=f"{seed}/{family}/{i}",family=family,k=k,l=l,u=u,v=v,pair=i))
    return tasks

def target(t,x,y):
    k,l,u,v,f=(t[z] for z in ("k","l","u","v","family"))
    a,b=x+u,y+v
    if f=="mixed_cubic":return k*a*a*b+l*a*b*b+u
    if f=="quartic":return k*a**4+l*b*b+v
    if f=="separable_abs":return k*abs(a)+l*b**3+u
    if f=="conditional":return k*a+l*b if a>b else l*a-k*b
    if f=="modular":return (k*a+l*b)%5+u
    if f=="nonlinear_interaction":return k*abs(a*b+v)+l*a
    base=k*x+l*y+u
    if f=="alias_linear":return base
    if f=="alias_hidden":return base+abs(x-8)+x-8
    raise ValueError(f)

def view(t,seed,probe=False):
    obs,held=v9.observations(seed)
    obs=list(dict.fromkeys([*m.GRID,*obs]))
    held=[tuple(z) for z in held if tuple(z) not in set(obs)|set(PROBES)]
    if probe:obs+=list(PROBES)
    return obs,[target(t,x,y) for x,y in obs],held

def extended(method,obs,ans,reg,cap):
    if method=="factorized":return a.alternate(obs,ans,reg,cap,"factorized")
    if method=="polynomial":return p.polynomial(obs,ans) if cap else (None,0)
    if method=="constraints":return c.constrained(obs,ans,cap,True)
    raise ValueError(method)

def propose(policy,obs,ans,reg,first,base_n):
    if first is not None or policy=="short":return first,base_n,[]
    order=("polynomial","constraints","factorized") if policy.startswith("portfolio") else (policy,)
    n=0;used=[]
    for method in order:
        if n>=CAP:break
        e,k=extended(method,obs,ans,reg,CAP-n)
        n+=k;used.append(method);assert n<=CAP
        if e is not None:return e,base_n+n,used
    return None,base_n+n,used

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];train=[]
    for seed in SEEDS:
        pool,_=v10.suite(seed);mem=v9.Registry(out/f"{seed}.sqlite3")
        for i,t in enumerate(pool):
            reg=mem.snapshot();v,held=m.task_view(t,seed+i*701)
            expected=[b.target(t,x,y) for x,y in held]
            rr=m.trial(v,reg,12000,expected,held,True)
            acquired=False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                acquired=mem.register(rr["expanded"],t["id"],held,expected)
            train.append(dict(seed=seed,task=t,acquired=acquired,**rr))
        reg=mem.snapshot();mem.close();frozen=v9.digest(reg)
        for i,t in enumerate(suite(seed)):
            # Paired functions deliberately share identical initial inputs and answers.
            z=seed*17+(36+t["pair"] if "pair" in t else i)*971
            obs,ans,held=view(t,z)
            obs2,ans2,held2=view(t,z,True)
            assert held==held2 and not set(obs2)&set(held)
            start=time.perf_counter_ns()
            first,meta=v10.solve(obs,ans,reg,3600)
            base_ns=time.perf_counter_ns()-start
            proposals={}
            for policy in POLICIES:
                start=time.perf_counter_ns()
                if policy=="portfolio_probe":
                    f,d=v10.solve(obs2,ans2,reg,3600)
                    e,n,used=propose(policy,obs2,ans2,reg,f,d["candidates"])
                    elapsed=time.perf_counter_ns()-start;queries=len(obs2)
                else:
                    e,n,used=propose(policy,obs,ans,reg,first,meta["candidates"])
                    elapsed=base_ns+time.perf_counter_ns()-start;queries=len(obs)
                assert n<=12000
                proposals[policy]=(e,n,used,elapsed,queries)
            expected=[target(t,x,y) for x,y in held]
            for policy,(e,n,used,elapsed,q) in proposals.items():
                rows.append(dict(seed=seed,task=t,policy=policy,candidate=e,emitted=e is not None,
                    success=v9.check(e,held,expected,reg),candidates=n,wall_ns=elapsed,
                    queries=q,methods=used))
        assert frozen==v9.digest(reg)
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            candidates=sum(r["candidates"] for r in rr),queries=sum(r["queries"] for r in rr),
            wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V17-transfer-ambiguity-v1",seeds=SEEDS,
        aggregate=[dict(policy=k,**metric([r for r in rows if r["policy"]==k])) for k in POLICIES],
        by_family=[dict(family=f,policy=k,**metric([r for r in rows if r["policy"]==k and r["task"]["family"]==f])) for f in FAMILIES for k in POLICIES],
        by_seed=[dict(seed=s,policy=k,**metric([r for r in rows if r["policy"]==k and r["seed"]==s])) for s in SEEDS for k in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",train)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(v9.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            tasks=suite(s);self.assertEqual(len(tasks),48)
            self.assertEqual(len({t["id"] for t in tasks}),48)
    def test_alias(self):
        ts=suite(SEEDS[0]);a,b=ts[-2:]
        obs,ans,held=view(a,9)
        obs2,ans2,held2=view(b,9)
        self.assertEqual((obs,ans,held),(obs2,ans2,held2))
        self.assertNotEqual(view(a,9,True)[1],view(b,9,True)[1])
        self.assertTrue(any(target(a,x,y)!=target(b,x,y) for x,y in held))
    def test_poly(self):
        t=suite(SEEDS[0])[0];obs,ans,held=view(t,44)
        e,n=extended("polynomial",obs,ans,{},CAP)
        self.assertTrue(v9.check(e,held,[target(t,x,y) for x,y in held],{}))
    def test_probe(self):
        t=suite(SEEDS[0])[0];obs,ans,held=view(t,99,True)
        self.assertFalse(set(obs)&set(held))
        self.assertEqual(len(obs),len(view(t,99)[0])+4)

if __name__=="__main__":
    q=argparse.ArgumentParser();q.add_argument("--self-test",action="store_true");q.add_argument("--output",type=Path);z=q.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:q.error("new output inside V17 required")
    run(z.output)
