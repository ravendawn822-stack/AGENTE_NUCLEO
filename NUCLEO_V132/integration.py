"""Fixed offline evaluation of strategy monitoring and empirical selection."""
import argparse,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
for v in (125,127,129,130,131):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
from NUCLEO_V128 import selection as policy
import allocation as alloc
import composite as comp
import monitor
import context as ctx
from decomposition import closure
s=comp.s
SEEDS=tuple(98000019+30001*i for i in range(16))
def write(path,value):
    with path.open("x",encoding="utf-8") as fp:json.dump(value,fp,indent=2,sort_keys=True)
def stage(out,n,result,rows=None):
    d=out/f"NUCLEO_V{n}";d.mkdir();write(d/"summary.json",result)
    if rows is not None:write(d/"records.json",rows)
    return d
def plan(public,mode,seed,counts,budget=alloc.BUDGET):
    if type(budget) is not int or not 0<=budget<=alloc.BUDGET:raise ValueError("budget")
    left=budget;models={};ledger=[]
    for i in closure(alloc.GRAPH,alloc.GOALS):
        if any(p not in models for p in alloc.GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0,observations=0));continue
        if not left:
            ledger.append(dict(task=i,status="budget",candidates=0,observations=0));continue
        fit,oracle=public[i]
        r=comp.solve(fit,oracle,mode,seed+997*i,min(s.CAP,left),counts)
        left-=r["candidates"]
        if left<0:raise AssertionError("budget")
        p=r["program"]
        if p is not None:models[i]=p
        ledger.append(dict(task=i,status="accepted" if p is not None else "failed",candidates=r["candidates"],
            observations=len(r["queries"]),search=r))
    return models,ledger,budget-left
def session(seed,mode,counts):
    cases=alloc.cases(seed)
    public=[(c["fit"],comp.amb.Oracle(c["audit"],2)) for c in cases]
    models,ledger,spent=plan(public,mode,seed,counts)
    scores=[s.score(models.get(i),c["held"]) for i,c in enumerate(cases)]
    goals=[]
    for g in alloc.GOALS:
        deps=closure(alloc.GRAPH,[g]);complete=all(i in models for i in deps)
        good=complete and all(scores[i]["solved"] for i in deps)
        goals.append(dict(goal=g,status="correct" if good else "wrong" if complete else "incomplete"))
    right=sum(g["status"]=="correct" for g in goals);wrong=sum(g["status"]=="wrong" for g in goals)
    return dict(seed=seed,mode=mode,cases=cases,models=models,ledger=ledger,spent=spent,goals=goals,task_results=scores,
        correct_goals=right,wrong_goals=wrong,incomplete_goals=len(goals)-right-wrong,utility=10*right-40*wrong,
        blocked=sum(e["status"]=="blocked" for e in ledger),observations=sum(e["observations"] for e in ledger),
        **{k:sum(x[k] for x in scores) for k in ("correct","wrong","abstained","solved")})
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    train=comp.batch(policy.TRAIN,policy.MODES)
    counts=policy.train(train)
    stage(out,127,dict(protocol="V127-observable-context-v1",training_tasks=len(train)//len(policy.MODES),
        contexts={k:counts[k][policy.MODES[0]][0] for k in ctx.KEYS},
        by_context=[dict(context=k,aggregate=monitor.summarize([r for r in train if r["context"]==k],policy.MODES)) for k in ctx.KEYS]))
    d=out/"NUCLEO_V128";d.mkdir()
    path=d/"memory.json";policy.save(path,counts);counts=policy.load(path)
    write(d/"summary.json",dict(protocol="V128-frozen-selector-v1",counts=counts,
        global_choice=policy.pick(counts),training_candidates=sum(r["candidates"] for r in train),
        aggregate=monitor.summarize(train,policy.MODES)))
    write(d/"training.json",train)
    rows=comp.batch(monitor.SEEDS,comp.MODES,counts)
    all_results=monitor.summarize(rows,comp.MODES)
    stage(out,129,dict(protocol="V129-strategy-monitor-v1",aggregate=all_results,
        by_context=[dict(context=k,aggregate=monitor.summarize([r for r in rows if r["context"]==k],comp.MODES)) for k in ctx.KEYS]),rows)
    stage(out,130,dict(protocol="V130-switch-v1",aggregate=monitor.summarize(rows,("pool_active","expand_active","switch"))))
    stage(out,131,dict(protocol="V131-composite-v1",aggregate=all_results))
    sessions=[session(seed,m,counts) for seed in SEEDS for m in comp.MODES]
    keys=("correct_goals","wrong_goals","incomplete_goals","utility","spent","observations","blocked","correct","wrong","abstained","solved")
    aggregate=[]
    for mode in comp.MODES:
        rs=[r for r in sessions if r["mode"]==mode]
        selected=[e["search"]["selected"] for r in rs for e in r["ledger"] if "search" in e]
        aggregate.append(dict(mode=mode,sessions=len(rs),**{k:sum(r[k] for r in rs) for k in keys},
            selected={m:selected.count(m) for m in sorted(set(selected))}))
    result=dict(protocol="V132-meta-control-v1",aggregate=aggregate,budget=alloc.BUDGET,graph=alloc.GRAPH,goals=alloc.GOALS,
        global_choice=policy.pick(counts),deployment=False)
    stage(out,132,result,sessions);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_context(self):
        self.assertEqual(ctx.context([(-1,2),(0,2),(1,3)]),"monotone:low")
        self.assertEqual(ctx.context([(0,0),(1,4),(2,1),(3,3)]),"nonmonotone:high")
    def test_memory(self):
        rows=[dict(context=ctx.KEYS[0],mode=m,utility=10 if m=="switch" else 0,candidates=20) for m in policy.MODES]
        counts=policy.train(rows);self.assertEqual(policy.pick(counts),"switch")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"memory.json";policy.save(p,counts);self.assertEqual(policy.load(p),counts)
            e=json.loads(p.read_bytes());e["payload"]["schema"]=2;p.write_text(json.dumps(e))
            with self.assertRaises(ValueError):policy.load(p)
    def test_policies(self):
        counts=policy.train([])
        for c in comp.amb.lab.cases(monitor.SEEDS[0]):
            for mode in comp.MODES:
                r=comp.solve(c["fit"],comp.amb.Oracle(c["audit"],2),mode,1,cap=400,counts=counts)
                self.assertLessEqual(r["candidates"],400);self.assertLessEqual(len(r["queries"]),2)
                if r["program"] is not None:self.assertTrue(s.matches(r["program"],c["fit"]+r["queries"]))
    def test_planner(self):
        counts=policy.train([])
        for m in comp.MODES:
            public=[(c["fit"],comp.amb.Oracle(c["audit"],2)) for c in alloc.cases(SEEDS[0])]
            models,ledger,spent=plan(public,m,1,counts,budget=300)
            self.assertLessEqual(spent,300);self.assertEqual(spent,sum(e["candidates"] for e in ledger))
            self.assertTrue(all(e["observations"]<=2 for e in ledger))
            self.assertTrue(all(set(alloc.GRAPH[i])<=models.keys() for i in models))
    def test_split(self):
        sets=[set(x) for x in (policy.TRAIN,monitor.SEEDS,SEEDS)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
        for c in alloc.cases(SEEDS[0]):self.assertEqual(len({x for k in ("fit","audit","held") for x,y in c[k]}),17)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V132 required")
    run(a.output.resolve())
if __name__=="__main__":main()
