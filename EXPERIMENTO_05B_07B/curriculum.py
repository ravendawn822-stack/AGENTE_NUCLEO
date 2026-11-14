"""05B/07B/08B: persistent symbolic skills, autonomous curriculum and capability estimates."""
import argparse
import hashlib
import json
import math
import random
import sqlite3
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"EXPERIMENTO_05"))
from programs import ACC,ITEM,CONST,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ,IF,FOLD,value,execute,roundrobin

SEEDS=(104729,130363,155921)
FAMILIES=("linear","absolute","square","threshold","extreme","mod_count")
POLICIES=("no_memory","cyclic","random","progress")
CAP=1800
MEMCAP=18
STEPS=24
CHECKPOINTS=(0,12,24)


def task_pool(seed):
    r=random.Random(seed);train={};test=[]
    choices={
        "linear":[(a,b) for a in (-2,-1,1,2,3) for b in range(-4,5)],
        "absolute":[(sign,t) for sign in (-1,1) for t in range(-4,5)],
        "square":[(sign,t) for sign in (-1,1) for t in range(-4,5)],
        "threshold":[(sign,t) for sign in (-1,1) for t in range(-5,6)],
        "extreme":[(sign,t) for sign in (-1,1) for t in range(-4,5)],
        "mod_count":[(p,q) for p in range(2,7) for q in range(p)],
    }
    for f in FAMILIES:
        a=list(choices[f]);r.shuffle(a)
        train[f]=[(f,v) for v in a[:10]]
        test.extend((f,v) for v in a[10:14])
    r.shuffle(test)
    assert not set(test)&{x for v in train.values() for x in v}
    return train,test


def oracle(task,seq):
    family,(p,q)=task;a=0
    for x in seq:
        if family=="linear":a+=p*x+q
        elif family=="absolute":a+=p*abs(x-q)
        elif family=="square":a+=p*(x-q)**2
        elif family=="threshold":a+=int(x>q if p==1 else x<q)
        elif family=="extreme":a=max(a,x+q) if p==1 else min(a,x+q)
        else:a+=int(x%p==q)
    return a


def observation_sequences(seed):
    r=random.Random(seed)
    seq=[(),*((x,) for x in range(-4,5))]
    seq.extend(tuple(r.randint(-5,5) for _ in range(r.randint(2,4))) for i in range(8))
    return seq


def check_sequences(seed):
    r=random.Random(seed^0xAABBCC)
    return [tuple(r.randint(-8,8) for _ in range(r.randint(6,12))) for i in range(16)]


def transitions(query,seqs):
    cache={}
    def get(seq):
        if seq not in cache:cache[seq]=query(seq)
        return cache[seq]
    init=get(());pairs={}
    for seq in seqs:
        for i,x in enumerate(seq):
            a,b=get(seq[:i]),get(seq[:i+1])
            key=(a,x)
            if key in pairs and pairs[key]!=b:return init,[],[],len(cache),False
            pairs[key]=b
    return init,list(pairs),list(pairs.values()),len(cache),True


def freeze(x):return tuple(freeze(y) for y in x) if isinstance(x,(list,tuple)) else x

def size(e):return 1+sum(size(x) for x in e[1:] if isinstance(x,tuple))
def subtrees(e):
    if size(e)>1:
        yield e
        for c in e[1:]:
            if isinstance(c,tuple):yield from subtrees(c)


