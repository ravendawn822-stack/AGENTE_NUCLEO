"""V4: bounded residual planning, independent transfer, and an offline lesson gate."""
import argparse
import hashlib
import itertools
import json
import random
import sqlite3
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V3_1"))
import hierarchy as h
from hierarchy import old,sequence,prev,FOLD,execute,value,CONST,ACC,ITEM,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ
SEEDS=(990011,1020011,1050011,1080007)
FAMILIES=("pair","triple","product","mixed_product","order")
POLICIES=("pair_only","primitive_plan","memory_plan","expert_plan","guarded","lesson_gate")
CAP=500
PAIR_CAP=60000
PLAN_CAP=2000
GUARD=(-15,-11,11,15)
A=(ACC,)
X=(ITEM,)


def enc(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def sha(x):return hashlib.sha256(enc(x).encode()).hexdigest()


def make_tasks(seed,forbidden):
    rng=random.Random(seed);seen=set(forbidden);train=[];test=[]
    def gen(f,idx,phase):
        count=3 if f in ("triple","mixed_product") else 2
        while True:
            terms=tuple(h.term(rng) for _ in range(count))
            if len(set(terms))<count:continue
            t=dict(family=f,terms=terms,id=f"{seed}/{phase}/{f}/{idx}")
            sig=signature(t)
            if sig not in seen:
                seen.add(sig);return t
    for f in FAMILIES:
        train.extend(gen(f,i,"dev") for i in range(3))
        test.extend(gen(f,i,"final") for i in range(10))
    rng.shuffle(train);rng.shuffle(test)
    return train,test


def target(t,z):
    f=t["family"];terms=t["terms"]
    if f=="order":return sum((-1 if i%2 else 1)*h.atom(terms[0],x)+h.atom(terms[1],x) for i,x in enumerate(z))
    if f=="product":return sum(h.atom(terms[0],x)*h.atom(terms[1],x) for x in z)
    if f=="mixed_product":return sum(h.atom(terms[0],x)*h.atom(terms[1],x)+h.atom(terms[2],x) for x in z)
    return sum(sum(h.atom(a,x) for a in terms) for x in z)


def signature(t):
    return tuple(target(t,(x,)) for x in range(-31,32))+(target(t,(2,-3,5)),target(t,(5,-3,2)))


def prior_signatures():
    result=set()
    for seed in h.SEEDS:
        train,test=h.tasks(seed)
        for t in train+test:
            result.add(tuple(h.target(t,(x,)) for x in range(-31,32))+(h.target(t,(2,-3,5)),h.target(t,(5,-3,2))))
    return result


def plus(a,b):return tuple(x+y for x,y in zip(a,b))
def minus(a,b):return tuple(x-y for x,y in zip(a,b))
def times(a,b):return tuple(x*y for x,y in zip(a,b))


class Planner:
    # Index is constructed before receiving a task, from only allowed expressions.
    def __init__(self,pool,plan=True):
        start=time.perf_counter_ns();self.pool=pool;self.index={r["vec"]:i for i,r in enumerate(pool)}
        self.pairs={};self.spent=0
        if plan:
            # Interleave combination type, deterministic pair order; no target-based cache.
            for i,j in itertools.combinations_with_replacement(range(len(pool)),2):
                a,b=pool[i]["vec"],pool[j]["vec"]
                for op,v in ((ADD,plus(a,b)),(MUL,times(a,b))):
                    if self.spent>=PAIR_CAP:break
                    self.spent+=1
                    self.pairs.setdefault(v,(op,i,j))
                if self.spent>=PAIR_CAP:break
        self.build_ns=time.perf_counter_ns()-start
    def leaf(self,i):return self.pool[i]["expr"]
    def origin(self,i):return self.pool[i]["source"]
    def form(self,op,i,j):return (op,self.leaf(i),self.leaf(j))
    def solve(self,v,plan=True):
        trace=[];checks=0
        if v in self.index:
            i=self.index[v];return self.leaf(i),1,[self.origin(i)],[dict(goal="direct",found=True)]
        checks+=1
        # First use previous pair join; this preserves its first candidate.
        for i,r in enumerate(self.pool):
            for op,rest in ((ADD,minus(v,r["vec"])),(SUB,minus(r["vec"],v))):
                if checks>=h.JOIN_CAP:break
                checks+=1
                j=self.index.get(rest)
                if j is not None and h.size(self.form(op,i,j))<=75:
                    return self.form(op,i,j),checks,[self.origin(i),self.origin(j)],[dict(goal="two_terms",found=True)]
            if checks>=h.JOIN_CAP:break
        trace.append(dict(goal="two_terms",found=False))
        if not plan:return None,checks,[],trace
        # A subgoal is the residual vector remaining after a hypothesized first term.
        # The indexed subproblem can be a sum or product of two fragments.
        checks+=1
        pair=self.pairs.get(v)
        if pair:
            op,i,j=pair
            e=self.form(op,i,j)
            if h.size(e)<=110:return e,checks,[self.origin(i),self.origin(j)],trace+[dict(goal="indexed_pair",operator=op,found=True)]
        for i,r in enumerate(self.pool):
            if checks>=PLAN_CAP:break
            checks+=1;residual=minus(v,r["vec"]);pair=self.pairs.get(residual)
            if pair:
                op,j,k=pair;e=(ADD,self.leaf(i),self.form(op,j,k))
                if h.size(e)<=110:
                    return e,checks,[self.origin(i),self.origin(j),self.origin(k)],trace+[dict(goal="residual",found=True,chosen=r["expr"],remaining=list(residual),operator=op)]
        return None,checks,[],trace+[dict(goal="residual",found=False)]


def lesson_rows(group):
    # Fixed offline lessons, provided by developer rather than generated by an LLM.
    # A separate reference checks all proposed expressions on a wide grid.
    rows=[];rejected=0
    specs=[]
    if group=="shape":
        for c in range(-5,6):
            specs.extend([((ABS,(SUB,X,(CONST,c))),("abs",c,1)),
                          ((MUL,(SUB,X,(CONST,c)),(SUB,X,(CONST,c))),("square",c,1))])
    elif group=="predicate":
        for c in range(-5,6):
            specs.extend([((GT,X,(CONST,c)),("gt",c,1)),((GT,(CONST,c),X),("lt",c,1))])
        for p in range(2,8):
            for q in range(p):specs.append(((EQ,(MOD,X,(CONST,p)),(CONST,q)),("mod",p,q)))
        specs.append(((CONST,0),("gt",0,1))) # negative control
    else:raise ValueError(group)
    for e,t in specs:
        if all(value(e,0,x)==h.atom(t,x) for x in range(-31,32)):
            rows.append(dict(expr=e,vec=h.vector(e),source=dict(kind="offline_lesson",group=group,contract=t)))
        else:rejected+=1
    return rows,rejected


def restore(bank):
    rows=[]
    for r in bank["learned"]:
        e=h.freeze(r["expr"]);v=h.vector(e)
        assert list(v)==r["vec"]
        rows.append(dict(expr=e,vec=v,source=r["source"]))
    return rows


def verify_program(p,t,seed):
    checks=[]
    if p:
        for z in h.validation_seqs(seed):
            if len(z)==1 and z[0] in GUARD:continue
            y=target(t,z)
            try:v=execute(p,z)
            except (ValueError,ZeroDivisionError):v=None
            checks.append([z,y,v])
    return p is not None and all(a==b for _,a,b in checks),checks


def solve(t,planner,mode,seed):
    start=time.perf_counter_ns()
    init,pairs,ys,queries,ok=sequence.transitions(lambda z:target(t,z),h.observation_seqs())
    bounds=old.constraints(pairs,ys,"add") if ok else None
    p=None;used=[];trace=[];work=0
    if bounds is not None and all(lo is not None and lo==hi for lo,hi in bounds):
        by_x=dict(zip(sorted({x for a,x in pairs}),(lo for lo,hi in bounds)))
        g,work,used,trace=planner.solve(tuple(by_x[x] for x in h.XS),mode!="pair_only")
        if g is not None:
            p=(FOLD,init,(ADD,A,g))
            assert prev.consistent(p[2],pairs,ys)
    else:trace=[dict(goal="additive_model",found=False)]
    guard=[]
    if p is not None and mode in ("guarded","lesson_gate"):
        for x in GUARD:
            expected=target(t,(x,));queries+=1
            try:pred=execute(p,(x,))
            except (ValueError,ZeroDivisionError):pred=None
            guard.append([x,expected,pred])
            if pred!=expected:p=None;break
    decision_ns=time.perf_counter_ns()-start
    success,checks=verify_program(p,t,seed)
    return dict(task=t,mode=mode,program=p,success=success,abstained=p is None,queries=queries,work=work,
                trace=trace,guard=guard,sources=used,checks=checks,decision_ns=decision_ns,total_ns=time.perf_counter_ns()-start)


def metric(rows):
    n=len(rows);ok=sum(r["success"] for r in rows);stop=sum(r["abstained"] for r in rows)
    return dict(n=n,correct=ok,abstained=stop,wrong=n-ok-stop,mean_queries=sum(r["queries"] for r in rows)/n,
                mean_decision_ns=sum(r["decision_ns"] for r in rows)/n,residual_correct=sum(r["success"] and any(x["goal"]=="residual" and x["found"] for x in r["trace"]) for r in rows),
                lesson_correct=sum(r["success"] and any(x["kind"]=="offline_lesson" for x in r["sources"]) for r in rows))


def compiler(e):
    # Only numeric ASTs from the fixed DSL. Never accept raw source text.
    if not isinstance(e,tuple):raise ValueError("AST required")
    op=e[0]
    if op in (ACC,ITEM) and len(e)==1:return "a" if op==ACC else "x"
    if op==CONST and len(e)==2 and type(e[1]) is int and abs(e[1])<=100:return str(e[1])
    if op in (ABS,NEG) and len(e)==2:
        z=compiler(e[1]);return f"abs({z})" if op==ABS else f"(-({z}))"
    operators={ADD:"+",SUB:"-",MUL:"*",MOD:"%",GT:">",EQ:"=="}
    if op in operators and len(e)==3:
        v=f"({compiler(e[1])} {operators[op]} {compiler(e[2])})"
        return f"int({v})" if op in (GT,EQ) else v
    raise ValueError("unsupported export opcode")


def export(folder,rows):
    sources=[];checks=[]
    # Export exactly successful emitted guarded programs. Evaluation chooses no new skills.
    for i,r in enumerate(r for r in rows if r["success"] and r["program"] is not None):
        p=h.freeze(r["program"]);name=f"task_{i}"
        if p[0]!=FOLD or p[1]!=0 or h.size(p[2])>120:continue
        try:expr=compiler(p[2])
        except ValueError:continue
        sources.append(f"def {name}(items):\n    a = 0\n    for x in items:\n        a = {expr}\n    return a\n")
        checks.append(dict(name=name,program=p,cases=r["checks"],task_id=r["task"]["id"]))
    (folder/"generated.py").write_text("\n".join(sources),encoding="utf-8")
    (folder/"export_checks.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    return len(checks)


def run(folder,prior,banks):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    snapshots=json.loads(prior.read_bytes());saved=json.loads(banks.read_bytes())
    forbidden=prior_signatures();rows=[];decisions=[];index_cost=[]
    suites={}
    for seed in SEEDS:
        dev,final=make_tasks(seed,forbidden);suites[seed]=(dev,final)
        forbidden.update(signature(t) for t in dev+final)
    db=sqlite3.connect(folder/"planner.sqlite3")
    db.executescript("CREATE TABLE episodes(id INTEGER PRIMARY KEY,payload TEXT); CREATE TABLE decisions(seed INTEGER PRIMARY KEY,payload TEXT);")
    for seed,ps,bs in zip(SEEDS,prev.SEEDS,h.SEEDS):
        dev,final=suites[seed];snap=snapshots[str(ps)]
        primitive,_=h.build_pool("grammar",snap);memory,_=h.build_pool("schema",snap)
        memory=h.add_layer(memory,restore(saved[str(bs)]))
        expert,_=h.build_pool("expert",snap)
        planners={"pair_only":Planner(memory,False),"primitive_plan":Planner(primitive),"memory_plan":Planner(memory),"expert_plan":Planner(expert)}
        base=planners["memory_plan"];tries={}
        reference=[solve(t,base,"guarded",seed+i) for i,t in enumerate(dev)]
        for r in reference:rows.append(dict(seed=seed,phase="development",policy="guarded",**r))
        # The agent requests lessons only after a development failure; choose at most one
        # of two predefined topic packs using development scores, no final labels.
        chosen="none";picked=base;negative=0
        if any(not r["success"] for r in reference):
            for topic in ("shape","predicate"):
                lessons,rejected=lesson_rows(topic);negative+=rejected
                model=Planner(h.add_layer(memory,lessons))
                checks=[solve(t,model,"lesson_gate",seed+i) for i,t in enumerate(dev)]
                for r in checks:rows.append(dict(seed=seed,phase="development",policy=topic,**r))
                losses=sum(a["success"] and not b["success"] for a,b in zip(reference,checks))
                gains=sum(not a["success"] and b["success"] for a,b in zip(reference,checks))
                errors=sum(not b["success"] and not b["abstained"] for b in checks)
                tries[topic]=dict(gains=gains,losses=losses,wrong=errors,accepted_lessons=len(lessons),build_ns=model.build_ns)
                if not losses and gains>0 and errors<=metric(reference)["wrong"] and (chosen=="none" or gains>tries[chosen]["gains"]):
                    chosen=topic;picked=model
        decision=dict(seed=seed,requested=bool(tries),chosen=chosen,trials=tries,rejected_negative_control=negative)
        decisions.append(decision);db.execute("INSERT INTO decisions VALUES(?,?)",(seed,enc(decision)))
        planners.update(guarded=base,lesson_gate=picked)
        for label,p in planners.items():index_cost.append(dict(seed=seed,policy=label,pool=len(p.pool),indexed=len(p.pairs),build_units=p.spent,build_ns=p.build_ns))
        frozen={k:sha(v.pool) for k,v in planners.items()}
        for i,t in enumerate(final):
            for pol in POLICIES:
                r=solve(t,planners[pol],pol,seed*17+i*579)
                rows.append(dict(seed=seed,phase="final",policy=pol,**r))
        assert frozen=={k:sha(v.pool) for k,v in planners.items()}
    for r in rows:db.execute("INSERT INTO episodes(payload) VALUES(?)",(enc(r),))
    db.commit();db.close()
    final=[r for r in rows if r["phase"]=="final"]
    exports=export(folder,[r for r in final if r["policy"]=="lesson_gate"])
    base={(r["seed"],r["task"]["id"]):r for r in final if r["policy"]=="pair_only"}
    agg=[]
    for p in POLICIES:
        rr=[r for r in final if r["policy"]==p]
        m=metric(rr);m["gain_vs_pair"]=sum(r["success"] and not base[r["seed"],r["task"]["id"]]["success"] for r in rr)
        m["loss_vs_pair"]=sum(not r["success"] and base[r["seed"],r["task"]["id"]]["success"] for r in rr)
        agg.append(dict(policy=p,**m))
    result=dict(protocol="NUCLEO_V4-v1",seeds=SEEDS,episodes=len(rows),exports=exports,decisions=decisions,
        aggregate=agg,by_family=[dict(policy=p,family=f,**metric([r for r in final if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in FAMILIES],
        index_cost=index_cost,prior_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),banks_sha256=hashlib.sha256(banks.read_bytes()).hexdigest())
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(enc(r)+"\n")
    print("SUMMARY_V4="+enc(result))


class Tests(unittest.TestCase):
    def test_residual(self):
        e=[(ABS,X),(MUL,X,X),(GT,X,(CONST,3))]
        pool=[dict(expr=x,vec=h.vector(x),source={"kind":"test"}) for x in e]
        p=Planner(pool);goal=plus(plus(pool[0]["vec"],pool[1]["vec"]),pool[2]["vec"])
        r,n,src,trace=p.solve(goal)
        self.assertEqual(h.vector(r),goal);self.assertLessEqual(n,PLAN_CAP)
        self.assertTrue(any(t["goal"]=="residual" for t in trace))
    def test_order(self):
        p=Planner([])
        t=dict(family="order",terms=(("abs",0,1),("gt",0,1)),id="test")
        self.assertTrue(solve(t,p,"guarded",1)["abstained"])
    def test_teacher(self):
        r,n=lesson_rows("predicate");self.assertGreater(len(r),0);self.assertEqual(n,1)
    def test_export(self):
        self.assertEqual(compiler((ADD,A,X)),"(a + x)")
        with self.assertRaises(ValueError):compiler((999,X))
        with self.assertRaises(ValueError):compiler((CONST,"not code"))
    def test_splits(self):
        dev,final=make_tasks(SEEDS[0],prior_signatures())
        self.assertEqual((len(dev),len(final)),(15,50))
        self.assertEqual(len(set(signature(t) for t in dev+final)),65)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);p.add_argument("--banks",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or not a.prior or not a.banks or ROOT not in a.output.resolve().parents:p.error("new output inside V4 and archived snapshots required")
    run(a.output,a.prior,a.banks)
