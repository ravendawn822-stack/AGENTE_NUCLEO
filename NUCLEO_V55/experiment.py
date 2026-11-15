"""Independent experiment harness for V55. Only writes to a new directory."""
import argparse,json,random,unittest
from unittest.mock import patch
from pathlib import Path
from core import Core,POLICIES,ROOT,previous,v,e,h,c,f,m

SEEDS=(7260017,7290023,7320031,7350041)
REGRESSION=7140017
PROTOCOL="V55-integrated-core-v1"
LOGIC=("step","id","context","status","prior_status","prior_trial_sha","pair","before_sha",
       "after_sha","added","accepted","validation_checks","validation_matches","validation_failure",
       "pair_examined","pair_checks","positions_scanned","cached_skips","cache_entries")
FINAL=("name","stratum","program","correct","emitted","held_matches","held_tests","first_failure",
       "pair_examined","pair_checks","extension_used")

def validation(name,teach,pair):
    checks=matches=0;failure=None
    for x in teach:
        expected=e.oracle(name,x);actual=c.eval_pair(pair,x)
        checks+=1;matches+=expected==actual
        if expected!=actual and failure is None:failure=dict(input=x,expected=expected,actual=actual)
    return checks,matches,failure

def curriculum(seed,base,public,teach,policy):
    names=list(v.CURRICULUM);random.Random(seed^0x5401).shuffle(names)
    order=list(range(len(names)));random.Random(seed^0x5402).shuffle(order)
    core=Core(base,policy)
    for i,name in enumerate(names):
        core.observe(i,tuple((x,e.oracle(name,x)) for x in public))
    records=[]
    for step in range(previous.ATTEMPTS):
        eligible=[i for i in order if core.tasks[i].status=="deferred" and core.eligible(i)]
        i=order[step] if step<previous.COMMON else (eligible[0] if eligible else None)
        if i is None:
            records.append(dict(seed=seed,policy=policy,step=step,id=None,status="idle"))
            continue
        row=core.investigate(i,lambda p:validation(names[i],teach,p))
        records.append(dict(seed=seed,policy=policy,step=step,name=names[i],**row))
    core.freeze()
    return core,records,names

def metrics(rows):
    active=[r for r in rows if r["id"] is not None]
    accepted=sum(r["accepted"] for r in active);emitted=sum(r["emitted"] for r in active)
    keys=("pair_examined","pair_checks","positions_scanned","cached_skips","pair_wall_ns",
          "validation_checks","real_motif_evaluations","prediction_hits","prediction_misses",
          "cross_task_hits","prediction_evictions")
    return dict(attempted=len(active),idle=len(rows)-len(active),accepted=accepted,
        wrong=emitted-accepted,abstained=len(active)-emitted,
        recovered=sum(r["recovered"] for r in active),
        peak_prediction_entries=max((r["prediction_entries"] for r in active),default=0),
        peak_prediction_storage_bytes=max((r["prediction_storage_bytes"] for r in active),default=0),
        peak_negative_storage_bytes=max((r["cache_storage_checkpoint_bytes"] for r in active),default=0),
        **{k:sum(r[k] for r in active) for k in keys})

def signature(rows,fields):
    return [tuple(r.get(k) for k in fields) for r in rows]

