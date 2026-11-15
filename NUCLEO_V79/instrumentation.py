"""Fixed offline evaluation harness. No agent code or permissions are modified."""
import json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V78"))
import autonomous_cycle as old
from autonomous_cycle import closure,probe,score,N,GOALS,memory
DEV=tuple(32000019+30001*i for i in range(24))
VALID=tuple(34000019+30001*i for i in range(24))
TEST=tuple(36000019+30001*i for i in range(32))
CONDITIONS=("compatible","exceptions")
CAP=12

def scenario(seed,context,condition):
    graph,data,_=old.scenario(seed,context,"compatible")
    rng=random.Random(seed^0x7901);edits=[]
    if condition=="exceptions":
        for i in rng.sample(range(len(data)),2):
            edits_for_task={s:rng.randrange(1,N) for s in rng.sample(range(N),3)}
            t=data[i]
            data[i]=dict(t,**{key:[(s,(v+edits_for_task.get(s,0))%N) for s,v in t[key]]
                             for key in ("points","held")})
            edits.append(dict(task=i,delta=edits_for_task))
    elif condition!="compatible":raise ValueError("condition")
    return graph,data,edits

def baseline(ready,required,goals,graph,models,failed,blocked):
    return ready[0]

class LabCycle(old.Cycle):
    def __init__(self,graph,points,context,counts):
        super().__init__(graph,GOALS,points,"integrated",context,counts,CAP)
    def execute(self,select):
        while self.spent<self.budget and not set(self.goals)<=self.models.keys():
            ready=[i for i in self.order if i not in self.models and i not in self.failed and i not in self.blocked
                   and all(p in self.models for p in self.graph[i])]
            if not ready:break
            i=select(ready,self.required,self.goals,self.graph,self.models,self.failed,self.blocked)
            if i not in ready:raise ValueError("invalid schedule")
            self.events.append(dict(type="goal_decomposition",task=i,requires=self.graph[i],spent=self.spent))
            accepted=False
            for d in self.families:
                if self.spent>=self.budget:break
                h=probe(self.points[i],d);self.spent+=1
                self.events.append(dict(type="investigate",task=i,family=d,accepted=h is not None,spent=self.spent))
                if h is not None:
                    self.models[i]=h;accepted=True;break
            if not accepted:
                if self.spent>=self.budget:
                    self.events.append(dict(type="budget_stop",task=i,spent=self.spent));break
                self.failed.add(i);self.revise()
        return self

def session(seed,context,condition,name,select,counts):
    graph,data,edits=scenario(seed,context,condition)
    points={i:t["points"] for i,t in enumerate(data)}
    cycle=LabCycle(graph,points,context,counts).execute(select)
    result,rows,goals=old.evaluate(cycle,data)
    result["utility"]=10*result["correct_goals"]-40*result["wrong_goals"]-result["spent"]
    if cycle.spent>CAP:raise RuntimeError("budget")
    return dict(seed=seed,context=context,condition=condition,policy=name,**result,
                events=cycle.events,graph=graph,data=data,edits=edits,
                models=cycle.models,task_results=rows,goal_results=goals,required=cycle.required)

KEYS=("goals","correct_goals","wrong_goals","incomplete_goals","spent","solved","failed","blocked",
      "revisions","correct_predictions","wrong_predictions","abstained","utility")
def aggregate(rows):
    return dict(sessions=len(rows),**{k:sum(r[k] for r in rows) for k in KEYS})
def split(rows):
    return [dict(condition=c,**aggregate([r for r in rows if r["condition"]==c])) for c in CONDITIONS]
def contexts(rows):
    return [dict(context=c,**aggregate([r for r in rows if r["context"]==c])) for c in memory.CONTEXTS]
def batch(seeds,name,select,counts):
    return [session(seed,c,k,name,select,counts) for seed in seeds for c in memory.CONTEXTS for k in CONDITIONS]
def write(path,value):
    with path.open("x",encoding="utf-8") as f:json.dump(value,f,indent=2,sort_keys=True)
def run(out,counts):
    out.mkdir(parents=True,exist_ok=False)
    rows=batch(DEV,"baseline",baseline,counts)
    write(out/"sessions.json",rows)
    summary=dict(protocol="V79-instrumentation-v1",aggregate=aggregate(rows),by_condition=split(rows),by_context=contexts(rows))
    write(out/"summary.json",summary)
    return rows
