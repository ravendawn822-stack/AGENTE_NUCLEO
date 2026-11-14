"""V2.1: observation-derived constraints before searching a numeric update rule."""
import argparse
import json
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V2"))
import meta
from meta import s,sequence,FOLD,execute
from programs import ACC,ITEM,CONST,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ,IF,value,roundrobin
SEEDS=(630017,660047,690037,720007)
POLICIES=("baseline","constraints","derived","gated")
LIMIT=3600
A=(ACC,)
TEMPLATES=("add","sub","reverse_sub","mul","max","min","replace")
OPS=(ADD,SUB,MUL,MOD,GT,EQ)


def constraints(pairs,ys,kind):
    xs=sorted({x for a,x in pairs})
    bounds={x:(None,None) for x in xs}
    for (a,x),y in zip(pairs,ys):
        lower=upper=None
        if kind=="add":lower=upper=y-a
        elif kind=="sub":lower=upper=a-y
        elif kind=="reverse_sub":lower=upper=y+a
        elif kind=="replace":lower=upper=y
        elif kind=="mul":
            if a==0:
                if y!=0:return None
            else:
                if y%a:return None
                lower=upper=y//a
        elif kind=="max":
            if y<a:return None
            if y==a:upper=a
            else:lower=upper=y
        elif kind=="min":
            if y>a:return None
            if y==a:lower=a
            else:lower=upper=y
        lo,hi=bounds[x]
        if lower is not None:lo=lower if lo is None else max(lo,lower)
        if upper is not None:hi=upper if hi is None else min(hi,upper)
        if lo is not None and hi is not None and lo>hi:return None
        bounds[x]=(lo,hi)
    return tuple(bounds[x] for x in xs)


def accepts(vec,box):
    return all((lo is None or z>=lo) and (hi is None or z<=hi) for z,(lo,hi) in zip(vec,box))


def wrap(kind,g):
    return {"add":(ADD,A,g),"sub":(SUB,A,g),"reverse_sub":(SUB,g,A),"mul":(MUL,A,g),
            "max":(IF,(GT,A,g),A,g),"min":(IF,(GT,A,g),g,A),"replace":g}[kind]


def synthesize(pairs,ys,kind,limit=LIMIT):
    xs=tuple(sorted({x for a,x in pairs}))
    feasible=[(t,b) for t in TEMPLATES if (b:=constraints(pairs,ys,t)) is not None]
    extra=[]
    if kind=="derived":
        # Bounded constants proposed from the observed input support and exact constraints.
        candidates={z for x in xs for z in (x-1,x,x+1,-x)}
        candidates.update(lo for _,b in feasible for lo,hi in b if lo is not None and lo==hi)
        extra=sorted({z for z in candidates if -8<=z<=8 and z not in (-2,-1,0,1,2)},key=lambda z:(abs(z),z))
    levels={1:[]};seen=set();spent=generated=checked=0
    def offer(e,c):
        nonlocal spent,generated,checked
        if spent>=limit:return None
        spent+=1;generated+=1
        try:vec=tuple(value(e,0,x) for x in xs)
        except (ValueError,ZeroDivisionError):return None
        if vec in seen:return None
        seen.add(vec);levels[c].append(e)
        for name,box in feasible:
            if spent>=limit:return None
            spent+=1;checked+=1
            if accepts(vec,box):
                p=wrap(name,e)
                # Independent direct interpreter consistency on all observed pairs.
                if all(value(p,a,x)==y for (a,x),y in zip(pairs,ys)):return p
        return None
    def info():
        return dict(feasible=[t for t,_ in feasible],boxes=feasible,constants=extra,generated=generated,checked=checked)
    if not feasible:return None,0,info()
    for e in ((ITEM,),*((CONST,n) for n in [-2,-1,0,1,2,*extra])):
        p=offer(e,1)
        if p is not None:return p,spent,info()
    for cost in range(2,9):
        levels[cost]=[]
        unary=((op,e) for e in levels[cost-1] for op in (ABS,NEG))
        binary=((op,a,b) for k in range(1,cost-1) for a in levels[k] for b in levels[cost-1-k] for op in OPS)
        for e in roundrobin(unary,binary):
            if spent>=limit:return None,spent,info()
            p=offer(e,cost)
            if p is not None:return p,spent,info()
    return None,spent,info()


