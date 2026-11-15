"""V52: contextual negative memory for bounded mathematical searches."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V49"))
import cumulative_motifs as v
e,h,c,f,m=v.e,v.h,v.c,v.f,v.m
SEEDS=(6900017,6930023,6960031,6990041)
POLICIES=("restart","cached_prefix","cached_extend")
COMMON=14
ATTEMPTS=20
CAP=e.CAP
SCAN_CAP=2*CAP
CACHE_CAP=7*CAP
INDEX={p:i for i,p in enumerate(c.MOTIFS)}
PROTOCOL="V52-contextual-negative-memory-v1"

class NegativeMemory:
    def __init__(self,examples):
        self.context=m.digest(examples)
        self.ids=set()
    def check(self,examples):
        if self.context!=m.digest(examples):
            raise ValueError("negative cache belongs to different observations")
    def remember(self,i):
        if len(self.ids)>=CACHE_CAP:raise RuntimeError("negative cache cap")
        self.ids.add(i)

def search(examples,lib,policy,cache=None,cap=CAP):
    if policy not in POLICIES or not 1<=cap<=CAP or not examples:raise ValueError("search bounds")
    if policy=="restart" and cache is not None:raise ValueError("restart has no cache")
    if policy!="restart":
        if cache is None:raise ValueError("cache required")
        cache.check(examples)
    start=time.perf_counter_ns()
    examined=checks=scanned=skipped=0;found=origin=None
    scan_limit=2*cap if policy=="cached_extend" else cap
    for pair,source in itertools.islice(e.order(lib),scan_limit):
        if examined>=cap:break
        scanned+=1
        key=INDEX[pair[0]]*len(c.MOTIFS)+INDEX[pair[1]]
        if cache is not None and key in cache.ids:
            skipped+=1;continue
        examined+=1
        for x,y in examples:
            checks+=1
            if c.eval_pair(pair,x)!=y:
                if cache is not None:cache.remember(key)
                break
        else:
            found,origin=pair,source;break
    assert scanned==examined+skipped
    return found,dict(pair_examined=examined,pair_checks=checks,positions_scanned=scanned,
        cached_skips=skipped,pair_wall_ns=time.perf_counter_ns()-start,source=origin)

def curriculum(seed,base,public,teach,policy):
    names=list(v.CURRICULUM);random.Random(seed^0x5201).shuffle(names)
    menu={i:tuple((x,e.oracle(n,x)) for x in public) for i,n in enumerate(names)}
    order=list(menu);random.Random(seed^0x5202).shuffle(order)
    states={i:dict(status="unseen",last_sha=None,attempts=0) for i in menu}
    caches={};lib=base;rows=[]
    for step in range(ATTEMPTS):
        sha=m.digest(lib);before=lib
        eligible=[i for i in order if states[i]["status"]=="deferred" and states[i]["last_sha"]!=sha]
        i=order[step] if step<COMMON else (eligible[0] if eligible else None)
        if i is None:
            rows.append(dict(seed=seed,policy=policy,step=step,id=None,name=None,status="idle",prior_status=None,
                before_sha=sha,after_sha=sha,added=(),pair=None,emitted=False,accepted=False,
                recovered=False,validation_checks=0,validation_matches=0,validation_failure=None,
                pair_examined=0,pair_checks=0,positions_scanned=0,cached_skips=0,pair_wall_ns=0,
                source=None,cache_entries=sum(len(x.ids) for x in caches.values()),cache_peak_round=sum(len(x.ids) for x in caches.values())))
            continue
        old=states[i]
        if old["status"] not in ("unseen","deferred") or old["last_sha"]==sha:raise RuntimeError("invalid retry")
        cache=None
        if policy!="restart":
            if i not in caches:caches[i]=NegativeMemory(menu[i])
            cache=caches[i]
        pair,stats=search(menu[i],lib,policy,cache)
        cache_peak=sum(len(x.ids) for x in caches.values())
        matches=checks=0;failure=None
        if pair:
            for x in teach:
                expected=e.oracle(names[i],x);actual=c.eval_pair(pair,x)
                checks+=1;matches+=expected==actual
                if expected!=actual and failure is None:failure=dict(input=x,expected=expected,actual=actual)
        accepted=pair is not None and matches==len(teach)
        status="accepted" if accepted else ("rejected" if pair else "deferred")
        states[i]=dict(status=status,last_sha=sha,attempts=old["attempts"]+1)
        if status!="deferred":caches.pop(i,None)
        lib,added=v.extend(lib,pair,accepted)
        rows.append(dict(seed=seed,policy=policy,step=step,id=i,name=names[i],
            status=status,prior_status=old["status"],prior_trial_sha=old["last_sha"],
            before_sha=sha,after_sha=m.digest(lib),before_size=len(before),after_size=len(lib),
            added=added,pair=pair,emitted=pair is not None,accepted=accepted,
            recovered=accepted and old["status"]=="deferred",validation_checks=checks,
            validation_matches=matches,validation_failure=failure,
            cache_entries=sum(len(x.ids) for x in caches.values()),cache_peak_round=cache_peak,
            **stats))
    return lib,rows,names

def training_metric(rows):
    accepted=sum(r["accepted"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    idle=sum(r["id"] is None for r in rows);n=len(rows)
    return dict(n=n,attempted=n-idle,accepted=accepted,rejected=emitted-accepted,
        abstained=n-idle-emitted,idle=idle,retried=sum(r["prior_status"]=="deferred" for r in rows),
        recovered=sum(r["recovered"] for r in rows),acquired_motifs=sum(len(r["added"]) for r in rows),
        peak_cache_entries_one_replica=max((r["cache_peak_round"] for r in rows),default=0),
        **{k:sum(r[k] for r in rows) for k in ("pair_examined","pair_checks","positions_scanned",
           "cached_skips","pair_wall_ns","validation_checks")})

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
            if policy=="restart":menus.append(dict(seed=seed,id_to_target=names))
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
    summary=dict(protocol=PROTOCOL,seeds=seeds,attempts=ATTEMPTS,round_budget=CAP,common_attempts=COMMON,scan_cap=SCAN_CAP,
        menu_public_observations_per_seed_per_policy=len(v.CURRICULUM)*14,
        timing="Final single-stage search shared. Negative cache only in acquisition. Selection order shared until policies diverge.",
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
    def test_cache(self):
        square=("fork","mul","","","")
        examples=(((2,3),(987,)),)
        cache=NegativeMemory(examples)
        p,s=search(examples,(square,),"cached_prefix",cache,8)
        self.assertIsNone(p);self.assertEqual(s["pair_examined"],8)
        p,s=search(examples,(square,),"cached_prefix",cache,8)
        self.assertIsNone(p);self.assertEqual(s["cached_skips"],8)
        self.assertEqual(s["pair_examined"],0)
        p,s=search(examples,(square,),"cached_extend",cache,8)
        self.assertEqual(s["positions_scanned"],16)
        self.assertEqual(s["pair_examined"],8)
        with self.assertRaises(ValueError):search((((2,3),(4,9)),),(square,),"cached_prefix",cache,8)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"case";s=run(out,SEEDS[:1])
            self.assertTrue(all(r["n"]==ATTEMPTS and r["pair_examined"]<=ATTEMPTS*CAP for r in s["training"]))
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))
            t=[json.loads(z) for z in (out/"curriculum.jsonl").read_text().splitlines()]
            def key(policy):
                return [(r["id"],r["status"],r["pair"],r["after_sha"]) for r in t if r["policy"]==policy]
            self.assertEqual(key("restart"),key("cached_prefix"))
            for r in t:
                self.assertEqual(r["positions_scanned"],r["pair_examined"]+r["cached_skips"])
                self.assertLessEqual(r["positions_scanned"],SCAN_CAP)
                self.assertLessEqual(r["pair_examined"],CAP)
                self.assertTrue(not r["added"] or r["accepted"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V52 required")
    run(out)

if __name__=="__main__":main()
