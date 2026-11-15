"""Paired offline recovery experiment. Child executes only this fixed evaluator."""
import argparse,json,random,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from checkpoint import (ROOT,Core,previous,v,e,h,c,f,m,capture,canonical,
                        write_checkpoint,read_checkpoint,digest)
from experiment import validation,metrics,signature,LOGIC,FINAL,write
SEEDS=(7380017,7410023,7440031,7470041)
CUT=7
POLICY="motif_8192"
PROTOCOL="V56-checkpoint-recovery-v1"

def setup(seed):
    initial,pool,ch,teach,pub2,teach2,public,held=h.inputs(seed)
    names=list(v.CURRICULUM);random.Random(seed^0x5401).shuffle(names)
    order=list(range(len(names)));random.Random(seed^0x5402).shuffle(order)
    return (initial,pool,ch,teach,pub2,teach2,public,held),names,order

def advance(core,seed,names,order,teach,start,stop):
    records=[]
    for step in range(start,stop):
        available=[i for i in order if core.tasks[i].status=="deferred" and core.eligible(i)]
        i=order[step] if step<previous.COMMON else (available[0] if available else None)
        if i is None:records.append(dict(seed=seed,step=step,id=None,status="idle"));continue
        row=core.investigate(i,lambda p:validation(names[i],teach,p))
        records.append(dict(seed=seed,step=step,name=names[i],**row))
    return records

def clean(data):
    # Resource size and timing can vary by process; they are not logical state.
    if isinstance(data,dict):
        return {k:clean(v) for k,v in data.items() if k not in ("pair_wall_ns",
            "prediction_storage_bytes","cache_storage_checkpoint_bytes")}
    if isinstance(data,(list,tuple)):return [clean(v) for v in data]
    return data

def score(core,base,public,held):
    lib=core.freeze();before=canonical(core.snapshot());rows=[]
    for stratum,names in v.GROUPS:
        for name in names:
            examples=tuple((x,v.oracle(name,x)) for x in public)
            single,prep=f.search(examples,True,True,(),1)
            if single:
                program=("single",single[0]);stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
            else:
                pair,stats=e.pair_search(examples,lib)
                program=("pair",pair) if pair else None
            used=bool(program and program[0]=="pair" and any(p in lib and p not in base for p in program[1]))
            rows.append(dict(stratum=stratum,name=name,**v.score(program,name,held),**stats,
                extension_used=used,single_examined=prep["examined"],single_checks=prep["checks"],
                shared_single_ns=prep["wall_ns"]))
    if canonical(core.snapshot())!=before:raise RuntimeError("final memory changed")
    return rows

