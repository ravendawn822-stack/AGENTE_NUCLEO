"""V8: synthesize new probes against live competing repair hypotheses.
Only trusted synthetic fixtures; bounded data, restricted AST interpreter.
"""
import argparse,ast,itertools,json,random,sys,time,unittest
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V7"))
import learn as v7
v6=v7.v6
SEEDS=(1710011,1740017,1770007)
POLICIES=("fixed_pool","random_guard","fresh_active","mutated_active")
QUERY_CAP=7
INITIAL_ROUNDS=3
BATCH=40
CAP=256
FIXTURES={
"bounded_fees":("""def solve(items):
    total = 0
    for x in items:
        if x > 37:
            total += x // 5
        else:
            total += 2
        if total > 83:
            total = 83
    return total
""",lambda z:fees(z)),
"alternating_delta":("""def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x > previous:
            total += x - previous
        else:
            total -= 2
        previous = x
    return total
""",lambda z:sum(x-p if x>p else -2 for p,x in zip((0,*z),z))),
"reserve_floor":("""def solve(items):
    total = 12
    for x in items:
        if x > 0:
            total -= x
        else:
            total += 3
        if total < 4:
            total = 4
    return total
""",lambda z:reserve(z)),
"residue_fee":("""def solve(items):
    total = 0
    for x in items:
        if x % 7 == 2:
            total += x + 3
        else:
            total += 1
    return total
""",lambda z:sum(x+3 if x%7==2 else 1 for x in z)),
"running_compare":("""def solve(items):
    total = 0
    for x in items:
        if x >= total:
            total += 4
        else:
            total -= 2
    return total
""",lambda z:running(z)),
"dual_threshold":("""def solve(items):
    total = 0
    for x in items:
        if x >= 61:
            total += 6
        if x < -17:
            total -= 3
    return total
""",lambda z:sum(6*(x>=61)-3*(x< -17) for x in z)),
}
def fees(z):
    a=0
    for x in z:a=min(83,a+(x//5 if x>37 else 2))
    return a
def reserve(z):
    a=12
    for x in z:a=max(4,a-x if x>0 else a+3)
    return a
def running(z):
    a=0
    for x in z:a+=4 if x>=a else -2
    return a

def reserved(seed):
    r=random.Random(seed)
    # disjoint by length from every permitted generated probe (0..6).
    result=[(x,)*8 for x in range(-110,111)]
    result.extend(tuple(r.randint(-200,200) for _ in range(r.randint(9,16))) for _ in range(30))
    result.extend(tuple(r.choice((-18,-17,-16,0,1,2,3,36,37,38,60,61,62,82,83,84)) for _ in range(10)) for _ in range(30))
    return list(dict.fromkeys(result))

def proposals(src,seed,phase):
    rng=random.Random(seed);rows=[]
    for name,(src,ref) in FIXTURES.items():
        t=v6.safe_tree(src);m=list(v6.mutations(t))
        edits=[];used=set()
        for _ in range(3):
            e=rng.choice([x for x in m if x[0] not in used]);used.add(e[0]);edits.append(e)
        for n in range(4):
            observed=ast.unparse(v6.patch(t,edits[:n]))+"\n"
            p=v7.input_pool(observed,seed);final=reserved(seed+91)
            assert all(len(z)<=6 for z in p)
            assert all(v6.safe_eval(t,z)==ref(z) for z in p+final)
            rows.append(dict(id=f"{seed}/{name}/{n}",fixture=name,mutations=n,edits=edits[:n],source=observed,pool=p,final=final,ref=ref))
    return rows

def values(src):
    cs={n.value for n in ast.walk(v6.safe_tree(src)) if isinstance(n,ast.Constant)}
    return sorted({-128,-32,-8,-2,-1,0,1,2,8,32,128}|{v+d for v in cs for d in (-2,-1,0,1,2)})

def fresh(rng,vals):
    n=rng.randint(1,6)
    return tuple(rng.choice(vals) if rng.random()<.85 else rng.randint(-160,160) for _ in range(n))

def mutate(rng,z,vals):
    z=list(z) or [rng.choice(vals)];i=rng.randrange(len(z));op=rng.randrange(6)
    if op==0:z[i]=rng.choice(vals)
    elif op==1:z[i]=max(-200,min(200,z[i]+rng.choice((-3,-2,-1,1,2,3))))
    elif op==2:z.reverse()
    elif op==3 and len(z)<6:z.insert(i,rng.choice(vals))
    elif op==4 and len(z)>1:z.pop(i)
    else:z[i]=-z[i]
    return tuple(z)

def diversity(vals):
    c=Counter(vals);n=len(vals)
    if not n:return (0,0.)
    return len(c),1-sum((k/n)**2 for k in c.values())

class World:
    def __init__(self,case):
        self.case=case;self.pool=tuple(case["pool"])
        start=time.perf_counter_ns()
        session=v7.previous.Session(case["source"],self.pool)
        self.trees=[t for _,t,_ in session.candidates];self.edits=[e for e,_,_ in session.candidates]
        self.initial=tuple(s for _,_,s in session.candidates);self.generated=session.generated
        self.build_ns=time.perf_counter_ns()-start
    def oracle(self,z):return self.case["ref"](z)
    def validate(self,i):
        return all(v6.safe_eval(self.trees[i],z)==self.case["ref"](z) for z in self.case["final"])

def investigate(world,policy,seed):
    start=time.perf_counter_ns()
    rng=random.Random(seed);pool=world.pool;vals=values(world.case["source"])
    remain=tuple(range(len(world.trees)));asked=set();trace=[];local={};parents=[];work=0;novel=0
    # Known pool prediction vectors are shared equally, but novel predictions are policy-local.
    def original_classes():
        return {world.initial[i] for i in remain}
    def prediction(z):
        nonlocal work
        cache=local.setdefault(z,{})
        for i in remain:
            if i not in cache:
                cache[i]=v6.safe_eval(world.trees[i],z);work+=1
        return tuple(cache[i] for i in remain)
    def agreement():
        if not remain or len(original_classes())!=1:return False
        return all(len({records[i] for i in remain})==1 for records in local.values())
    for step in range(QUERY_CAP):
        if not remain:break
        if policy=="fixed_pool" and step and agreement():break
        if policy!="fixed_pool" and step>=INITIAL_ROUNDS and len(remain)==1 and novel>=1:break
        initial=step<INITIAL_ROUNDS or policy=="fixed_pool"
        unused=[i for i,z in enumerate(pool) if z not in asked]
        if initial and unused:
            classes=original_classes()
            j=unused[0] if step==0 else max(unused,key=lambda j:(len({s[j] for s in classes}),-j))
            z=pool[j];pred=tuple(world.initial[i][j] for i in remain);origin="initial"
            if policy!="fixed_pool" and step and len(classes)==1:
                initial=False
        if not initial or not unused:
            if policy=="fixed_pool":break
            batch=[];seen=set(pool)|asked|set(local)
            # All novel arms get at most BATCH candidates per round.
            for _ in range(BATCH*4):
                if len(batch)>=BATCH:break
                if policy=="mutated_active" and parents and rng.random()<.70:
                    z=mutate(rng,rng.choice(parents),vals)
                else:z=fresh(rng,vals)
                if z not in seen:seen.add(z);batch.append(z)
            if not batch:break
            predicted=[(z,prediction(z)) for z in batch]
            ranked=sorted(predicted,key=lambda p:diversity(p[1]),reverse=True)
            parents=[z for z,_ in ranked[:5]]
            z,pred=predicted[0] if policy=="random_guard" else ranked[0]
            origin="generated";novel+=1
        y=world.oracle(z);before=len(remain)
        remain=tuple(i for i,p in zip(remain,pred) if p==y)
        asked.add(z)
        trace.append(dict(input=z,output=y,before=before,after=len(remain),origin=origin,
                          predicted_classes=diversity(pred)[0]))
        if origin=="initial" and policy=="mutated_active":
            parents=[z,*parents][:5]
    # Every new hypothetical input actually inspected can expose disagreement.
    agreed=bool(trace) and agreement()
    chosen=remain[0] if agreed else None
    elapsed=time.perf_counter_ns()-start
    success=chosen is not None and world.validate(chosen)
    return dict(id=world.case["id"],fixture=world.case["fixture"],mutations=world.case["mutations"],
       policy=policy,correct=success,emitted=chosen is not None,queries=len(trace),novel_queries=novel,
       generated_inputs=len(local),local_evaluations=work,remaining=len(remain),trace=trace,
       patch=world.edits[chosen] if chosen is not None else None,decision_ns=elapsed,build_ns=world.build_ns,
       candidate_count=world.generated)

def stats(rows):
    n=len(rows);c=sum(r["correct"] for r in rows);e=sum(r["emitted"] for r in rows)
    return dict(n=n,correct=c,wrong=e-c,abstained=n-e,
      mean_queries=sum(r["queries"] for r in rows)/n,mean_novel=sum(r["novel_queries"] for r in rows)/n,
      mean_generated=sum(r["generated_inputs"] for r in rows)/n,
      mean_local_evaluations=sum(r["local_evaluations"] for r in rows)/n,mean_decision_ns=sum(r["decision_ns"] for r in rows)/n)

def run(folder):
    folder.mkdir(parents=True,exist_ok=False);rows=[];cases=[]
    for seed in SEEDS:
        for i,case in enumerate(proposals("",seed,"final")):
            world=World(case);cases.append({k:v for k,v in case.items() if k!="ref"})
            for policy in POLICIES:
                rr=investigate(world,policy,seed+i*131)
                rows.append(dict(seed=seed,**rr))
    base={(r["seed"],r["id"]):r for r in rows if r["policy"]=="fixed_pool"}
    aggregate=[]
    for p in POLICIES:
        rr=[r for r in rows if r["policy"]==p];m=stats(rr)
        m.update(gains=sum(r["correct"] and not base[r["seed"],r["id"]]["correct"] for r in rr),
          losses=sum(not r["correct"] and base[r["seed"],r["id"]]["correct"] for r in rr),
          prevented_errors=sum(base[r["seed"],r["id"]]["emitted"] and not base[r["seed"],r["id"]]["correct"] and not (r["emitted"] and not r["correct"]) for r in rr))
        aggregate.append(dict(policy=p,**m))
    result=dict(protocol="V8-generated-experiments-v1",episodes=len(rows),seeds=SEEDS,aggregate=aggregate,
        by_fault=[dict(policy=p,mutations=n,**stats([r for r in rows if r["policy"]==p and r["mutations"]==n])) for p in POLICIES for n in range(4)])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"cases.json").write_text(json.dumps(cases,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_V8="+json.dumps(result,separators=(",",":")))

class Tests(unittest.TestCase):
    def test_novel_bounds(self):
        rng=random.Random(3);v=values(FIXTURES["dual_threshold"][0]);z=(0,)
        for _ in range(100):
            z=mutate(rng,z,v)
            self.assertTrue(1<=len(z)<=6 and all(abs(x)<=200 for x in z))
    def test_diversity(self):
        self.assertGreater(diversity([0,1,2]),diversity([0,0,0]))
    def test_disjoint(self):
        self.assertTrue(all(len(z)>=8 for z in reserved(2)))
    def test_investigate(self):
        c=proposals("",SEEDS[0],"test")[0];w=World(c)
        for p in POLICIES:
            r=investigate(w,p,5)
            self.assertLessEqual(r["queries"],QUERY_CAP)
            self.assertLessEqual(r["generated_inputs"],BATCH*QUERY_CAP)
            self.assertEqual(len({tuple(e["input"]) for e in r["trace"]}),r["queries"])
            self.assertTrue(all(len(e["input"])<=6 for e in r["trace"]))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V8 required")
    run(a.output)
