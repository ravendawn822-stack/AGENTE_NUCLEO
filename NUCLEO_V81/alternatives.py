"""Allowlisted, hand-specified scheduling alternatives. No generated code."""
import sys
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V79"))
from instrumentation import closure,baseline,write

def signals(ready,goals,graph,models,failed,blocked):
    viable=[]
    unavailable=set(failed)|set(blocked)
    for g in goals:
        remaining=set(closure(graph,[g]))-models.keys()
        if remaining and not remaining&unavailable:viable.append(remaining)
    result={}
    for i in ready:
        hits=[len(r) for r in viable if i in r]
        result[i]=(len(hits),min(hits) if hits else len(graph)+1)
    return result

def near(ready,required,goals,graph,models,failed,blocked):
    s=signals(ready,goals,graph,models,failed,blocked)
    return min(ready,key=lambda i:(s[i][1],i))
def shared(ready,required,goals,graph,models,failed,blocked):
    s=signals(ready,goals,graph,models,failed,blocked)
    return min(ready,key=lambda i:(-s[i][0],i))
def ratio(ready,required,goals,graph,models,failed,blocked):
    s=signals(ready,goals,graph,models,failed,blocked)
    return min(ready,key=lambda i:(-Fraction(s[i][0],s[i][1]),i))
POLICIES={"baseline":baseline,"near":near,"shared":shared,"ratio":ratio}

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    result=dict(protocol="V81-allowlisted-alternatives-v1",policies=sorted(POLICIES),
        alternatives=["near","shared","ratio"],generated_code=False)
    write(out/"summary.json",result)
    return result