def worker(seed,checkpoint,out,mode):
    parts,names,order=setup(seed)
    t=time.perf_counter_ns()
    core,cursor=read_checkpoint(checkpoint,discard_predictions=mode=="cold")
    elapsed=time.perf_counter_ns()-t
    if cursor!=CUT:raise ValueError("unexpected cursor")
    restored=capture(core,cursor)
    restored_sha=digest(restored)
    rows=advance(core,seed,names,order,parts[5],cursor,previous.ATTEMPTS)
    write(out,dict(rows=rows,state=capture(core,previous.ATTEMPTS),
                   restored_sha=restored_sha,read_ns=elapsed))

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    records=[];all_passed=True
    for seed in SEEDS:
        parts,names,order=setup(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        base,learned=h.acquire_base(seed,initial,pool,ch,teach)
        core=Core(base,POLICY)
        for i,name in enumerate(names):core.observe(i,tuple((x,e.oracle(name,x)) for x in pub2))
        prefix=advance(core,seed,names,order,teach2,0,CUT)
        checkpoint=out/f"checkpoint_{seed}.json"
        t=time.perf_counter_ns();size=write_checkpoint(checkpoint,core,CUT);elapsed=time.perf_counter_ns()-t
        start=capture(core,CUT);start_sha=digest(start)
        cold_start=dict(start,predictions=[]);cold_sha=digest(cold_start)
        prefix_metrics=metrics(prefix)
        mid=dict(deferred=sum(t.status=="deferred" for t in core.tasks.values()),
                 negative_entries=sum(len(n) for n in core.negative.values()),
                 prediction_entries=len(core.prediction.store))
        suffix=advance(core,seed,names,order,teach2,CUT,previous.ATTEMPTS)
        end=capture(core,previous.ATTEMPTS)
        final=score(core,base,public,held)
        write(out/f"continuous_{seed}.json",dict(prefix=prefix,rows=suffix,state=end,final=final,base_acquisition=learned))
        seed_result=dict(seed=seed,checkpoint_bytes=size,write_ns=elapsed,
             checkpoint_state=mid,prefix=prefix_metrics,continuous=metrics(suffix),
             final=e.metric(final),resumes=[])
        for mode in ("full","cold"):
            child=out/f"resume_{mode}_{seed}.json"
            subprocess.run([sys.executable,str(Path(__file__).resolve()),"--worker",
                str(seed),str(checkpoint),str(child),mode],check=True,timeout=90)
            a=json.loads(child.read_text(encoding="utf-8"));state=a["state"]
            # Reconstruct the final library solely from the worker's output.
            restored_core=Core(tuple(tuple(p) for p in state["library"]),POLICY)
            final2=score(restored_core,base,public,held)
            # JSON normalization handles tuples versus lists.
            same_logic=canonical(signature(suffix,LOGIC))==canonical(signature(a["rows"],LOGIC))
            same_final=canonical(signature(final,FINAL))==canonical(signature(final2,FINAL))
            shared_state_keys=("schema","fingerprint","cursor","policy","library","frozen","tasks","negative")
            same_state=all(canonical(end[k])==canonical(state[k]) for k in shared_state_keys)
            same_cache=canonical(end["predictions"])==canonical(state["predictions"])
            same_stats=end["stats"]==state["stats"]
            provenance_keys=("id","context","status","pair","added","provenance","validation_checks","validation_matches","validation_failure")
            same_ledger=canonical(signature(end["events"],provenance_keys))==canonical(signature(state["events"],provenance_keys))
            same_start=a["restored_sha"]==(start_sha if mode=="full" else cold_sha)
            passed=all((same_logic,same_final,same_state,same_ledger,same_start)) and (mode!="full" or (same_cache and same_stats))
            all_passed&=passed
            seed_result["resumes"].append(dict(mode=mode,passed=passed,start_exact=same_start,
                logical=same_logic,final=same_final,state=same_state,ledger=same_ledger,
                cache=same_cache,stats=same_stats,read_ns=a["read_ns"],suffix=metrics(a["rows"]),
                final_metrics=e.metric(final2)))
            write(out/f"final_{mode}_{seed}.json",final2)
        records.append(seed_result)
    summary=dict(protocol=PROTOCOL,seeds=SEEDS,cut=CUT,policy=POLICY,
        experiment_passed=all_passed,by_seed=records,
        aggregate=dict(checkpoint_bytes=sum(r["checkpoint_bytes"] for r in records),
            continuous_evals=sum(r["continuous"]["real_motif_evaluations"] for r in records),
            full_evals=sum(r["resumes"][0]["suffix"]["real_motif_evaluations"] for r in records),
            cold_evals=sum(r["resumes"][1]["suffix"]["real_motif_evaluations"] for r in records),
            correct=sum(r["final"]["correct"] for r in records),
            wrong=sum(r["final"]["wrong"] for r in records),
            abstained=sum(r["final"]["abstained"] for r in records)))
    write(out/"summary.json",summary);print(json.dumps(summary["aggregate"],indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_roundtrip(self):
        core=Core((),POLICY);core.observe(0,(((1,2),(3,)),))
        t=core.tasks[0];t.status="deferred";t.last_sha=m.digest(core.library);t.attempts=1
        core.events=[dict(id=0,status="deferred")]
        neg=previous.NegativeMemory(t.examples,"paged");neg.remember(1);neg.remember(previous.UNIVERSE-1);core.negative[0]=neg
        p=c.MOTIFS[0];q=c.MOTIFS[1]
        core.prediction.lookup((p,(1,)),0,lambda:None)
        core.prediction.lookup((q,(2,)),0,lambda:(2,))
        core.prediction.lookup((p,(1,)),0,lambda:self.fail("cache miss"))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"state.json";write_checkpoint(path,core,1)
            other,cursor=read_checkpoint(path);self.assertEqual(cursor,1)
            self.assertEqual(canonical(capture(core,1)),canonical(capture(other,1)))
            self.assertIn(previous.UNIVERSE-1,other.negative[0])
            self.assertEqual(list(other.prediction.store),list(core.prediction.store))
            self.assertIsNone(other.prediction.store[(p,(1,))][0])
            cold,_=read_checkpoint(path,True);self.assertFalse(cold.prediction.store)
            self.assertEqual(cold.prediction.stats,other.prediction.stats)
            with self.assertRaises(FileExistsError):write_checkpoint(path,core,1)
            envelope=json.loads(path.read_bytes());envelope["payload"]["cursor"]=2
            path.write_bytes(canonical(envelope))
            with self.assertRaises(ValueError):read_checkpoint(path)
            envelope["payload"]["schema"]=-1;envelope["sha256"]=digest(envelope["payload"])
            path.write_bytes(canonical(envelope))
            with self.assertRaises(ValueError):read_checkpoint(path)
    def test_frozen(self):
        core=Core((),POLICY);core.freeze()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"state.json";write_checkpoint(path,core,0)
            other,_=read_checkpoint(path)
            with self.assertRaises(RuntimeError):other.observe(1,(((1,),(1,)),))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true")
    p.add_argument("--output",type=Path);p.add_argument("--worker",nargs=4);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.worker:
        seed,path,out,mode=a.worker
        if int(seed) not in SEEDS or mode not in ("full","cold"):p.error("invalid worker")
        worker(int(seed),Path(path),Path(out),mode);return
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V56 required")
    run(a.output.resolve())

if __name__=="__main__":main()
