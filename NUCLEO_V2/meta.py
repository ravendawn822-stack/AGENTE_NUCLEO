"""Bounded configuration improvement: only data genomes, never source edits."""
import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
import unittest
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V1_1"))
import synthesis as s
from synthesis import sequence,teacher,FOLD,execute
SEEDS=(510007,540041,570001,600011)
METHODS=("cold","structured","structured_teacher")
BASE=("structured", "none", 3600)
COLD=("cold","none",3600)
BUDGET=3600
TRIALS=8
POLICIES=("fixed_cold","fixed_structured","random_search","local_search","shared_search")


def genome(a,b,k):
    if a not in METHODS or b not in (*METHODS,"none"):raise ValueError("method")
    if b=="none":
        if k!=BUDGET:raise ValueError("single budget")
    elif a==b or k not in (900,1800,2700):raise ValueError("invalid split")
    return a,b,k


def universe():
    return [genome(a,"none",3600) for a in METHODS]+[genome(a,b,k) for a in METHODS for b in METHODS if a!=b for k in (900,1800,2700)]


def neighbors(g):
    # One small data edit, or add/drop the second stage.
    a,b,k=g
    return [h for h in universe() if h!=g and
            (sum(x!=y for x,y in zip(g,h))==1 or (a==h[0] and ("none" in (b,h[1]))))]


def split(seed):
    train,test=sequence.task_pool(seed)
    rng=random.Random(seed^0xAB72)
    dev=[];gate=[]
    for f in sequence.FAMILIES:
        pool=list(train[f]);rng.shuffle(pool);dev.extend(pool[:2]);gate.extend(pool[2:4])
    rng.shuffle(dev);rng.shuffle(gate)
    assert len(dev)==len(gate)==12 and len(test)==24
    assert not(set(dev)&set(gate) or set(dev)&set(test) or set(gate)&set(test))
    return dev,gate,test


def solve(task,g,macros,seed):
    start=time.perf_counter_ns()
    init,pairs,ys,q,consistent=sequence.transitions(lambda z:sequence.oracle(task,z),sequence.observation_sequences(seed))
    a,b,k=genome(*g);attempts=[];expr=None
    plan=[(a,k)]+([] if b=="none" else [(b,BUDGET-k)])
    if consistent:
        for method,cap in plan:
            if method=="cold":expr,n=sequence.synthesize(pairs,ys,[],limit=cap)
            else:expr,n,_=s.structured(pairs,ys,macros if method=="structured_teacher" else [],cap)
            attempts.append(dict(method=method,cap=cap,spent=n,found=expr is not None))
            if expr is not None:break
    p=(FOLD,init,expr) if expr is not None else None
    checks=[]
    if p:
        for z in sequence.check_sequences(seed):
            y=sequence.oracle(task,z)
            try:v=execute(p,z)
            except (ValueError,ZeroDivisionError):v=None
            checks.append([z,y,v])
    return dict(task=task,genome=g,program=p,success=p is not None and all(y==v for _,y,v in checks),
        abstained=p is None,checks=checks,spent=sum(t["spent"] for t in attempts),queries=q,
        attempts=attempts,ns=time.perf_counter_ns()-start)


def batch(tasks,g,macros,seed,phase):
    salt={"development":143,"gate":271,"final":397}[phase]
    return [solve(t,g,macros,seed*29+salt+i*971) for i,t in enumerate(tasks)]


def score(rows):
    # deterministic. Time is recorded but not used to select.
    return (sum(r["success"] for r in rows),-sum(not r["success"] and not r["abstained"] for r in rows),-sum(r["spent"] for r in rows))


def gate_decision(base,new):
    losses=sum(a["success"] and not b["success"] for a,b in zip(base,new))
    gain=sum(not a["success"] and b["success"] for a,b in zip(base,new))
    base_wrong=sum(not a["success"] and not a["abstained"] for a in base)
    new_wrong=sum(not b["success"] and not b["abstained"] for b in new)
    # Protect all known passing gate cases. Require improved correctness or strictly fewer errors.
    accept= not losses and new_wrong<=base_wrong and (gain>0 or new_wrong<base_wrong)
    return dict(accepted=accept,gains=gain,losses=losses,base_wrong=base_wrong,new_wrong=new_wrong)


class Lab:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.executescript("""
          CREATE TABLE trials(seed,policy,phase,trial,genome,score,payload,PRIMARY KEY(seed,policy,phase,trial));
          CREATE TABLE decisions(seed,policy,payload,PRIMARY KEY(seed,policy));
        """)
    def record(self,seed,policy,phase,i,g,rows):
        self.db.execute("INSERT INTO trials VALUES(?,?,?,?,?,?,?)",(seed,policy,phase,i,json.dumps(g),json.dumps(score(rows)),json.dumps(rows)))
        self.db.commit()
    def decision(self,seed,policy,data):
        self.db.execute("INSERT INTO decisions VALUES(?,?,?)",(seed,policy,json.dumps(data)));self.db.commit()


