"""Declarative goal decomposition; simulated tasks only."""
import argparse,json,random,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=tuple(25000019+30001*i for i in range(24))
MODES=("random","all","closure")

def closure(catalog,goals):
    visiting=set();done=set();order=[]
    def visit(node):
        if node not in catalog:raise ValueError("unknown dependency")
        if node in visiting:raise ValueError("dependency cycle")
        if node in done:return
        visiting.add(node)
        for p in sorted(catalog[node]):visit(p)
        visiting.remove(node);done.add(node);order.append(node)
    for g in sorted(goals):visit(g)
    return order

def catalog(seed,n=18):
    rng=random.Random(seed)
    return {i:tuple(sorted(rng.sample(list(range(i)),rng.randint(1,min(3,i))))) if i>=4 else () for i in range(n)}

def schedule(graph,goals,budget,mode,seed):
    if mode not in MODES or budget<0:raise ValueError("mode/budget")
    required=closure(graph,goals);full=closure(graph,graph)
    order=required if mode=="closure" else full
    done=set();events=[];rng=random.Random(seed)
    while len(events)<budget and not set(goals)<=done:
        options=[i for i in order if i not in done and set(graph[i])<=done]
        if not options:break
        i=rng.choice(options) if mode=="random" else options[0]
        done.add(i);events.append(i)
    return dict(goals=len(goals),complete=sum(g in done for g in goals),executed=len(events),
                irrelevant=sum(i not in required for i in events),violations=0,
                abstained=sum(g not in done for g in goals),events=events,required=required)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in SEEDS:
        g=catalog(seed);goals=random.Random(seed^0x7401).sample(range(10,18),4)
        for mode in MODES:
            r=schedule(g,goals,18,mode,seed^0x7402)
            rows.append(dict(seed=seed,mode=mode,catalog=g,targets=goals,**r))
    metrics=("goals","complete","executed","irrelevant","violations","abstained")
    agg=[dict(mode=m,**{k:sum(r[k] for r in rows if r["mode"]==m) for k in metrics}) for m in MODES]
    result=dict(protocol="V74-decomposition-v1",aggregate=agg,by_seed=rows)
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_closure(self):
        g={0:(),1:(0,),2:(0,),3:(1,2),4:()}
        self.assertEqual(closure(g,[3]),[0,1,2,3])
        self.assertEqual(schedule(g,[3],4,"closure",1)["events"],[0,1,2,3])
    def test_invalid(self):
        for g in ({0:(0,)},{0:(1,)}):
            with self.assertRaises(ValueError):closure(g,[0])
    def test_budget(self):
        r=schedule({0:(),1:(0,)},[1],1,"closure",1)
        self.assertEqual(r["complete"],0);self.assertEqual(r["executed"],1)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V74 required")
    run(a.output.resolve())
if __name__=="__main__":main()
