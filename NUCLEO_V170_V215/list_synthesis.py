"""V180–183: bounded synthesis, separate oracle/evaluator and audit-driven repair."""
import random,time,itertools
from collections import deque
import vm
LIB=tuple(110000019+30001*i for i in range(16))
TRAIN=tuple(112000019+30001*i for i in range(16))
VAL=tuple(114000019+30001*i for i in range(16))
TEST=tuple(116000019+30001*i for i in range(24))
OPS=tuple(118000019+30001*i for i in range(16))
CSV=tuple(120000019+30001*i for i in range(24))
MODES=("single","direct","learned","retry")
CAP=600
# External reference uses ordinary Python transforms, not VM output.
def reference(seq,x):
    v=tuple(x)
    for name in seq:
        if type(v) is not tuple:raise ValueError("type")
        if name=="double":v=tuple(2*i for i in v)
        elif name=="inc":v=tuple(i+1 for i in v)
        elif name=="reverse":v=v[::-1]
        elif name=="sort":v=tuple(sorted(v))
        elif name=="nonnegative":v=tuple(i for i in v if i>=0)
        elif name=="nonzero":v=tuple(i for i in v if i)
        elif name=="unique":v=tuple(dict.fromkeys(v))
        elif name=="sum":v=sum(v)
        elif name=="count":v=len(v)
        else:raise ValueError("atom")
    return v
MOTIFS=(("nonnegative","sort"),("unique","nonzero","sum"),("double","inc","reverse"),("nonzero","unique","count"),
        ("nonnegative","unique","sum"),("inc","nonnegative","reverse"),("unique","double","sort"),("reverse","nonzero","count"))
def cases(seed,library=False):
    rng=random.Random(seed)
    motifs=MOTIFS[:4] if library else MOTIFS
    chosen=[motifs[(seed//30001+i)%len(motifs)] for i in range(4)]
    rows=[]
    for seq in chosen:
        xs=[tuple(rng.randrange(-5,6) for _ in range(rng.randrange(2,7))) for j in range(16)]
        examples=[(x,reference(seq,x)) for x in xs]
        rows.append(dict(fit=examples[:5],audit=examples[5:8],held=examples[8:],target=seq))
    return rows
def norm(rows):
    return [(vm.value(x),vm.value(y)) for x,y in rows]
def matches(seq,rows):
    if seq is None:return False
    try:return all(vm.run_pipeline(seq,x)==y for x,y in norm(rows))
    except vm.Invalid:return False
def search(rows,cap=CAP,library=(),depth=3):
    if not 0<=cap<=CAP or depth not in (1,3):raise ValueError("search budget")
    known=norm(rows)
    xs=tuple(x for x,y in known);ys=tuple(y for x,y in known)
    atoms=[tuple(a) for a in library if 1<=len(a)<=depth]+[(a,) for a in vm.ATOMS]
    atoms=list(dict.fromkeys(atoms))
    q=deque([((),xs)]);seen={()};cache={};cost=0;evals=0
    while q and cost<cap:
        prefix,values=q.popleft()
        for fragment in atoms:
            seq=prefix+fragment
            if len(seq)>depth or seq in seen:continue
            if cost>=cap:break
            seen.add(seq);cost+=1
            vals=values
            try:
                for op in fragment:
                    result=[]
                    for v in vals:
                        k=(op,v)
                        if k not in cache:
                            evals+=1
                            try:cache[k]=vm.run_pipeline((op,),v)
                            except vm.Invalid:cache[k]=None
                        if cache[k] is None:raise vm.Invalid("candidate type")
                        result.append(cache[k])
                    vals=tuple(result)
                if vals==ys and matches(seq,known):
                    return dict(program=seq,candidates=cost,atom_evaluations=evals)
                if len(seq)<depth and all(type(v) is tuple for v in vals):q.append((seq,vals))
            except vm.Invalid:continue
    return dict(program=None,candidates=cost,atom_evaluations=evals)
def solve(fit,audit,mode="direct",library=()):
    if mode not in MODES:raise ValueError("mode")
    t=time.perf_counter_ns()
    first=search(fit,300 if mode=="retry" else CAP,library if mode=="learned" else (),1 if mode=="single" else 3)
    p=first["program"];cost=first["candidates"];ev=first["atom_evaluations"];repaired=False
    rejected=p is not None and not matches(p,audit)
    if rejected:
        p=None
        if mode=="retry" and cost<CAP:
            repaired=True
            second=search(list(fit)+list(audit),CAP-cost)
            cost+=second["candidates"];ev+=second["atom_evaluations"];p=second["program"]
    return dict(program=p,candidates=cost,atom_evaluations=ev,audit_rejected=int(rejected),retried=int(repaired),
        elapsed_ns=time.perf_counter_ns()-t)
def assess(c,r):
    p=r["program"];right=0;wrong=0;abst=0
    for x,y in norm(c["held"]):
        if p is None:abst+=1;continue
        try:out=vm.run_pipeline(p,x)
        except vm.Invalid:abst+=1;continue
        if out==y:right+=1
        else:wrong+=1
    success=right==len(c["held"]);incorrect=p is not None and not success
    return dict(solved=int(success),incorrect=int(incorrect),correct=right,wrong=wrong,abstained=abst,
        utility=10*success-40*incorrect)
def acquire():
    library=[];records=[]
    for seed in LIB:
        for c in cases(seed,True):
            r=solve(c["fit"],c["audit"],"retry");a=assess(c,r)
            if a["solved"] and r["program"] and len(r["program"])>=2 and r["program"] not in library and len(library)<8:
                library.append(r["program"])
            records.append(dict(seed=seed,case=c,search=r,**a))
    return tuple(library),records
def batch(seeds,modes,library):
    return [dict(seed=seed,task=i,mode=m,case=c,search=r,**assess(c,r)) for seed in seeds
        for i,c in enumerate(cases(seed)) for m in modes for r in [solve(c["fit"],c["audit"],m,library)]]
def aggregate(rows):
    result=[]
    for m in sorted({r["mode"] for r in rows}):
        rs=[r for r in rows if r["mode"]==m]
        result.append(dict(mode=m,tasks=len(rs),**{k:sum(r[k] for r in rs) for k in ("solved","incorrect","correct","wrong","abstained","utility")},
            **{k:sum(r["search"][k] for r in rs) for k in ("candidates","atom_evaluations","audit_rejected","retried","elapsed_ns")}))
    return result
