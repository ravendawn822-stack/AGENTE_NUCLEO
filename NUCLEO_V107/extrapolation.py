"""New program arrangements and shifted input distribution, same finite DSL."""
import sys
from pathlib import Path
for v in (103,106):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import structure as st
import instances as ins
s=st.s
SEEDS=tuple(66000019+30001*i for i in range(24))
OUTSIDE=tuple(range(-14,-8))+tuple(range(9,15))
def outside(case):return [(x,s.execute(case["target"],x)) for x in OUTSIDE]
def run(library,novel,control):
    rows=ins.batch(SEEDS,st.cases,library,novel,control)
    for r in rows:r["extrapolation"]=s.score(r["program"],outside(r["case"]))
    return rows
def aggregate(rows,modes=ins.MODES):
    return [dict(mode=m,**{k:sum(r["extrapolation"][k] for r in rows if r["mode"]==m)
        for k in ("correct","wrong","abstained","solved")}) for m in modes]
