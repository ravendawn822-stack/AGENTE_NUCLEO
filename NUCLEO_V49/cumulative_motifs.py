"""V49: verified incremental motif reuse in a fixed curriculum."""
import argparse,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V48"))
import extracted_motifs as e
h,c,f,m=e.h,e.c,e.f,e.m
SEEDS=(6540017,6570023,6600031,6630041)
POLICIES=("frozen","delayed","cumulative","random_growth")
CURRICULUM=(*h.PAIR_TASKS,*e.GROUPS[0][1],*e.GROUPS[1][1])
GROUPS=(("new",("mirror_product_neg_concat","sorted_delta_duplicate",
    "even_concat_sorted_delta","reverse_delta_neg_concat",
    "mirror_product_even_concat","sorted_delta_mirror_product",
    "reverse_delta_sorted_concat","negative_concat_reverse_delta")),
    ("anchor",("fourth_power","sorted_concat_mirror_product")),
    ("simple",("span","prefix")),("control",c.CONTROL))
PROTOCOL="V49-cumulative-motifs-v1"
LIB_CAP=18

def oracle(name,x):
    if name=="mirror_product_neg_concat":
        y=tuple(u*v for u,v in zip(x,reversed(x)))
        return y+tuple(-z for z in y)
    if name=="sorted_delta_duplicate":
        y=tuple(u-v for u,v in zip(sorted(x),x))
        return y+y
    if name=="even_concat_sorted_delta":
        y=tuple(z for z in x if z%2==0)+x
        return tuple(u-v for u,v in zip(sorted(y),y))
    if name=="reverse_delta_neg_concat":
        y=tuple(v-u for u,v in zip(x,reversed(x)))
        return y+tuple(-z for z in y)
    if name=="mirror_product_even_concat":
        y=tuple(u*v for u,v in zip(x,reversed(x)))
        return tuple(z for z in y if z%2==0)+y
    if name=="sorted_delta_mirror_product":
        y=tuple(u-v for u,v in zip(sorted(x),x))
        return tuple(u*v for u,v in zip(y,reversed(y)))
    if name=="reverse_delta_sorted_concat":
        y=tuple(v-u for u,v in zip(x,reversed(x)))
        return y+tuple(sorted(y))
    if name=="negative_concat_reverse_delta":
        y=x+tuple(-z for z in x)
        return tuple(v-u for u,v in zip(y,reversed(y)))
    return e.oracle(name,x)

def extend(lib,pair,accepted):
    if len(lib)>LIB_CAP or any(p not in c.MOTIF_SET for p in lib) or len(set(lib))!=len(lib):
        raise ValueError("library bounds")
    if not accepted:return lib,()
    if not h.valid_pair(pair):raise ValueError("verified pair expected")
    added=[]
    for p in pair:
        if p not in lib and p not in added and len(lib)+len(added)<LIB_CAP:
            added.append(p)
    return lib+tuple(added),tuple(added)

def trial(name,lib,public,teach):
    examples=tuple((x,e.oracle(name,x)) for x in public)
    pair,stats=e.pair_search(examples,lib)
    matches=0;failure=None
    if pair:
        for x in teach:
            y=e.oracle(name,x);actual=c.eval_pair(pair,x)
            matches+=y==actual
            if y!=actual and failure is None:failure=dict(input=x,expected=y,actual=actual)
    accepted=pair is not None and matches==len(teach)
    return dict(name=name,pair=pair,accepted=accepted,emitted=pair is not None,
        validation_matches=matches,validation_checks=len(teach) if pair else 0,
        observations=len(public),validation_failure=failure,**stats)

def train(seed,base,public,teach,policy,schedule=None):
    if policy not in ("frozen","cumulative","random_growth"):raise ValueError("training policy")
    if policy=="random_growth" and (schedule is None or len(schedule)!=len(CURRICULUM)):
        raise ValueError("size schedule")
    lib=base;rows=[];sizes=[];prov=[]
    shuffled=[p for p in c.MOTIFS if p not in base]
    random.Random(seed^0x4901).shuffle(shuffled)
    for i,name in enumerate(CURRICULUM):
        before=lib
        row=trial(name,lib,public,teach)
        added=()
        if policy=="cumulative":
            lib,added=extend(lib,row["pair"],row["accepted"])
        elif policy=="random_growth":
            size=schedule[i]
            if not len(lib)<=size<=LIB_CAP:raise RuntimeError("invalid size schedule")
            lib=base+tuple(shuffled[:size-len(base)])
            added=lib[len(before):]
        if added:
            prov.extend(dict(index=i,motif=p,individually_verified=False,
                source_pair_hash=m.digest(row["pair"]) if policy=="cumulative" else None)
                for p in added)
        rows.append(dict(seed=seed,index=i,policy=policy,before_size=len(before),
            after_size=len(lib),before_sha=m.digest(before),after_sha=m.digest(lib),
            added=added,**row))
        sizes.append(len(lib))
    return lib,rows,tuple(sizes),prov

def delayed_library(base,rows):
    lib=base;prov=[]
    for row in rows:
        lib,added=extend(lib,row["pair"],row["accepted"])
        prov.extend(dict(index=row["index"],motif=p,individually_verified=False,
            source_pair_hash=m.digest(row["pair"])) for p in added)
    return lib,prov

