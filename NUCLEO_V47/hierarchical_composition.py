"""V47: bounded hierarchical composition using empirically verified pairs."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V46"))
import active_acquisition as a
mix,c,f,m=a.mix,a.c,a.f,a.m
SEEDS=(6300017,6330023,6360031,6390041)
POLICIES=("base_only","random_pairs","learned_pairs")
PAIR_TASKS=("fourth_power","square_duplicate","mirror_square","mirror_neg_concat",
            "sorted_concat_square","even_concat_pair")
GROUPS=(
    ("base_composed",("fourth_duplicate","square_duplicate_consecutive","mirror_square_reverse_concat")),
    ("mixed_prefix",("mirror_neg_consecutive","sorted_square_consecutive","even_pair_palindrome")),
    ("mixed_suffix",("square_mirror_neg","mirror_sorted_square","mirror_even_pair")),
    ("untrained",("reverse_delta_sorted_mirror_product","sorted_mirror_sorted_delta")),
    ("simple",("span",)),
    ("pair",("square_duplicate",)),
    ("control",c.CONTROL))
CAP=6000
PROTOCOL="V47-hierarchical-composition-v1"

def oracle(name,x):
    # Definitions remain inside the experimental evaluator, not the search.
    if name=="fourth_duplicate":
        return tuple(z**4 for z in x)*2
    if name=="square_duplicate_consecutive":
        return tuple(z*z*(z*z+1) for z in x)*2
    if name=="mirror_square_reverse_concat":
        y=tuple((u+v)**2 for u,v in zip(x,reversed(x)))
        return y+y[::-1]
    if name=="mirror_neg_consecutive":
        y=tuple(u+v for u,v in zip(x,reversed(x)))
        return tuple(z*(z+1) for z in y+tuple(-z for z in y))
    if name=="sorted_square_consecutive":
        return tuple(z*z*(z*z+1) for z in x+tuple(sorted(x)))
    if name=="even_pair_palindrome":
        y=tuple(z*(z+1) for z in tuple(z for z in x if z%2==0)+x)
        return y+y[::-1]
    if name=="square_mirror_neg":
        y=tuple(u*u+v*v for u,v in zip(x,reversed(x)))
        return y+tuple(-z for z in y)
    if name=="mirror_sorted_square":
        y=tuple(u+v for u,v in zip(x,reversed(x)))
        return tuple(z*z for z in y+tuple(sorted(y)))
    if name=="mirror_even_pair":
        y=tuple(u+v for u,v in zip(x,reversed(x)))
        return tuple(z*(z+1) for z in tuple(z for z in y if z%2==0)+y)
    if name=="reverse_delta_sorted_mirror_product":
        y=tuple(v-u for u,v in zip(x,reversed(x)))
        y=y+tuple(sorted(y))
        return tuple(u*v for u,v in zip(y,reversed(y)))
    if name=="sorted_mirror_sorted_delta":
        y=x+tuple(sorted(x))
        y=tuple(u*v for u,v in zip(y,reversed(y)))
        return tuple(u-v for u,v in zip(sorted(y),y))
    return mix.oracle(name,x)

def inputs(seed):
    initial,pool,challenge,teach,pair_public,reserved=a.inputs(seed)
    pair_teach=reserved[:24]
    all_initial=tuple(y for part in a.cost.a.inputs(seed) for y in part)
    seen=set((*all_initial,*pair_public,*reserved))
    rng=random.Random(seed^0x4701)
    def draw(n,domain,max_len):
        out=[]
        while len(out)<n:
            i=len(out)%3
            lo,hi=(1,domain) if i==0 else (-domain,-1) if i==1 else (-domain,domain)
            x=tuple(rng.randint(lo,hi) for _ in range(rng.randint(1,max_len)))
            if x not in seen:seen.add(x);out.append(x)
        return tuple(out)
    parts=(initial,pool,challenge,teach,pair_public,pair_teach,draw(14,5,6),draw(80,8,8))
    assert len(set(x for part in parts for x in part))==sum(map(len,parts))
    return parts

def acquire_base(seed,initial,pool,challenge,teach):
    rows=[];base=[]
    for i,name in enumerate(f.DIRECT):
        ask=lambda x:f.oracle(name,x)
        examples=tuple((x,ask(x)) for x in initial)
        classes,prep=a.prepare(examples,pool,challenge)
        res=a.cost.investigate(classes,pool,ask,seed+971*i,"active",a.BUDGET)
        verdict=a.validate(res,teach,ask)
        p=verdict["proposal"]
        retained=verdict["accepted"] and p not in base
        if retained:base.append(p)
        rows.append(dict(seed=seed,policy="active",name=name,retained=retained,**res,**verdict,**prep))
    return tuple(base),rows

def valid_pair(p):
    return isinstance(p,tuple) and len(p)==2 and all(v in c.MOTIF_SET for v in p)

def acquire_pairs(seed,base,public,teach):
    pairs=[];rows=[]
    for name in PAIR_TASKS:
        examples=tuple((x,mix.oracle(name,x)) for x in public)
        pair,stats=mix.pair_search(examples,base,bool(base))
        matches=0;failure=None
        if pair is not None:
            if not valid_pair(pair):raise ValueError("invalid acquired pair")
            for x in teach:
                y=mix.oracle(name,x);actual=c.eval_pair(pair,x);matches+=y==actual
                if y!=actual and failure is None:failure=dict(input=x,expected=y,actual=actual)
        accepted=pair is not None and matches==len(teach)
        retained=accepted and pair not in pairs
        if retained:pairs.append(pair)
        rows.append(dict(seed=seed,name=name,pair=pair,accepted=accepted,retained=retained,
            validation_checks=len(teach) if pair is not None else 0,
            validation_matches=matches,validation_failure=failure,**stats))
    return tuple(pairs),rows

def random_pairs(seed,n):
    size=len(c.MOTIFS)
    indices=random.Random(seed^0x4702).sample(range(size*size),n)
    return tuple((c.MOTIFS[i//size],c.MOTIFS[i%size]) for i in indices)

def freeze_pairs(path,pairs):
    pairs=tuple(pairs)
    if len(pairs)>6 or len(set(pairs))!=len(pairs) or not all(valid_pair(p) for p in pairs):
        raise ValueError("pair library bounds")
    body=dict(pairs=pairs);sha=m.digest(body)
    path.write_text(m.enc(dict(body,sha=sha)),encoding="utf-8")
    obj=json.loads(path.read_text(encoding="utf-8"))
    restored=tuple(tuple(tuple(x) for x in pair) for pair in obj["pairs"])
    if obj["sha"]!=sha or m.digest(dict(pairs=restored))!=sha or restored!=pairs:
        raise RuntimeError("pair library integrity")
    return restored,sha

def order(base,pairs):
    if len(base)>6 or len(set(base))!=len(base) or any(p not in c.MOTIF_SET for p in base):
        raise ValueError("base library")
    if len(pairs)>6 or len(set(pairs))!=len(pairs) or not all(valid_pair(p) for p in pairs):
        raise ValueError("pair library")
    seen=set()
    for (p,q),r in itertools.product(pairs,base):
        for triple in ((p,q,r),(r,p,q)):
            if triple not in seen:
                seen.add(triple);yield triple,"pair_memory"
    for triple in itertools.product(base,repeat=3):
        if triple not in seen:
            seen.add(triple);yield triple,"base_triple"
    for triple in itertools.product(c.MOTIFS,repeat=3):
        if triple not in seen:yield triple,"default"

def eval_triple(triple,x):
    if len(triple)!=3 or any(p not in c.MOTIF_SET for p in triple):
        raise ValueError("invalid triple")
    for p in triple:
        x=f.evaluate(p,x)
        if x is None:return None
    return x

def triple_search(examples,base,pairs,limit=CAP):
    if not examples or not 1<=limit<=CAP:raise ValueError("search bounds")
    examined=checks=0;found=source=None
    start=time.perf_counter_ns()
    for triple,origin in itertools.islice(order(base,pairs),limit):
        examined+=1
        for x,y in examples:
            checks+=1
            if eval_triple(triple,x)!=y:break
        else:
            found,source=triple,origin;break
    return found,dict(triple_examined=examined,triple_checks=checks,
        triple_wall_ns=time.perf_counter_ns()-start,source=source)

def evaluate(program,name,held):
    matches=0;failure=None
    if program:
        for x in held:
            y=oracle(name,x)
            actual=eval_triple(program[1],x) if program[0]=="triple" else c.run_program(program,x)
            matches+=actual==y
            if actual!=y and failure is None:failure=dict(input=x,expected=y,actual=actual)
    return dict(program=program,emitted=program is not None,
        correct=program is not None and matches==len(held),
        held_matches=matches,held_tests=len(held) if program else 0,first_failure=failure)

def metric(rows):
    n=len(rows);correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=n,correct=correct,wrong=emitted-correct,abstained=n-emitted,
        **{k:sum(r[k] for r in rows) for k in ("single_examined","single_checks",
             "pair_examined","pair_checks","triple_examined","triple_checks",
             "shared_single_ns","shared_pair_ns","triple_wall_ns")},
        sources={s:sum(r["correct"] and r["source"]==s for r in rows)
                 for s in ("single","pair","pair_memory","base_triple","default")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False)
    base_rows=[];pair_rows=[];rows=[];snapshots=[]
    for seed in seeds:
        parts=inputs(seed)
        initial,pool,ch,teach,pub2,teach2,pub,held=parts
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(zip(
            ("initial","pool","challenge","base_teach","pair_public","pair_teach","final_public","held"),parts))),encoding="utf-8")
        base,base_training=acquire_base(seed,initial,pool,ch,teach)
        base_rows.extend(base_training)
        base,base_sha=c.freeze(out/f"base_{seed}.json",base)
        learned,training=acquire_pairs(seed,base,pub2,teach2);pair_rows.extend(training)
        libraries={"base_only":(),"random_pairs":random_pairs(seed,len(learned)),"learned_pairs":learned}
        frozen={}
        for policy in POLICIES:
            library,sha=freeze_pairs(out/f"pairs_{seed}_{policy}.json",libraries[policy])
            frozen[policy]=(library,sha)
            snapshots.append(dict(seed=seed,policy=policy,base=base,base_sha=base_sha,pairs=library,pair_sha=sha))
        for stratum,names in GROUPS:
            for name in names:
                examples=tuple((x,oracle(name,x)) for x in pub)
                single,prep=f.search(examples,True,True,(),1)
                single_program=("single",single[0]) if single else None
                pair_stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0)
                pair_program=None
                if not single_program:
                    p,pair_stats=mix.pair_search(examples,base,bool(base))
                    if p is not None:pair_program=("pair",p)
                for policy in POLICIES:
                    library,_=frozen[policy]
                    stats=dict(triple_examined=0,triple_checks=0,triple_wall_ns=0,source=None)
                    program=single_program or pair_program
                    if program:stats["source"]=program[0]
                    else:
                        triple,stats=triple_search(examples,base,library)
                        if triple is not None:program=("triple",triple)
                    rows.append(dict(seed=seed,policy=policy,name=name,stratum=stratum,
                        **evaluate(program,name,held),**stats,single_examined=prep["examined"],
                        single_checks=prep["checks"],shared_single_ns=prep["wall_ns"],
                        pair_examined=pair_stats["pair_examined"],pair_checks=pair_stats["pair_checks"],
                        shared_pair_ns=pair_stats["pair_wall_ns"]))
        for library,sha in frozen.values():
            if m.digest(dict(pairs=library))!=sha:raise RuntimeError("pair memory changed")
    summary=dict(protocol=PROTOCOL,seeds=seeds,triple_budget=CAP,universe=len(c.MOTIFS)**3,
        timing="Single and pair stages shared across policies. Acquisition costs reported separately.",
        base_acquisition=a.training_metric(base_rows),
        pair_acquisition=dict(n=len(pair_rows),accepted=sum(r["accepted"] for r in pair_rows),
            retained=sum(r["retained"] for r in pair_rows),
            **{k:sum(r[k] for r in pair_rows) for k in ("pair_examined","pair_checks","validation_checks")}),
        snapshots=snapshots,aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,policy=p,**metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,records in (("base_acquisition",base_rows),("pair_acquisition",pair_rows),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,base_acquisition=summary["base_acquisition"],
        pair_acquisition=summary["pair_acquisition"],aggregate=summary["aggregate"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_tasks_and_inputs(self):
        names=[n for _,group in GROUPS for n in group]
        self.assertEqual(len(names),15);self.assertEqual(len(set(names)),15)
        for seed in SEEDS:
            parts=inputs(seed)
            self.assertEqual(tuple(map(len,parts)),(4,32,24,24,14,24,14,80))
            self.assertEqual(len(set(x for part in parts for x in part)),216)
    def test_order(self):
        p=("fork","mul","","","");q=("fork","concat","","","")
        base=(p,q);pairs=((p,q),)
        result=list(itertools.islice(order(base,pairs),CAP))
        self.assertEqual(len(result),CAP);self.assertEqual(len({x for x,_ in result}),CAP)
        self.assertEqual(result[0],((p,q,p),"pair_memory"))
        self.assertEqual(eval_triple((p,p,q),(2,-3)),(16,81,16,81))
        with self.assertRaises(ValueError):eval_triple((p,p,("shell",)),(1,))
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            summary=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==15 and r["triple_examined"]<=15*CAP for r in summary["aggregate"]))
            self.assertEqual(len(summary["snapshots"]),3)
            self.assertEqual(len(summary["snapshots"][1]["pairs"]),len(summary["snapshots"][2]["pairs"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V47 required")
    run(out)

if __name__=="__main__":main()
