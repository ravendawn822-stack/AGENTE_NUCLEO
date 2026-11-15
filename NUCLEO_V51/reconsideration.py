"""V51: reconsider unresolved mathematical tasks after library changes."""
import argparse,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V49"))
import cumulative_motifs as v
e,h,c,f,m=v.e,v.h,v.c,v.f,v.m
SEEDS=(6780017,6810023,6840031,6870041)
POLICIES=("new_first","retry_first","random")
ATTEMPTS=14
COMMON=8
CAP=e.CAP
PROTOCOL="V51-contextual-reconsideration-v1"

def select(states,order,sha,policy,rng):
    if policy not in POLICIES:raise ValueError("policy")
    unseen=[i for i in order if states[i]["status"]=="unseen"]
    deferred=[i for i in order if states[i]["status"]=="deferred" and states[i]["last_sha"]!=sha]
    eligible=unseen+deferred
    if not eligible:return None,unseen,deferred
    if policy=="random":i=rng.choice(eligible)
    elif policy=="retry_first":i=(deferred or unseen)[0]
    else:i=(unseen or deferred)[0]
    return i,unseen,deferred

def curriculum(seed,base,public,teach,policy):
    if policy not in POLICIES:raise ValueError("policy")
    names=list(v.CURRICULUM);random.Random(seed^0x5101).shuffle(names)
    menu={i:tuple((x,e.oracle(n,x)) for x in public) for i,n in enumerate(names)}
    order=list(menu);random.Random(seed^0x5102).shuffle(order)
    rng=random.Random(seed^0x5103)
    states={i:dict(status="unseen",last_sha=None,attempts=0) for i in menu}
    lib=base;rows=[]
    for step in range(ATTEMPTS):
        before=lib;sha=m.digest(lib)
        start=time.perf_counter_ns()
        if step<COMMON:
            i=order[step];reason="common"
            unseen=[j for j in order if states[j]["status"]=="unseen"]
            deferred=[j for j in order if states[j]["status"]=="deferred" and states[j]["last_sha"]!=sha]
        else:
            i,unseen,deferred=select(states,order,sha,policy,rng)
            reason="idle" if i is None else ("reconsider" if i in deferred else "new")
        scheduling_ns=time.perf_counter_ns()-start
        if i is None:
            rows.append(dict(seed=seed,policy=policy,step=step,id=None,name=None,
                reason=reason,prior_status=None,status="idle",prior_attempts=0,
                before_sha=sha,after_sha=sha,prior_trial_sha=None,before_size=len(lib),after_size=len(lib),
                eligible_unseen=unseen,eligible_deferred=deferred,added=(),source_pair_hash=None,
                pair=None,emitted=False,accepted=False,recovered=False,validation_checks=0,
                validation_matches=0,validation_failure=None,pair_examined=0,pair_checks=0,
                pair_wall_ns=0,scheduling_ns=scheduling_ns,source=None))
            continue
        old=states[i]
        if old["status"] not in ("unseen","deferred") or (old["status"]=="deferred" and old["last_sha"]==sha):
            raise RuntimeError("invalid repeated attempt")
        pair,stats=e.pair_search(menu[i],lib,CAP)
        checks=matches=0;failure=None
        if pair:
            for x in teach:
                expected=e.oracle(names[i],x);actual=c.eval_pair(pair,x)
                checks+=1;matches+=actual==expected
                if actual!=expected and failure is None:
                    failure=dict(input=x,expected=expected,actual=actual)
        accepted=pair is not None and matches==len(teach)
        status="accepted" if accepted else ("rejected" if pair else "deferred")
        states[i]=dict(status=status,last_sha=sha,attempts=old["attempts"]+1)
        lib,added=v.extend(lib,pair,accepted)
        rows.append(dict(seed=seed,policy=policy,step=step,id=i,name=names[i],reason=reason,
            prior_status=old["status"],status=status,prior_attempts=old["attempts"],
            before_sha=sha,after_sha=m.digest(lib),prior_trial_sha=old["last_sha"],
            before_size=len(before),after_size=len(lib),eligible_unseen=unseen,eligible_deferred=deferred,
            added=added,source_pair_hash=m.digest(pair) if accepted else None,
            pair=pair,emitted=pair is not None,accepted=accepted,
            recovered=accepted and old["status"]=="deferred",
            validation_checks=checks,validation_matches=matches,validation_failure=failure,
            scheduling_ns=scheduling_ns,**stats))
    return lib,rows,names

def training_metric(rows):
    accepted=sum(r["accepted"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    idle=sum(r["id"] is None for r in rows);n=len(rows);attempted=n-idle
    return dict(n=n,attempted=attempted,accepted=accepted,rejected=emitted-accepted,
        abstained=attempted-emitted,idle=idle,
        retried=sum(r["prior_status"]=="deferred" for r in rows),
        recovered=sum(r["recovered"] for r in rows),
        acquired_motifs=sum(len(r["added"]) for r in rows),
        **{k:sum(r[k] for r in rows) for k in ("pair_examined","pair_checks","pair_wall_ns",
            "scheduling_ns","validation_checks")})

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
            if policy=="new_first":menus.append(dict(seed=seed,id_to_target=names))
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
    summary=dict(protocol=PROTOCOL,seeds=seeds,attempts=ATTEMPTS,round_budget=CAP,common_attempts=COMMON,
        menu_public_observations_per_seed_per_policy=len(v.CURRICULUM)*14,
        timing="Final single-stage search shared. No extra probes; scheduler sees states and library hash.",
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
    def test_selection(self):
        states={0:dict(status="deferred",last_sha="a"),1:dict(status="unseen",last_sha=None),
                2:dict(status="accepted",last_sha="a"),3:dict(status="rejected",last_sha="a")}
        order=[0,1,2,3];rng=random.Random(1)
        self.assertEqual(select(states,order,"a","retry_first",rng)[0],1)
        self.assertEqual(select(states,order,"b","retry_first",rng)[0],0)
        self.assertEqual(select(states,order,"b","new_first",rng)[0],1)
        self.assertEqual(select(states,order,"b","random",rng)[0] in (0,1),True)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"case";s=run(path,SEEDS[:1])
            self.assertTrue(all(r["n"]==ATTEMPTS and r["pair_examined"]<=ATTEMPTS*CAP for r in s["training"]))
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))
            traces=[json.loads(x) for x in (path/"curriculum.jsonl").read_text().splitlines()]
            common=[]
            for policy in POLICIES:
                rs=[r for r in traces if r["policy"]==policy]
                common.append([(r["id"],r["status"],r["after_sha"]) for r in rs[:COMMON]])
                self.assertTrue(all(r["pair_examined"]<=CAP for r in rs))
                self.assertTrue(all(not r["added"] or r["accepted"] for r in rs))
                self.assertTrue(all(r["prior_trial_sha"]!=r["before_sha"] for r in rs if r["prior_status"]=="deferred"))
                accepted=[r["id"] for r in rs if r["accepted"]]
                self.assertEqual(len(accepted),len(set(accepted)))
            self.assertEqual(common[0],common[1]);self.assertEqual(common[0],common[2])
    def test_menu(self):
        self.assertEqual(len(set(v.CURRICULUM)),14)
        self.assertEqual(ATTEMPTS,14)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V51 required")
    run(out)

if __name__=="__main__":main()
