"""V32: empirical perception of opaque resources in a pure simulated environment."""
import argparse,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V29"))
import teacher_learning as t
m,v=t.m,t.v
SEEDS=(4560017,4590023,4620031,4650041,4680053,4710059,4740061,4770067)
NAMES=(*t.NAMES,"sort","reverse")
POLICIES=("none","one","fixed","random","adaptive")
PROBE_CAP=4

def behavior(name,x):
    if name=="almost_total":return (sum(x)+int(len(x)>=5),)
    if name=="almost_prefix":
        y=t.oracle("prefix",x)
        return tuple(z+1 for z in y) if x and x[0]<0 else y
    if name in NAMES:return t.oracle(name,x)
    raise ValueError(name)

class Environment:
    """Only the authorized, deterministic list simulator. No host operations."""
    def __init__(self,seed,public,reserved):
        rng=random.Random(seed^0x3211)
        selected=rng.sample(NAMES,6)
        roles=[*selected,"unavailable","unavailable","almost_total","almost_prefix"]
        rng.shuffle(roles)
        ids=[f"resource_{rng.getrandbits(48):012x}" for _ in roles]
        assert len(set(ids))==10
        self._roles=dict(zip(ids,roles));self._public=set(public);self._reserved=set(reserved)
        self._probes={k:set() for k in ids};self.probe_count=0;self.route_count=0
        self._unavailable_seen=set()
    def list_resources(self):return tuple(self._roles)
    def probe(self,resource,x):
        assert resource in self._roles and x in self._public
        assert resource not in self._unavailable_seen
        assert len(self._probes[resource])<PROBE_CAP and x not in self._probes[resource]
        self._probes[resource].add(x);self.probe_count+=1
        role=self._roles[resource]
        if role=="unavailable":
            self._unavailable_seen.add(resource)
            return dict(status="unavailable")
        return dict(status="ok",output=behavior(role,x))
    def evaluate_route(self,resource,x):
        assert resource in self._roles and x in self._reserved
        self.route_count+=1
        role=self._roles[resource]
        if role=="unavailable":return dict(status="unavailable")
        return dict(status="ok",output=behavior(role,x))
    def evaluator_truth(self):return dict(self._roles)

def distance(x,y):
    return 7*abs(len(x)-len(y))+sum(abs(a-b) for a,b in zip(x,y))

def perceive(ids,probe,public,policy,seed):
    cap=0 if policy=="none" else 1 if policy=="one" else PROBE_CAP
    rng=random.Random(seed^0x3222);model={};cost=0
    # Predictions are based on known descriptions, not hidden resource labels.
    predicted={}
    if cap:
        for name in NAMES:
            for x in public:
                predicted[name,x]=t.oracle(name,x);cost+=1
    for resource in ids:
        candidates=list(NAMES);remaining=list(public);observed=[];trace=[]
        state="unprobed"
        for _ in range(cap):
            if policy=="random":x=rng.choice(remaining)
            elif policy=="adaptive":
                if len(candidates)>1:
                    def score(point):
                        nonlocal cost
                        counts={}
                        for name in candidates:
                            y=predicted[name,point];counts[y]=counts.get(y,0)+1;cost+=1
                        return len(candidates)**2-sum(z*z for z in counts.values())
                    x=max(remaining,key=score)
                elif observed:x=max(remaining,key=lambda point:min(distance(point,old) for old in observed))
                else:x=remaining[0]
            else:x=remaining[0]
            remaining.remove(x);result=probe(resource,x);before=len(candidates)
            if result["status"]=="unavailable":
                candidates=[];state="unavailable"
                trace.append(dict(input=x,response=result,before=before,after=0));break
            assert result["status"]=="ok"
            y=result["output"];observed.append(x)
            cost+=len(candidates)
            candidates=[name for name in candidates if predicted[name,x]==y]
            trace.append(dict(input=x,response=result,before=before,after=len(candidates)))
            state="unknown" if not candidates else "identified" if len(candidates)==1 else "ambiguous"
            if not candidates:break
        model[resource]=dict(state=state,identity=candidates[0] if state=="identified" else None,
                             candidates=candidates,trace=trace)
    return model,cost

def save(path,model):
    record=dict(model=model);record["sha"]=m.digest(record)
    path.write_text(m.enc(record),encoding="utf-8")
    loaded=json.loads(path.read_text());sha=loaded.pop("sha")
    assert m.digest(loaded)==sha
    return loaded["model"],sha

def route(model,goal):
    eligible=[r for r,row in model.items() if row["state"]=="identified" and row["identity"]==goal]
    return min(eligible,key=lambda r:(-len(model[r]["trace"]),r)) if eligible else None

