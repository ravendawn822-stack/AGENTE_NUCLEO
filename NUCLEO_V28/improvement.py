"""V28: bounded mutation of declarative investigation policies."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V27"))
import strategy as s
m,v=s.m,s.v
SEEDS=(4080017,4110023,4140031,4170041)
FIELDS=(("pairs","minimax","mixed","fixed"),(0,1),("fixed","distance","length","random"))
CONFIGS=tuple(itertools.product(*FIELDS))
BASE=("pairs",0,"fixed")
POLICIES=("baseline","mutation","mutation_validated","random","random_validated")
CAP=v.CAP

def split(seed,points):
    development,final=s.suite(seed,points)
    proposal=[];gate=[]
    for length in range(1,5):
        group=[t for t in development if t["length"]==length]
        n=len(group)//2;proposal.extend(group[:n]);gate.extend(group[n:])
    assert len(proposal)==len(gate)==15 and len(final)==30
    return proposal,gate,final

def neighbors(config):
    return sorted({config[:i]+(value,)+config[i+1:] for i,field in enumerate(FIELDS)
                   for value in field if value!=config[i]})

def solve(observed,initial,pool,ask,config,prepared,seed):
    assert config in CONFIGS
    identify,tie,verify=config
    width=len(observed);expected=tuple(observed);evidence=list(initial)
    candidates=[(p,sg) for p,sg in prepared if sg[:width]==expected]
    remaining=list(range(len(pool)));trace=[];cost=len(prepared)*width
    rng=random.Random(seed)
    def distance(j):return min(s.distance(pool[j],x) for x in evidence)
    for _ in range(CAP):
        if not candidates:break
        if len(candidates)==1:
            if verify=="random":i=rng.choice(remaining)
            elif verify=="distance":i=max(remaining,key=distance)
            elif verify=="length":
                i=max(remaining,key=lambda j:(-sum(len(x)==len(pool[j]) for x in evidence),distance(j)))
            else:i=remaining[0]
        elif identify=="fixed":i=remaining[0]
        else:
            best=None;i=None;n=len(candidates)
            for j in remaining:
                counts={}
                for _,sg in candidates:
                    z=sg[width+j];counts[z]=counts.get(z,0)+1;cost+=1
                pair=n*n-sum(k*k for k in counts.values())
                worst=n-max(counts.values())
                score=pair if identify=="pairs" else worst if identify=="minimax" else pair+n*worst
                key=(score,distance(j) if tie else 0)
                if best is None or key>best:best,i=key,j
        remaining.remove(i);x=pool[i];y=tuple(ask(x));evidence.append(x)
        before=len(candidates);candidates=[(p,sg) for p,sg in candidates if sg[width+i]==y]
        cost+=before
        trace.append(dict(input=x,output=y,before=before,after=len(candidates)))
    return (candidates[0][0] if len(candidates)==1 else None),trace,cost

def episode(t,initial,pool,held,prepared,config,seed,policy):
    target=t["program"];obs=m.sig(target,initial)
    start=time.perf_counter_ns()
    p,trace,cost=solve(obs,initial,pool,lambda x:m.execute_target(target,x),config,prepared,seed)
    elapsed=time.perf_counter_ns()-start
    return dict(task=t,policy=policy,config=config,program=p,emitted=p is not None,
        success=p is not None and m.sig(p,held)==m.sig(target,held),
        queries=len(trace),trace=trace,comparisons=cost,wall_ns=elapsed)

def rank(config,rows):
    metrics=s.metrics(rows)
    return (-metrics["score"],metrics["comparisons"],config)

def search(evaluate,seed,random_control=False,count=0):
    cache={BASE:evaluate(BASE)}
    rng=random.Random(seed)
    trail=[];incumbent=BASE
    if random_control:
        options=[cfg for cfg in CONFIGS if cfg!=BASE]
        tested=rng.sample(options,count)
        for cfg in tested:cache[cfg]=evaluate(cfg)
        incumbent=min(cache,key=lambda cfg:rank(cfg,cache[cfg]))
        trail.append(dict(tested=tested,chosen=incumbent))
    else:
        for round_no in range(3):
            options=[cfg for cfg in neighbors(incumbent) if cfg not in cache]
            tested=rng.sample(options,min(4,len(options)))
            for cfg in tested:cache[cfg]=evaluate(cfg)
            previous=incumbent
            incumbent=min([incumbent,*tested],key=lambda cfg:rank(cfg,cache[cfg]))
            trail.append(dict(round=round_no,previous=previous,tested=tested,chosen=incumbent))
    return incumbent,cache,trail

def approval(candidate,baseline_rows,candidate_rows):
    return candidate if s.metrics(candidate_rows)["score"]>s.metrics(baseline_rows)["score"] else BASE

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];decisions=[];preparation=[]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed)
        proposal,gate,final=split(seed,(*initial,*pool,*held))
        start=time.perf_counter_ns();prepared,n=v.prepare(m.FULL3,initial,pool)
        preparation.append(dict(seed=seed,programs=len(m.FULL3),classes=len(prepared),executions=n,wall_ns=time.perf_counter_ns()-start))
        def evaluate(tasks,config,phase):
            return [dict(seed=seed,**episode(t,initial,pool,held,prepared,config,seed+i*701,phase))
                    for i,t in enumerate(tasks)]
        chosen,cache,trail=search(lambda config:evaluate(proposal,config,"mutation_proposal"),seed^0x2801)
        random_cfg,random_cache,random_trail=search(lambda config:evaluate(proposal,config,"random_proposal"),
            seed^0x2802,True,len(cache)-1)
        proposal_rows=[r for rr in cache.values() for r in rr]
        random_rows=[r for rr in random_cache.values() for r in rr]
        baseline_gate=evaluate(gate,BASE,"baseline_gate")
        chosen_gate=evaluate(gate,chosen,"mutation_gate")
        random_gate=evaluate(gate,random_cfg,"random_gate")
        accepted=approval(chosen,baseline_gate,chosen_gate)
        accepted_random=approval(random_cfg,baseline_gate,random_gate)
        gate_rows=baseline_gate+chosen_gate+random_gate
        training.extend(proposal_rows+random_rows+gate_rows)
        decision=dict(seed=seed,baseline=BASE,mutation=chosen,mutation_validated=accepted,
            random=random_cfg,random_validated=accepted_random,trail=trail,random_trail=random_trail,
            mutation_configurations=len(cache),random_configurations=len(random_cache),
            proposal_sha=m.digest(proposal_rows),random_proposal_sha=m.digest(random_rows),gate_sha=m.digest(gate_rows),
            mutation_proposal=s.metrics(proposal_rows),random_proposal=s.metrics(random_rows),
            baseline_gate=s.metrics(baseline_gate),mutation_gate=s.metrics(chosen_gate),random_gate=s.metrics(random_gate))
        decision["sha"]=m.digest(decision)
        path=out/f"policy_{seed}.json";path.write_text(m.enc(decision),encoding="utf-8")
        loaded=json.loads(path.read_text());sha=loaded.pop("sha");assert m.digest(loaded)==sha
        config_map={name:tuple(loaded[name]) for name in POLICIES}
        assert all(config in CONFIGS for config in config_map.values())
        decisions.append(decision)
        for i,t in enumerate(final):
            for policy,config in config_map.items():
                rows.append(dict(seed=seed,**episode(t,initial,pool,held,prepared,config,seed+i*971,policy)))
        assert json.loads(path.read_text())["sha"]==sha
    result=dict(protocol="V28-bounded-policy-improvement-v1",seeds=SEEDS,decisions=decisions,preparation=preparation,
        aggregate=[dict(policy=p,**s.metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=seed,policy=p,**s.metrics([r for r in rows if r["seed"]==seed and r["policy"]==p])) for seed in SEEDS for p in POLICIES],
        by_length=[dict(length=l,policy=p,**s.metrics([r for r in rows if r["task"]["length"]==l and r["policy"]==p])) for l in range(1,5) for p in POLICIES])
    for policy in POLICIES[1:]:
        ref={(r["seed"],r["task"]["id"]):r for r in rows if r["policy"]=="baseline"}
        rr=[r for r in rows if r["policy"]==policy]
        result.setdefault("paired_vs_baseline",{})[policy]=dict(
            gains=sum(r["success"] and not ref[r["seed"],r["task"]["id"]]["success"] for r in rr),
            losses=sum(not r["success"] and ref[r["seed"],r["task"]["id"]]["success"] for r in rr))
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("development",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(m.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_configs(self):
        self.assertEqual(len(set(CONFIGS)),32)
        for cfg in CONFIGS:
            for neighbor in neighbors(cfg):
                self.assertIn(neighbor,CONFIGS)
                self.assertEqual(sum(a!=b for a,b in zip(cfg,neighbor)),1)
    def test_split(self):
        for seed in SEEDS:
            a,b,c=v.input_sets(seed);points=(*a,*b,*c)
            p,g,f=split(seed,points)
            self.assertEqual((len(p),len(g),len(f)),(15,15,30))
            self.assertEqual(len({m.sig(t["program"],points) for t in p+g+f}),60)
    def test_baseline(self):
        a,b,c=v.input_sets(SEEDS[0]);prepared,_=v.prepare(m.FULL3,a,b)
        target=("positive","sort","inc");obs=m.sig(target,a);ask=lambda x:v.execute(target,x)
        self.assertEqual(s.solve(obs,a,b,ask,s.BASE,prepared,1),solve(obs,a,b,ask,BASE,prepared,1))
        for cfg in CONFIGS:
            p,trace,cost=solve(obs,a,b,ask,cfg,prepared,1)
            points=[r["input"] for r in trace]
            self.assertLessEqual(len(points),CAP)
            self.assertEqual(len(points),len(set(points)))
            self.assertFalse(set(points)&set(c))
            if p is not None:self.assertTrue(all(v.execute(p,x)==ask(x) for x in (*a,*points)))
    def test_gate(self):
        ok=[dict(success=True,emitted=True,queries=1,comparisons=1,wall_ns=1)]
        bad=[dict(success=False,emitted=True,queries=1,comparisons=1,wall_ns=1)]
        cfg=("mixed",1,"distance")
        self.assertEqual(approval(cfg,ok,bad),BASE)
        self.assertEqual(approval(cfg,bad,ok),cfg)
        self.assertEqual(approval(cfg,ok,ok),BASE)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V28 required")
    run(z.output)
