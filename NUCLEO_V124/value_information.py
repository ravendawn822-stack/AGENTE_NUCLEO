"""Compare fixed policies with common finite observation interfaces."""
import random,sys
from fractions import Fraction
from pathlib import Path
for v in (115,116,117,118,121,122,123):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import ambiguity as amb
import hypotheses as hyp
import information as info
import observations as obs
import risk
import expansion as ex
s=amb.s
MODES=("pool_active","pool_consensus","split_random2","split_known4","expand_random","expand_active","risk_gate")
def distance(x,known):return min(abs(x-y) for y,_ in known)
def solve(fit,oracle,mode,seed,cap=s.CAP,counts=None):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    if mode in MODES[:4]:return obs.solve(fit,oracle,mode,seed,cap)
    if mode not in MODES:raise ValueError("mode")
    if mode=="risk_gate" and counts is None:raise ValueError("counts required")
    built=hyp.build(fit,min(400,cap));pool=built["pool"];initial=len(pool)
    spent=built["candidates"];expanded=False;added=0;emptied=0;events=[];expansion=None
    order=list(oracle.available());random.Random(seed^0x12400).shuffle(order)
    for _ in range(2):
        if not oracle.available():break
        known=list(fit)+oracle.events
        scores=info.scores(pool,oracle.available())
        if mode=="expand_random":x=next(x for x in order if x in oracle.available())
        elif max(scores.values(),default=0)>0:x=min(scores,key=lambda x:(-scores[x],x))
        else:x=min(oracle.available(),key=lambda v:(-distance(v,known),v))
        before=len(pool);y=oracle.observe(x);pool=info.retain(pool,x,y)
        if before and not pool:emptied+=1
        event=dict(state=x,value=y,disagreement=scores,before=before,after=len(pool))
        if not pool and not expanded and spent<cap:
            expanded=True;expansion=ex.expand(list(fit)+oracle.events,cap-spent)
            pool=expansion["pool"];spent+=expansion["candidates"];added=len(pool)
            event["after_expansion"]=added
        events.append(event)
    result=dict(program=pool[0]["program"] if pool else None,candidates=spent,queries=oracle.events,
        initial_pool=initial,remaining_pool=len(pool),expanded=expanded,expansion_added=added,
        eliminated_all=emptied,query_events=events,expansion=expansion,
        interpreter_evaluations=built["interpreter_evaluations"],signature_evaluations=expansion["signature_evaluations"] if expansion else 0)
    if counts is not None:
        prob=risk.estimate(counts,result);result["estimate"]=float(prob) if prob is not None else None
        if mode=="risk_gate" and prob is not None and prob<Fraction(4,5):
            result["ungated_program"]=result["program"];result["program"]=None;result["gated"]=True
    return result
def batch(seeds,modes,counts=None):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(amb.lab.cases(seed)):
            for mode in modes:
                r=solve(c["fit"],amb.Oracle(c["audit"],4 if mode=="split_known4" else 2),mode,seed+997*i,counts=counts)
                rows.append(dict(seed=seed,task=i,mode=mode,kind=c["kind"],case=c,search=r,**obs.evaluate(c,r)))
    return rows
def aggregate(rows,modes):
    base=obs.aggregate(rows,modes)
    for a in base:
        rs=[r for r in rows if r["mode"]==a["mode"]]
        a.update(expanded=sum(r["search"].get("expanded",False) for r in rs),
            gated=sum(r["search"].get("gated",False) for r in rs),
            signature_evaluations=sum(r["search"].get("signature_evaluations",0) for r in rs),
            incorrect_programs=sum(r["emitted"] and not r["solved"] for r in rs))
    return base
