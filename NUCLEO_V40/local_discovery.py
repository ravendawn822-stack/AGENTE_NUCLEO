"""V40: bounded local symbolic discovery before an enumerative teacher."""
import argparse,itertools,json,sys,time,unittest,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V33"))
import teaching_protocol as q
l,t,m,v=q.l,q.t,q.m,q.v
SEEDS=(5460017,5490023,5520031,5550041)
POLICIES=("baseline","teacher_only","hybrid","local_full")
SHORT=17+17**2
FULL=SHORT+17**3
PROTOCOL="V40-local-first-v1"

def search(req,budget):
    """Inputs are observations and allowed primitives, never target identity."""
    examples=q.validate_request(req)
    if not 0<=budget<=FULL:raise ValueError("candidate budget")
    examined=checks=0;proposals=[]
    candidates=(p for n in (1,2,3) for p in itertools.product(q.OPS,repeat=n))
    status="budget"
    for p in itertools.islice(candidates,budget):
        examined+=1
        for x,y in examples:
            checks+=1
            if t.module(p,x)!=y:break
        else:proposals.append(list(p))
        if len(proposals)==4:
            status="proposal_cap";break
    else:
        if examined==FULL:status="exhausted"
    response=dict(version=q.VERSION,request_sha=req["request_sha"],proposals=proposals)
    return response,dict(examined=examined,checks=checks,status=status)

def verify(req,response,points,ask):
    """Evaluator has independent feedback; it returns only proposal and trace."""
    examples=q.validate_request(req)
    candidates=q.validate_response(req,response)
    # Each validation point is observed once per verification batch.
    expected=tuple(ask(x) for x in points) if candidates else ()
    selected=None;trace=[]
    for p in candidates:
        public=sum(t.module(p,x)==y for x,y in examples)
        tests=len(points) if public==len(examples) else 0
        matches=sum(t.module(p,x)==y for x,y in zip(points,expected)) if tests else 0
        accepted=public==len(examples) and tests==len(points) and matches==tests and selected is None
        if accepted:selected=p
        trace.append(dict(program=p,public_matches=public,public_tests=len(examples),
                          matches=matches,tests=tests,accepted=accepted))
    return selected,trace,len(expected)

def discover(policy,req,validate):
    """The caller provides a bounded teaching verifier, not a target name."""
    stages=[];selected=None
    if policy in ("hybrid","local_full"):
        response,cost=search(req,SHORT if policy=="hybrid" else FULL)
        selected,trace,n=validate(req,response)
        stages.append(dict(source="local",response=response,cost=cost,validation=trace,validation_observations=n))
    if selected is None and policy in ("teacher_only","hybrid"):
        response,cost=q.teacher(req)
        selected,trace,n=validate(req,response)
        cost=dict(cost,status="proposal_cap" if len(response["proposals"])==4 else "exhausted")
        stages.append(dict(source="simulated_teacher",response=response,cost=cost,validation=trace,validation_observations=n))
    return selected,stages

def observation_oracle(task):
    # Evaluator-only construction. The solver never receives this label.
    goal=tuple(task["program"])
    if goal==("control_square",):return lambda x:tuple(z*z for z in x)
    if goal==("control_duplicate",):return lambda x:tuple(x)+tuple(x)
    return lambda x:t.target(goal,x)

def controls(seed,phase):
    return [dict(id=f"{seed}/{phase}/control/{i}",stratum="control",program=(name,))
            for i,name in enumerate(("control_square","control_duplicate"))]

def episode(initial,pool,ask,registry,seed):
    prepared,prep=l.prepare(registry,initial,pool)
    observed=tuple(ask(x) for x in initial)
    row=l.investigate(initial,observed,pool,ask,registry,prepared,seed)
    row["preparation_executions"]=prep["executions"]
    row["initial_observations"]=len(initial)
    return row,observed

