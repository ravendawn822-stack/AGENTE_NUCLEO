"""Offline experimental integration of finite branch synthesis and DAG planning."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,109,110,111,112,113):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
from decomposition import closure
import limits as lab
import partition
import partial
import compose as cm
import repair
s=lab.s
SEEDS=tuple(76000019+30001*i for i in range(16))
GRAPH={0:(),1:(),2:(0,),3:(0,1),4:(2,3),5:(3,1)}
GOALS=(4,5)
BUDGET=3600
def write(path,value):
    with path.open("x",encoding="utf-8") as fp:json.dump(value,fp,indent=2,sort_keys=True)
def stage(out,n,summary,rows=None):
    d=out/f"NUCLEO_V{n}";d.mkdir();write(d/"summary.json",summary)
    if rows is not None:write(d/"records.json",rows)
def session_cases(seed):
    rows=lab.cases(seed);rng=random.Random(seed^0x11401)
    rows.extend((s.case(seed+8191,lab.st.primitive(rng,2),"elementary"),s.case(seed+16381,lab.st.control(rng),"elementary")))
    rng.shuffle(rows);return rows
def plan(public,mode,library,novel,budget=BUDGET):
    if type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("budget")
    left=budget;models={};ledger=[]
    for i in closure(GRAPH,GOALS):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0));continue
        if not left:
            ledger.append(dict(task=i,status="budget",candidates=0));continue
        r=repair.search(public[i]["fit"],public[i]["audit"],mode,library,novel,min(s.CAP,left))
        left-=r["candidates"]
        if left<0:raise AssertionError("budget")
        p=r["program"];ok=p is not None and s.matches(p,public[i]["audit"])
        if ok:models[i]=p
        ledger.append(dict(task=i,status="accepted" if ok else "failed",candidates=r["candidates"],search=r))
    return models,ledger,budget-left
def session(seed,mode,library,novel):
    cases=session_cases(seed)
    models,ledger,spent=plan([{k:c[k] for k in ("fit","audit")} for c in cases],mode,library,novel)
    rows=[s.score(models.get(i),c["held"]) for i,c in enumerate(cases)]
    goals=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        good=complete and all(rows[i]["solved"] for i in deps)
        goals.append(dict(goal=g,status="correct" if good else "wrong" if complete else "incomplete"))
    return dict(seed=seed,mode=mode,cases=cases,models=models,ledger=ledger,spent=spent,goals=goals,task_results=rows,
        correct_goals=sum(g["status"]=="correct" for g in goals),wrong_goals=sum(g["status"]=="wrong" for g in goals),
        incomplete_goals=sum(g["status"]=="incomplete" for g in goals),blocked=sum(x["status"]=="blocked" for x in ledger),
        **{k:sum(r[k] for r in rows) for k in ("correct","wrong","abstained","solved")})
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    library,novel,acquisition=lab.memory()
    rows=lab.run(library,novel)
    stage(out,109,dict(protocol="V109-limit-diagnosis-v1",aggregate=lab.summarize(rows,("weighted","generalized")),
        by_kind=[dict(kind=k,**a) for k in lab.KINDS for a in lab.summarize([r for r in rows if r["kind"]==k],("weighted","generalized"))],
        acquisition_candidates=acquisition),rows)
    parts=[dict(seed=seed,kind=c["kind"],fit=c["fit"],options=partition.options(c["fit"])) for seed in lab.DEV for c in lab.cases(seed)]
    stage(out,110,dict(protocol="V110-observed-partition-v1",tasks=len(parts),
        admissible=sum(bool(r["options"]) for r in parts),two_options=sum(len(r["options"])==2 for r in parts),
        available={p:sum(any(o["predicate"]==p for o in r["options"]) for r in parts) for p in partition.PREDS}),parts)
    splits=[dict(seed=seed,kind=c["kind"],search=cm.split_search(c["fit"])) for seed in lab.DEV for c in lab.cases(seed)]
    events=[e for r in splits for e in r["search"]["events"]]
    stage(out,111,dict(protocol="V111-partial-search-v1",tasks=len(splits),partitions_attempted=len(events),
        branch_searches=sum(len(e["parts"]) for e in events),
        branch_candidates=sum(b["candidates"] for e in events for b in e["parts"]),
        branches_with_candidate=sum(b["program"] is not None for e in events for b in e["parts"]),
        assembled=sum(e["assembled"] for e in events)),splits)
    rows=repair.batch(cm.SEEDS,cm.MODES,library,novel)
    stage(out,112,dict(protocol="V112-composition-v1",aggregate=repair.summary(rows,cm.MODES),
        by_kind=[dict(kind=k,**a) for k in lab.KINDS for a in repair.summary([r for r in rows if r["kind"]==k],cm.MODES)]),rows)
    rows=repair.batch(repair.SEEDS,repair.MODES,library,novel)
    stage(out,113,dict(protocol="V113-local-recovery-v1",aggregate=repair.summary(rows,repair.MODES)),rows)
    rows=[session(seed,mode,library,novel) for seed in SEEDS for mode in repair.MODES]
    keys=("correct_goals","wrong_goals","incomplete_goals","spent","correct","wrong","abstained","solved","blocked")
    summary=dict(protocol="V114-bounded-partial-planning-v1",aggregate=[dict(mode=m,sessions=len(SEEDS),
        **{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys}) for m in repair.MODES],
        budget=BUDGET,graph=GRAPH,goals=GOALS,deployment=False)
    stage(out,114,summary,rows);print(json.dumps(summary,indent=2))
class Tests(unittest.TestCase):
    def test_partition(self):
        rows=[(x,x) for x in range(-4,4)]
        for op in partition.options(rows):
            self.assertEqual(set(op["yes"])|set(op["no"]),set(rows))
            self.assertFalse(set(op["yes"])&set(op["no"]))
    def test_split(self):
        fit=[(x,2*(x+1) if x%2==0 else -x+1) for x in (-6,-4,-2,1,3,5)]
        r=cm.split_search(fit)
        self.assertTrue(s.matches(r["program"],fit))
        self.assertEqual(r["candidates"],sum(e["spent"] for e in r["events"]))
        for cap in (0,1,2,19):
            self.assertLessEqual(cm.split_search(fit,cap)["candidates"],cap)
    def test_repair_cap(self):
        c=lab.cases(lab.DEV[0])[0]
        for mode in repair.MODES:
            r=repair.search(c["fit"],c["audit"],mode,(),(),cap=60)
            self.assertLessEqual(r["candidates"],60)
    def test_planner(self):
        public=[{k:c[k] for k in ("fit","audit")} for c in session_cases(SEEDS[0])]
        for m in repair.MODES:
            models,ledger,spent=plan(public,m,(),(),budget=60)
            self.assertLessEqual(spent,60);self.assertEqual(spent,sum(e["candidates"] for e in ledger))
            self.assertTrue(all(set(GRAPH[i])<=models.keys() for i in models))
    def test_disjoint(self):
        sets=[set(x) for x in (lab.DEV,cm.SEEDS,repair.SEEDS,SEEDS)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
        for c in lab.cases(lab.DEV[0]):
            parts=[{x for x,y in c[k]} for k in ("fit","audit","held")]
            self.assertEqual([len(p) for p in parts],[6,4,7])
            self.assertEqual(len(set.union(*parts)),17)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V114 required")
    run(a.output.resolve())
if __name__=="__main__":main()
