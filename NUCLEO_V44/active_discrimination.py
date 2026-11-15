"""V44: bounded active experiments and uncertainty-aware abstention."""
import argparse,collections,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V41"))
import fork_memory as f
m=f.m
SEEDS=(5940017,5970023,6000031,6030041)
POLICIES=("first","random6","active6","guarded6")
QUERY_CAP=6
GROUPS=(("sign",("negate","absolute","neg_min","abs_min")),
        ("other",("positive","total","square","mirror_sum","span","duplicate_sort")),
        ("control",("product_prefix_mod97","repeat_three")))
PROTOCOL="V44-active-discrimination-v1"

def inputs(seed):
    rng=random.Random(seed)
    initial=((-3,),(-1,-3),(-4,-1,-2),(-2,-2,-1))
    pool=[(),(0,),(3,),(2,1,4),(3,-2,0),(-1,0,2),(-4,),(0,0)]
    seen=set((*initial,*pool))
    def draw(n,domain,max_len):
        out=[]
        while len(out)<n:
            group=len(out)%3
            lo,hi=(1,domain) if group==0 else (-domain,-1) if group==1 else (-domain,domain)
            x=tuple(rng.randint(lo,hi) for _ in range(rng.randint(1,max_len)))
            if x not in seen:seen.add(x);out.append(x)
        return tuple(out)
    pool=tuple(pool)+draw(24,4,6)
    challenge=draw(24,8,7);held=draw(80,12,8)
    assert len(seen)==140
    return initial,pool,challenge,held

def oracle(name,x):
    # Evaluator only. Search receives examples and an observation callback.
    if name=="negate":return tuple(-z for z in x)
    if name=="absolute":return tuple(abs(z) for z in x)
    if name=="neg_min":return (-min(x) if x else 0,)
    if name=="abs_min":return (abs(min(x)) if x else 0,)
    if name=="positive":return tuple(z for z in x if z>0)
    if name=="total":return (sum(x),)
    return f.oracle(name,x)

def prepare(examples,pool,challenge):
    if len(examples)!=4 or len(pool)!=32 or len(challenge)!=24:raise ValueError("input budget")
    start=time.perf_counter_ns()
    groups={};examined=matches=checks=predictions=0
    for p in f.grammar(True,True):
        examined+=1
        for x,y in examples:
            checks+=1
            if f.evaluate(p,x)!=y:break
        else:
            matches+=1
            signature=tuple(f.evaluate(p,x) for x in (*pool,*challenge))
            predictions+=len(signature)
            if signature in groups:
                groups[signature][1]+=1
            else:groups[signature]=[p,1]
    assert examined==f.FINAL_CAP
    classes=tuple((value[0],sig,value[1]) for sig,value in groups.items())
    return classes,dict(preparation_examined=examined,initial_checks=checks,
        initial_matches=matches,initial_classes=len(classes),prediction_checks=predictions,
        shared_preparation_ns=time.perf_counter_ns()-start)

def investigate(classes,pool,ask,seed,policy):
    if policy not in ("first","random6","active6"):raise ValueError("policy")
    start=time.perf_counter_ns()
    alive=list(range(len(classes)));unused=list(range(len(pool)))
    rng=random.Random(seed);trace=[];selection_checks=0;filter_checks=0
    if policy!="first":
        for _ in range(QUERY_CAP):
            if not alive or not unused:break
            if policy=="random6":
                index=rng.choice(unused);score=None
            else:
                def disagreement(idx):
                    nonlocal selection_checks
                    counts=collections.Counter(classes[j][1][idx] for j in alive)
                    selection_checks+=len(alive)
                    return len(alive)**2-sum(v*v for v in counts.values())
                index=max(unused,key=disagreement)
                # A score recomputation is not needed for selection; record it separately.
                score=len(alive)**2-sum(v*v for v in collections.Counter(classes[j][1][index] for j in alive).values())
                selection_checks+=len(alive)
            unused.remove(index);answer=ask(pool[index]);before=len(alive)
            filter_checks+=before
            alive=[j for j in alive if classes[j][1][index]==answer]
            trace.append(dict(index=index,input=pool[index],output=answer,before=before,after=len(alive),
                              disagreement=score))
    chosen=classes[alive[0]][0] if alive else None
    return dict(program=chosen,queries=len(trace),remaining_classes=len(alive),
        remaining_programs=sum(classes[j][2] for j in alive),trace=trace,
        selection_checks=selection_checks,filter_checks=filter_checks,
        selection_ns=time.perf_counter_ns()-start)

