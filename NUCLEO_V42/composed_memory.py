"""V42: bounded symbolic composition and matched random-memory control."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V41"))
import fork_memory as f
m=f.m
SEEDS=(5700017,5730023,5760031,5790041)
POLICIES=("plain","random","memory")
PAIR_CAP=12000
MOTIFS=tuple(("fork",c,a,b,"") for c,a,b in itertools.product(f.COMB,f.LEAVES,f.LEAVES))
MOTIF_SET=frozenset(MOTIFS)
RELATED=("fourth_power","square_duplicate","mirror_square","repeat_four","pair_product_square","delta_duplicate")
NOVEL=("double_square","mirror_product_duplicate","neg_concat_mirror_product","sorted_neg_mirror","reverse_delta_product","positive_concat_square")
SIMPLE=("span","prefix","square_sum","reverse_concat")
CONTROL=("product_prefix_mod97","repeat_three")
PROTOCOL="V42-composed-memory-v1"

def inputs(seed):
    rng=random.Random(seed);used=set()
    def sample(n,domain,maxlen,balanced=False):
        out=[]
        while len(out)<n:
            k=rng.randint(2,maxlen)
            group=len(out)%3 if balanced else 2
            lo,hi=(1,domain) if group==0 else (-domain,-1) if group==1 else (-domain,domain)
            x=tuple(rng.randint(lo,hi) for _ in range(k))
            if x not in used:used.add(x);out.append(x)
        return tuple(out)
    a=sample(12,4,6,True)
    public=sample(12,5,6,True)
    teach=sample(24,6,7,True)
    held=sample(80,8,8,True)
    return a,public,teach,held

def oracle(name,x):
    # Independent definitions confined to the experimental evaluator.
    if name=="fourth_power":return tuple(z**4 for z in x)
    if name=="square_duplicate":return tuple(z*z for z in x)*2
    if name=="mirror_square":return tuple((u+v)**2 for u,v in zip(x,reversed(x)))
    if name=="repeat_four":return x*4
    if name=="pair_product_square":return tuple((z*(z+1))**2 for z in x)
    if name=="delta_duplicate":return tuple(abs(z)-z for z in x)*2
    if name=="double_square":return tuple(4*z*z for z in x)
    if name=="mirror_product_duplicate":return tuple(u*v for u,v in zip(x,reversed(x)))*2
    if name=="neg_concat_mirror_product":
        y=tuple(-z for z in x)+x
        return tuple(u*v for u,v in zip(y,reversed(y)))
    if name=="sorted_neg_mirror":
        y=tuple(sorted(x))+tuple(-z for z in x)
        return tuple(u+v for u,v in zip(y,reversed(y)))
    if name=="reverse_delta_product":
        return tuple(d*(d+1) for d in (v-u for u,v in zip(x,reversed(x))))
    if name=="positive_concat_square":return tuple(z*z for z in x if z>0)+tuple(z*z for z in reversed(x))
    return f.oracle(name,x)

def eval_pair(pair,x):
    if len(pair)!=2 or any(p not in MOTIF_SET for p in pair):raise ValueError("invalid pair")
    intermediate=f.evaluate(pair[0],x)
    return None if intermediate is None else f.evaluate(pair[1],intermediate)

def pair_order(priority):
    if len(priority)>6 or len(set(priority))!=len(priority) or any(p not in MOTIF_SET for p in priority):
        raise ValueError("invalid priority")
    fast=tuple(itertools.product(priority,repeat=2));skip=set(fast)
    yield from fast
    for pair in itertools.product(MOTIFS,repeat=2):
        if pair not in skip:yield pair

def pair_search(examples,priority,cap=PAIR_CAP):
    if not examples or not 1<=cap<=PAIR_CAP:raise ValueError("budget")
    checks=examined=0;start=time.perf_counter_ns();found=None
    for pair in itertools.islice(pair_order(priority),cap):
        examined+=1
        for x,y in examples:
            checks+=1
            if eval_pair(pair,x)!=y:break
        else:
            found=pair;break
    return found,dict(pair_examined=examined,pair_checks=checks,
                      from_priority=bool(found and examined<=len(priority)**2),
                      pair_wall_ns=time.perf_counter_ns()-start)

def solve(examples,priority):
    # No evaluator labels or held outputs enter either search.
    found,cost=f.search(examples,True,True,(),1)
    stats=dict(single_examined=cost["examined"],single_checks=cost["checks"],
        single_wall_ns=cost["wall_ns"],pair_examined=0,pair_checks=0,pair_wall_ns=0,from_priority=False)
    if found:return ("single",found[0]),stats
    pair,cost=pair_search(examples,priority);stats.update(cost)
    return (("pair",pair) if pair else None),stats

def run_program(program,x):
    return f.evaluate(program[1],x) if program[0]=="single" else eval_pair(program[1],x)

def acquire(seed,public,teach):
    registry,training=f.acquire(seed,"memory",public,teach)
    assert all(p in MOTIF_SET for p in registry)
    return tuple(registry),training

def freeze(path,library):
    body={"library":library};body["sha"]=m.digest(body)
    path.write_text(m.enc(body),encoding="utf-8")
    loaded=json.loads(path.read_text(encoding="utf-8"));sha=loaded.pop("sha")
    if sha!=m.digest(loaded):raise ValueError("hash")
    value=tuple(tuple(p) for p in loaded["library"])
    if tuple(library)!=value or len(value)>6 or len(set(value))!=len(value) or any(p not in MOTIF_SET for p in value):
        raise ValueError("library")
    return value,sha

def metric(rows):
    correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
        **{k:sum(r[k] for r in rows) for k in ("single_examined","single_checks","single_wall_ns","pair_examined","pair_checks","pair_wall_ns","from_priority")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);rows=[];learning=[];snapshots=[]
    for seed in seeds:
        a,b,teach,held=inputs(seed)
        assert len(set((*a,*b,*teach,*held)))==128
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(acquisition=a,public=b,teaching=teach,held=held)),encoding="utf-8")
        registry,training=acquire(seed,a,teach);learning.extend(training)
        random_lib=tuple(random.Random(seed^0x4201).sample(MOTIFS,len(registry)))
        libraries={"plain":(),"random":random_lib,"memory":registry}
        for policy in POLICIES:
            library,sha=freeze(out/f"library_{seed}_{policy}.json",libraries[policy])
            snapshots.append(dict(seed=seed,policy=policy,library=library,sha=sha))
            for stratum,names in (("related",RELATED),("novel",NOVEL),("simple",SIMPLE),("control",CONTROL)):
                for name in names:
                    examples=tuple((x,oracle(name,x)) for x in b)
                    program,cost=solve(examples,library)
                    matched=0;failure=None
                    if program:
                        for x in held:
                            expected=oracle(name,x);actual=run_program(program,x)
                            matched+=expected==actual
                            if expected!=actual and failure is None:failure=dict(input=x,expected=expected,actual=actual)
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,program=program,
                        emitted=program is not None,correct=program is not None and matched==len(held),
                        held_matches=matched,held_tests=len(held) if program else 0,first_failure=failure,**cost))
            if m.digest({"library":library})!=sha:raise RuntimeError("changed memory")
    summary=dict(protocol=PROTOCOL,seeds=seeds,pair_budget=PAIR_CAP,motifs=len(MOTIFS),pair_universe=len(MOTIFS)**2,
        snapshots=snapshots,acquisition=f.metric(learning),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
            for p in POLICIES for s in ("related","novel","simple","control")],
        by_seed=[dict(seed=seed,policy=p,**metric([r for r in rows if r["seed"]==seed and r["policy"]==p])) for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,records in (("acquisition",learning),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,aggregate=summary["aggregate"],by_stratum=summary["by_stratum"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(len(MOTIF_SET),1296)
        square=("fork","mul","","","")
        self.assertEqual(eval_pair((square,square),(-2,3)),(16,81))
        with self.assertRaises(ValueError):eval_pair((square,("shell",)),(1,))
        self.assertEqual(next(pair_order((square,))),(square,square))
        first=list(itertools.islice(pair_order((square,)),PAIR_CAP))
        self.assertEqual(len(first),len(set(first)))
    def test_disjoint(self):
        for seed in SEEDS:
            a,b,t,h=inputs(seed)
            self.assertEqual((len(a),len(b),len(t),len(h)),(12,12,24,80))
            self.assertEqual(len(set((*a,*b,*t,*h))),128)
    def test_budget(self):
        square=("fork","mul","","","")
        e=tuple((x,oracle("fourth_power",x)) for x in ((2,3),(-3,1)))
        p,c=pair_search(e,(square,),1)
        self.assertEqual(p,(square,square));self.assertEqual(c["pair_examined"],1)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==18 for r in s["aggregate"]))
            self.assertTrue(all(r["pair_examined"]<=18*PAIR_CAP for r in s["aggregate"]))
            self.assertEqual(len(s["snapshots"][1]["library"]),len(s["snapshots"][2]["library"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None:p.error("--output required")
    out=a.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V42 required")
    run(out)

if __name__=="__main__":main()