def solve(task,policy,seed):
    start=time.perf_counter_ns()
    init,pairs,ys,q,ok=sequence.transitions(lambda x:sequence.oracle(task,x),sequence.observation_sequences(seed))
    assert ok
    if policy=="baseline":
        e,n,m=s.structured(pairs,ys,[],LIMIT)
    else:e,n,m=synthesize(pairs,ys,policy)
    search_ns=time.perf_counter_ns()-start
    p=(FOLD,init,e) if e is not None else None
    checks=[]
    if p:
        for x in sequence.check_sequences(seed):
            y=sequence.oracle(task,x)
            try:z=execute(p,x)
            except (ValueError,ZeroDivisionError):z=None
            checks.append([x,y,z])
    return dict(task=task,method=policy,program=p,success=p is not None and all(y==z for _,y,z in checks),
                abstained=p is None,spent=n,queries=q,search_ns=search_ns,ns=time.perf_counter_ns()-start,
                search=m,checks=checks)


def batch(tasks,policy,seed,phase):
    salt={"development":103,"gate":307,"final":709}[phase]
    return [solve(t,policy,seed*31+salt+i*701) for i,t in enumerate(tasks)]


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    rows=[];decisions=[]
    def record(seed,policy,phase,data):
        rows.extend(dict(seed=seed,index=i,policy=policy,phase=phase,**r) for i,r in enumerate(data))
    suites={seed:meta.split(seed) for seed in SEEDS}
    selected={}
    for seed,(dev,gate,_) in suites.items():
        scores={}
        for p in POLICIES[:3]:
            rr=batch(dev,p,seed,"development");record(seed,p,"development",rr);scores[p]=meta.score(rr)
        best=max(POLICIES[:3],key=lambda p:scores[p])
        old=batch(gate,"baseline",seed,"gate");new=batch(gate,best,seed,"gate")
        record(seed,"gate_baseline","gate",old);record(seed,"gate_proposed","gate",new)
        result=meta.gate_decision(old,new)
        selected[seed]=best if result["accepted"] else "baseline"
        decisions.append(dict(seed=seed,scores=scores,proposal=best,selected=selected[seed],gate=result))
    for seed,(_,_,test) in suites.items():
        for p in POLICIES:
            rr=batch(test,selected[seed] if p=="gated" else p,seed,"final");record(seed,p,"final",rr)
    final=[r for r in rows if r["phase"]=="final"]
    base={(r["seed"],r["index"]):r for r in final if r["policy"]=="baseline"}
    def summary(rr):
        n=len(rr)
        return dict(n=n,correct=sum(r["success"] for r in rr),wrong=sum(not r["success"] and not r["abstained"] for r in rr),
            abstained=sum(r["abstained"] for r in rr),gain=sum(r["success"] and not base[r["seed"],r["index"]]["success"] for r in rr),
            loss=sum(not r["success"] and base[r["seed"],r["index"]]["success"] for r in rr),mean_spent=sum(r["spent"] for r in rr)/n,
            mean_search_ns=sum(r["search_ns"] for r in rr)/n)
    result=dict(protocol="NUCLEO_V2_1-constraints-v1",seeds=SEEDS,episodes=len(rows),decisions=decisions,
        aggregate=[dict(policy=p,**summary([r for r in final if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**summary([r for r in final if r["policy"]==p and r["task"][0]==f])) for p in POLICIES for f in sequence.FAMILIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_CONSTRAINTS="+json.dumps(result,separators=(",",":")))


class Tests(unittest.TestCase):
    def test_inverse(self):
        self.assertEqual(constraints([(1,4),(5,4)],[3,7],"add"),((2,2),))
        self.assertIsNone(constraints([(1,4),(5,4)],[3,8],"add"))
        self.assertIsNone(constraints([(4,1)],[2],"max"))
        self.assertEqual(constraints([(0,1)],[0],"mul"),((None,None),))
        self.assertEqual(constraints([(3,1),(1,1)],[3,2],"max"),((2,2),))
    def test_template_equivalence(self):
        for t in TEMPLATES:
            g=(CONST,2);p=wrap(t,g)
            pairs=[(a,x) for a in range(-4,5) for x in (-2,0,2)]
            ys=[value(p,a,x) for a,x in pairs]
            box=constraints(pairs,ys,t);self.assertIsNotNone(box)
            self.assertTrue(accepts((2,2,2),box))
    def test_solve(self):
        for policy in ("constraints","derived"):
            self.assertTrue(solve(("square",(1,0)),policy,81)["success"])
            self.assertLessEqual(solve(("linear",(2,1)),policy,81)["spent"],LIMIT)
    def test_bound(self):
        p,n,_=synthesize([(0,0),(0,1)],[8,9],"derived",3)
        self.assertIsNone(p);self.assertLessEqual(n,3)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output in experiment required")
    run(a.output)
