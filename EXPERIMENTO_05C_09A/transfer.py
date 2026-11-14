"""05C/09A: protect cold search, verify offline teacher proposals, measure transfer."""
import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"EXPERIMENTO_05B_07B"))
from curriculum import (SEEDS,FAMILIES,task_pool,oracle,transitions,observation_sequences,
                        check_sequences,synthesize,freeze)
from programs import ACC,ITEM,CONST,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ,IF,FOLD,value,execute
POLICIES=("cold_1800","learned_1800","teacher_1800","cold_3600","guarded_learned","guarded_teacher")


def check_tree(e,level=0):
    if level>7 or not isinstance(e,list) or not e or type(e[0]) is not int:return False
    op=e[0]
    if op in (ACC,ITEM):return len(e)==1
    if op==CONST:return len(e)==2 and type(e[1]) is int and -16<=e[1]<=16
    arity={ABS:1,NEG:1,ADD:2,SUB:2,MUL:2,MOD:2,GT:2,EQ:2,IF:3}.get(op)
    return arity is not None and len(e)==1+arity and all(check_tree(x,level+1) for x in e[1:])


def truth(contract,x):
    if contract=="square":return x*x
    if contract=="positive":return int(x>0)
    if contract=="negative":return int(x<0)
    if contract=="even":return int(x%2==0)
    if contract=="absolute":return abs(x)
    if contract=="double":return 2*x
    raise ValueError("unknown contract")


def verify_teacher(proposals):
    mem=[];records=[]
    for p in proposals["skills"]:
        e=p["expr"];valid=False;reason="invalid DSL";checks=[]
        if check_tree(e):
            try:
                e=freeze(e)
                for a in (-13,-2,0,4,11):
                    for x in range(-19,20):
                        y=truth(p["contract"],x);z=value(e,a,x)
                        checks.append([a,x,y,z])
                valid=all(y==z for _,_,y,z in checks);reason="passed finite checks" if valid else "counterexample"
            except (ValueError,ZeroDivisionError):reason="undefined behavior or contract"
        if valid and e not in mem:mem.append(e)
        records.append(dict(id=p["id"],contract=p["contract"],expr=p["expr"],accepted=valid,reason=reason,checks=checks))
    return mem,records


def new_tasks(seed):
    # The earlier train pool and even its final evaluation set are excluded per seed.
    # All remaining specifications are generated independently of policy results.
    train,test=task_pool(seed)
    used={x for vs in train.values() for x in vs}|set(test)
    universes={
      "linear":[(a,b) for a in (-2,-1,1,2,3) for b in range(-4,5)],
      "absolute":[(s,t) for s in (-1,1) for t in range(-4,5)],
      "square":[(s,t) for s in (-1,1) for t in range(-4,5)],
      "threshold":[(s,t) for s in (-1,1) for t in range(-5,6)],
      "extreme":[(s,t) for s in (-1,1) for t in range(-4,5)],
      "mod_count":[(p,q) for p in range(2,7) for q in range(p)]}
    r=random.Random(seed^0xCEFF45);rows=[]
    for f in FAMILIES:
        available=[(f,p) for p in universes[f] if (f,p) not in used]
        r.shuffle(available);rows+=available[:4]
    assert len(rows)==24 and not set(rows)&used
    r.shuffle(rows)
    return rows


def load_snapshots(path):
    db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    try:
        snapshots={}
        for seed,skills,history,digest in db.execute("SELECT seed,skills,history,digest FROM snapshots WHERE policy='cyclic' AND step=24"):
            parsed=json.loads(skills);hh=json.loads(history)
            assert hashlib.sha256(json.dumps([parsed,hh],sort_keys=True).encode()).hexdigest()==digest
            snapshots[seed]=[freeze(e) for e in parsed]
        assert set(snapshots)==set(SEEDS)
        return snapshots
    finally:db.close()


