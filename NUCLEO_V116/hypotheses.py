"""Bounded version-space sample in an inert integer DSL."""
import itertools,sys
from pathlib import Path
for v in (110,115):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from ambiguity import s,DOMAIN
from partition import predicate,PREDS
from language import validate,Invalid
MAX_POOL=64
def build(fit,cap=s.CAP):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    if not fit or len(dict(fit))!=len(fit) or any(x not in DOMAIN for x,y in fit):raise ValueError("fit")
    checked=0;evaluations=0;pool=[];seen=set();primitives=[]
    def accept(p,v,kind):
        if v not in seen and all(v[x-DOMAIN[0]]==y for x,y in fit):
            validate(p);seen.add(v);pool.append(dict(program=p,values=v,kind=kind))
    for size in range(4):
        for ops in itertools.product(s.OPS,repeat=size):
            if checked>=cap or len(pool)>=MAX_POOL:break
            p=s.seq(*ops);checked+=1;evaluations+=len(DOMAIN)
            v=tuple(s.execute(p,x) for x in DOMAIN)
            primitives.append((p,v));accept(p,v,"sequence")
        if checked>=cap or len(pool)>=MAX_POOL:break
    def branches(pred,side):
        pts=[(x,y) for x,y in fit if predicate(pred,x)==side]
        if len(pts)<2:return []
        positions=[x-DOMAIN[0] for x in DOMAIN if predicate(pred,x)==side]
        found=[];seen=set()
        for p,v in primitives:
            if not all(v[x-DOMAIN[0]]==y for x,y in pts):continue
            sig=tuple(v[j] for j in positions)
            if sig in seen:continue
            found.append((p,v));seen.add(sig)
            if len(found)==12:break
        return found
    lists=[]
    for pred in PREDS:
        pairs=list(itertools.product(branches(pred,True),branches(pred,False)))
        pairs.sort(key=lambda pair:len(pair[0][0])+len(pair[1][0]))
        lists.append(iter([(pred,a,b) for a,b in pairs]))
    assembled=0
    while lists and checked<cap and len(pool)<MAX_POOL:
        remaining=[]
        for it in lists:
            if checked>=cap or len(pool)>=MAX_POOL:break
            item=next(it,None)
            if item is None:continue
            remaining.append(it);pred,(a,av),(b,bv)=item
            checked+=1;assembled+=1
            p=(("if",pred,a,b),)
            v=tuple(av[j] if predicate(pred,x) else bv[j] for j,x in enumerate(DOMAIN))
            accept(p,v,pred)
        lists=remaining
    return dict(pool=pool,candidates=checked,interpreter_evaluations=evaluations,assembled=assembled)
