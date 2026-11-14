"""NUCLEO_V1.1 pilot: decompose state update into an item expression and an operation."""
import argparse
import itertools
import json
import sys
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V1"))
import core
from core import sequence,teacher
from programs import ACC,ITEM,CONST,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ,IF,FOLD,value,execute,roundrobin

SEEDS=(420031,450001,480013)
POLICIES=("cold","structured","structured_teacher","protected","protected_teacher")
LIMIT=3600
OPS=(ADD,SUB,MUL,MOD,GT,EQ)
A=(ACC,)


def input_only(e):
    return e[0]!=ACC and all(input_only(x) for x in e[1:] if isinstance(x,tuple))


def structured(pairs,ys,macros,limit):
    # All templates are supplied as a generic state-update grammar, not task-specific solutions.
    xs=tuple(x for a,x in pairs);acc=tuple(a for a,x in pairs);target=tuple(ys)
    levels={1:[]};seen=set();spent=0;generated=checked=0
    def offer(g,cv,level):
        nonlocal spent,generated,checked
        if spent>=limit:return None
        spent+=1;generated+=1
        if cv is None or cv in seen:return None
        seen.add(cv);levels[level].append((g,cv))
        choices=((ADD,A,g),(SUB,A,g),(SUB,g,A),(MUL,A,g),
                 (IF,(GT,A,g),A,g),(IF,(GT,A,g),g,A),g)
        # Cheap vector predictions are a partial evaluator for the same AST.
        vectors=(lambda:tuple(a+b for a,b in zip(acc,cv)),
                 lambda:tuple(a-b for a,b in zip(acc,cv)),
                 lambda:tuple(b-a for a,b in zip(acc,cv)),
                 lambda:tuple(a*b for a,b in zip(acc,cv)),
                 lambda:tuple(max(a,b) for a,b in zip(acc,cv)),
                 lambda:tuple(min(a,b) for a,b in zip(acc,cv)),
                 lambda:cv)
        for expr,vec in zip(choices,vectors):
            if spent>=limit:return None
            spent+=1;checked+=1
            if vec()==target:return expr
        return None
    def vector(e):
        try:return tuple(value(e,0,x) for x in xs)
        except (ValueError,ZeroDivisionError):return None
    leaves=((ITEM,),*((CONST,i) for i in (-2,-1,0,1,2)))
    for g in (*leaves,*[m for m in macros if input_only(m)]):
        p=offer(g,vector(g),1)
        if p is not None:return p,spent,dict(generated=generated,checked=checked)
    for c in range(2,9):
        levels[c]=[]
        unary=((op,e) for e,_ in levels[c-1] for op in (ABS,NEG))
        binary=((op,a,b) for s in range(1,c-1) for a,_ in levels[s] for b,_ in levels[c-1-s] for op in OPS)
        # Interleave generation paths; every generated expression consumes budget.
        for g in roundrobin(unary,binary):
            if spent>=limit:return None,spent,dict(generated=generated,checked=checked)
            p=offer(g,vector(g),c)
            if p is not None:return p,spent,dict(generated=generated,checked=checked)
    return None,spent,dict(generated=generated,checked=checked)


def solve(task,seed,policy,macros):
    started=time.perf_counter_ns()
    init,pairs,ys,q,consistent=sequence.transitions(lambda s:sequence.oracle(task,s),sequence.observation_sequences(seed))
    paths={"cold":[("cold",[],LIMIT)],
           "structured":[("structured",[],LIMIT)],
           "structured_teacher":[("structured",macros,LIMIT)],
           "protected":[("cold",[],1800),("structured",[],1800)],
           "protected_teacher":[("cold",[],1800),("structured",macros,1800)]}
    attempts=[];e=None
    if consistent:
        for method,m,cap in paths[policy]:
            if method=="cold":
                e,n=sequence.synthesize(pairs,ys,m,limit=cap);meta={}
            else:e,n,meta=structured(pairs,ys,m,cap)
            attempts.append(dict(method=method,spent=n,limit=cap,found=e is not None,**meta))
            if e is not None:break
    search_ns=time.perf_counter_ns()-started
    p=(FOLD,init,e) if e is not None else None
    checks=[]
    if p is not None:
        for seq in sequence.check_sequences(seed):
            y=sequence.oracle(task,seq)
            try:z=execute(p,seq)
            except (ValueError,ZeroDivisionError):z=None
            checks.append([seq,y,z])
    return dict(program=p,success=p is not None and all(y==z for _,y,z in checks),checks=checks,
        abstained=p is None,attempts=attempts,spent=sum(x["spent"] for x in attempts),queries=q,
        search_ns=search_ns,total_ns=time.perf_counter_ns()-started)


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    p=ROOT.parent/"EXPERIMENTO_05C_09A"/"TEACHER_PROPOSALS.json"
    macros,evidence=teacher.verify_teacher(json.loads(p.read_text(encoding="utf-8")))
    rows=[]
    for seed in SEEDS:
        _,tasks=sequence.task_pool(seed)
        for i,task in enumerate(tasks):
            for policy in POLICIES:
                r=solve(task,seed*71+i*97,policy,macros)
                rows.append(dict(seed=seed,index=i,task=task,policy=policy,**r))
    cold={(x["seed"],x["index"]):x for x in rows if x["policy"]=="cold"}
    def summary(rr):
        n=len(rr)
        return dict(n=n,correct=sum(r["success"] for r in rr),
            wrong=sum(not r["success"] and not r["abstained"] for r in rr),abstained=sum(r["abstained"] for r in rr),
            gains_vs_cold=sum(r["success"] and not cold[r["seed"],r["index"]]["success"] for r in rr),
            losses_vs_cold=sum(not r["success"] and cold[r["seed"],r["index"]]["success"] for r in rr),
            mean_spent=sum(r["spent"] for r in rr)/n,mean_queries=sum(r["queries"] for r in rr)/n,
            mean_search_ns=sum(r["search_ns"] for r in rr)/n)
    aggregate=[dict(policy=p,**summary([r for r in rows if r["policy"]==p])) for p in POLICIES]
    by_family=[dict(policy=p,family=f,**summary([r for r in rows if r["policy"]==p and r["task"][0]==f])) for p in POLICIES for f in sequence.FAMILIES]
    result=dict(protocol="NUCLEO_V1_1_synthesis_v1",episodes=len(rows),seeds=SEEDS,aggregate=aggregate,by_family=by_family,
                teacher_accepted=[r["id"] for r in evidence if r["accepted"]])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"teacher_validation.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_STRUCTURED="+json.dumps(result))


class Tests(unittest.TestCase):
    def test_square(self):
        m=solve(("square",(1,0)),7,"structured",[])
        self.assertTrue(m["success"]);self.assertLessEqual(m["spent"],LIMIT)
    def test_threshold(self):
        m=solve(("threshold",(1,0)),7,"structured",[])
        self.assertTrue(m["success"])
    def test_bounds(self):
        e,n,m=structured([(0,0),(0,1)],[500,900],[],3)
        self.assertIsNone(e);self.assertEqual(n,3)
    def test_macro_filter(self):
        self.assertFalse(input_only((ADD,(ACC,),(ITEM,))))
        self.assertTrue(input_only((MUL,(ITEM,),(ITEM,))))
    def test_templates(self):
        for task in (("linear",(2,0)),("extreme",(1,0)),("absolute",(1,0))):
            self.assertTrue(solve(task,11,"structured",[])["success"])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output inside NUCLEO_V1_1 required")
    run(a.output)
