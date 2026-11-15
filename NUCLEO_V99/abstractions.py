"""Finite observed parameter domains; serialized data never executes host code."""
import hashlib,json,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V98"))
from fragments import signature
from language import OPS,validate
def templates(library):
    groups=defaultdict(set)
    for p in library:
        if not all(len(i)==1 and i[0] in OPS for i in p):continue
        for j in range(len(p)):
            key=tuple(None if k==j else i[0] for k,i in enumerate(p))
            groups[key].add(p[j][0])
    result=[]
    for pattern,values in sorted(groups.items(),key=lambda kv:(-len(kv[1]),repr(kv[0]))):
        if len(values)>=2:
            result.append(dict(pattern=pattern,values=tuple(sorted(values))))
        if len(result)==4:break
    return result
def members(t):
    p=t["pattern"];v=t["values"]
    if not 2<=len(p)<=3 or p.count(None)!=1 or any(x is not None and x not in OPS for x in p):raise ValueError("pattern")
    if not 2<=len(v)<=len(OPS) or any(x not in OPS for x in v) or len(set(v))!=len(v):raise ValueError("values")
    return tuple(validate(tuple((x if x is not None else op,) for x in p)) for op in v)
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(path,library,ts):
    p=dict(schema=1,library=library,templates=ts)
    with path.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    e=json.loads(raw);p=e["payload"]
    if p["schema"]!=1 or e["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    if len(p["library"])>8 or len(p["templates"])>4:raise ValueError("size")
    library=tuple(validate(x) for x in p["library"])
    if any(not 2<=len(x)<=3 for x in library) or len({signature(x) for x in library})!=len(library):raise ValueError("library")
    ts=[dict(pattern=tuple(t["pattern"]),values=tuple(t["values"])) for t in p["templates"]]
    if any(not set(members(t))<=set(library) for t in ts):raise ValueError("unobserved member")
    return library,ts
