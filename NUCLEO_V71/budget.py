"""Finite budget allocation, no external actions."""
import argparse,json,random,sys,unittest
from collections import Counter,deque
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V65"))
from transfer import N,predict,interpolate
TRAIN=tuple(17000019+30001*i for i in range(10))
TEST=tuple(16000019+30001*i for i in range(20))
MODES=("uniform","sequential","adaptive")
BUDGET=32
FAMILIES=(1,2,3)

def tasks(seed):
    rng=random.Random(seed);degrees=[1]*10+[2]*6+[3]*4;rng.shuffle(degrees)
    out=[]
    for degree in degrees:
        h=tuple(rng.randrange(N) for _ in range(degree))+(rng.randrange(1,N),)
        xs=rng.sample(range(N),6)
        out.append(dict(degree=degree,points=[(s,predict(h,s)) for s in xs],
            held=[(s,predict(h,s)) for s in range(N) if s not in xs]))
    return out

def probe(points,degree):
    h=interpolate(points[:4],degree)
    if degree>1 and h[-1]==0:return None
    return h if all(predict(h,s)==t for s,t in points) else None

def train():
    counts=Counter()
    for seed in TRAIN:
        for task in tasks(seed):
            p=task["points"]
            if probe(p,1) is None:
                for d in (2,3):counts[d]+=probe(p,d) is not None
    return tuple(sorted((2,3),key=lambda d:(-counts[d],d))),dict(counts)

def allocate(points,mode,priority,budget=BUDGET):
    if mode not in MODES or not 0<=budget<=BUDGET:raise ValueError("budget")
    order=(1,*priority) if mode=="adaptive" else FAMILIES
    states=[dict(tried=[],model=None) for _ in points];events=[]
    def spend(i):
        state=states[i]
        degree=order[len(state["tried"])]
        state["tried"].append(degree)
        state["model"]=probe(points[i],degree)
        events.append(dict(task=i,degree=degree,success=state["model"] is not None))
    if mode=="sequential":
        for i in range(len(points)):
            while len(events)<budget and states[i]["model"] is None and len(states[i]["tried"])<3:spend(i)
    else:
        queue=deque(range(len(points)));limit=2 if mode=="uniform" else 3
        while queue and len(events)<budget:
            i=queue.popleft();spend(i)
            if states[i]["model"] is None and len(states[i]["tried"])<limit:queue.append(i)
    return states,events

def run(out):
    out.mkdir(parents=True,exist_ok=False);priority,counts=train();records=[]
    for seed in TEST:
        data=tasks(seed)
        for mode in MODES:
            states,events=allocate([t["points"] for t in data],mode,priority)
            rows=[]
            for task,st in zip(data,states):
                h=st["model"];pairs=[(predict(h,s) if h is not None else None,t) for s,t in task["held"]]
                rows.append(dict(degree=task["degree"],tried=st["tried"],solved=h is not None,
                    correct=sum(p==t for p,t in pairs),wrong=sum(p is not None and p!=t for p,t in pairs),
                    abstained=sum(p is None for p,t in pairs)))
            row=dict(seed=seed,mode=mode,spent=len(events),solved=sum(r["solved"] for r in rows),
                **{k:sum(r[k] for r in rows) for k in ("correct","wrong","abstained")},
                coverage={str(d):sum(r["solved"] for r in rows if r["degree"]==d) for d in FAMILIES})
            records.append(row)
            (out/f"{seed}_{mode}.json").write_text(json.dumps(dict(result=row,tasks=data,events=events,rows=rows),indent=2),encoding="utf-8")
    aggregate=[dict(mode=m,**{k:sum(r[k] for r in records if r["mode"]==m) for k in ("spent","solved","correct","wrong","abstained")},
        coverage={str(d):sum(r["coverage"][str(d)] for r in records if r["mode"]==m) for d in FAMILIES}) for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V71-budget-v1",priority=priority,training_counts=counts,aggregate=aggregate,by_seed=records),indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_budget(self):
        points=[t["points"] for t in tasks(TEST[0])]
        for mode in MODES:
            states,events=allocate(points,mode,(2,3),5)
            self.assertEqual(len(events),5);self.assertEqual(sum(len(s["tried"]) for s in states),5)
    def test_probe(self):
        p=[(s,predict((1,2,3),s)) for s in range(6)]
        self.assertIsNone(probe(p,1));self.assertEqual(probe(p,2),(1,2,3))
    def test_split(self):self.assertFalse(set(TRAIN)&set(TEST))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V71 required")
    run(a.output.resolve())
if __name__=="__main__":main()