def score(program,name,held):
    matches=0;failure=None
    if program:
        for x in held:
            expected=oracle(name,x);actual=c.run_program(program,x)
            matches+=expected==actual
            if expected!=actual and failure is None:failure=dict(input=x,expected=expected,actual=actual)
    return dict(program=program,emitted=program is not None,
        correct=program is not None and matches==len(held),
        held_matches=matches,held_tests=len(held) if program else 0,first_failure=failure)

def training_metric(rows):
    accepted=sum(r["accepted"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=len(rows),accepted=accepted,rejected=emitted-accepted,
        abstained=len(rows)-emitted,
        acquired_motifs=sum(len(r["added"]) for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("pair_examined","pair_checks","pair_wall_ns",
            "observations","validation_checks")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];training=[];base_rows=[];snapshots=[]
    for seed in seeds:
        parts=h.inputs(seed)
        initial,pool,ch,teach,public2,teach2,public,held=parts
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(zip(
            ("initial","pool","challenge","base_teach","curriculum_public","curriculum_teach","final_public","held"),parts))),encoding="utf-8")
        base,base_training=h.acquire_base(seed,initial,pool,ch,teach)
        base_rows.extend(base_training)
        base,base_sha=c.freeze(out/f"base_{seed}.json",base)
        cumulative,ct,sizes,cp=train(seed,base,public2,teach2,"cumulative")
        frozen,ft,_,_=train(seed,base,public2,teach2,"frozen")
        delayed,dp=delayed_library(base,ft)
        random_lib,rt,random_sizes,rp=train(seed,base,public2,teach2,"random_growth",sizes)
        assert random_sizes==sizes and frozen==base
        training.extend(ct+ft+rt)
        training.extend(dict(row,policy="delayed",shared_with="frozen") for row in ft)
        libraries={"frozen":(frozen,[]),"delayed":(delayed,dp),
                   "cumulative":(cumulative,cp),"random_growth":(random_lib,rp)}
        saved={}
        for policy in POLICIES:
            lib,prov=libraries[policy]
            lib,sha=e.freeze(out/f"library_{seed}_{policy}.json",lib)
            saved[policy]=(lib,sha)
            snapshots.append(dict(seed=seed,policy=policy,base_sha=base_sha,library=lib,
                library_sha=sha,extra_count=len(lib)-len(base),provenance=prov))
        for stratum,names in GROUPS:
            for name in names:
                examples=tuple((x,oracle(name,x)) for x in public)
                single,prep=f.search(examples,True,True,(),1)
                for policy in POLICIES:
                    lib,_=saved[policy]
                    if single:
                        program=("single",single[0])
                        stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
                    else:
                        pair,stats=e.pair_search(examples,lib)
                        program=("pair",pair) if pair else None
                    use=bool(program and program[0]=="pair" and any(p not in base and p in lib for p in program[1]))
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        **score(program,name,held),**stats,extension_used=use,
                        single_examined=prep["examined"],single_checks=prep["checks"],
                        shared_single_ns=prep["wall_ns"]))
        for lib,sha in saved.values():
            if m.digest(dict(library=lib))!=sha:raise RuntimeError("memory changed")
    data=dict(protocol=PROTOCOL,seeds=seeds,curriculum=CURRICULUM,pair_budget=e.CAP,
        library_cap=LIB_CAP,timing="Frozen and delayed share curriculum computation; final single-stage timing shared.",
        random_control="Number of motifs at each checkpoint matched to cumulative; independent random motif identities.",
        base_acquisition=h.a.training_metric(base_rows),
        training=[dict(policy=p,**training_metric([r for r in training if r["policy"]==p])) for p in POLICIES],
        by_checkpoint=[dict(policy=p,index=i,name=name,**training_metric([
            r for r in training if r["policy"]==p and r["index"]==i]))
            for p in POLICIES for i,name in enumerate(CURRICULUM)],
        snapshots=snapshots,
        aggregate=[dict(policy=p,**e.metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**e.metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
            for p in POLICIES for s,_ in GROUPS],
        by_seed=[dict(seed=seed,policy=p,**e.metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
            for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    for name,records in (("base_acquisition",base_rows),("curriculum",training),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,training=data["training"],aggregate=data["aggregate"]),indent=2))
    return data

class Tests(unittest.TestCase):
    def test_extension(self):
        p=("fork","mul","","","");q=("fork","concat","","sort","")
        self.assertEqual(extend((p,),(q,p),False),((p,),()))
        self.assertEqual(extend((p,),(q,p),True),((p,q),(q,)))
        self.assertEqual(extend((p,q),(p,q),True),((p,q),()))
    def test_tasks(self):
        self.assertEqual(len(CURRICULUM),14);self.assertEqual(len(set(CURRICULUM)),14)
        names=[name for _,names in GROUPS for name in names]
        self.assertEqual(len(names),14);self.assertEqual(len(set(names)),14)
        self.assertFalse(set(GROUPS[0][1])&set(CURRICULUM))
        for name in names:
            for x in ((),(2,),(-2,0,3)):
                self.assertIsInstance(oracle(name,x),tuple)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))
            self.assertTrue(all(r["n"]==14 and r["pair_examined"]<=14*e.CAP for r in s["training"]))
            ss={r["policy"]:r for r in s["snapshots"]}
            self.assertEqual(ss["random_growth"]["extra_count"],ss["cumulative"]["extra_count"])
            self.assertEqual(ss["frozen"]["extra_count"],0)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V49 required")
    run(out)

if __name__=="__main__":main()
