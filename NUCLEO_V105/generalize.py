"""Propose new finite DSL instances, never host-language code."""
import random,sys
from pathlib import Path
for v in (98,99,103):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import fragments as f
import abstractions as a
from structure import w,s
from language import validate,Invalid
def initial_signatures(library):
    return {f.signature(()),*(f.signature(x) for x in w.atoms(False)),*(f.signature(x) for x in library)}
def propose(library,templates):
    seen=initial_signatures(library);new=[];origins=[];skipped=0
    for i,t in enumerate(templates):
        for op in s.OPS:
            if op in t["values"]:continue
            p=validate(tuple((x if x is not None else op,) for x in t["pattern"]))
            sig=f.signature(p)
            if sig in seen:skipped+=1;continue
            seen.add(sig);new.append(p);origins.append(dict(template=i,parameter=op,program=p))
            if len(new)==8:return tuple(new),origins,skipped
    return tuple(new),origins,skipped
def control(library,novel):
    rng=random.Random(105001);seen=initial_signatures(library);out=[]
    for p in novel:
        for _ in range(2000):
            q=s.seq(*(rng.choice(s.OPS) for _ in p))
            sig=f.signature(q)
            if sig not in seen:seen.add(sig);out.append(q);break
        else:raise RuntimeError("matched control unavailable")
    return tuple(out)
