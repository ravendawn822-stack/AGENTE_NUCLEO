"""Frozen empirical strategy policy; no test outcomes enter decisions."""
import hashlib,json,sys
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V127"))
from context import context,KEYS
TRAIN=tuple(94000019+30001*i for i in range(24))
MODES=("pool_active","pool_consensus","split_random2","expand_active","switch","crosscheck")
def train(rows):
    counts={k:{m:[0,0,0] for m in MODES} for k in ("global",)+KEYS}
    for row in rows:
        for k in ("global",row["context"]):
            v=counts[k][row["mode"]];v[0]+=1;v[1]+=row["utility"];v[2]+=row["candidates"]
    return counts
def global_score(counts,m):
    n,u,c=counts["global"][m]
    return Fraction(u,n) if n else Fraction(0)
def pick(counts,fit=None):
    k=context(fit) if fit is not None else "global"
    def score(m):
        n,u,c=counts[k][m];g=global_score(counts,m)
        return g if fit is None else (u+8*g)/(n+8)
    def cost(m):
        n,u,c=counts["global"][m];return Fraction(c,max(n,1))
    return min(MODES,key=lambda m:(-score(m),cost(m),MODES.index(m)))
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(path,counts):
    p=dict(schema=1,counts=counts)
    with path.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    outer=json.loads(raw);p=outer["payload"]
    if p["schema"]!=1 or outer["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    c=p["counts"]
    if set(c)!={"global",*KEYS}:raise ValueError("contexts")
    for table in c.values():
        if set(table)!=set(MODES):raise ValueError("modes")
        for v in table.values():
            if type(v) is not list or len(v)!=3 or any(type(n) is not int for n in v):raise ValueError("counts")
            n,u,cost=v
            if not 0<=n<=100000 or not -40*n<=u<=10*n or not 0<=cost<=1200*n:raise ValueError("range")
    for m in MODES:
        if c["global"][m]!=[sum(c[k][m][i] for k in KEYS) for i in range(3)]:raise ValueError("totals")
    return c
