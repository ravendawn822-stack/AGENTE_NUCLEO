"""Frozen context-conditioned strategy selector in a bounded simulator."""
import argparse,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V67"))
from self_estimate import features
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V62"))
from revision import Revised,N,ACTIONS,world,train,write
TRAIN=tuple(14000019+30001*i for i in range(32))
TEST=tuple(15000019+30001*i for i in range(24))
STRATA=(0,1,3)
OPTIONS=("exact","repair","map")
MODES=OPTIONS+("selector",)

def context(exact,repair,a):
    f=features(repair,a)
    return (exact.models[a] is not None, None if f is None else f[1:])

def outcomes(memory,a,held):
    predictions=[memory.belief(a,s)[0] for s,t in held]
    correct=sum(p==t for p,(s,t) in zip(predictions,held))
    wrong=sum(p is not None and p!=t for p,(s,t) in zip(predictions,held))
    return dict(correct=correct,wrong=wrong,abstained=len(held)-correct-wrong,utility=correct-4*wrong)

class Selector:
    def __init__(self):self.history={};self.frozen=False
    def learn(self,key,results):
        if self.frozen:raise RuntimeError("frozen")
        for mode in OPTIONS:
            k=str((key,mode));n,u=self.history.get(k,(0,0))
            self.history[k]=(n+1,u+results[mode]["utility"]/7)
    def freeze(self):self.frozen=True
    def choose(self,key):
        if not self.frozen:raise RuntimeError("not frozen")
        scores={}
        for mode in OPTIONS:
            n,u=self.history.get(str((key,mode)),(0,0));scores[mode]=u/(n+2)
        choice=max(OPTIONS,key=lambda m:scores[m])
        return (choice if scores[choice]>0 else "map"),scores

def samples(seeds):
    for seed in seeds:
        for k in STRATA:
            table,_,_=world(seed,k);models={m:train(table,seed,m) for m in OPTIONS}
            for a in ACTIONS:
                held=[(s,table[s,a]) for s in range(N) if s not in models["exact"].observed[a]]
                yield dict(seed=seed,exceptions=k,action=a,key=context(models["exact"],models["repair"],a),
                    models={m:models[m].models[a] for m in OPTIONS},results={m:outcomes(models[m],a,held) for m in OPTIONS})

def trained():
    selector=Selector();training=list(samples(TRAIN))
    for row in training:selector.learn(row["key"],row["results"])
    selector.freeze();return selector,training

def run(out):
    out.mkdir(parents=True,exist_ok=False);selector,training=trained();rows=[]
    for r in samples(TEST):
        choice,scores=selector.choose(r["key"]);r["choice"]=choice;r["scores"]=scores
        r["results"]["selector"]=r["results"][choice];rows.append(r)
    def agg(rs,mode):
        return dict(rules=len(rs),**{k:sum(r["results"][mode][k] for r in rs)
            for k in ("correct","wrong","abstained","utility")},
            model_fits=len(rs)*(2 if mode=="selector" else 0 if mode=="map" else 1))
    summary=dict(protocol="V70-strategy-v1",aggregate=[dict(mode=m,**agg(rows,m)) for m in MODES],
        by_stratum=[dict(exceptions=k,mode=m,**agg([r for r in rows if r["exceptions"]==k],m)) for k in STRATA for m in MODES],
        choices={m:sum(r["choice"]==m for r in rows) for m in OPTIONS},history=selector.history)
    write(out/"training.json",training);write(out/"test.json",rows);write(out/"summary.json",summary)
    print(json.dumps(summary["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_choice(self):
        s=Selector();key=(False,(5,4));s.learn(key,{"exact":{"utility":0},"repair":{"utility":7},"map":{"utility":0}});s.freeze()
        self.assertEqual(s.choose(key)[0],"repair");self.assertEqual(s.choose((False,None))[0],"map")
        with self.assertRaises(RuntimeError):s.learn(key,{})
    def test_split(self):self.assertFalse(set(TRAIN)&set(TEST))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V70 required")
    run(a.output.resolve())
if __name__=="__main__":main()
