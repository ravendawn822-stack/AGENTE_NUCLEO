"""Fixed offline synthesis suite and bounded declarative planning."""
import argparse,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,96,97,98,99,100,101):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
import weighted as w
import fragments as f
import abstractions as a
import composition as c
import transfer as t
from decomposition import closure
from integration import GRAPH,GOALS,BUDGET,write,stage
from audit import assess
s=w.syn
SEEDS=tuple(60000019+30001*i for i in range(16))
def session_cases(seed):
    tasks=c.old.cases(seed)+[s.case(seed+8191,s.seq("inc","double","neg"),"elementary"),
                          s.case(seed+16381,s.branch("negative","neg","inc"),"elementary")]
    random.Random(seed^0x10200).shuffle(tasks);return tasks
def plan(public,mode,library,control,budget=BUDGET):
    if type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("budget")
    remaining=budget;models={};ledger=[]
    for i in closure(GRAPH,GOALS):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0));continue
        if not remaining:
            ledger.append(dict(task=i,status="budget",candidates=0));continue
        r=c.search(public[i]["fit"],mode,library,control,min(s.CAP,remaining))
        remaining-=r["candidates"];p=r["program"];ok=p is not None and s.matches(p,public[i]["audit"])
        if ok:models[i]=p
        ledger.append(dict(task=i,status="accepted" if ok else "failed",search=r,candidates=r["candidates"]))
    return models,ledger,budget-remaining
def session(seed,mode,library,control):
    tasks=session_cases(seed);public=[{k:x[k] for k in ("fit","audit")} for x in tasks]
    models,ledger,spent=plan(public,mode,library,control)
    rows=[s.score(models.get(i),x["held"]) for i,x in enumerate(tasks)]
    goals=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        correct=complete and all(rows[i]["solved"] for i in deps)
        goals.append(dict(id=g,status="correct" if correct else "wrong" if complete else "incomplete"))
    return dict(seed=seed,mode=mode,cases=tasks,models=models,ledger=ledger,spent=spent,goals=goals,
        correct_goals=sum(g["status"]=="correct" for g in goals),wrong_goals=sum(g["status"]=="wrong" for g in goals),
        incomplete_goals=sum(g["status"]=="incomplete" for g in goals),task_results=rows,
        **{k:sum(r[k] for r in rows) for k in ("correct","wrong","abstained","solved")})
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    modes=("primitive","structured","weighted")
    rows=c.batch(w.SEEDS,s.cases,(),(),modes)
    kinds=("primitive","condition","repeat","outside")
    stage(out,97,dict(protocol="V97-cost-stratified-v1",aggregate=c.aggregate(rows,modes),
        by_kind=[dict(kind=k,**m) for k in kinds for m in c.aggregate([r for r in rows if r["kind"]==k],modes)]),rows)
    library,training,provenance=f.acquire()
    stage(out,98,dict(protocol="V98-fragment-acquisition-v1",library=library,acquired=len(library),
        training_accepted=sum(r["accepted"] for r in training),training_candidates=sum(r["search"]["candidates"] for r in training),
        provenance=provenance),training)
    ts=a.templates(library)
    d=stage(out,99,dict(protocol="V99-finite-abstractions-v1",templates=ts,template_count=len(ts),
        represented_members=len(set(p for temp in ts for p in a.members(temp))),instances=sum(len(a.members(temp)) for temp in ts),
        novel_instances=0))
    path=d/"memory.json";a.save(path,library,ts);library,ts=a.load(path)
    control=c.control_library(library)
    rows=c.batch(c.SEEDS,c.old.cases,library,control)
    stage(out,100,dict(protocol="V100-composition-v1",library=library,control=control,aggregate=c.aggregate(rows)),rows)
    rows=c.batch(t.SEEDS,t.cases,library,control)
    stage(out,101,dict(protocol="V101-transfer-v1",aggregate=c.aggregate(rows)),rows)
    rows=[session(seed,m,library,control) for seed in SEEDS for m in c.MODES]
    keys=("correct_goals","wrong_goals","incomplete_goals","spent","correct","wrong","abstained","solved")
    result=dict(protocol="V102-bounded-planning-v1",aggregate=[dict(mode=m,sessions=len(SEEDS),
        **{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys}) for m in c.MODES],
        budget=BUDGET,graph=GRAPH,goals=GOALS,library_size=len(library),deployment=False)
    stage(out,102,result,rows);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_weighted(self):
        for p in (s.seq("inc","double","neg"),s.branch("negative","neg","inc")):
            case=s.case(3,p,"test");r=w.search(case["fit"])
            self.assertTrue(s.matches(r["program"],case["fit"]))
            self.assertLessEqual(r["candidates"],s.CAP)
        self.assertIsNone(w.search([(0,1)],cap=0)["program"])
    def test_memory(self):
        l=(s.seq("inc","double"),s.seq("inc","neg"));ts=a.templates(l)
        self.assertEqual(len(ts),1);self.assertEqual(set(a.members(ts[0])),set(l))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.json";a.save(p,l,ts);self.assertEqual(a.load(p),(l,ts))
            o=json.loads(p.read_bytes());o["payload"]["schema"]=9;p.write_text(json.dumps(o))
            with self.assertRaises(ValueError):a.load(p)
    def test_control(self):
        l=(s.seq("inc","double"),s.seq("inc","neg"));r=c.control_library(l)
        self.assertEqual([len(x) for x in l],[len(x) for x in r])
        self.assertEqual(len({f.signature(x) for x in r}),len(r))
    def test_budget(self):
        cs=session_cases(SEEDS[0]);p=[{k:x[k] for k in ("fit","audit")} for x in cs]
        for m in c.MODES:
            models,ledger,spent=plan(p,m,(),(),60)
            self.assertLessEqual(spent,60);self.assertEqual(spent,sum(x["candidates"] for x in ledger))
            self.assertTrue(all(set(GRAPH[i])<=models.keys() for i in models))
    def test_split(self):
        sets=[set(x) for x in (w.SEEDS,f.TRAIN,c.SEEDS,t.SEEDS,SEEDS,s.SEEDS,c.old.TRAIN,c.old.TEST)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V102 required")
    run(a.output.resolve())
if __name__=="__main__":main()