def write(path,value):
    path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    result=[];training=[];final=[];comparisons=[];base_rows=[];menus=[]
    for seed in (REGRESSION,*SEEDS):
        parts=h.inputs(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        write(out/f"inputs_{seed}.json",dict(zip(
            ("initial","pool","challenge","base_teach","curriculum_public","curriculum_teach","final_public","held"),parts)))
        base,learned=h.acquire_base(seed,initial,pool,ch,teach);base_rows.extend(learned)
        base,base_sha=c.freeze(out/f"base_{seed}.json",base)
        cores={};rows_by_policy={};final_by_policy={};snapshots={}
        for policy in POLICIES:
            core,records,names=curriculum(seed,base,pub2,teach2,policy)
            cores[policy]=core;rows_by_policy[policy]=records;training.extend(records)
            snapshots[policy]=core.snapshot()
            write(out/f"state_{seed}_{policy}.json",snapshots[policy])
            final_by_policy[policy]=[]
        menus.append(dict(seed=seed,id_to_target=names,base_sha=base_sha))
        for stratum,names in v.GROUPS:
            for name in names:
                examples=tuple((x,v.oracle(name,x)) for x in public)
                single,prep=f.search(examples,True,True,(),1)
                for policy,core in cores.items():
                    lib=core.library
                    if single:
                        program=("single",single[0]);stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
                    else:
                        pair,stats=e.pair_search(examples,lib)
                        program=("pair",pair) if pair else None
                    used=bool(program and program[0]=="pair" and any(p in lib and p not in base for p in program[1]))
                    row=dict(seed=seed,policy=policy,stratum=stratum,name=name,
                        **v.score(program,name,held),**stats,extension_used=used,
                        single_examined=prep["examined"],single_checks=prep["checks"],shared_single_ns=prep["wall_ns"])
                    final_by_policy[policy].append(row);final.append(row)
        for policy,core in cores.items():
            if snapshots[policy]!=core.snapshot():raise RuntimeError("final state changed")
            same=dict(training=signature(rows_by_policy[policy],LOGIC)==signature(rows_by_policy["direct"],LOGIC),
                final=signature(final_by_policy[policy],FINAL)==signature(final_by_policy["direct"],FINAL),
                library=core.library==cores["direct"].library,
                cache_bound=len(core.prediction.store)<=POLICIES[policy][1])
            comparisons.append(dict(seed=seed,policy=policy,**same))
            result.append(dict(seed=seed,policy=policy,regression=seed==REGRESSION,
                training=metrics(rows_by_policy[policy]),final=e.metric(final_by_policy[policy])))
    historical=next(r for r in result if r["regression"] and r["policy"]=="direct")["final"]
    expected=dict(n=14,correct=12,wrong=0,abstained=2,single_examined=342629,
                  single_checks=342655,pair_examined=25403,pair_checks=25536,extension_used=9)
    regression_match=all(historical.get(k)==value for k,value in expected.items())
    equivalent=all(all(row[k] for k in ("training","final","library","cache_bound")) for row in comparisons)
    aggregate=[]
    for policy in POLICIES:
        r=[x for x in training if x["seed"] in SEEDS and x["policy"]==policy]
        q=[x for x in final if x["seed"] in SEEDS and x["policy"]==policy]
        # Checkpoint maxima must be per replica, not total across replicas.
        aggregate.append(dict(policy=policy,training=metrics(r),final=e.metric(q)))
    summary=dict(protocol=PROTOCOL,seeds=SEEDS,regression_seed=REGRESSION,
        historical_expected=expected,regression_match=regression_match,
        equivalent=equivalent,experiment_passed=equivalent and regression_match,
        comparisons=comparisons,by_seed=result,aggregate_new_seeds=aggregate,menus=menus,
        memory_measurement="Attributed shallow cache storage, not RSS or byte-budget enforcement")
    for name,records in (("base_acquisition",base_rows),("curriculum",training),("final",final)):
        (out/(name+".jsonl")).write_text("".join(m.enc(r)+"\n" for r in records),encoding="utf-8")
    write(out/"summary.json",summary)
    print(json.dumps(dict(experiment_passed=summary["experiment_passed"],aggregate=aggregate),indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_observation_and_freeze(self):
        core=Core((),"motif_1024");a=(((1,2),(2,1)),)
        core.observe(1,a);core.observe(1,a)
        with self.assertRaises(ValueError):core.observe(1,(((1,2),(1,2)),))
        core.freeze()
        with self.assertRaises(RuntimeError):core.observe(2,a)
        with self.assertRaises(RuntimeError):core.investigate(1,lambda p:(1,1,None))
    def test_state_and_context(self):
        core=Core((),"direct");a=(((1,2),(2,1)),)
        core.observe(1,a);core.observe(2,a);core.observe(3,a)
        with patch.object(previous,"search",return_value=(None,{})):
            row=core.investigate(1,lambda p:self.fail("no candidate"))
        self.assertEqual(row["status"],"deferred")
        self.assertFalse(core.eligible(1))
        pair=(c.MOTIFS[0],c.MOTIFS[1])
        with patch.object(previous,"search",return_value=(pair,{})):
            row=core.investigate(2,lambda p:(2,1,dict(input=(1,),expected=(2,),actual=(1,))))
            self.assertEqual(row["status"],"rejected")
            self.assertEqual(core.library,())
            row=core.investigate(3,lambda p:(2,2,None))
            self.assertTrue(row["accepted"])
        self.assertTrue(core.eligible(1))
        self.assertFalse(core.eligible(2))
        self.assertTrue(all(not p["individually_verified"] for p in row["provenance"]))
        self.assertIn(1,core.negative)
        self.assertNotIn(2,core.negative)
    def test_cache_capacity(self):
        for policy in POLICIES:
            core=Core((),policy);cache=core.prediction
            for i in range(1200):
                p=(c.MOTIFS[0],c.MOTIFS[1]);x=(i,1)
                self.assertEqual(cache.pair(p,x,i),c.eval_pair(p,x))
            self.assertLessEqual(len(cache.store),POLICIES[policy][1])

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--output",type=Path);args=parser.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None:parser.error("--output required")
    out=args.output.resolve()
    if ROOT not in out.parents:parser.error("new output directory inside NUCLEO_V55 required")
    run(out)

if __name__=="__main__":main()