def optimize(lab,seed,policy,dev,gate,macros,shared):
    rng=random.Random(seed+6689)
    parent=BASE;seen=set();best=None;best_score=None;history=[]
    for i in range(TRIALS):
        if i==0:g=BASE
        else:
            remaining=[g for g in universe() if g not in seen]
            if policy=="shared_search" and i<=3:
                offer=next((g for g in shared if g not in seen),None)
            else:offer=None
            local=[g for g in neighbors(parent) if g not in seen]
            g=offer if offer else rng.choice(local if policy!="random_search" and local else remaining)
        rows=batch(dev,g,macros,seed,"development");sc=score(rows)
        lab.record(seed,policy,"development",i,g,rows)
        history.append(dict(trial=i,genome=g,score=sc,parent=parent,source="shared" if i and policy=="shared_search" and offer else "local_or_random"))
        seen.add(g)
        if best_score is None or sc>best_score:best,best_score=g,sc;parent=g
    base_rows=batch(gate,BASE,macros,seed,"gate")
    new_rows=batch(gate,best,macros,seed,"gate")
    lab.record(seed,policy,"gate",0,BASE,base_rows);lab.record(seed,policy,"gate",1,best,new_rows)
    gate_result=gate_decision(base_rows,new_rows)
    chosen=best if gate_result["accepted"] else BASE
    state=dict(seed=seed,policy=policy,current=chosen,proposed=best,previous=BASE,gate=gate_result,
               history=history,development_score=best_score)
    state["sha256"]=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    lab.decision(seed,policy,state)
    return state


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    p=ROOT.parent/"EXPERIMENTO_05C_09A"/"TEACHER_PROPOSALS.json"
    macros,records=teacher.verify_teacher(json.loads(p.read_text(encoding="utf-8")))
    lab=Lab(folder/"optimization.sqlite3")
    decisions=[];final=[];suites={seed:split(seed) for seed in SEEDS}
    # Finish all development and acceptance gates before the first final evaluation.
    own={}
    for seed,(dev,gate,_) in suites.items():
        for policy in ("random_search","local_search"):
            state=optimize(lab,seed,policy,dev,gate,macros,[])
            decisions.append(state)
            if policy=="local_search":
                own[seed]=[tuple(h["genome"]) for h in sorted(state["history"],key=lambda h:tuple(h["score"]),reverse=True)]
    # Shared proposals are only other agents' configurations found in development.
    # No test outcomes exchanged. Same 8 local trials; source exploration has extra system-wide cost.
    for seed,(dev,gate,_) in suites.items():
        shared=list(dict.fromkeys(g for other in SEEDS if other!=seed for g in own[other][:2]))
        decisions.append(optimize(lab,seed,"shared_search",dev,gate,macros,shared))
    for seed,(_,_,test) in suites.items():
        configs={"fixed_cold":COLD,"fixed_structured":BASE}
        configs.update({d["policy"]:tuple(d["current"]) for d in decisions if d["seed"]==seed})
        for policy,g in configs.items():
            rows=batch(test,g,macros,seed,"final")
            lab.record(seed,policy,"final",0,g,rows)
            final.extend(dict(seed=seed,index=i,policy=policy,**r) for i,r in enumerate(rows))
    base={(r["seed"],r["index"]):r for r in final if r["policy"]=="fixed_structured"}
    agg=[]
    for policy in POLICIES:
        rr=[r for r in final if r["policy"]==policy]
        agg.append(dict(policy=policy,n=len(rr),correct=sum(r["success"] for r in rr),
            wrong=sum(not r["success"] and not r["abstained"] for r in rr),
            abstained=sum(r["abstained"] for r in rr),
            gain=sum(r["success"] and not base[r["seed"],r["index"]]["success"] for r in rr),
            loss=sum(not r["success"] and base[r["seed"],r["index"]]["success"] for r in rr),
            mean_spent=sum(r["spent"] for r in rr)/len(rr),mean_ns=sum(r["ns"] for r in rr)/len(rr),
            accepted=sum(d["gate"]["accepted"] for d in decisions if d["policy"]==policy)))
    count=0
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for seed,policy,phase,trial,g,sc,payload in lab.db.execute("SELECT * FROM trials ORDER BY rowid"):
            for i,r in enumerate(json.loads(payload)):
                f.write(json.dumps(dict(seed=seed,policy=policy,phase=phase,trial=trial,index=i,**r))+"\n");count+=1
    lab.db.close()
    result=dict(protocol="NUCLEO_V2_meta_v1",seeds=SEEDS,episodes=count,aggregate=agg,decisions=decisions)
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"teacher_validation.json").write_text(json.dumps(records,indent=2),encoding="utf-8")
    # Small actual data-only configuration, with integrity digest for future loading.
    (folder/"selected_configurations.json").write_text(json.dumps(decisions,indent=2),encoding="utf-8")
    print("SUMMARY_META="+json.dumps(result,separators=(",",":")))


class Tests(unittest.TestCase):
    def test_genome(self):
        self.assertEqual(len(universe()),21)
        with self.assertRaises(ValueError):genome("shell","none",3600)
        with self.assertRaises(ValueError):genome("cold","structured",4000)
    def test_split(self):
        for seed in SEEDS:self.assertEqual(tuple(map(len,split(seed))),(12,12,24))
    def test_gate(self):
        ok=dict(success=True,abstained=False);bad=dict(success=False,abstained=False);stop=dict(success=False,abstained=True)
        self.assertFalse(gate_decision([ok,bad],[bad,ok])["accepted"])
        self.assertTrue(gate_decision([ok,bad],[ok,ok])["accepted"])
        self.assertTrue(gate_decision([ok,bad],[ok,stop])["accepted"])
    def test_budget(self):
        for g in universe():
            r=solve(("square",(1,0)),g,[],77)
            self.assertLessEqual(r["spent"],BUDGET)
    def test_neighborhood(self):
        self.assertTrue(neighbors(BASE));self.assertNotIn(BASE,neighbors(BASE))


if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--self-test",action="store_true");a.add_argument("--output",type=Path);args=a.parse_args()
    if args.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None or ROOT not in args.output.resolve().parents:a.error("new output inside NUCLEO_V2 required")
    run(args.output)
