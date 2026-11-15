"""Bounded change of investigation strategy based on observed contradictions."""
import sys
from pathlib import Path
for v in (112,115,116,117,124):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import compose as cm
import ambiguity as amb
import hypotheses as hyp
import information as info
import value_information as vi
s=amb.s
def explore(fit,oracle,cap):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    built=hyp.build(fit,min(400,cap));pool=built["pool"];events=[]
    for _ in range(2):
        states=oracle.available()
        if not states:break
        known=list(fit)+oracle.events
        scores=info.scores(pool,states)
        if max(scores.values(),default=0)>0:x=min(scores,key=lambda x:(-scores[x],x))
        else:x=min(states,key=lambda x:(-vi.distance(x,known),x))
        before=len(pool);y=oracle.observe(x);pool=info.retain(pool,x,y)
        events.append(dict(state=x,value=y,before=before,after=len(pool),scores=scores))
    return dict(pool=pool,initial_pool=len(built["pool"]),remaining_pool=len(pool),
        candidates=built["candidates"],interpreter_evaluations=built["interpreter_evaluations"],
        query_events=events,queries=list(oracle.events),signature_evaluations=0)
def solve(fit,oracle,cap=s.CAP):
    r=explore(fit,oracle,cap);pool=r.pop("pool")
    r.update(program=pool[0]["program"] if pool else None,switched=False)
    if not pool and r["candidates"]<cap:
        r["switched"]=True;r["reason"]="initial_empty" if not r["initial_pool"] else "all_eliminated"
        secondary=cm.split_search(list(fit)+r["queries"],cap-r["candidates"])
        r["secondary"]=secondary;r["candidates"]+=secondary["candidates"];r["program"]=secondary["program"]
    return r
