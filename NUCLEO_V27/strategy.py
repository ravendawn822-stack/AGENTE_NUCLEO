"""V27: select a bounded investigation strategy from measured development results."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V24"))
import reuse as m
v=m.v
SEEDS=(3960017,3990023,4020031,4050041)
RECIPES=tuple(itertools.product(("pairs","minimax","fixed"),("fixed","distance","random")))
BASE=("pairs","fixed")
CAP=v.CAP
def suite(seed,points):
    rng=random.Random(seed^0x2717);seen=set();excluded={m.sig((),points)};dev=[];final=[]
    for length in range(1,5):
        options=list(itertools.product(v.OPS,repeat=length));rng.shuffle(options)
        current=set();selected=[]
        for p in options:
            s=m.sig(p,points)
            if s in excluded or s in current:continue
            current.add(s)
            if len(selected)<16:selected.append(p)
            if length==4 and len(selected)==16:break
        assert len(selected)==16 or (length==1 and len(selected)==12)
        if length==1:
            # The DSL only has 12 nonidentity primitives. Use disjoint 6+6.
            n=6
        else:n=8
        for dest,phase,subset in ((dev,"dev",selected[:n]),(final,"final",selected[n:2*n])):
            for p in subset:
                s=m.sig(p,points);assert s not in seen;seen.add(s)
                dest.append(dict(id=f"{seed}/{phase}/{len(dest)}",length=length,program=p))
        excluded.update(current)
    rng.shuffle(dev);rng.shuffle(final)
    return dev,final

def distance(x,y):
    return 7*abs(len(x)-len(y))+sum(abs(a-b) for a,b in zip(x,y))

def solve(observed,initial,pool,ask,recipe,prepared,seed):
    evidence=list(initial);width=len(observed);expected=tuple(observed)
    candidates=[(p,s) for p,s in prepared if s[:width]==expected]
    cost=len(prepared)*width;trace=[];remaining=list(range(len(pool)))
    rng=random.Random(seed)
    identify,verify=recipe
    for _ in range(CAP):
        if not candidates:break
        if len(candidates)==1:
            if verify=="random":i=rng.choice(remaining)
            elif verify=="distance":
                def score(j):return min(distance(pool[j],x) for x in evidence)
                i=max(remaining,key=score)
            else:i=remaining[0]
        elif identify=="fixed":i=remaining[0]
        else:
            best=None;i=None
            for j in remaining:
                counts={}
                for _,s in candidates:
                    pred=s[width+j];counts[pred]=counts.get(pred,0)+1;cost+=1
                score=(len(candidates)**2-sum(k*k for k in counts.values())) if identify=="pairs" else -max(counts.values())
                if best is None or score>best:best,i=score,j
        remaining.remove(i);x=pool[i];y=tuple(ask(x))
        evidence.append(x);before=len(candidates)
        candidates=[(p,s) for p,s in candidates if s[width+i]==y]
        cost+=before
        trace.append(dict(input=x,output=y,before=before,after=len(candidates)))
    return (candidates[0][0] if len(candidates)==1 else None),trace,cost

def episode(t,initial,pool,held,recipe,prepared,seed,policy):
    target=t["program"];obs=m.sig(target,initial)
    start=time.perf_counter_ns()
    p,trace,cost=solve(obs,initial,pool,lambda x:m.execute_target(target,x),recipe,prepared,seed)
    elapsed=time.perf_counter_ns()-start
    return dict(task=t,policy=policy,recipe=recipe,program=p,emitted=p is not None,
        success=p is not None and m.sig(p,held)==m.sig(target,held),
        queries=len(trace),trace=trace,comparisons=cost,wall_ns=elapsed)

def metrics(rows):
    correct=sum(r["success"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    queries=sum(r["queries"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
        queries=queries,comparisons=sum(r["comparisons"] for r in rows),
        wall_ns=sum(r["wall_ns"] for r in rows),score=100*correct-200*(emitted-correct)-queries)

def select(rows):
    scores=[dict(recipe=p,**metrics([r for r in rows if r["recipe"]==p])) for p in RECIPES]
    best=min(scores,key=lambda x:(-x["score"],x["comparisons"],x["recipe"]))
    return best["recipe"],scores

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];development=[];decisions=[];preparation=[]
    labels=("selected","original","fixed","random",*("recipe:"+"/".join(p) for p in RECIPES))
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed)
        dev,final=suite(seed,(*initial,*pool,*held))
        start=time.perf_counter_ns();prepared,n=v.prepare(m.FULL3,initial,pool)
        preparation.append(dict(seed=seed,programs=len(m.FULL3),classes=len(prepared),executions=n,wall_ns=time.perf_counter_ns()-start))
        local=[]
        for i,t in enumerate(dev):
            for recipe in RECIPES:local.append(dict(seed=seed,**episode(t,initial,pool,held,recipe,prepared,seed+i*701,"development")))
        selected,scores=select(local)
        decision=dict(seed=seed,recipe=selected,scores=scores,development_sha=m.digest(local))
        decision["sha"]=m.digest(decision);path=out/f"decision_{seed}.json"
        path.write_text(m.enc(decision),encoding="utf-8")
        loaded=json.loads(path.read_text());sha=loaded.pop("sha")
        assert m.digest(loaded)==sha
        chosen=tuple(loaded["recipe"]);assert chosen==selected
        decisions.append(decision);development.extend(local)
        for i,t in enumerate(final):
            recipe_map={"selected":chosen,"original":BASE,"fixed":("fixed","fixed"),
              "random":random.Random(seed+i*971).choice(RECIPES)}
            recipe_map.update({"recipe:"+"/".join(p):p for p in RECIPES})
            for label,recipe in recipe_map.items():
                rows.append(dict(seed=seed,**episode(t,initial,pool,held,recipe,prepared,seed+i*971,label)))
        assert json.loads(path.read_text())["sha"]==sha
    result=dict(protocol="V27-strategy-selection-v1",seeds=SEEDS,decisions=decisions,preparation=preparation,
        development=metrics(development),
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in labels],
        by_length=[dict(length=l,policy=p,**metrics([r for r in rows if r["policy"]==p and r["task"]["length"]==l])) for l in range(1,5) for p in labels],
        by_seed=[dict(seed=s,policy=p,**metrics([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in labels])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("development",development)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(m.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            a,b,c=v.input_sets(s);points=(*a,*b,*c);d,f=suite(s,points)
            self.assertEqual((len(d),len(f)),(30,30))
            self.assertEqual(len({m.sig(t["program"],points) for t in d+f}),60)
    def test_distance(self):
        self.assertEqual(distance((1,2),(1,2)),0)
        self.assertEqual(distance((1,),()),7)
    def test_bounds(self):
        a,b,c=v.input_sets(SEEDS[0]);pr,_=v.prepare(m.FULL3,a,b)
        p=("positive","sort");t=dict(program=p)
        for recipe in RECIPES:
            r=episode(t,a,b,c,recipe,pr,1,"test")
            pts=[x["input"] for x in r["trace"]]
            self.assertLessEqual(len(pts),CAP)
            self.assertEqual(len(pts),len(set(pts)))
            self.assertFalse(set(pts)&set(c))
            if r["program"] is not None:
                self.assertTrue(all(v.execute(r["program"],x)==v.execute(p,x) for x in (*a,*pts)))
    def test_baseline(self):
        a,b,c=v.input_sets(SEEDS[0]);pr,_=v.prepare(m.FULL3,a,b)
        p=("positive","sort","inc");obs=m.sig(p,a)
        old=v.investigate(obs,b,lambda x:v.execute(p,x),"full_active",pr,1)
        new=solve(obs,a,b,lambda x:v.execute(p,x),BASE,pr,1)
        # V23 evaluates all remaining predictions even for one candidate;
        # V27 directly selects the first remaining point in that state.
        self.assertEqual(old[:2],new[:2])
        expected_difference=sum(len(b)-i for i,row in enumerate(new[1]) if row["before"]==1)
        self.assertEqual(old[2]-new[2],expected_difference)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V27 required")
    run(z.output)
