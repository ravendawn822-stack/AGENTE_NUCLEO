"""V30: request teaching on observed gaps; freeze skills before offline evaluation."""
import argparse,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V29"))
import teacher_learning as t
m,v=t.m,t.v
SEEDS=(4320017,4350023,4380031,4410041)
ACQUISITION=("none","random","targeted")
POLICIES=(*ACQUISITION,"ideal")
REQUEST_CAP=4

def final_inputs(seed,forbidden):
    rng=random.Random(seed^0x3001);seen=set(forbidden);out=[]
    while len(out)<116:
        x=tuple(rng.randint(-3,3) for _ in range(rng.randint(0,5)))
        if x not in seen:seen.add(x);out.append(x)
    return tuple(out[:4]),tuple(out[4:36]),tuple(out[36:])

def acquisition(seed,points):
    rng=random.Random(seed^0x3002)
    names=tuple(sorted(rng.sample(t.NAMES,4)))
    tasks=[dict(id=f"{seed}/learn/{i}",stratum="direct",program=(name,)) for i,name in enumerate(names)]
    seen={tuple(t.target(row["program"],x) for x in points) for row in tasks}
    candidates=list(v.FULL[1:]);rng.shuffle(candidates);n=0
    for p in candidates:
        sig=tuple(t.target(p,x) for x in points)
        if sig in seen:continue
        seen.add(sig);tasks.append(dict(id=f"{seed}/basic/{n}",stratum="basic",program=p));n+=1
        if n==8:break
    assert n==8
    rng.shuffle(tasks)
    return names,tasks

def choose_card(observed,cards,attempted,policy,rng):
    available=sorted(name for name in cards if name not in attempted)
    if not available or policy=="none":return None
    if policy=="random":return rng.choice(available)
    matching=[name for name in available if tuple(cards[name])==tuple(observed)]
    return matching[0] if matching else None

class Teacher:
    """Experimental offline broker. Not callable by the final solver."""
    def __init__(self,packet,initial,points,seed):
        self.lessons={lesson["name"]:lesson for lesson in packet["lessons"]}
        assert set(self.lessons)==set(t.NAMES)
        self.cards={name:tuple(t.oracle(name,x) for x in initial) for name in t.NAMES}
        self.points=points;self.seed=seed
    def request(self,name):
        proposals=list(self.lessons[name]["proposals"])
        random.Random(self.seed^sum((i+1)*ord(c) for i,c in enumerate(name))).shuffle(proposals)
        expected=[t.oracle(name,x) for x in self.points];trace=[];accepted=None
        for proposal in proposals:
            p=tuple(proposal);legal=t.valid(p)
            matched=sum(t.module(p,x)==y for x,y in zip(self.points,expected)) if legal else 0
            adopt=legal and matched==len(expected) and accepted is None
            if adopt:accepted=p
            trace.append(dict(proposal=p,legal=legal,tests=len(expected) if legal else 0,matches=matched,accepted=adopt))
        return accepted,trace

def investigate(initial,observed,pool,ask,registry,prepared,seed):
    # No teacher, target source, task label, or reserved feedback in this interface.
    start=time.perf_counter_ns()
    p,trace,cost,n=v.investigate(observed,pool,ask,"full_active",prepared,seed)
    return dict(program=p,emitted=p is not None,queries=len(trace),comparisons=cost,
                trace=trace,remaining=n,wall_ns=time.perf_counter_ns()-start)

def score(row,goal,held,registry):
    p=row["program"]
    return p is not None and all(t.execute(p,x,registry)==t.target(goal,x) for x in held)

def prepare(registry,initial,pool):
    start=time.perf_counter_ns();p,n=t.prepare(registry,initial,pool)
    return p,dict(programs=n,classes=len(p),executions=n*(len(initial)+len(pool)),wall_ns=time.perf_counter_ns()-start)

def acquire(policy,seed,tasks,initial,pool,held,teacher):
    registry={};attempted=set();rows=[];requests=[];preparations=[]
    prepared,cost=prepare(registry,initial,pool);preparations.append(cost)
    rng=random.Random(seed^0x3003)
    for i,task in enumerate(tasks):
        goal=task["program"];obs=tuple(t.target(goal,x) for x in initial)
        ask=lambda x:t.target(goal,x)
        first=investigate(initial,obs,pool,ask,registry,prepared,seed+i*701)
        first_ok=score(first,goal,held,registry)
        selected=None;retry=None;retry_ok=False
        if not first["emitted"] and len(requests)<REQUEST_CAP:
            selected=choose_card(obs,teacher.cards,attempted,policy,rng)
            if selected is not None:
                attempted.add(selected);start=time.perf_counter_ns()
                skill,trace=teacher.request(selected)
                elapsed=time.perf_counter_ns()-start
                requests.append(dict(task=task["id"],goal=goal,topic=selected,
                    relevant=goal==(selected,),accepted=skill,trace=trace,teaching_ns=elapsed))
                if skill is not None:
                    assert t.valid(skill);registry[selected]=skill
                    prepared,cost=prepare(registry,initial,pool);preparations.append(cost)
                retry=investigate(initial,obs,pool,ask,registry,prepared,seed+i*701)
                retry_ok=score(retry,goal,held,registry)
        last=retry if retry is not None else first
        rows.append(dict(seed=seed,policy=policy,task=task,request=selected,
            first=first,first_success=first_ok,retry=retry,
            success=retry_ok if retry is not None else first_ok,emitted=last["emitted"],
            queries=first["queries"]+(retry["queries"] if retry else 0),
            comparisons=first["comparisons"]+(retry["comparisons"] if retry else 0),
            wall_ns=first["wall_ns"]+(retry["wall_ns"] if retry else 0)))
    assert len(requests)<=REQUEST_CAP
    return registry,rows,requests,preparations

