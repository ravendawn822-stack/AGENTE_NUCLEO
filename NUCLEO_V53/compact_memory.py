"""V53: equivalent exact negative-memory representations."""
import argparse,itertools,json,random,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V49"))
import cumulative_motifs as v
e,h,c,f,m=v.e,v.h,v.c,v.f,v.m
SEEDS=(7020017,7050023,7080031,7110041)
POLICIES=("set","dense","paged")
COMMON=14
ATTEMPTS=20
CAP=e.CAP
SCAN_CAP=2*CAP
CACHE_CAP=7*CAP
INDEX={p:i for i,p in enumerate(c.MOTIFS)}
PROTOCOL="V53-exact-compact-negative-memory-v1"
UNIVERSE=len(c.MOTIFS)**2
PAGE_BITS=4096
PAGE_BYTES=PAGE_BITS//8

class NegativeMemory:
    """Exact representation; IDs identify ordered pairs in an immutable grammar."""
    def __init__(self,examples,mode):
        if mode not in POLICIES:raise ValueError("backend")
        self.context=m.digest(examples)
        self.mode=mode
        self.count=0
        self.store=set() if mode=="set" else (bytearray((UNIVERSE+7)//8) if mode=="dense" else {})
    def check(self,examples):
        if self.context!=m.digest(examples):
            raise ValueError("negative cache belongs to different observations")
    def __len__(self):return self.count
    def __contains__(self,i):
        if not isinstance(i,int) or not 0<=i<UNIVERSE:raise ValueError("candidate ID")
        if self.mode=="set":return i in self.store
        if self.mode=="dense":return bool(self.store[i//8] & (1<<(i%8)))
        page,offset=divmod(i,PAGE_BITS)
        data=self.store.get(page)
        return data is not None and bool(data[offset//8] & (1<<(offset%8)))
    def remember(self,i):
        if i in self:return
        if self.count>=CACHE_CAP:raise RuntimeError("negative cache cap")
        if self.mode=="set":self.store.add(i)
        elif self.mode=="dense":self.store[i//8]|=1<<(i%8)
        else:
            page,offset=divmod(i,PAGE_BITS)
            data=self.store.get(page)
            if data is None:
                data=bytearray(PAGE_BYTES);self.store[page]=data
            data[offset//8]|=1<<(offset%8)
        self.count+=1
    def storage_bytes(self):
        size=sys.getsizeof(self.store)
        if self.mode=="set":return size+sum(sys.getsizeof(i) for i in self.store)
        if self.mode=="paged":
            return size+sum(sys.getsizeof(k)+sys.getsizeof(b) for k,b in self.store.items())
        return size
    def bitmap_payload_bytes(self):
        if self.mode=="dense":return len(self.store)
        if self.mode=="paged":return len(self.store)*PAGE_BYTES
        return 0

def memory_stats(caches):
    return dict(cache_peak_round=sum(len(x) for x in caches.values()),
        cache_storage_checkpoint_bytes=sum(x.storage_bytes() for x in caches.values()),
        bitmap_payload_checkpoint_bytes=sum(x.bitmap_payload_bytes() for x in caches.values()))

def search(examples,lib,policy,cache=None,cap=CAP):
    if policy not in POLICIES or not 1<=cap<=CAP or not examples:raise ValueError("search bounds")
    if cache is None or cache.mode!=policy:raise ValueError("matching cache required")
    cache.check(examples)
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
            if c.eval_pair(pair,x)!=y:
                cache.remember(key)
                break
        else:
            found,origin=pair,source;break
    assert scanned==examined+skipped
    return found,dict(pair_examined=examined,pair_checks=checks,positions_scanned=scanned,
        cached_skips=skipped,pair_wall_ns=time.perf_counter_ns()-start,source=origin)

def curriculum(seed,base,public,teach,policy):
    names=list(v.CURRICULUM);random.Random(seed^0x5301).shuffle(names)
    menu={i:tuple((x,e.oracle(n,x)) for x in public) for i,n in enumerate(names)}
    order=list(menu);random.Random(seed^0x5302).shuffle(order)
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
                source=None,cache_entries=sum(len(x) for x in caches.values()),**memory_stats(caches)))
            continue
        old=states[i]
        if old["status"] not in ("unseen","deferred") or old["last_sha"]==sha:raise RuntimeError("invalid retry")
        if i not in caches:caches[i]=NegativeMemory(menu[i],policy)
        cache=caches[i]
        pair,stats=search(menu[i],lib,policy,cache)
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
            **stats))
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
            if policy=="set":menus.append(dict(seed=seed,id_to_target=names))
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
        memory_measurement="Attributed backend storage via sys.getsizeof at round checkpoints; not RSS or whole-process peak.",
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
            if signatures(training,"set",keys)!=signatures(training,policy,keys):
                raise RuntimeError("training representation divergence")
            if signatures(rows,"set",final_keys)!=signatures(rows,policy,final_keys):
                raise RuntimeError("final representation divergence")
            if signatures(snapshots,"set",("library_sha",))!=signatures(snapshots,policy,("library_sha",)):
                raise RuntimeError("library divergence")
    return dict(exact_trajectory_match=True,seeds=len(seeds))

class Tests(unittest.TestCase):
    def test_exact(self):
        rng=random.Random(53)
        selected={0,7,8,PAGE_BITS-1,PAGE_BITS,UNIVERSE-1}
        selected.update(rng.sample(range(UNIVERSE),12000))
        probes=set(rng.sample(range(UNIVERSE),12000))|selected
        examples=(((2,3),(987,)),)
        for mode in POLICIES:
            cache=NegativeMemory(examples,mode)
            for i in sorted(selected):
                cache.remember(i);cache.remember(i)
            self.assertEqual(len(cache),len(selected))
            self.assertTrue(all((i in cache)==(i in selected) for i in probes))
            self.assertGreater(cache.storage_bytes(),0)
            for i in (-1,UNIVERSE):
                with self.assertRaises(ValueError):cache.remember(i)
            with self.assertRaises(ValueError):cache.check((((2,3),(4,9)),))
    def test_resume(self):
        square=("fork","mul","","","")
        examples=(((2,3),(987,)),)
        for mode in POLICIES:
            cache=NegativeMemory(examples,mode)
            p,s=search(examples,(square,),mode,cache,8)
            self.assertIsNone(p);self.assertEqual(s["pair_examined"],8)
            p,s=search(examples,(square,),mode,cache,8)
            self.assertIsNone(p);self.assertEqual(s["cached_skips"],8)
            self.assertEqual(s["positions_scanned"],16);self.assertEqual(s["pair_examined"],8)
            with self.assertRaises(ValueError):
                search((((2,3),(4,9)),),(square,),mode,cache,8)
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            s=run(Path(d)/"case",SEEDS[:1])
            self.assertTrue(s["equivalence"]["exact_trajectory_match"])
            self.assertTrue(all(r["n"]==ATTEMPTS and r["pair_examined"]<=ATTEMPTS*CAP for r in s["training"]))
            self.assertTrue(all(r["n"]==14 for r in s["aggregate"]))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:p.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:p.error("new output directory inside NUCLEO_V53 required")
    run(out)

if __name__=="__main__":main()
