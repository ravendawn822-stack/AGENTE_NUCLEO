"""Autonomous cycle inside a fixed, offline declarative simulator."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for v in (74,75,77):
    sys.path.insert(0,str(ROOT.parent/f"NUCLEO_V{v}"))
from decomposition import closure
from investigation import probe,score,N
import strategy_memory as memory
SEEDS=tuple(31000019+30001*i for i in range(24))
MODES=("all_fixed","closure_fixed","integrated")
CAP=18
GOALS=(8,9,10,11)

def scenario(seed,context,condition):
    rng=random.Random(seed^0x7801)
    # Four common foundation tasks, four intermediate tasks, four terminals.
    graph={i:() for i in range(4)}
    for i in range(4,8):graph[i]=tuple(sorted(rng.sample(range(4),2)))
    for i in GOALS:graph[i]=tuple(sorted(rng.sample(range(4,8),1+rng.randrange(2))))
    data=memory.tasks(seed,context)
    edits=[]
    if condition=="outside":
        for i in rng.sample(range(12),2):
            # Change three of the observed values. The six public observations
            # remain fixed inputs; no labels from the reserved set are exposed.
            points=list(data[i]["points"])
            changed=rng.sample(range(6),3)
            for j in changed:
                s,t=points[j];points[j]=(s,(t+rng.randrange(1,N))%N)
            data[i]=dict(data[i],points=points)
            edits.append(i)
    return graph,data,edits

class Cycle:
    def __init__(self,graph,goals,points,mode,context,counts,budget=CAP):
        if mode not in MODES or not 0<=budget<=CAP:raise ValueError("mode/budget")
        self.graph={i:tuple(p) for i,p in graph.items()}
        self.goals=tuple(goals);self.points=points;self.mode=mode;self.budget=budget
        self.required=closure(graph,goals)
        self.order=closure(graph,graph) if mode=="all_fixed" else self.required
        self.families=memory.priority(counts,context) if mode=="integrated" else (1,2,3)
        self.models={};self.failed=set();self.blocked=set();self.events=[];self.spent=0
        self.revisions=0
    def revise(self):
        before=set(self.blocked)
        # Propagate impossibility to every downstream task, never to siblings.
        for i in self.order:
            if i not in self.failed and any(p in self.failed or p in self.blocked for p in self.graph[i]):
                self.blocked.add(i)
        new=sorted(self.blocked-before)
        self.events.append(dict(type="revision" if self.mode=="integrated" else "blocked",
                                blocked=new,spent=self.spent))
        if self.mode=="integrated":self.revisions+=1
    def run(self):
        while self.spent<self.budget and not set(self.goals)<=self.models.keys():
            ready=[i for i in self.order if i not in self.models and i not in self.failed and i not in self.blocked
                   and all(p in self.models for p in self.graph[i])]
            if not ready:break
            i=ready[0]
            self.events.append(dict(type="goal_decomposition",task=i,requires=self.graph[i],spent=self.spent))
            accepted=False
            for d in self.families:
                if self.spent>=self.budget:break
                h=probe(self.points[i],d);self.spent+=1
                self.events.append(dict(type="investigate",task=i,family=d,accepted=h is not None,spent=self.spent))
                if h is not None:
                    self.models[i]=h;accepted=True;break
            if not accepted:
                if self.spent>=self.budget:
                    self.events.append(dict(type="budget_stop",task=i,spent=self.spent));break
                self.failed.add(i);self.revise()
        return self

def evaluate(cycle,data):
    rows=[]
    for i,t in enumerate(data):
        r=score(t,cycle.models.get(i))
        rows.append(dict(id=i,emitted=i in cycle.models,**r))
    goal_rows=[]
    for g in cycle.goals:
        dependencies=closure(cycle.graph,[g])
        emitted=all(i in cycle.models for i in dependencies)
        correct=emitted and all(rows[i]["wrong"]==0 for i in dependencies)
        goal_rows.append(dict(goal=g,status="correct" if correct else "wrong" if emitted else "incomplete"))
    return dict(goals=len(goal_rows),correct_goals=sum(r["status"]=="correct" for r in goal_rows),
        wrong_goals=sum(r["status"]=="wrong" for r in goal_rows),incomplete_goals=sum(r["status"]=="incomplete" for r in goal_rows),
        solved=len(cycle.models),spent=cycle.spent,blocked=len(cycle.blocked),failed=len(cycle.failed),revisions=cycle.revisions,
        irrelevant=sum(i not in cycle.required for i in cycle.models),
        wrong_predictions=sum(r["wrong"] for r in rows),correct_predictions=sum(r["correct"] for r in rows),
        abstained=sum(r["abstained"] for r in rows)),rows,goal_rows

def run(out):
    out.mkdir(parents=True,exist_ok=False);counts=memory.train()
    path=out/"strategy_memory.json";memory.save(path,counts);counts=memory.load(path);records=[]
    for seed in SEEDS:
        for context in memory.CONTEXTS:
            for condition in ("compatible","outside"):
                graph,data,edits=scenario(seed,context,condition)
                for mode in MODES:
                    cycle=Cycle(graph,GOALS,{i:t["points"] for i,t in enumerate(data)},mode,context,counts).run()
                    result,rows,goals=evaluate(cycle,data);row=dict(seed=seed,context=context,condition=condition,mode=mode,**result)
                    records.append(row)
                    (out/f"{seed}_{context}_{condition}_{mode}.json").write_text(json.dumps(dict(result=row,
                        graph=graph,data=data,edits=edits,required=cycle.required,models=cycle.models,
                        events=cycle.events,rows=rows,goals=goals),indent=2),encoding="utf-8")
    keys=("goals","correct_goals","wrong_goals","incomplete_goals","solved","spent","blocked","failed","revisions",
          "irrelevant","wrong_predictions","correct_predictions","abstained")
    agg=[dict(condition=c,mode=m,**{k:sum(r[k] for r in records if r["condition"]==c and r["mode"]==m)
              for k in keys}) for c in ("compatible","outside") for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V78-autonomous-cycle-v1",counts=counts,aggregate=agg,by_seed=records),indent=2),encoding="utf-8")
    print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_dependencies(self):
        graph={0:(),1:(0,),2:()};p=[(s,s) for s in range(6)]
        c=Cycle(graph,[1],{0:p,1:p,2:p},"integrated","A",{"A":(8,3,1),"B":(1,3,8)},2).run()
        self.assertEqual(set(c.models),{0,1});self.assertEqual(c.spent,2)
    def test_failure(self):
        graph={0:(),1:(0,),2:()};bad=[(s,pow(s,4,N)) for s in range(6)];p=[(s,s) for s in range(6)]
        c=Cycle(graph,[1,2],{0:bad,1:p,2:p},"integrated","A",{"A":(8,3,1),"B":(1,3,8)},5).run()
        self.assertIn(0,c.failed);self.assertIn(1,c.blocked);self.assertIn(2,c.models)
        self.assertEqual(c.revisions,1)
    def test_budget(self):
        g,d,_=scenario(SEEDS[0],"A","compatible")
        c=Cycle(g,GOALS,{i:t["points"] for i,t in enumerate(d)},"closure_fixed","A",{"A":(8,3,1),"B":(1,3,8)},1).run()
        self.assertEqual(c.spent,1)
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V78 required")
    run(a.output.resolve())
if __name__=="__main__":main()
