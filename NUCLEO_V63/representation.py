"""Fixed expanded grammar in finite simulated environments."""
import argparse,itertools,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V62"))
from revision import N,ACTIONS,order,unique_best,predict,plans,evaluate,write,summarize
SEEDS=tuple(8200017+30001*i for i in range(16))
STRATA=("affine","quadratic","outside")
MODES=("affine","expanded","map")
AFFINE=tuple((0,a,b) for a in range(N) for b in range(N))
EXPANDED=tuple(itertools.product(range(N),repeat=3))
def polynomial(h,s):return (h[0]*s*s+h[1]*s+h[2])%N

class Model:
    def __init__(self,mode):
        self.mode=mode;self.observed={a:{} for a in ACTIONS};self.models={a:None for a in ACTIONS}
        self.candidates=0;self.events=[]
    def observe(self,a,s,t):
        obs=self.observed[a]
        if s in obs or len(obs)>=10:raise ValueError("query")
        obs[s]=t;self.events.append([a,s,t])
        if len(obs)!=10 or self.mode=="map":return
        family=AFFINE if self.mode=="affine" else EXPANDED
        self.candidates+=len(family)
        pairs=list(obs.items())
        h,n=unique_best(family,pairs[:6],6,polynomial)
        if h is not None and all(polynomial(h,s)==t for s,t in pairs[6:]):self.models[a]=h
    def belief(self,a,s):
        if s in self.observed[a]:return self.observed[a][s],"observed"
        h=self.models[a]
        return (None,"unknown") if h is None else (polynomial(h,s),"inferred")
    def graph(self):
        return {(s,a):p for a in ACTIONS for s in range(N) for p,_ in (self.belief(a,s),) if p is not None}

def world(seed,stratum):
    rng=random.Random(seed)
    rules={a:(rng.randrange(1,N),rng.randrange(N),rng.randrange(N)) for a in ACTIONS}
    if stratum=="affine":rules={a:(0,h[1],h[2]) for a,h in rules.items()}
    table={(s,a):polynomial(rules[a],s) for a in ACTIONS for s in range(N)}
    changed=[]
    if stratum=="outside":
        for a in ACTIONS:
            for s in rng.sample(range(N),3):
                table[s,a]=(table[s,a]+rng.randrange(1,N))%N;changed.append((s,a))
    return table,rules,changed

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        goals=random.Random(seed^0x6302).sample([(s,t) for s in range(N) for t in range(N) if s!=t],12)
        for k in STRATA:
            table,rules,changed=world(seed,k)
            for mode in MODES:
                m=Model(mode)
                for a in ACTIONS:
                    for s in order(seed,a):m.observe(a,s,table[s,a])
                held={(s,a) for s in range(N) for a in ACTIONS if s not in m.observed[a]}
                hm,hr=evaluate(m,table,held);pm,pr=plans(m,table,goals)
                row=dict(seed=seed,stratum=k,mode=mode,held=hm,plans=pm,queries=len(m.events),candidates=m.candidates)
                results.append(row)
                write(out/f"{seed}_{k}_{mode}.json",dict(result=row,rules=rules,changed=changed,observations=m.events,
                    models=m.models,held=hr,plans=pr))
    summary=dict(protocol="V63-representation-v1",aggregate=summarize(results,STRATA,MODES,"stratum"),by_seed=results)
    write(out/"summary.json",summary);print(json.dumps(summary["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_quadratic(self):
        for mode in MODES:
            m=Model(mode)
            for s in range(10):m.observe(0,s,polynomial((2,3,4),s))
            self.assertEqual(m.belief(0,10)[0],polynomial((2,3,4),10) if mode=="expanded" else None)
    def test_audit(self):
        m=Model("expanded")
        for s in range(10):m.observe(0,s,(polynomial((2,3,4),s)+(s==8))%N)
        self.assertIsNone(m.belief(0,10)[0])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V63 required")
    run(a.output.resolve())
if __name__=="__main__":main()
