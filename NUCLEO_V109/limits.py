"""Finite task generator and external diagnostic; no target labels in search."""
import random,sys
from pathlib import Path
for v in (93,97,98,99,103,105,106):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import structure as st
import fragments as f
import abstractions as a
import generalize as gen
import instances as ins
from audit import assess
s=st.s;w=st.w
DEV=tuple(70000019+30001*i for i in range(16))
KINDS=("parity","sign","primitive","mixed")
def cases(seed):
    rng=random.Random(seed^0x10900)
    def branched(pred):
        return (("if",pred,st.primitive(rng,rng.randrange(2,4)),st.primitive(rng,rng.randrange(2,4))),)
    targets=(branched("even"),branched("negative"),st.primitive(rng,rng.randrange(3,6)),
        st.control(rng)+st.primitive(rng,2)+st.control(rng))
    return [s.case(seed+997*i,p,k) for i,(p,k) in enumerate(zip(targets,KINDS))]
def memory():
    library,training,provenance=f.acquire()
    novel,origins,_=gen.propose(library,a.templates(library))
    return library,novel,sum(r["search"]["candidates"] for r in training)
def run(library,novel):
    rows=[]
    for seed in DEV:
        for i,c in enumerate(cases(seed)):
            for mode in ("weighted","generalized"):
                r=ins.search(c["fit"],mode,library,novel,())
                a=assess(c,r)
                rows.append(dict(seed=seed,task=i,kind=c["kind"],mode=mode,case=c,search=r,
                    no_candidate=int(r["program"] is None),**a))
    return rows
def summarize(rows,modes):
    return [dict(mode=m,**s.aggregate(rs),no_candidate=sum(r.get("no_candidate",0) for r in rs),
        emitted_incorrect=sum(r["emitted"] and not r["solved"] for r in rs))
        for m in modes for rs in ([r for r in rows if r["mode"]==m],)]
