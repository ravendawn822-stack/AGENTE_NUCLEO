"""Combined local session; evaluator supplies all observations and goals."""
import argparse,hashlib,json,random,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V62"))
import revision as env
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V56"))
import restart_experiment as mathlab
from checkpoint import canonical,digest,capture,read_checkpoint,write_checkpoint
SEEDS=tuple(8300017+30001*i for i in range(4))
CUT=7
CAP=mathlab.previous.ATTEMPTS

class Session:
    def __init__(self,core,environment=None,cursor=0):
        self.core=core;self.environment=environment or env.Revised("repair");self.cursor=cursor
    def observe(self,a,s,t):
        self.environment.observe(a,s,t)
    def investigate(self,task,validator):
        return self.core.investigate(task,validator)
    def plan(self,s,t):
        return env.path_to(self.environment.graph(),s,lambda x:x==t)
    def save(self,folder):
        folder.mkdir(exist_ok=False)
        mathfile=folder/"math.json"
        write_checkpoint(mathfile,self.core,self.cursor)
        payload=dict(schema=1,cursor=self.cursor,environment=self.environment.state(),
            math_sha=hashlib.sha256(mathfile.read_bytes()).hexdigest())
        with (folder/"session.json").open("xb") as fp:fp.write(canonical(dict(payload=payload,sha256=digest(payload))))
    @classmethod
    def restore(cls,folder):
        with (folder/"session.json").open("rb") as fp:raw=fp.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError("session size")
        a=json.loads(raw);p=a["payload"]
        if a["sha256"]!=digest(p) or p["schema"]!=1:raise ValueError("session integrity")
        mathfile=folder/"math.json"
        with mathfile.open("rb") as fp:raw=fp.read(32*1024*1024+1)
        if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=p["math_sha"]:raise ValueError("math binding")
        core,cursor=read_checkpoint(mathfile)
        memory=env.Revised.restore(p["environment"])
        if (cursor!=p["cursor"] or memory.mode!="repair" or
            canonical(memory.state())!=canonical(p["environment"])):raise ValueError("session mismatch")
        expected=min(cursor,5)+max(0,min(cursor-7,5))
        if any(len(memory.observed[a])!=expected for a in env.ACTIONS):raise ValueError("environment cursor")
        return cls(core,memory,cursor)

def setup(seed):
    parts,names,order=mathlab.setup(seed)
    table,_,_=env.world(seed^0x6401,1)
    goals=random.Random(seed^0x6402).sample([(s,t) for s in range(env.N) for t in range(env.N) if s!=t],12)
    return parts,names,order,table,goals

def advance(session,seed,parts,names,order,table,stop):
    rows=[]
    while session.cursor<stop:
        step=session.cursor
        # Alternate a bounded environmental observation round with a math attempt.
        index=step if step<5 else (step-2 if 7<=step<12 else None)
        if index is not None:
            for a in env.ACTIONS:
                s=env.order(seed,a)[index];session.observe(a,s,table[s,a])
        eligible=[i for i in order if session.core.tasks[i].status=="deferred" and session.core.eligible(i)]
        i=order[step] if step<mathlab.previous.COMMON else (eligible[0] if eligible else None)
        if i is None:rows.append(dict(seed=seed,step=step,id=None,status="idle"))
        else:
            row=session.investigate(i,lambda p:mathlab.validation(names[i],parts[5],p))
            rows.append(dict(seed=seed,step=step,name=names[i],**row))
        session.cursor+=1
    return rows

def final(session,base,parts,table,goals):
    mathrows=mathlab.score(session.core,base,parts[6],parts[7])
    held={(s,a) for a in env.ACTIONS for s in range(env.N) if s not in session.environment.observed[a]}
    em,er=env.evaluate(session.environment,table,held)
    pm,pr=env.plans(session.environment,table,goals)
    chosen=[session.plan(s,t) for s,t in goals]
    if canonical(chosen)!=canonical([x["route"] for x in pr]):raise RuntimeError("session planner mismatch")
    return dict(math=mathlab.e.metric(mathrows),math_rows=mathlab.signature(mathrows,mathlab.FINAL),
                environment=em,environment_rows=er,plans=pm,plan_rows=pr)

