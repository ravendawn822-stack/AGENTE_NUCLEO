"""V37: bounded integrated perception, teaching, skill retention and policy review."""
import argparse,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V36"))
import recovery as rec
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V33"))
import teaching_protocol as teach
rw,envmod=rec.v,rec.v.v
l,t,m,v=teach.l,teach.t,teach.m,teach.v
SEEDS=(5280017,5310023,5340031,5370041)
POLICIES=("local","resources","teacher","integrated","review")
REQUEST_CAP=6

def save_state(directory,registry,requests,cursor,source):
    record=dict(registry=registry,requests=requests,cursor=cursor,source_sha=m.digest(source))
    record["sha"]=m.digest(record)
    pending=directory/"state.pending.json";path=directory/"state.json"
    pending.write_text(m.enc(record),encoding="utf-8");pending.replace(path)
    loaded=json.loads(path.read_text(encoding="utf-8"));sha=loaded.pop("sha")
    assert m.digest(loaded)==sha and loaded["source_sha"]==m.digest(source)
    frozen={k:tuple(p) for k,p in loaded["registry"].items()}
    assert frozen==registry and all(t.valid(p) for p in frozen.values())
    assert loaded["requests"]==requests and loaded["cursor"]==cursor
    return frozen,sha

def attempt(initial,observed,pool,ask,registry,seed):
    prepared,prep=l.prepare(registry,initial,pool)
    r=l.investigate(initial,observed,pool,ask,registry,prepared,seed)
    return dict(**r,preparation_executions=prep["executions"])

def route(model,initial,observed,trace):
    evidence=list(zip(initial,observed))+[(tuple(r["input"]),tuple(r["output"])) for r in trace]
    possible=[name for name in envmod.NAMES if all(t.oracle(name,x)==y for x,y in evidence)]
    # Require a single compatible reference behavior, not just one available resource.
    if len(possible)!=1:return None
    return envmod.route(model,possible[0])

def world(seed,policy,source,registry,requests,training):
    initial,pool,held=v.input_sets(seed);public=(*initial,*pool)
    teacher_points=t.teaching_points(seed,(*public,*held))
    env=envmod.Environment(seed,public,held)
    model={};perception_cost=0
    if policy in ("resources","integrated","review"):
        model,perception_cost=rw.perceive(env.list_resources(),env.probe,public,source)
    rows=[];lessons=[]
    tasks=t.suite(seed,(*public,*held))
    before=m.digest(registry)
    for i,task in enumerate(tasks):
        goal=task["program"];ask=lambda x:t.target(goal,x)
        observed=tuple(ask(x) for x in initial)
        first=attempt(initial,observed,pool,ask,registry,seed+i*971)
        last=first;chosen_route=None;extra=0;teacher_checks=0;teaching_tests=0
        if not first["emitted"] and model:
            chosen_route=route(model,initial,observed,first["trace"])
        if not first["emitted"] and chosen_route is None and training and policy in ("teacher","integrated","review") and requests<REQUEST_CAP:
            examples,extra=teach.supplement(initial,observed,first["trace"],pool,ask)
            req=teach.request(examples,registry);response,cost=teach.teacher(req)
            p,trace=teach.choose_proposal(req,response,teacher_points,ask,True)
            teacher_checks=cost["checks"];teaching_tests=sum(z["tests"] for z in trace)
            requests+=1;name=teach.register(registry,p) if p is not None else None
            lessons.append(dict(task=task["id"],request=req,response=response,trace=trace,
                                skill=name,teacher_cost=cost,supplemental_queries=extra))
            if name is not None:last=attempt(initial,observed,pool,ask,registry,seed+i*971)
        # Evaluation remains outside the selection logic.
        if chosen_route is not None:
            match=0
            for x in held:
                reply=env.evaluate_route(chosen_route,x)
                match+=reply["status"]=="ok" and reply["output"]==ask(x)
            success=match==len(held);origin="resource";emitted=True
        elif last["emitted"]:
            success=l.score(last,goal,held,registry);origin="local";emitted=True
        else:success=False;origin="none";emitted=False
        retry=last is not first
        rows.append(dict(seed=seed,policy=policy,phase="acquisition" if training else "final",
          task=task,origin=origin,resource=chosen_route,success=success,emitted=emitted,
          first=first,retry=last if retry else None,
          queries=first["queries"]+extra+(last["queries"] if retry else 0),
          comparisons=first["comparisons"]+(last["comparisons"] if retry else 0),
          preparation_executions=first["preparation_executions"]+(last["preparation_executions"] if retry else 0),
          teacher_checks=teacher_checks,teaching_tests=teaching_tests))
    if not training:assert not lessons and m.digest(registry)==before
    assert requests<=REQUEST_CAP and env.probe_count<=40
    # Resource truth is accessed solely for evaluator diagnostics after all decisions.
    truth=env.evaluator_truth()
    classified=sum(row["state"]==("identified" if truth[r] in envmod.NAMES else "unavailable" if truth[r]=="unavailable" else "unknown")
                   and (row["state"]!="identified" or row["identity"]==truth[r]) for r,row in model.items())
    return rows,registry,requests,dict(seed=seed,policy=policy,training=training,model=model,
        probes=env.probe_count,perception_cost=perception_cost,classified=classified,
        evaluation_calls=env.route_count,lessons=lessons,source_sha=m.digest(source))

