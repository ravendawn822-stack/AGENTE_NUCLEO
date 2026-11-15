"""Finite BFS over program compositions, signatures use fit examples only."""
import random,sys
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V92"))
from interpreter import execute
from language import atoms,validate,Invalid,OPS
DOMAIN=tuple(range(-8,9))
SEEDS=tuple(44000019+30001*i for i in range(16))
CAP=1200
DEPTH=4
def seq(*ops):return tuple((o,) for o in ops)
def branch(pred,a,b):return (("if",pred,seq(a),seq(b)),)
def repeat(n,op):return (("repeat",n,seq(op)),)
def case(seed,target,kind,corrupt=False):
    rng=random.Random(seed)
    values={x:execute(target,x) for x in DOMAIN}
    if corrupt:
        for x in rng.sample(DOMAIN,3):values[x]+=rng.choice((-2,-1,1,2))
    xs=list(DOMAIN);rng.shuffle(xs)
    rows=[(x,values[x]) for x in xs]
    return dict(kind=kind,target=target,fit=rows[:6],audit=rows[6:10],held=rows[10:])
def cases(seed):
    targets=(("primitive",seq("inc","double","neg")),("primitive",seq("neg","half","inc")),
        ("condition",branch("even","double","half")),("condition",branch("negative","neg","inc")),
        ("repeat",repeat(3,"inc")),("outside",seq("double","inc")))
    return [case(seed+997*j,p,k,k=="outside") for j,(k,p) in enumerate(targets)]
def search(fit,structured=True,macros=(),cap=CAP):
    if type(cap) is not int or not 0<=cap<=CAP:raise ValueError("cap")
    if not fit or len({x for x,t in fit})!=len(fit):raise ValueError("fit")
    primitives=atoms(False);controls=atoms(True)[len(primitives):] if structured else ()
    vocab=tuple(dict.fromkeys(primitives+tuple(validate(p) for p in macros)+controls))
    xs=tuple(x for x,t in fit);target=tuple(t for x,t in fit)
    q=deque([((),xs,0)]);seen={xs};cache={};checked=0;pruned=0
    if cap:
        checked=1
        if xs==target:return dict(program=(),candidates=checked,pruned=pruned)
    while q and checked<cap:
        p,signature,depth=q.popleft()
        if depth>=DEPTH:continue
        for atom in vocab:
            if checked>=cap:break
            checked+=1;program=p+atom
            try:
                validate(program)
                vals=[]
                for x in signature:
                    key=(atom,x)
                    if key not in cache:cache[key]=execute(atom,x)
                    vals.append(cache[key])
                value=tuple(vals)
            except Invalid:continue
            if value==target:return dict(program=program,candidates=checked,pruned=pruned)
            if value in seen:pruned+=1;continue
            seen.add(value);q.append((program,value,depth+1))
    return dict(program=None,candidates=checked,pruned=pruned)
def matches(program,rows):
    if program is None:return False
    try:return all(execute(program,x)==t for x,t in rows)
    except Invalid:return False
def score(program,rows):
    correct=wrong=abstained=0
    for x,t in rows:
        if program is None:abstained+=1;continue
        try:y=execute(program,x)
        except Invalid:abstained+=1;continue
        if y==t:correct+=1
        else:wrong+=1
    return dict(correct=correct,wrong=wrong,abstained=abstained,solved=int(correct==len(rows)))
def aggregate(rows):
    keys=("correct","wrong","abstained","solved","candidates","emitted","rejected")
    return dict(tasks=len(rows),**{k:sum(r.get(k,0) for r in rows) for k in keys})
