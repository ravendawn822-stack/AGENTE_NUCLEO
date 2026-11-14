import time, tracemalloc, itertools

# Tuplas: (10, constante), (11, identificador), (operacao, esquerda, direita).
BASE = [(10, i) for i in (-2,-1,0,1,2)] + [(11,0)]
def value(e,x):
    if e[0]==10: return e[1]
    if e[0]==11: return x
    a,b=value(e[1],x),value(e[2],x)
    return a+b if e[0]==1 else a-b if e[0]==2 else a*b
def depth(e): return 1 if e[0]>3 else 1+max(depth(e[1]),depth(e[2]))
def size(e): return 1 if e[0]>3 else 1+size(e[1])+size(e[2])
def subs(e):
    if e[0]<=3:
        yield e
        yield from subs(e[1]); yield from subs(e[2])
def candidates(skills):
    current=list(dict.fromkeys(BASE+list(skills))); seen=set(current)
    yield from current
    for _ in range(3):
        new=[]
        for a in current:
            for b in current:
                if max(depth(a),depth(b))>=4: continue
                for op in (1,2,3):
                    e=(op,a,b)
                    if e not in seen:
                        seen.add(e); new.append(e); yield e
        current+=new

def solve(query, skills, mode, config):
    tracemalloc.start(); start=time.perf_counter(); cpu=time.process_time()
    deadline=start+config['seconds'] if mode=='time' else float('inf')
    observations=[]; best=None; n=0; reused=0
    # Todas as previsoes usadas para escolher consultas contam no orçamento.
    batch=[]
    for e in itertools.islice(candidates(skills), config['hypotheses'] if mode=='hypotheses' else config['safety_cap']):
        if time.perf_counter()>=deadline: break
        n+=1; batch.append(e)
        if len(batch)==32:
            if not observations:
                # Entropia da particao de previsoes, prior uniforme sobre o lote.
                import math, collections
                def entropy(x):
                    counts=collections.Counter(value(h,x) for h in batch)
                    return -sum((v/len(batch))*math.log2(v/len(batch)) for v in counts.values())
                pool=list(range(-6,7))
                first=max(pool,key=entropy)
                inputs=[first]+[v for v in (-3,-1,0,2,4) if v!=first]
                observations=[(x,query(x)) for x in inputs]
            for h in batch:
                if all(value(h,x)==y for x,y in observations): best=h; break
            batch=[]
            if best: break
    if best is None and observations:
        for h in batch:
            if all(value(h,x)==y for x,y in observations): best=h; break
    if best: reused=sum(s in set(skills) for s in subs(best))
    elapsed=time.perf_counter()-start; cpu=time.process_time()-cpu
    peak=tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
    return best,dict(hypotheses=n,seconds=elapsed,cpu_seconds=cpu,peak_bytes=peak,
        experiments=len(observations),skills=len(skills),reuse=reused,
        depth=depth(best) if best else 0,size=size(best) if best else 0,
        observations=observations)
