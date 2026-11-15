"""V46: active acquisition feeding bounded mixed-composition transfer."""
import argparse,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V43"))
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V45"))
import mixed_composition as mix
import cost_aware as cost
c,f,m=mix.c,mix.f,mix.m
SEEDS=(6180017,6210023,6240031,6270041)
POLICIES=("empty","random_library","random","active","dense")
ACQUISITION=("random","active","dense")
PROTOCOL="V46-active-acquisition-v1"
BUDGET=16

def inputs(seed):
    initial,pool,challenge,reserved=cost.a.inputs(seed)
    teach=reserved[:24];seen=set((*initial,*pool,*challenge,*reserved))
    rng=random.Random(seed^0x4601)
    def draw(n,domain,max_len):
        out=[]
        while len(out)<n:
            i=len(out)%3
            lo,hi=(1,domain) if i==0 else (-domain,-1) if i==1 else (-domain,domain)
            x=tuple(rng.randint(lo,hi) for _ in range(rng.randint(1,max_len)))
            if x not in seen:seen.add(x);out.append(x)
        return tuple(out)
    return initial,pool,challenge,teach,draw(14,5,6),draw(80,8,8)

def prepare(examples,pool,challenge):
    if len(examples)!=4 or len(pool)!=32 or len(challenge)!=24:
        raise ValueError("input bounds")
    groups={};checks=predictions=matches=0
    start=time.perf_counter_ns()
    for p in c.MOTIFS:
        for x,y in examples:
            checks+=1
            if f.evaluate(p,x)!=y:break
        else:
            matches+=1
            sig=tuple(f.evaluate(p,x) for x in (*pool,*challenge));predictions+=len(sig)
            if sig not in groups:groups[sig]=[p,0]
            groups[sig][1]+=1
    classes=tuple((v[0],sig,v[1]) for sig,v in groups.items())
    return classes,dict(initial_classes=len(classes),initial_matches=matches,
        preparation_examined=len(c.MOTIFS),initial_checks=checks,prediction_checks=predictions,
        shared_preparation_ns=time.perf_counter_ns()-start)

def dense(classes,pool,ask):
    alive=list(range(len(classes)));spent=filter_checks=0;trace=[]
    start=time.perf_counter_ns()
    for i,x in enumerate(pool):
        if not alive:break
        y=ask(x);before=len(alive);filter_checks+=before
        n=cost.query_cost(x);spent+=n
        alive=[j for j in alive if classes[j][1][i]==y]
        trace.append(dict(index=i,input=x,output=y,cost=n,cumulative_cost=spent,before=before,after=len(alive)))
    return dict(program=classes[alive[0]][0] if alive else None,remaining_classes=len(alive),
        remaining_programs=sum(classes[j][2] for j in alive),trace=trace,queries=len(trace),spent=spent,
        stop="no_candidate" if not alive else "pool_exhausted",selection_checks=0,filter_checks=filter_checks,
        selection_ns=time.perf_counter_ns()-start)

def validate(result,teach,ask):
    p=result["program"] if result["remaining_classes"]==1 else None
    if p is not None and p not in c.MOTIF_SET:raise ValueError("non-motif proposal")
    matches=checks=0;failure=None
    if p is not None:
        for x in teach:
            y=ask(x);actual=f.evaluate(p,x);checks+=1;matches+=actual==y
            if actual!=y and failure is None:failure=dict(input=x,expected=y,actual=actual)
    return dict(emitted=p is not None,accepted=p is not None and matches==len(teach),
        validation_checks=checks,validation_matches=matches,validation_failure=failure,proposal=p)

def acquisition(seed,initial,pool,challenge,teach):
    libraries={p:[] for p in ACQUISITION};rows=[]
    for i,name in enumerate(f.DIRECT):
        ask=lambda x:f.oracle(name,x)
        examples=tuple((x,ask(x)) for x in initial)
        classes,prep=prepare(examples,pool,challenge)
        for policy in ACQUISITION:
            result=dense(classes,pool,ask) if policy=="dense" else cost.investigate(classes,pool,ask,seed+971*i,policy,BUDGET)
            verdict=validate(result,teach,ask);p=verdict["proposal"]
            retained=verdict["accepted"] and p not in libraries[policy]
            if retained:libraries[policy].append(p)
            rows.append(dict(seed=seed,name=name,policy=policy,retained=retained,**result,**verdict,**prep))
    libraries["empty"]=[]
    libraries["random_library"]=random.Random(seed^0x4602).sample(c.MOTIFS,6)
    return {p:tuple(v) for p,v in libraries.items()},rows

