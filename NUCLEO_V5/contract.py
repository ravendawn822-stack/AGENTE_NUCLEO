"""V5: finite input/output contracts -> bounded program proposal, with explicit sample requests."""
import argparse
import hashlib
import json
import sys
import random
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V4_1"))
import state as st
from state import v4,h,prev
SEEDS=(1230007,1260011,1290017,1320013)
POLICIES=("fixed","primitive","memory","dense")
MAX_ROUNDS=5
MAX_SAMPLES=450


class Missing(Exception):
    def __init__(self,seq):self.seq=seq


def checked_examples(rows):
    if not isinstance(rows,list) or len(rows)>MAX_SAMPLES:raise ValueError("sample cap")
    result={}
    for row in rows:
        x=row["input"];y=row["output"]
        if not isinstance(x,list) or len(x)>32 or any(type(v) is not int or abs(v)>1000 for v in x) or type(y) is not int or abs(y)>10**12:raise ValueError("invalid example")
        k=tuple(x)
        if k in result and result[k]!=y:raise ValueError("contradictory examples")
        result[k]=y
    return result


def needed_inputs(prefixes,items):
    return list(dict.fromkeys(x for prefix in prefixes for item in items for x in (prefix,prefix+(item,))))


def propose(samples,planner,mode="memory"):
    """No reference function or external I/O is available here."""
    data=checked_examples(samples)
    policy="lesson_dense" if mode=="dense" else "stateless" if mode=="fixed" else "lesson_active"
    initial=needed_inputs(st.PREFIXES,h.XS if mode=="dense" else st.PROBES)
    missing=[z for z in initial if z not in data]
    if missing:return dict(status="needs_examples",reason="initial_observations",requests=missing)
    transitions={(p,x):data[p+(x,)]-data[p] for p in st.PREFIXES for x in (h.XS if mode=="dense" else st.PROBES)}
    models=("none",) if mode=="fixed" else st.MODELS
    feasible=[m for m in models if st.grouped(m,transitions) is not None]
    requests=[]
    for m in feasible:
        reps=[next(p for p in st.PREFIXES if st.state(m,p)==k) for k in range(st.state_count(m))]
        requests.extend(needed_inputs(reps,h.XS))
    missing=[z for z in dict.fromkeys(requests) if z not in data]
    if missing:return dict(status="needs_examples",reason="resolve_state_subgoals",requests=missing,feasible_models=feasible)
    def query(z):
        z=tuple(z)
        if z not in data:raise Missing(z)
        return data[z]
    try:p,meta=st.solve(query,planner,policy)
    except Missing as e:
        requests=[z for z in st.GUARD if z not in data]
        if e.seq not in requests:requests.append(e.seq)
        return dict(status="needs_examples",reason="verify_candidate",requests=requests,feasible_models=feasible)
    if p is None:return dict(status="insufficient_model",events=meta["events"],used_queries=meta["queries"])
    # Every delivered example (including extra examples not demanded by the mechanism) must agree.
    try:
        if any(st.predict(p,z)!=y for z,y in data.items()):return dict(status="contradicted_by_examples",events=meta["events"])
    except (ValueError,ZeroDivisionError):return dict(status="contradicted_by_examples",events=meta["events"])
    return dict(status="candidate",program=p,events=meta["events"],used_queries=meta["queries"])


def render(p,name="solve"):
    if not (name=="solve" or name.startswith("task_") and name[5:].isdigit()):raise ValueError("name")
    model=p["model"]
    if model not in st.MODELS or len(p["rules"])!=st.state_count(model):raise ValueError("state model")
    rules=[h.freeze(e) for e in p["rules"]]
    if any(h.size(e)>110 or h.has(e,h.ACC) for e in rules):raise ValueError("rule shape")
    expressions=[v4.compiler(e) for e in rules]
    code=[f"def {name}(items):","    a = 0","    previous = 0","    for i, x in enumerate(items):"]
    selector="0" if model=="none" else "(int(previous > 0) - int(previous < 0) + 1)" if model=="prev_sign" else f"i % {int(model[-1])}"
    code.append(f"        state = {selector}")
    for i,expr in enumerate(expressions):
        code.append(("        if" if i==0 else "        elif")+f" state == {i}:")
        code.append(f"            a += {expr}")
    code+=["        previous = x","    return a",""]
    return "\n".join(code)


def bank(prior,banks,idx,memory=True):
    snap=json.loads(prior.read_text())[str(prev.SEEDS[idx])]
    if not memory:
        pool,_=h.build_pool("grammar",snap);return v4.Planner(pool)
    saved=json.loads(banks.read_text())[str(h.SEEDS[idx])]
    pool,_=h.build_pool("schema",snap);pool=h.add_layer(pool,v4.restore(saved))
    lesson,_=v4.lesson_rows("shape");pool=h.add_layer(pool,lesson)
    return v4.Planner(pool)


def fulfill(task,requests):
    # Benchmark-only environment; never called inside propose.
    return [dict(input=list(z),output=st.target(task,z)) for z in requests]


