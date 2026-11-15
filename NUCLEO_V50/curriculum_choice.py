"""V50: bounded curriculum choice using observable mathematical examples."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V49"))
import cumulative_motifs as v
e,h,c,f,m=v.e,v.h,v.c,v.f,v.m
SEEDS=(6660017,6690023,6720031,6750041)
POLICIES=("designed","random","adaptive")
ATTEMPTS=8
PROBE=256
CAP=e.CAP
PROTOCOL="V50-bounded-curriculum-choice-v1"

def probe(examples,lib):
    examined=checks=best=0;found=None;origin=None
    for pair,source in itertools.islice(e.order(lib),PROBE):
        examined+=1;matched=0
        for x,y in examples:
            checks+=1
            if c.eval_pair(pair,x)!=y:break
            matched+=1
        best=max(best,matched)
        if matched==len(examples):
            found=pair;origin=source;break
    novelty=len(set(found)-set(lib)) if found else 0
    return dict(pair=found,source=origin,examined=examined,checks=checks,best_prefix=best,novelty=novelty)

def rank(record):
    if record["pair"] and record["novelty"]:
        return (2,record["novelty"],-record["examined"])
    if record["pair"] is None:
        return (1,record["best_prefix"],0)
    return (0,0,-record["examined"])

def choose(menu,remaining,lib):
    """No evaluator labels or validation outputs enter the selector."""
    start=time.perf_counter_ns()
    probes=[dict(id=i,**probe(menu[i],lib)) for i in sorted(remaining)]
    picked=max(probes,key=rank)
    return picked,probes,time.perf_counter_ns()-start

def curriculum(seed,base,public,teach,policy):
    if policy not in POLICIES:raise ValueError("policy")
    names=list(v.CURRICULUM)
    random.Random(seed^0x5001).shuffle(names)
    menu={i:tuple((x,e.oracle(n,x)) for x in public) for i,n in enumerate(names)}
    # The scheduler sees opaque integer IDs and observation pairs.
    designed=[names.index(n) for n in v.CURRICULUM]
    randomized=list(menu);random.Random(seed^0x5002).shuffle(randomized)
    remaining=set(menu);lib=base;rows=[]
    for step in range(ATTEMPTS):
        before=lib;probes=[];planning_ns=0
        if policy=="adaptive":
            selected,probes,planning_ns=choose(menu,remaining,lib)
            i=selected["id"]
        else:
            i=(designed if policy=="designed" else randomized)[step]
            selected=None
        remaining.remove(i)
        planned=sum(p["examined"] for p in probes)
        planning_checks=sum(p["checks"] for p in probes)
        if selected and selected["pair"]:
            pair=selected["pair"]
            stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="probe")
        else:
            pair,stats=e.pair_search(menu[i],lib,CAP-planned)
        total=stats["pair_examined"]+planned
        if total>CAP:raise RuntimeError("round budget")
        checks=matches=0;failure=None
        if pair:
            for x in teach:
                y=e.oracle(names[i],x);actual=c.eval_pair(pair,x)
                checks+=1;matches+=actual==y
                if actual!=y and failure is None:
                    failure=dict(input=x,expected=y,actual=actual)
        accepted=pair is not None and matches==len(teach)
        lib,added=v.extend(lib,pair,accepted)
        rows.append(dict(seed=seed,policy=policy,step=step,id=i,name=names[i],
            before_sha=m.digest(before),after_sha=m.digest(lib),
            before_size=len(before),after_size=len(lib),added=added,
            source_pair_hash=m.digest(pair) if accepted else None,
            pair=pair,emitted=pair is not None,accepted=accepted,
            validation_checks=checks,validation_matches=matches,validation_failure=failure,
            planning_examined=planned,planning_checks=planning_checks,planning_ns=planning_ns,
            total_examined=total,total_checks=stats["pair_checks"]+planning_checks,
            probes=probes,**stats))
    return lib,rows,names

def training_metric(rows):
    n=len(rows);accepted=sum(r["accepted"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    return dict(n=n,accepted=accepted,rejected=emitted-accepted,abstained=n-emitted,
        acquired_motifs=sum(len(r["added"]) for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("planning_examined","planning_checks","planning_ns",
            "pair_examined","pair_checks","pair_wall_ns","total_examined","total_checks","validation_checks")})

def run(out,seeds=SEEDS):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];training=[];base_rows=[];snapshots=[];menus=[]
    for seed in seeds:
        parts=h.inputs(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        (out/f"inputs_{seed}.json").write_text(m.enc(dict(zip(
            ("initial","pool","challenge","base_teach","curriculum_public","curriculum_teach","final_public","held"),parts))),encoding="utf-8")
        base,learned=h.acquire_base(seed,initial,pool,ch,teach);base_rows.extend(learned)
        base,base_sha=c.freeze(out/f"base_{seed}.json",base)
        frozen={}
        for policy in POLICIES:
            lib,records,names=curriculum(seed,base,pub2,teach2,policy)
            training.extend(records)
            lib,sha=e.freeze(out/f"library_{seed}_{policy}.json",lib)
            frozen[policy]=(lib,sha)
            snapshots.append(dict(seed=seed,policy=policy,base_sha=base_sha,
                library=lib,library_sha=sha,extra_count=len(lib)-len(base)))
            if policy=="adaptive":menus.append(dict(seed=seed,id_to_target=names))
        for stratum,names in v.GROUPS:
            for name in names:
                examples=tuple((x,v.oracle(name,x)) for x in public)
                single,prep=f.search(examples,True,True,(),1)
                for policy in POLICIES:
                    lib,_=frozen[policy]
                    if single:
                        program=("single",single[0])
                        stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
                    else:
                        pair,stats=e.pair_search(examples,lib)
                        program=("pair",pair) if pair else None
                    used=bool(program and program[0]=="pair" and any(p in lib and p not in base for p in program[1]))
                    rows.append(dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        **v.score(program,name,held),**stats,extension_used=used,
                        single_examined=prep["examined"],single_checks=prep["checks"],
                        shared_single_ns=prep["wall_ns"]))
        for lib,sha in frozen.values():
            if m.digest(dict(library=lib))!=sha:raise RuntimeError("memory changed")
    summary=dict(protocol=PROTOCOL,seeds=seeds,attempts=ATTEMPTS,round_budget=CAP,probe_budget=PROBE,
        menu_public_observations_per_seed_per_policy=len(v.CURRICULUM)*14,
        timing="Final single-stage search shared. Adaptive planning counted against round budget.",
        menus=menus,snapshots=snapshots,base_acquisition=h.a.training_metric(base_rows),
        training=[dict(policy=p,**training_metric([r for r in training if r["policy"]==p])) for p in POLICIES],
        aggregate=[dict(policy=p,**e.metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(policy=p,stratum=s,**e.metric([r for r in rows if r["policy"]==p and r["stratum"]==s]))
                    for p in POLICIES for s,_ in v.GROUPS],
        by_seed=[dict(seed=seed,policy=p,**e.metric([r for r in rows if r["seed"]==seed and r["policy"]==p]))
                 for seed in seeds for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,records in (("base_acquisition",base_rows),("curriculum",training),("final",rows)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    print(json.dumps(dict(protocol=PROTOCOL,training=summary["training"],aggregate=summary["aggregate"]),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_probe(self):
        square=("fork","mul","","","")
        result=probe([((2,3),(16,81)),((-2,4),(16,256))],(square,))
        self.assertEqual(result["pair"],(square,square))
        self.assertEqual(result["examined"],1)
        self.assertGreater(rank(dict(result,novelty=1)),rank(result))
        self.assertGreater(rank(dict(pair=None,best_prefix=1)),rank(result))
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"case";s=run(path,SEEDS[:1])
            self.assertEqual(len(s["training"]),3)
            self.assertTrue(all(r["n"]==ATTEMPTS and r["total_examined"]<=ATTEMPTS*CAP for r in s["training"]))
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))
            traces=[json.loads(x) for x in (path/"curriculum.jsonl").read_text().splitlines()]
            for policy in POLICIES:
                rs=[r for r in traces if r["policy"]==policy]
                self.assertEqual(len({r["id"] for r in rs}),ATTEMPTS)
                self.assertTrue(all(r["total_examined"]<=CAP for r in rs))
                self.assertTrue(all(not r["added"] or r["accepted"] for r in rs))
    def test_menu(self):
        self.assertEqual(len(set(v.CURRICULUM)),14)
        self.assertLess(PROBE*len(v.CURRICULUM),CAP)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V50 required")
    run(out)

if __name__=="__main__":main()
