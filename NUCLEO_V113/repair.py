"""Bounded local retry from audit counterexamples; no cross-task learning."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V112"))
import compose as cm
lab=cm.lab;s=cm.s;w=cm.w
SEEDS=tuple(74000019+30001*i for i in range(24))
MODES=cm.MODES+("repair_direct","repair_split")
def search(fit,audit,mode,library,novel,cap=s.CAP):
    if mode in cm.MODES:return cm.search(fit,audit,mode,library,novel,cap)
    if mode not in MODES:raise ValueError("mode")
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    first=w.search(fit,cap=min(400,cap));p=first["program"];left=cap-first["candidates"]
    if p is not None and s.matches(p,audit):
        return dict(program=p,candidates=first["candidates"],first=first,retried=False,recovered=False)
    if p is None:
        why="no_candidate";known=fit+audit;counterexample=None
    else:
        why="audit_rejection";counterexample=next((pair for pair in audit if not s.matches(p,[pair])),None)
        if counterexample is None:raise AssertionError("missing counterexample")
        known=fit+[counterexample]
    if left<=0:return dict(program=None,candidates=first["candidates"],first=first,retried=False,recovered=False,reason=why)
    second=w.search(known,cap=left) if mode=="repair_direct" else cm.split_search(known,left)
    q=second["program"]
    return dict(program=q,candidates=first["candidates"]+second["candidates"],first=first,second=second,
        retried=True,recovered=q is not None and s.matches(q,audit),reason=why,counterexample=counterexample)
def batch(seeds,modes,library,novel):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(lab.cases(seed)):
            for mode in modes:
                r=search(c["fit"],c["audit"],mode,library,novel)
                rows.append(dict(seed=seed,task=i,kind=c["kind"],mode=mode,case=c,search=r,
                    retried=int(r.get("retried",False)),recovered=int(r.get("recovered",False)),**cm.evaluate(c,r)))
    return rows
def summary(rows,modes):
    result=lab.summarize(rows,modes)
    for a in result:
        subset=[r for r in rows if r["mode"]==a["mode"]]
        a.update(retries=sum(r.get("retried",0) for r in subset),recoveries=sum(r.get("recovered",0) for r in subset),
            recovery_from_no_candidate=sum(r.get("recovered",0) and r["search"].get("reason")=="no_candidate" for r in subset),
            recovery_from_audit=sum(r.get("recovered",0) and r["search"].get("reason")=="audit_rejection" for r in subset))
    return result
