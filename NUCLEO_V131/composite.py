"""Cross-check two bounded search procedures on the same observed evidence."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for v in (115,124,127,129,130):sys.path.insert(0,str(ROOT/f"NUCLEO_V{v}"))
from NUCLEO_V128 import selection as policy
import switching as sw
import monitor
import context as ctx
import value_information as vi
amb=sw.amb;s=sw.s
MODES=policy.MODES+("global","contextual")
def crosscheck(fit,oracle,cap=s.CAP):
    r=sw.explore(fit,oracle,cap);pool=r.pop("pool")
    r.update(program=None,agreement_attempted=False,agreement=False)
    if not pool or r["candidates"]>=cap:return r
    r["agreement_attempted"]=True
    secondary=sw.cm.split_search(list(fit)+r["queries"],cap-r["candidates"])
    r["secondary"]=secondary;r["candidates"]+=secondary["candidates"]
    p=secondary["program"]
    if p is None:return r
    try:values=tuple(s.execute(p,x) for x in s.DOMAIN)
    except sw.cm.w.Invalid:return r
    r["signature_evaluations"]=len(s.DOMAIN)
    match=next((h for h in pool if h["values"]==values),None)
    if match is not None:r["agreement"]=True;r["program"]=match["program"]
    return r
def solve(fit,oracle,mode,seed,cap=s.CAP,counts=None):
    if mode not in MODES:raise ValueError("mode")
    if mode in ("global","contextual"):
        if counts is None:raise ValueError("counts")
        selected=policy.pick(counts,fit if mode=="contextual" else None)
    else:selected=mode
    if selected=="switch":r=sw.solve(fit,oracle,cap)
    elif selected=="crosscheck":r=crosscheck(fit,oracle,cap)
    else:r=vi.solve(fit,oracle,selected,seed,cap)
    r["selected"]=selected;r["context"]=ctx.context(fit)
    if r["candidates"]>cap or len(r["queries"])>2:raise AssertionError("budget")
    if r["program"] is not None and not s.matches(r["program"],list(fit)+r["queries"]):raise AssertionError("consistency")
    return r
def batch(seeds,modes,counts=None):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(amb.lab.cases(seed)):
            for mode in modes:
                r=solve(c["fit"],amb.Oracle(c["audit"],2),mode,seed+997*i,counts=counts)
                p=r["program"];v=s.score(p,c["held"]);emitted=int(p is not None)
                rows.append(dict(seed=seed,task=i,mode=mode,kind=c["kind"],context=r["context"],selected=r["selected"],
                    case=c,search=r,candidates=r["candidates"],observations=len(r["queries"]),emitted=emitted,
                    utility=10*v["solved"]-40*(emitted-v["solved"]),**v))
    return rows
