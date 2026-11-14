"""V22: controlled integration of mathematical perception, memory and search."""
import argparse,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V21"))
import memory as mem
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V17"))
import transfer as gen
e,v=mem.e,mem.v
v9,v10=gen.v9,gen.v10
SEEDS=(3360017,3390023,3420031,3450041)
POLICIES=("generic","active","integrated","integrated_memory")
CAP=e.CAP

def suite(seed):
    train,final=mem.suite(seed)
    tasks=[dict(domain="piecewise",**t) for t in final]
    tasks.extend(dict(domain="structural",stratum=t["family"],**t) for t in gen.suite(seed) if t["family"] not in ("alias_linear","alias_hidden"))
    return train,tasks

def target(t,p):
    return e.target(t,p) if t["domain"]=="piecewise" else gen.target(t,*p)

def affine(obs):
    c=obs[(0,0)];a=obs[(1,0)]-c;b=obs[(0,1)]-c
    return all(a*x+b*y+c==z for (x,y),z in obs.items())

def candidate_values(candidate,points):
    kind,h=candidate
    if kind=="active":return tuple(e.value(h,p) for p in points)
    if kind=="symbolic":
        x,y=zip(*points)
        return v9.apply(h,x,y,{})
    raise ValueError(kind)

def consistent(candidate,obs):
    if candidate is None:return False
    try:return candidate_values(candidate,list(obs))==tuple(obs.values())
    except ZeroDivisionError:return False

def investigate(initial,ask,policy,learned=()):
    obs=dict(initial);trace=[];route=[];active_cost=0;symbolic_cost=0;expanded=False;methods=[]
    candidate=None
    def query(point):
        assert point in e.POOL and point not in obs
        assert len(trace)<CAP
        y=ask(point)
        obs[point]=y;trace.append(dict(point=point,response=y))
        return y
    if policy!="generic" and affine(obs):
        route.append("active")
        active_policy="memory_expand" if policy=="integrated_memory" else "expand"
        h,detail,active_cost,expanded,n=mem.investigate(initial,query,active_policy,learned)
        assert [r["point"] for r in detail]==[r["point"] for r in trace]
        if h is not None:
            candidate=("active",h)
    if candidate is None and policy!="active":
        route.append("generic")
        while len(trace)<CAP:
            remaining=[p for p in e.POOL if p not in obs]
            query(e.verify_point(remaining,trace))
        points=list(obs);answers=list(obs.values())
        first,meta=v10.solve(points,answers,{},3600)
        h,symbolic_cost,methods=gen.propose("portfolio",points,answers,{},first,meta["candidates"])
        if h is not None:candidate=("symbolic",h)
        assert symbolic_cost<=12000
    if candidate is not None and not consistent(candidate,obs):candidate=None
    return dict(candidate=candidate,trace=trace,queries=len(trace),route=route,methods=methods,
        expanded=expanded,hypothesis_evaluations=active_cost,symbolic_candidates=symbolic_cost)

def episode(t,policy,learned):
    obs={p:target(t,p) for p in v.INITIAL}
    start=time.perf_counter_ns()
    row=investigate(obs,lambda p:target(t,p),policy,learned)
    elapsed=time.perf_counter_ns()-start
    h=row["candidate"]
    ok=consistent(h,{p:target(t,p) for p in e.RESERVED})
    return dict(task=t,policy=policy,success=ok,emitted=h is not None,wall_ns=elapsed,**row)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[]
    for seed in SEEDS:
        train,final=suite(seed)
        path=out/f"{seed}.sqlite3";store=mem.Memory(path)
        for t in train:
            rr=mem.episode(t,"expand")
            added=rr["success"] and store.add(rr["candidate"][1],t["id"])
            training.append(dict(seed=seed,added=added,**rr))
        learned=store.snapshot();store.close();store=mem.Memory(path)
        assert store.snapshot()==learned
        snapshots.append(dict(seed=seed,skills=len(learned),sha=mem.digest(learned)))
        for t in final:
            for policy in POLICIES:
                rows.append(dict(seed=seed,**episode(t,policy,learned)))
        assert store.snapshot()==learned;store.close()
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            queries=sum(r["queries"] for r in rr),expansions=sum(r["expanded"] for r in rr),
            hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in rr),
            symbolic_candidates=sum(r["symbolic_candidates"] for r in rr),
            wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V22-integrated-math-v1",seeds=SEEDS,snapshots=snapshots,
        training=dict(n=len(training),added=sum(r["added"] for r in training),
            queries=sum(r["queries"] for r in training),hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in training)),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_domain=[dict(domain=d,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["domain"]==d])) for d in ("piecewise","structural") for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in sorted({r["task"]["stratum"] for r in rows}) for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for r in data:f.write(mem.encode(r)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            a,b=suite(s);self.assertEqual((len(a),len(b)),(12,72))
            self.assertEqual(len({(t["domain"],t["id"]) for t in b}),72)
    def test_route(self):
        for fn,expected in ((lambda p:2*p[0]+p[1]+1,"active"),(lambda p:p[0]**2+p[1],"generic")):
            obs={p:fn(p) for p in v.INITIAL}
            row=investigate(obs,fn,"integrated")
            self.assertEqual(row["route"][0],expected)
            self.assertTrue(consistent(row["candidate"],obs))
            self.assertLessEqual(row["queries"],CAP)
            pts=[r["point"] for r in row["trace"]]
            self.assertEqual(len(pts),len(set(pts)))
            self.assertTrue(set(pts)<=set(e.POOL))
            self.assertFalse(set(pts)&set(e.RESERVED))
    def test_no_hidden_feedback(self):
        t=dict(domain="piecewise",family="double",coefs=(1,2,3),parts=((0,1,7,1),(1,-1,9,2)))
        initial={p:target(t,p) for p in v.INITIAL}
        calls=[]
        def ask(p):
            calls.append(p)
            self.assertIn(p,e.POOL)
            return target(t,p)
        row=investigate(initial,ask,"integrated_memory")
        self.assertEqual(len(calls),row["queries"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V22 required")
    run(z.output)
