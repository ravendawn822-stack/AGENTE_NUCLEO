"""V26: progressive acquisition of reusable subprograms in a bounded pure DSL."""
import argparse,itertools,json,random,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V24"))
import reuse as m
v=m.v
SEEDS=(3840017,3870023,3900031,3930041)
POLICIES=("full3","frozen","progressive","random_macros","full4")
STRATA=("linked3","new3","linked4","new4")
FULL4=(*m.FULL3,*itertools.product(v.OPS,repeat=4))

def suite(seed,points):
    rng=random.Random(seed^0x2617);cache={};seen=set();train=[];final=[]
    def sig(p):
        if p not in cache:cache[p]=m.sig(p,points)
        return cache[p]
    base2={sig(p) for p in v.FULL}
    base3={sig(p) for p in m.FULL3}
    def add(programs,n,dest,stratum,exclude):
        options=list(programs);rng.shuffle(options);count=0
        for p in options:
            s=sig(p)
            if s in seen or s in exclude:continue
            seen.add(s)
            dest.append(dict(id=f"{seed}/{stratum}/{count}",stratum=stratum,program=p))
            count+=1
            if count==n:break
        assert count==n,(seed,stratum,count)
    add(v.FULL[len(v.SMALL):],8,train,"train2",{sig(p) for p in v.SMALL})
    linked3=m.compose([t["program"] for t in train])
    add(linked3,8,train,"train3",base2)
    linked4=m.compose([t["program"] for t in train if t["stratum"]=="train3"])
    add(linked3,8,final,"linked3",base2)
    add(m.FULL3[len(v.FULL):],8,final,"new3",base2|{sig(p) for p in linked3})
    add(linked4,8,final,"linked4",base3)
    add(FULL4[len(m.FULL3):],8,final,"new4",base3|{sig(p) for p in linked4})
    rng.shuffle(final)
    return train,final

class Memory:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS skills(program TEXT PRIMARY KEY, origin TEXT NOT NULL, sha TEXT NOT NULL)")
        self.db.commit()
    def add(self,p,origin):
        p=tuple(p)
        if len(p) not in (2,3) or p not in m.FULL3:return False
        s=m.enc(p)
        cur=self.db.execute("INSERT OR IGNORE INTO skills VALUES(?,?,?)",(s,origin,m.digest([s,origin])))
        self.db.commit();return cur.rowcount==1
    def snapshot(self):
        out=[]
        for s,o,h in self.db.execute("SELECT program,origin,sha FROM skills ORDER BY program"):
            assert m.digest([s,o])==h
            p=tuple(json.loads(s));assert len(p) in (2,3) and p in m.FULL3
            out.append(p)
        return tuple(out)
    def close(self):self.db.close()

def grammar(parts):
    return tuple(sorted(set(v.FULL)|set(m.compose(parts)),key=lambda p:(len(p),p)))

def prepare(programs,initial,pool):
    points=(*initial,*pool);groups={}
    for p in sorted(programs,key=lambda p:(len(p),p)):
        signature=m.sig(p,points)
        groups.setdefault(signature,p)
    return tuple((p,sig) for sig,p in groups.items()),len(programs)*len(points)

def episode(t,initial,pool,held,prepared,seed,policy):
    target=t["program"];observed=m.sig(target,initial)
    start=time.perf_counter_ns()
    p,trace,cost,n=v.investigate(observed,pool,lambda x:m.execute_target(target,x),"full_active",prepared,seed)
    elapsed=time.perf_counter_ns()-start
    ok=p is not None and m.sig(p,held)==m.sig(target,held)
    return dict(task=t,policy=policy,program=p,success=ok,emitted=p is not None,
        trace=trace,queries=len(trace),comparisons=cost,remaining=n,wall_ns=elapsed,
        initial=list(zip(initial,observed)))

