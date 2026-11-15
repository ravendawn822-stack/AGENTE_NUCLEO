"""One fixed offline experiment suite; no deployment or recursive optimization."""
import argparse,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (79,80,81,82,83):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
import instrumentation as lab
import diagnosis,alternatives,comparison,retention

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    counts=lab.memory.train()
    rows=lab.run(out/"NUCLEO_V79",counts)
    diagnosis.run(out/"NUCLEO_V80",rows)
    alternatives.run(out/"NUCLEO_V81")
    compared=comparison.run(out/"NUCLEO_V82",rows,counts)
    rec=retention.run(out/"NUCLEO_V83",compared);p=retention.load(rec)
    frozen=p["recommended"]
    d=out/"NUCLEO_V84";d.mkdir()
    a=lab.batch(lab.TEST,"baseline",alternatives.POLICIES["baseline"],counts)
    b=lab.batch(lab.TEST,frozen,alternatives.POLICIES[frozen],counts)
    aa=comparison.describe(a);bb=comparison.describe(b)
    delta={k:bb["aggregate"][k]-aa["aggregate"][k] for k in lab.KEYS}
    checks=dict(utility_improved=delta["utility"]>0,no_more_wrong_goals=delta["wrong_goals"]<=0,
                no_more_wrong_predictions=delta["wrong_predictions"]<=0,no_fewer_correct_goals=delta["correct_goals"]>=0)
    lab.write(d/"baseline.json",a);lab.write(d/"recommended.json",b)
    result=dict(protocol="V84-frozen-evaluation-v1",recommendation=p,baseline=aa,recommended=bb,delta=delta,
                test_checks=checks,final_advantage=frozen!="baseline" and all(checks.values()),
                test_sessions=len(a)+len(b),deployment=False,counts=counts)
    lab.write(d/"summary.json",result);print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_splits(self):
        sets=[set(x) for x in (lab.DEV,lab.VALID,lab.TEST,lab.memory.TRAIN)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
    def test_scenario(self):
        seed=lab.DEV[0];g,a,_=lab.scenario(seed,"A","compatible");h,b,edits=lab.scenario(seed,"A","exceptions")
        self.assertEqual(g,h);self.assertEqual(len(edits),2)
        for i,(x,y) in enumerate(zip(a,b)):
            for k in ("points","held"):self.assertEqual([s for s,t in x[k]],[s for s,t in y[k]])
            diff=sum(t!=v for k in ("points","held") for (s,t),(u,v) in zip(x[k],y[k]))
            self.assertEqual(diff,3 if i in [e["task"] for e in edits] else 0)
    def test_baseline_equivalence(self):
        seed=lab.DEV[0];counts=lab.memory.train()
        g,data,_=lab.scenario(seed,"B","compatible");pts={i:t["points"] for i,t in enumerate(data)}
        old=lab.old.Cycle(g,lab.GOALS,pts,"integrated","B",counts,lab.CAP).run()
        new=lab.LabCycle(g,pts,"B",counts).execute(lab.baseline)
        self.assertEqual((old.models,old.events,old.spent),(new.models,new.events,new.spent))
    def test_budget_dependencies(self):
        counts=lab.memory.train()
        for name,policy in alternatives.POLICIES.items():
            row=lab.session(lab.DEV[0],"A","exceptions",name,policy,counts)
            self.assertLessEqual(row["spent"],lab.CAP)
            accepted=set()
            for e in row["events"]:
                if e["type"]=="investigate":
                    self.assertTrue(set(row["graph"][e["task"]])<=accepted)
                    if e["accepted"]:accepted.add(e["task"])
            self.assertEqual(accepted,set(row["models"]))
    def test_recommendation(self):
        def summary(utility,wrong=0):
            return dict(aggregate=dict(utility=utility,wrong_goals=0,wrong_predictions=wrong,correct_goals=2),
                        by_condition=[dict(condition=k,utility=utility) for k in lab.CONDITIONS])
        c=dict(candidate="near",validation={"baseline":summary(3),"near":summary(4)})
        p=retention.recommendation(c);self.assertTrue(p["approved"])
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"rec.json";retention.save(f,p);self.assertEqual(retention.load(f),p)
            x=json.loads(f.read_bytes());x["payload"]["recommended"]="baseline";f.write_text(json.dumps(x))
            with self.assertRaises(ValueError):retention.load(f)
        c["validation"]["near"]=summary(4,1);self.assertFalse(retention.recommendation(c)["approved"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V84 required")
    run(a.output.resolve())
if __name__=="__main__":main()
