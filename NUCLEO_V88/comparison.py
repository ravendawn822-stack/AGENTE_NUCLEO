"""External one-round selection and validation, fixed criteria."""
import sys
from pathlib import Path
for v in (85,86,87):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from diagnosis import DEV,VALID,lab
from audit_cycle import batch,describe
from risk_order import POLICIES

def checks(reference,candidate):
    a=reference["aggregate"];b=candidate["aggregate"]
    x={r["condition"]:r for r in reference["by_condition"]}
    y={r["condition"]:r for r in candidate["by_condition"]}
    return dict(utility_improved=b["utility"]>a["utility"],
        no_more_wrong_goals=b["wrong_goals"]<=a["wrong_goals"],
        no_more_wrong_predictions=b["wrong_predictions"]<=a["wrong_predictions"],
        no_fewer_correct_goals=b["correct_goals"]>=a["correct_goals"],
        no_stratum_utility_regression=all(y[k]["utility"]>=x[k]["utility"] for k in lab.CONDITIONS))

def run(out,dev,counts):
    out.mkdir(parents=True,exist_ok=False)
    summaries={name:describe(rows) for name,rows in dev.items()}
    candidate=min((name for name in dev if name!="baseline"),key=lambda n:(-summaries[n]["aggregate"]["utility"],n))
    valid={name:batch(VALID,name,POLICIES[name],counts) for name in ("baseline",candidate)}
    validation={name:describe(rows) for name,rows in valid.items()}
    gate=checks(validation["baseline"],validation[candidate])
    for stage,groups in (("dev",dev),("validation",valid)):
        for name,rows in groups.items():lab.write(out/f"{stage}_{name}.json",rows)
    result=dict(protocol="V88-audit-comparison-v1",candidate=candidate,development=summaries,validation=validation,
        checks=gate,approved=all(gate.values()),development_sessions=sum(map(len,dev.values())),
        validation_sessions=sum(map(len,valid.values())))
    lab.write(out/"summary.json",result)
    return result
