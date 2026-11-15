"""Retrospective metrics, isolated from the scheduler."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V79"))
from instrumentation import closure,write,CONDITIONS,aggregate

def diagnose(row):
    completed=[g["goal"] for g in row["goal_results"] if g["status"]=="correct"]
    useful=set(closure(row["graph"],completed))
    attempts=[e for e in row["events"] if e["type"]=="investigate"]
    spent=len(attempts)
    if spent!=row["spent"]:raise ValueError("ledger mismatch")
    return dict(seed=row["seed"],context=row["context"],condition=row["condition"],
        spent=spent,completed=len(completed),
        outside_completed_closure=sum(e["task"] not in useful for e in attempts),
        failed_probes=sum(not e["accepted"] for e in attempts),
        budget_exhausted=spent==12 and row["incomplete_goals"]>0,
        blocked_stop=spent<12 and row["incomplete_goals"]>0)

def run(out,rows):
    out.mkdir(parents=True,exist_ok=False)
    records=[diagnose(r) for r in rows]
    keys=("spent","completed","outside_completed_closure","failed_probes","budget_exhausted","blocked_stop")
    def totals(rs):
        d={k:sum(r[k] for r in rs) for k in keys}
        d["cost_per_completed"]=d["spent"]/d["completed"] if d["completed"] else None
        return d
    result=dict(protocol="V80-diagnosis-v1",aggregate=totals(records),
                by_condition=[dict(condition=c,**totals([r for r in records if r["condition"]==c])) for c in CONDITIONS])
    write(out/"diagnosis.json",records);write(out/"summary.json",result)
    return result
