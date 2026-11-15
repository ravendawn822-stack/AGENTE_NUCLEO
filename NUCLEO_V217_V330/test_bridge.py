import argparse,json,tempfile,unittest
from pathlib import Path
from cognition import Learner,apply
from experiment import Environment
from bridge import CognitiveCore
import list_synthesis as synth
import vm
class Tests(unittest.TestCase):
    def test_induction(self):
        l=Learner(("opaque",))
        for x in range(2,8):l.observe((x,0),"opaque",(x+1 if x<7 else x,0))
        l.observe((7,1),"opaque",(7,1))
        self.assertEqual(l.predict((7,2),"opaque")[0],(7,2))
        self.assertEqual(l.predict((4,2),"opaque")[0],(5,2))
        self.assertEqual(l.predict((4,2),"opaque",True)[0],None)
        self.assertTrue(any(e["revised"] for e in l.events))
    def test_conflict(self):
        l=Learner(("a",));l.observe((0,),"a",(1,));l.observe((0,),"a",(2,))
        self.assertTrue(l.events[-1]["changed"])
        self.assertEqual(l.predict((0,),"a")[0],(2,))
    def test_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"memory.sqlite";env=Environment("cycle",123)
            c=CognitiveCore(p,env.actions,"test")
            for _ in range(25):c.tick(env)
            before=c.learner.report();c.ingest("sensor",[1,2],"fixture")
            c.close();c=CognitiveCore(p,env.actions,"test")
            self.assertEqual(before,c.learner.report())
            self.assertEqual(c.dialogue("mostre dado sensor")["data"]["value"],[1,2])
            self.assertEqual(c.dialogue("execute shell")["status"],"unknown")
            c.tick(env);self.assertEqual(len(c.learner.events),26);c.close()
    def test_limits(self):
        l=Learner(("a",))
        with self.assertRaises(ValueError):l.observe((1,),"a",(1,2))
        with self.assertRaises(ValueError):l.observe((1,),"b",(1,))
        with tempfile.TemporaryDirectory() as d:
            c=CognitiveCore(Path(d)/"m.sqlite",("a",),"test")
            with self.assertRaises(ValueError):c.ingest("x","execute","x")
            c.close()
def integrated(out):
    records=[]
    # Independent task seeds, no target motif sent to agent.
    for i in range(8):
        seed=331001+i*30001;family=("bounded","cycle","conditional","coupled")[i%4]
        env=Environment(family,seed);case=synth.cases(seed)[0]
        with tempfile.TemporaryDirectory() as d:
            c=CognitiveCore(Path(d)/"m.sqlite",env.actions,"integration",seed)
            for _ in range(16):c.tick(env)
            g=c.learn_tool(case["fit"],case["audit"])
            row=c.mem.goals()[0];p=row["result"].get("program")
            checked=synth.assess(case,dict(program=p))
            x,y=case["held"][0]
            b=c.apply_tool(g,x);z=c.stats(b);goals=c.mem.goals()
            actual=goals[1]["result"].get("value")
            correct=goals[1]["status"]=="done" and vm.value(actual)==vm.value(y)
            # Store observation as declared input; no claim of independent truth.
            c.ingest("obs",list(env.observe()),"fixture observation")
            records.append(dict(seed=seed,family=family,observations=c.learner.report(),case=case,
                checked=checked,correct_apply=correct,stats_status=goals[2]["status"],goals=goals,
                dialogue=c.dialogue("mostre dado obs"),memory=c.mem.counts()))
            c.close()
    out.write_text(json.dumps(records,indent=2))
    print(json.dumps(dict(tasks=len(records),full_held=sum(r["checked"]["solved"] for r in records),
        wrong_program=sum(r["checked"]["incorrect"] for r in records),apply=sum(r["correct_apply"] for r in records),
        stats_done=sum(r["stats_status"]=="done" for r in records)),indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--integration",type=Path);a=p.parse_args()
    if a.integration:integrated(a.integration)
    else:unittest.main(argv=[__file__],verbosity=2)
