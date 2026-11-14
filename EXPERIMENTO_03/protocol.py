"""Avaliador: não é importado pelo mecanismo de seleção."""
import random
from fractions import Fraction
from model import *
def random_tree(r,d):
    if d==1 or r.random()<.12:return r.choice(BASE)
    return (r.choice((1,2,3)),random_tree(r,d-1),random_tree(r,d-1))
def suite(seed,n=100):
    r=random.Random(seed); seen=set(); result=[]
    while len(result)<2*n:
        e=random_tree(r,r.choice((2,3,4)));sig=tuple(value(e,x) for x in range(-4,5))
        if sig in seen or len(set(sig))==1:continue
        seen.add(sig);result.append(e)
    return result[:n],result[n:]
def check(expr,target,expanded=False):
    xs=[(x,y) for x in (-7,-4,0,4,7) for y in (-6,-3,1,3,6)] if expanded else list(range(10,27))+list(range(-26,-9))
    return bool(expr) and all(value(expr,x)==value(target,x) for x in xs)
def interpolation(target):
    # Referência forte separada; não é disponibilizada à busca simbólica.
    xs=list(range(-4,5));ys=[value(target,x) for x in xs]
    def predict(z):
        total=Fraction(0)
        for i,x in enumerate(xs):
            term=Fraction(ys[i])
            for j,t in enumerate(xs):
                if i!=j:term*=Fraction(z-t,x-t)
            total+=term
        return total
    return all(predict(z)==value(target,z) for z in list(range(10,27))+list(range(-26,-9)))
def programs(seed,n=30):
    r=random.Random(seed);seen=set();out=[];atoms=list(BASE)+[(11,1)]
    while len(out)<2*n:
        branches=[]
        for _ in range(2):
            branches.append(r.choice(atoms) if r.random()<.5 else (r.choice((1,2,3)),r.choice(atoms),r.choice(atoms)))
        e=(30,(r.choice((20,21)),r.choice(atoms),r.choice(atoms)),*branches)
        sig=tuple(value(e,(x,y)) for x in range(-3,4) for y in range(-3,4))
        if sig in seen or len(set(sig))<2:continue
        seen.add(sig);out.append(e)
    return out[:n],out[n:]
