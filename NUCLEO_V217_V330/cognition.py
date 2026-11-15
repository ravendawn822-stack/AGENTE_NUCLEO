"""Symbolic transition learning, bounded model search, intrinsic action selection."""
from collections import Counter
from itertools import product
import random, json
CAP=512
WINDOW=48
def apply(h,s):
    kind,axis,cut,left,right=h
    if kind=="constant":return left
    if kind=="delta":d=left
    elif kind=="eq":d=left if s[axis]==cut else right
    elif kind=="le":d=left if s[axis]<=cut else right
    else:raise ValueError("template")
    return tuple(x+y for x,y in zip(s,d))
def delta(s,t):return tuple(y-x for x,y in zip(s,t))
def complexity(h):return {"delta":1,"constant":2,"eq":3,"le":3}[h[0]]
def hypotheses(rows,order=("delta","constant","eq","le")):
    ds=Counter(delta(s,t) for s,t in rows)
    shifts=sorted(ds,key=lambda d:(-ds[d],d))[:6]
    # Candidate guards derived from observed feature values only.
    cuts=[(i,c) for i in range(len(rows[0][0])) for c in sorted({s[i] for s,t in rows})]
    def gen():
        for kind in order:
            if kind=="delta":
                for d in shifts:yield (kind,0,0,d,())
            elif kind=="constant":
                for t in sorted({t for s,t in rows}):yield (kind,0,0,t,())
            else:
                for i,c in cuts:
                    yes=Counter(delta(s,t) for s,t in rows if (s[i]==c if kind=="eq" else s[i]<=c))
                    no=Counter(delta(s,t) for s,t in rows if not (s[i]==c if kind=="eq" else s[i]<=c))
                    if not yes or not no:continue
                    for d,e in product([v for v,n in yes.most_common(2)],[v for v,n in no.most_common(2)]):
                        if d!=e:yield (kind,i,c,d,e)
    ranked=[];seen=set()
    for h in gen():
        if h in seen:continue
        if len(seen)>=CAP:break
        seen.add(h)
        errors=sum(apply(h,s)!=t for s,t in rows)
        ranked.append((errors,complexity(h),h))
    ranked.sort()
    return ranked[:8],len(seen)
class Learner:
    def __init__(self,actions,mode="active",seed=0,order=("delta","constant","eq","le")):
        self.actions=tuple(actions)
        if not 1<=len(self.actions)<=16 or len(set(self.actions))!=len(self.actions):raise ValueError("actions")
        if mode not in ("random","novel","active"):raise ValueError("mode")
        self.mode=mode;self.rng=random.Random(seed);self.order=tuple(order)
        if sorted(self.order)!=["constant","delta","eq","le"]:raise ValueError("order")
        self.edges={};self.models={};self.cost=0;self.counts=Counter();self.visits=Counter();self.events=[]
    def predict(self,s,a,exact=False):
        if (s,a) in self.edges:return self.edges[s,a],"memory"
        if exact or not self.models.get(a):return None,"unknown"
        errs,_,h=self.models[a][0]
        # Uncertain and erroneous fit must not become asserted knowledge.
        if errs:return None,"conflict"
        return apply(h,s),"hypothesis"
    def choose(self,s):
        if self.mode=="random":return self.rng.choice(self.actions),{}
        scores={}
        for a in self.actions:
            unseen=int((s,a) not in self.edges)
            m=self.models.get(a,[])
            best=m[0][0] if m else None
            preds={apply(h,s) for error,_,h in m if error==best}
            disagreement=max(0,len(preds)-1)
            p,_=self.predict(s,a)
            # Exact state repetition gets less value; uncertainty is not reward from the environment.
            novelty=1/(1+self.visits[p]) if p is not None else 1
            scores[a]=round(2*unseen+novelty+1/(1+self.counts[a])+(disagreement if self.mode=="active" else 0),8)
        best=max(scores.values())
        return self.rng.choice([a for a in self.actions if scores[a]==best]),scores
    def observe(self,s,a,t,scores=None):
        if a not in self.actions or not 1<=len(s)<=4 or len(t)!=len(s) or any(type(x) is not int or abs(x)>1000000 for x in s+t):raise ValueError("observation")
        p,source=self.predict(s,a)
        old=self.edges.get((s,a));self.edges[s,a]=t
        self.counts[a]+=1;self.visits[s]+=1;self.visits[t]+=1
        rows=[(x,y) for (x,b),y in self.edges.items() if b==a][-WINDOW:]
        before=self.models.get(a,[])
        self.models[a],n=hypotheses(rows,self.order);self.cost+=n
        after=self.models[a]
        event=dict(step=len(self.events)+1,before=s,action=a,after=t,prediction=p,source=source,
            correct=None if p is None else p==t,changed=old is not None and old!=t,novel=old is None,
            revised=bool(before and after and before[0][2]!=after[0][2]),model=after[0] if after else None,
            candidates=n,scores=scores or {})
        self.events.append(event);return event
    def step(self,env):
        s=tuple(env.observe());a,scores=self.choose(s);t=tuple(env.act(a))
        return self.observe(s,a,t,scores)
    def report(self):
        return dict(events=len(self.events),pairs=len(self.edges),candidate_cost=self.cost,
            models={a:self.models.get(a,[]) for a in self.actions})
    def checkpoint(self):
        return dict(actions=self.actions,mode=self.mode,order=self.order,events=self.events)
    @classmethod
    def restore(cls,data,seed=0):
        if len(data["events"])>4096:raise ValueError("checkpoint")
        x=cls(data["actions"],data["mode"],seed,data["order"])
        for e in data["events"]:x.observe(tuple(e["before"]),e["action"],tuple(e["after"]),e["scores"])
        return x
