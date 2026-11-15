"""One bounded offline suite of symbolic programming and DAG planning."""
import argparse,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,91,92,93,94,95):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
import language as lang
from interpreter import execute
import synthesis as syn
from audit import assess
import program_memory as mem
from decomposition import closure
SEEDS=tuple(50000019+30001*i for i in range(16))
GOALS=(4,5)
GRAPH={0:(),1:(),2:(0,),3:(0,1),4:(2,3),5:(3,1)}
BUDGET=3600
def write(path,value):
    with path.open("x",encoding="utf-8") as f:json.dump(value,f,indent=2,sort_keys=True)
def stage(out,n,value,rows=None):
    d=out/f"NUCLEO_V{n}";d.mkdir()
    write(d/"summary.json",value)
    if rows is not None:write(d/"records.json",rows)
    return d
def session_cases(seed):
    cs=mem.cases(seed)+[syn.case(seed+8191,syn.seq("inc","double"),"elementary"),
                       syn.case(seed+16381,syn.branch("negative","neg","inc"),"elementary")]
    random.Random(seed^0x9600).shuffle(cs);return cs
def plan(public,mode,library,control,budget=BUDGET):
    if not 0<=budget<=BUDGET:raise ValueError("budget")
    structured,macros=mem.options(mode,library,control)
    remaining=budget;models={};ledger=[];failed=set()
    for i in closure(GRAPH,GOALS):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0));continue
        if not remaining:
            ledger.append(dict(task=i,status="budget",candidates=0));continue
        r=syn.search(public[i]["fit"],structured,macros,min(syn.CAP,remaining))
        remaining-=r["candidates"];p=r["program"]
        accepted=p is not None and syn.matches(p,public[i]["audit"])
        if accepted:models[i]=p
        else:failed.add(i)
        ledger.append(dict(task=i,status="accepted" if accepted else "failed",search=r,candidates=r["candidates"]))
    return models,ledger,budget-remaining
