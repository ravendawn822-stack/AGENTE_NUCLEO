"""External one-round comparison; validation is not used for tuning."""
import sys
from pathlib import Path
for v in (79,81):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from instrumentation import DEV,VALID,batch,aggregate,split,contexts,write
from alternatives import POLICIES

def describe(rows):
    return dict(aggregate=aggregate(rows),by_condition=split(rows),by_context=contexts(rows))
def run(out,baseline_dev,counts):
    out.mkdir(parents=True,exist_ok=False)
    dev={"baseline":baseline_dev}
    for name in sorted(set(POLICIES)-{"baseline"}):
        dev[name]=batch(DEV,name,POLICIES[name],counts)
    summaries={name:describe(rows) for name,rows in dev.items()}
    candidate=min((name for name in dev if name!="baseline"),
                  key=lambda name:(-summaries[name]["aggregate"]["utility"],name))
    valid={name:batch(VALID,name,POLICIES[name],counts) for name in ("baseline",candidate)}
    validation={name:describe(rows) for name,rows in valid.items()}
    for stage,groups in (("dev",dev),("validation",valid)):
        for name,rows in groups.items():write(out/f"{stage}_{name}.json",rows)
    result=dict(protocol="V82-controlled-comparison-v1",candidate=candidate,development=summaries,
                validation=validation,development_sessions=sum(map(len,dev.values())),
                validation_sessions=sum(map(len,valid.values())))
    write(out/"summary.json",result)
    return result
