"""Revision of finite simulated transition models, no external actions."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V61"))
from epistemic import N,ACTIONS,HYPOTHESES,predict,world,plans,evaluate,write,path_to
SEEDS=tuple(8100017+30001*i for i in range(24))
MODES=("exact","repair","map")
STRATA=(0,1,3)

def order(seed,a):
    return random.Random(seed^(0x620000+a)).sample(range(N),10)

def unique_best(hypotheses,observations,minimum,fn):
    best=[];score=-1
    for h in hypotheses:
        n=sum(fn(h,s)==t for s,t in observations)
        if n>score:best=[h];score=n
        elif n==score:best.append(h)
    return (best[0] if len(best)==1 and score>=minimum else None),score

class Revised:
    def __init__(self,mode):
        if mode not in MODES:raise ValueError("mode")
        self.mode=mode;self.observed={a:{} for a in ACTIONS};self.events=[]
        self.models={a:None for a in ACTIONS};self.status={a:"unknown" for a in ACTIONS}
    def observe(self,a,s,t):
        if a not in ACTIONS or not 0<=s<N or not 0<=t<N:raise ValueError("observation")
        obs=self.observed[a]
        if s in obs or len(obs)>=10:raise ValueError("query")
        obs[s]=t
        self.events.append([a,s,t])
        if len(obs)!=10:return
        if self.mode=="map":return
        pairs=list(obs.items())
        if self.mode=="exact":
            h,n=unique_best(HYPOTHESES,pairs,10,predict)
        else:
            h,n=unique_best(HYPOTHESES,pairs[:6],5,predict)
            if h is not None and sum(predict(h,x)==y for x,y in pairs[6:])<3:h=None
        self.models[a]=h
        self.status[a]="contradicted" if h is None else ("revised" if any(predict(h,x)!=y for x,y in pairs) else "inferred")
    def belief(self,a,s):
        if s in self.observed[a]:return self.observed[a][s],"observed"
        h=self.models[a]
        return (None,self.status[a]) if h is None else (predict(h,s),self.status[a])
    def graph(self):
        return {(s,a):p for a in ACTIONS for s in range(N)
                for p,status in (self.belief(a,s),) if p is not None}
    def state(self):
        return dict(mode=self.mode,events=self.events,models=self.models,status=self.status)
    @classmethod
    def restore(cls,state):
        x=cls(state["mode"])
        for a,s,t in state["events"]:x.observe(a,s,t)
        return x

def train(table,seed,mode):
    mem=Revised(mode)
    for a in ACTIONS:
        for s in order(seed,a):mem.observe(a,s,table[s,a])
    return mem

def summarize(results,strata,modes,field):
    aggregate=[]
    for k in strata:
        for mode in modes:
            rows=[x for x in results if x[field]==k and x["mode"]==mode]
            d=dict((key,rows[0][key]) for key in ())
            for name in ("held","plans"):
                d[name]={key:sum(x[name][key] for x in rows) for key in rows[0][name]}
            for name in ("queries","revised","contradicted","candidates"):
                if name in rows[0]:d[name]=sum(x[name] for x in rows)
            aggregate.append(dict(**{field:k},mode=mode,**d))
    return aggregate

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        goals=random.Random(seed^0x6202).sample([(s,t) for s in range(N) for t in range(N) if s!=t],12)
        for k in STRATA:
            table,rules,changed=world(seed,k)
            for mode in MODES:
                mem=train(table,seed,mode)
                held={(s,a) for a in ACTIONS for s in range(N) if s not in mem.observed[a]}
                metrics,rows=evaluate(mem,table,held);pm,pr=plans(mem,table,goals)
                row=dict(seed=seed,exceptions=k,mode=mode,held=metrics,plans=pm,queries=len(mem.events),
                    revised=list(mem.status.values()).count("revised"),contradicted=list(mem.status.values()).count("contradicted"))
                results.append(row)
                write(out/f"{seed}_{k}_{mode}.json",dict(result=row,observations=mem.events,rules=rules,changed=changed,models=mem.models,held=rows,plans=pr))
    summary=dict(protocol="V62-revision-v1",aggregate=summarize(results,STRATA,MODES,"exceptions"),by_seed=results)
    write(out/"summary.json",summary);print(json.dumps(summary["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_repair(self):
        x=Revised("repair")
        for s in range(10):x.observe(0,s,(3*s+4+(s==2))%N)
        self.assertEqual(x.belief(0,2),(11,"observed"))
        self.assertEqual(x.belief(0,10),(0,"revised"))
        self.assertEqual(x.state(),Revised.restore(x.state()).state())
    def test_exact(self):
        x=Revised("exact")
        for s in range(10):x.observe(0,s,(3*s+4+(s==2))%N)
        self.assertEqual(x.belief(0,10),(None,"contradicted"))
    def test_tie(self):
        h,n=unique_best(HYPOTHESES,[(0,0)],1,predict);self.assertIsNone(h)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V62 required")
    run(a.output.resolve())
if __name__=="__main__":main()
