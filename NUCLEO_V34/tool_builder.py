"""V34: synthesize, validate, persist, and compose bounded parametric tools."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V24"))
import reuse as m
v=m.v
SEEDS=(4920017,4950023,4980031,5010041)
FILTERS=("a_gt","b_ge","active","total_gt","even_b")
AGGS=("count","sum_a","sum_b","max_a","min_b","sum_diff")
BASE=tuple((f,a) for n in (0,1) for f in itertools.combinations(FILTERS,n) for a in AGGS)
FULL=(*BASE,*((f,a) for f in itertools.combinations(FILTERS,2) for a in AGGS))
POLICIES=("base","library","exhaustive")
VERSION="nucleo-table-tool-v1"

def canonical(filters,agg):
    return (tuple(x for x in FILTERS if x in filters),agg)

def valid(program):
    return program in FULL

def check_input(x):
    k,rows=x
    if type(k)!=int or abs(k)>4 or len(rows)>16:raise ValueError("input bounds")
    for row in rows:
        if len(row)!=3 or any(type(z)!=int for z in row) or abs(row[0])>9 or abs(row[1])>9 or row[2] not in (0,1):
            raise ValueError("invalid record")

def pred(name,row,k):
    a,b,flag=row
    if name=="a_gt":return a>k
    if name=="b_ge":return b>=k
    if name=="active":return flag==1
    if name=="total_gt":return a+b>k
    if name=="even_b":return b%2==0
    raise ValueError("unknown predicate")

def execute(program,x):
    if not valid(program):raise ValueError("invalid program")
    check_input(x);k,rows=x;filters,agg=program
    for f in filters:rows=tuple(row for row in rows if pred(f,row,k))
    if agg=="count":y=len(rows)
    elif agg=="sum_a":y=sum(row[0] for row in rows)
    elif agg=="sum_b":y=sum(row[1] for row in rows)
    elif agg=="max_a":y=max((row[0] for row in rows),default=0)
    elif agg=="min_b":y=min((row[1] for row in rows),default=0)
    else:y=sum(row[0]-row[1] for row in rows)
    return (y,)

def reference(program,x):
    """Independent evaluator, not used to generate the agent's candidates."""
    fs,agg=program;k,records=x;selected=[]
    for a,b,flag in records:
        conditions={"a_gt":a>k,"b_ge":b>=k,"active":bool(flag),
                    "total_gt":a+b>k,"even_b":b==2*(b//2)}
        if all(conditions[z] for z in fs):selected.append((a,b))
    aa=[z[0] for z in selected];bb=[z[1] for z in selected]
    values={"count":len(selected),"sum_a":sum(aa),"sum_b":sum(bb),
        "max_a":max(aa) if aa else 0,"min_b":min(bb) if bb else 0,
        "sum_diff":sum(aa)-sum(bb)}
    return (values[agg],)

def inputs(seed):
    rng=random.Random(seed^0x3411);seen=set();out=[]
    while len(out)<232:
        k=rng.randint(-4,4)
        rows=tuple((rng.randint(-9,9),rng.randint(-9,9),rng.randrange(2)) for _ in range(rng.randrange(9)))
        x=(k,rows)
        if x not in seen:seen.add(x);out.append(x)
    def split(z):return tuple(z[:4]),tuple(z[4:36]),tuple(z[36:])
    return split(out[:116]),split(out[116:])

def derive(program):
    fs,agg=program
    return [canonical((*fs,f),agg) for f in FILTERS if f not in fs and len(fs)<2]

def suite(seed,points):
    rng=random.Random(seed^0x3422);seen=set();train=[];final=[]
    sigs={p:tuple(reference(p,x) for x in points) for p in FULL}
    base_sigs={sigs[p] for p in BASE}
    def add(pool,n,dest,stratum,excluded=()):
        pool=list(dict.fromkeys(pool));rng.shuffle(pool);count=0
        for p in pool:
            sig=sigs[p]
            if sig in seen or sig in excluded:continue
            seen.add(sig);dest.append(dict(id=f"{seed}/{stratum}/{count}",stratum=stratum,goal=p));count+=1
            if count==n:break
        assert count==n,(seed,stratum,count)
    add([p for p in BASE if p[0]],8,train,"train")
    linked=list(dict.fromkeys(q for z in train for q in derive(z["goal"])))
    add(linked,8,final,"linked",base_sigs)
    add(FULL[len(BASE):],8,final,"unseen",base_sigs|{sigs[p] for p in linked})
    add([p for p in BASE if p[0]],8,final,"direct")
    rng.shuffle(final);return train,final

def manifest(program):
    if program not in BASE or len(program[0])!=1:raise ValueError("invalid tool")
    body=dict(version=VERSION,input_schema="records(a:int,b:int,flag:0|1),k:int",
        output_schema="integer singleton",limits=dict(records=16,field_abs=9,k_abs=4),
        program=program)
    body["id"]="tool_"+m.digest(body)[:20]
    body["sha"]=m.digest(body)
    return body

def load_tool(path):
    body=json.loads(path.read_text());sha=body.pop("sha")
    if sha!=m.digest(body):raise ValueError("manifest integrity")
    program=(tuple(body["program"][0]),body["program"][1])
    expected=manifest(program)
    if expected["sha"]!=sha:raise ValueError("unexpected manifest schema")
    return expected["id"],program

def route_library(registry):
    routes={}
    for name,p in sorted(registry.items()):
        for q in derive(p):
            extra=next(f for f in q[0] if f not in p[0])
            routes.setdefault(q,(name,extra))
    return routes

def run_candidate(program,x,registry,routes):
    if program not in routes:return execute(program,x)
    name,extra=routes[program];k,rows=x;check_input(x)
    filtered=tuple(r for r in rows if pred(extra,r,k))
    return execute(registry[name],(k,filtered))

def prepare(grammar,initial,pool,registry,routes):
    points=(*initial,*pool);classes={}
    for p in sorted(grammar,key=lambda h:(len(h[0]),h)):
        sig=tuple(run_candidate(p,x,registry,routes) for x in points)
        classes.setdefault(sig,p)
    return tuple((p,sig) for sig,p in classes.items()),len(grammar)*len(points)

def episode(task,inputs,registry,routes,prepared,seed,policy):
    initial,pool,held=inputs;goal=task["goal"]
    observed=tuple(reference(goal,x) for x in initial)
    start=time.perf_counter_ns()
    # V23 solver's trace schema accepts structured, hashable input and tuple output.
    p,trace,cost,n=v.investigate(observed,pool,lambda x:reference(goal,x),"full_active",prepared,seed)
    elapsed=time.perf_counter_ns()-start
    ok=p is not None and all(run_candidate(p,x,registry,routes)==reference(goal,x) for x in held)
    return dict(task=task,policy=policy,program=p,success=ok,emitted=p is not None,
        uses_tool=p in routes if p is not None else False,tool_route=routes.get(p),
        trace=trace,queries=len(trace),comparisons=cost,remaining=n,wall_ns=elapsed)

def metric(rows):
    ok=sum(r["success"] for r in rows);em=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=ok,wrong=em-ok,abstained=len(rows)-em,
        tool_calls_in_solutions=sum(r["uses_tool"] for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("queries","comparisons","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[];preparation=[]
    for seed in SEEDS:
        acq,final_inputs=inputs(seed);points=tuple(x for g in (*acq,*final_inputs) for x in g)
        train,final=suite(seed,points)
        directory=out/f"tools_{seed}";directory.mkdir()
        registry={}
        def prep(grammar,inp,registry,routes,policy):
            start=time.perf_counter_ns()
            pr,executions=prepare(grammar,*inp[:2],registry,routes)
            preparation.append(dict(seed=seed,policy=policy,programs=len(grammar),classes=len(pr),
                executions=executions,wall_ns=time.perf_counter_ns()-start))
            return pr
        train_prep=prep(BASE,acq,{},{},"acquisition")
        for i,task in enumerate(train):
            rr=episode(task,acq,{}, {},train_prep,seed+i*701,"acquisition")
            added=False
            if rr["success"] and len(rr["program"][0])==1:
                body=manifest(rr["program"]);path=directory/(body["id"]+".json")
                if not path.exists():
                    path.write_text(m.enc(body),encoding="utf-8")
                    name,program=load_tool(path);registry[name]=program;added=True
            training.append(dict(seed=seed,added=added,**rr))
        loaded=dict(load_tool(path) for path in sorted(directory.glob("*.json")))
        assert loaded==registry
        registry=loaded;routes=route_library(registry)
        snapshots.append(dict(seed=seed,tools=len(registry),derived=len(routes),registry=registry,sha=m.digest(registry)))
        grammars={"base":BASE,"library":tuple(dict.fromkeys((*BASE,*routes))),"exhaustive":FULL}
        for policy in POLICIES:
            rr=routes if policy=="library" else {}
            rg=registry if policy=="library" else {}
            prepared=prep(grammars[policy],final_inputs,rg,rr,policy)
            for i,task in enumerate(final):
                rows.append(dict(seed=seed,**episode(task,final_inputs,rg,rr,prepared,seed+i*971,policy)))
        assert dict(load_tool(path) for path in sorted(directory.glob("*.json")))==registry
    result=dict(protocol="V34-parametric-tools-v1",seeds=SEEDS,snapshots=snapshots,preparation=preparation,
        training=dict(**metric(training),added=sum(r["added"] for r in training)),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=z,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for p in POLICIES for z in ("linked","unseen","direct")],
        by_seed=[dict(policy=p,seed=s,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for p in POLICIES for s in SEEDS])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for seed in SEEDS:
            a,b=inputs(seed);points=tuple(x for g in (*a,*b) for x in g)
            self.assertEqual(len(set(points)),232)
            tr,te=suite(seed,points);self.assertEqual((len(tr),len(te)),(8,24))
            self.assertEqual(len({tuple(reference(t["goal"],x) for x in points) for t in tr+te}),32)
    def test_interpreter(self):
        a,b=inputs(SEEDS[0])
        for p in FULL:
            for x in a[0]+a[1]:self.assertEqual(execute(p,x),reference(p,x))
        with self.assertRaises(ValueError):execute((("unknown",),"count"),(0,()))
        with self.assertRaises(ValueError):execute(((),"count"),(5,()))
    def test_manifest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"tool.json";p=(("a_gt",),"sum_a")
            body=manifest(p);path.write_text(m.enc(body));name,program=load_tool(path)
            self.assertEqual(program,p)
            registry={name:p};routes=route_library(registry)
            a,b=inputs(SEEDS[0])
            for q in routes:
                for x in a[0]+a[1]:self.assertEqual(run_candidate(q,x,registry,routes),reference(q,x))
            body["program"]=[["active"],"count"];path.write_text(m.enc(body))
            with self.assertRaises(ValueError):load_tool(path)
    def test_solver(self):
        a,b=inputs(SEEDS[0]);p=(("active",),"count")
        pr,_=prepare(BASE,*a[:2],{}, {})
        r=episode(dict(goal=p),a,{}, {},pr,1,"base")
        self.assertLessEqual(r["queries"],v.CAP)
        self.assertFalse({z["input"] for z in r["trace"]}&set(a[2]))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V34 required")
    run(z.output)