def solve(task,learned,teacher,policy,seed):
    start=time.perf_counter_ns()
    init,pairs,ys,queries,consistent=transitions(lambda s:oracle(task,s),observation_sequences(seed))
    assert consistent
    plans={
      "cold_1800":[("cold",[],1800)],"learned_1800":[("learned",learned,1800)],
      "teacher_1800":[("teacher",teacher,1800)],"cold_3600":[("cold",[],3600)],
      "guarded_learned":[("cold",[],1800),("learned",learned,1800)],
      "guarded_teacher":[("cold",[],1800),("teacher",teacher,1800)]}
    attempts=[];e=None
    for channel,mem,cap in plans[policy]:
        e,n=synthesize(pairs,ys,mem,limit=cap)
        attempts.append(dict(channel=channel,count=n,found=e is not None,limit=cap))
        # No access to final checks until selection is finalized.
        if e is not None:break
    search_ns=time.perf_counter_ns()-start
    program=(FOLD,init,e) if e is not None else None
    checks=[]
    if program:
        for seq in check_sequences(seed):
            y=oracle(task,seq)
            try:z=execute(program,seq)
            except (ValueError,ZeroDivisionError):z=None
            checks.append([seq,y,z])
    return dict(program=program,success=program is not None and all(y==z for _,y,z in checks),
        observations=list(zip(pairs,ys)),queries=queries,attempts=attempts,
        candidates=sum(a["count"] for a in attempts),search_ns=search_ns,
        total_ns=time.perf_counter_ns()-start,checks=checks)


def run(folder,snapshot):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    snaps=load_snapshots(snapshot)
    proposals=json.loads((ROOT/"TEACHER_PROPOSALS.json").read_text(encoding="utf-8"))
    teacher,records=verify_teacher(proposals)
    rows=[]
    for seed in SEEDS:
        for i,task in enumerate(new_tasks(seed)):
            for policy in POLICIES:
                m=solve(task,snaps[seed],teacher,policy,seed*43+i*197)
                rows.append(dict(seed=seed,index=i,task=task,policy=policy,**m))
    base={(x["seed"],x["index"]):x for x in rows if x["policy"]=="cold_1800"}
    agg=[]
    for p in POLICIES:
        rr=[r for r in rows if r["policy"]==p]
        agg.append(dict(policy=p,n=len(rr),correct=sum(r["success"] for r in rr),
          losses_vs_cold=sum(base[r["seed"],r["index"]]["success"] and not r["success"] for r in rr),
          gains_vs_cold=sum(not base[r["seed"],r["index"]]["success"] and r["success"] for r in rr),
          mean_candidates=sum(r["candidates"] for r in rr)/len(rr),
          mean_total_ns=sum(r["total_ns"] for r in rr)/len(rr),
          fallback=sum(len(r["attempts"])>1 for r in rr)))
    summary=dict(protocol="05C-09A-v1",episodes=len(rows),seeds=SEEDS,teacher_accepted=[r["id"] for r in records if r["accepted"]],
      teacher_rejected=[r["id"] for r in records if not r["accepted"]],aggregate=agg,
      snapshot_bytes_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest())
    (folder/"teacher_validation.json").write_text(json.dumps(records,indent=2),encoding="utf-8")
    (folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row)+"\n")
    print("SUMMARY_05C09A="+json.dumps(summary))


class Tests(unittest.TestCase):
    def test_validation(self):
        p=json.loads((ROOT/"TEACHER_PROPOSALS.json").read_text(encoding="utf-8"))
        mem,rows=verify_teacher(p)
        self.assertEqual(len(mem),6)
        self.assertEqual(sum(not x["accepted"] for x in rows),2)
    def test_new_cases(self):
        for seed in SEEDS:self.assertEqual(len(new_tasks(seed)),24)
    def test_guard(self):
        a=solve(("linear",(1,0)),[],[],"cold_1800",5)
        b=solve(("linear",(1,0)),[(MUL,(ITEM,),(ITEM,))],[],"guarded_learned",5)
        self.assertTrue(a["success"]);self.assertEqual(a["program"],b["program"])
        self.assertEqual(len(b["attempts"]),1)
    def test_reject_code(self):
        self.assertFalse(check_tree([999,[1]]))
        self.assertFalse(check_tree([2,10000000]))
        self.assertFalse(check_tree([10,[1]]))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--snapshot",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or a.snapshot is None or ROOT not in a.output.resolve().parents:p.error("new output and prior snapshot required")
    run(a.output,a.snapshot)
