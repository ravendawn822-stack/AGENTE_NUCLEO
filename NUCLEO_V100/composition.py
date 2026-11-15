"""Frozen library comparison, with a matched nonredundant control."""
import random,sys
from pathlib import Path
for v in (94,95,97,98,99):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import weighted as w
import fragments as f
import abstractions as a
import program_memory as old
from audit import assess
syn=w.syn
SEEDS=tuple(56000019+30001*i for i in range(24))
MODES=("primitive","structured","weighted","learned","random")
def control_library(library):
    rng=random.Random(100001);result=[]
    seen={f.signature(()),*(f.signature(x) for x in w.atoms(False))}
    singles={op:tuple(atom[0] for atom in w.atoms(True) if atom[0][0]==op) for op in ("if","repeat")}
    primitives=tuple(atom[0] for atom in w.atoms(False))
    for p in library:
        for _ in range(2000):
            q=tuple(rng.choice(singles.get(i[0],primitives)) for i in p)
            try:s=f.signature(q)
            except w.Invalid:continue
            if s not in seen:seen.add(s);result.append(q);break
        else:raise RuntimeError("matched control not found")
    return tuple(result)
def search(fit,mode,library,control,cap=syn.CAP):
    if mode=="primitive":return syn.search(fit,False,cap=cap)
    if mode=="structured":return syn.search(fit,True,cap=cap)
    if mode not in MODES:raise ValueError("mode")
    return w.search(fit,library if mode=="learned" else control if mode=="random" else (),cap)
def batch(seeds,cases,library,control,modes=MODES):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(cases(seed)):
            for mode in modes:
                r=search(c["fit"],mode,library,control)
                rows.append(dict(seed=seed,task=i,mode=mode,kind=c["kind"],case=c,search=r,**assess(c,r)))
    return rows
def aggregate(rows,modes=MODES):
    return [dict(mode=m,**syn.aggregate([r for r in rows if r["mode"]==m])) for m in modes]
