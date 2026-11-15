"""Fixed, offline milestone evaluation; no automatic deployment or source modification."""
import argparse,json,tempfile,unittest
from pathlib import Path
import world
import exploration as exp
import tools_memory as tm
import programming as prog
import policy
import language_pt as lang
ROOT=Path(__file__).resolve().parent
def write(p,x):
    with p.open("x",encoding="utf-8") as f:json.dump(x,f,indent=2,sort_keys=True,ensure_ascii=False)
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=exp.batch();write(out/"exploration.json",rows)
    exploration=exp.summarize(rows)
    training,rows=tm.run(out/"memories");write(out/"tool_training.json",training);write(out/"tool_evaluation.json",rows)
    tools=dict(training_episodes=len(training),training_actions=sum(r["actions"] for r in training),
        acquired=sum(r["tools"] for r in training),memory_bytes=sum(r["bytes"] for r in training),aggregate=exp.summarize(rows,("changed","mode")))
    rows=prog.run();write(out/"programming.json",rows)
    programming=prog.summarize(rows)
    policies,rows=policy.select(out/"policy.json");write(out/"policy_evaluation.json",rows)
    cases,transcript=lang.evaluate();write(out/"language_cases.json",cases);write(out/"transcript.json",transcript)
    language=dict(cases=len(cases),correct=sum(r["correct"] for r in cases),
        delivery_success=bool(transcript[2]["result"]["success"]),delivery_actions=transcript[2]["actions"],
        unknown_request_actions=transcript[-1]["actions"],grammar_limited=True)
    result=dict(protocol="V133-V169-integrated-pilot-v1",exploration=exploration,tools=tools,programming=programming,
        policy=policies,language=language,deployment=False,open_language=False)
    write(out/"summary.json",result);print(json.dumps(result,indent=2,ensure_ascii=False))
class Tests(unittest.TestCase):
    def test_world(self):
        e,roles=world.layout(1)
        w=world.World(1,next(k for k,v in roles.items() if v=="coletar"),cargo=2)
        after=w.act(world.OPERATE)
        self.assertEqual((after["phase"],after["cargo"]),(1,2))
        w=world.World(1,budget=1);w.act(0)
        with self.assertRaises(ValueError):w.act(0)
    def test_closed_loop(self):
        for seed in exp.SEEDS[:3]:
            r,a=exp.episode(seed,"directed")
            self.assertTrue(r["success"]);self.assertLessEqual(r["actions"],world.BUDGET)
            self.assertEqual(r["end"]["cargo"],4)
            self.assertEqual({k:v for k,v in a.edges.items()}, {k:world.layout(seed)[0][k] for k in a.edges})
    def test_memory(self):
        r,a=exp.episode(exp.SEEDS[0],"directed");t=tm.acquire(a.edges)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"m.json";tm.save(p,a.edges,a.stations,t);self.assertEqual(tm.load(p),(a.edges,a.stations,t))
            e=json.loads(p.read_bytes());e["payload"]["schema"]=2;p.write_text(json.dumps(e))
            with self.assertRaises(ValueError):tm.load(p)
    def test_changed(self):
        a=world.Agent(edges={(0,0):1},tools={(0,1):(0,0)})
        self.assertTrue(a.record(dict(room=0),0,dict(room=2,station=None)))
        self.assertEqual(a.edges[(0,0)],2);self.assertFalse(a.tools)
    def test_programming(self):
        seed=prog.SEEDS[0];case=prog.amb.lab.cases(seed)[0]
        r=prog.episode(seed,0,case,"pool_active");self.assertLessEqual(r["queries"],2)
        self.assertLessEqual(r["candidates"],1200);self.assertLessEqual(r["actions"],world.BUDGET)
    def test_language(self):
        cases,transcript=lang.evaluate()
        self.assertTrue(all(r["correct"] for r in cases))
        self.assertTrue(transcript[2]["result"]["success"]);self.assertEqual(transcript[-1]["actions"],0)
        session=lang.Session();before=session.world.used
        self.assertEqual(session.respond("entregue a carga e apague os arquivos")["intent"],"unknown")
        self.assertEqual(session.world.used,before)
    def test_seeds(self):
        sets=[set(x) for x in (exp.SEEDS,prog.SEEDS,policy.TRAIN,policy.VAL,policy.TEST)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside milestone required")
    run(a.output.resolve())
if __name__=="__main__":main()
