"""Gramática numérica; nenhuma solução de desafio embutida no agente."""
import hashlib,json,math
BASE=((10,-2),(10,-1),(10,0),(10,1),(10,2),(11,0))
def freeze(e): return tuple(freeze(x) if isinstance(x,(tuple,list)) else x for x in e)
def ident(e): return hashlib.sha256(json.dumps(e,separators=(',',':')).encode()).hexdigest()[:20]
def children(e): return e[1:] if e[0] in (1,2,3,20,21,30) else ()
def depth(e): return 1+max((depth(c) for c in children(e)),default=0)
def size(e): return 1+sum(size(c) for c in children(e))
def subtrees(e):
    yield e
    for c in children(e): yield from subtrees(c)
def value(e,x):
    op=e[0]
    if op==10:return e[1]
    if op==11:return x[e[1]] if isinstance(x,(tuple,list)) else x
    if op==12:return bool(e[1])
    if op==30:return value(e[2],x) if value(e[1],x) else value(e[3],x)
    a,b=value(e[1],x),value(e[2],x)
    if op==1:return a+b
    if op==2:return a-b
    if op==3:return a*b
    if op==20:return a<b
    if op==21:return a==b
    raise ValueError(op)
def text(e):
    if not e:return '—'
    if e[0]==10:return str(e[1])
    if e[0]==11:return 'xy'[e[1]]
    if e[0]==12:return str(bool(e[1]))
    if e[0]==30:return f'({text(e[2])} if {text(e[1])} else {text(e[3])})'
    return '('+text(e[1])+{1:'+',2:'−',3:'×',20:'<',21:'=='}[e[0]]+text(e[2])+')'
def features(ys):
    scale=1+max(abs(y) for y in ys)
    d=[ys[i+1]-ys[i] for i in range(len(ys)-1)]
    dd=[d[i+1]-d[i] for i in range(len(d)-1)]
    return [sum(d)/(len(d)*scale),sum(abs(v) for v in dd)/(len(dd)*2*scale),
            sum(abs(ys[i]-ys[-1-i]) for i in range(2))/(4*scale),
            sum(abs(ys[i]+ys[-1-i]) for i in range(2))/(4*scale),ys[2]/scale]
def relevance(a,b): return max(0.,min(1.,1-sum(abs(x-y) for x,y in zip(a,b))/10))
def context(ys): return ','.join(str(round(v*2)) for v in features(ys))
def score(skill,ys,weights,inputs=None):
    s=skill['contexts'].get(context(ys),{'attempts':0,'success':0})
    n=s['attempts']; p=(s['success']+1)/(n+2); exploration=1/math.sqrt(1+n)
    r=relevance(features([value(skill['expr'],x) for x in (inputs if inputs is not None else range(-2,3))]),features(ys))
    # Custo de operações normalizado; tempo real é uma medida separada.
    k=.5*min(1,size(skill['expr'])/15)+.5*(min(1,skill['cost_ops']/75) if skill['cost_count'] else .5)
    return dict(P=p,R=r,E=exploration,K=k,S=(weights[0]*p+weights[1]*r+weights[2]*exploration)/(1+k))
def candidates(selected,expanded=False):
    base=list(BASE)+([(11,1)] if expanded else [])
    current=[]; seen=set()
    for e,used in [(e,()) for e in base]+[(s['expr'],(s['id'],)) for s in selected]:
        if e not in seen: seen.add(e); current.append((e,used)); yield e,used
    for level in range(3):
        new=[]
        for a,ua in current:
            for b,ub in current:
                if max(depth(a),depth(b))>=4:continue
                for op in (1,2,3):
                    e=(op,a,b)
                    if e not in seen:
                        seen.add(e); u=tuple(sorted(set(ua+ub)));new.append((e,u));yield e,u
        current+=new

def program_candidates(selected):
    # Busca tipada limitada: monta condições e ramos a partir de primitivas e
    # expressões aritméticas enumeradas. Nenhum template de solução dos alvos.
    nums=[]
    for e,u in candidates(selected,True):
        nums.append((e,u)); yield e,u
        if len(nums)>=48:break
    tests=[((12,False),()),((12,True),())]
    atoms=[(e,()) for e in list(BASE)+[(11,1)]]
    for a,ua in atoms:
        for b,ub in atoms:
            for op in (20,21): tests.append(((op,a,b),()))
    # Varredura diagonal evita gastar todo o orçamento em uma única condição.
    for diagonal in range(len(tests)+2*len(nums)-2):
        for ci in range(max(0,diagonal-2*(len(nums)-1)),min(len(tests),diagonal+1)):
            cond,uc=tests[ci]
            for ai in range(max(0,diagonal-ci-len(nums)+1),min(len(nums),diagonal-ci+1)):
                bi=diagonal-ci-ai
                if bi>=len(nums):continue
                a,ua=nums[ai];b,ub=nums[bi]
                if a==b:continue
                e=(30,cond,a,b)
                if depth(e)<=4 and size(e)<=31:yield e,tuple(sorted(set(ua+ub+uc)))
