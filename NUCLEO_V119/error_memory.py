"""Frozen empirical observation-error memory, learned only on training queries."""
import hashlib,json,sys
from fractions import Fraction
from pathlib import Path
for v in (97,115,116,117,118):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import weighted as w
import ambiguity as amb
import hypotheses as hyp
import information as info
import observations as obs
TRAIN=tuple(82000019+30001*i for i in range(24))
TEST=tuple(84000019+30001*i for i in range(24))
MODES=obs.MODES+("pool_memory",)
KEYS=("global",)+tuple(f"{k}:{n}" for k in ("sequence","even","negative") for n in ("small","medium","large"))
def key(h):
    n=w.nodes(h["program"])
    return h["kind"]+":"+("small" if n<=2 else "medium" if n<=4 else "large")
def train():
    counts={k:[0,0] for k in KEYS};records=[];cost=0
    for seed in TRAIN:
        for i,c in enumerate(amb.lab.cases(seed)):
            r=hyp.build(c["fit"]);cost+=r["candidates"]
            oracle=amb.Oracle(c["audit"],4)
            known=[(x,oracle.observe(x)) for x in oracle.available()]
            errors=0
            for h in r["pool"]:
                for x,y in known:
                    correct=info.predict(h,x)==y;errors+=not correct
                    for k in ("global",key(h)):counts[k][int(not correct)]+=1
            records.append(dict(seed=seed,task=i,fit=c["fit"],observations=known,pool=len(r["pool"]),
                errors=errors,candidates=r["candidates"]))
    return counts,records,cost
def ranker(counts):
    def rank(h):
        right,wrong=counts[key(h)]
        if right+wrong==0:right,wrong=counts["global"]
        return Fraction(right+1,right+wrong+2)
    return rank
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def save(path,counts):
    p=dict(schema=1,counts=counts)
    with path.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    e=json.loads(raw);p=e["payload"]
    if p["schema"]!=1 or e["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    counts=p["counts"]
    if set(counts)!=set(KEYS) or any(type(v) is not list or len(v)!=2 or any(type(n) is not int or not 0<=n<=10000000 for n in v) for v in counts.values()):raise ValueError("counts")
    if any(counts["global"][i]!=sum(counts[k][i] for k in KEYS if k!="global") for i in (0,1)):raise ValueError("totals")
    return counts
