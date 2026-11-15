"""Observable features of finite arithmetic tasks; no access to evaluation labels."""
import random,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V97"))
import weighted as w
s=w.syn
SEEDS=tuple(62000019+30001*i for i in range(16))
KINDS=("primitive","control_first","control_last","mixed")
def primitive(rng,n):return s.seq(*(rng.choice(s.OPS) for _ in range(n)))
def control(rng):return rng.choice(w.atoms(True)[6:])
def targets(seed):
    rng=random.Random(seed^0x10300)
    return (primitive(rng,rng.randrange(3,6)),control(rng)+primitive(rng,2),
            primitive(rng,2)+control(rng),control(rng)+primitive(rng,1)+control(rng))
def cases(seed):
    return [s.case(seed+997*j,p,k) for j,(p,k) in enumerate(zip(targets(seed),KINDS))]
def features(fit,library):
    ordered=sorted(fit);ys=[y for x,y in ordered]
    diffs=[b-a for a,b in zip(ys,ys[1:])]
    baseline=statistics.median(abs(x-y) for x,y in fit)
    improvement=[baseline-statistics.median(abs(s.execute(p,x)-y) for x,y in fit) for p in library]
    return dict(monotonic=all(d>=0 for d in diffs) or all(d<=0 for d in diffs),
        distinct=len(set(ys)),sign_change=min(ys)<0<max(ys),parity_match=sum(x%2==y%2 for x,y in fit),
        median_improvement=improvement)
def describe(library):
    rows=[dict(seed=seed,kind=c["kind"],fit=c["fit"],features=features(c["fit"],library))
          for seed in SEEDS for c in cases(seed)]
    summary=[]
    for k in KINDS:
        fs=[r["features"] for r in rows if r["kind"]==k]
        summary.append(dict(kind=k,tasks=len(fs),monotonic=sum(f["monotonic"] for f in fs),
            mean_distinct=statistics.mean(f["distinct"] for f in fs),
            sign_change=sum(f["sign_change"] for f in fs),mean_parity_match=statistics.mean(f["parity_match"] for f in fs),
            mean_best_improvement=statistics.mean(max(f["median_improvement"],default=0) for f in fs)))
    return rows,summary
