"""Fixed offline evaluation of bounded uncertainty and observation policies."""
import argparse,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (115,121,122,123,124,125):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
import ambiguity as amb
import risk
import insufficiency as gap
import expansion as ex
import value_information as vi
import allocation as alloc
s=amb.s
def write(path,value):
    with path.open("x",encoding="utf-8") as f:json.dump(value,f,indent=2,sort_keys=True)
def stage(out,n,result,rows=None):
    d=out/f"NUCLEO_V{n}";d.mkdir();write(d/"summary.json",result)
    if rows is not None:write(d/"records.json",rows)
    return d
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    training=vi.batch(risk.TRAIN,("expand_active",))
    counts=risk.train(training)
    d=out/"NUCLEO_V121";d.mkdir()
    path=d/"memory.json";risk.save(path,counts);counts=risk.load(path)
    rows=vi.batch(gap.SEEDS,vi.MODES,counts)
    active=[r for r in rows if r["mode"]=="expand_active"]
    write(d/"summary.json",dict(protocol="V121-empirical-risk-v1",counts=counts,training_tasks=len(training),
        training_candidates=sum(r["candidates"] for r in training),calibration=risk.calibrate(active,counts)))
    write(d/"training.json",training)
    stage(out,122,dict(protocol="V122-pool-insufficiency-v1",**gap.diagnose(active)),active)
    stage(out,123,dict(protocol="V123-selective-expansion-v1",aggregate=vi.aggregate(rows,("pool_active","expand_active")),
        expanded_with_candidate=sum(r["search"]["expansion_added"]>0 for r in active),
        expanded_correct=sum(r["search"]["expanded"] and r["solved"] for r in active)))
    stage(out,124,dict(protocol="V124-information-value-v1",aggregate=vi.aggregate(rows,vi.MODES)),rows)
    sessions=[alloc.session(seed,m,counts) for seed in alloc.SEEDS for m in alloc.MODES]
    pair=("expand_active","adaptive_budget")
    stage(out,125,dict(protocol="V125-budget-allocation-v1",aggregate=alloc.aggregate(sessions,pair),budget=alloc.BUDGET),
        [r for r in sessions if r["mode"] in pair])
    result=dict(protocol="V126-uncertainty-planning-v1",aggregate=alloc.aggregate(sessions),
        budget=alloc.BUDGET,graph=alloc.GRAPH,goals=alloc.GOALS,utility_definition="10 correct -40 wrong goals",deployment=False)
    stage(out,126,result,sessions);print(json.dumps(result,indent=2))
class Tests(unittest.TestCase):
    def test_risk(self):
        counts={k:[0,0] for k in risk.KEYS};counts["one:initial"]=[8,2];counts["global"]=[8,2]
        result=dict(program=(),remaining_pool=1,expanded=False)
        self.assertAlmostEqual(float(risk.estimate(counts,result)),.75)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.json";risk.save(p,counts);self.assertEqual(risk.load(p),counts)
            e=json.loads(p.read_bytes());e["payload"]["schema"]=2;p.write_text(json.dumps(e))
            with self.assertRaises(ValueError):risk.load(p)
    def test_expansion(self):
        known=[(x,2*(x+1) if x%2==0 else -x+1) for x in (-6,-4,-2,1,3,5)]
        r=ex.expand(known,600);self.assertTrue(r["pool"]);self.assertLessEqual(r["candidates"],600)
        self.assertTrue(all(s.matches(h["program"],known) for h in r["pool"]))
        self.assertEqual(ex.expand(known,0)["candidates"],0)
    def test_policies(self):
        c=amb.lab.cases(gap.SEEDS[0])[0];counts={k:[0,0] for k in risk.KEYS}
        for m in vi.MODES:
            limit=4 if m=="split_known4" else 2
            r=vi.solve(c["fit"],amb.Oracle(c["audit"],limit),m,1,cap=500,counts=counts)
            self.assertLessEqual(r["candidates"],500);self.assertLessEqual(len(r["queries"]),limit)
            if r["program"] is not None:self.assertTrue(s.matches(r["program"],c["fit"]+r["queries"]))
    def test_planner(self):
        counts={k:[0,0] for k in risk.KEYS}
        for m in alloc.MODES:
            limit=4 if m=="split_known4" else 2
            public=[(c["fit"],amb.Oracle(c["audit"],limit)) for c in alloc.cases(alloc.SEEDS[0])]
            models,ledger,spent=alloc.plan(public,m,1,counts,budget=300)
            self.assertLessEqual(spent,300);self.assertEqual(spent,sum(e["candidates"] for e in ledger))
            self.assertTrue(all(e["observations"]<=limit and e["candidates"]<=e["allotment"] for e in ledger))
            self.assertTrue(all(set(alloc.GRAPH[i])<=models.keys() for i in models))
    def test_splits(self):
        sets=[set(x) for x in (risk.TRAIN,gap.SEEDS,alloc.SEEDS)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
        for c in alloc.cases(alloc.SEEDS[0]):
            self.assertEqual(len({x for k in ("fit","audit","held") for x,y in c[k]}),17)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V126 required")
    run(a.output.resolve())
if __name__=="__main__":main()
