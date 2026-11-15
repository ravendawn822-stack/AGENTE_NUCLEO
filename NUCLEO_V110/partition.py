"""Partition observed pairs by predicates already in the finite DSL."""
PREDS=("even","negative")
def predicate(p,x):
    if p=="even":return x%2==0
    if p=="negative":return x<0
    raise ValueError("predicate")
def options(rows):
    result=[]
    for i,p in enumerate(PREDS):
        yes=tuple((x,y) for x,y in rows if predicate(p,x))
        no=tuple((x,y) for x,y in rows if not predicate(p,x))
        if min(len(yes),len(no))>=2:result.append(dict(predicate=p,yes=yes,no=no,index=i))
    return sorted(result,key=lambda p:(-min(len(p["yes"]),len(p["no"])),p["index"]))
