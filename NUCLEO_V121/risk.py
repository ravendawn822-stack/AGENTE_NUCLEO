"""Empirical task-level reliability, fitted only on training cases."""
import hashlib,json
from fractions import Fraction
TRAIN=tuple(88000019+30001*i for i in range(24))
KEYS=("global",)+tuple(f"{k}:{e}" for k in ("one","few","many") for e in ("initial","expanded"))
def key(result):
    n=result["remaining_pool"]
    return ("one" if n==1 else "few" if n<4 else "many")+":"+("expanded" if result["expanded"] else "initial")
def train(rows):
    counts={k:[0,0] for k in KEYS}
    for row in rows:
        if row["emitted"]:
            for k in ("global",key(row["search"])):counts[k][int(not row["solved"])]+=1
    return counts
def estimate(counts,result):
    if result["program"] is None:return None
    right,wrong=counts[key(result)]
    if right+wrong<5:right,wrong=counts["global"]
    return Fraction(right+1,right+wrong+2)
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(path,counts):
    p=dict(schema=1,counts=counts)
    with path.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    e=json.loads(raw);p=e["payload"]
    if p["schema"]!=1 or e["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    c=p["counts"]
    if set(c)!=set(KEYS) or any(type(v) is not list or len(v)!=2 or any(type(n) is not int or not 0<=n<=10000000 for n in v) for v in c.values()):raise ValueError("counts")
    if any(c["global"][i]!=sum(c[k][i] for k in KEYS if k!="global") for i in (0,1)):raise ValueError("totals")
    return c
def calibrate(rows,counts):
    pairs=[(float(estimate(counts,r["search"])),r["solved"]) for r in rows if r["emitted"]]
    n=len(pairs)
    return dict(emitted=n,brier=sum((p-y)**2 for p,y in pairs)/n if n else None,
        mean_estimate=sum(p for p,y in pairs)/n if n else None,
        actual=sum(y for p,y in pairs)/n if n else None)
