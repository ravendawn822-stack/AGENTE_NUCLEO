"""Independent final comparison even when candidate was rejected."""
import sys
from pathlib import Path
for v in (85,86,87,88):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from diagnosis import TEST,lab
from audit_cycle import batch,describe,KEYS
from risk_order import POLICIES
from comparison import checks

def run(out,comparison,counts):
    out.mkdir(parents=True,exist_ok=False)
    candidate=comparison["candidate"]
    baseline=batch(TEST,"baseline",POLICIES["baseline"],counts)
    selected=batch(TEST,candidate,POLICIES[candidate],counts)
    a=describe(baseline);b=describe(selected);gate=checks(a,b)
    result=dict(protocol="V89-frozen-audit-test-v1",candidate=candidate,validation_approved=comparison["approved"],
        baseline=a,candidate_metrics=b,checks=gate,replicated=all(gate.values()),
        delta={k:b["aggregate"][k]-a["aggregate"][k] for k in KEYS},
        sessions=len(baseline)+len(selected),used_for_selection=False)
    lab.write(out/"baseline.json",baseline);lab.write(out/"candidate.json",selected);lab.write(out/"summary.json",result)
    return result
