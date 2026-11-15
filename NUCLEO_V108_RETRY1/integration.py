"""Fixed, offline finite DSL generalization experiment; no deployment."""
import argparse,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,96,98,99,103,104,105,106,107):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
# NUCLEO_V96 has the same basename as this executable, so import only its
# stable graph semantics explicitly here rather than resolving integration.
from decomposition import closure
import structure as st
import selection as sel
import generalize as gen
import instances as ins
import extrapolation as ext
import fragments as f
import abstractions as a
s=st.s
SEEDS=tuple(68000019+30001*i for i in range(16))
GRAPH={0:(),1:(),2:(0,),3:(0,1),4:(2,3),5:(3,1)}
GOALS=(4,5)
BUDGET=3600
def write(path,value):
    with path.open("x",encoding="utf-8") as fp:json.dump(value,fp,indent=2,sort_keys=True)
def stage(out,n,summary,rows=None):
    p=out/f"NUCLEO_V{n}";p.mkdir();write(p/"summary.json",summary)
    if rows is not None:write(p/"records.json",rows)
    return p
def session_cases(seed):
    rows=st.cases(seed)
    rng=random.Random(seed^0x10801)
    rows.extend((s.case(seed+8191,st.primitive(rng,2),"elementary"),
                 s.case(seed+16381,st.control(rng),"elementary")))
    rng.shuffle(rows);return rows
def plan(public,mode,library,novel,control,budget=BUDGET):
    if type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("budget")
    left=budget;models={};ledger=[]
    for i in closure(GRAPH,GOALS):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0));continue
        if not left:
            ledger.append(dict(task=i,status="budget",candidates=0));continue
        r=ins.search(public[i]["fit"],mode,library,novel,control,min(s.CAP,left))
        left-=r["candidates"];p=r["program"]
        ok=p is not None and s.matches(p,public[i]["audit"])
        if ok:models[i]=p
        ledger.append(dict(task=i,status="accepted" if ok else "failed",candidates=r["candidates"],search=r))
    return models,ledger,budget-left
def session(seed,mode,library,novel,control):
    cases=session_cases(seed);public=[{k:x[k] for k in ("fit","audit")} for x in cases]
    models,ledger,spent=plan(public,mode,library,novel,control)
    rows=[s.score(models.get(i),c["held"]) for i,c in enumerate(cases)]
    outside=[s.score(models.get(i),ext.outside(c)) for i,c in enumerate(cases)]
    goals=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        right=complete and all(rows[i]["solved"] for i in deps)
        goals.append(dict(goal=g,status="correct" if right else "wrong" if complete else "incomplete"))
    return dict(seed=seed,mode=mode,cases=cases,models=models,ledger=ledger,spent=spent,
        correct_goals=sum(g["status"]=="correct" for g in goals),wrong_goals=sum(g["status"]=="wrong" for g in goals),
        incomplete_goals=sum(g["status"]=="incomplete" for g in goals),goals=goals,task_results=rows,
        extrapolation=outside,blocked=sum(x["status"]=="blocked" for x in ledger),
        ranking_evaluations=sum(x.get("search",{}).get("ranking_evaluations",0) for x in ledger),
        extra_accepted=sum(x.get("search",{}).get("extra_used",0) for x in ledger if x["status"]=="accepted"),
        **{k:sum(r[k] for r in rows) for k in ("correct","wrong","abstained","solved")})
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    library,training,provenance=f.acquire();ts=a.templates(library)
    rows,summary=st.describe(library)
    stage(out,103,dict(protocol="V103-observable-features-v1",by_kind=summary,library=library),rows)
    rows=sel.run(library)
    stage(out,104,dict(protocol="V104-fragment-selection-v1",aggregate=ins.aggregate(rows,sel.MODES)),rows)
    novel,origins,skipped=gen.propose(library,ts);control=gen.control(library,novel)
    stage(out,105,dict(protocol="V105-finite-instances-v1",library=library,templates=ts,
        novel=novel,control=control,novel_count=len(novel),origins=origins,equivalent_skipped=skipped,
        acquisition_candidates=sum(x["search"]["candidates"] for x in training),provenance=provenance))
    rows=ins.batch(ins.SEEDS,ins.cases,library,novel,control)
    stage(out,106,dict(protocol="V106-instance-transfer-v1",aggregate=ins.aggregate(rows)),rows)
    rows=ext.run(library,novel,control)
    stage(out,107,dict(protocol="V107-extrapolation-v1",aggregate=ins.aggregate(rows),outside=ext.aggregate(rows)),rows)
    rows=[session(seed,m,library,novel,control) for seed in SEEDS for m in ins.MODES]
    keys=("correct_goals","wrong_goals","incomplete_goals","spent","correct","wrong","abstained","solved","blocked","ranking_evaluations","extra_accepted")
    aggregate=[dict(mode=m,sessions=len(SEEDS),**{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys},
        extrapolation={k:sum(x[k] for r in rows if r["mode"]==m for x in r["extrapolation"])
            for k in ("correct","wrong","abstained","solved")}) for m in ins.MODES]
    result=dict(protocol="V108-generalization-planning-v1",aggregate=aggregate,budget=BUDGET,graph=GRAPH,goals=GOALS,
        library_size=len(library),novel_count=len(novel),deployment=False)
    stage(out,108,result,rows);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_traced_reference(self):
        for c in st.cases(st.SEEDS[0]):
            old=st.w.search(c["fit"],cap=400);new=ins.traced(c["fit"],(),400)
            self.assertEqual(old,{k:new[k] for k in old})
            if new["program"] is not None:
                self.assertEqual(new["program"],tuple(i for p in new["path"] for i in p))
    def test_propose(self):
        library=(s.seq("inc","double"),s.seq("neg","double"))
        novel,origins,_=gen.propose(library,a.templates(library))
        self.assertTrue(novel);self.assertEqual(len(novel),len(origins))
        self.assertFalse(gen.initial_signatures(library)&{f.signature(p) for p in novel})
        controls=gen.control(library,novel)
        self.assertEqual(len(controls),len(novel))
        self.assertEqual(len({f.signature(p) for p in controls}),len(controls))
    def test_budget(self):
        public=[{k:c[k] for k in ("fit","audit")} for c in session_cases(SEEDS[0])]
        for m in ins.MODES:
            models,ledger,spent=plan(public,m,(),(),(),60)
            self.assertLessEqual(spent,60);self.assertEqual(spent,sum(e["candidates"] for e in ledger))
            self.assertTrue(all(set(GRAPH[i])<=models.keys() for i in models))
    def test_split(self):
        sets=[set(x) for x in (st.SEEDS,ins.SEEDS,ext.SEEDS,SEEDS,f.TRAIN)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
        self.assertFalse(set(ext.OUTSIDE)&set(s.DOMAIN))
    def test_select(self):
        l=(s.seq("inc","double"),s.seq("neg","double"))
        chosen,scores,rank=sel.select([(1,4),(2,6)],l)
        self.assertEqual(chosen[0],l[0]);self.assertEqual(rank,4);self.assertEqual(scores[0],0)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V108 required")
    run(a.output.resolve())
if __name__=="__main__":main()
