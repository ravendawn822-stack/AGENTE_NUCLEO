"""V7: bounded synthesis of query-ranking rules, with a separate promotion gate."""
import argparse,ast,hashlib,itertools,json,math,random,sqlite3,sys,time,unittest
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V6_1"))
import contract_repair as previous
v6=previous.v6
SEEDS=(1620011,1650013,1680017)
TRIALS=24
BUDGET=7
FEATURES=("diversity","entropy","expected_elimination","worst_elimination","short_input","small_input")
DIVERSITY=(0,0)
ENTROPY=(0,1)
MINIMAX=(0,3)
POLICIES=("diversity","entropy","minimax","learned","gated")
FINAL_FIXTURES={
"threshold_count":("""def solve(items):
    total = 0
    for x in items:
        if x >= 17:
            total += 2
        if x < -7:
            total += 3
    return total
""",lambda z:sum(2*(x>=17)+3*(x< -7) for x in z)),
"step_cost":("""def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x > previous:
            total += 4
        else:
            total += 1
        previous = x
    return total
""",lambda z:sum(4 if x>p else 1 for p,x in zip((0,*z),z))),
"reserve":("""def solve(items):
    total = 7
    for x in items:
        total -= x
        if total < 2:
            total = 2
        if total > 65:
            total = 65
    return total
""",lambda z:reserve(z)),
"credit":("""def solve(items):
    total = 0
    for x in items:
        if x % 3 == 1:
            total += x + 4
        else:
            total += x - 2
    return total
""",lambda z:sum(x+4 if x%3==1 else x-2 for x in z)),
"mixed_fee":("""def solve(items):
    total = 0
    for x in items:
        if x > 23:
            total += x // 4
        else:
            if x >= 4:
                total += 2
            else:
                total -= 1
    return total
""",lambda z:sum(x//4 if x>23 else 2 if x>=4 else -1 for x in z)),
}
def reserve(z):
    a=7
    for x in z:a=min(65,max(2,a-x))
    return a

def encode(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def fingerprint(x):return hashlib.sha256(encode(x).encode()).hexdigest()

def features(signatures,i,z):
    counts=Counter(s[i] for s in signatures);n=len(signatures)
    p=[k/n for k in counts.values()]
    return (len(p)/n, -sum(q*math.log2(q) for q in p)/math.log2(n) if n>1 else 0,
            1-sum(q*q for q in p),1-max(p),1/(1+len(z)),1/(1+sum(abs(x) for x in z)))

def score(e,f):
    if e[0]==0:return f[e[1]]
    a,b=score(e[1],f),score(e[2],f)
    if e[0]==1:return a+b
    if e[0]==2:return a-b
    if e[0]==3:return a*b
    raise ValueError("unknown rule opcode")

def proposals(seed):
    leaves=[(0,i) for i in range(len(FEATURES))]
    universe=[*leaves]
    for op in (1,2,3):
        for i,a in enumerate(leaves):
            for j,b in enumerate(leaves):
                if i==j or (op!=2 and i>j):continue
                universe.append((op,a,b))
    rng=random.Random(seed);others=[e for e in universe if e not in (DIVERSITY,ENTROPY,MINIMAX)]
    rng.shuffle(others)
    return [DIVERSITY,ENTROPY,MINIMAX,*others[:TRIALS-3]]

def input_pool(src,seed):
    rng=random.Random(seed);tree=v6.safe_tree(src)
    const={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant)}
    vals=sorted({-100,-10,-1,0,1,10,100}|{v+d for v in const for d in (-1,0,1)})
    z=[(),*((v,) for v in vals)]
    z += [(v-1,v,v+1) for v in sorted(const)]
    z += [tuple(rng.choice(vals) for _ in range(rng.randint(2,6))) for _ in range(18)]
    return list(dict.fromkeys(z))

def reserved(seed,pool):
    rng=random.Random(seed)
    zs=[*((v,) for v in range(-35,101)),*(tuple(rng.randint(-130,130) for _ in range(rng.randint(7,15))) for i in range(28))]
    return list(dict.fromkeys(z for z in zs if z not in pool))

def cases(fixtures,seed,phase):
    rng=random.Random(seed);rows=[]
    for name,(src,ref) in fixtures.items():
        original=v6.safe_tree(src);m=list(v6.mutations(original))
        a=rng.choice(m);b=rng.choice([x for x in m if x[0]!=a[0]])
        for kind,edits in (("clean",()),("single",(a,)),("double",(a,b))):
            observed=ast.unparse(v6.patch(original,edits))+"\n"
            pool=input_pool(observed,seed)
            final=reserved(seed+53,pool)
            assert all(v6.safe_eval(original,z)==ref(z) for z in pool+final)
            rows.append(dict(id=f"{seed}/{phase}/{name}/{kind}",source=observed,pool=pool,final=final,ref=ref,kind=kind,fixture=name,mutations=edits))
    return rows

class Environment:
    def __init__(self,case):
        start=time.perf_counter_ns()
        self.case=case;self.pool=case["pool"]
        s=previous.Session(case["source"],self.pool)
        self.candidates=s.candidates;self.generated=s.generated
        self.cache={};self.verdicts={}
        self.build_ns=time.perf_counter_ns()-start
    def observe(self,i):return self.case["ref"](self.pool[i])
    def verify(self,i):
        if i not in self.verdicts:
            tr=self.candidates[i][1]
            self.verdicts[i]=all(v6.safe_eval(tr,z)==self.case["ref"](z) for z in self.case["final"])
        return self.verdicts[i]
    def snapshot(self,remain,unused):
        key=(remain,unused)
        if key not in self.cache:
            sigs=tuple(sorted({self.candidates[i][2] for i in remain}))
            self.cache[key]=tuple((i,features(sigs,i,self.pool[i])) for i in unused)
        return self.cache[key]

def investigate(env,rule):
    start=time.perf_counter_ns()
    remain=tuple(range(len(env.candidates)));unused=tuple(range(len(env.pool)));trace=[];candidate=None
    for step in range(BUDGET+1):
        if not remain:break
        if step and len({env.candidates[i][2] for i in remain})==1:
            candidate=remain[0];break
        if step==BUDGET or not unused:break
        # Same initial probe as V6.1; subsequent choices use the generated score tree.
        i=unused[0] if step==0 else max(env.snapshot(remain,unused),key=lambda k:(score(rule,k[1]),-k[0]))[0]
        y=env.observe(i)
        next_remain=tuple(k for k in remain if env.candidates[k][2][i]==y)
        trace.append(dict(input=env.pool[i],output=y,before=len(remain),after=len(next_remain)))
        remain=next_remain;unused=tuple(k for k in unused if k!=i)
    elapsed=time.perf_counter_ns()-start
    # The environment releases reserved-test outcome only after a decision.
    correct=candidate is not None and env.verify(candidate)
    return dict(id=env.case["id"],family=env.case["kind"],fixture=env.case["fixture"],rule=rule,
        success=correct,emitted=candidate is not None,queries=len(trace),trace=trace,
        edits=env.candidates[candidate][0] if candidate is not None else None,decision_ns=elapsed,build_ns=env.build_ns)

def metric(rows):
    n=len(rows);k=sum(r["success"] for r in rows);e=sum(r["emitted"] for r in rows)
    return dict(n=n,correct=k,wrong=e-k,abstained=n-e,queries=sum(r["queries"] for r in rows),
                mean_queries=sum(r["queries"] for r in rows)/n)
def objective(rows):
    m=metric(rows);return (m["correct"],-m["wrong"],-m["queries"])
def gate(base,new):
    a,b=metric(base),metric(new)
    losses=sum(x["success"] and not y["success"] for x,y in zip(base,new))
    gains=sum(not x["success"] and y["success"] for x,y in zip(base,new))
    accepted=not losses and b["wrong"]<=a["wrong"] and (gains>0 or b["wrong"]<a["wrong"] or b["queries"]<a["queries"])
    return dict(accepted=bool(accepted),losses=losses,gains=gains,base=a,proposal=b)

def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    rows=[];decisions=[];frozen={};suite_log=[]
    db=sqlite3.connect(folder/"learning.sqlite3")
    db.executescript("CREATE TABLE trials(seed INTEGER,trial INTEGER,rule TEXT,metrics TEXT,PRIMARY KEY(seed,trial)); CREATE TABLE choices(seed INTEGER PRIMARY KEY,payload TEXT,sha TEXT);")
    def batch(envs,rule,phase,policy,seed):
        rr=[investigate(e,rule) for e in envs]
        rows.extend(dict(seed=seed,phase=phase,policy=policy,**r) for r in rr)
        return rr
    for seed in SEEDS:
        chosen=DIVERSITY;best=None
        tr=[Environment(c) for c in cases(v6.FIXTURES,seed,"train")]
        for i,rule in enumerate(proposals(seed)):
            rr=batch(tr,rule,"train",f"trial_{i}",seed)
            s=objective(rr)
            db.execute("INSERT INTO trials VALUES(?,?,?,?)",(seed,i,encode(rule),encode(metric(rr))))
            if best is None or s>best:chosen,best=rule,s
        del tr
        gates=[Environment(c) for c in cases(previous.FIXTURES,seed+1,"gate")]
        base=batch(gates,DIVERSITY,"gate","diversity",seed)
        proposed=batch(gates,chosen,"gate","learned",seed)
        g=gate(base,proposed);active=chosen if g["accepted"] else DIVERSITY
        d=dict(seed=seed,learned=chosen,active=active,train_score=best,gate=g)
        decisions.append(d);db.execute("INSERT INTO choices VALUES(?,?,?)",(seed,encode(d),fingerprint(d)));db.commit()
        frozen[seed]=(chosen,active)
    # No final fixture is constructed until all choices have been committed.
    db.close();db=sqlite3.connect(folder/"learning.sqlite3")
    for seed,data,h in db.execute("SELECT seed,payload,sha FROM choices"):
        assert fingerprint(json.loads(data))==h
    db.close()
    for seed in SEEDS:
        learned,active=frozen[seed]
        tests=[Environment(c) for c in cases(FINAL_FIXTURES,seed+2,"final")]
        for env in tests:
            c=env.case
            suite_log.append({k:v for k,v in c.items() if k!="ref"})
        # Same held-out fixtures/pool, compare to strong hand-coded rules.
        for pol,rule in zip(POLICIES,(DIVERSITY,ENTROPY,MINIMAX,learned,active)):
            batch(tests,rule,"final",pol,seed)
    final=[r for r in rows if r["phase"]=="final"]
    base={(r["seed"],r["id"]):r for r in final if r["policy"]=="diversity"}
    agg=[]
    for pol in POLICIES:
        rr=[r for r in final if r["policy"]==pol];m=metric(rr)
        m.update(gains=sum(r["success"] and not base[r["seed"],r["id"]]["success"] for r in rr),
            losses=sum(not r["success"] and base[r["seed"],r["id"]]["success"] for r in rr))
        agg.append(dict(policy=pol,**m))
    result=dict(protocol="V7-score-synthesis-v1",episodes=len(rows),seeds=SEEDS,aggregate=agg,decisions=decisions,features=FEATURES)
    (folder/"summary.json").write_text(json.dumps(result,indent=2))
    (folder/"final_fixtures.json").write_text(json.dumps(suite_log,indent=2))
    with (folder/"raw.jsonl").open("w") as f:
        for r in rows:f.write(encode(r)+"\n")
    print("SUMMARY_V7="+encode(result))

class Tests(unittest.TestCase):
    def test_rules(self):
        ps=proposals(13);self.assertEqual(len(ps),TRIALS);self.assertEqual(len(set(ps)),TRIALS)
        self.assertEqual(score((1,(0,0),(0,1)),[.2,.3]),.5)
    def test_information(self):
        sigs=((0,0),(0,1),(0,2),(1,3))
        self.assertGreater(features(sigs,1,[0])[1],features(sigs,0,[0])[1])
    def test_gate(self):
        a=dict(success=True,emitted=True,queries=3)
        b=dict(success=True,emitted=True,queries=2)
        c=dict(success=False,emitted=True,queries=1)
        self.assertTrue(gate([a],[b])["accepted"]);self.assertFalse(gate([a],[c])["accepted"])
    def test_fixture_oracles(self):
        for src,ref in FINAL_FIXTURES.values():
            t=v6.safe_tree(src);self.assertEqual(v6.evaluate(t,[-8,4,24,50,-3]),ref([-8,4,24,50,-3]))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V7 required")
    run(a.output)
