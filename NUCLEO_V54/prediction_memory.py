"""V54: exact cross-task prediction reuse with bounded LRU."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
from collections import OrderedDict
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V49"))
import cumulative_motifs as v
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V53"))
from compact_memory import NegativeMemory, memory_stats
e,h,c,f,m=v.e,v.h,v.c,v.f,v.m
SEEDS=(7140017,7170023,7200031,7230041)
POLICIES=("direct","pair_lru","motif_lru")
COMMON=14
ATTEMPTS=20
CAP=e.CAP
SCAN_CAP=2*CAP
CACHE_CAP=7*CAP
INDEX={p:i for i,p in enumerate(c.MOTIFS)}
PROTOCOL="V54-cross-task-prediction-reuse-v1"
PREDICTION_CAP=32768
UNIVERSE=len(c.MOTIFS)**2
PAGE_BITS=4096
PAGE_BYTES=PAGE_BITS//8

class PredictionMemory:
    def __init__(self,mode,capacity=PREDICTION_CAP):
        if mode not in POLICIES or not 1<=capacity<=PREDICTION_CAP:raise ValueError("prediction cache bounds")
        self.mode=mode;self.capacity=capacity;self.store=OrderedDict()
        self.stats=dict(real_motif_evaluations=0,prediction_hits=0,prediction_misses=0,
                        cross_task_hits=0,prediction_evictions=0)
    def lookup(self,key,task,compute):
        if key in self.store:
            value,origin=self.store[key]
            self.store.move_to_end(key)
            self.stats["prediction_hits"]+=1
            self.stats["cross_task_hits"]+=origin!=task
            return value
        self.stats["prediction_misses"]+=1
        value=compute();self.store[key]=(value,task)
        if len(self.store)>self.capacity:
            self.store.popitem(last=False);self.stats["prediction_evictions"]+=1
        return value
    def calculate_motif(self,p,x):
        self.stats["real_motif_evaluations"]+=1
        return f.evaluate(p,x)
    def motif(self,p,x,task):
        if self.mode=="motif_lru":
            return self.lookup((p,x),task,lambda:self.calculate_motif(p,x))
        return self.calculate_motif(p,x)
    def pair(self,pair,x,task):
        def compute():
            first=self.motif(pair[0],x,task)
            return None if first is None else self.motif(pair[1],first,task)
        if self.mode=="pair_lru":return self.lookup((pair,x),task,compute)
        return compute()
    def storage_bytes(self):
        if self.mode=="direct":return 0
        return sys.getsizeof(self.store)+sum(
            sys.getsizeof(key)+sys.getsizeof(value)+sys.getsizeof(key[1])+sys.getsizeof(value[0])
            for key,value in self.store.items())

def search(examples,lib,policy,cache,prediction,task,cap=CAP):
    if policy not in POLICIES or not 1<=cap<=CAP or not examples:raise ValueError("search bounds")
    if cache.mode!="paged" or prediction.mode!=policy:raise ValueError("matching cache required")
    cache.check(examples)
    before=prediction.stats.copy()
    start=time.perf_counter_ns()
    examined=checks=scanned=skipped=0;found=origin=None
    scan_limit=2*cap
    for pair,source in itertools.islice(e.order(lib),scan_limit):
        if examined>=cap:break
        scanned+=1
        key=INDEX[pair[0]]*len(c.MOTIFS)+INDEX[pair[1]]
        if key in cache:
            skipped+=1;continue
        examined+=1
        for x,y in examples:
            checks+=1
            if prediction.pair(pair,x,task)!=y:
                cache.remember(key)
                break
        else:
            found,origin=pair,source;break
    assert scanned==examined+skipped
    return found,dict(pair_examined=examined,pair_checks=checks,positions_scanned=scanned,
        cached_skips=skipped,pair_wall_ns=time.perf_counter_ns()-start,source=origin,
        **{k:prediction.stats[k]-before[k] for k in before})

def curriculum(seed,base,public,teach,policy):
    names=list(v.CURRICULUM);random.Random(seed^0x5401).shuffle(names)
    menu={i:tuple((x,e.oracle(n,x)) for x in public) for i,n in enumerate(names)}
    order=list(menu);random.Random(seed^0x5402).shuffle(order)
    states={i:dict(status="unseen",last_sha=None,attempts=0) for i in menu}
    caches={};lib=base;rows=[];prediction=PredictionMemory(policy)
    for step in range(ATTEMPTS):
        sha=m.digest(lib);before=lib
        eligible=[i for i in order if states[i]["status"]=="deferred" and states[i]["last_sha"]!=sha]
        i=order[step] if step<COMMON else (eligible[0] if eligible else None)
        if i is None:
            rows.append(dict(seed=seed,policy=policy,step=step,id=None,name=None,status="idle",prior_status=None,
                before_sha=sha,after_sha=sha,added=(),pair=None,emitted=False,accepted=False,
                recovered=False,validation_checks=0,validation_matches=0,validation_failure=None,
                pair_examined=0,pair_checks=0,positions_scanned=0,cached_skips=0,pair_wall_ns=0,
                source=None,cache_entries=sum(len(x) for x in caches.values()),**memory_stats(caches),
                prediction_entries=len(prediction.store),prediction_storage_bytes=prediction.storage_bytes(),
                **{k:0 for k in prediction.stats}))
            continue
        old=states[i]
        if old["status"] not in ("unseen","deferred") or old["last_sha"]==sha:raise RuntimeError("invalid retry")
        if i not in caches:caches[i]=NegativeMemory(menu[i],"paged")
        cache=caches[i]
        pair,stats=search(menu[i],lib,policy,cache,prediction,i)
        memory=memory_stats(caches)
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
            cache_entries=sum(len(x) for x in caches.values()),**memory,
            prediction_entries=len(prediction.store),prediction_storage_bytes=prediction.storage_bytes(),**stats))
    return lib,rows,names

def training_metric(rows):
    accepted=sum(r["accepted"] for r in rows);emitted=sum(r["emitted"] for r in rows)
    idle=sum(r["id"] is None for r in rows);n=len(rows)
    return dict(n=n,attempted=n-idle,accepted=accepted,rejected=emitted-accepted,
        abstained=n-idle-emitted,idle=idle,retried=sum(r["prior_status"]=="deferred" for r in rows),
        recovered=sum(r["recovered"] for r in rows),acquired_motifs=sum(len(r["added"]) for r in rows),
        peak_cache_entries_one_replica=max((r["cache_peak_round"] for r in rows),default=0),
        peak_checkpoint_storage_bytes=max((r["cache_storage_checkpoint_bytes"] for r in rows),default=0),
        peak_checkpoint_bitmap_payload_bytes=max((r["bitmap_payload_checkpoint_bytes"] for r in rows),default=0),
        peak_prediction_entries=max((r["prediction_entries"] for r in rows),default=0),
        peak_prediction_storage_bytes=max((r["prediction_storage_bytes"] for r in rows),default=0),
        **{k:sum(r[k] for r in rows) for k in ("pair_examined","pair_checks","positions_scanned",
           "cached_skips","pair_wall_ns","validation_checks","real_motif_evaluations","prediction_hits",
           "prediction_misses","cross_task_hits","prediction_evictions")})

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
            if policy=="direct":menus.append(dict(seed=seed,id_to_target=names))
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
    equivalence=verify_equivalence(training,rows,snapshots,seeds)
    summary=dict(equivalence=equivalence,protocol=PROTOCOL,seeds=seeds,attempts=ATTEMPTS,round_budget=CAP,common_attempts=COMMON,scan_cap=SCAN_CAP,
        menu_public_observations_per_seed_per_policy=len(v.CURRICULUM)*14,
        timing="Final single-stage search shared. Negative cache only in acquisition. Storage measurement outside search timer.",
        memory_measurement="Shallow attributed prediction storage at checkpoints; tuple members not recursively charged. Not RSS.",
        prediction_capacity=PREDICTION_CAP,
        universe=UNIVERSE,page_bits=PAGE_BITS,
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



def verify_equivalence(training,rows,snapshots,seeds):
    keys=("step","id","status","pair","before_sha","after_sha","added","accepted",
          "validation_matches","validation_checks","validation_failure","pair_examined",
          "pair_checks","positions_scanned","cached_skips","cache_entries","cache_peak_round")
    final_keys=("name","stratum","program","correct","emitted","held_matches","held_tests","first_failure","pair_examined","pair_checks")
    for seed in seeds:
        def signatures(records,policy,fields):
            return [tuple(r[k] for k in fields) for r in records if r["seed"]==seed and r["policy"]==policy]
        for policy in POLICIES[1:]:
            if signatures(training,"direct",keys)!=signatures(training,policy,keys):
                raise RuntimeError("training representation divergence")
            if signatures(rows,"direct",final_keys)!=signatures(rows,policy,final_keys):
                raise RuntimeError("final representation divergence")
            if signatures(snapshots,"direct",("library_sha",))!=signatures(snapshots,policy,("library_sha",)):
                raise RuntimeError("library divergence")
    return dict(exact_trajectory_match=True,seeds=len(seeds))

class Tests(unittest.TestCase):
    def test_prediction(self):
        rng=random.Random(54)
        for mode in POLICIES:
            p=PredictionMemory(mode,capacity=32)
            for i in range(200):
                pair=rng.choice(c.MOTIFS),rng.choice(c.MOTIFS)
                x=tuple(rng.randint(-4,4) for _ in range(rng.randint(1,6)))
                self.assertEqual(p.pair(pair,x,i%3),c.eval_pair(pair,x))
                self.assertEqual(p.pair(pair,x,(i+1)%3),c.eval_pair(pair,x))
            self.assertLessEqual(len(p.store),32)
            if mode!="direct":self.assertGreater(p.stats["cross_task_hits"],0)
    def test_lru(self):
        p=PredictionMemory("pair_lru",2)
        self.assertIsNone(p.lookup(("a",(1,)),0,lambda:None))
        self.assertIsNone(p.lookup(("a",(1,)),1,lambda:self.fail("unexpected computation")))
        p.lookup(("b",(1,)),0,lambda:(1,))
        p.lookup(("c",(1,)),0,lambda:(2,))
        self.assertNotIn(("a",(1,)),p.store)
        self.assertEqual(p.stats["prediction_evictions"],1)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(s["equivalence"]["exact_trajectory_match"])
            self.assertTrue(all(r["n"]==ATTEMPTS and r["pair_examined"]<=ATTEMPTS*CAP for r in s["training"]))
            self.assertTrue(all(r["peak_prediction_entries"]<=PREDICTION_CAP for r in s["training"]))
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V54 required")
    run(out)

if __name__=="__main__":main()
