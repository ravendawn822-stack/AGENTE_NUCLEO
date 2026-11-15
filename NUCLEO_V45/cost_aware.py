"""V45: cost-aware information acquisition and adaptive stopping."""
import argparse,collections,json,random,sys,tempfile,time,unittest
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V44"))
import active_discrimination as a
f,m=a.f,a.m
SEEDS=(6060017,6090023,6120031,6150041)
BUDGETS=(4,8,16)
POLICIES=("random","cheap","active","efficient")
GROUPS=(*a.GROUPS,("additional",("minimum","prefix","distinct_count","reverse_concat")))
PROTOCOL="V45-cost-aware-investigation-v1"

def oracle(name,x):
    if name=="distinct_count":return (len(set(x)),)
    return a.oracle(name,x)

def query_cost(x):return 1+len(x)

def investigate(classes,pool,ask,seed,policy,budget):
    if policy not in POLICIES or budget not in BUDGETS or len(pool)>32:
        raise ValueError("constraints")
    rng=random.Random(seed);alive=list(range(len(classes)));unused=list(range(len(pool)))
    spent=selection_checks=filter_checks=0;trace=[]
    start=time.perf_counter_ns()
    for _ in range(a.QUERY_CAP):
        if len(alive)<=1:break
        affordable=[i for i in unused if query_cost(pool[i])<=budget-spent]
        if not affordable:break
        scores={}
        if policy=="random":
            index=rng.choice(affordable)
        elif policy=="cheap":
            index=min(affordable,key=lambda i:(query_cost(pool[i]),i))
        else:
            for i in affordable:
                counts=collections.Counter(classes[j][1][i] for j in alive)
                selection_checks+=len(alive)
                scores[i]=len(alive)**2-sum(n*n for n in counts.values())
            def key(i):
                cost=query_cost(pool[i])
                value=Fraction(scores[i],cost) if policy=="efficient" else scores[i]
                return value,-cost,-i
            index=max(affordable,key=key)
        cost=query_cost(pool[index]);spent+=cost;unused.remove(index)
        observed=ask(pool[index]);before=len(alive);filter_checks+=before
        alive=[j for j in alive if classes[j][1][index]==observed]
        trace.append(dict(index=index,input=pool[index],output=observed,cost=cost,
            cumulative_cost=spent,before=before,after=len(alive),disagreement=scores.get(index)))
    assert spent<=budget and len(trace)<=a.QUERY_CAP
    if not alive:stop="no_candidate"
    elif len(alive)==1:stop="consensus"
    elif len(trace)==a.QUERY_CAP:stop="query_cap"
    else:stop="unaffordable"
    return dict(program=classes[alive[0]][0] if alive else None,remaining_classes=len(alive),
        remaining_programs=sum(classes[j][2] for j in alive),trace=trace,queries=len(trace),
        spent=spent,stop=stop,selection_checks=selection_checks,filter_checks=filter_checks,
        selection_ns=time.perf_counter_ns()-start)

def metric(rows):
    n=len(rows);correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    confirmed=sum(r["remaining_classes"]==1 for r in rows)
    confirmed_correct=sum(r["remaining_classes"]==1 and r["correct"] for r in rows)
    return dict(n=n,correct=correct,wrong=emitted-correct,abstained=n-emitted,
        guarded_correct=confirmed_correct,guarded_wrong=confirmed-confirmed_correct,
        guarded_abstained=n-confirmed,consensus=confirmed,
        **{k:sum(r[k] for r in rows) for k in ("spent","queries","remaining_classes","remaining_programs",
          "initial_classes","selection_checks","filter_checks","selection_ns",
          "preparation_examined","initial_checks","prediction_checks","shared_preparation_ns")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for seed in seeds:
        initial,pool,challenge,held=a.inputs(seed)
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(initial=initial,pool=pool,challenge=challenge,held=held,
            costs=[query_cost(x) for x in pool])),encoding="utf-8")
        ti=0
        for stratum,names in GROUPS:
            for name in names:
                ti+=1;ask=lambda x:oracle(name,x)
                examples=tuple((x,ask(x)) for x in initial)
                classes,cost=a.prepare(examples,pool,challenge)
                for budget in BUDGETS:
                    for policy in POLICIES:
                        result=investigate(classes,pool,ask,seed+ti*971,policy,budget)
                        rows.append(dict(seed=seed,stratum=stratum,name=name,budget=budget,policy=policy,
                            **result,**a.score(result,held,ask),**cost))
    summary=dict(protocol=PROTOCOL,seeds=seeds,budgets=BUDGETS,query_cap=a.QUERY_CAP,
        costs="Simulated cost: 1 + input length; four initial observations uncharged.",
        timing="Shared preparation replicated in metrics; separate selection timings.",
        aggregate=[dict(budget=b,policy=p,**metric([r for r in rows if r["budget"]==b and r["policy"]==p]))
                   for b in BUDGETS for p in POLICIES],
        by_stratum=[dict(budget=b,policy=p,stratum=s,**metric([r for r in rows if r["budget"]==b and r["policy"]==p and r["stratum"]==s]))
                   for b in BUDGETS for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,budget=b,policy=p,**metric([r for r in rows if r["seed"]==seed and r["budget"]==b and r["policy"]==p]))
                  for seed in seeds for b in BUDGETS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    (out/"final.jsonl").write_text("".join(m.enc(r)+"\n" for r in rows),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,aggregate=summary["aggregate"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_stopping(self):
        pool=((1,),(-1,),(2,3,4,5))
        classes=((("pipe",("neg",)),((-1,),(1,),(-2,-3,-4,-5)),1),
                 (("pipe",("abs",)),((1,),(1,),(2,3,4,5)),1))
        r=investigate(classes,pool,lambda x:tuple(-z for z in x),0,"efficient",4)
        self.assertEqual(r["queries"],1);self.assertEqual(r["spent"],2)
        self.assertEqual(r["program"],("pipe",("neg",)));self.assertEqual(r["stop"],"consensus")
        r=investigate((),pool,lambda x:self.fail("unexpected query"),0,"active",4)
        self.assertEqual(r["stop"],"no_candidate");self.assertEqual(r["spent"],0)
    def test_costs(self):
        pool=((1,),(2,3,4,5))
        classes=tuple((("pipe",()),((i//2,), (i,)),1) for i in range(4))
        ask=lambda x:(0,)
        r=investigate(classes,pool,ask,0,"efficient",8)
        self.assertEqual(r["trace"][0]["index"],0)
        r=investigate(classes,pool,ask,0,"active",8)
        self.assertEqual(r["trace"][0]["index"],1)
        for p in POLICIES:
            for b in BUDGETS:
                r=investigate(classes,pool,ask,0,p,b)
                self.assertLessEqual(r["spent"],b)
                self.assertEqual(r["spent"],sum(z["cost"] for z in r["trace"]))
                self.assertEqual(len({z["index"] for z in r["trace"]}),r["queries"])
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertEqual(len(s["aggregate"]),12)
            self.assertTrue(all(r["n"]==16 and r["spent"]<=r["n"]*r["budget"] for r in s["aggregate"]))
            self.assertTrue(all(r["guarded_correct"]<=r["correct"] and r["guarded_wrong"]<=r["wrong"] for r in s["aggregate"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    path=args.output.resolve()
    if ROOT not in path.parents:p.error("new output directory inside NUCLEO_V45 required")
    run(path)

if __name__=="__main__":main()
