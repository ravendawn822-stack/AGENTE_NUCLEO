"""Fixed finite hypothesis vocabulary; record actual macro use in search paths."""
import heapq,itertools,random,sys
from pathlib import Path
for v in (94,103,104,105):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import structure as st
import selection as sel
import generalize as gen
from audit import assess
w=st.w;s=st.s
SEEDS=tuple(64000019+30001*i for i in range(24))
MODES=("weighted","learned","selected","generalized","random")
def cases(seed):
    rng=random.Random(seed^0x10600)
    p=st.primitive(rng,2)
    targets=(p+p+st.primitive(rng,1),
        st.control(rng)+st.primitive(rng,3),
        st.primitive(rng,3)+st.control(rng),st.primitive(rng,4))
    return [s.case(seed+997*j,p,k) for j,(p,k) in enumerate(zip(targets,("repeated_pattern","control_first","control_last","primitive")))]
def traced(fit,macros,cap=s.CAP):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    if not fit or len({x for x,t in fit})!=len(fit):raise ValueError("fit")
    vocab={a:1 for a in w.atoms(False)}
    for p in macros:
        p=w.validate(p)
        if p:vocab.setdefault(p,max(1,w.nodes(p)-1))
    for a in w.atoms(True)[6:]:vocab.setdefault(a,3)
    xs=tuple(x for x,t in fit);target=tuple(t for x,t in fit)
    q=[];counter=itertools.count();seen={(xs,0):0};cache={};checked=0;pruned=0
    def extend(path,signature,depth,cost):
        if depth<s.DEPTH:
            for a,v in vocab.items():heapq.heappush(q,(cost+v,next(counter),path,signature,depth+1,a))
    if cap:
        checked=1
        if xs==target:return dict(program=(),path=(),candidates=1,pruned=0,cost=0)
        extend((),xs,0,0)
    while q and checked<cap:
        cost,_,path,signature,depth,a=heapq.heappop(q);checked+=1
        path=path+(a,);program=tuple(i for block in path for i in block)
        try:
            w.validate(program);v=[]
            for x in signature:
                key=(a,x)
                if key not in cache:cache[key]=s.execute(a,x)
                v.append(cache[key])
            value=tuple(v)
        except w.Invalid:continue
        if value==target:return dict(program=program,path=path,candidates=checked,pruned=pruned,cost=cost)
        key=(value,depth)
        if key in seen and seen[key]<=cost:pruned+=1;continue
        seen[key]=cost;extend(path,value,depth,cost)
    return dict(program=None,path=(),candidates=checked,pruned=pruned,cost=None)
def search(fit,mode,library,novel,control,cap=s.CAP):
    if mode=="selected":macros,scores,rank=sel.select(fit,library)
    elif mode in MODES:
        macros={"weighted":(),"learned":library,"generalized":library+novel,"random":library+control}[mode]
        scores=[];rank=0
    else:raise ValueError("mode")
    r=traced(fit,macros,cap)
    extra=novel if mode=="generalized" else control if mode=="random" else ()
    r.update(ranking_evaluations=rank,ranking_scores=scores,extra_used=sum(x in extra for x in r["path"]))
    return r
def batch(seeds,generator,library,novel,control):
    rows=[]
    for seed in seeds:
        for j,c in enumerate(generator(seed)):
            for mode in MODES:
                r=search(c["fit"],mode,library,novel,control)
                a=assess(c,r)
                emitted=a["program"] is not None
                rows.append(dict(seed=seed,task=j,mode=mode,case=c,search=r,
                    ranking_evaluations=r["ranking_evaluations"],extra_used=r["extra_used"],
                    extra_accepted=r["extra_used"]*int(emitted),**a))
    return rows
def aggregate(rows,modes=MODES):
    return [dict(mode=m,**s.aggregate(rs),ranking_evaluations=sum(r.get("ranking_evaluations",0) for r in rs),
        extra_used=sum(r.get("extra_used",0) for r in rs),extra_accepted=sum(r.get("extra_accepted",0) for r in rs))
        for m in modes for rs in ([r for r in rows if r["mode"]==m],)]