def evaluate(env,model,reserved,seed,policy):
    truth=env.evaluator_truth();resources=[];goals=[]
    for resource,role in truth.items():
        row=model[resource];state=row["state"]
        expected="identified" if role in NAMES else "unavailable" if role=="unavailable" else "unknown"
        correct=state==expected and (expected!="identified" or row["identity"]==role)
        resources.append(dict(seed=seed,policy=policy,resource=resource,truth=role,expected_state=expected,
            state=state,identity=row["identity"],correct=correct,false_identity=state=="identified" and row["identity"]!=role,
            queries=len(row["trace"])))
    for goal in NAMES:
        resource=route(model,goal);present=goal in truth.values()
        counter_before=env.route_count;match=0
        if resource is not None:
            for x in reserved:
                response=env.evaluate_route(resource,x)
                match+=response["status"]=="ok" and response["output"]==t.oracle(goal,x)
        correct=resource is not None and match==len(reserved)
        goals.append(dict(seed=seed,policy=policy,goal=goal,present=present,resource=resource,
            true_role=truth.get(resource),success=correct,emitted=resource is not None,
            appropriate_abstention=resource is None and not present,matches=match,
            evaluation_calls=env.route_count-counter_before))
    return resources,goals

def metric(rr):
    ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
    return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
        appropriate_abstention=sum(r["appropriate_abstention"] for r in rr),
        evaluation_calls=sum(r["evaluation_calls"] for r in rr))

def run(out):
    out.mkdir(parents=True,exist_ok=False);resources=[];goals=[];snapshots=[]
    for seed in SEEDS:
        a,b,held=v.input_sets(seed);public=(*a,*b)
        for policy in POLICIES:
            env=Environment(seed,public,held)
            start=time.perf_counter_ns()
            model,cost=perceive(env.list_resources(),env.probe,public,policy,seed)
            elapsed=time.perf_counter_ns()-start
            frozen,sha=save(out/f"model_{seed}_{policy}.json",model)
            assert m.enc(frozen)==m.enc(model)
            rr,gg=evaluate(env,frozen,held,seed,policy)
            assert env.probe_count==sum(r["queries"] for r in rr)<=40
            snapshots.append(dict(seed=seed,policy=policy,sha=sha,probes=env.probe_count,
                predicted_or_compared=cost,wall_ns=elapsed,
                identified=sum(r["state"]=="identified" for r in rr),
                false_identity=sum(r["false_identity"] for r in rr)))
            resources.extend(rr);goals.extend(gg)
    result=dict(protocol="V32-resource-perception-v1",seeds=SEEDS,snapshots=snapshots,
        aggregate=[dict(policy=p,**metric([g for g in goals if g["policy"]==p])) for p in POLICIES],
        resource_classification=[dict(policy=p,n=len(rr),correct=sum(r["correct"] for r in rr),
            false_identity=sum(r["false_identity"] for r in rr),probes=sum(r["queries"] for r in rr),
            states={z:sum(r["state"]==z for r in rr) for z in ("identified","unavailable","unknown","ambiguous","unprobed")})
            for p in POLICIES for rr in [[r for r in resources if r["policy"]==p]]],
        by_presence=[dict(policy=p,present=present,**metric([g for g in goals if g["policy"]==p and g["present"]==present]))
            for p in POLICIES for present in (True,False)],
        by_seed=[dict(seed=s,policy=p,**metric([g for g in goals if g["seed"]==s and g["policy"]==p])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("resources",resources),("goals",goals)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for row in data:f.write(m.enc(row)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_environment(self):
        a,b,c=v.input_sets(SEEDS[0]);public=(*a,*b)
        env=Environment(SEEDS[0],public,c)
        truth=env.evaluator_truth();self.assertEqual(len(truth),10)
        self.assertEqual(sum(z in NAMES for z in truth.values()),6)
        self.assertEqual(sum(z=="unavailable" for z in truth.values()),2)
        resource=next(r for r,z in truth.items() if z=="unavailable")
        self.assertEqual(env.probe(resource,public[0]),{"status":"unavailable"})
        with self.assertRaises(AssertionError):env.probe(resource,public[1])
        with self.assertRaises(AssertionError):env.probe(next(iter(truth)),c[0])
    def test_models(self):
        a,b,c=v.input_sets(SEEDS[0]);public=(*a,*b)
        for policy in POLICIES:
            env=Environment(SEEDS[0],public,c)
            model,cost=perceive(env.list_resources(),env.probe,public,policy,SEEDS[0])
            self.assertLessEqual(env.probe_count,40)
            for row in model.values():
                points=[r["input"] for r in row["trace"]]
                self.assertEqual(len(set(points)),len(points))
                self.assertFalse(set(points)&set(c))
                if row["state"]=="identified":self.assertEqual(len(row["candidates"]),1)
            rr,gg=evaluate(env,model,c,SEEDS[0],policy)
            self.assertEqual((len(rr),len(gg)),(10,8))
            self.assertEqual(sum(r["present"] for r in gg),6)
            if policy=="none":self.assertEqual(sum(r["emitted"] for r in gg),0)
    def test_persistence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"model.json"
            model={"a":{"state":"identified","identity":"sort","trace":[]}}
            loaded,sha=save(path,model)
            self.assertEqual(loaded,model);self.assertEqual(route(loaded,"sort"),"a")
            self.assertIsNone(route(loaded,"reverse"))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V32 required")
    run(z.output)