def guard(active):
    # Shared active investigation, no additional oracle calls.
    result=dict(active)
    if result["remaining_classes"]!=1:result["program"]=None
    return result

def score(result,held,ask):
    p=result["program"];matches=0;failure=None
    if p is not None:
        for x in held:
            expected=ask(x);actual=f.evaluate(p,x)
            matches+=actual==expected
            if actual!=expected and failure is None:
                failure=dict(input=x,expected=expected,actual=actual)
    return dict(emitted=p is not None,correct=p is not None and matches==len(held),
                held_matches=matches,held_tests=len(held) if p is not None else 0,first_failure=failure)

def metrics(rows):
    correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
        **{k:sum(r[k] for r in rows) for k in ("queries","remaining_classes","initial_classes",
            "remaining_programs","initial_matches","preparation_examined","initial_checks",
            "prediction_checks","selection_checks","filter_checks","shared_preparation_ns","selection_ns")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in seeds:
        initial,pool,challenge,held=inputs(seed)
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(initial=initial,pool=pool,challenge=challenge,held=held)),encoding="utf-8")
        task_index=0
        for stratum,names in GROUPS:
            for name in names:
                task_index+=1
                ask=lambda x:oracle(name,x)
                examples=tuple((x,ask(x)) for x in initial)
                classes,cost=prepare(examples,pool,challenge)
                results={p:investigate(classes,pool,ask,seed+task_index*971,p)
                         for p in ("first","random6","active6")}
                results["guarded6"]=guard(results["active6"])
                for policy in POLICIES:
                    result=results[policy]
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        **result,**score(result,held,ask),**cost))
    data=dict(protocol=PROTOCOL,seeds=seeds,query_cap=QUERY_CAP,grammar_size=f.FINAL_CAP,
        timing="Preparation shared across policies; guarded reuses active trace and timing. Not independent total runtimes.",
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metrics([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,policy=p,**metrics([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    (out/"final.jsonl").write_text("".join(m.enc(r)+"\n" for r in rows),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,aggregate=data["aggregate"],by_stratum=data["by_stratum"]),indent=2))
    return data

class Tests(unittest.TestCase):
    def test_input_disjoint(self):
        for seed in SEEDS:
            sets=inputs(seed)
            self.assertEqual(tuple(map(len,sets)),(4,32,24,80))
            self.assertEqual(len(set(it for seq in sets for it in seq)),140)
    def test_active(self):
        pool=((2,),(-3,), (0,))
        # Candidates agree on negatives; the positive observation discriminates.
        classes=((("pipe",("abs",)),((2,),(3,),(0,)),1),
                 (("pipe",("neg",)),((-2,),(3,),(0,)),1))
        seen=[]
        def ask(x):
            seen.append(x);return tuple(-z for z in x)
        res=investigate(classes,pool,ask,0,"active6")
        self.assertEqual(seen[0],(2,))
        self.assertEqual(res["program"],("pipe",("neg",)))
        self.assertEqual(guard(res)["program"],res["program"])
        self.assertIsNone(guard(investigate(classes,pool,ask,0,"first"))["program"])
    def test_prepare(self):
        a,b,ch,h=inputs(SEEDS[0])
        classes,cost=prepare(tuple((x,oracle("negate",x)) for x in a),b,ch)
        self.assertEqual(cost["preparation_examined"],28548)
        self.assertEqual(sum(z[2] for z in classes),cost["initial_matches"])
        self.assertGreaterEqual(len(classes),2)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            data=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==12 for r in data["aggregate"]))
            by={r["policy"]:r for r in data["aggregate"]}
            self.assertEqual(by["first"]["queries"],0)
            self.assertEqual(by["active6"]["queries"],by["guarded6"]["queries"])
            self.assertLessEqual(by["guarded6"]["correct"],by["active6"]["correct"])
            self.assertLessEqual(by["guarded6"]["wrong"],by["active6"]["wrong"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None:p.error("--output required")
    out=a.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V44 required")
    run(out)

if __name__=="__main__":main()
