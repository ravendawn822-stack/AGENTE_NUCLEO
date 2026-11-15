"""Bounded cost-stratified search for an inert arithmetic DSL."""
import heapq,itertools,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V93"))
import synthesis as syn
from language import atoms,validate,Invalid
SEEDS=tuple(52000019+30001*i for i in range(16))
def nodes(p):
    return sum(1+(nodes(i[2])+nodes(i[3]) if i[0]=="if" else nodes(i[2]) if i[0]=="repeat" else 0) for i in p)
def search(fit,macros=(),cap=syn.CAP):
    if type(cap) is not int or not 0<=cap<=syn.CAP:raise ValueError("cap")
    if not fit or len({x for x,t in fit})!=len(fit):raise ValueError("fit")
    vocab={}
    for a in atoms(False):vocab[a]=1
    for p in macros:
        a=validate(p)
        if a:vocab.setdefault(a,max(1,nodes(a)-1))
    for a in atoms(True)[6:]:vocab.setdefault(a,3)
    xs=tuple(x for x,t in fit);target=tuple(t for x,t in fit)
    # Queue individual extensions, not whole batches of successors, so expensive
    # control atoms do not consume the budget before cheaper compositions.
    q=[];counter=itertools.count();seen={(xs,0):0};cache={};checked=0;pruned=0
    def extend(p,signature,depth,cost):
        if depth<syn.DEPTH:
            for a,w in vocab.items():
                heapq.heappush(q,(cost+w,next(counter),p,signature,depth+1,a))
    if cap:
        checked=1
        if xs==target:return dict(program=(),candidates=1,pruned=0,cost=0)
        extend((),xs,0,0)
    while q and checked<cap:
        cost,_,p,signature,depth,a=heapq.heappop(q);checked+=1
        program=p+a
        try:
            validate(program);v=[]
            for x in signature:
                key=(a,x)
                if key not in cache:cache[key]=syn.execute(a,x)
                v.append(cache[key])
            value=tuple(v)
        except Invalid:continue
        if value==target:return dict(program=program,candidates=checked,pruned=pruned,cost=cost)
        key=(value,depth)
        if key in seen and seen[key]<=cost:pruned+=1;continue
        seen[key]=cost;extend(program,value,depth,cost)
    return dict(program=None,candidates=checked,pruned=pruned,cost=None)