def training_metric(rows):
    return dict(n=len(rows),accepted=sum(r["accepted"] for r in rows),
        rejected=sum(r["emitted"] and not r["accepted"] for r in rows),
        abstained=sum(not r["emitted"] for r in rows),
        retained=sum(r["retained"] for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("spent","queries","selection_checks","filter_checks",
            "validation_checks","initial_checks","prediction_checks","preparation_examined",
            "shared_preparation_ns","selection_ns")})

def evaluate(seed,library,policy,name,stratum,examples,held,single,prep):
    if single:
        program=("single",single[0]);stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
    else:
        pair,stats=mix.pair_search(examples,library,bool(library));program=("pair",pair) if pair else None
    matches=0;failure=None
    if program:
        for x in held:
            y=mix.oracle(name,x);actual=c.run_program(program,x);matches+=actual==y
            if actual!=y and failure is None:failure=dict(input=x,expected=y,actual=actual)
    return dict(seed=seed,policy=policy,stratum=stratum,name=name,program=program,
        emitted=program is not None,correct=program is not None and matches==len(held),
        held_matches=matches,held_tests=len(held) if program else 0,first_failure=failure,
        single_examined=prep["examined"],single_checks=prep["checks"],single_wall_ns=prep["wall_ns"],**stats)

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);training=[];rows=[];snapshots=[]
    for seed in seeds:
        initial,pool,challenge,teach,public,held=inputs(seed)
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(initial=initial,pool=pool,challenge=challenge,
            teaching=teach,public=public,held=held)),encoding="utf-8")
        libraries,learned=acquisition(seed,initial,pool,challenge,teach);training.extend(learned)
        frozen={}
        for policy in POLICIES:
            lib,sha=c.freeze(out/f"library_{seed}_{policy}.json",libraries[policy])
            frozen[policy]=(lib,sha);snapshots.append(dict(seed=seed,policy=policy,library=lib,sha=sha,
                validated_library=policy in ACQUISITION))
        for stratum,names in mix.GROUPS:
            for name in names:
                examples=tuple((x,mix.oracle(name,x)) for x in public)
                single,prep=f.search(examples,True,True,(),1)
                for policy in POLICIES:
                    rows.append(evaluate(seed,frozen[policy][0],policy,name,stratum,examples,held,single,prep))
        for lib,sha in frozen.values():
            if m.digest({"library":lib})!=sha:raise RuntimeError("memory changed")
    summary=dict(protocol=PROTOCOL,seeds=seeds,query_budget=BUDGET,pair_budget=mix.CAP,
        timing="Preparation shared across acquisition policies and first-stage final search across all policies.",
        acquisition=[dict(policy=p,**training_metric([r for r in training if r["policy"]==p])) for p in ACQUISITION],
        snapshots=snapshots,
        aggregate=[dict(policy=p,**mix.metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**mix.metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in mix.GROUPS],
        by_seed=[dict(seed=seed,policy=p,**mix.metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,records in (("acquisition",training),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,acquisition=summary["acquisition"],aggregate=summary["aggregate"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_inputs(self):
        for seed in SEEDS:
            parts=inputs(seed)
            self.assertEqual(tuple(map(len,parts)),(4,32,24,24,14,80))
            self.assertEqual(len(set(x for part in parts for x in part)),178)
    def test_acquisition(self):
        a,b,ch,t,_,_=inputs(SEEDS[0])
        libs,rows=acquisition(SEEDS[0],a,b,ch,t)
        self.assertEqual(len(rows),18)
        self.assertEqual(len(libs["empty"]),0)
        self.assertEqual(len(libs["random_library"]),6)
        for row in rows:
            if row["policy"]!="dense":self.assertLessEqual(row["spent"],BUDGET)
            if row["retained"]:
                self.assertEqual(row["validation_matches"],24)
                self.assertIn(row["proposal"],libs[row["policy"]])
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertEqual(len(s["aggregate"]),5)
            self.assertTrue(all(r["n"]==24 and r["pair_examined"]<=24*mix.CAP for r in s["aggregate"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None:p.error("--output required")
    out=a.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V46 required")
    run(out)

if __name__=="__main__":main()
