"""Closed-loop learning: baseline, lazy fallback, full factorization; disjoint seeds."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V217_V330"))
sys.path.insert(0,str(ROOT/"NUCLEO_V217_V330_REFINO1"))
from cognition import Learner,WINDOW
from experiment import Environment,FAMILIES,BUDGET,metrics
from factor import fit_component,scalar
VAL=range(367001,367009)
TEST=range(377001,377017)
MODES=("novel","hybrid","factor")
class Online(Learner):
    def __init__(self,actions,variant,seed):
        super().__init__(actions,"novel",seed)
        self.variant=variant;self.cache={};self.factor_cost=0;self.frozen=False
    def prepare(self,a):
        if a in self.cache:return self.cache[a]
        if self.frozen:raise RuntimeError("fit attempted after freeze")
        rows=[(s,t) for (s,b),t in self.edges.items() if b==a][-WINDOW:]
        models=[]
        if rows and len(rows[0][0])==2:
            for i in range(2):
                m,n=fit_component(rows,i);models.append(m);self.factor_cost+=n
        self.cache[a]=models
        return models
    def predict(self,s,a,exact=False):
        p,source=super().predict(s,a,exact)
        if exact or source=="memory" or self.variant=="novel":return p,source
        if self.variant=="hybrid" and source!="conflict":return p,source
        if a not in self.models:return None,"unknown"
        models=self.prepare(a)
        if len(models)!=2 or any(not m or m[0][0] for m in models):return None,"conflict"
        return tuple(scalar(m[0][2],s,i) for i,m in enumerate(models)),"factorized"
    def observe(self,s,a,t,scores=None):
        if self.frozen:raise RuntimeError("frozen")
        e=super().observe(s,a,t,scores)
        if e["novel"] or e["changed"]:self.cache.pop(a,None)
        e["cumulative_factor_candidates"]=self.factor_cost
        return e
    def freeze(self):
        for a,m in self.models.items():
            if self.variant=="factor" or (self.variant=="hybrid" and m and m[0][0]):
                self.prepare(a)
        self.frozen=True
def episode(f,s,mode):
    e=Environment(f,s);l=Online(e.actions,mode,s+13)
    for _ in range(BUDGET):l.step(e)
    l.freeze();return e,l
def run(seeds):
    rows=[]
    for f in FAMILIES:
        for s in seeds:
            runs=[(mode,*episode(f,s,mode)) for mode in MODES]
            e=runs[0][1]
            pairs=[(s,a) for s in e.states for a in e.actions]
            common=[(s,a) for s,a in pairs if all((s,a) not in l.edges for _,_,l in runs)]
            for mode,e,l in runs:
                cost=(l.cost,l.factor_cost)
                scopes={"all":pairs,"unseen":[(s,a) for s,a in pairs if (s,a) not in l.edges],"common":common}
                result={k:metrics(e,l,p) for k,p in scopes.items()}
                assert cost==(l.cost,l.factor_cost)
                rows.append(dict(family=f,seed=s,mode=mode,pairs=len(l.edges),actions=BUDGET,
                    cost_base=l.cost,cost_factor=l.factor_cost,results=result,events=l.events,
                    final_models=l.models,final_factor_models=l.cache))
    return rows
def summarize(rows):
    output=[]
    for f in ("all",)+FAMILIES:
        for m in MODES:
            rr=[r for r in rows if (f=="all" or f==r["family"]) and r["mode"]==m]
            out=dict(family=f,mode=m,episodes=len(rr))
            for k in ("pairs","actions","cost_base","cost_factor"):out[k]=sum(r[k] for r in rr)
            for scope in ("all","unseen","common"):
                for k in ("total","correct","wrong","abstained"):out[scope+"_"+k]=sum(r["results"][scope][k] for r in rr)
            output.append(out)
    return output
def test():
    a=Online(("a",),"hybrid",0)
    for x in range(7):
        for y in range(3):
            if (x,y)!=(2,0):a.observe((x,y),"a",(x+1 if x<5 and y==0 else x,(y+1)%3))
    a.freeze()
    assert a.predict((2,0),"a")==((3,1),"factorized")
    before=a.factor_cost
    a.predict((2,0),"a")
    assert a.factor_cost==before
def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True,type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    test()
    v=run(VAL);sv=summarize(v)
    base=sv[0]
    eligible=[r for r in sv[1:3] if r["common_correct"]>base["common_correct"] and r["common_wrong"]<=base["common_wrong"]]
    chosen=max(eligible,key=lambda r:(r["common_correct"],-r["common_wrong"],-r["cost_base"]-r["cost_factor"])) if eligible else base
    gate=dict(policy=chosen["mode"],promoted=chosen["mode"]!="novel")
    (a.out/"gate.json").write_text(json.dumps(gate,sort_keys=True))
    t=run(TEST);st=summarize(t)
    for name,data in (("validation",v),("test",t)):
        with (a.out/(name+".jsonl")).open("x") as f:
            for row in data:f.write(json.dumps(row,separators=(",",":"))+"\n")
    summary=dict(gate=gate,validation=sv,test=st)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
