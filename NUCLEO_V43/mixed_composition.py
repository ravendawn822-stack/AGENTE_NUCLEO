"""V43: search mixed known/unknown compositions within a fixed budget."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V42"))
import composed_memory as c
f,m=c.f,c.m
SEEDS=(5820017,5850023,5880031,5910041)
POLICIES=("plain","learned_pairs","mixed_random","mixed_learned")
CAP=c.PAIR_CAP
GROUPS=(
    ("related",c.RELATED[:4]),
    ("replication",c.NOVEL),
    ("known_first",("square_sorted_concat","mirror_neg_concat","pair_sorted_delta","delta_neg_reverse_concat")),
    ("known_second",("sorted_concat_square","reverse_delta_abs_delta","neg_concat_pair","even_concat_pair")),
    ("both_untrained",("mirror_product_sorted_delta","sorted_concat_mirror_product")),
    ("simple",c.SIMPLE[:2]),
    ("control",c.CONTROL))
PROTOCOL="V43-mixed-composition-v1"

def oracle(name,x):
    if name=="square_sorted_concat":
        y=tuple(z*z for z in x);return y+tuple(sorted(y))
    if name=="mirror_neg_concat":
        y=tuple(u+v for u,v in zip(x,reversed(x)));return y+tuple(-z for z in y)
    if name=="pair_sorted_delta":
        y=tuple(z*(z+1) for z in x);return tuple(u-v for u,v in zip(sorted(y),y))
    if name=="delta_neg_reverse_concat":
        y=tuple(abs(z)-z for z in x);return y+tuple(-z for z in reversed(y))
    if name=="sorted_concat_square":
        return tuple(z*z for z in x+tuple(sorted(x)))
    if name=="reverse_delta_abs_delta":
        return tuple(abs(d)-d for d in (v-u for u,v in zip(x,reversed(x))))
    if name=="neg_concat_pair":
        return tuple(z*(z+1) for z in x+tuple(-z for z in x))
    if name=="even_concat_pair":
        return tuple(z*(z+1) for z in tuple(z for z in x if z%2==0)+x)
    if name=="mirror_product_sorted_delta":
        y=tuple(u*v for u,v in zip(x,reversed(x)));return tuple(u-v for u,v in zip(sorted(y),y))
    if name=="sorted_concat_mirror_product":
        y=x+tuple(sorted(x));return tuple(u*v for u,v in zip(y,reversed(y)))
    return c.oracle(name,x)

def order(library,mixed):
    if len(library)>6 or len(set(library))!=len(library) or any(p not in c.MOTIF_SET for p in library):
        raise ValueError("library")
    known=frozenset(library)
    for p,q in itertools.product(library,repeat=2):yield (p,q),"known_pair"
    if mixed:
        for unknown in c.MOTIFS:
            if unknown in known:continue
            for p in library:
                yield (p,unknown),"mixed_pair"
                yield (unknown,p),"mixed_pair"
    for p,q in itertools.product(c.MOTIFS,repeat=2):
        if (p in known or q in known) if mixed else (p in known and q in known):
            continue
        yield (p,q),"default"

def pair_search(examples,library,mixed,cap=CAP):
    if not examples or not 1<=cap<=CAP:raise ValueError("search constraints")
    examined=checks=0;found=source=None
    start=time.perf_counter_ns()
    for pair,origin in itertools.islice(order(library,mixed),cap):
        examined+=1
        for x,y in examples:
            checks+=1
            if c.eval_pair(pair,x)!=y:break
        else:
            found,source=pair,origin;break
    return found,dict(pair_examined=examined,pair_checks=checks,
                      pair_wall_ns=time.perf_counter_ns()-start,source=source)

def metric(rows):
    correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
        **{k:sum(r[k] for r in rows) for k in ("single_examined","single_checks","single_wall_ns",
                                               "pair_examined","pair_checks","pair_wall_ns")},
        sources={s:sum(r["correct"] and r["source"]==s for r in rows)
                 for s in ("single","known_pair","mixed_pair","default")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[]
    for seed in seeds:
        a,b,teach,held=c.inputs(seed)
        b=b+((),(2,));held=held+((-3,),(0,))
        assert len(set((*a,*b,*teach,*held)))==132
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(acquisition=a,public=b,teaching=teach,held=held)),encoding="utf-8")
        registry,learned=c.acquire(seed,a,teach);training.extend(learned)
        random_lib=tuple(random.Random(seed^0x4301).sample(c.MOTIFS,len(registry)))
        libs={"plain":(),"learned_pairs":registry,"mixed_random":random_lib,"mixed_learned":registry}
        frozen={}
        for policy in POLICIES:
            lib,sha=c.freeze(out/f"library_{seed}_{policy}.json",libs[policy])
            snapshots.append(dict(seed=seed,policy=policy,library=lib,sha=sha));frozen[policy]=(lib,sha)
        for stratum,names in GROUPS:
            for name in names:
                examples=tuple((x,oracle(name,x)) for x in b)
                single,cost=f.search(examples,True,True,(),1)
                for policy in POLICIES:
                    lib,sha=frozen[policy]
                    if single:
                        program=("single",single[0]);stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
                    else:
                        pair,stats=pair_search(examples,lib,policy.startswith("mixed_"))
                        program=("pair",pair) if pair else None
                    matches=0;failure=None
                    if program:
                        for x in held:
                            y=oracle(name,x);actual=c.run_program(program,x)
                            matches+=actual==y
                            if actual!=y and failure is None:failure=dict(input=x,expected=y,actual=actual)
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        program=program,emitted=program is not None,correct=program is not None and matches==len(held),
                        held_matches=matches,held_tests=len(held) if program else 0,first_failure=failure,
                        single_examined=cost["examined"],single_checks=cost["checks"],single_wall_ns=cost["wall_ns"],**stats))
        for lib,sha in frozen.values():
            if m.digest({"library":lib})!=sha:raise RuntimeError("memory changed")
    summary=dict(protocol=PROTOCOL,seeds=seeds,pair_budget=CAP,universe=len(c.MOTIFS)**2,
        single_timing="shared measurement replicated per policy; not independent total runtime",
        snapshots=snapshots,acquisition=f.metric(training),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,policy=p,**metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,records in (("acquisition",training),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,aggregate=summary["aggregate"],by_stratum=summary["by_stratum"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_order(self):
        known=(("fork","mul","","",""),("fork","concat","","",""))
        for mixed in (False,True):
            first=list(itertools.islice(order(known,mixed),CAP))
            self.assertEqual(len(first),CAP)
            self.assertEqual(len({p for p,_ in first}),CAP)
            self.assertEqual(first[0],((known[0],known[0]),"known_pair"))
            if mixed:
                self.assertEqual(first[4][1],"mixed_pair")
                self.assertEqual(first[4][0],tuple(reversed(first[5][0])))
    def test_solver(self):
        square=("fork","mul","","","")
        p,cost=pair_search([((2,3),(16,81)),((-2,4),(16,256))],(square,),True,1)
        self.assertEqual(p,(square,square))
        self.assertEqual(cost["pair_examined"],1)
    def test_tasks(self):
        names=[name for _,group in GROUPS for name in group]
        self.assertEqual(len(names),24)
        self.assertEqual(len(set(names)),24)
        for name in names:
            for x in ((),(2,),(-3,),(2,-1,4)):
                y=oracle(name,x)
                self.assertIsInstance(y,tuple)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            data=run(Path(d)/"case",SEEDS[:1])
            self.assertEqual(len(data["aggregate"]),4)
            self.assertTrue(all(r["n"]==24 and r["pair_examined"]<=24*CAP for r in data["aggregate"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None:p.error("--output required")
    out=a.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V43 required")
    run(out)

if __name__=="__main__":main()