def score(row,held,ask,registry):
    return bool(row["program"] is not None and all(t.execute(row["program"],x,registry)==ask(x) for x in held))

def acquire(policy,seed,tasks,initial,pool,held,teaching):
    registry={};rows=[];records=[]
    for i,task in enumerate(tasks):
        ask=observation_oracle(task);epseed=seed+i*701
        first,observed=episode(initial,pool,ask,registry,epseed)
        last=first;retry=None;extra=0;selected=None;stages=[];req=None
        gap=not first["emitted"]
        if gap and policy!="baseline":
            examples,extra=q.supplement(initial,observed,first["trace"],pool,ask)
            req=q.request(examples,registry)
            validator=lambda request,response:verify(request,response,teaching,ask)
            selected,stages=discover(policy,req,validator)
            if selected is not None:
                skill=q.register(registry,selected)
                retry,_=episode(initial,pool,ask,registry,epseed);last=retry
            else:skill=None
            records.append(dict(seed=seed,policy=policy,task=task["id"],request=req,
                                stages=stages,accepted=selected,skill=skill))
        # Only now score against evaluator-reserved data. Never use score for routing.
        success=score(last,held,ask,registry)
        local=[s for s in stages if s["source"]=="local"]
        teacher=[s for s in stages if s["source"]=="simulated_teacher"]
        rows.append(dict(seed=seed,policy=policy,task=task,success=success,
            emitted=last["emitted"],program=last["program"],gap=gap,
            learned=selected is not None,unresolved_gap=gap and selected is None,
            discovery_source=stages[-1]["source"] if selected is not None else None,
            local_status=local[0]["cost"]["status"] if local else None,
            teacher_requests=len(teacher),would_request_broader=policy=="local_full" and gap and selected is None,
            local_examined=sum(s["cost"]["examined"] for s in local),
            local_checks=sum(s["cost"]["checks"] for s in local),
            teacher_examined=sum(s["cost"]["examined"] for s in teacher),
            teacher_checks=sum(s["cost"]["checks"] for s in teacher),
            verification_public_checks=sum(z["public_tests"] for s in stages for z in s["validation"]),
            teaching_tests=sum(z["tests"] for s in stages for z in s["validation"]),
            teaching_observations=sum(s["validation_observations"] for s in stages),
            queries=first["queries"]+extra+(retry["queries"] if retry else 0),
            initial_observations=first["initial_observations"]+(retry["initial_observations"] if retry else 0),
            comparisons=first["comparisons"]+(retry["comparisons"] if retry else 0),
            preparation_executions=first["preparation_executions"]+(retry["preparation_executions"] if retry else 0),
            first=first,retry=retry))
    return registry,rows,records

def final_rows(policy,seed,tasks,initial,pool,held,registry):
    before=m.digest(registry);rows=[]
    for i,task in enumerate(tasks):
        ask=observation_oracle(task)
        row,_=episode(initial,pool,ask,registry,seed+i*971)
        success=score(row,held,ask,registry)
        rows.append(dict(seed=seed,policy=policy,task=task,success=success,**row))
    if m.digest(registry)!=before:raise RuntimeError("final registry changed")
    return rows

COUNTS=("queries","initial_observations","comparisons","preparation_executions",
        "gap","learned","unresolved_gap","teacher_requests","would_request_broader",
        "local_examined","local_checks","teacher_examined","teacher_checks",
        "verification_public_checks","teaching_tests","teaching_observations")
