"""05A: bounded numeric program synthesis for sequence reductions; no exec/eval."""
import argparse
import itertools
import json
import random
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ACC,ITEM,CONST=0,1,2
ABS,NEG=3,4
ADD,SUB,MUL,MOD,GT,EQ=10,11,12,13,14,15
IF,FOLD,SINGLE=20,30,31
SEEDS=(104729,130363,155921)
LIMIT=9000
LEAVES=((ACC,),(ITEM,),*((CONST,c) for c in (-1,0,1,2)))
OPS=(ADD,SUB,MUL,MOD,GT,EQ)


def value(e,a,x):
    op=e[0]
    if op==ACC:return a
    if op==ITEM:return x
    if op==CONST:return e[1]
    if op==ABS:return abs(value(e[1],a,x))
    if op==NEG:return -value(e[1],a,x)
    if op==IF:return value(e[2] if value(e[1],a,x) else e[3],a,x)
    l,r=value(e[1],a,x),value(e[2],a,x)
    if op==ADD:return l+r
    if op==SUB:return l-r
    if op==MUL:return l*r
    if op==MOD:return l%r
    if op==GT:return int(l>r)
    if op==EQ:return int(l==r)
    raise ValueError("unknown opcode")


def execute(program,seq):
    if len(seq)>32:raise ValueError("sequence cap")
    mode,a,e=program
    if mode==SINGLE: seq=seq[-1:]
    elif mode!=FOLD:raise ValueError("unknown program type")
    for x in seq:
        a=value(e,a,x)
        if abs(a)>10**12:raise ValueError("integer cap")
    return a


def roundrobin(*iterables):
    sources=[iter(s) for s in iterables]
    while sources:
        next_sources=[]
        for source in sources:
            try: yield next(source);next_sources.append(source)
            except StopIteration:pass
        sources=next_sources


def expressions():
    simple=[(op,a,b) for a in LEAVES for b in LEAVES for op in OPS]
    unary=[(op,a) for a in LEAVES for op in (ABS,NEG)]
    yield from LEAVES;yield from unary;yield from simple
    nested=((op,a,b) for a in unary+simple for b in LEAVES for op in OPS)
    nested2=((op,a,b) for b in unary+simple for a in LEAVES for op in OPS)
    cond=((IF,(op,a,b),t,f) for a in LEAVES for b in LEAVES for t in LEAVES for f in LEAVES for op in (GT,EQ))
    predicates=((EQ,(MOD,(ITEM,),(CONST,2)),(CONST,0)),)
    cond2=((IF,p,t,f) for p in predicates for t in LEAVES for f in LEAVES)
    # cond2 is a family of comparisons using the grammar, not a full task solution.
    # Its parity-specific grammar would bias that task, so leave it out of enumeration.
    yield from roundrobin(nested,nested2,cond)


def programs(mode):
    seen=set()
    for e in expressions():
        if e in seen: continue
        seen.add(e)
        for initial in (0,1,-1):yield (mode,initial,e)


def synthesize(observations,mode,limit=LIMIT):
    start=time.perf_counter_ns()
    for n,p in enumerate(itertools.islice(programs(mode),limit),1):
        try:
            if all(execute(p,seq)==y for seq,y in observations):
                return p,n,time.perf_counter_ns()-start
        except (ZeroDivisionError,ValueError):pass
    return None,n,time.perf_counter_ns()-start


def reference(task,seq):
    if task=="sum":return sum(seq)
    if task=="product":
        a=1
        for x in seq:a*=x
        return a
    if task=="length":return len(seq)
    if task=="sum_squares":return sum(x*x for x in seq)
    if task=="sum_abs":return sum(abs(x) for x in seq)
    if task=="positive_count":return sum(x>0 for x in seq)
    if task=="negative_count":return sum(x<0 for x in seq)
    if task=="even_count":return sum(x%2==0 for x in seq)
    if task=="max_zero":return max((0,*seq))
    if task=="min_zero":return min((0,*seq))
    if task=="alternating":
        a=0
        for x in seq:a=x-a
        return a
    if task=="range_zero":return max((0,*seq))-min((0,*seq))
    raise ValueError(task)


TASKS=("sum","product","length","sum_squares","sum_abs","positive_count","negative_count","even_count",
       "max_zero","min_zero","alternating","range_zero")


def sequences(seed):
    r=random.Random(seed)
    train=[(),(2,),(-3,),(1,2),(2,1),(0,-2)]
    while len(train)<20:
        s=tuple(r.randint(-4,4) for _ in range(r.randint(1,5)))
        if s not in train:train.append(s)
    test=[]
    while len(test)<40:
        s=tuple(r.randint(-4,4) for _ in range(r.randint(6,14)))
        if s not in test:test.append(s)
    return train,test


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    rows=[]
    for seed in SEEDS:
        train,test=sequences(seed)
        for task in TASKS:
            obs=[(seq,reference(task,seq)) for seq in train]
            for mode in (SINGLE,FOLD):
                p,n,ns=synthesize(obs,mode)
                checks=[]
                if p:
                    for seq in test:
                        expected=reference(task,seq)
                        try: predicted=execute(p,seq)
                        except (ValueError,ZeroDivisionError):predicted=None
                        checks.append([seq,expected,predicted])
                rows.append(dict(seed=seed,task=task,mode="fold" if mode==FOLD else "single",program=p,
                                 candidates=n,search_ns=ns,train=obs,checks=checks,
                                 success=p is not None and all(y==z for _,y,z in checks)))
    aggregate=[]
    for mode in ("single","fold"):
        rr=[x for x in rows if x["mode"]==mode]
        aggregate.append(dict(mode=mode,n=len(rr),correct=sum(x["success"] for x in rr),
                              found=sum(x["program"] is not None for x in rr),
                              mean_candidates=sum(x["candidates"] for x in rr)/len(rr)))
    by_task=[dict(task=task,mode=mode,correct=sum(x["success"] for x in rows if x["task"]==task and x["mode"]==mode),
                  n=len(SEEDS)) for task in TASKS for mode in ("single","fold")]
    summary=dict(protocol="05A-v1",seeds=SEEDS,episodes=len(rows),candidate_limit=LIMIT,aggregate=aggregate,by_task=by_task,
                 examples=[dict(task=x["task"],program=x["program"]) for x in rows if x["seed"]==SEEDS[0] and x["mode"]=="fold" and x["success"]])
    (folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row)+"\n")
    print("SUMMARY_05A="+json.dumps(summary))


class Tests(unittest.TestCase):
    def test_interpreter(self):
        self.assertEqual(execute((FOLD,0,(ADD,(ACC,),(ITEM,))),[2,3,4]),9)
        self.assertEqual(execute((FOLD,0,(IF,(GT,(ITEM,),(ACC,)),(ITEM,),(ACC,))),[-2,4,1]),4)
    def test_synthesis(self):
        train,test=sequences(4)
        p,n,_=synthesize([(s,sum(s)) for s in train],FOLD)
        self.assertIsNotNone(p)
        self.assertLessEqual(n,LIMIT)
        self.assertTrue(all(execute(p,s)==sum(s) for s in test))
    def test_safety_limits(self):
        with self.assertRaises(ValueError):execute((FOLD,0,(ACC,)),[0]*33)
        with self.assertRaises(ZeroDivisionError):execute((FOLD,0,(MOD,(ITEM,),(ACC,))),[5])
    def test_partition(self):
        train,test=sequences(104729);self.assertFalse(set(train)&set(test))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output inside EXPERIMENTO_05 required")
    run(a.output)
