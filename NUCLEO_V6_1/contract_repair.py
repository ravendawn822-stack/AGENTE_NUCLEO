"""V6.1: read a restricted Python module, request examples, propose a separate patch."""
import argparse,ast,hashlib,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V6"))
import repair as v6
CAP=256
ROUNDS=7
SEEDS=(1530001,1560001,1590001)
POLICIES=("fixed","active")
# New hand-authored logic, different from the eight original V6 templates.
FIXTURES={
"fees":("""def solve(items):
    total = 0
    for x in items:
        if x < 20:
            total += 3
        else:
            if x < 80:
                total += 7
            else:
                total += 12
    return total
""",lambda z:sum(3 if x<20 else 7 if x<80 else 12 for x in z)),
"reversal":("""def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x > 0:
            if previous < 0:
                total += 1
        previous = x
    return total
""",lambda z:sum(p<0 and x>0 for p,x in zip((0,*z),z))),
"bounded_stock":("""def solve(items):
    total = 10
    for x in items:
        total += x
        if total < 0:
            total = 0
        if total > 40:
            total = 40
    return total
""",lambda z:stock(z)),
"weighted_change":("""def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x >= previous:
            total += x - previous
        else:
            total += previous - x
        previous = x
    return total
""",lambda z:sum(abs(x-p) for p,x in zip((0,*z),z))),
"quota":("""def solve(items):
    total = 0
    for x in items:
        if x > 10:
            total += x // 3
        else:
            if x > 0:
                total += 1
    return total
""",lambda z:sum(x//3 if x>10 else int(x>0) for x in z)),
}
def stock(z):
    a=10
    for x in z:a=min(40,max(0,a+x))
    return a

def digest(x):return hashlib.sha256(x).hexdigest()
def checked_examples(samples):
    if not isinstance(samples,list) or len(samples)>100:raise ValueError("example cap")
    out={}
    for r in samples:
        z,y=r["input"],r["output"]
        if not isinstance(z,list) or len(z)>32 or any(type(x)!=int or abs(x)>1000 for x in z) or type(y)!=int:raise ValueError("example schema")
        key=tuple(z)
        if key in out and out[key]!=y:raise ValueError("contradictory examples")
        out[key]=y
    return out

def probes(seed):
    rng=random.Random(seed)
    base=[(),(-1,),(0,),(1,),(9,10,11),(19,20,21),(39,40,41),(79,80,81),(-3,3,-4,4),(100,-110,30,50)]
    domain=(-110,-10,-1,0,1,9,10,11,19,20,21,39,40,41,79,80,81,100)
    base.extend(tuple(rng.choice(domain) for _ in range(rng.randint(2,7))) for i in range(20))
    return list(dict.fromkeys(base))
def reserved(seed,pool):
    rng=random.Random(seed^0xA4C1)
    rows=[*((x,) for x in range(-8,110)),*(tuple(rng.randint(-140,140) for _ in range(rng.randint(8,16))) for i in range(32))]
    return list(dict.fromkeys(z for z in rows if z not in pool))

class Session:
    def __init__(self,src,pool):
        self.src=src;self.tree=v6.safe_tree(src);self.pool=pool;self.candidates=[];self.generated=0
        for edits in itertools.islice(v6.candidate_edits(self.tree,True),CAP):
            self.generated+=1
            t=v6.patch(self.tree,edits)
            sig=tuple(v6.safe_eval(t,z) for z in pool)
            if all(type(v)==int for v in sig):self.candidates.append((edits,t,sig))
    def propose(self,samples,policy):
        data=checked_examples(samples)
        remain=[(e,t,s) for e,t,s in self.candidates if all(v6.safe_eval(t,z)==y for z,y in data.items())]
        if not remain:return dict(status="out_of_model",remaining=0)
        signatures={s for _,_,s in remain}
        available=[i for i,z in enumerate(self.pool) if z not in data]
        if not data:
            return dict(status="needs_example",input=list(self.pool[0]),remaining=len(remain),classes=len(signatures))
        if len(signatures)==1:
            edits,tree,_=remain[0]
            return dict(status="candidate",edits=edits,source=ast.unparse(tree)+"\n",remaining=len(remain),classes=1)
        if not available:return dict(status="ambiguous",remaining=len(remain),classes=len(signatures))
        i=available[0] if policy=="fixed" else max(available,key=lambda k:(len({s[k] for s in signatures}),-k))
        return dict(status="needs_example",input=list(self.pool[i]),remaining=len(remain),classes=len(signatures))

def run(folder):
    folder.mkdir(parents=True,exist_ok=False);files=folder/"fixtures";files.mkdir();rows=[]
    for seed in SEEDS:
        rng=random.Random(seed);pool=probes(seed);final=reserved(seed,pool)
        for name,(src,ref) in FIXTURES.items():
            tree=v6.safe_tree(src)
            assert all(v6.safe_eval(tree,z)==ref(z) for z in pool+final)
            mutations=list(v6.mutations(tree));a=rng.choice(mutations);b=rng.choice([m for m in mutations if m[0]!=a[0]])
            for family,edits in (("clean",()),("single",(a,)),("double",(a,b))):
                uid=f"{seed}_{name}_{family}";path=files/(uid+".py")
                path.write_text(ast.unparse(v6.patch(tree,edits))+"\n",encoding="utf-8")
                original=path.read_bytes()
                start=time.perf_counter_ns();session=Session(path.read_text(encoding="utf-8"),pool);build=time.perf_counter_ns()-start
                for policy in POLICIES:
                    samples=[];trace=[];start=time.perf_counter_ns()
                    for round in range(ROUNDS+1):
                        out=session.propose(samples,policy)
                        trace.append({k:v for k,v in out.items() if k!="source"})
                        if out["status"]!="needs_example":break
                        if round==ROUNDS:out=dict(status="sample_budget");break
                        z=out["input"];samples.append(dict(input=z,output=ref(z)))
                    checks=[];emitted=out["status"]=="candidate"
                    if emitted:
                        candidate=v6.safe_tree(out["source"])
                        checks=[[z,ref(z),v6.safe_eval(candidate,z)] for z in final]
                        (files/(uid+"_"+policy+"_candidate.py")).write_text(out["source"],encoding="utf-8")
                    rows.append(dict(seed=seed,uid=uid,family=family,fixture=name,policy=policy,generated=session.generated,
                        emitted=emitted,success=emitted and all(y==p for _,y,p in checks),checks=checks,samples=samples,trace=trace,
                        decision_ns=time.perf_counter_ns()-start,shared_build_ns=build,result=out,original_sha=digest(original)))
                    assert path.read_bytes()==original
    def stats(rr):
        n=len(rr);ok=sum(r["success"] for r in rr);emitted=sum(r["emitted"] for r in rr)
        return dict(n=n,correct=ok,wrong=emitted-ok,abstained=n-emitted,
                    mean_examples=sum(len(r["samples"]) for r in rr)/n,mean_decision_ns=sum(r["decision_ns"] for r in rr)/n,
                    mean_shared_build_ns=sum(r["shared_build_ns"] for r in rr)/n)
    result=dict(protocol="V6.1-example-repair-v1",episodes=len(rows),
        aggregate=[dict(policy=p,**stats([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**stats([r for r in rows if r["policy"]==p and r["family"]==f])) for p in POLICIES for f in ("clean","single","double")])
    (folder/"summary.json").write_text(json.dumps(result,indent=2))
    with (folder/"raw.jsonl").open("w") as f:
        for row in rows:f.write(json.dumps(row)+"\n")
    print("SUMMARY_REPAIR_CONTRACT="+json.dumps(result,separators=(",",":")))

def cli(source,examples,folder):
    folder.mkdir(parents=True,exist_ok=False)
    src=source.read_bytes()
    if len(src)>16000:raise ValueError("source size")
    samples=json.loads(examples.read_text(encoding="utf-8"))
    out=Session(src.decode("utf-8"),probes(42)).propose(samples,"active")
    (folder/"result.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    if out["status"]=="candidate":(folder/"candidate.py").write_text(out["source"],encoding="utf-8")
    elif out["status"]=="needs_example":(folder/"request.json").write_text(json.dumps(dict(input=out["input"],output=None),indent=2),encoding="utf-8")
    assert source.read_bytes()==src
    print(out["status"])

class Tests(unittest.TestCase):
    def test_reference(self):
        for src,ref in FIXTURES.values():
            tree=v6.safe_tree(src)
            self.assertEqual(v6.evaluate(tree,[-10,100,10,40,-30,2]),ref([-10,100,10,40,-30,2]))
    def test_requests(self):
        src="def solve(items):\n    total = 0\n    for x in items:\n        total -= x\n    return total\n"
        s=Session(src,[(),(1,),(2,3),(-2,),(8,9)])
        self.assertEqual(s.propose([],"active")["status"],"needs_example")
        samples=[]
        for i in range(ROUNDS):
            out=s.propose(samples,"active")
            if out["status"]!="needs_example":break
            z=out["input"];samples.append(dict(input=z,output=sum(z)))
        self.assertEqual(out["status"],"candidate")
        self.assertEqual(v6.evaluate(v6.safe_tree(out["source"]),[9,-2,7]),14)
    def test_contradiction(self):
        with self.assertRaises(ValueError):checked_examples([dict(input=[1],output=2),dict(input=[1],output=3)])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--source",type=Path);p.add_argument("--examples",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V6.1 required")
    if a.source and a.examples:cli(a.source,a.examples,a.output)
    elif a.source or a.examples:p.error("both source and examples required")
    else:run(a.output)
