"""Bounded per-task budget allocation in a fixed declarative DAG."""
import random,sys
from pathlib import Path
for v in (74,115,124):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from decomposition import closure
import ambiguity as amb
import value_information as vi
s=amb.s
SEEDS=tuple(92000019+30001*i for i in range(16))
GRAPH={0:(),1:(),2:(0,),3:(0,1),4:(2,3),5:(3,1)}
GOALS=(4,5);BUDGET=3600
MODES=vi.MODES+("adaptive_budget",)
def cases(seed):
    rng=random.Random(seed^0x12501);rows=amb.lab.cases(seed)
    rows.extend((s.case(seed+8191,amb.lab.st.primitive(rng,2),"elementary"),
                 s.case(seed+16381,amb.lab.st.control(rng),"elementary")))
    rng.shuffle(rows);return rows
def plan(public,mode,seed,counts,budget=BUDGET):
    if type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("budget")
    if mode not in MODES:raise ValueError("mode")
    left=budget;models={};ledger=[];order=closure(GRAPH,GOALS)
    for j,i in enumerate(order):
        if any(p not in models for p in GRAPH[i]):
            ledger.append(dict(task=i,status="blocked",candidates=0,observations=0,allotment=0));continue
        allot=min(s.CAP,left//(len(order)-j) if mode=="adaptive_budget" else left)
        if not allot:
            ledger.append(dict(task=i,status="budget",candidates=0,observations=0,allotment=0));continue
        fit,oracle=public[i]
        r=vi.solve(fit,oracle,"expand_active" if mode=="adaptive_budget" else mode,seed+997*i,allot,counts)
        left-=r["candidates"]
        if r["candidates"]>allot or left<0:raise AssertionError("budget")
        p=r["program"];ok=p is not None and s.matches(p,list(fit)+r["queries"])
        if ok:models[i]=p
        ledger.append(dict(task=i,status="accepted" if ok else "failed",candidates=r["candidates"],
            observations=len(r["queries"]),allotment=allot,search=r))
    return models,ledger,budget-left
def session(seed,mode,counts):
    rows=cases(seed);limit=4 if mode=="split_known4" else 2
    public=[(c["fit"],amb.Oracle(c["audit"],limit)) for c in rows]
    models,ledger,spent=plan(public,mode,seed,counts)
    scores=[s.score(models.get(i),c["held"]) for i,c in enumerate(rows)]
    goals=[]
    for g in GOALS:
        deps=closure(GRAPH,[g]);complete=all(i in models for i in deps)
        correct=complete and all(scores[i]["solved"] for i in deps)
        goals.append(dict(goal=g,status="correct" if correct else "wrong" if complete else "incomplete"))
    right=sum(g["status"]=="correct" for g in goals);wrong=sum(g["status"]=="wrong" for g in goals)
    return dict(seed=seed,mode=mode,cases=rows,models=models,ledger=ledger,spent=spent,goals=goals,task_results=scores,
        correct_goals=right,wrong_goals=wrong,incomplete_goals=len(GOALS)-right-wrong,utility=10*right-40*wrong,
        blocked=sum(e["status"]=="blocked" for e in ledger),observations=sum(e["observations"] for e in ledger),
        **{k:sum(r[k] for r in scores) for k in ("correct","wrong","abstained","solved")})
def aggregate(rows,modes=MODES):
    keys=("correct_goals","wrong_goals","incomplete_goals","utility","spent","observations","blocked","correct","wrong","abstained","solved")
    return [dict(mode=m,sessions=sum(r["mode"]==m for r in rows),**{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys}) for m in modes]
