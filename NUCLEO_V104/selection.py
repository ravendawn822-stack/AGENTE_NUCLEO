"""Select a small vocabulary by fit-only error; equal candidate caps."""
import random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V103"))
import structure as st
w=st.w;s=st.s
MODES=("weighted","learned","selected","subset_random")
def select(fit,library):
    scores=[sum(abs(s.execute(p,x)-y) for x,y in fit) for p in library]
    order=sorted(range(len(library)),key=lambda i:(scores[i],i))[:4]
    return tuple(library[i] for i in order),scores,len(fit)*len(library)
def subset(seed,library):
    rng=random.Random(seed^0x10400)
    return tuple(library[i] for i in sorted(rng.sample(range(len(library)),min(4,len(library)))))
def choose(fit,mode,library,seed):
    if mode=="weighted":return (),[],0
    if mode=="learned":return library,[],0
    if mode=="selected":return select(fit,library)
    if mode=="subset_random":return subset(seed,library),[],0
    raise ValueError("mode")
def run(library):
    from audit import assess
    rows=[]
    for seed in st.SEEDS:
        for i,c in enumerate(st.cases(seed)):
            for m in MODES:
                macros,scores,ranking=choose(c["fit"],m,library,seed+997*i)
                r=w.search(c["fit"],macros)
                rows.append(dict(seed=seed,task=i,mode=m,kind=c["kind"],case=c,
                    vocabulary=macros,ranking_scores=scores,ranking_evaluations=ranking,search=r,**assess(c,r)))
    return rows
