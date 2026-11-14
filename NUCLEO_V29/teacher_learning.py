"""V29: offline teacher proposals, empirical validation and frozen skill transfer."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V24"))
import reuse as m
v=m.v
SEEDS=(4200017,4230023,4260031,4290041)
POLICIES=("basic","unverified","verified","ideal")
NAMES=("total","prefix","count_positive","distinct_count","span","minimum")
EXTRA=("sum","scan","count","bounds","maximum")
ALLOWED=set(v.OPS)|set(EXTRA)

def valid(p):
    return isinstance(p,(tuple,list)) and 1<=len(p)<=4 and all(isinstance(x,str) and x in ALLOWED for x in p)

def module(p,x):
    if not valid(p):raise ValueError("invalid declarative module")
    a=tuple(x)
    for op in p:
        if op in v.OPS:a=v.execute((op,),a)
        elif op=="sum":a=(sum(a),)
        elif op=="count":a=(len(a),)
        elif op=="scan":a=tuple(itertools.accumulate(a))
        elif op=="bounds":a=(min(a),max(a)) if a else (0,0)
        elif op=="maximum":a=(max(a),) if a else (0,)
    return a

def oracle(name,x):
    if name=="total":return (sum(x),)
    if name=="prefix":return tuple(sum(x[:i]) for i in range(1,len(x)+1))
    if name=="count_positive":return (sum(z>0 for z in x),)
    if name=="distinct_count":return (len(set(x)),)
    if name=="span":return (max(x)-min(x) if x else 0,)
    if name=="minimum":return (min(x) if x else 0,)
    if name in v.OPS:return v.execute((name,),x)
    raise ValueError(name)

def target(program,x):
    for name in program:x=oracle(name,x)
    return x

def execute(program,x,registry):
    if len(program)>2:raise ValueError("program too long")
    for name in program:
        if name in v.OPS:x=v.execute((name,),x)
        elif name in registry:x=module(registry[name],x)
        else:raise ValueError("unknown skill")
    return x

def teaching_points(seed,forbidden):
    rng=random.Random(seed^0x2911);seen=set(forbidden);out=[]
    while len(out)<24:
        x=tuple(rng.randint(-5,5) for _ in range(rng.randint(1,8)))
        if x not in seen:seen.add(x);out.append(x)
    return tuple(out)

def teach(seed,lessons,points):
    rng=random.Random(seed^0x2922);checked={};blind={};ideal={};traces=[]
    for lesson in lessons:
        name=lesson["name"];proposals=list(lesson["proposals"])
        assert name in NAMES and name not in ideal
        ideal[name]=tuple(proposals[0])
        rng.shuffle(proposals)
        expected=[oracle(name,x) for x in points]
        for p in proposals:
            p=tuple(p);legal=valid(p)
            matches=sum(module(p,x)==y for x,y in zip(points,expected)) if legal else 0
            take=legal and matches==len(points) and name not in checked
            if legal and name not in blind:blind[name]=p
            if take:checked[name]=p
            traces.append(dict(name=name,proposal=p,syntactically_valid=legal,matches=matches,
                tests=len(points) if legal else 0,accepted=take))
    assert set(ideal)==set(NAMES)
    return checked,blind,ideal,traces

def suite(seed,points):
    rng=random.Random(seed^0x2933);seen=set();out=[]
    def sig(p):return tuple(target(p,x) for x in points)
    base={sig(p) for p in v.FULL}
    direct={sig((name,)) for name in NAMES}
    def add(options,n,stratum,excluded):
        options=list(options);rng.shuffle(options);count=0
        for p in options:
            z=sig(p)
            if z in excluded or z in seen:continue
            seen.add(z);out.append(dict(id=f"{seed}/{stratum}/{count}",stratum=stratum,program=p));count+=1
            if count==n:break
        assert count==n,(stratum,count)
    add(((name,) for name in NAMES),6,"direct",base)
    add((p for a in NAMES for b in v.OPS for p in ((a,b),(b,a))),12,"composed",base|direct)
    add(v.FULL[1:],6,"basic",direct)
    rng.shuffle(out);return out

def prepare(registry,initial,pool):
    ops=(*v.OPS,*sorted(registry))
    programs=((),*((x,) for x in ops),*itertools.product(ops,repeat=2))
    points=(*initial,*pool);groups={}
    for p in sorted(programs,key=lambda z:(len(z),z)):
        sg=tuple(execute(p,x,registry) for x in points)
        groups.setdefault(sg,p)
    return tuple((p,sg) for sg,p in groups.items()),len(programs)

def episode(t,initial,pool,held,registry,prepared,seed,policy):
    obs=tuple(target(t["program"],x) for x in initial)
    start=time.perf_counter_ns()
    p,trace,cost,n=v.investigate(obs,pool,lambda x:target(t["program"],x),"full_active",prepared,seed)
    elapsed=time.perf_counter_ns()-start
    ok=p is not None and all(execute(p,x,registry)==target(t["program"],x) for x in held)
    return dict(task=t,policy=policy,program=p,emitted=p is not None,success=ok,
        trace=trace,queries=len(trace),comparisons=cost,remaining=n,wall_ns=elapsed)

def metric(rows):
    ok=sum(r["success"] for r in rows);em=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=ok,wrong=em-ok,abstained=len(rows)-em,
        **{k:sum(r[k] for r in rows) for k in ("queries","comparisons","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[];preparation=[]
    packet=json.loads((ROOT/"teacher.json").read_text());lessons=packet["lessons"]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed);points=(*initial,*pool,*held)
        teach_points=teaching_points(seed,points)
        start=time.perf_counter_ns();checked,blind,ideal,traces=teach(seed,lessons,teach_points)
        elapsed=time.perf_counter_ns()-start
        training.extend(dict(seed=seed,**row) for row in traces)
        evidence=[dict(name=name,examples=[dict(input=x,output=oracle(name,x)) for x in teach_points]) for name in NAMES]
        saved=dict(source=packet["source"],teacher_sha=m.digest(packet),registry=checked,evidence=evidence,trace=traces)
        saved["sha"]=m.digest(saved);path=out/f"skills_{seed}.json"
        path.write_text(m.enc(saved),encoding="utf-8")
        loaded=json.loads(path.read_text());sha=loaded.pop("sha");assert m.digest(loaded)==sha
        verified={name:tuple(p) for name,p in loaded["registry"].items()}
        assert verified==checked and all(valid(p) for p in verified.values())
        snapshots.append(dict(seed=seed,approved=len(verified),blind_correct=sum(blind[n]==ideal[n] for n in NAMES),
            invalid=sum(not z["syntactically_valid"] for z in traces),tested=sum(z["tests"] for z in traces),
            teaching_ns=elapsed,registry=verified,sha=sha))
        registries={"basic":{},"unverified":blind,"verified":verified,"ideal":ideal}
        tasks=suite(seed,points)
        for policy,registry in registries.items():
            start=time.perf_counter_ns();prep,n=prepare(registry,initial,pool)
            preparation.append(dict(seed=seed,policy=policy,programs=n,classes=len(prep),
                executions=n*(len(initial)+len(pool)),wall_ns=time.perf_counter_ns()-start))
            for i,t in enumerate(tasks):
                rows.append(dict(seed=seed,**episode(t,initial,pool,held,registry,prep,seed+i*971,policy)))
        assert json.loads(path.read_text())["sha"]==sha
    result=dict(protocol="V29-offline-teacher-v1",seeds=SEEDS,teacher_mode="static ChatGPT lessons, no model calls",
        snapshots=snapshots,preparation=preparation,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in ("direct","composed","basic") for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_teacher(self):
        lessons=json.loads((ROOT/"teacher.json").read_text())["lessons"]
        a,b,c=v.input_sets(SEEDS[0]);points=(*a,*b,*c)
        t=teaching_points(SEEDS[0],points);self.assertEqual(len(t),24)
        self.assertFalse(set(t)&set(points))
        checked,blind,ideal,trace=teach(SEEDS[0],lessons,t)
        self.assertEqual(checked,ideal)
        self.assertEqual(sum(not r["syntactically_valid"] for r in trace),6)
        for name,p in ideal.items():
            self.assertTrue(all(module(p,x)==oracle(name,x) for x in points))
        with self.assertRaises(ValueError):module(("unknown",),(1,))
    def test_suite(self):
        for seed in SEEDS:
            a,b,c=v.input_sets(seed);points=(*a,*b,*c);ts=suite(seed,points)
            self.assertEqual(len(ts),24)
            self.assertEqual(len({tuple(target(t["program"],x) for x in points) for t in ts}),24)
    def test_offline(self):
        a,b,c=v.input_sets(SEEDS[0]);registry={"prefix":("scan",)}
        prep,n=prepare(registry,a,b)
        t=dict(program=("prefix",))
        rr=episode(t,a,b,c,registry,prep,1,"offline")
        self.assertLessEqual(rr["queries"],v.CAP)
        self.assertFalse(set(z["input"] for z in rr["trace"])&set(c))
        self.assertTrue(rr["success"])
        with self.assertRaises(ValueError):execute(("sum",),(1,),{})

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V29 required")
    run(z.output)
