"""Finite typed DSL. No eval, shell, network, or executable text input."""
from collections import Counter, deque
from itertools import product
import random

OPS=("inc","dec","double","neg","abs","half","mod3")
RED=("identity","sum","min","max")
CAP=480
MAX_LEN=5
def primitive(o,x):
    if o=="inc":return x+1
    if o=="dec":return x-1
    if o=="double":return 2*x
    if o=="neg":return -x
    if o=="abs":return abs(x)
    if o=="half":return x//2
    if o=="mod3":return x%3
    raise ValueError("operation")
def transform(seq,x):
    for o in seq:x=primitive(o,x)
    return x
def execute(program,x):
    seq,red=program
    if not 1<=len(seq)<=MAX_LEN or any(o not in OPS for o in seq):raise ValueError("program")
    if red=="scalar":
        if type(x) is not int or abs(x)>10000:raise ValueError("input")
        return transform(seq,x)
    if not isinstance(x,(tuple,list)) or not 1<=len(x)<=32 or any(type(v) is not int or abs(v)>10000 for v in x):raise ValueError("input")
    y=tuple(transform(seq,v) for v in x)
    if red=="identity":return y
    if red=="sum":return sum(y)
    if red=="min":return min(y)
    if red=="max":return max(y)
    raise ValueError("reduction")
def enumerate_programs(macros=(),kind="vector",cap=CAP):
    if not 1<=cap<=CAP or kind not in ("vector","scalar"):raise ValueError("budget")
    if len(macros)>12 or any(not 2<=len(m)<=3 or any(o not in OPS for o in m) for m in macros):raise ValueError("macro")
    tokens=tuple(dict.fromkeys(tuple(tuple(m) for m in macros)+tuple((o,) for o in OPS)))
    queue=deque([()]);seen={()};cost=0
    while queue:
        prefix=queue.popleft()
        for tok in tokens:
            s=prefix+tok
            if len(s)>MAX_LEN or s in seen:continue
            seen.add(s)
            for red in (RED if kind=="vector" else ("scalar",)):
                if cost>=cap:return
                cost+=1;yield (s,red)
            if len(s)<MAX_LEN:queue.append(s)
class Oracle:
    """Only query pool outputs; external held-out rows are not accessible."""
    def __init__(self,rows,limit=3):
        self._rows=dict(rows);self.pool=tuple(self._rows);self.limit=limit;self.queries=[]
    def ask(self,x):
        if x not in self._rows or x in self.queries or len(self.queries)>=self.limit:raise ValueError("query")
        self.queries.append(x);return self._rows[x]
def synthesize(fit,oracle,macros=(),active=False,kind="vector",cap=CAP):
    candidates=[];cost=0
    for p in enumerate_programs(macros,kind,cap):
        cost+=1
        if all(execute(p,x)==y for x,y in fit):candidates.append(p)
    trace=[]
    remaining=list(oracle.pool)
    while candidates and remaining and len(trace)<oracle.limit:
        if active:
            def disagreement(x):
                n=len(candidates);hist=Counter(execute(p,x) for p in candidates)
                return n*n-sum(v*v for v in hist.values())
            x=max(remaining,key=disagreement)
        else:x=remaining[0]
        remaining.remove(x);y=oracle.ask(x);before=len(candidates)
        candidates=[p for p in candidates if execute(p,x)==y]
        trace.append(dict(input=x,output=y,before=before,after=len(candidates)))
    # Ranking only among observed-compatible hypotheses, prefer simpler expanded program.
    p=min(candidates,key=lambda p:(len(p[0]),p)) if candidates else None
    return dict(program=p,candidates=cost,remaining=len(candidates),queries=trace)
def random_macros(macros,seed):
    r=random.Random(seed);out=[]
    for m in macros:
        while True:
            q=tuple(r.choice(OPS) for _ in m)
            if q not in out and q not in macros:out.append(q);break
    return tuple(out)
def export_python(program):
    seq,red=program
    # Validate operations using the interpreter; emit only fixed templates.
    execute(program,0 if red=="scalar" else (0,))
    lines={"inc":"x + 1","dec":"x - 1","double":"x * 2","neg":"-x","abs":"abs(x)","half":"x // 2","mod3":"x % 3"}
    src="def transform(x):\n"
    for o in seq:src+="    x = "+lines[o]+"\n"
    src+="    return x\n\ndef solve(data):\n"
    if red=="scalar":return src+"    return transform(data)\n"
    src+="    result = tuple(transform(x) for x in data)\n"
    return src+"    return "+("result" if red=="identity" else red+"(result)")+"\n"