def episode(task,planner,policy,seed):
    start=time.perf_counter_ns();samples=[];history=[]
    for i in range(MAX_ROUNDS+1):
        result=propose(samples,planner,policy)
        if result["status"]!="needs_examples":break
        if i==MAX_ROUNDS or len(samples)+len(result["requests"])>MAX_SAMPLES:
            result=dict(status="sample_budget_exhausted");break
        history.append(dict(round=i+1,reason=result["reason"],count=len(result["requests"])))
        samples+=fulfill(task,result["requests"])
    p=result.get("program");checks=[]
    if p:
        for z in st.tests(seed):
            y=st.target(task,z)
            try:v=st.predict(p,z)
            except (ValueError,ZeroDivisionError):v=None
            checks.append([z,y,v])
    return dict(task=task,policy=policy,result=result,samples=samples,requests=history,checks=checks,
                success=p is not None and all(y==v for _,y,v in checks),emitted=p is not None,
                ns=time.perf_counter_ns()-start)


def metrics(rows):
    ok=sum(r["success"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=ok,wrong=emitted-ok,abstained=len(rows)-emitted,
                mean_samples=sum(len(r["samples"]) for r in rows)/len(rows),
                mean_rounds=sum(len(r["requests"]) for r in rows)/len(rows),mean_ns=sum(r["ns"] for r in rows)/len(rows))


def run(folder,prior,banks):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    seen=set();rows=[];exports=[];source=[]
    # Exclude signatures from V4.1, then keep only first five new cases per family.
    for seed in st.SEEDS:st.tasks(seed,seen)
    for idx,seed in enumerate(SEEDS):
        all_tasks=st.tasks(seed,seen);counts={f:0 for f in st.FAMILIES};tasks=[]
        for t in all_tasks:
            f=t["family"]
            if counts[f]<5:tasks.append(t);counts[f]+=1
        planners={k:bank(prior,banks,idx,k!="primitive") for k in ("primitive","memory")}
        frozen={k:h.sha(p.pool) for k,p in planners.items()}
        for n,t in enumerate(tasks):
            for policy in POLICIES:
                r=episode(t,planners["primitive" if policy=="primitive" else "memory"],policy,seed*17+n*641)
                rows.append(dict(seed=seed,**r))
                if policy=="memory" and r["emitted"]:
                    name=f"task_{len(exports)}";p=r["result"]["program"]
                    source.append(render(p,name));exports.append(dict(name=name,program=p,checks=r["checks"],task_id=t["id"],interpreter_success=r["success"]))
        assert frozen=={k:h.sha(p.pool) for k,p in planners.items()}
    result=dict(protocol="NUCLEO_V5-example-contract-v1",episodes=len(rows),seeds=SEEDS,exports=len(exports),
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metrics([r for r in rows if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in st.FAMILIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"generated.py").write_text("\n".join(source),encoding="utf-8")
    (folder/"export_checks.json").write_text(json.dumps(exports,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(v4.enc(r)+"\n")
    print("SUMMARY_V5="+v4.enc(result))


def cli(examples,folder,prior,banks,idx):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    samples=json.loads(examples.read_text(encoding="utf-8"))
    result=propose(samples,bank(prior,banks,idx),"memory")
    (folder/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    if result["status"]=="candidate":
        (folder/"solution.py").write_text(render(result["program"]),encoding="utf-8")
    elif result["status"]=="needs_examples":
        (folder/"requests.json").write_text(json.dumps([dict(input=z,output=None) for z in result["requests"]],indent=2),encoding="utf-8")
    print(result["status"])


class Tests(unittest.TestCase):
    def test_no_oracle(self):
        plan=v4.Planner([])
        r=propose([],plan);self.assertEqual(r["status"],"needs_examples")
        self.assertTrue(r["requests"])
    def test_invalid(self):
        with self.assertRaises(ValueError):checked_examples([dict(input=[1],output=2),dict(input=[1],output=3)])
    def test_render(self):
        p=dict(model="phase2",rules=[(h.ITEM,),(h.ABS,(h.ITEM,))])
        s=render(p);self.assertIn("i % 2",s);self.assertIn("abs(x)",s)
        with self.assertRaises(ValueError):render(p,"arbitrary()")
    def test_example_only(self):
        e=(h.ITEM,);p=v4.Planner([dict(expr=e,vec=h.vector(e),source={"kind":"test"})])
        t=dict(family="stateless",terms=((("linear",1,0),),),id="test")
        r=episode(t,p,"memory",1);self.assertTrue(r["success"]);self.assertLessEqual(len(r["samples"]),MAX_SAMPLES)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);p.add_argument("--banks",type=Path);p.add_argument("--examples",type=Path);p.add_argument("--memory-index",type=int,choices=range(4),default=0);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or not a.prior or not a.banks or ROOT not in a.output.resolve().parents:p.error("new output inside V5 and prior snapshots required")
    if a.examples:cli(a.examples,a.output,a.prior,a.banks,a.memory_index)
    else:run(a.output,a.prior,a.banks)
