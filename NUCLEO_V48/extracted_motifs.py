"""V48: extract reusable search motifs from verified mathematical compositions."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V47"))
import hierarchical_composition as h
mix,c,f,m=h.mix,h.c,h.f,h.m
SEEDS=(6420017,6450023,6480031,6510041)
POLICIES=("base","random_extra","extracted")
GROUPS=(
    ("exposed",("sorted_concat_mirror_product","even_concat_mirror_product",
        "neg_concat_sorted_delta","sorted_concat_neg_concat","even_concat_sorted_concat",
        "neg_concat_mirror_product")),
    ("unexposed",("reverse_delta_mirror_product","mirror_product_sorted_delta")),
    ("anchor",("fourth_power","mirror_square","mirror_neg_concat","neg_concat_pair")),
    ("simple",("span","prefix")),
    ("control",c.CONTROL))
CAP=12000
PROTOCOL="V48-extracted-motifs-v1"

def oracle(name,x):
    # Evaluator only: search receives input/output examples.
    if name=="even_concat_mirror_product":
        y=tuple(z for z in x if z%2==0)+x
        return tuple(u*v for u,v in zip(y,reversed(y)))
    if name=="neg_concat_sorted_delta":
        y=x+tuple(-z for z in x)
        return tuple(u-v for u,v in zip(sorted(y),y))
    if name=="sorted_concat_neg_concat":
        y=x+tuple(sorted(x));return y+tuple(-z for z in y)
    if name=="even_concat_sorted_concat":
        y=tuple(z for z in x if z%2==0)+x
        return y+tuple(sorted(y))
    if name=="reverse_delta_mirror_product":
        y=tuple(v-u for u,v in zip(x,reversed(x)))
        return tuple(u*v for u,v in zip(y,reversed(y)))
    return mix.oracle(name,x)

def extract(base,pairs):
    """Syntactic components of verified pairs, NOT verified as standalone targets."""
    if len(base)>6 or len(pairs)>6 or not all(h.valid_pair(p) for p in pairs):
        raise ValueError("acquisition bounds")
    result={}
    for pair in pairs:
        for p in pair:
            if p not in base:
                result.setdefault(p,[]).append(m.digest(pair))
    if len(result)>12:raise RuntimeError("extension bound")
    return tuple(result),[dict(motif=p,source_pair_hashes=sorted(set(ids)),
        individually_verified=False) for p,ids in result.items()]

def freeze(path,library):
    lib=tuple(library)
    if len(lib)>18 or len(set(lib))!=len(lib) or any(p not in c.MOTIF_SET for p in lib):
        raise ValueError("invalid library")
    body=dict(library=lib);sha=m.digest(body)
    path.write_text(m.enc(dict(body,sha=sha)),encoding="utf-8")
    loaded=json.loads(path.read_text(encoding="utf-8"))
    restored=tuple(tuple(x) for x in loaded["library"])
    if restored!=lib or loaded["sha"]!=sha or m.digest(dict(library=restored))!=sha:
        raise RuntimeError("library integrity")
    return restored,sha

def order(lib):
    if len(lib)>18 or len(set(lib))!=len(lib) or any(p not in c.MOTIF_SET for p in lib):
        raise ValueError("library bounds")
    known=frozenset(lib)
    for pair in itertools.product(lib,repeat=2):yield pair,"priority_pair"
    for unknown in c.MOTIFS:
        if unknown in known:continue
        for p in lib:
            yield (p,unknown),"mixed_pair"
            yield (unknown,p),"mixed_pair"
    for p,q in itertools.product(c.MOTIFS,repeat=2):
        if p not in known and q not in known:yield (p,q),"default"

def pair_search(examples,lib,cap=CAP):
    if not examples or not 1<=cap<=CAP:raise ValueError("budget")
    start=time.perf_counter_ns();examined=checks=0;found=source=None
    for pair,origin in itertools.islice(order(lib),cap):
        examined+=1
        for x,y in examples:
            checks+=1
            if c.eval_pair(pair,x)!=y:break
        else:
            found,source=pair,origin;break
    return found,dict(pair_examined=examined,pair_checks=checks,
        pair_wall_ns=time.perf_counter_ns()-start,source=source)

def score(program,name,held):
    matches=0;failure=None
    if program:
        for x in held:
            y=oracle(name,x);actual=c.run_program(program,x);matches+=y==actual
            if y!=actual and failure is None:failure=dict(input=x,expected=y,actual=actual)
    return dict(program=program,emitted=program is not None,
        correct=program is not None and matches==len(held),
        held_matches=matches,held_tests=len(held) if program else 0,first_failure=failure)

def metric(rows):
    correct=sum(r["correct"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),correct=correct,wrong=emitted-correct,abstained=len(rows)-emitted,
        **{k:sum(r[k] for r in rows) for k in ("single_examined","single_checks",
            "shared_single_ns","pair_examined","pair_checks","pair_wall_ns","extension_used")},
        sources={s:sum(r["correct"] and r["source"]==s for r in rows)
                 for s in ("single","priority_pair","mixed_pair","default")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];base_rows=[];pair_rows=[];snapshots=[]
    for seed in seeds:
        parts=h.inputs(seed)
        initial,pool,ch,teach,pub2,teach2,pub,held=parts
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(zip(
            ("initial","pool","challenge","base_teach","pair_public","pair_teach","final_public","held"),parts))),encoding="utf-8")
        base,learned=h.acquire_base(seed,initial,pool,ch,teach);base_rows.extend(learned)
        base,base_sha=c.freeze(out/f"base_{seed}.json",base)
        pairs,learned=h.acquire_pairs(seed,base,pub2,teach2);pair_rows.extend(learned)
        pairs,pair_sha=h.freeze_pairs(out/f"pairs_{seed}.json",pairs)
        ext,provenance=extract(base,pairs)
        random_ext=tuple(random.Random(seed^0x4802).sample([p for p in c.MOTIFS if p not in base],len(ext)))
        libraries={"base":base,"random_extra":base+random_ext,"extracted":base+ext}
        frozen={}
        for policy in POLICIES:
            lib,sha=freeze(out/f"library_{seed}_{policy}.json",libraries[policy])
            frozen[policy]=(lib,sha)
            snapshots.append(dict(seed=seed,policy=policy,base_sha=base_sha,pair_sha=pair_sha,
                library=lib,library_sha=sha,extra_count=len(lib)-len(base),
                provenance=provenance if policy=="extracted" else []))
        for stratum,names in GROUPS:
            for name in names:
                examples=tuple((x,oracle(name,x)) for x in pub)
                single,prep=f.search(examples,True,True,(),1)
                for policy in POLICIES:
                    library,_=frozen[policy]
                    if single:
                        program=("single",single[0])
                        stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
                    else:
                        pair,stats=pair_search(examples,library)
                        program=("pair",pair) if pair else None
                    extension=set(library)-set(base)
                    use=bool(program and program[0]=="pair" and any(x in extension for x in program[1]))
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        extension_used=use,**score(program,name,held),**stats,
                        single_examined=prep["examined"],single_checks=prep["checks"],
                        shared_single_ns=prep["wall_ns"]))
        for lib,sha in frozen.values():
            if m.digest(dict(library=lib))!=sha:raise RuntimeError("memory changed")
    data=dict(protocol=PROTOCOL,seeds=seeds,pair_budget=CAP,
        timing="Single-stage preparation shared; pair timings measured separately.",
        base_acquisition=h.a.training_metric(base_rows),
        pair_acquisition=dict(n=len(pair_rows),accepted=sum(r["accepted"] for r in pair_rows),
            retained=sum(r["retained"] for r in pair_rows),
            **{k:sum(r[k] for r in pair_rows) for k in ("pair_examined","pair_checks","validation_checks")}),
        snapshots=snapshots,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,policy=p,**metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    for name,records in (("base_acquisition",base_rows),("pair_acquisition",pair_rows),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,aggregate=data["aggregate"],by_stratum=data["by_stratum"]),indent=2))
    return data

class Tests(unittest.TestCase):
    def test_extraction(self):
        p=("fork","mul","","","");q=("fork","concat","","sort","")
        ext,prov=extract((p,),((q,p),(p,q)))
        self.assertEqual(ext,(q,))
        self.assertFalse(prov[0]["individually_verified"])
        self.assertEqual(len(prov[0]["source_pair_hashes"]),2)
    def test_order(self):
        p=("fork","mul","","","");q=("fork","concat","","sort","")
        candidates=list(itertools.islice(order((p,q)),CAP))
        self.assertEqual(len(candidates),CAP)
        self.assertEqual(len({x for x,_ in candidates}),CAP)
        self.assertEqual(candidates[0],((p,p),"priority_pair"))
        self.assertEqual(candidates[4][0],tuple(reversed(candidates[5][0])))
    def test_targets(self):
        names=[name for _,names in GROUPS for name in names]
        self.assertEqual(len(names),16);self.assertEqual(len(set(names)),16)
        for name in names:
            for x in ((),(-3,),(2,-3,0,1)):
                self.assertIsInstance(oracle(name,x),tuple)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            data=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==16 and r["pair_examined"]<=16*CAP for r in data["aggregate"]))
            self.assertEqual(data["snapshots"][1]["extra_count"],data["snapshots"][2]["extra_count"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V48 required")
    run(out)

if __name__=="__main__":main()
