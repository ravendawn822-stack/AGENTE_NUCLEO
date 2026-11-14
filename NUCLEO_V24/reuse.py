"""V24: verified reusable subprograms in finite list DSL."""
import argparse,hashlib,itertools,json,random,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V23"))
import synthesis as v
SEEDS=(3600017,3630023,3660031,3690041)
POLICIES=("fixed2","memory","full3")
STRATA=("linked3","new3","new2","outside4")
FULL3=(*v.FULL,*itertools.product(v.OPS,repeat=3))

def enc(x):return json.dumps(x,separators=(",",":"),sort_keys=True)
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def execute_target(program,x):
    assert len(program)<=4
    for op in program:x=v.execute((op,),x)
    return x

def sig(program,points):
    return tuple(execute_target(program,x) for x in points)

def compose(parts):
    return tuple(sorted({p for m in parts for op in v.OPS for p in ((op,*m),(*m,op))},key=lambda x:(len(x),x)))

def suite(seed,points):
    rng=random.Random(seed^0x2411)
    signatures={p:sig(p,points) for p in FULL3}
    small={signatures[p] for p in v.SMALL}
    full2={signatures[p] for p in v.FULL}
    full3=set(signatures.values())
    seen=set();train=[];final=[]
    def add(programs,n,dest,stratum,excluded):
        programs=list(programs);rng.shuffle(programs);count=0
        for p in programs:
            s=signatures[p] if p in signatures else sig(p,points)
            if s in seen or s in excluded:continue
            seen.add(s);dest.append(dict(id=f"{seed}/{stratum}/{count}",stratum=stratum,program=p))
            count+=1
            if count==n:break
        assert count==n,(seed,stratum,count)
    add(v.FULL[len(v.SMALL):],12,train,"train",small)
    linked=compose([t["program"] for t in train])
    linked_signatures={signatures[p] for p in linked}
    add(linked,12,final,"linked3",full2)
    add(FULL3[len(v.FULL):],12,final,"new3",full2|linked_signatures)
    add(v.FULL[len(v.SMALL):],8,final,"new2",small)
    add(itertools.product(v.OPS,repeat=4),4,final,"outside4",full3)
    rng.shuffle(train);rng.shuffle(final)
    return train,final

class Memory:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS skills(program TEXT PRIMARY KEY, origin TEXT NOT NULL, sha TEXT NOT NULL)")
        self.db.commit()
    def add(self,p,origin):
        if len(p)!=2 or p not in v.FULL:return False
        s=enc(p)
        cur=self.db.execute("INSERT OR IGNORE INTO skills VALUES(?,?,?)",(s,origin,digest([s,origin])))
        self.db.commit();return cur.rowcount==1
    def snapshot(self):
        out=[]
        for s,o,h in self.db.execute("SELECT program,origin,sha FROM skills ORDER BY program"):
            assert digest([s,o])==h
            p=tuple(json.loads(s));assert len(p)==2 and p in v.FULL
            out.append(p)
        return tuple(out)
    def close(self):self.db.close()

def episode(t,initial,pool,held,prepared,seed,policy):
    target=t["program"];observed=sig(target,initial)
    start=time.perf_counter_ns()
    p,trace,cost,n=v.investigate(observed,pool,lambda x:execute_target(target,x),"full_active",prepared,seed)
    elapsed=time.perf_counter_ns()-start
    ok=p is not None and sig(p,held)==sig(target,held)
    return dict(task=t,policy=policy,program=p,success=ok,emitted=p is not None,
        trace=trace,queries=len(trace),comparisons=cost,remaining=n,wall_ns=elapsed,
        initial=list(zip(initial,observed)))

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];preparation=[];snapshots=[]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed)
        train,final=suite(seed,(*initial,*pool,*held))
        def prepare(grammar,policy):
            start=time.perf_counter_ns();pr,cost=v.prepare(grammar,initial,pool)
            preparation.append(dict(seed=seed,policy=policy,programs=len(grammar),classes=len(pr),
                program_executions=cost,wall_ns=time.perf_counter_ns()-start))
            return pr
        base=prepare(v.FULL,"fixed2")
        path=out/f"{seed}.sqlite3";store=Memory(path)
        for i,t in enumerate(train):
            row=episode(t,initial,pool,held,base,seed+i*701,"train")
            added=row["success"] and store.add(row["program"],t["id"])
            training.append(dict(seed=seed,added=added,**row))
        learned=store.snapshot();store.close();store=Memory(path)
        assert store.snapshot()==learned
        macros=compose(learned)
        snapshots.append(dict(seed=seed,skills=len(learned),sha=digest(learned),programs=learned,compositions=len(macros)))
        prepared={"fixed2":base,"memory":prepare((*v.FULL,*macros),"memory"),"full3":prepare(FULL3,"full3")}
        for i,t in enumerate(final):
            for p in POLICIES:
                rows.append(dict(seed=seed,**episode(t,initial,pool,held,prepared[p],seed+i*971,p)))
        assert store.snapshot()==learned;store.close()
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
            queries=sum(r["queries"] for r in rr),comparisons=sum(r["comparisons"] for r in rr),
            wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V24-subprogram-memory-v1",seeds=SEEDS,snapshots=snapshots,preparation=preparation,
        training=dict(**metric(training),added=sum(r["added"] for r in training)),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in STRATA for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for r in data:f.write(enc(r)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            a,b,c=v.input_sets(s);points=(*a,*b,*c)
            train,final=suite(s,points)
            self.assertEqual((len(train),len(final)),(12,36))
            self.assertEqual(len({sig(t["program"],points) for t in train+final}),48)
    def test_compose(self):
        m=("positive","sort");p=compose([m])
        self.assertIn(("neg",*m),p)
        self.assertIn((*m,"unique"),p)
        self.assertTrue(set(p)<=set(FULL3))
    def test_memory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"skills.db";m=Memory(p)
            self.assertTrue(m.add(("positive","sort"),"test"))
            self.assertFalse(m.add(("positive","sort"),"repeat"))
            self.assertFalse(m.add(("abs",),"invalid"))
            m.close();m=Memory(p)
            self.assertEqual(m.snapshot(),(("positive","sort"),));m.close()
    def test_bounds(self):
        self.assertEqual(execute_target(("inc",)*4,(1,)),(5,))
        a,b,c=v.input_sets(SEEDS[0])
        prepared,_=v.prepare(v.FULL,a,b)
        t=dict(program=("positive","sort"))
        row=episode(t,a,b,c,prepared,1,"fixed2")
        self.assertLessEqual(row["queries"],v.CAP)
        self.assertFalse(set(r["input"] for r in row["trace"])&set(c))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V24 required")
    run(z.output)
