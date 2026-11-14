"""V4.1 — finite latent-state selection from black-box prefix transitions."""
import argparse
import hashlib
import json
import random
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V4"))
import planner as v4
from planner import h,prev,value,ACC,ITEM,ADD
SEEDS=(1110011,1140017,1170013,1200007)
MODELS=("none","phase2","phase3","phase4","prev_sign")
FAMILIES=("stateless","phase2","phase3","phase4","prev_sign","prev_exact")
POLICIES=("stateless","phase2","primitive_active","memory_active","lesson_active","lesson_dense")
PROBES=(-3,0,3)
PREFIXES=((),*(tuple([1]*(n-1)+[x]) for n in range(1,9) for x in (-3,0,4)))
GUARD=((2,-7,11),(-6,0,5,2),(8,7,-11,0,2),(-2,-1,9,1,8,-4),(0,)*9,(3,-8,4,-2,9,0,7,11,-5,2))
MAX_QUERIES=450


def state(model,prefix):
    if model=="none":return 0
    if model.startswith("phase"):return len(prefix)%int(model[-1])
    if model=="prev_sign":
        x=prefix[-1] if prefix else 0
        return (x>0)-(x<0)+1
    raise ValueError(model)


def state_count(model):
    return 1 if model=="none" else 3 if model=="prev_sign" else int(model[-1])


def target(task,seq):
    a=0;prefix=[]
    for x in seq:
        if task["family"]=="prev_exact":
            a+=(prefix[-1] if prefix else 0)*x+h.atom(task["terms"][0][0],x)
        else:
            model="none" if task["family"]=="stateless" else task["family"]
            terms=task["terms"][state(model,prefix)]
            a+=sum(h.atom(t,x) for t in terms)
        prefix.append(x)
    return a


def signature(t):
    seqs=[(),*((x,) for x in range(-12,13)),*((x,y) for x in (-7,-2,0,2,9) for y in (-5,0,6)),
          tuple(range(-5,8)),tuple(range(8,-6,-1)),(1,)*12]
    return tuple(target(t,s) for s in seqs)


def tasks(seed,seen):
    rng=random.Random(seed);result=[]
    for f in FAMILIES:
        for i in range(10):
            while True:
                k=1 if f in ("prev_exact","stateless") else state_count(f)
                groups=tuple(tuple(h.term(rng) for _ in range(1+(rng.random()<.35))) for j in range(k))
                t=dict(family=f,terms=groups,id=f"{seed}/{f}/{i}")
                sig=signature(t)
                if sig not in seen:
                    seen.add(sig);result.append(t);break
    rng.shuffle(result);return result


class Budget(Exception):pass


class Oracle:
    def __init__(self,q):self.q=q;self.cache={};self.transitions={}
    def get(self,z):
        z=tuple(z)
        if z not in self.cache:
            if len(self.cache)>=MAX_QUERIES:raise Budget()
            self.cache[z]=self.q(z)
        return self.cache[z]
    def observe(self,prefix,x):
        key=(tuple(prefix),x)
        if key not in self.transitions:
            p=tuple(prefix);self.transitions[key]=self.get(p+(x,))-self.get(p)
        return self.transitions[key]


def grouped(model,observations):
    groups=[{} for _ in range(state_count(model))]
    for (prefix,x),y in observations.items():
        table=groups[state(model,prefix)]
        if x in table and table[x]!=y:return None
        table[x]=y
    return groups


def predict(program,seq):
    a=0;prefix=[]
    if len(seq)>32:raise ValueError("length cap")
    for x in seq:
        a+=value(program["rules"][state(program["model"],prefix)],0,x)
        if abs(a)>10**12:raise ValueError("integer cap")
        prefix.append(x)
    return a


def tests(seed):
    rng=random.Random(seed^0xF17)
    return [*((x,) for x in range(-20,21) if x not in h.XS),
            *((x,y) for x in (-14,-7,-1,0,2,8,13) for y in (-12,0,11)),
            *(tuple(rng.randint(-20,20) for _ in range(rng.randint(9,20))) for i in range(24))]


def solve(view,planner,policy):
    start=time.perf_counter_ns();oracle=Oracle(view);events=[];work=0;program=None
    candidates=("none",) if policy=="stateless" else ("phase2",) if policy=="phase2" else MODELS
    try:
        for prefix in PREFIXES:
            for x in (h.XS if policy=="lesson_dense" else PROBES):oracle.observe(prefix,x)
        for model in candidates:
            groups=grouped(model,oracle.transitions)
            if groups is None:
                events.append(dict(model=model,status="contradicted"));continue
            # Complete only the needed state tables, one representative prefix per state.
            for k in range(state_count(model)):
                representative=next(p for p in PREFIXES if state(model,p)==k)
                for x in h.XS:oracle.observe(representative,x)
            groups=grouped(model,oracle.transitions)
            if groups is None:
                events.append(dict(model=model,status="contradicted_after_probe"));continue
            rules=[];origins=[]
            for table in groups:
                e,n,src,trace=planner.solve(tuple(table[x] for x in h.XS));work+=n
                if e is None:break
                rules.append(e);origins.append(src)
            if len(rules)!=len(groups):
                events.append(dict(model=model,status="unsolved_subgoal",resolved=len(rules)));continue
            proposal=dict(model=model,rules=rules,origins=origins)
            # Guard queries are available to the agent, unlike the final evaluation.
            passed=True
            for seq in GUARD:
                y=oracle.get(seq)
                try:z=predict(proposal,seq)
                except (ValueError,ZeroDivisionError):z=None
                if y!=z:
                    events.append(dict(model=model,status="refuted_guard",probe=seq,expected=y,observed=z))
                    passed=False;break
            if passed:
                program=proposal;events.append(dict(model=model,status="candidate",rules=len(rules)));break
    except Budget:
        events.append(dict(status="query_budget_exhausted"))
    return program,dict(events=events,queries=len(oracle.cache),work=work,decision_ns=time.perf_counter_ns()-start)


