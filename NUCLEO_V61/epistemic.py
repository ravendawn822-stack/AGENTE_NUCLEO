"""Audit a fixed candidate rule with bounded simulated observations."""
import argparse,json,math,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V60"))
from rule_discovery import N,ACTIONS,HYPOTHESES,predict,path_to
SEEDS=tuple(7980017+30001*i for i in range(24))
MODES=("deterministic6","audit6","audit10","map6")
STRATA=(0,1,3)

def upper_bad(population,sample):
    if not 0<sample<=population:raise ValueError("sample")
    denominator=math.comb(population,sample)
    return max(k for k in range(population+1)
        if 20*(math.comb(population-k,sample) if population-k>=sample else 0)>=denominator)

class RuleMemory:
    def __init__(self,mode):
        if mode not in MODES:raise ValueError("mode")
        self.mode=mode
        self.observed={a:{} for a in ACTIONS}
        self.candidates={a:None for a in ACTIONS}
        self.contradicted={a:False for a in ACTIONS}
        self.events=[]
    def observe(self,a,s,t):
        if a not in ACTIONS or type(s) is not int or type(t) is not int or not 0<=s<N or not 0<=t<N:raise ValueError("observation")
        known=self.observed[a]
        if s in known or len(known)>=(10 if self.mode=="audit10" else 6):raise ValueError("query")
        if len(known)<2 and s!=len(known):raise ValueError("fit inputs")
        known[s]=t
        if len(known)==2:
            compatible=[h for h in HYPOTHESES if all(predict(h,x)==y for x,y in known.items())]
            if len(compatible)!=1:raise RuntimeError("fit not unique")
            self.candidates[a]=compatible[0]
        elif len(known)>2 and predict(self.candidates[a],s)!=t:
            self.contradicted[a]=True
        self.events.append(dict(action=a,state=s,target=t,phase="fit" if len(known)<=2 else "audit",
                                contradicted=self.contradicted[a]))
    def belief(self,a,s):
        if s in self.observed[a]:return self.observed[a][s],"observed"
        if self.mode=="map6":return None,"unknown"
        if self.contradicted[a]:return None,"contradicted"
        required=10 if self.mode=="audit10" else 6
        if len(self.observed[a])<required:return None,"unknown"
        return predict(self.candidates[a],s),"inferred"
    def bounds(self,a):
        if self.mode not in ("audit6","audit10") or self.contradicted[a]:return None
        n=len(self.observed[a])-2
        if n!=(8 if self.mode=="audit10" else 4):return None
        return upper_bad(N-2,n)
    def graph(self):
        return {(s,a):p for a in ACTIONS for s in range(N)
                for p,status in (self.belief(a,s),) if p is not None}

class Sim:
    def __init__(self,table,limit):
        self.__table=table;self.limit=limit;self.used={a:0 for a in ACTIONS}
    def query(self,a,s):
        if a not in ACTIONS or not 0<=s<N or self.used[a]>=self.limit:raise ValueError("budget")
        self.used[a]+=1
        return self.__table[s,a]

def world(seed,exceptions):
    rng=random.Random(seed)
    rules={a:(rng.randrange(N),rng.randrange(N)) for a in ACTIONS}
    table={(s,a):predict(rules[a],s) for s in range(N) for a in ACTIONS}
    changed=[]
    for a in ACTIONS:
        edits=[(s,rng.randrange(1,N)) for s in rng.sample(range(N),3)]
        for s,delta in edits[:exceptions]:
            table[s,a]=(table[s,a]+delta)%N;changed.append((s,a))
    return table,rules,changed

def query_order(seed,a,mode):
    rest=list(range(2,N))
    if mode!="deterministic6":random.Random(seed^(0x610000+a)).shuffle(rest)
    return [0,1]+rest[:8 if mode=="audit10" else 4]

def train(table,seed,mode):
    memory=RuleMemory(mode);sim=Sim(table,10 if mode=="audit10" else 6)
    for a in ACTIONS:
        for s in query_order(seed,a,mode):memory.observe(a,s,sim.query(a,s))
    return memory

def unseen(memory):
    return {(s,a) for a in ACTIONS for s in range(N) if s not in memory.observed[a]}

def evaluate(memory,table,held):
    rows=[]
    for s,a in sorted(held):
        p,status=memory.belief(a,s);target=table[s,a]
        rows.append(dict(state=s,action=a,prediction=p,evidence=status,target=target))
    return dict(n=len(rows),correct=sum(x["prediction"]==x["target"] for x in rows),
                wrong=sum(x["prediction"] is not None and x["prediction"]!=x["target"] for x in rows),
                abstained=sum(x["prediction"] is None for x in rows)),rows

