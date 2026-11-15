"""External evaluator, disjoint phases, deterministic bounded environment experiments."""
import argparse, json, random, itertools, hashlib
from pathlib import Path
from collections import Counter
from cognition import Learner
TRAIN=range(217001,217009)
VAL=range(227001,227009)
TEST=range(237001,237017)
FAMILIES=("bounded","cycle","conditional","coupled","table")
DEFAULT=("delta","constant","eq","le")
BUDGET=64
class Environment:
    def __init__(self,family,seed):
        self.family=family;self.seed=seed;r=random.Random(seed)
        self.lo=r.randrange(-13,14);self.n=r.randrange(5,10);self.k=r.randrange(3,6)
        self.states=tuple(itertools.product(range(self.lo,self.lo+self.n),range(self.k)))
        self.actions=tuple("op"+str(i) for i in range(4))
        self.ops=list(range(4));r.shuffle(self.ops)
        self.state=r.choice(self.states)
        self.table={(s,a):r.choice(self.states) for s in self.states for a in self.actions} if family=="table" else {}
    def observe(self):return self.state
    def transition(self,s,a):
        x,y=s;i=self.ops[self.actions.index(a)];lo=self.lo;hi=lo+self.n-1;k=self.k
        if self.family=="table":return self.table[s,a]
        if self.family=="bounded":
            return ((min(hi,x+1),y),(max(lo,x-1),y),(x,min(k-1,y+1)),(x,max(0,y-1)))[i]
        if self.family=="cycle":
            return ((lo+(x-lo+1)%self.n,y),(lo+(x-lo-1)%self.n,y),(x,(y+1)%k),(x,(y-1)%k))[i]
        if self.family=="conditional":
            return ((min(hi,x+1) if y==0 else x,y),(max(lo,x-1),y),(x,(y+1)%k),(x,0))[i]
        if self.family=="coupled":
            return ((min(hi,x+1), (y+1)%k),(max(lo,x-1),y),(x,(y+1)%k),(x,(y-1)%k))[i]
        raise ValueError("family")
    def act(self,a):
        self.state=self.transition(self.state,a);return self.state
def metrics(env,learner,scope,exact=False):
    c=Counter()
    for s,a in scope:
        p,_=learner.predict(s,a,exact)
        c["total"]+=1
        if p is None:c["abstained"]+=1
        elif p==env.transition(s,a):c["correct"]+=1
        else:c["wrong"]+=1
    return {k:c[k] for k in ("total","correct","wrong","abstained")}
def episode(family,seed,mode,order):
    env=Environment(family,seed)
    agent=Learner(env.actions,mode,seed+13,order)
    for _ in range(BUDGET):agent.step(env)
    return env,agent
def phase(seeds,families,configs):
    rows=[]
    for f in families:
        for seed in seeds:
            runs=[(name,*episode(f,seed,mode,order)) for name,mode,order in configs]
            # Same held-out pairs for all arms for that world.
            e=runs[0][1];common=[(s,a) for s in e.states for a in e.actions
                if all((s,a) not in l.edges for _,_,l in runs)]
            for name,e,l in runs:
                scopes={"all":[(s,a) for s in e.states for a in e.actions],
                    "unseen":[(s,a) for s in e.states for a in e.actions if (s,a) not in l.edges],"common":common}
                for label in (name,"exact") if name=="novel" else (name,):
                    rows.append(dict(family=f,seed=seed,mode=label,order=l.order,actions=BUDGET,
                        pairs=len(l.edges),states=len(l.visits),blocked=sum(e["before"]==e["after"] for e in l.events),
                        candidates=l.cost,matched={a:metrics(e,l,q,label=="exact") for a,q in scopes.items()},
                        events=l.events if label!="exact" else []))
    return rows
def aggregate(rows):
    groups={}
    for r in rows:
        for f in ("all",r["family"]):
            k=(f,r["mode"])
            d=groups.setdefault(k,dict(family=f,mode=r["mode"],episodes=0,actions=0,pairs=0,states=0,blocked=0,candidates=0,
                **{scope+"_"+m:0 for scope in ("all","unseen","common") for m in ("total","correct","wrong","abstained")}))
            for v in ("actions","pairs","states","blocked","candidates"):d[v]+=r[v]
            d["episodes"]+=1
            for scope,vals in r["matched"].items():
                for m,n in vals.items():d[scope+"_"+m]+=n
    return list(groups.values())
def learn_order(rows):
    counts=Counter()
    for r in rows:
        for e in r["events"]:
            if e["model"] and e["model"][0]==0:counts[e["model"][2][0]]+=1
    return tuple(sorted(DEFAULT,key=lambda k:(-counts[k],DEFAULT.index(k))))
def overall(rows,mode):return next(r for r in aggregate(rows) if r["family"]=="all" and r["mode"]==mode)
def main():
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    training=phase(TRAIN,FAMILIES[:2],[("random","random",DEFAULT),("novel","novel",DEFAULT),("active","active",DEFAULT),("planned","planned",DEFAULT)])
    order=learn_order([r for r in training if r["mode"]=="active"])
    train_scores={m:overall(training,m) for m in ("random","novel","active","planned")}
    candidate=max(train_scores,key=lambda m:(train_scores[m]["common_correct"],-train_scores[m]["common_wrong"],-train_scores[m]["candidates"]))
    validation=phase(VAL,FAMILIES[2:4],[("novel","novel",DEFAULT),("candidate",candidate,order)])
    x=overall(validation,"candidate");y=overall(validation,"novel")
    promote=x["common_correct"]>y["common_correct"] and x["common_wrong"]<=y["common_wrong"]
    gate=dict(candidate=candidate,learned_order=order,promoted=promote,policy=candidate if promote else "novel",
        order=order if promote else DEFAULT)
    frozen=json.dumps(gate,sort_keys=True);(a.out/"gate.json").write_text(frozen)
    configs=[("random","random",DEFAULT),("novel","novel",DEFAULT),("active","active",DEFAULT),("planned","planned",DEFAULT),
             ("transfer","active",order),("gate",gate["policy"],gate["order"])]
    final=phase(TEST,FAMILIES,configs)
    for name,rows in (("train",training),("validation",validation),("test",final)):
        with (a.out/(name+".jsonl")).open("x") as out:
            for r in rows:out.write(json.dumps(r,separators=(",",":"))+"\n")
    summary=dict(protocol="V217–330 pilot",budget=BUDGET,gate=gate,gate_sha256=hashlib.sha256(frozen.encode()).hexdigest(),
        train=aggregate(training),validation=aggregate(validation),test=aggregate(final))
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps([r for r in summary["test"] if r["family"]=="all"],indent=2))
if __name__=="__main__":main()
