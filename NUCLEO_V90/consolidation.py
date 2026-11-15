"""Fixed one-round offline evaluation; no deployment or code modification."""
import argparse,hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (85,86,87,88,89):sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
import diagnosis as diag
import audit_cycle as cycle
from risk_order import POLICIES
import comparison
import final_test
lab=diag.lab

def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(path,p):lab.write(path,dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest()))
def load(path):
    with path.open("rb") as fp:raw=fp.read(65537)
    if len(raw)>65536:raise ValueError("size")
    envelope=json.loads(raw);p=envelope["payload"]
    if envelope["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("checksum")
    if p["schema"]!=1 or p["options"]!=sorted(POLICIES) or p["candidate"] not in POLICIES or p["candidate"]=="baseline":raise ValueError("configuration")
    if any(type(p[k]) is not bool for k in ("validation_approved","test_replicated","confirmed_advantage")):raise ValueError("flags")
    if p["validation_recommendation"]!=(p["candidate"] if p["validation_approved"] else "baseline"):raise ValueError("recommendation")
    if p["confirmed_advantage"]!=(p["validation_approved"] and p["test_replicated"]):raise ValueError("confirmation")
    if p["deployment"] is not False or p["human_review_required"] is not True:raise ValueError("scope")
    return p

def run(out):
    out.mkdir(parents=True,exist_ok=False);counts=lab.memory.train()
    dev={n:cycle.batch(diag.DEV,n,p,counts) for n,p in POLICIES.items()}
    diag.run(out/"NUCLEO_V85",dev["baseline"])
    d=out/"NUCLEO_V86";d.mkdir()
    lab.write(d/"summary.json",dict(protocol="V86-audit-v1",development={n:cycle.describe(dev[n]) for n in ("baseline","dfs_audit1","dfs_audit2")}))
    d=out/"NUCLEO_V87";d.mkdir()
    lab.write(d/"summary.json",dict(protocol="V87-structural-risk-v1",development={n:cycle.describe(dev[n]) for n in ("baseline","ratio","ratio_audit1","ratio_impact")}))
    compared=comparison.run(out/"NUCLEO_V88",dev,counts)
    final=final_test.run(out/"NUCLEO_V89",compared,counts)
    p=dict(schema=1,protocol="V90-consolidation-v1",options=sorted(POLICIES),candidate=compared["candidate"],
        validation_approved=compared["approved"],test_replicated=final["replicated"],
        confirmed_advantage=compared["approved"] and final["replicated"],
        validation_recommendation=compared["candidate"] if compared["approved"] else "baseline",
        validation_checks=compared["checks"],test_checks=final["checks"],test_delta=final["delta"],
        origin="V85-V89 fixed offline suite",deployment=False,human_review_required=True)
    d=out/"NUCLEO_V90";d.mkdir()
    path=d/"recommendation.json";save(path,p)
    if load(path)!=p:raise RuntimeError("roundtrip")
    lab.write(d/"summary.json",p);print(json.dumps(p,indent=2))

class Tests(unittest.TestCase):
    def test_split(self):
        sets=[set(x) for x in (diag.DEV,diag.VALID,diag.TEST,lab.DEV,lab.VALID,lab.TEST,lab.memory.TRAIN)]
        self.assertTrue(all(not a&b for i,a in enumerate(sets) for b in sets[i+1:]))
    def test_observations(self):
        g,data,_=diag.scenario(diag.DEV[0],"A","exceptions")
        for t in data:
            groups=[{s for s,v in t[k]} for k in ("points","audit","held")]
            self.assertEqual([len(x) for x in groups],[6,2,9])
            self.assertEqual(len(set.union(*groups)),17)
    def test_baseline(self):
        g,data,_=diag.scenario(diag.DEV[0],"B","compatible");counts=lab.memory.train()
        points={i:t["points"] for i,t in enumerate(data)}
        ref=lab.old.Cycle(g,lab.GOALS,points,"integrated","B",counts,diag.CAP).run()
        new=cycle.AuditCycle(g,points,diag.AuditOracle({i:t["audit"] for i,t in enumerate(data)}),
            "B",counts,*POLICIES["baseline"]).execute()
        self.assertEqual((ref.models,ref.spent),(new.models,new.spent))
    def test_budget(self):
        counts=lab.memory.train()
        for n,p in POLICIES.items():
            r=cycle.session(diag.DEV[0],"A","exceptions",n,p,counts)
            self.assertLessEqual(r["spent"],diag.CAP)
            self.assertEqual(r["spent"],r["probes"]+r["audits"])
            committed=set()
            for e in r["events"]:
                if e["type"]=="investigate":self.assertTrue(set(r["graph"][e["task"]])<=committed)
                elif e["type"]=="commit":committed.add(e["task"])
            self.assertEqual(committed,set(r["models"]))
    def test_audit_rejection(self):
        graph={i:() for i in range(12)}
        points={i:[(s,s) for s in range(6)] for i in graph}
        values={i:[(6,7),(7,7)] for i in graph}
        c=cycle.AuditCycle(graph,points,diag.AuditOracle(values),"A",{"A":(8,3,1),"B":(1,3,8)},*POLICIES["dfs_audit1"]).execute()
        self.assertEqual(c.audit_rejections,4);self.assertEqual(c.models,{})
    def test_integrity(self):
        p=dict(schema=1,options=sorted(POLICIES),candidate="ratio",validation_approved=False,test_replicated=True,
            confirmed_advantage=False,validation_recommendation="baseline",deployment=False,human_review_required=True)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"conf.json";save(path,p);self.assertEqual(load(path),p)
            v=json.loads(path.read_bytes());v["payload"]["candidate"]="ratio_impact";path.write_text(json.dumps(v))
            with self.assertRaises(ValueError):load(path)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V90 required")
    run(a.output.resolve())
if __name__=="__main__":main()