def metric(rr):
    ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
    return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
                **{k:sum(r[k] for r in rr) for k in ("queries","comparisons","wall_ns")})

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];preparation=[];snapshots=[]
    for seed in SEEDS:
        initial,pool,held=v.input_sets(seed)
        train,final=suite(seed,(*initial,*pool,*held))
        def prep(programs,policy):
            start=time.perf_counter_ns()
            prepared,n=prepare(programs,initial,pool)
            preparation.append(dict(seed=seed,policy=policy,programs=len(programs),
                classes=len(prepared),program_executions=n,wall_ns=time.perf_counter_ns()-start))
            return prepared
        path=out/f"{seed}.sqlite3";store=Memory(path)
        train2=prep(v.FULL,"train2")
        for i,t in enumerate(train):
            if t["stratum"]=="train2":
                r=episode(t,initial,pool,held,train2,seed+i*701,"train2")
                added=r["success"] and len(r["program"])==2 and store.add(r["program"],t["id"])
                training.append(dict(seed=seed,added=added,**r))
        pairs=store.snapshot()
        train3=prep(grammar(pairs),"train3_frozen")
        for i,t in enumerate(train):
            if t["stratum"]=="train3":
                r=episode(t,initial,pool,held,train3,seed+i*701,"train3")
                added=r["success"] and len(r["program"])==3 and store.add(r["program"],t["id"])
                training.append(dict(seed=seed,added=added,**r))
        learned=store.snapshot();store.close();store=Memory(path);assert store.snapshot()==learned
        triples=tuple(p for p in learned if len(p)==3)
        choices=[p for p in m.FULL3[len(v.FULL):] if p not in triples]
        random_triples=tuple(random.Random(seed^0x2699).sample(choices,len(triples)))
        snapshots.append(dict(seed=seed,pairs=len(pairs),triples=len(triples),
            programs=learned,random_triples=random_triples,sha=m.digest(learned)))
        prepared={"full3":prep(m.FULL3,"full3"),"frozen":train3,
                  "progressive":prep(grammar(learned),"progressive"),
                  "random_macros":prep(grammar((*pairs,*random_triples)),"random_macros"),
                  "full4":prep(FULL4,"full4")}
        for i,t in enumerate(final):
            for p in POLICIES:
                rows.append(dict(seed=seed,**episode(t,initial,pool,held,prepared[p],seed+i*971,p)))
        assert store.snapshot()==learned;store.close()
    result=dict(protocol="V26-progressive-skills-v1",seeds=SEEDS,snapshots=snapshots,preparation=preparation,
        training=[dict(phase=z,**metric([r for r in training if r["policy"]==z]),
            added=sum(r["added"] for r in training if r["policy"]==z)) for z in ("train2","train3")],
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in STRATA for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    for name in ("frozen","random_macros","full4"):
        ref={(r["seed"],r["task"]["id"]):r for r in rows if r["policy"]==name}
        pp=[r for r in rows if r["policy"]=="progressive"]
        result.setdefault("paired_progressive",{})[name]=dict(
            gains=sum(r["success"] and not ref[r["seed"],r["task"]["id"]]["success"] for r in pp),
            losses=sum(not r["success"] and ref[r["seed"],r["task"]["id"]]["success"] for r in pp))
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(m.enc(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            a,b,c=v.input_sets(s);points=(*a,*b,*c)
            tr,te=suite(s,points)
            self.assertEqual((len(tr),len(te)),(16,32))
            self.assertEqual(len({m.sig(t["program"],points) for t in tr+te}),48)
    def test_grammar(self):
        p=("positive","sort","inc")
        g=grammar((p,))
        self.assertIn((*p,"reverse"),g)
        self.assertTrue(set(g)<=set(FULL4))
    def test_memory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"x.db";store=Memory(path)
            self.assertTrue(store.add(("positive","sort"),"test2"))
            self.assertTrue(store.add(("positive","sort","inc"),"test3"))
            self.assertFalse(store.add(("positive","sort","inc"),"duplicate"))
            self.assertFalse(store.add(("abs",),"bad"))
            snap=store.snapshot();store.close();store=Memory(path)
            self.assertEqual(store.snapshot(),snap);store.close()
    def test_episode(self):
        a,b,c=v.input_sets(SEEDS[0]);p=("positive","sort","inc","reverse")
        pr,_=prepare(grammar((p[:3],)),a,b)
        r=episode(dict(program=p),a,b,c,pr,1,"progressive")
        self.assertLessEqual(r["queries"],v.CAP)
        self.assertFalse(set(z["input"] for z in r["trace"])&set(c))
        if r["program"] is not None:
            self.assertTrue(all(m.execute_target(r["program"],z["input"])==z["output"] for z in r["trace"]))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V26 required")
    run(z.output)
