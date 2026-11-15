"""Bounded finite-state rule inference and frozen planning; offline simulator only."""
import argparse,json,random,sys,unittest
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V59"))
from environment import path_to
SEEDS=(7860017,7890023,7920031,7950041)
N=17
ACTIONS=tuple(range(3))
HYPOTHESES=tuple((a,b) for a in range(N) for b in range(N))
MODES=("active","random","map")
BUDGET=6

def predict(h,s):return (h[0]*s+h[1])%N

class Learner:
    def __init__(self,mode):
        self.mode=mode;self.remaining={a:HYPOTHESES for a in ACTIONS};self.observed={a:{} for a in ACTIONS}
        self.identification={a:None for a in ACTIONS};self.events=[]
    def choose(self,a,rng):
        unknown=[s for s in range(N) if s not in self.observed[a]]
        if self.mode=="random":return rng.choice(unknown)
        def score(s):
            counts=Counter(predict(h,s) for h in self.remaining[a])
            return sum(v*v for v in counts.values()),s
        return min(unknown,key=score)
    def observe(self,a,s,t):
        if s in self.observed[a]:raise ValueError("duplicate query")
        self.observed[a][s]=t
        self.remaining[a]=tuple(h for h in self.remaining[a] if predict(h,s)==t)
        if len(self.remaining[a])==1 and self.identification[a] is None:self.identification[a]=len(self.observed[a])
        self.events.append(dict(action=a,state=s,target=t,hypotheses=len(self.remaining[a])))
    def estimate(self,a,s):
        if s in self.observed[a]:return self.observed[a][s]
        if self.mode=="map" or not self.remaining[a]:return None
        values={predict(h,s) for h in self.remaining[a]}
        return next(iter(values)) if len(values)==1 else None
    def graph(self):
        graph={}
        for a in ACTIONS:
            for s in range(N):
                t=self.estimate(a,s)
                if t is not None:graph[s,a]=t
        return graph

class Oracle:
    def __init__(self,table):self._table=table;self.used=Counter()
    def query(self,a,s):
        if a not in ACTIONS or not 0<=s<N or self.used[a]>=BUDGET:raise ValueError("query budget")
        self.used[a]+=1;return self._table[s,a]

def world(seed,outside):
    rng=random.Random(seed);rules={a:(rng.randrange(N),rng.randrange(N)) for a in ACTIONS}
    table={(s,a):predict(rules[a],s) for s in range(N) for a in ACTIONS}
    changed=[]
    if outside:
        for a in ACTIONS:
            for s in rng.sample(range(N),3):
                table[s,a]=(table[s,a]+rng.randrange(1,N))%N;changed.append((s,a))
    return table,rules,changed

def train(table,mode,seed,active=None):
    learner=Learner(mode);oracle=Oracle(table);rng=random.Random(seed^0x6001)
    for a in ACTIONS:
        for i in range(BUDGET):
            s=list(active.observed[a])[i] if mode=="map" else learner.choose(a,rng)
            learner.observe(a,s,oracle.query(a,s))
    return learner

def evaluate(learner,table,held,goals):
    correct=wrong=abstained=0;rows=[]
    for s,a in held:
        p=learner.estimate(a,s);target=table[s,a]
        correct+=p==target;wrong+=p is not None and p!=target;abstained+=p is None
        rows.append(dict(state=s,action=a,prediction=p,target=target))
    graph=learner.graph();plans=[]
    for start,goal in goals:
        plan=path_to(graph,start,lambda s:s==goal);state=start
        if plan is not None:
            if len(plan)>N:raise RuntimeError("path budget")
            for a in plan:state=table[state,a]
        plans.append(dict(start=start,goal=goal,plan=plan,success=plan is not None and state==goal,
             wrong=plan is not None and state!=goal,abstained=plan is None))
    result=dict(held=len(held),correct=correct,wrong=wrong,abstained=abstained,
        goals=len(goals),goal_success=sum(p["success"] for p in plans),
        goal_wrong=sum(p["wrong"] for p in plans),goal_abstained=sum(p["abstained"] for p in plans),
        empty_hypothesis_sets=sum(not learner.remaining[a] for a in ACTIONS),
        identified_actions=sum(len(learner.remaining[a])==1 for a in ACTIONS) if learner.mode!="map" else 0,
        identification_queries=[learner.identification[a] for a in ACTIONS] if learner.mode!="map" else [])
    return result,rows,plans

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        for outside in (False,True):
            table,rules,changed=world(seed,outside)
            active=train(table,"active",seed);random_agent=train(table,"random",seed)
            mapping=train(table,"map",seed,active)
            held=[(s,a) for a in ACTIONS for s in range(N) if s not in active.observed[a] and s not in random_agent.observed[a]]
            goals=random.Random(seed^0x6002).sample([(s,t) for s in range(N) for t in range(N) if s!=t],12)
            for learner in (active,random_agent,mapping):
                result,rows,plans=evaluate(learner,table,held,goals)
                record=dict(seed=seed,outside=outside,mode=learner.mode,**result);results.append(record)
                (out/f"{seed}_{outside}_{learner.mode}.json").write_text(json.dumps(dict(result=record,
                    rules=rules,changed=changed,observations=learner.events,predictions=rows,plans=plans),indent=2),encoding="utf-8")
    keys=("held","correct","wrong","abstained","goals","goal_success","goal_wrong","goal_abstained","empty_hypothesis_sets","identified_actions")
    aggregate=[dict(outside=outside,mode=mode,**{k:sum(r[k] for r in results if r["outside"]==outside and r["mode"]==mode) for k in keys})
               for outside in (False,True) for mode in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V60-rule-discovery-v1",aggregate=aggregate,by_seed=results),indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_identification(self):
        l=Learner("active")
        l.observe(0,0,4);l.observe(0,1,7)
        self.assertEqual(l.remaining[0],((3,4),))
        self.assertEqual(l.estimate(0,9),14)
        l.observe(0,9,15);self.assertIsNone(l.estimate(0,8))
    def test_map(self):
        l=Learner("map");l.observe(1,0,4);self.assertIsNone(l.estimate(1,1))
    def test_budget(self):
        o=Oracle(world(SEEDS[0],False)[0])
        for s in range(BUDGET):o.query(0,s)
        with self.assertRaises(ValueError):o.query(0,BUDGET)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V60 required")
    run(a.output.resolve())
if __name__=="__main__":main()
