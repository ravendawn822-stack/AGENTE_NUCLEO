"""Paired offline audit dataset and fixed external diagnostics."""
import random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V79"))
import instrumentation as lab
DEV=tuple(38000019+30001*i for i in range(24))
VALID=tuple(40000019+30001*i for i in range(24))
TEST=tuple(42000019+30001*i for i in range(32))
CAP=18

def scenario(seed,context,condition):
    graph,tasks,edits=lab.scenario(seed,context,condition)
    data=[]
    for i,t in enumerate(tasks):
        unseen=list(t["held"])
        random.Random(seed^(0x850000+i)).shuffle(unseen)
        data.append(dict(points=t["points"],audit=unseen[:2],held=unseen[2:],degree=t["degree"]))
    return graph,data,edits

class AuditOracle:
    """Budget for optional observations; never exposes final test states."""
    def __init__(self,observations):
        self.__values={i:tuple(rows) for i,rows in observations.items()}
        self.__used=set()
    def observe(self,i,j):
        if (i,j) in self.__used or j not in (0,1):raise ValueError("audit slot")
        point=self.__values[i][j]
        self.__used.add((i,j))
        return point

def diagnose(row):
    wrong_tasks={t["id"] for t in row["task_results"] if t["wrong"]>0}
    impact={i:sum(i in lab.closure(row["graph"],[g]) for g in lab.GOALS) for i in wrong_tasks}
    wrong_goals=sum(g["status"]=="wrong" for g in row["goal_results"])
    return dict(seed=row["seed"],context=row["context"],condition=row["condition"],
        wrong_tasks=len(wrong_tasks),wrong_goals=wrong_goals,shared_wrong_tasks=sum(v>=2 for v in impact.values()),
        potential_dependency_impact=sum(impact.values()),wrong_predictions=row["wrong_predictions"])

def run(out,rows):
    out.mkdir(parents=True,exist_ok=False)
    records=[diagnose(r) for r in rows]
    keys=("wrong_tasks","wrong_goals","shared_wrong_tasks","potential_dependency_impact","wrong_predictions")
    def totals(rs):return dict(sessions=len(rs),**{k:sum(r[k] for r in rs) for k in keys})
    summary=dict(protocol="V85-error-diagnosis-v1",aggregate=totals(records),
        by_condition=[dict(condition=k,**totals([r for r in records if r["condition"]==k])) for k in lab.CONDITIONS])
    lab.write(out/"diagnosis.json",records);lab.write(out/"summary.json",summary)
    return summary
