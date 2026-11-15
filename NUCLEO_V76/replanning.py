"""Bounded replanning in a finite changing graph."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V59"))
from environment import path_to
N=20
ACTIONS=tuple(range(4))
SEEDS=tuple(28000019+30001*i for i in range(32))
MODES=("frozen","replan","explore","oracle")
CAP=40

def world(seed):
    rng=random.Random(seed)
    ring=list(range(N));rng.shuffle(ring);a=rng.choice(ACTIONS)
    initial={(s,k):rng.randrange(N) for s in range(N) for k in ACTIONS}
    for i,s in enumerate(ring):initial[s,a]=ring[(i+1)%N]
    altered=dict(initial)
    edits=rng.sample([k for k in initial if k[1]!=a],6)
    for k in edits:altered[k]=(initial[k]+rng.randrange(1,N))%N
    start,goal=rng.sample(range(N),2)
    return initial,altered,start,goal,edits

class World:
    def __init__(self,table,start):
        self._table=dict(table);self.state=start;self.used=0
    def act(self,a):
        if a not in ACTIONS or self.used>=CAP:raise ValueError("budget/action")
        self.state=self._table[self.state,a];self.used+=1;return self.state

def solve(initial,world,goal,mode):
    if mode not in MODES:raise ValueError("mode")
    graph=dict(initial);confirmed=set();events=[];replans=0
    route=path_to(graph,world.state,lambda s:s==goal)
    while world.state!=goal and world.used<CAP:
        origin=world.state
        if not route:
            if mode!="explore":break
            route=path_to(graph,origin,lambda s:any((s,a) not in confirmed for a in ACTIONS))
            if route is None:break
            if not route:route=(next(a for a in ACTIONS if (origin,a) not in confirmed),)
        action=route[0];route=route[1:]
        expected=graph[origin,action];actual=world.act(action)
        mismatch=actual!=expected;confirmed.add((origin,action))
        if mode in ("replan","explore") and mismatch:
            graph[origin,action]=actual
            route=path_to(graph,actual,lambda s:s==goal);replans+=1
        elif mode=="explore" and not route and actual!=goal:
            route=path_to(graph,actual,lambda s:s==goal);replans+=1
        events.append(dict(origin=origin,action=action,expected=expected,actual=actual,mismatch=mismatch))
    return dict(success=world.state==goal,steps=world.used,divergences=sum(e["mismatch"] for e in events),
                replans=replans,events=events)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in SEEDS:
        old,new,start,goal,edits=world(seed)
        for condition,table in (("stable",old),("changed",new)):
            for mode in MODES:
                result=solve(table if mode=="oracle" else old,World(table,start),goal,mode)
                row=dict(seed=seed,condition=condition,mode=mode,success=result["success"],steps=result["steps"],
                         divergences=result["divergences"],replans=result["replans"])
                rows.append(row)
                (out/f"{seed}_{condition}_{mode}.json").write_text(json.dumps(dict(result=row,start=start,goal=goal,
                    initial=[[s,a,t] for (s,a),t in sorted(old.items())],actual=[[s,a,t] for (s,a),t in sorted(table.items())],
                    edits=edits if condition=="changed" else [],events=result["events"]),indent=2),encoding="utf-8")
    agg=[dict(condition=c,mode=m,sessions=len(SEEDS),**{k:sum(r[k] for r in rows if r["condition"]==c and r["mode"]==m)
        for k in ("success","steps","divergences","replans")}) for c in ("stable","changed") for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V76-replanning-v1",aggregate=agg,by_seed=rows),indent=2),encoding="utf-8");print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_stable(self):
        old,new,s,t,edits=world(SEEDS[0])
        for m in MODES:self.assertTrue(solve(old,World(old,s),t,m)["success"])
    def test_revision(self):
        old={(s,a):s for s in range(N) for a in ACTIONS};old[0,0]=1;old[2,1]=1
        new=dict(old);new[0,0]=2
        self.assertFalse(solve(old,World(new,0),1,"frozen")["success"])
        self.assertTrue(solve(old,World(new,0),1,"replan")["success"])
    def test_budget(self):
        g={(s,a):s for s in range(N) for a in ACTIONS}
        self.assertLessEqual(solve(g,World(g,0),1,"explore")["steps"],CAP)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V76 required")
    run(a.output.resolve())
if __name__=="__main__":main()
