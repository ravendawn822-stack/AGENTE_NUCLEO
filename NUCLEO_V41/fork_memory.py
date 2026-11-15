"""V41: bounded fork expressions, independent evaluation and memory ordering."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V33"))
import teaching_protocol as q
t,m=q.t,q.m
OPS=tuple(q.OPS)
LEAVES=("",*OPS)
COMB=("add","concat","mul","sub")
SEEDS=(5580017,5610023,5640031,5670041)
POLICIES=("seq","expanded","memory")
DIRECT=("square","duplicate","pair_product","mirror_sum","abs_delta","reverse_concat")
TRANSFER=("square_sum","square_even","duplicate_sort","duplicate_count",
          "mirror_positive","pair_sum","delta_sum","reverse_concat_difference")
LEGACY=("span","prefix","minimum")
OUTSIDE=("product_prefix_mod97","repeat_three")
PROTOCOL="V41-fork-memory-v1"
SEQ_CAP=sum(len(OPS)**n for n in range(4))
ACQ_CAP=SEQ_CAP+len(COMB)*len(LEAVES)**2
FINAL_CAP=SEQ_CAP+len(COMB)*len(LEAVES)**3

def valid(p):
    if not isinstance(p,tuple) or not p:return False
    if p[0]=="pipe":
        return len(p)==2 and isinstance(p[1],tuple) and len(p[1])<=3 and all(z in OPS for z in p[1])
    if p[0]=="fork":
        return len(p)==5 and p[1] in COMB and all(z in LEAVES for z in p[2:])
    return False

def unary(op,x):
    return t.module((op,),x) if op else x

def evaluate(p,x):
    # All expressions are generated from a fixed finite grammar. No host operations.
    if not valid(p):raise ValueError("invalid expression")
    if len(x)>32 or any(type(z)!=int or abs(z)>100000 for z in x):raise ValueError("input bounds")
    if p[0]=="pipe":
        y=t.module(p[1],x) if p[1] else x
    else:
        _,comb,left,right,post=p
        a,b=unary(left,x),unary(right,x)
        if comb=="concat":y=a+b
        elif len(a)!=len(b):return None
        elif comb=="add":y=tuple(u+v for u,v in zip(a,b))
        elif comb=="sub":y=tuple(u-v for u,v in zip(a,b))
        else:y=tuple(u*v for u,v in zip(a,b))
        if len(y)>32 or any(abs(z)>100000 for z in y):return None
        y=unary(post,y)
    if len(y)>32 or any(abs(z)>100000 for z in y):return None
    return y

def grammar(expanded,post):
    for n in range(4):
        for seq in itertools.product(OPS,repeat=n):yield ("pipe",seq)
    if expanded:
        for comb,left,right,after in itertools.product(COMB,LEAVES,LEAVES,LEAVES if post else ("",)):
            yield ("fork",comb,left,right,after)

def memory_candidates(registry):
    # Reordering only: every returned expression is already in the final grammar.
    seen=set()
    for p in registry:
        if not valid(p) or p[0]!="fork" or p[4]!="":raise ValueError("registry expression")
        for post in LEAVES:
            candidate=(*p[:4],post)
            if candidate not in seen:
                seen.add(candidate);yield candidate

def search(examples,expanded,post,registry=(),limit=4):
    if not examples or limit not in (1,4):raise ValueError("search bounds")
    if registry and (not expanded or not post):raise ValueError("memory only in expanded final")
    priority=tuple(memory_candidates(registry));priority_set=set(priority)
    candidates=itertools.chain(priority,(p for p in grammar(expanded,post) if p not in priority_set))
    examined=checks=0;found=[];status="exhausted"
    start=time.perf_counter_ns()
    cap=SEQ_CAP if not expanded else FINAL_CAP if post else ACQ_CAP
    for p in candidates:
        examined+=1
        if examined>cap:raise RuntimeError("grammar budget exceeded")
        for x,y in examples:
            checks+=1
            if evaluate(p,x)!=y:break
        else:
            found.append(p)
            if len(found)==limit:status="proposal_cap";break
    return found,dict(examined=examined,checks=checks,status=status,wall_ns=time.perf_counter_ns()-start,
                      priority_examined=min(examined,len(priority)),priority_size=len(priority),
                      first_from_memory=bool(found and found[0] in priority_set))

def oracle(name,x):
    # Evaluator-only behavior definitions; search receives no name or source.
    if name=="square":return tuple(z*z for z in x)
    if name=="duplicate":return x+x
    if name=="pair_product":return tuple(z*(z+1) for z in x)
    if name=="mirror_sum":return tuple(x[i]+x[-1-i] for i in range(len(x)))
    if name=="abs_delta":return tuple(abs(z)-z for z in x)
    if name=="reverse_concat":return x+x[::-1]
    if name=="square_sum":return (sum(z*z for z in x),)
    if name=="square_even":return tuple(z*z for z in x if z%2==0)
    if name=="duplicate_sort":return tuple(sorted(list(x)*2))
    if name=="duplicate_count":return (2*len(x),)
    if name=="mirror_positive":return tuple(z for z in (x[i]+x[-1-i] for i in range(len(x))) if z>0)
    if name=="pair_sum":return (sum(z*z+z for z in x),)
    if name=="delta_sum":return (sum(abs(z)-z for z in x),)
    if name=="reverse_concat_difference":
        y=(*x,*reversed(x));return tuple(y[i+1]-y[i] for i in range(len(y)-1))
    if name in LEGACY:return t.oracle(name,x)
    if name=="product_prefix_mod97":
        y=[];p=1
        for z in x:p=(p*z)%97;y.append(p)
        return tuple(y)
    if name=="repeat_three":return x*3
    raise ValueError("unknown evaluator behavior")

def inputs(seed):
    rng=random.Random(seed)
    a=[(),(0,),(3,),(2,4,1),(-3,-1,-2),(2,-2,0,2)]
    f=[(1,),(-2,),(5,3,2),(-4,-4,-1),(0,0,0),(3,-1,3,-2)]
    seen=set(a+f)
    def draw(n,domain,max_len):
        out=[]
        while len(out)<n:
            x=tuple(rng.randint(-domain,domain) for _ in range(rng.randint(1,max_len)))
            if x not in seen:seen.add(x);out.append(x)
        return out
    a+=draw(6,4,6);f+=draw(6,4,6)
    teach=draw(24,6,7);held=draw(80,12,8)
    assert len(seen)==12+12+24+80
    return tuple(a),tuple(f),tuple(teach),tuple(held)

def verify(programs,examples,points,ask):
    desired=[ask(x) for x in points];selected=None;trace=[]
    for p in programs:
        public=sum(evaluate(p,x)==y for x,y in examples)
        matches=sum(evaluate(p,x)==y for x,y in zip(points,desired))
        take=selected is None and public==len(examples) and matches==len(points)
        if take:selected=p
        trace.append(dict(program=p,public_matches=public,public_tests=len(examples),
                          matches=matches,tests=len(points),accepted=take))
    return selected,trace

def freeze(path,registry):
    body=dict(registry=registry);body["sha"]=m.digest(body)
    path.write_text(m.enc(body),encoding="utf-8")
    restored=json.loads(path.read_text(encoding="utf-8"));sha=restored.pop("sha")
    if m.digest(restored)!=sha:raise ValueError("registry hash")
    frozen=tuple(tuple(p) for p in restored["registry"])
    if len(frozen)>6 or any(not valid(p) or p[0]!="fork" or p[4] for p in frozen):
        raise ValueError("registry bounds")
    if frozen!=tuple(registry):raise ValueError("registry differs")
    return frozen,sha

def acquire(seed,policy,public,teach):
    registry=[];rows=[]
    for name in DIRECT:
        ask=lambda x:oracle(name,x)
        examples=tuple((x,ask(x)) for x in public)
        found,cost=search(examples,policy!="seq",False)
        selected,trace=verify(found,examples,teach,ask)
        retained=bool(policy=="memory" and selected and selected[0]=="fork" and selected not in registry)
        if retained:registry.append(selected)
        rows.append(dict(seed=seed,policy=policy,name=name,selected=selected,retained=retained,
            correct=selected is not None,emitted=selected is not None,validation=trace,
            teaching_observations=len(teach),teaching_checks=sum(z["tests"] for z in trace),
            **cost))
    return registry,rows

def final(seed,policy,public,held,registry):
    rows=[];before=m.digest(registry)
    for stratum,names in (("direct",DIRECT),("transfer",TRANSFER),("legacy",LEGACY),("control",OUTSIDE)):
        for name in names:
            ask=lambda x:oracle(name,x)
            examples=tuple((x,ask(x)) for x in public)
            found,cost=search(examples,policy!="seq",True,registry if policy=="memory" else (),1)
            p=found[0] if found else None
            result=[]
            if p is not None:
                for x in held:
                    y=ask(x);actual=evaluate(p,x)
                    result.append(dict(input=x,expected=y,actual=actual,matches=y==actual))
            matched=sum(z["matches"] for z in result)
            rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,program=p,
                emitted=p is not None,correct=p is not None and matched==len(held),
                held_matches=matched,held_tests=len(result),
                first_failure=next((z for z in result if not z["matches"]),None),
                **cost))
    if m.digest(registry)!=before:raise RuntimeError("final updated memory")
    return rows

def metric(rows):
    correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
                **{k:sum(r.get(k,0) for r in rows) for k in (
                    "examined","checks","wall_ns","priority_examined","first_from_memory",
                    "teaching_observations","teaching_checks","retained")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);learning=[];rows=[];snapshots=[]
    for seed in seeds:
        a,f,teach,held=inputs(seed)
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(acquisition=a,final=f,teaching=teach,held=held)),encoding="utf-8")
        for policy in POLICIES:
            registry,training=acquire(seed,policy,a,teach)
            frozen,sha=freeze(out/f"skills_{seed}_{policy}.json",registry)
            snapshots.append(dict(seed=seed,policy=policy,registry=frozen,sha=sha))
            learning.extend(training);rows.extend(final(seed,policy,f,held,frozen))
    data=dict(protocol=PROTOCOL,seeds=seeds,budgets=dict(sequential=SEQ_CAP,acquisition=ACQ_CAP,final=FINAL_CAP),
        snapshots=snapshots,acquisition=[dict(policy=p,**metric([r for r in learning if r["policy"]==p])) for p in POLICIES],
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s in ("direct","transfer","legacy","control")],
        by_seed=[dict(seed=seed,policy=p,**metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    for name,records in (("acquisition",learning),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,acquisition=data["acquisition"],aggregate=data["aggregate"],by_stratum=data["by_stratum"]),indent=2))
    return data

class Tests(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual((SEQ_CAP,ACQ_CAP,FINAL_CAP),(5220,6516,28548))
        self.assertEqual(len(set(grammar(True,True))),FINAL_CAP)
        p=("fork","mul","","","")
        self.assertEqual(evaluate(p,(-2,0,3)),(4,0,9))
        self.assertEqual(evaluate(("fork","concat","","",""),(1,2)),(1,2,1,2))
        self.assertIsNone(evaluate(("fork","add","drop1","",""),(1,2)))
        with self.assertRaises(ValueError):evaluate(("pipe",("shell",)),(1,))
    def test_search(self):
        a,_,teach,_=inputs(SEEDS[0])
        examples=tuple((x,oracle("square",x)) for x in a)
        found,cost=search(examples,True,False)
        p,trace=verify(found,examples,teach,lambda x:oracle("square",x))
        self.assertIsNotNone(p);self.assertEqual(p[0],"fork")
        self.assertLessEqual(cost["examined"],ACQ_CAP)
        self.assertTrue(set(memory_candidates((p,)))<=set(grammar(True,True)))
    def test_disjoint(self):
        for seed in SEEDS:
            a,f,teach,held=inputs(seed)
            self.assertEqual((len(a),len(f),len(teach),len(held)),(12,12,24,80))
            self.assertEqual(len(set((*a,*f,*teach,*held))),128)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            data=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==19 for r in data["aggregate"]))
            self.assertTrue(all(r["n"]==6 for r in data["acquisition"]))
            self.assertEqual(sum(s["policy"]!="memory" and bool(s["registry"]) for s in data["snapshots"]),0)

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--output",type=Path);args=parser.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:parser.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:parser.error("new output directory inside NUCLEO_V41 required")
    run(out)

if __name__=="__main__":main()