def plans(memory,table,goals):
    graph=memory.graph();rows=[]
    for s,t in goals:
        route=path_to(graph,s,lambda x:x==t)
        state=s;contradictions=0
        if route is not None:
            if len(route)>N:raise RuntimeError("plan bound")
            for a in route:
                predicted,status=memory.belief(a,state)
                actual=table[state,a]
                contradictions+=predicted!=actual
                state=actual
        rows.append(dict(start=s,goal=t,route=route,success=route is not None and state==t,
                         wrong=route is not None and state!=t,abstained=route is None,step_mismatches=contradictions))
    return dict(n=len(rows),success=sum(r["success"] for r in rows),wrong=sum(r["wrong"] for r in rows),
                abstained=sum(r["abstained"] for r in rows),step_mismatches=sum(r["step_mismatches"] for r in rows)),rows

def write(path,data):
    path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        goals=random.Random(seed^0x6102).sample([(s,t) for s in range(N) for t in range(N) if s!=t],12)
        for exceptions in STRATA:
            table,rules,changed=world(seed,exceptions)
            memories={mode:train(table,seed,mode) for mode in MODES}
            common=set.intersection(*(unseen(memories[x]) for x in ("deterministic6","audit6","map6")))
            nested=unseen(memories["audit10"])
            for mode,mem in memories.items():
                own,own_rows=evaluate(mem,table,unseen(mem))
                same,same_rows=evaluate(mem,table,common) if mode!="audit10" else (None,[])
                pair,pair_rows=evaluate(mem,table,nested) if mode in ("audit6","audit10") else (None,[])
                plan,plan_rows=plans(mem,table,goals)
                row=dict(seed=seed,exceptions=exceptions,mode=mode,own=own,common6=same,nested=pair,
                         plans=plan,queries=len(mem.events),contradicted=sum(mem.contradicted.values()),
                         bounds=[mem.bounds(a) for a in ACTIONS])
                results.append(row)
                write(out/f"{seed}_{exceptions}_{mode}.json",dict(result=row,rules=rules,changed=changed,
                    observations=mem.events,own=own_rows,common6=same_rows,nested=pair_rows,plans=plan_rows))
    aggregate=[]
    for exceptions in STRATA:
        for mode in MODES:
            r=[x for x in results if x["exceptions"]==exceptions and x["mode"]==mode]
            def total(key):
                entries=[x[key] for x in r if x[key] is not None]
                return {k:sum(x[k] for x in entries) for k in entries[0]} if entries else None
            aggregate.append(dict(exceptions=exceptions,mode=mode,queries=sum(x["queries"] for x in r),
                contradicted=sum(x["contradicted"] for x in r),own=total("own"),common6=total("common6"),
                nested=total("nested"),plans=total("plans")))
    write(out/"summary.json",dict(protocol="V61-epistemic-audit-v1",seeds=SEEDS,
        bound_audit6=upper_bad(15,4),bound_audit10=upper_bad(15,8),aggregate=aggregate,by_seed=results))
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_belief(self):
        m=RuleMemory("audit6")
        m.observe(0,0,4);m.observe(0,1,7)
        self.assertEqual(m.belief(0,8),(None,"unknown"))
        for s in (2,3,4,5):m.observe(0,s,predict((3,4),s))
        self.assertEqual(m.belief(0,8),(11,"inferred"))
        self.assertEqual(m.belief(0,1),(7,"observed"))
        self.assertEqual(m.bounds(0),upper_bad(15,4))
    def test_contradiction(self):
        m=RuleMemory("audit6")
        m.observe(0,0,4);m.observe(0,1,7);m.observe(0,2,11)
        self.assertEqual(m.belief(0,8),(None,"contradicted"))
        self.assertEqual(m.belief(0,2),(11,"observed"))
        self.assertIsNone(m.bounds(0))
    def test_bound(self):
        for n in (4,8):
            k=upper_bad(15,n);d=math.comb(15,n)
            self.assertGreaterEqual(20*math.comb(15-k,n),d)
            self.assertLess(20*(math.comb(14-k,n) if 14-k>=n else 0),d)
    def test_prefix(self):
        for seed in SEEDS:
            for a in ACTIONS:
                self.assertEqual(query_order(seed,a,"audit6"),query_order(seed,a,"audit10")[:6])
                self.assertEqual(query_order(seed,a,"audit6"),query_order(seed,a,"map6"))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V61 required")
    run(a.output.resolve())
if __name__=="__main__":main()
