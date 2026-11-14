"""V33: bounded, evidence-only teaching request/response protocol."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V30"))
import targeted_learning as l
t,m,v=l.t,l.m,l.v
SEEDS=(4800017,4830023,4860031,4890041)
POLICIES=("none","blind","verified","ideal")
OPS=tuple(sorted(t.ALLOWED))
CAP=6
VERSION="nucleo-teaching-v1"

def request(observations,registry):
    assert 1<=len(observations)<=16
    body=dict(version=VERSION,reason="no_unique_local_program",
        available_operations=list(v.OPS)+sorted(registry),
        allowed_primitives=list(OPS),max_proposals=4,max_steps=3,
        examples=[dict(input=list(x),output=list(y)) for x,y in observations])
    body["request_sha"]=m.digest(body)
    return body

def validate_request(req):
    if not isinstance(req,dict):raise ValueError("request object")
    body=dict(req);sha=body.pop("request_sha",None)
    if sha!=m.digest(body) or body.get("version")!=VERSION:raise ValueError("request integrity")
    if body.get("allowed_primitives")!=list(OPS):raise ValueError("primitive mismatch")
    examples=body.get("examples")
    if not isinstance(examples,list) or not 1<=len(examples)<=16:raise ValueError("example bounds")
    for example in examples:
        if not isinstance(example,dict) or set(example)!={"input","output"}:raise ValueError("example shape")
        for seq in example.values():
            if not isinstance(seq,list) or len(seq)>32 or any(type(z)!=int or abs(z)>100000 for z in seq):
                raise ValueError("invalid value")
    return [(tuple(z["input"]),tuple(z["output"])) for z in examples]

def validate_response(req,response):
    validate_request(req)
    if not isinstance(response,dict) or set(response)!={"version","request_sha","proposals"}:
        raise ValueError("response shape")
    if response["version"]!=VERSION or response["request_sha"]!=req["request_sha"]:
        raise ValueError("response binding")
    proposals=response["proposals"]
    if not isinstance(proposals,list) or len(proposals)>4:raise ValueError("proposal bounds")
    result=[]
    for p in proposals:
        if not isinstance(p,list) or not 1<=len(p)<=3 or not t.valid(p):
            raise ValueError("invalid proposal")
        p=tuple(p)
        if p not in result:result.append(p)
    return result

def teacher(req):
    """Deterministic teacher simulator; only observes request."""
    examples=validate_request(req);proposals=[];checks=0;examined=0
    for n in (1,2,3):
        for p in itertools.product(OPS,repeat=n):
            examined+=1
            for x,y in examples:
                checks+=1
                if t.module(p,x)!=y:break
            else:
                proposals.append(list(p))
            if len(proposals)==4:break
        if len(proposals)==4:break
    return dict(version=VERSION,request_sha=req["request_sha"],proposals=proposals),dict(examined=examined,checks=checks)

def choose_proposal(req,response,points,oracle,verify=True):
    proposals=validate_response(req,response);trace=[];chosen=None
    for p in proposals:
        matches=sum(t.module(p,x)==oracle(x) for x in points) if verify else None
        accepted=(not verify or matches==len(points)) and chosen is None
        trace.append(dict(program=p,matches=matches,tests=len(points) if verify else 0,accepted=accepted))
        if accepted:chosen=p
    return chosen,trace

def register(registry,p):
    name="skill_"+m.digest(p)[:20]
    if name in registry and registry[name]!=p:raise ValueError("skill collision")
    registry[name]=p
    return name

def supplement(initial,observed,trace,pool,ask):
    examples=list(zip(initial,observed))
    examples.extend((tuple(x["input"]),tuple(x["output"])) for x in trace)
    seen={x for x,y in examples};remaining=[x for x in pool if x not in seen]
    def dist(a,b):return 7*abs(len(a)-len(b))+sum(abs(x-y) for x,y in zip(a,b))
    for _ in range(min(6,len(remaining))):
        x=max(remaining,key=lambda p:min(dist(p,q) for q in seen))
        remaining.remove(x);seen.add(x);examples.append((x,ask(x)))
    return examples,len(examples)-len(initial)-len(trace)

def acquisition(seed,points):
    rng=random.Random(seed^0x3311)
    tasks=[dict(id=f"{seed}/direct/{i}",stratum="direct",program=(name,)) for i,name in enumerate(t.NAMES)]
    seen={tuple(t.target(z["program"],x) for x in points) for z in tasks}
    candidates=list(v.FULL[1:]);rng.shuffle(candidates)
    for p in candidates:
        sig=tuple(t.target(p,x) for x in points)
        if sig in seen:continue
        seen.add(sig);tasks.append(dict(id=f"{seed}/basic/{len(tasks)-6}",stratum="basic",program=p))
        if len(tasks)==12:break
    assert len(tasks)==12;rng.shuffle(tasks);return tasks

def attempt(goal,initial,pool,held,registry,seed):
    prepared,prep=l.prepare(registry,initial,pool)
    ask=lambda x:t.target(goal,x);obs=tuple(ask(x) for x in initial)
    row=l.investigate(initial,obs,pool,ask,registry,prepared,seed)
    row["success"]=l.score(row,goal,held,registry)
    row["preparation_executions"]=prep["executions"]
    return row

def acquire(policy,seed,tasks,initial,pool,held,teaching):
    registry={};rows=[];requests=[]
    for i,task in enumerate(tasks):
        goal=task["program"];ask=lambda x:t.target(goal,x)
        first=attempt(goal,initial,pool,held,registry,seed+i*701)
        last=first;extra=0;cost=dict(examined=0,checks=0);tests=0
        if not first["emitted"] and policy!="none" and len(requests)<CAP:
            obs=tuple(ask(x) for x in initial)
            examples,extra=supplement(initial,obs,first["trace"],pool,ask)
            req=request(examples,registry);response,cost=teacher(req)
            p,trace=choose_proposal(req,response,teaching,ask,policy=="verified")
            tests=sum(z["tests"] for z in trace)
            name=register(registry,p) if p is not None else None
            requests.append(dict(seed=seed,policy=policy,task=task["id"],request=req,response=response,
                trace=trace,skill=name,accepted=p,teacher_cost=cost,supplemental_queries=extra))
            if name is not None:last=attempt(goal,initial,pool,held,registry,seed+i*701)
        retry=last is not first
        rows.append(dict(seed=seed,policy=policy,task=task,success=last["success"],emitted=last["emitted"],
            first=first,retry=last if retry else None,teacher_checks=cost["checks"],teacher_examined=cost["examined"],
            teaching_tests=tests,queries=first["queries"]+extra+(last["queries"] if retry else 0),
            comparisons=first["comparisons"]+(last["comparisons"] if retry else 0),
            preparation_executions=first["preparation_executions"]+(last["preparation_executions"] if retry else 0),
            wall_ns=first["wall_ns"]+(last["wall_ns"] if retry else 0)))
    return registry,rows,requests

def freeze(path,registry):
    body=dict(registry=registry);body["sha"]=m.digest(body)
    path.write_text(m.enc(body),encoding="utf-8")
    rec=json.loads(path.read_text());sha=rec.pop("sha")
    assert sha==m.digest(rec)
    result={k:tuple(p) for k,p in rec["registry"].items()}
    assert result==registry and all(t.valid(p) for p in result.values())
    return result,sha

def metrics(rr):
    correct=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
    return dict(n=len(rr),correct=correct,wrong=em-correct,abstained=len(rr)-em,
        **{k:sum(r.get(k,0) for r in rr) for k in ("queries","comparisons","preparation_executions","teacher_checks","teacher_examined","teaching_tests","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];requests=[];snapshots=[]
    packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text())
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed);points=(*initial,*pool,*held)
        fi,fp,fh=l.final_inputs(seed,points)
        teaching=t.teaching_points(seed,(*points,*fi,*fp,*fh))
        tasks=acquisition(seed,points)
        registries={}
        for policy in POLICIES[:-1]:
            registry,rr,req=acquire(policy,seed,tasks,initial,pool,held,teaching)
            frozen,sha=freeze(out/f"skills_{seed}_{policy}.json",registry)
            registries[policy]=frozen;training.extend(rr);requests.extend(req)
            snapshots.append(dict(seed=seed,policy=policy,skills=len(frozen),requests=len(req),sha=sha,registry=frozen))
        ideal={}
        for lesson in packet["lessons"]:register(ideal,tuple(lesson["proposals"][0]))
        registries["ideal"]=ideal
        final=t.suite(seed,(*fi,*fp,*fh))
        for policy,registry in registries.items():
            before=m.digest(registry)
            for i,task in enumerate(final):
                rr=attempt(task["program"],fi,fp,fh,registry,seed+i*971)
                rows.append(dict(seed=seed,policy=policy,task=task,**rr))
            assert m.digest(registry)==before
    result=dict(protocol="V33-evidence-teaching-v1",teacher="enumerative simulator, no live AI",seeds=SEEDS,snapshots=snapshots,
        acquisition=[dict(policy=p,**metrics([r for r in training if r["policy"]==p]),
          requests=sum(r["policy"]==p for r in requests)) for p in POLICIES[:-1]],
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=z,**metrics([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for p in POLICIES for z in ("direct","composed","basic")],
        by_seed=[dict(policy=p,seed=s,**metrics([r for r in rows if r["policy"]==p and r["seed"]==s])) for p in POLICIES for s in SEEDS])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("acquisition",training),("requests",requests)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_protocol(self):
        points=[(),(1,-2,3),(2,2),(-3,)]
        req=request([(x,(sum(x),)) for x in points],{})
        response,cost=teacher(req)
        self.assertTrue(validate_response(req,response))
        p,trace=choose_proposal(req,response,[(2,3,-1)],lambda x:(sum(x),))
        self.assertIsNotNone(p)
        bad=dict(response,request_sha="wrong")
        with self.assertRaises(ValueError):validate_response(req,bad)
        bad=dict(response,proposals=[["unknown"]])
        with self.assertRaises(ValueError):validate_response(req,bad)
    def test_inputs(self):
        for seed in SEEDS:
            a,b,c=v.input_sets(seed);points=(*a,*b,*c)
            self.assertEqual(len(acquisition(seed,points)),12)
            d,e,f=l.final_inputs(seed,points);other=(*d,*e,*f)
            self.assertFalse(set(points)&set(other))
            self.assertFalse(set(t.teaching_points(seed,(*points,*other)))&(set(points)|set(other)))
            self.assertEqual(len(t.suite(seed,other)),24)
    def test_supplement(self):
        a,b,c=v.input_sets(SEEDS[0]);ask=lambda x:(sum(x),)
        examples,n=supplement(a,tuple(ask(x) for x in a),[],b,ask)
        self.assertEqual(n,6);self.assertEqual(len(examples),10)
        self.assertFalse({x for x,y in examples}&set(c))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V33 required")
    run(z.output)
