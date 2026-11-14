"""V5.1: test inferred previous-value dependence with bounded numeric hypotheses."""
import argparse,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V5"))
import contract as c
from contract import st,h,v4
SEEDS=(1350013,1380007,1410011)
FAMILIES=("stateless","phase2","prev_linear","prev_abs","prev_square")
POLICIES=("old","extended_primitive","extended_memory")
FEATURES=("linear","abs")
CAP=500

def target(t,seq):
    f=t["family"];a=0;prev=0
    for i,x in enumerate(seq):
        a+=sum(h.atom(k,x) for k in t["terms"])
        if f=="phase2":a+=t["p"]*x*(i%2)
        if f=="prev_linear":a+=t["p"]*prev*x
        if f=="prev_abs":a+=t["p"]*abs(prev)*x
        if f=="prev_square":a+=t["p"]*prev*prev*x
        prev=x
    return a

def tasks(seed,seen):
    rng=random.Random(seed);rows=[]
    for f in FAMILIES:
        for i in range(12):
            while True:
                t=dict(family=f,terms=[h.term(rng) for _ in range(1+(rng.random()<.4))],p=rng.choice((-3,-2,-1,1,2,3)),id=f"{seed}/{f}/{i}")
                sig=tuple(target(t,z) for z in [*((x,) for x in range(-15,16)),*((x,y) for x in (-5,-2,0,1,4) for y in (-4,1,7)),(1,2,3,4)])
                if sig not in seen:seen.add(sig);rows.append(t);break
    rng.shuffle(rows);return rows

def feat(mode,x):return x if mode=="linear" else abs(x)
def predict(p,z):
    if p["kind"]=="old":return st.predict(p["program"],z)
    a=0;prev=0
    for x in z:
        a+=h.value(p["g"],0,x)+p["coefficient"]*feat(p["feature"],prev)*x
        prev=x
    return a

def extend(query,planner):
    # Derive g(x) from singletons; infer coefficient independently from differences.
    observed=tuple(query((x,))-query(()) for x in h.XS)
    e,n,orig,trace=planner.solve(observed)
    if e is None:return None,dict(status="unsolved_item",work=n,trace=trace)
    for mode in FEATURES:
        coeff=None;valid=True
        for p in (-3,-1,0,1,4):
            for x in (-4,-1,2,5):
                observed=query((p,x))-query((p,))-query((x,))+query(())
                denom=feat(mode,p)*x
                if denom==0:
                    if observed!=0:valid=False
                elif observed%denom:valid=False
                elif coeff is None:coeff=observed//denom
                elif coeff!=observed//denom:valid=False
            if not valid:break
        if not valid or coeff is None or abs(coeff)>100:continue
        p=dict(kind="extension",g=e,coefficient=coeff,feature=mode)
        if all(predict(p,z)==query(z) for z in st.GUARD):
            return p,dict(status="candidate",work=n,trace=trace,origins=orig)
    return None,dict(status="no_consistent_feature",work=n,trace=trace)

def solve(q,planner,policy):
    cache={};start=time.perf_counter_ns();logs=[]
    def query(z):
        z=tuple(z)
        if z not in cache:
            if len(cache)>=CAP:raise st.Budget()
            cache[z]=q(z)
        return cache[z]
    p=None
    try:
        old,m=st.solve(query,planner,"lesson_active");logs.append(m)
        if old is not None:p=dict(kind="old",program=old)
        elif policy!="old":
            p,m=extend(query,planner);logs.append(m)
    except st.Budget:logs.append(dict(status="budget"))
    return p,dict(queries=len(cache),trace=logs,ns=time.perf_counter_ns()-start)

def episode(t,planner,policy,seed):
    p,m=solve(lambda z:target(t,z),planner,policy);checks=[]
    if p:
        for z in st.tests(seed):
            y=target(t,z)
            try:v=predict(p,z)
            except (ValueError,ZeroDivisionError):v=None
            checks.append([z,y,v])
    return dict(task=t,policy=policy,program=p,emitted=p is not None,success=p is not None and all(y==v for _,y,v in checks),checks=checks,**m)

def metric(rows):
    n=len(rows);k=sum(r["success"] for r in rows);e=sum(r["emitted"] for r in rows)
    return dict(n=n,correct=k,wrong=e-k,abstained=n-e,mean_queries=sum(r["queries"] for r in rows)/n,mean_ns=sum(r["ns"] for r in rows)/n,
                extension_correct=sum(r["success"] and r["program"]["kind"]=="extension" for r in rows))

def run(folder,prior,banks):
    folder.mkdir(parents=True,exist_ok=False);rows=[];seen=set()
    for i,seed in enumerate(SEEDS):
        plans={k:c.bank(prior,banks,i,k!="primitive") for k in ("memory","primitive")}
        for j,t in enumerate(tasks(seed,seen)):
            for pol in POLICIES:
                r=episode(t,plans["primitive" if pol=="extended_primitive" else "memory"],pol,seed+j*7919)
                rows.append(dict(seed=seed,**r))
    result=dict(protocol="V5.1-v1",episodes=len(rows),aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metric([r for r in rows if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in FAMILIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2))
    with (folder/"raw.jsonl").open("w") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_PREV="+json.dumps(result,separators=(",",":")))

class Tests(unittest.TestCase):
    def test_extension(self):
        e=(h.ITEM,);planner=v4.Planner([dict(expr=e,vec=h.vector(e),source={"kind":"test"})])
        t=dict(family="prev_linear",terms=[("linear",1,0)],p=-2,id="test")
        p,m=extend(lambda z:target(t,z),planner)
        self.assertEqual(p["coefficient"],-2);self.assertEqual(predict(p,[7,-9,4]),target(t,[7,-9,4]))
    def test_outside(self):
        e=(h.ITEM,);planner=v4.Planner([dict(expr=e,vec=h.vector(e),source={"kind":"test"})])
        t=dict(family="prev_square",terms=[("linear",1,0)],p=2,id="test")
        self.assertIsNone(extend(lambda z:target(t,z),planner)[0])
    def test_suite(self):
        seen=set();self.assertEqual(len(tasks(SEEDS[0],seen)),60);self.assertEqual(len(seen),60)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);p.add_argument("--banks",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or not a.prior or not a.banks or ROOT not in a.output.resolve().parents:p.error("new output and snapshots required")
    run(a.output,a.prior,a.banks)
