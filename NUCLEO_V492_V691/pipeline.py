"""Hierarchical typed synthesis over scalar routines + structural list tools."""
import sys
from pathlib import Path
from collections import deque,Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V331_V491"))
from skills import OPS,primitive,Oracle
STRUCT=("same","reverse","sort","unique","nonnegative")
RED=("identity","sum","min","max","count")
CAP=960
def structure(xs,op):
    if op=="same":return tuple(xs)
    if op=="reverse":return tuple(reversed(xs))
    if op=="sort":return tuple(sorted(xs))
    if op=="unique":return tuple(dict.fromkeys(xs))
    if op=="nonnegative":return tuple(v for v in xs if v>=0)
    raise ValueError("structure")
def check(program):
    seq,op,stage,red=program
    if not 1<=len(seq)<=5 or any(x not in OPS for x in seq) or op not in STRUCT or stage not in ("pre","post") or red not in RED:raise ValueError("program")
def execute(program,x):
    check(program)
    if type(x) not in (tuple,list) or not 1<=len(x)<=32 or any(type(v) is not int or abs(v)>10000 for v in x):raise ValueError("input")
    seq,op,stage,red=program
    def scalar(v):
        for o in seq:v=primitive(o,v)
        return v
    xs=structure(x,op) if stage=="pre" else tuple(x)
    ys=tuple(scalar(v) for v in xs)
    if stage=="post":ys=structure(ys,op)
    if red=="identity":return ys
    if red=="sum":return sum(ys)
    if red=="count":return len(ys)
    if red=="min":return min(ys) if ys else None
    if red=="max":return max(ys) if ys else None
def programs(macros,reds):
    tokens=tuple(dict.fromkeys(tuple(tuple(m) for m in macros)+tuple((o,) for o in OPS)))
    if len(macros)>12 or any(not 2<=len(m)<=3 or any(x not in OPS for x in m) for m in macros):raise ValueError("library")
    q=deque([()]);seen={()}
    # Each token-level sequence is evaluated with a complete fixed set of structural contexts.
    while q:
        prefix=q.popleft()
        for tok in tokens:
            s=prefix+tok
            if len(s)>5 or s in seen:continue
            seen.add(s)
            for op in STRUCT:
                for stage in (("pre",) if op=="same" else ("pre","post")):
                    for red in reds:yield (s,op,stage,red)
            if len(s)<5:q.append(s)
def solve(fit,oracle,lib=(),control=(),mode="base"):
    if mode not in ("base","random","learned","alternating"):raise ValueError("policy")
    kinds={type(y) for x,y in fit}
    reds=("identity",) if kinds=={tuple} else ("sum","min","max","count") if kinds<={int,type(None)} else ()
    if not reds:raise ValueError("output type")
    streams=[programs((),reds),programs(control if mode=="random" else lib,reds)]
    seen=set();matches=[];duplicates=0
    while len(seen)<CAP:
        i=0 if mode=="base" else len(seen)%2 if mode=="alternating" else 1
        try:p=next(streams[i])
        except StopIteration:break
        if p in seen:duplicates+=1;continue
        seen.add(p)
        if all(execute(p,x)==y for x,y in fit):matches.append(p)
    remaining=list(oracle.pool);trace=[]
    while matches and remaining and len(trace)<oracle.limit:
        def score(x):
            hist=Counter(execute(p,x) for p in matches);return len(matches)**2-sum(n*n for n in hist.values())
        x=max(remaining,key=score);remaining.remove(x);y=oracle.ask(x);n=len(matches)
        matches=[p for p in matches if execute(p,x)==y]
        trace.append(dict(input=x,output=y,before=n,after=len(matches)))
    p=min(matches,key=lambda p:(len(p[0])+(p[1]!="same"),p)) if matches else None
    return dict(program=p,candidates=len(seen),duplicates=duplicates,remaining=len(matches),queries=trace)
def export(program):
    check(program);seq,op,stage,red=program
    scalar={"inc":"x + 1","dec":"x - 1","double":"2 * x","neg":"-x","abs":"abs(x)","half":"x // 2","mod3":"x % 3"}
    structs={"same":"tuple(xs)","reverse":"tuple(reversed(xs))","sort":"tuple(sorted(xs))","unique":"tuple(dict.fromkeys(xs))","nonnegative":"tuple(v for v in xs if v >= 0)"}
    reductions={"identity":"tuple(xs)","sum":"sum(xs)","count":"len(xs)","min":"min(xs) if xs else None","max":"max(xs) if xs else None"}
    out="def scalar(x):\n"+"".join("    x = "+scalar[o]+"\n" for o in seq)+"    return x\n\ndef structure(xs):\n    return "+structs[op]+"\n\ndef reduce(xs):\n    return "+reductions[red]+"\n\ndef solve(data):\n"
    out+="    xs = structure(data)\n    ys = tuple(scalar(x) for x in xs)\n" if stage=="pre" else "    xs = tuple(scalar(x) for x in data)\n    ys = structure(xs)\n"
    return out+"    return reduce(ys)\n"