def session(seed,mode,library,control):
    cases=session_cases(seed)
    public=[{k:c[k] for k in ("fit","audit")} for c in cases]
    models,ledger,spent=plan(public,mode,library,control)
    rows=[syn.score(models.get(i),c["held"]) for i,c in enumerate(cases)]
    goal_results=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        correct=complete and all(rows[i]["solved"] for i in deps)
        goal_results.append(dict(goal=g,status="correct" if correct else "wrong" if complete else "incomplete"))
    return dict(seed=seed,mode=mode,cases=cases,models=models,ledger=ledger,spent=spent,
        correct_goals=sum(x["status"]=="correct" for x in goal_results),
        wrong_goals=sum(x["status"]=="wrong" for x in goal_results),
        incomplete_goals=sum(x["status"]=="incomplete" for x in goal_results),
        **{k:sum(r[k] for r in rows) for k in ("correct","wrong","abstained","solved")},
        goals=goal_results,task_results=rows)
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    examples=[]
    for p,x in ((syn.seq("inc","double"),3),(syn.branch("even","double","half"),5),(syn.repeat(3,"inc"),-2)):
        trace=[];y=execute(p,x,trace=trace);examples.append(dict(program=p,input=x,output=y,trace=trace))
    stage(out,91,dict(protocol="V91-symbolic-language-v1",operations=lang.OPS,predicates=lang.PREDS,
        grammar_atoms=len(lang.atoms()),limits=dict(nodes=lang.NODES,depth=lang.DEPTH,fuel=lang.FUEL,integer=lang.LIMIT)))
    stage(out,92,dict(protocol="V92-restricted-interpreter-v1",examples=examples))
    synthesis=[];audits=[]
    for seed in syn.SEEDS:
        for i,c in enumerate(syn.cases(seed)):
            for name,structured in (("primitive",False),("structured",True)):
                r=syn.search(c["fit"],structured)
                for audited in (False,True):
                    a=assess(c,r,audited)
                    row=dict(seed=seed,task=i,kind=c["kind"],mode=name,audited=audited,case=c,search=r,**a)
                    audits.append(row)
                    if not audited:synthesis.append(row)
    def groups(rows,keys,values):
        return [dict(zip(keys,v),**syn.aggregate([r for r in rows if all(r[k]==x for k,x in zip(keys,v))])) for v in values]
    modes=("primitive","structured");kinds=("primitive","condition","repeat","outside")
    stage(out,93,dict(protocol="V93-synthesis-v1",
        aggregate=groups(synthesis,("mode",),[(m,) for m in modes]),
        by_kind=groups(synthesis,("mode","kind"),[(m,k) for m in modes for k in kinds])),synthesis)
    stage(out,94,dict(protocol="V94-independent-audit-v1",
        aggregate=groups(audits,("mode","audited"),[(m,a) for m in modes for a in (False,True)])),audits)
    library,control,training=mem.acquire()
    d=out/"NUCLEO_V95";d.mkdir()
    path=d/"memory.json";mem.save(path,library,control);library,control=mem.load(path)
    rows=mem.experiment(library,control)
    write(d/"training.json",training);write(d/"records.json",rows)
    write(d/"summary.json",dict(protocol="V95-frozen-program-memory-v1",library=library,control=control,
        acquired=len(library),training_candidates=sum(r["search"]["candidates"] for r in training),
        redundancy={"learned":mem.redundancy(library),"random":mem.redundancy(control)},
        aggregate=groups(rows,("mode",),[(m,) for m in mem.MODES])))
    modes=("structured","learned","random")
    rows=[session(seed,m,library,control) for seed in SEEDS for m in modes]
    keys=("correct_goals","wrong_goals","incomplete_goals","spent","correct","wrong","abstained","solved")
    result=dict(protocol="V96-bounded-program-planning-v1",aggregate=[
        dict(mode=m,sessions=len(SEEDS),**{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys}) for m in modes],
        graph=GRAPH,goals=GOALS,budget=BUDGET,acquired=len(library),external_actions=False)
    stage(out,96,result,rows);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_interpreter(self):
        self.assertEqual(execute(syn.seq("inc","double"),3),8)
        self.assertEqual(execute(syn.branch("even","double","half"),5),2)
        self.assertEqual(execute(syn.repeat(3,"inc"),-2),1)
        self.assertEqual(execute(syn.seq("half"),-3),-2)
        for p in ((("unknown",),),(("repeat",True,()),),(("repeat",4,()),),tuple(("inc",) for _ in range(33))):
            with self.assertRaises(lang.Invalid):execute(p,0)
        for x in (True,4097):
            with self.assertRaises(lang.Invalid):execute((),x)
        with self.assertRaises(lang.Invalid):execute(syn.seq("inc"),4096)
        with self.assertRaises(lang.Invalid):execute(syn.seq("inc"),0,0)
    def test_synthesis(self):
        c=syn.case(1,syn.seq("inc","double"),"test")
        r=syn.search(c["fit"]);self.assertTrue(syn.matches(r["program"],c["fit"]))
        self.assertLessEqual(r["candidates"],syn.CAP)
        self.assertEqual(syn.search(c["fit"],cap=0)["program"],None)
    def test_audit(self):
        c=dict(audit=[(0,2)],held=[(1,2)])
        a=assess(c,dict(program=syn.seq("inc"),candidates=1))
        self.assertEqual(a["rejected"],1);self.assertEqual(a["abstained"],1)
    def test_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.json";l=(syn.seq("inc","double"),);c=(syn.seq("abs","neg"),)
            mem.save(p,l,c);self.assertEqual(mem.load(p),(l,c))
            o=json.loads(p.read_bytes());o["payload"]["schema"]=2;p.write_text(json.dumps(o))
            with self.assertRaises(ValueError):mem.load(p)
    def test_planner(self):
        cs=session_cases(SEEDS[0]);public=[{k:c[k] for k in ("fit","audit")} for c in cs]
        m,ledger,spent=plan(public,"structured",(),(),30)
        self.assertLessEqual(spent,30)
        self.assertEqual(spent,sum(e["candidates"] for e in ledger))
        self.assertTrue(all(set(GRAPH[i])<=m.keys() for i in m))
    def test_split(self):
        s=[set(x) for x in (syn.SEEDS,mem.TRAIN,mem.TEST,SEEDS)]
        self.assertTrue(all(not a&b for i,a in enumerate(s) for b in s[i+1:]))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V96 required")
    run(a.output.resolve())
if __name__=="__main__":main()