def freeze(path,registry,requests):
    record=dict(registry=registry,requests_sha=m.digest(requests))
    record["sha"]=m.digest(record);path.write_text(m.enc(record),encoding="utf-8")
    loaded=json.loads(path.read_text());sha=loaded.pop("sha");assert m.digest(loaded)==sha
    frozen={name:tuple(p) for name,p in loaded["registry"].items()}
    assert all(name in t.NAMES and t.valid(p) for name,p in frozen.items())
    return frozen,sha

def metric(rows):
    ok=sum(r["success"] for r in rows);em=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=ok,wrong=em-ok,abstained=len(rows)-em,
        **{k:sum(r[k] for r in rows) for k in ("queries","comparisons","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text())
    rows=[];training=[];requests=[];snapshots=[];preparation=[]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed);acq_points=(*initial,*pool,*held)
        fi,fp,fh=final_inputs(seed,acq_points);final_points=(*fi,*fp,*fh)
        teaching=t.teaching_points(seed,(*acq_points,*final_points))
        names,tasks=acquisition(seed,acq_points)
        teacher=Teacher(packet,initial,teaching,seed)
        registries={}
        for policy in ACQUISITION:
            registry,rr,req,prep=acquire(policy,seed,tasks,initial,pool,held,teacher)
            path=out/f"skills_{seed}_{policy}.json";frozen,sha=freeze(path,registry,req)
            registries[policy]=frozen;training.extend(rr)
            requests.extend(dict(seed=seed,policy=policy,**r) for r in req)
            preparation.extend(dict(seed=seed,policy=policy,phase="acquisition",**x) for x in prep)
            snapshots.append(dict(seed=seed,policy=policy,acquisition_topics=names,
                learned=sorted(frozen),requests=len(req),relevant=sum(r["relevant"] for r in req),
                false_activations=sum(r["goal"][0] in v.OPS for r in req),
                teaching_tests=sum(z["tests"] for r in req for z in r["trace"]),
                teaching_ns=sum(r["teaching_ns"] for r in req),sha=sha))
        registries["ideal"]={lesson["name"]:tuple(lesson["proposals"][0]) for lesson in packet["lessons"]}
        del teacher
        final=t.suite(seed,final_points)
        for policy,registry in registries.items():
            prepared,cost=prepare(registry,fi,fp)
            preparation.append(dict(seed=seed,policy=policy,phase="offline",**cost))
            for i,task in enumerate(final):
                goal=task["program"];observed=tuple(t.target(goal,x) for x in fi)
                rr=investigate(fi,observed,fp,lambda x:t.target(goal,x),registry,prepared,seed+i*971)
                topics=set(goal)&set(t.NAMES)
                relation="basic" if not topics else "acquisition_topic" if topics<=set(names) else "other_topic"
                rows.append(dict(seed=seed,policy=policy,task=task,relation=relation,
                    success=score(rr,goal,fh,registry),**rr))
        for policy in ACQUISITION:
            path=out/f"skills_{seed}_{policy}.json";snapshot=json.loads(path.read_text())
            sha=snapshot.pop("sha");assert m.digest(snapshot)==sha
            assert {k:tuple(p) for k,p in snapshot["registry"].items()}==registries[policy]
    result=dict(protocol="V30-targeted-offline-learning-v1",seeds=SEEDS,snapshots=snapshots,preparation=preparation,
        acquisition=[dict(policy=p,**metric([r for r in training if r["policy"]==p]),
            requests=sum(r["policy"]==p for r in requests),
            relevant=sum(r["policy"]==p and r["relevant"] for r in requests)) for p in ACQUISITION],
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_relation=[dict(relation=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["relation"]==z])) for z in ("basic","acquisition_topic","other_topic") for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in ("direct","composed","basic") for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["seed"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("acquisition",training),("requests",requests)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_inputs(self):
        for seed in SEEDS:
            a,b,c=v.input_sets(seed);points=(*a,*b,*c)
            d,e,f=final_inputs(seed,points);final=(*d,*e,*f)
            self.assertEqual(len(set(final)),116)
            self.assertFalse(set(final)&set(points))
            self.assertFalse(set(t.teaching_points(seed,(*points,*final)))&(set(points)|set(final)))
            names,tasks=acquisition(seed,points)
            self.assertEqual((len(names),len(tasks)),(4,12))
            self.assertEqual(len(t.suite(seed,final)),24)
    def test_choose(self):
        cards={"a":((1,),),"b":((2,),)};rng=random.Random(1)
        self.assertEqual(choose_card(((2,),),cards,set(),"targeted",rng),"b")
        self.assertIsNone(choose_card(((3,),),cards,set(),"targeted",rng))
        self.assertIsNone(choose_card(((2,),),cards,{"b"},"targeted",rng))
    def test_offline(self):
        a,b,c=v.input_sets(SEEDS[0]);registry={"total":("sum",)}
        prepared,_=prepare(registry,a,b)
        ask=lambda x:(sum(x),);obs=tuple(ask(x) for x in a)
        rr=investigate(a,obs,b,ask,registry,prepared,1)
        self.assertLessEqual(rr["queries"],v.CAP)
        self.assertFalse(set(z["input"] for z in rr["trace"])&set(c))
        self.assertTrue(score(rr,("total",),c,registry))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V30 required")
    run(z.output)
