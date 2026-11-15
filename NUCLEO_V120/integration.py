"""Fixed offline suite: hypothesis sampling, observation selection and DAG planning."""
import argparse,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,115,116,117,118,119):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
from decomposition import closure
import ambiguity as amb
import hypotheses as hyp
import information as info
import observations as obs
import error_memory as mem
s=amb.s
SEEDS=tuple(86000019+30001*i for i in range(16))
GRAPH={0:(),1:(),2:(0,),3:(0,1),4:(2,3),5:(3,1)}
GOALS=(4,5);BUDGET=3600
def write(path,value):
    with path.open("x",encoding="utf-8") as f:json.dump(value,f,indent=2,sort_keys=True)
def stage(out,n,result,rows=None):
    d=out/f"NUCLEO_V{n}";d.mkdir();write(d/"summary.json",result)
    if rows is not None:write(d/"records.json",rows)
    return d
def diagnose():
    rows=[]
    for seed in amb.DEV:
        for j,c in enumerate(amb.lab.cases(seed)):
            built=hyp.build(c["fit"]);pool=built["pool"]
            a=amb.ambiguity(pool,c["fit"]);scores=info.scores(pool,[x for x,y in c["audit"]])
            rows.append(dict(seed=seed,task=j,kind=c["kind"],fit=c["fit"],ambiguity=a,search=built,
                query_scores=scores,nonzero_query_scores=sum(v>0 for v in scores.values())))
    return rows
def cases(seed):
    rng=random.Random(seed^0x12001);rows=amb.lab.cases(seed)
    rows.extend((s.case(seed+8191,amb.lab.st.primitive(rng,2),"elementary"),
                 s.case(seed+16381,amb.lab.st.control(rng),"elementary")))
    rng.shuffle(rows);return rows
def plan(public,mode,seed,rank,budget=BUDGET):
    if type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("budget")
    left=budget;models={};ledger=[]
    for i in closure(GRAPH,GOALS):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0,observations=0));continue
        if not left:
            ledger.append(dict(task=i,status="budget",candidates=0,observations=0));continue
        fit,oracle=public[i]
        r=obs.solve(fit,oracle,mode,seed+997*i,min(s.CAP,left),rank)
        left-=r["candidates"]
        if left<0:raise AssertionError("budget")
        p=r["program"];ok=p is not None and s.matches(p,list(fit)+r["queries"])
        if ok:models[i]=p
        ledger.append(dict(task=i,status="accepted" if ok else "failed",candidates=r["candidates"],
            observations=len(r["queries"]),search=r))
    return models,ledger,budget-left
