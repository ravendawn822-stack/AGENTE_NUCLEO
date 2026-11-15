"""Factorized transition rules; offline, matched trajectories and disjoint seeds."""
import sys,json,argparse,itertools,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V217_V330"))
from cognition import hypotheses,apply
from experiment import Environment,episode,FAMILIES,DEFAULT,BUDGET
CAP=256
VAL=range(347001,347009)
TEST=range(357001,357017)
def test_guard(g,s):
    i,op,k=g;v=s[i]
    return v==k if op=="eq" else v!=k if op=="ne" else v<=k if op=="le" else v>k
def leaf(f,x):return x+f[1] if f[0]=="delta" else f[1]
def scalar(h,s,i):
    guards,l,r=h
    return leaf(l if all(test_guard(g,s) for g in guards) else r,s[i])
def leaf_fit(rows,i):
    d=Counter(t[i]-s[i] for s,t in rows)
    c=Counter(t[i] for s,t in rows)
    results=[]
    for kind,counts in (("delta",d),("const",c)):
        for v,n in sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))[:2]:
            results.append((len(rows)-n,0 if kind=="delta" else 1,(kind,v)))
    return sorted(results)
def fit_component(rows,i):
    seen=set();ranked=[]
    def add(h):
        if len(seen)>=CAP or h in seen:return None
        seen.add(h)
        error=sum(scalar(h,s,i)!=t[i] for s,t in rows)
        complexity=1+2*len(h[0])+int(h[1][0]=="const")+int(bool(h[0]) and h[2][0]=="const")
        item=(error,complexity,h);ranked.append(item);return item
    for _,_,f in leaf_fit(rows,i):add(((),f,f))
    singles=[(axis,op,k) for axis in range(2) for k in sorted({s[axis] for s,t in rows}) for op in ("eq","le","ne","gt")]
    scores=[[],[]]
    def guarded(gs):
        yes=[(s,t) for s,t in rows if all(test_guard(g,s) for g in gs)]
        no=[(s,t) for s,t in rows if not all(test_guard(g,s) for g in gs)]
        if not yes or not no:return None
        l=leaf_fit(yes,i)[0][2];r=leaf_fit(no,i)[0][2]
        if l==r:return None
        return add((gs,l,r))
    for g in singles:
        item=guarded((g,))
        if item is not None:scores[g[0]].append((item[:2],g))
    # Rank by fit on observed data alone; fixed width, no evaluation labels.
    best=[[g for _,g in sorted(sc)[:8]] for sc in scores]
    for g,h in itertools.product(*best):
        if len(seen)>=CAP:break
        guarded((g,h))
    ranked.sort()
    return ranked[:8],len(seen)
class Predictors:
    def __init__(self,learner):
        self.exact=learner.edges;self.old={};self.new={};self.cost=Counter()
        for a in learner.actions:
            rows=[(s,t) for (s,b),t in self.exact.items() if b==a][-48:]
            if not rows:continue
            self.old[a],c=hypotheses(rows);self.cost["old"]+=c
            self.new[a]=[]
            for i in range(2):
                m,c=fit_component(rows,i);self.new[a].append(m);self.cost["factor"]+=c
    def predict(self,s,a,mode):
        if (s,a) in self.exact:return self.exact[s,a]
        if mode=="old":
            m=self.old.get(a)
            return apply(m[0][2],s) if m and m[0][0]==0 else None
        if a not in self.new:return None
        p=[]
        for i,m in enumerate(self.new[a]):
            if not m or m[0][0]:return None
            values={scalar(h,s,i) for e,c,h in m if (e,c)==m[0][:2]}
            if mode=="consensus" and len(values)!=1:return None
            p.append(scalar(m[0][2],s,i))
        return tuple(p)
def run(seeds):
    records=[]
    for f in FAMILIES:
        for seed in seeds:
            env,l=episode(f,seed,"novel",DEFAULT);p=Predictors(l)
            pairs=[(s,a,env.transition(s,a)) for s in env.states for a in env.actions if (s,a) not in l.edges]
            rows=[]
            for s,a,t in pairs:
                rows.append(dict(state=s,action=a,actual=t,**{m:p.predict(s,a,m) for m in ("old","factor","consensus")}))
            records.append(dict(family=f,seed=seed,actions=len(l.events),cost=dict(p.cost),
                observations=l.events,models_old=p.old,models_factor=p.new,held=rows))
    return records
def summarize(rows):
    out=[]
    for family in ("all",)+FAMILIES:
        subset=[r for r in rows if family=="all" or r["family"]==family]
        for mode in ("old","factor","consensus"):
            pairs=[x for r in subset for x in r["held"]]
            correct=sum(x[mode]==x["actual"] for x in pairs)
            abstained=sum(x[mode] is None for x in pairs)
            out.append(dict(family=family,mode=mode,worlds=len(subset),total=len(pairs),correct=correct,
                wrong=len(pairs)-correct-abstained,abstained=abstained,
                candidates=sum(r["cost"].get("old" if mode=="old" else "factor",0) for r in subset)))
    return out
def test():
    rows=[((x,y),(x+1 if x<5 and y==0 else x,(y+1)%3)) for x in range(7) for y in range(3) if (x,y) not in ((2,0),(5,1),(4,2))]
    models=[fit_component(rows,i)[0] for i in range(2)]
    assert all(m and m[0][0]==0 for m in models)
    for s in ((2,0),(5,1),(4,2)):
        predicted=tuple(scalar(m[0][2],s,i) for i,m in enumerate(models))
        assert predicted==(s[0]+1 if s[0]<5 and s[1]==0 else s[0],(s[1]+1)%3),(s,predicted,models)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    test()
    v=run(VAL);sv=summarize(v);base,c1,c2=sv[:3]
    choice=max((c1,c2),key=lambda z:(z["correct"],-z["wrong"]))
    gate=dict(candidate=choice["mode"],promoted=choice["correct"]>base["correct"] and choice["wrong"]<=base["wrong"])
    gate["policy"]=gate["candidate"] if gate["promoted"] else "old"
    (a.out/"gate.json").write_text(json.dumps(gate,sort_keys=True))
    t=run(TEST);st=summarize(t)
    for name,data in (("validation",v),("test",t)):
        with (a.out/(name+".jsonl")).open("x") as f:
            for r in data:f.write(json.dumps(r,separators=(",",":"))+"\n")
    summary=dict(gate=gate,validation=sv,test=st)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
