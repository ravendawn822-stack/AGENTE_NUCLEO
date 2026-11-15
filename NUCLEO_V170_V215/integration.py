"""V170–215: fixed six-phase integrated evaluation; no automatic deployment."""
import argparse,json,tempfile,unittest
from pathlib import Path
import vm
import list_synthesis as synth
import nucleus
import policy_lab
import operation_lab as lab
import dialogue
ROOT=Path(__file__).resolve().parent
def write(p,x):
    with p.open("x",encoding="utf-8") as f:json.dump(x,f,indent=2,sort_keys=True,ensure_ascii=False)
def memory_trial(path):
    xs=[(-2,0,3),(1,2),(-4,5,1),(0,0),(3,-1)]
    fit=[(x,synth.reference(("double",),x)) for x in xs]
    audit=[((2,-5),(4,-10)),((4,0),(8,0)),((-3,-1),(-6,-2))]
    payload=dict(fit=fit,audit=audit)
    core=nucleus.Nucleus(memory=nucleus.Memory(path),reuse=True)
    a=core.add("list_solve",payload)
    b=core.add("list_apply",dict(program=a,input=[2,-3]),(a,))
    core.run(limit=1);before=core.mem.goals();core.mem.close()
    core=nucleus.Nucleus(memory=nucleus.Memory(path,resume=True),reuse=True)
    core.run();c=core.add("list_solve",payload);after=core.run()
    result=dict(before=before,after=after,counts=core.mem.counts(),
        resumed_output=after[b-1]["result"]["value"],memory_reused=after[c-1]["result"]["memory_checks"]==1,
        candidates_saved=after[a-1]["result"]["candidates"]-after[c-1]["result"]["candidates"])
    core.mem.close();return result
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    mem=memory_trial(out/"memory.sqlite");write(out/"memory_trial.json",mem)
    library,acquisition=synth.acquire();write(out/"library.json",dict(library=library,records=acquisition))
    policy,training,validation,final=policy_lab.run(out/"policy.json",library)
    for name,rows in (("training",training),("validation",validation),("programs",final)):write(out/(name+".json"),rows)
    selected=policy["selected"]
    ops=[lab.episode(seed,m,library) for seed in synth.OPS for m in ("direct",selected)]
    # Keep distinct labels even when the gate rejects the candidate.
    for i,r in enumerate(ops):r["solver"]=r["mode"];r["mode"]="baseline" if i%2==0 else "gate"
    write(out/"operations.json",ops)
    csv=[lab.csv_episode(seed,m,library) for seed in synth.CSV for m in ("direct",selected)]
    for i,r in enumerate(csv):r["solver"]=r["mode"];r["mode"]="baseline" if i%2==0 else "gate"
    invalid=lab.invalid_csv();write(out/"csv.json",csv);write(out/"invalid_csv.json",invalid)
    phrases,transcript,goals=dialogue.evaluate()
    write(out/"language_cases.json",phrases);write(out/"transcript.json",transcript);write(out/"dialogue_goals.json",goals)
    summary=dict(protocol="V170-V215-integrated-pilot-v1",deployment=False,
        memory=dict(resumed_output=mem["resumed_output"],memory_reused=mem["memory_reused"],candidates_saved=mem["candidates_saved"],counts=mem["counts"]),
        programming=dict(library=library,acquisition_tasks=len(acquisition),acquisition_candidates=sum(r["search"]["candidates"] for r in acquisition),aggregate=synth.aggregate(final)),
        policy=policy,operations=lab.aggregate(ops,("success","solved","incorrect","output_correct","stats_correct","arithmetic_correct","second_correct","second_stats","navigation_correct","blocked","actions","candidates")),
        practical=lab.aggregate(csv,("transformed","stats_correct","solved","incorrect","wrong")),invalid_csv=sum(r["rejected"] for r in invalid),
        language=dict(cases=len(phrases),correct=sum(r["correct"] for r in phrases),goals=len(goals),completed=sum(g["status"]=="done" for g in goals),
            unknown_actions=sum(r["actions"] for r in transcript if r["intent"]=="unknown"),open_language=False))
    write(out/"summary.json",summary);print(json.dumps(summary,indent=2,ensure_ascii=False))
class Tests(unittest.TestCase):
    def test_vm(self):
        for seq in synth.MOTIFS:
            for x in ((),(0,-2,3,3),(1,-1,2,0,5,-5)):
                self.assertEqual(vm.run_pipeline(seq,x),synth.reference(seq,x))
        p=((("return",("call",0,("var",0))),),)
        with self.assertRaises(vm.Invalid):vm.execute(p,1)
        with self.assertRaises(vm.Invalid):vm.run_pipeline(("sum","inc"),[1])
        with self.assertRaises(vm.Invalid):vm.execute(vm.compile_pipeline(("double",)),[3],fuel=1)
        with self.assertRaises(vm.Invalid):vm.run_pipeline(("count",),[0]*33)
    def test_search(self):
        c=synth.cases(synth.TRAIN[0])[0]
        for mode in synth.MODES:
            r=synth.solve(c["fit"],c["audit"],mode)
            self.assertLessEqual(r["candidates"],synth.CAP)
            if r["program"] is not None:self.assertTrue(synth.matches(r["program"],c["fit"]+c["audit"]))
        self.assertEqual(len({x for k in ("fit","audit","held") for x,y in c[k]}),16)
    def test_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"mem.sqlite";r=memory_trial(p)
            self.assertEqual(r["resumed_output"],[4,-6]);self.assertTrue(r["memory_reused"])
            self.assertEqual(r["before"][1]["status"],"pending")
            self.assertEqual(r["counts"]["evidence"],3)
            with self.assertRaises(FileExistsError):nucleus.Memory(p)
    def test_dependency(self):
        core=nucleus.Nucleus()
        a=core.add("list_solve",dict(fit=[([1],[99])],audit=[([2],[99])]))
        b=core.add("list_apply",dict(program=a,input=[1]),(a,))
        rows=core.run()
        self.assertEqual(rows[0]["status"],"failed");self.assertEqual(rows[1]["status"],"blocked")
        core.mem.close()
    def test_operations(self):
        r=lab.episode(synth.OPS[0],"direct",())
        self.assertEqual(len(r["goals"]),8);self.assertLessEqual(r["actions"],120)
        self.assertTrue(all(g["status"]!="pending" for g in r["goals"]))
    def test_csv(self):
        self.assertTrue(all(r["rejected"] for r in lab.invalid_csv()))
        self.assertEqual(lab.parse_csv("value,category\n1,A\n-2,B\n"),((1,-2),["A","B"]))
        r=lab.csv_episode(synth.CSV[0],"direct",());self.assertTrue(r["stats_correct"])
    def test_dialogue(self):
        phrases,transcript,goals=dialogue.evaluate()
        self.assertTrue(all(r["correct"] for r in phrases))
        self.assertEqual(transcript[0]["actions"],0);self.assertEqual(transcript[3]["actions"],0)
        self.assertEqual(transcript[6]["actions"],0);self.assertEqual(len(goals),2)
        self.assertTrue(all(g["status"]=="done" for g in goals))
        self.assertEqual(sum(r["actions"] for r in transcript if r["intent"]=="unknown"),0)
    def test_seeds(self):
        sets=[set(x) for x in (synth.LIB,synth.TRAIN,synth.VAL,synth.TEST,synth.OPS,synth.CSV)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside milestone required")
    run(a.output.resolve())
if __name__=="__main__":main()