def session(seed,mode,rank):
    rows=cases(seed);limit=4 if mode=="split_known4" else 2
    public=[(c["fit"],amb.Oracle(c["audit"],limit)) for c in rows]
    models,ledger,spent=plan(public,mode,seed,rank)
    scores=[s.score(models.get(i),c["held"]) for i,c in enumerate(rows)]
    goals=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        correct=complete and all(scores[i]["solved"] for i in deps)
        goals.append(dict(goal=g,status="correct" if correct else "wrong" if complete else "incomplete"))
    return dict(seed=seed,mode=mode,cases=rows,models=models,ledger=ledger,spent=spent,goals=goals,task_results=scores,
        correct_goals=sum(g["status"]=="correct" for g in goals),wrong_goals=sum(g["status"]=="wrong" for g in goals),
        incomplete_goals=sum(g["status"]=="incomplete" for g in goals),
        blocked=sum(e["status"]=="blocked" for e in ledger),observations=sum(e["observations"] for e in ledger),
        **{k:sum(r[k] for r in scores) for k in ("correct","wrong","abstained","solved")})
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=diagnose()
    stage(out,115,dict(protocol="V115-ambiguity-v1",tasks=len(rows),nonempty=sum(r["ambiguity"]["hypotheses"]>0 for r in rows),
        ambiguous=sum(r["ambiguity"]["hypotheses"]>1 for r in rows),
        disagreement_states=sum(r["ambiguity"]["disagreement_states"] for r in rows)),rows)
    stage(out,116,dict(protocol="V116-bounded-hypotheses-v1",tasks=len(rows),
        hypotheses=sum(r["ambiguity"]["hypotheses"] for r in rows),
        candidates=sum(r["search"]["candidates"] for r in rows),
        interpreter_evaluations=sum(r["search"]["interpreter_evaluations"] for r in rows),
        assembled=sum(r["search"]["assembled"] for r in rows),max_pool=max(r["ambiguity"]["hypotheses"] for r in rows)))
    stage(out,117,dict(protocol="V117-query-disagreement-v1",tasks=len(rows),
        tasks_with_informative_query=sum(r["nonzero_query_scores"]>0 for r in rows),
        informative_query_options=sum(r["nonzero_query_scores"] for r in rows)))
    rows=obs.batch(obs.SEEDS,obs.MODES)
    stage(out,118,dict(protocol="V118-active-observations-v1",aggregate=obs.aggregate(rows,obs.MODES)),rows)
    counts,training,cost=mem.train()
    d=out/"NUCLEO_V119";d.mkdir()
    path=d/"memory.json";mem.save(path,counts);counts=mem.load(path);rank=mem.ranker(counts)
    rows=obs.batch(mem.TEST,mem.MODES,rank)
    write(d/"summary.json",dict(protocol="V119-frozen-error-memory-v1",counts=counts,training_candidates=cost,
        training_tasks=len(training),aggregate=obs.aggregate(rows,mem.MODES)))
    write(d/"training.json",training);write(d/"records.json",rows)
    rows=[session(seed,m,rank) for seed in SEEDS for m in mem.MODES]
    keys=("correct_goals","wrong_goals","incomplete_goals","spent","observations","blocked","correct","wrong","abstained","solved")
    result=dict(protocol="V120-adaptive-investigation-v1",aggregate=[dict(mode=m,sessions=len(SEEDS),
        **{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys}) for m in mem.MODES],
        budget=BUDGET,graph=GRAPH,goals=GOALS,deployment=False)
    stage(out,120,result,rows);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_oracle(self):
        oracle=amb.Oracle([(1,4),(2,5)],1)
        self.assertEqual(oracle.observe(2),5)
        with self.assertRaises(ValueError):oracle.observe(1)
    def test_pool(self):
        fit=[(x,2*(x+1) if x%2==0 else -x+1) for x in (-6,-4,-2,1,3,5)]
        r=hyp.build(fit)
        self.assertTrue(r["pool"])
        self.assertEqual(len({h["values"] for h in r["pool"]}),len(r["pool"]))
        for h in r["pool"]:
            self.assertTrue(s.matches(h["program"],fit))
            self.assertEqual(h["values"],tuple(s.execute(h["program"],x) for x in s.DOMAIN))
        for cap in (0,1,60):self.assertLessEqual(hyp.build(fit,cap)["candidates"],cap)
    def test_information(self):
        pool=[{"values":tuple(x for x in s.DOMAIN)},{"values":tuple(x+(x==1) for x in s.DOMAIN)}]
        x,scores=info.choose(pool,(0,1,2));self.assertEqual(x,1);self.assertEqual(scores[0],0)
        self.assertEqual(len(info.retain(pool,1,2)),1)
    def test_memory(self):
        counts={k:[0,0] for k in mem.KEYS};counts["sequence:small"]=[3,1];counts["global"]=[3,1]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"memory.json";mem.save(p,counts);self.assertEqual(mem.load(p),counts)
            e=json.loads(p.read_bytes());e["payload"]["schema"]=2;p.write_text(json.dumps(e))
            with self.assertRaises(ValueError):mem.load(p)
    def test_budget(self):
        rank=mem.ranker({k:[0,0] for k in mem.KEYS})
        for m in mem.MODES:
            limit=4 if m=="split_known4" else 2
            public=[(c["fit"],amb.Oracle(c["audit"],limit)) for c in cases(SEEDS[0])]
            models,rows,spent=plan(public,m,SEEDS[0],rank,budget=60)
            self.assertLessEqual(spent,60);self.assertEqual(spent,sum(e["candidates"] for e in rows))
            self.assertTrue(all(e["observations"]<=limit for e in rows))
            self.assertTrue(all(set(GRAPH[i])<=models.keys() for i in models))
    def test_splits(self):
        sets=[set(x) for x in (amb.DEV,obs.SEEDS,mem.TRAIN,mem.TEST,SEEDS)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
        for c in cases(SEEDS[0]):
            self.assertEqual(len({x for k in ("fit","audit","held") for x,y in c[k]}),17)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V120 required")
    run(a.output.resolve())
if __name__=="__main__":main()
