"""Compare active and random observations; final values never enter the solver."""
import random,sys
from pathlib import Path
for v in (112,115,116,117):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import ambiguity as amb
import hypotheses as hyp
import information as info
import compose as cm
s=amb.s
SEEDS=tuple(80000019+30001*i for i in range(24))
MODES=("pool_random","pool_active","pool_consensus","split_random2","split_known4")
def solve(fit,oracle,mode,seed,cap=s.CAP,rank=None):
    if mode not in MODES+("pool_memory",):raise ValueError("mode")
    limit=4 if mode=="split_known4" else 2
    rng=random.Random(seed^0x11800)
    order=list(oracle.available());rng.shuffle(order)
    if mode.startswith("split_"):
        known=list(fit)+[(x,oracle.observe(x)) for x in order[:limit]]
        r=cm.split_search(known,cap)
        return dict(program=r["program"],candidates=r["candidates"],queries=oracle.events,search=r,
            initial_pool=0,remaining_pool=0,query_events=[],interpreter_evaluations=0)
    built=hyp.build(fit,cap);pool=built["pool"];initial=len(pool);events=[]
    for _ in range(limit):
        if not pool or not oracle.available():break
        if mode=="pool_random":
            x=next(x for x in order if x in oracle.available());scores=info.scores(pool,oracle.available())
        else:x,scores=info.choose(pool,oracle.available())
        y=oracle.observe(x);before=len(pool);pool=info.retain(pool,x,y)
        events.append(dict(state=x,value=y,scores=scores,before=before,after=len(pool)))
    if mode=="pool_consensus" and len(pool)!=1:p=None
    elif not pool:p=None
    elif mode=="pool_memory":
        if rank is None:raise ValueError("memory missing")
        p=min(enumerate(pool),key=lambda iv:(-rank(iv[1]),iv[0]))[1]["program"]
    else:p=pool[0]["program"]
    return dict(program=p,candidates=built["candidates"],queries=oracle.events,initial_pool=initial,
        remaining_pool=len(pool),query_events=events,interpreter_evaluations=built["interpreter_evaluations"],
        ambiguity=amb.ambiguity(pool,list(fit)+oracle.events))
def evaluate(c,r):
    p=r["program"];v=s.score(p,c["held"])
    return dict(**v,candidates=r["candidates"],emitted=int(p is not None),rejected=0,
        observations=len(r["queries"]),initial_pool=r["initial_pool"],remaining_pool=r["remaining_pool"],
        interpreter_evaluations=r["interpreter_evaluations"])
def batch(seeds,modes,rank=None):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(amb.lab.cases(seed)):
            for mode in modes:
                r=solve(c["fit"],amb.Oracle(c["audit"],4 if mode=="split_known4" else 2),mode,seed+997*i,rank=rank)
                rows.append(dict(seed=seed,task=i,kind=c["kind"],mode=mode,case=c,search=r,**evaluate(c,r)))
    return rows
def aggregate(rows,modes):
    return [dict(mode=m,**s.aggregate(rs),**{k:sum(r[k] for r in rs) for k in
        ("observations","initial_pool","remaining_pool","interpreter_evaluations")})
        for m in modes for rs in ([r for r in rows if r["mode"]==m],)]