def metrics(rows):
    ok=sum(r["success"] for r in rows);em=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=ok,wrong=em-ok,abstained=len(rows)-em,
        local_correct=sum(r["success"] and r["origin"]=="local" for r in rows),
        resource_correct=sum(r["success"] and r["origin"]=="resource" for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("queries","comparisons","preparation_executions","teacher_checks","teaching_tests")})

def revise(directory,seed,proposals,gate):
    start=time.perf_counter_ns()
    candidate,cache,trail=rw.search(lambda src:rw.episodes(src,proposals,"proposal"),seed^0x3711)
    trial_rows=[row for group in cache.values() for row in group]
    event=None
    if candidate!=rw.BASE:
        active,event=rec.monitored_update(directory,candidate,gate,[])
    else:active=rw.load(directory/"active.json")
    return active,dict(candidate=candidate,active=active,source_sha=m.digest(active),trail=trail,
        trials=len(cache),proposal_metrics=rw.metrics(trial_rows),event=event,
        wall_ns=time.perf_counter_ns()-start)

def experiment(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];worlds=[];snapshots=[];reviews=[]
    for replica in SEEDS:
        seeds=tuple(replica+1009*i for i in range(1,11))
        acquisition=seeds[:2];proposals=seeds[2:5];gate=seeds[5:8];final=seeds[8:]
        for policy in POLICIES:
            directory=out/f"{replica}_{policy}";source=rw.install(directory,rw.BASE)
            registry={};requests=0
            for cursor,seed in enumerate((*acquisition,*final)):
                training=cursor<2
                rr,registry,requests,report=world(seed,policy,source,registry,requests,training)
                rows.extend(dict(replica=replica,**r) for r in rr)
                worlds.append(dict(replica=replica,**report))
                if cursor==0 and policy=="review" and report["probes"]>0:
                    source,review=revise(directory,replica,proposals,gate)
                    reviews.append(dict(replica=replica,**review))
                source=rw.load(directory/"active.json")
                registry,sha=save_state(directory,registry,requests,cursor+1,source)
                snapshots.append(dict(replica=replica,policy=policy,cursor=cursor+1,
                    skills=len(registry),requests=requests,sha=sha,source_sha=m.digest(source)))
            assert requests<=REQUEST_CAP
    final=[r for r in rows if r["phase"]=="final"]
    result=dict(protocol="V37-integrated-cycle-v1",seeds=SEEDS,snapshots=snapshots,reviews=reviews,
        aggregate=[dict(policy=p,**metrics([r for r in final if r["policy"]==p])) for p in POLICIES],
        acquisition=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p and r["phase"]=="acquisition"])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=z,**metrics([r for r in final if r["policy"]==p and r["task"]["stratum"]==z])) for p in POLICIES for z in ("direct","composed","basic")],
        by_replica=[dict(replica=s,policy=p,**metrics([r for r in final if r["replica"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES],
        environment_cost=[dict(policy=p,phase=phase,**{k:sum(w[k] for w in worlds if w["policy"]==p and w["training"]==(phase=="acquisition")) for k in ("probes","perception_cost","classified","evaluation_calls")},
          requests=sum(len(w["lessons"]) for w in worlds if w["policy"]==p and w["training"]==(phase=="acquisition"))) for p in POLICIES for phase in ("acquisition","final")])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for key,data in (("raw",rows),("worlds",worlds)):
        with (out/(key+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(m.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_seeds(self):
        self.assertEqual(len({s+1009*i for s in SEEDS for i in range(1,11)}),40)
    def test_route(self):
        a,b,c=v.input_sets(SEEDS[0]);observed=tuple(t.oracle("total",x) for x in a)
        model={"abc":dict(state="identified",identity="total",trace=[])}
        self.assertEqual(route(model,a,observed,[]),"abc")
        self.assertIsNone(route({},a,observed,[]))
    def test_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);registry={"skill":("sum",)}
            frozen,sha=save_state(p,registry,1,2,rw.BASE)
            self.assertEqual(frozen,registry)
            self.assertEqual(json.loads((p/"state.json").read_text())["sha"],sha)
    def test_world(self):
        rr,registry,requests,report=world(SEEDS[0],"local",rw.BASE,{},0,False)
        self.assertEqual(len(rr),24);self.assertEqual(requests,0);self.assertEqual(registry,{})
        self.assertEqual(report["probes"],0);self.assertFalse(report["lessons"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V37 required")
    experiment(z.output)
