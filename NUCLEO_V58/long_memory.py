"""Portable knowledge priorities; no task-local negative or prediction cache."""
import argparse,json,random,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V56"))
from restart_experiment import setup,advance,write,Core,previous,v,e,h,c,f,m
from checkpoint import canonical,digest,fingerprint,tup
SEEDS=(7620017,7650023,7680031,7710041)
MODES=("base","learned","random")

def export(path,base,core):
    payload=dict(schema=1,fingerprint=fingerprint(),base=base,library=core.library,
        verified=[dict(context=x["context"],pair=x["pair"],checks=x["validation_checks"],
                       matches=x["validation_matches"],added=x["added"],provenance=x["provenance"])
                  for x in core.events if x["accepted"]])
    with path.open("xb") as fp:fp.write(canonical(dict(payload=payload,sha256=digest(payload))))

def load(path):
    with path.open("rb") as fp:raw=fp.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError("memory too large")
    envelope=json.loads(raw);p=envelope["payload"]
    if envelope["sha256"]!=digest(p) or p["schema"]!=1 or p["fingerprint"]!=fingerprint():raise ValueError("memory integrity")
    base=tup(p["base"]);lib=tup(p["library"]);current,_=v.extend(base,None,False)
    for row in p["verified"]:
        if not isinstance(row["checks"],int) or row["checks"]<=0 or row["checks"]!=row["matches"]:raise ValueError("validation")
        pair=tup(row["pair"]);current,added=v.extend(current,pair,True)
        if added!=tup(row["added"]):raise ValueError("provenance mismatch")
        if len(row["provenance"])!=len(added):raise ValueError("provenance count")
        for item,motif in zip(row["provenance"],added):
            if tup(item["motif"])!=motif or item["individually_verified"] is not False or item["source_pair_sha"]!=m.digest(pair):raise ValueError("provenance")
    if current!=lib:raise ValueError("library mismatch")
    return base,lib

def evaluate(seed,path,out):
    base,lib=load(path)
    choices=[p for p in c.MOTIFS if p not in base]
    random.Random(seed^0x5801).shuffle(choices)
    libraries={"base":base,"learned":lib,"random":base+tuple(choices[:len(lib)-len(base)])}
    public,held=h.inputs(seed+1000003)[-2:]
    rows=[]
    for name in v.GROUPS[0][1]:
        examples=tuple((x,v.oracle(name,x)) for x in public)
        single,prep=f.search(examples,True,True,(),1)
        for mode,library in libraries.items():
            if single:program=("single",single[0]);stats=dict(pair_examined=0,pair_checks=0,pair_wall_ns=0,source="single")
            else:
                pair,stats=e.pair_search(examples,library);program=("pair",pair) if pair else None
            used=bool(program and program[0]=="pair" and any(p in library and p not in base for p in program[1]))
            rows.append(dict(mode=mode,name=name,stratum="new",**v.score(program,name,held),**stats,
                extension_used=used,single_examined=prep["examined"],single_checks=prep["checks"],shared_single_ns=prep["wall_ns"]))
    write(out,dict(seed=seed,test_seed=seed+1000003,library_sizes={k:len(o) for k,o in libraries.items()},
        library_sha={k:m.digest(o) for k,o in libraries.items()},rows=rows,
        results=[dict(mode=mode,**e.metric([x for x in rows if x["mode"]==mode])) for mode in MODES]))

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        parts,names,order=setup(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        base,acquired=h.acquire_base(seed,initial,pool,ch,teach)
        core=Core(base,"motif_8192")
        for i,name in enumerate(names):core.observe(i,tuple((x,e.oracle(name,x)) for x in pub2))
        rows=advance(core,seed,names,order,teach2,0,previous.ATTEMPTS);core.freeze()
        path=out/f"knowledge_{seed}.json";export(path,base,core)
        target=out/f"transfer_{seed}.json"
        subprocess.run([sys.executable,str(Path(__file__).resolve()),"--worker",str(seed),str(path),str(target)],check=True,timeout=90)
        a=json.loads(target.read_bytes());a["memory_bytes"]=path.stat().st_size;results.append(a)
        write(out/f"acquisition_{seed}.json",dict(base=acquired,rows=rows))
    aggregate=[]
    for mode in MODES:
        data=[x for r in results for x in r["results"] if x["mode"]==mode]
        aggregate.append(dict(mode=mode,**{k:sum(x[k] for x in data) for k in ("n","correct","wrong","abstained","pair_examined","pair_checks")}))
    write(out/"summary.json",dict(protocol="V58-portable-knowledge-v1",aggregate=aggregate,
        memory_bytes=[r["memory_bytes"] for r in results],by_seed=[{k:v for k,v in r.items() if k!="rows"} for r in results]))
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_roundtrip(self):
        core=Core((),"motif_8192")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"k.json";export(p,(),core);self.assertEqual(load(p),((),()))
            with self.assertRaises(FileExistsError):export(p,(),core)
            a=json.loads(p.read_bytes());a["payload"]["schema"]=2;p.write_bytes(canonical(a))
            with self.assertRaises(ValueError):load(p)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--worker",nargs=3);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.worker:
        seed,path,out=a.worker
        if int(seed) not in SEEDS:p.error("seed")
        evaluate(int(seed),Path(path),Path(out));return
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V58 required")
    run(a.output.resolve())
if __name__=="__main__":main()