def synthesize(pairs,expected,mem,limit=CAP):
    # Candidate cost counts even duplicates/undefined candidates. Semantic dedup is local to evidence.
    target=tuple(expected);seen=set();levels={};count=0
    leaves=((ACC,),(ITEM,),*((CONST,c) for c in (-2,-1,0,1,2)))
    def offer(expr,vec,cost):
        nonlocal count
        count+=1
        if vec is None or size(expr)>25:return False
        if vec==target:return True
        if vec not in seen:
            seen.add(vec);levels[cost].append((expr,vec))
        return False
    levels[1]=[]
    for expr in (*leaves,*mem):
        if count>=limit:return None,count
        try:vec=tuple(value(expr,a,x) for a,x in pairs)
        except (ZeroDivisionError,ValueError):vec=None
        if offer(expr,vec,1):return expr,count
    binary=(ADD,SUB,MUL,MOD,GT,EQ)
    def apply(op,vs):
        try:
            if op==ABS:return tuple(abs(a) for a in vs[0])
            if op==NEG:return tuple(-a for a in vs[0])
            if op==IF:return tuple(b if a else c for a,b,c in zip(*vs))
            a,b=vs
            if op==ADD:return tuple(x+y for x,y in zip(a,b))
            if op==SUB:return tuple(x-y for x,y in zip(a,b))
            if op==MUL:return tuple(x*y for x,y in zip(a,b))
            if op==MOD:return tuple(x%y for x,y in zip(a,b))
            if op==GT:return tuple(int(x>y) for x,y in zip(a,b))
            if op==EQ:return tuple(int(x==y) for x,y in zip(a,b))
        except ZeroDivisionError:return None
    for cost in range(2,8):
        levels[cost]=[]
        unary=((op,(e,),(v,)) for e,v in levels[cost-1] for op in (ABS,NEG))
        bgen=((op,(a,b),(av,bv)) for s in range(1,cost-1)
              for a,av in levels[s] for b,bv in levels[cost-1-s] for op in binary)
        cgen=((IF,(a,b,c),(av,bv,cv)) for s in range(1,cost-2)
              for t in range(1,cost-1-s) for a,av in levels[s] for b,bv in levels[t]
              for c,cv in levels[cost-1-s-t])
        for op,exprs,vs in roundrobin(unary,bgen,cgen):
            if count>=limit:return None,count
            if offer((op,*exprs),apply(op,vs),cost):return (op,*exprs),count
    return None,count


def solve_task(task,mem,seed):
    start=time.perf_counter_ns()
    initial,pairs,ys,queries,consistent=transitions(lambda s:oracle(task,s),observation_sequences(seed))
    e,n=synthesize(pairs,ys,mem) if consistent else (None,0)
    p=(FOLD,initial,e) if e is not None else None
    checks=[]
    if p:
        for seq in check_sequences(seed):
            expected=oracle(task,seq)
            try:pred=execute(p,seq)
            except (ZeroDivisionError,ValueError):pred=None
            checks.append([seq,expected,pred])
    return dict(program=p,success=p is not None and all(y==z for _,y,z in checks),
                candidates=n,oracle_queries=queries,checks=checks,observed=list(zip(pairs,ys)),
                elapsed_ns=time.perf_counter_ns()-start)


def update_memory(mem,program):
    for e in subtrees(program[2]):
        if e not in mem:
            mem.append(e)
            if len(mem)>MEMCAP:mem.pop(0)


def choose(policy,history,pool,rng,step):
    available=[f for f in FAMILIES if pool[f]]
    if policy=="random":return rng.choice(available),{}
    if policy in ("cyclic","no_memory"):
        return next(FAMILIES[(step+i)%len(FAMILIES)] for i in range(len(FAMILIES)) if FAMILIES[(step+i)%len(FAMILIES)] in available),{}
    scores={}
    for f in available:
        h=history[f]
        recent=h[-3:];prior=h[-6:-3]
        a=(sum(recent)+1)/(len(recent)+2);b=(sum(prior)+1)/(len(prior)+2)
        scores[f]=max(0,a-b)+.35/math.sqrt(len(h)+1)+(1 if not h else 0)
    best=max(scores.values())
    return rng.choice([f for f in available if scores[f]==best]),scores