def metrics(rows):
    correct=sum(r["success"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
                **{k:sum(r.get(k,0) for r in rows) for k in COUNTS})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);training=[];records=[];final=[];snapshots=[]
    for seed in seeds:
        initial,pool,held=v.input_sets(seed);acq_points=(*initial,*pool,*held)
        fi,fp,fh=l.final_inputs(seed,acq_points);final_points=(*fi,*fp,*fh)
        teaching=t.teaching_points(seed,(*acq_points,*final_points))
        assert len(teaching)==24 and not set(teaching)&set((*acq_points,*final_points))
        tasks=(*q.acquisition(seed,acq_points),*controls(seed,"acquisition"))
        tests=(*t.suite(seed,final_points),*controls(seed,"final"))
        for policy in POLICIES:
            registry,rows,reqs=acquire(policy,seed,tasks,initial,pool,held,teaching)
            frozen,sha=q.freeze(out/f"skills_{seed}_{policy}.json",registry)
            snapshots.append(dict(seed=seed,policy=policy,skills=len(frozen),sha=sha,registry=frozen))
            training.extend(rows);records.extend(reqs)
            final.extend(final_rows(policy,seed,tests,fi,fp,fh,frozen))
    body=dict(protocol=PROTOCOL,seeds=seeds,local_budgets=dict(hybrid=SHORT,local_full=FULL),
        teacher="enumerative simulator V33; no model calls",snapshots=snapshots,
        acquisition=[dict(policy=p,**metrics([r for r in training if r["policy"]==p])) for p in POLICIES],
        aggregate=[dict(policy=p,**metrics([r for r in final if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metrics([r for r in final if r["policy"]==p and r["task"]["stratum"]==s]))
                    for p in POLICIES for s in ("direct","composed","basic","control")],
        acquisition_by_stratum=[dict(policy=p,stratum=s,**metrics([r for r in training if r["policy"]==p and r["task"]["stratum"]==s]))
                    for p in POLICIES for s in ("direct","basic","control")],
        by_seed=[dict(seed=seed,policy=p,**metrics([r for r in final if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(body,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    for name,data in (("training",training),("requests",records),("final",final)):
        (out/(name+".jsonl")).write_text("".join(m.enc(row)+"\n" for row in data),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,acquisition=body["acquisition"],aggregate=body["aggregate"]),indent=2))
    return body

class Tests(unittest.TestCase):
    def test_local_span(self):
        examples=[(x,t.oracle("span",x)) for x in ((),(1,),(-3,2,1),(4,4,-1),(-3,-3,-3))]
        req=q.request(examples,{})
        response,cost=search(req,FULL)
        expected,old=q.teacher(req)
        self.assertEqual(response,expected);self.assertEqual(cost["examined"],old["examined"])
        selected,trace,n=verify(req,response,((1,3),(-6,2,6)),lambda x:t.oracle("span",x))
        self.assertEqual(selected,("bounds","difference"))
        self.assertEqual(n,2)
    def test_public_gate(self):
        req=q.request([((1,), (2,))],{})
        response=dict(version=q.VERSION,request_sha=req["request_sha"],proposals=[["abs"]])
        selected,trace,_=verify(req,response,((2,),),lambda x:x)
        self.assertIsNone(selected);self.assertEqual(trace[0]["tests"],0)
    def test_budget_and_representability(self):
        req=q.request([((2,3),(4,9)),((3,-2),(9,4)),((5,), (25,))],{})
        _,cost=search(req,SHORT);self.assertLessEqual(cost["examined"],SHORT)
        response,cost=search(req,FULL)
        self.assertEqual(response["proposals"],[]);self.assertEqual(cost["status"],"exhausted")
        self.assertEqual(cost["examined"],FULL)
    def test_offline_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            body=run(Path(d)/"case",SEEDS[:1])
            self.assertEqual(len(body["aggregate"]),4)
            self.assertTrue(all(r["n"]==26 for r in body["aggregate"]))
            by={r["policy"]:r for r in body["acquisition"]}
            self.assertEqual(by["local_full"]["teacher_requests"],0)
            self.assertEqual(by["baseline"]["learned"],0)
            self.assertLessEqual(by["hybrid"]["teacher_requests"],by["teacher_only"]["teacher_requests"]+14)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true")
    p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None:p.error("--output required")
    out=a.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V40 required")
    run(out)

if __name__=="__main__":main()
