"""Finite simulated worlds; no external tools or arbitrary code."""
import argparse,json,random,unittest
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=(7740017,7770023,7800031,7830041)
N=24
ACTIONS=tuple(range(4))
BUDGET=80
MODES=("explore","random")

def path_to(graph,start,goal):
    queue=deque([(start,())]);seen={start}
    while queue:
        s,path=queue.popleft()
        if goal(s):return path
        for (source,a),target in sorted(graph.items()):
            if source==s and target not in seen:
                seen.add(target);queue.append((target,path+(a,)))
    return None

class World:
    def __init__(self,transitions,budget=BUDGET):
        self._transitions=dict(transitions);self._budget=budget;self._used=0;self._state=0;self.resets=0
    def observe(self):return self._state,ACTIONS,self._budget-self._used
    def reset(self):self._state=0;self.resets+=1;return self.observe()
    def act(self,a):
        if a not in ACTIONS or self._used>=self._budget:raise ValueError("action or budget")
        self._used+=1;self._state=self._transitions[self._state,a];return self.observe()

class Agent:
    def __init__(self):self.model={};self.events=[]
    def choose(self,state,actions):
        path=path_to(self.model,state,lambda s:any((s,a) not in self.model for a in actions))
        if path is None:return None
        return path[0] if path else next(a for a in actions if (state,a) not in self.model)
    def learn(self,s,a,t):
        key=(s,a)
        if key in self.model and self.model[key]!=t:raise ValueError("nonstationary world")
        self.model[key]=t;self.events.append((s,a,t))
    def train(self,world,mode,rng):
        while True:
            s,actions,remaining=world.observe()
            if not remaining:break
            if mode=="random":a=rng.choice(actions)
            else:
                a=self.choose(s,actions)
                if a is None:
                    s,actions,_=world.reset();a=self.choose(s,actions)
                if a is None:break
            t,_,_=world.act(a);self.learn(s,a,t)

def make_world(seed):
    rng=random.Random(seed);ring=list(range(N));rng.shuffle(ring);ring_action=rng.choice(ACTIONS)
    table={(s,a):rng.randrange(N) for s in range(N) for a in ACTIONS}
    for i,s in enumerate(ring):table[s,ring_action]=ring[(i+1)%N]
    return table

def evaluate(model,table,goals):
    records=[]
    for goal in goals:
        plan=path_to(model,0,lambda s:s==goal)
        world=World(table,N);state=0
        if plan is not None:
            for a in plan:state,_,_=world.act(a)
        records.append(dict(goal=goal,plan=plan,success=plan is not None and state==goal,
            wrong=plan is not None and state!=goal,abstained=plan is None,cost=len(plan or ())))
    return records

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        table=make_world(seed);goals=random.Random(seed^0x5901).sample(list(range(1,N)),12)
        for mode in MODES:
            world=World(table);agent=Agent();agent.train(world,mode,random.Random(seed^0x5902))
            final=evaluate(agent.model,table,goals)
            row=dict(seed=seed,mode=mode,observations=len(agent.events),coverage=len(agent.model),
                resets=world.resets,model_errors=sum(table[k]!=t for k,t in agent.model.items()),
                success=sum(x["success"] for x in final),wrong=sum(x["wrong"] for x in final),
                abstained=sum(x["abstained"] for x in final),plan_cost=sum(x["cost"] for x in final))
            results.append(row)
            (out/f"{seed}_{mode}.json").write_text(json.dumps(dict(result=row,table=[[s,a,t] for (s,a),t in sorted(table.items())],
                observations=agent.events,goals=final),indent=2),encoding="utf-8")
    aggregate=[dict(mode=mode,**{k:sum(r[k] for r in results if r["mode"]==mode) for k in
        ("observations","coverage","resets","model_errors","success","wrong","abstained","plan_cost")}) for mode in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V59-environment-v1",aggregate=aggregate,by_seed=results),indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_path(self):
        graph={(0,1):2,(2,0):3,(3,0):0}
        self.assertEqual(path_to(graph,0,lambda s:s==3),(1,0))
        self.assertIsNone(path_to(graph,0,lambda s:s==4))
    def test_budget(self):
        w=World(make_world(SEEDS[0]),1);a=Agent();a.train(w,"explore",random.Random(1))
        self.assertEqual(len(a.events),1)
        with self.assertRaises(ValueError):w.act(0)
    def test_conflict(self):
        a=Agent();a.learn(0,0,1)
        with self.assertRaises(ValueError):a.learn(0,0,2)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V59 required")
    run(a.output.resolve())
if __name__=="__main__":main()