def probability(events):return (sum(events)+1)/(len(events)+2)
def state_digest(mem,history):
    return hashlib.sha256(json.dumps([mem,history],sort_keys=True).encode()).hexdigest()


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    db=sqlite3.connect(folder/"memory.sqlite3")
    db.executescript("""CREATE TABLE snapshots(seed,policy,step,skills,history,digest,PRIMARY KEY(seed,policy,step));
    CREATE TABLE episodes(seed,policy,phase,step,idx,payload,PRIMARY KEY(seed,policy,phase,step,idx));""")
    results=[]
    for seed in SEEDS:
        base,test=task_pool(seed)
        for pi,policy in enumerate(POLICIES):
            pool={k:list(v) for k,v in base.items()}
            mem=[];history={f:[] for f in FAMILIES};rng=random.Random(seed+pi*919)
            for step in range(STEPS+1):
                if step in CHECKPOINTS:
                    digest=state_digest(mem,history)
                    db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?)",(seed,policy,step,json.dumps(mem),json.dumps(history),digest));db.commit()
                    saved=db.execute("SELECT skills,history,digest FROM snapshots WHERE seed=? AND policy=? AND step=?",(seed,policy,step)).fetchone()
                    recovered=[freeze(e) for e in json.loads(saved[0])]
                    hh=json.loads(saved[1])
                    assert state_digest(recovered,hh)==saved[2]
                    rows=[];global_p=probability([x for h in hh.values() for x in h])
                    for i,task in enumerate(test):
                        row=solve_task(task,recovered,seed*19+i*701)
                        row.update(task=task,predicted_capability=probability(hh[task[0]]),global_capability=global_p)
                        rows.append(row)
                        db.execute("INSERT INTO episodes VALUES(?,?,?,?,?,?)",(seed,policy,"evaluation",step,i,json.dumps(row)))
                    assert state_digest(recovered,hh)==digest
                    results.append(dict(seed=seed,policy=policy,step=step,n=len(rows),correct=sum(x["success"] for x in rows),
                        memory=len(mem),mean_candidates=sum(x["candidates"] for x in rows)/len(rows),
                        mean_queries=sum(x["oracle_queries"] for x in rows)/len(rows),
                        mean_ms=sum(x["elapsed_ns"] for x in rows)/len(rows)/1e6,
                        brier_context=sum((x["predicted_capability"]-int(x["success"]))**2 for x in rows)/len(rows),
                        brier_global=sum((x["global_capability"]-int(x["success"]))**2 for x in rows)/len(rows),
                        brier_neutral=.25,train_by_family={f:len(history[f]) for f in FAMILIES}))
                    db.commit()
                if step==STEPS:break
                family,scores=choose(policy,history,pool,rng,step)
                task=pool[family].pop(0)
                row=solve_task(task,mem,seed*37+step*1009)
                history[family].append(int(row["success"]))
                before=len(mem)
                if row["success"] and policy!="no_memory":update_memory(mem,row["program"])
                row.update(task=task,curriculum_scores=scores,memory_before=before,memory_after=len(mem))
                db.execute("INSERT INTO episodes VALUES(?,?,?,?,?,?)",(seed,policy,"training",step+1,0,json.dumps(row)));db.commit()
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for seed,policy,phase,step,idx,payload in db.execute("SELECT * FROM episodes ORDER BY seed,policy,phase,step,idx"):
            f.write(json.dumps(dict(seed=seed,policy=policy,phase=phase,step=step,index=idx,**json.loads(payload)))+"\n")
    total=db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0];db.close()
    aggregate=[]
    for policy in POLICIES:
        for step in CHECKPOINTS:
            rr=[x for x in results if x["policy"]==policy and x["step"]==step]
            aggregate.append(dict(policy=policy,step=step,n=sum(x["n"] for x in rr),correct=sum(x["correct"] for x in rr),
                memory_avg=sum(x["memory"] for x in rr)/len(rr),mean_candidates=sum(x["mean_candidates"] for x in rr)/len(rr),
                mean_ms=sum(x["mean_ms"] for x in rr)/len(rr),
                brier_context=sum(x["brier_context"] for x in rr)/len(rr),brier_global=sum(x["brier_global"] for x in rr)/len(rr),
                train_by_family={f:sum(x["train_by_family"][f] for x in rr) for f in FAMILIES}))
    summary=dict(protocol="05B-07B-08B-v1",episodes=total,seeds=SEEDS,aggregate=aggregate,by_seed=results)
    (folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print("SUMMARY_CURRICULUM="+json.dumps(summary))


class Tests(unittest.TestCase):
    def test_splits(self):
        for seed in SEEDS:
            a,b=task_pool(seed);self.assertEqual(len(b),24);self.assertFalse(set(b)&{x for vs in a.values() for x in vs})
    def test_synth(self):
        m=solve_task(("linear",(1,0)),[],5)
        self.assertTrue(m["success"]);self.assertLessEqual(m["candidates"],CAP)
    def test_limit(self):
        e,n=synthesize([(0,0),(0,1)],[500,900],[],limit=3)
        self.assertIsNone(e);self.assertEqual(n,3)
    def test_curriculum(self):
        history={f:[] for f in FAMILIES};pool,_=task_pool(5)
        family,s=choose("progress",history,pool,random.Random(4),0)
        self.assertIn(family,FAMILIES);self.assertEqual(len(s),len(FAMILIES))
        history[family].append(1)
        next_f,_=choose("progress",history,pool,random.Random(4),1)
        self.assertNotEqual(family,next_f)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output inside EXPERIMENTO_05B_07B required")
    run(a.output)