def worker(seed,folder,out,basefile):
    parts,names,order,table,goals=setup(seed)
    session=Session.restore(folder);start=digest(capture(session.core,session.cursor))
    base=tuple(tuple(x) for x in json.loads(basefile.read_bytes()))
    rows=advance(session,seed,parts,names,order,table,CAP)
    state=capture(session.core,CAP);result=final(session,base,parts,table,goals)
    env.write(out,dict(start=start,rows=rows,state=state,environment=session.environment.state(),result=result))

def run(out):
    out.mkdir(parents=True,exist_ok=False);records=[]
    for seed in SEEDS:
        parts,names,order,table,goals=setup(seed)
        initial,pool,ch,teach,pub2,teach2,public,held=parts
        base,learned=mathlab.h.acquire_base(seed,initial,pool,ch,teach)
        core=mathlab.Core(base,"motif_8192")
        for i,name in enumerate(names):core.observe(i,tuple((x,mathlab.e.oracle(name,x)) for x in pub2))
        s=Session(core);prefix=advance(s,seed,parts,names,order,table,CUT)
        folder=out/f"checkpoint_{seed}";s.save(folder)
        basefile=out/f"base_{seed}.json";env.write(basefile,base)
        start=digest(capture(core,CUT))
        rows=advance(s,seed,parts,names,order,table,CAP)
        state=capture(core,CAP);result=final(s,base,parts,table,goals)
        child=out/f"resume_{seed}.json"
        subprocess.run([sys.executable,str(Path(__file__).resolve()),"--worker",str(seed),str(folder),str(child),str(basefile)],check=True,timeout=90)
        a=json.loads(child.read_bytes())
        checks=dict(start=start==a["start"],
            trajectory=canonical(mathlab.signature(rows,mathlab.LOGIC))==canonical(mathlab.signature(a["rows"],mathlab.LOGIC)),
            math_state=all(canonical(state[k])==canonical(a["state"][k]) for k in ("library","tasks","negative","predictions","stats","cursor")),
            environment=canonical(s.environment.state())==canonical(a["environment"]),
            final=all(canonical(result[k])==canonical(a["result"][k]) for k in ("math_rows","environment","environment_rows","plans","plan_rows")))
        record=dict(seed=seed,checks=checks,passed=all(checks.values()),math=result["math"],environment=result["environment"],plans=result["plans"],
            checkpoint_bytes=sum(p.stat().st_size for p in folder.iterdir()))
        records.append(record)
        env.write(out/f"continuous_{seed}.json",dict(record=record,prefix=prefix,rows=rows,state=state,environment=s.environment.state(),result=result,base_acquisition=learned))
    summary=dict(protocol="V64-integrated-session-v1",experiment_passed=all(r["passed"] for r in records),by_seed=records,
        aggregate={key:{k:sum(r[key][k] for r in records) for k in keys} for key,keys in
            (("math",("n","correct","wrong","abstained")),("environment",("n","correct","wrong","abstained")),("plans",("n","success","wrong","abstained")))})
    env.write(out/"summary.json",summary);print(json.dumps(summary["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_restore(self):
        core=mathlab.Core((),"motif_8192")
        s=Session(core)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"case";s.save(p);other=Session.restore(p)
            self.assertEqual(canonical(s.environment.state()),canonical(other.environment.state()))
            a=json.loads((p/"session.json").read_bytes());a["payload"]["cursor"]=1
            (p/"session.json").write_bytes(canonical(a))
            with self.assertRaises(ValueError):Session.restore(p)
    def test_plan(self):
        s=Session(mathlab.Core((),"motif_8192"));s.observe(0,0,1)
        self.assertEqual(s.plan(0,1),(0,));self.assertIsNone(s.plan(0,2))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--worker",nargs=4);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.worker:
        seed,folder,out,base=a.worker
        if int(seed) not in SEEDS:p.error("seed")
        worker(int(seed),Path(folder),Path(out),Path(base));return
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V64 required")
    run(a.output.resolve())
if __name__=="__main__":main()
