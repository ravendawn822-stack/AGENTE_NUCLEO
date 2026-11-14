"""V3: discover parameterized symbolic skills from successful programs.
All proposals are bounded numeric AST data, never executable host code.
"""
import argparse
import hashlib
import itertools
import json
import random
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V2_1"))
import constraints as old
from constraints import sequence,meta,FOLD,execute,value,CONST,roundrobin
HOLE=90
SEEDS=(750019,780023,810013,840037)
BASE=3600
EXTRA=900
TRAIN=18000
MAX_SCHEMAS=48
POLICIES=("base","extended","exact","schema","gated")


def encode(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def digest(x):return hashlib.sha256(encode(x).encode()).hexdigest()
def size(e):return 1+sum(size(c) for c in e[1:] if isinstance(c,tuple))


def constants(e):
    if e[0]==CONST:return {e[1]}
    return set().union(*(constants(c) for c in e[1:] if isinstance(c,tuple)))


def abstract(e,chosen):
    if e[0]==CONST and e[1] in chosen:return (HOLE,chosen.index(e[1]))
    return tuple(abstract(c,chosen) if isinstance(c,tuple) else c for c in e)


def bind(e,values):
    if e[0]==HOLE:return (CONST,values[e[1]])
    return tuple(bind(c,values) if isinstance(c,tuple) else c for c in e)


def schemas(e):
    # The abstraction rule is provided; actual trees and slots are discovered from validated programs.
    cs=sorted(x for x in constants(e) if -8<=x<=8)
    for n in (1,2):
        for selected in itertools.combinations(cs,n):
            yield abstract(e,selected),selected


def split(seed):
    train,final=sequence.task_pool(seed)
    rng=random.Random(seed^0xB4105)
    learn=[];gate=[]
    for f in sequence.FAMILIES:
        pool=list(train[f]);rng.shuffle(pool);learn.extend(pool[:4]);gate.extend(pool[4:7])
    rng.shuffle(learn);rng.shuffle(gate)
    assert len(learn)==24 and len(gate)==18 and len(final)==24
    assert not(set(learn)&set(gate) or set(learn)&set(final) or set(gate)&set(final))
    return learn,gate,final


class Memory:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS programs(expr TEXT PRIMARY KEY,origins TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS rules(template TEXT PRIMARY KEY,origins TEXT NOT NULL,bindings TEXT NOT NULL);
        """)
    def acquire(self,e,origin):
        key=encode(e)
        row=self.db.execute("SELECT origins FROM programs WHERE expr=?",(key,)).fetchone()
        origins=json.loads(row[0]) if row else []
        if origin not in origins:origins.append(origin)
        self.db.execute("INSERT OR REPLACE INTO programs VALUES(?,?)",(key,encode(origins)))
        for form,binding in schemas(e):
            k=encode(form)
            row=self.db.execute("SELECT origins,bindings FROM rules WHERE template=?",(k,)).fetchone()
            origins,bindings=(json.loads(row[0]),json.loads(row[1])) if row else ([],[])
            if origin not in origins:origins.append(origin)
            b=list(binding)
            if b not in bindings:bindings.append(b)
            self.db.execute("INSERT OR REPLACE INTO rules VALUES(?,?,?)",(k,encode(origins),encode(bindings)))
        self.db.commit()
    def snapshot(self):
        programs=[dict(expr=json.loads(e),origins=json.loads(o)) for e,o in self.db.execute("SELECT * FROM programs ORDER BY expr")]
        rules=[dict(template=json.loads(e),origins=json.loads(o),bindings=json.loads(b)) for e,o,b in self.db.execute("SELECT * FROM rules ORDER BY template")]
        rules.sort(key=lambda r:(-len(r["origins"]),size(sequence.freeze(r["template"])),encode(r["template"])))
        return dict(programs=programs,rules=rules[:MAX_SCHEMAS],rules_total=len(rules))
    def close(self):self.db.close()


def consistent(e,pairs,ys):
    try:return all(value(e,a,x)==y for (a,x),y in zip(pairs,ys))
    except (ValueError,ZeroDivisionError):return False


def query_program(task,program,seed):
    checks=[]
    if program:
        for seq in sequence.check_sequences(seed):
            y=sequence.oracle(task,seq)
            try:z=execute(program,seq)
            except (ValueError,ZeroDivisionError):z=None
            checks.append([seq,y,z])
    valid=program is not None and all(y==z for _,y,z in checks)
    return valid,checks


def bindings(rule,pairs):
    # No hidden family label or target parameter. Enumerate bounded bindings,
    # prioritizing constants close to the observed input support.
    xs={x for a,x in pairs}
    order=sorted(range(-8,9),key=lambda v:(min(abs(v-x) for x in xs),abs(v),v))
    arity=len(rule["bindings"][0])
    prior={tuple(v) for v in rule["bindings"]}
    # The schema arm tests new instantiations only. Literal reuse is a separate control.
    for v in itertools.product(order,repeat=arity):
        if v not in prior:yield bind(sequence.freeze(rule["template"]),v),v,rule


def recall(snapshot,pairs,ys,kind,limit):
    if kind=="exact":
        pool=((sequence.freeze(r["expr"]),None,r) for r in snapshot["programs"])
    else:
        pool=roundrobin(*(bindings(r,pairs) for r in snapshot["rules"]))
    seen=set();tested=0
    for e,binding,rule in itertools.islice(pool,limit):
        tested+=1 # duplicates also consume a unit
        if e in seen:continue
        seen.add(e)
        if consistent(e,pairs,ys):
            return e,tested,dict(kind=kind,binding=binding,source=rule)
    return None,tested,None


def observations(task,seed):
    return sequence.transitions(lambda q:sequence.oracle(task,q),sequence.observation_sequences(seed))


def train(task,seed):
    start=time.perf_counter_ns()
    init,pairs,ys,q,ok=observations(task,seed)
    e,n,m=old.synthesize(pairs,ys,"derived",TRAIN) if ok else (None,0,{})
    p=(FOLD,init,e) if e is not None else None
    valid,checks=query_program(task,p,seed)
    return dict(task=task,program=p,success=valid,abstained=p is None,spent=n,queries=q,checks=checks,
                observations=list(zip(pairs,ys)),ns=time.perf_counter_ns()-start)


def solve(task,seed,policy,snapshot):
    start=time.perf_counter_ns()
    init,pairs,ys,q,ok=observations(task,seed)
    cap=BASE+EXTRA if policy=="extended" else BASE
    e,n,_=old.synthesize(pairs,ys,"derived",cap) if ok else (None,0,{})
    used=None;recall_n=0
    # Both memory arms preserve the identical cold candidate if found, even if it turns out wrong.
    if ok and e is None and policy in ("exact","schema"):
        e,recall_n,used=recall(snapshot,pairs,ys,policy,EXTRA)
    p=(FOLD,init,e) if e is not None else None
    elapsed=time.perf_counter_ns()-start
    success,checks=query_program(task,p,seed)
    return dict(task=task,method=policy,program=p,success=success,abstained=p is None,spent=n+recall_n,
                base_spent=n,recall_spent=recall_n,queries=q,recall=used,checks=checks,
                search_ns=elapsed,ns=time.perf_counter_ns()-start)


def batch(tasks,policy,snapshot,seed,phase):
    salt={"gate":217,"final":503}[phase]
    return [solve(t,seed*43+salt+i*631,policy,snapshot) for i,t in enumerate(tasks)]


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    rows=[];decisions=[];memories={}
    suites={seed:split(seed) for seed in SEEDS}
    def record(seed,phase,policy,items):
        rows.extend(dict(seed=seed,index=i,phase=phase,policy=policy,**item) for i,item in enumerate(items))
    for seed,(learn,gate,_) in suites.items():
        path=folder/f"memory_{seed}.sqlite3";mem=Memory(path)
        for i,t in enumerate(learn):
            r=train(t,seed*29+i*997)
            if r["success"]:mem.acquire(r["program"][2],f"{seed}/{i}")
            record(seed,"learn","acquire",[dict(r,training_index=i)])
        before=mem.snapshot();mem.close();mem=Memory(path);snapshot=mem.snapshot();mem.close()
        assert digest(before)==digest(snapshot)
        memories[seed]=snapshot
        gate_rows={}
        for p in ("extended","exact","schema"):
            rr=batch(gate,p,snapshot,seed,"gate");gate_rows[p]=rr;record(seed,"gate",p,rr)
        decision=meta.gate_decision(gate_rows["extended"],gate_rows["schema"])
        decisions.append(dict(seed=seed,gate=decision,selected="schema" if decision["accepted"] else "extended",
                              programs=len(snapshot["programs"]),rules=len(snapshot["rules"]),rules_total=snapshot["rules_total"],
                              memory_sha=digest(snapshot)))
    for seed,(_,_,tasks) in suites.items():
        snapshot=memories[seed];before=digest(snapshot)
        chosen=next(x["selected"] for x in decisions if x["seed"]==seed)
        for p in POLICIES:
            record(seed,"final",p,batch(tasks,chosen if p=="gated" else p,snapshot,seed,"final"))
        assert digest(snapshot)==before
        assert before==next(x["memory_sha"] for x in decisions if x["seed"]==seed)
    final=[r for r in rows if r["phase"]=="final"]
    base={(r["seed"],r["index"]):r for r in final if r["policy"]=="extended"}
    def metrics(rr):
        n=len(rr)
        return dict(n=n,correct=sum(r["success"] for r in rr),wrong=sum(not r["success"] and not r["abstained"] for r in rr),
            abstained=sum(r["abstained"] for r in rr),
            gain_vs_extended=sum(r["success"] and not base[r["seed"],r["index"]]["success"] for r in rr),
            loss_vs_extended=sum(not r["success"] and base[r["seed"],r["index"]]["success"] for r in rr),
            recalled=sum(r["recall"] is not None for r in rr),
            recalled_correct=sum(r["recall"] is not None and r["success"] for r in rr),
            mean_spent=sum(r["spent"] for r in rr)/n,mean_search_ns=sum(r["search_ns"] for r in rr)/n)
    examples=[dict(seed=r["seed"],task=r["task"],program=r["program"],source=r["recall"])
              for r in final if r["policy"]=="schema" and r["recall"] is not None and r["success"]]
    result=dict(protocol="NUCLEO_V3-schema-v1",episodes=len(rows),seeds=SEEDS,decisions=decisions,
        training_correct=sum(r["success"] for r in rows if r["phase"]=="learn"),training_n=sum(r["phase"]=="learn" for r in rows),
        aggregate=[dict(policy=p,**metrics([r for r in final if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metrics([r for r in final if r["policy"]==p and r["task"][0]==f])) for p in POLICIES for f in sequence.FAMILIES],
        examples=examples[:8])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"memories.json").write_text(json.dumps(memories,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_SCHEMA="+encode(result))


class Tests(unittest.TestCase):
    def test_abstract_bind(self):
        e=(10,(0,),(12,(1,),(2,3)))
        rules=list(schemas(e));self.assertEqual(len(rules),1)
        form,b=rules[0];self.assertEqual(bind(form,b),e)
        self.assertEqual(bind(form,(5,)),(10,(0,),(12,(1,),(2,5))))
    def test_generalization(self):
        e=(10,(0,),(12,(1,),(2,3)))
        with tempfile.TemporaryDirectory() as t:
            m=Memory(Path(t)/"m.db");m.acquire(e,"example");snapshot=m.snapshot();m.close()
            pairs=[(0,-2),(3,0),(7,3),(1,1)];ys=[a+5*x for a,x in pairs]
            p,n,record=recall(snapshot,pairs,ys,"schema",EXTRA)
            self.assertTrue(consistent(p,pairs,ys));self.assertEqual(record["binding"],(5,))
            self.assertEqual(recall(snapshot,pairs,ys,"exact",EXTRA)[0],None)
    def test_limits(self):
        e=(10,(0,),(12,(1,),(2,3)))
        with tempfile.TemporaryDirectory() as t:
            m=Memory(Path(t)/"m.db");m.acquire(e,"example");snapshot=m.snapshot();m.close()
            p,n,_=recall(snapshot,[(0,1),(0,2)],[999,999],"schema",3)
            self.assertIsNone(p);self.assertEqual(n,3)
    def test_partitions(self):
        for seed in SEEDS:self.assertEqual(tuple(map(len,split(seed))),(24,18,24))
    def test_reopen(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"m.db";m=Memory(path)
            m.acquire((10,(0,),(2,2)),"a");d=digest(m.snapshot());m.close();m=Memory(path)
            self.assertEqual(d,digest(m.snapshot()));m.close()


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output in NUCLEO_V3 required")
    run(a.output)
