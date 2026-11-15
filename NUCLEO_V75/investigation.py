"""Budgeted investigation of fixed modular polynomial families."""
import argparse,json,random,sys,unittest
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V65"))
from transfer import N,predict,interpolate
SEEDS=tuple(26000019+30001*i for i in range(24))
TRAIN=tuple(27000019+30001*i for i in range(12))
MODES=("sequential","round","return")
CAP=30
FAMILIES=(1,2,3)

def probe(points,degree):
    h=interpolate(points,degree)
    if degree>1 and not h[-1]:return None
    return h if all(predict(h,s)==t for s,t in points) else None

def tasks(seed):
    rng=random.Random(seed);degrees=[1,2,3]*5;rng.shuffle(degrees);result=[]
    for d in degrees:
        h=tuple(rng.randrange(N) for _ in range(d))+(rng.randrange(1,N),)
        xs=rng.sample(range(N),10)
        result.append(dict(points=[(s,predict(h,s)) for s in xs],held=[(s,predict(h,s)) for s in range(N) if s not in xs],degree=d))
    return result

def train():
    counts=Counter();hits=Counter()
    for seed in TRAIN:
        for t in tasks(seed):
            for d in FAMILIES:
                counts[d]+=1
                if probe(t["points"],d) is not None:hits[d]+=1;break
    return {d:(hits[d]+1)/(counts[d]+2) for d in FAMILIES}

def allocate(points,mode,prob,cap=CAP):
    if mode not in MODES or not 0<=cap<=CAP:raise ValueError("budget/mode")
    states=[dict(tried=[],model=None) for _ in points];events=[]
    while len(events)<cap:
        ready=[i for i,s in enumerate(states) if s["model"] is None and len(s["tried"])<3]
        if not ready:break
        if mode=="sequential":i=min(ready)
        elif mode=="round":i=min(ready,key=lambda i:(len(states[i]["tried"]),i))
        else:i=min(ready,key=lambda i:(-prob[len(states[i]["tried"])+1],len(states[i]["tried"]),i))
        st=states[i];d=len(st["tried"])+1;st["tried"].append(d);st["model"]=probe(points[i],d)
        events.append(dict(task=i,family=d,accepted=st["model"] is not None))
    return states,events

def score(task,h):
    pairs=[(None if h is None else predict(h,s),t) for s,t in task["held"]]
    c=sum(p==t for p,t in pairs);w=sum(p is not None and p!=t for p,t in pairs)
    return dict(correct=c,wrong=w,abstained=len(pairs)-c-w)

def run(out):
    out.mkdir(parents=True,exist_ok=False);prob=train();rows=[]
    for seed in SEEDS:
        ts=tasks(seed)
        for mode in MODES:
            states,events=allocate([t["points"] for t in ts],mode,prob)
            scores=[score(t,s["model"]) for t,s in zip(ts,states)]
            row=dict(seed=seed,mode=mode,spent=len(events),solved=sum(s["model"] is not None for s in states),
                     **{k:sum(s[k] for s in scores) for k in ("correct","wrong","abstained")},
                     coverage={str(d):sum(s["model"] is not None for t,s in zip(ts,states) if t["degree"]==d) for d in FAMILIES})
            rows.append(row)
            (out/f"{seed}_{mode}.json").write_text(json.dumps(dict(result=row,tasks=ts,states=states,events=events,scores=scores),indent=2),encoding="utf-8")
    agg=[dict(mode=m,**{k:sum(r[k] for r in rows if r["mode"]==m) for k in ("spent","solved","correct","wrong","abstained")},
              coverage={str(d):sum(r["coverage"][str(d)] for r in rows if r["mode"]==m) for d in FAMILIES}) for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V75-investigation-v1",probabilities=prob,aggregate=agg,by_seed=rows),indent=2),encoding="utf-8");print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_budget(self):
        data=[t["points"] for t in tasks(SEEDS[0])]
        for m in MODES:
            st,ev=allocate(data,m,{1:.3,2:.5,3:1},7)
            self.assertEqual(len(ev),7);self.assertEqual(sum(len(s["tried"]) for s in st),7)
    def test_probe(self):
        p=[(s,predict((1,2,3),s)) for s in range(10)]
        self.assertIsNone(probe(p,1));self.assertEqual(probe(p,2),(1,2,3))
    def test_split(self):self.assertFalse(set(SEEDS)&set(TRAIN))
def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V75 required")
    run(a.output.resolve())
if __name__=="__main__":main()
