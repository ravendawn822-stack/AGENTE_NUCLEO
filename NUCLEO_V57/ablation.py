"""Controlled ablations of V55. Fixed offline evaluator."""
import argparse,sys,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V56"))
from restart_experiment import setup,advance,score,metrics,write,Core,previous,h,e,m
SEEDS=(7500017,7530023,7560031,7590041)
MODES=("integral","no_predictions","no_negative","frozen_library")

class Ablated(Core):
    def __init__(self,base,mode):
        super().__init__(base,"direct" if mode=="no_predictions" else "motif_8192")
        self.mode=mode
    def investigate(self,task,validate):
        if self.mode=="no_negative":self.negative.pop(task,None)
        before=self.library
        row=super().investigate(task,validate)
        if self.mode=="frozen_library":
            self.library=before
            row.update(after_sha=m.digest(before),after_size=len(before),added=(),provenance=[])
        return row

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        parts,names,order=setup(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        base,learned=h.acquire_base(seed,initial,pool,ch,teach)
        for mode in MODES:
            core=Ablated(base,mode)
            for i,name in enumerate(names):core.observe(i,tuple((x,e.oracle(name,x)) for x in pub2))
            rows=advance(core,seed,names,order,teach2,0,previous.ATTEMPTS)
            final=score(core,base,public,held)
            record=dict(seed=seed,mode=mode,training=metrics(rows),final=e.metric(final),library_size=len(core.library))
            results.append(record)
            write(out/f"{seed}_{mode}.json",dict(result=record,training=rows,final=final,base_acquisition=learned,library=core.library))
    aggregate=[]
    for mode in MODES:
        rows=[x for x in results if x["mode"]==mode]
        aggregate.append(dict(mode=mode,**{k:sum(q["final"][k] for q in rows) for k in ("n","correct","wrong","abstained")},
            **{k:sum(q["training"][k] for q in rows) for k in ("accepted","attempted","recovered","pair_examined","real_motif_evaluations","cached_skips","pair_wall_ns")},
            peak_prediction_storage_bytes=max(q["training"]["peak_prediction_storage_bytes"] for q in rows),
            peak_negative_storage_bytes=max(q["training"]["peak_negative_storage_bytes"] for q in rows)))
    write(out/"summary.json",dict(protocol="V57-ablation-v1",seeds=SEEDS,aggregate=aggregate,by_seed=results))
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_modes(self):
        for mode in MODES:
            core=Ablated((),mode)
            self.assertEqual(core.prediction.mode,"direct" if mode=="no_predictions" else "motif_lru")
            self.assertEqual(core.library,())

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V57 required")
    run(a.output.resolve())
if __name__=="__main__":main()