def episode(task,planner,policy,seed):
    program,record=solve(lambda z:target(task,z),planner,policy)
    checks=[]
    if program:
        for seq in tests(seed):
            y=target(task,seq)
            try:z=predict(program,seq)
            except (ValueError,ZeroDivisionError):z=None
            checks.append([seq,y,z])
    success=program is not None and all(y==z for _,y,z in checks)
    return dict(task=task,policy=policy,program=program,success=success,abstained=program is None,checks=checks,**record)


def metrics(rows):
    n=len(rows);ok=sum(r["success"] for r in rows);a=sum(r["abstained"] for r in rows)
    return dict(n=n,correct=ok,abstained=a,wrong=n-a-ok,mean_queries=sum(r["queries"] for r in rows)/n,
        mean_decision_ns=sum(r["decision_ns"] for r in rows)/n,
        selected={m:sum(r["program"] is not None and r["program"]["model"]==m for r in rows) for m in MODELS},
        guard_refutations=sum(sum(e.get("status")=="refuted_guard" for e in r["events"]) for r in rows))


def run(folder,prior,banks):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    memories=json.loads(prior.read_text());hierarchy=json.loads(banks.read_text());seen=set();rows=[];costs=[]
    for seed,ps,bs in zip(SEEDS,prev.SEEDS,h.SEEDS):
        suite=tasks(seed,seen);snapshot=memories[str(ps)]
        primitive,_=h.build_pool("grammar",snapshot);memory,_=h.build_pool("schema",snapshot)
        memory=h.add_layer(memory,v4.restore(hierarchy[str(bs)]))
        lesson,rejected=v4.lesson_rows("shape");enhanced=h.add_layer(memory,lesson)
        models={"primitive":v4.Planner(primitive),"memory":v4.Planner(memory),"lesson":v4.Planner(enhanced)}
        costs.append(dict(seed=seed,indexes={p:dict(pool=len(m.pool),entries=len(m.pairs),build_ns=m.build_ns) for p,m in models.items()}))
        digest=h.sha([m.pool for m in models.values()])
        for i,t in enumerate(suite):
            for policy in POLICIES:
                model=models["primitive" if policy=="primitive_active" else "memory" if policy=="memory_active" else "lesson"]
                r=episode(t,model,policy,seed*31+i*997);rows.append(dict(seed=seed,**r))
        assert digest==h.sha([m.pool for m in models.values()])
    result=dict(protocol="NUCLEO_V4_1-state-v1",episodes=len(rows),seeds=SEEDS,
      aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
      by_family=[dict(policy=p,family=f,**metrics([r for r in rows if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in FAMILIES],
      index_cost=costs,prior_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),banks_sha256=hashlib.sha256(banks.read_bytes()).hexdigest(),
      examples=[dict(task=r["task"],program=r["program"],events=r["events"]) for r in rows if r["policy"]=="lesson_active" and r["success"] and r["program"]["model"]!="none"][:4])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(v4.enc(r)+"\n")
    print("SUMMARY_STATE="+v4.enc(result))


class Tests(unittest.TestCase):
    def test_state(self):
        self.assertEqual(state("phase3",(1,2,3,4)),1)
        self.assertEqual(state("prev_sign",(-3,)),0)
        self.assertEqual(state("prev_sign",()),1)
    def test_group(self):
        self.assertIsNone(grouped("none",{((),4):1,((1,),4):2}))
        self.assertIsNotNone(grouped("phase2",{((),4):1,((1,),4):2}))
    def test_identify(self):
        es=[(ITEM,),(h.ABS,(ITEM,))]
        pool=[dict(expr=e,vec=h.vector(e),source={"kind":"test"}) for e in es]
        planner=v4.Planner(pool)
        p,m=solve(lambda z:sum(x if i%2==0 else abs(x) for i,x in enumerate(z)),planner,"lesson_active")
        self.assertIsNotNone(p);self.assertEqual(p["model"],"phase2")
        self.assertEqual(predict(p,[-5,-4,3,-6]),8)
        self.assertLessEqual(m["queries"],MAX_QUERIES)
    def test_query_cap(self):
        o=Oracle(sum)
        for i in range(MAX_QUERIES):o.get((i,))
        with self.assertRaises(Budget):o.get((-1,))
    def test_tasks(self):
        seen=set();t=tasks(SEEDS[0],seen);self.assertEqual(len(t),60);self.assertEqual(len(seen),60)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);p.add_argument("--banks",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or not a.prior or not a.banks or ROOT not in a.output.resolve().parents:p.error("new output and archived snapshots required")
    run(a.output,a.prior,a.banks)
