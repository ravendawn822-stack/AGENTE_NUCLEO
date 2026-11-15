"""External recommendation with strict, fixed acceptance rules."""
import hashlib,json,sys
from pathlib import Path
for v in (79,81):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from instrumentation import write,CONDITIONS
from alternatives import POLICIES

def recommendation(comparison):
    candidate=comparison["candidate"]
    if candidate not in POLICIES or candidate=="baseline":raise ValueError("candidate")
    validation=comparison["validation"]
    old=validation["baseline"]["aggregate"];new=validation[candidate]["aggregate"]
    a={r["condition"]:r for r in validation["baseline"]["by_condition"]}
    b={r["condition"]:r for r in validation[candidate]["by_condition"]}
    checks=dict(utility_improved=new["utility"]>old["utility"],
                no_more_wrong_goals=new["wrong_goals"]<=old["wrong_goals"],
                no_more_wrong_predictions=new["wrong_predictions"]<=old["wrong_predictions"],
                no_fewer_correct_goals=new["correct_goals"]>=old["correct_goals"],
                no_stratum_utility_regression=all(b[k]["utility"]>=a[k]["utility"] for k in CONDITIONS))
    approved=all(checks.values())
    return dict(schema=1,candidate=candidate,recommended=candidate if approved else "baseline",
                approved=approved,checks=checks,baseline=old,challenger=new,
                deployment=False,human_review_required=True)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def save(path,payload):
    write(path,dict(payload=payload,sha256=hashlib.sha256(canonical(payload)).hexdigest()))
def load(path):
    with path.open("rb") as fp:raw=fp.read(65537)
    if len(raw)>65536:raise ValueError("oversize")
    envelope=json.loads(raw);p=envelope["payload"]
    if envelope["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("checksum")
    if p["schema"]!=1 or p["candidate"] not in POLICIES or p["candidate"]=="baseline" or p["recommended"] not in POLICIES:raise ValueError("invalid policy")
    expected={"utility_improved","no_more_wrong_goals","no_more_wrong_predictions","no_fewer_correct_goals","no_stratum_utility_regression"}
    if set(p["checks"])!=expected or any(type(v) is not bool for v in p["checks"].values()):raise ValueError("checks")
    if type(p["approved"]) is not bool or p["approved"]!=all(p["checks"].values()):raise ValueError("decision")
    if p["recommended"]!=(p["candidate"] if p["approved"] else "baseline"):raise ValueError("recommendation")
    if p["deployment"] is not False or p["human_review_required"] is not True:raise ValueError("scope")
    return p

def run(out,comparison):
    out.mkdir(parents=True,exist_ok=False)
    p=recommendation(comparison);path=out/"recommendation.json";save(path,p)
    recovered=load(path)
    if recovered!=p:raise RuntimeError("roundtrip")
    result=dict(protocol="V83-external-recommendation-v1",**p)
    write(out/"summary.json",result);return path
