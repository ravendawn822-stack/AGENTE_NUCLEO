"""Bounded audit experiment; all actions are synthetic observations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V85"))
from diagnosis import lab,CAP,AuditOracle,scenario
from instrumentation import probe,old,baseline,GOALS,memory
from investigation import predict

class AuditCycle(old.Cycle):
    def __init__(self,graph,points,oracle,context,counts,select,audit_count):
        super().__init__(graph,GOALS,points,"integrated",context,counts,CAP)
        self.oracle=oracle;self.select=select;self.audit_count=audit_count
        self.probes=0;self.audits=0;self.audit_rejections=0;self.unfinished_audits=0
    def execute(self):
        while self.spent<self.budget and not set(self.goals)<=self.models.keys():
            ready=[i for i in self.order if i not in self.models and i not in self.failed and i not in self.blocked
                   and all(p in self.models for p in self.graph[i])]
            if not ready:break
            i=self.select(ready,self.required,self.goals,self.graph,self.models,self.failed,self.blocked)
            if i not in ready:raise ValueError("schedule")
            count=self.audit_count(i,self)
            if count not in (0,1,2):raise ValueError("audit count")
            self.events.append(dict(type="goal_decomposition",task=i,requires=self.graph[i],audit_required=count,spent=self.spent))
            h=None;tried=0
            for d in self.families:
                if self.spent>=self.budget:break
                h=probe(self.points[i],d);self.probes+=1;self.spent+=1;tried+=1
                self.events.append(dict(type="investigate",task=i,family=d,accepted=h is not None,spent=self.spent))
                if h is not None:break
            if h is None:
                if tried==len(self.families):self.failed.add(i);self.revise()
                continue
            verified=True
            for j in range(count):
                if self.spent>=self.budget:
                    self.unfinished_audits+=1;verified=False
                    self.events.append(dict(type="audit_budget_stop",task=i,spent=self.spent));break
                s,t=self.oracle.observe(i,j);p=predict(h,s)
                self.spent+=1;self.audits+=1
                self.events.append(dict(type="audit",task=i,slot=j,state=s,predicted=p,observed=t,spent=self.spent))
                if p!=t:
                    self.audit_rejections+=1;verified=False
                    self.failed.add(i);self.revise();break
            if verified:
                self.models[i]=h
                self.events.append(dict(type="commit",task=i,spent=self.spent))
        if self.spent!=self.probes+self.audits or self.spent>self.budget:raise RuntimeError("budget")
        return self

def count0(i,c):return 0
def count1(i,c):return 1
def count2(i,c):return 2

def session(seed,context,condition,name,policy,counts):
    graph,data,edits=scenario(seed,context,condition)
    points={i:t["points"] for i,t in enumerate(data)}
    oracle=AuditOracle({i:t["audit"] for i,t in enumerate(data)})
    c=AuditCycle(graph,points,oracle,context,counts,*policy).execute()
    result,rows,goals=old.evaluate(c,data)
    result.update(probes=c.probes,audits=c.audits,audit_rejections=c.audit_rejections,unfinished_audits=c.unfinished_audits)
    result["utility"]=10*result["correct_goals"]-40*result["wrong_goals"]-result["spent"]
    return dict(seed=seed,context=context,condition=condition,policy=name,**result,
        events=c.events,graph=graph,data=data,edits=edits,models=c.models,task_results=rows,goal_results=goals)
KEYS=lab.KEYS+("probes","audits","audit_rejections","unfinished_audits")
def aggregate(rows):
    return dict(sessions=len(rows),**{k:sum(r[k] for r in rows) for k in KEYS})
def describe(rows):
    return dict(aggregate=aggregate(rows),
        by_condition=[dict(condition=k,**aggregate([r for r in rows if r["condition"]==k])) for k in lab.CONDITIONS],
        by_context=[dict(context=k,**aggregate([r for r in rows if r["context"]==k])) for k in memory.CONTEXTS])
def batch(seeds,name,policy,counts):
    return [session(s,c,k,name,policy,counts) for s in seeds for c in memory.CONTEXTS for k in lab.CONDITIONS]
