"""V21: persistent verified mathematical structures, frozen transfer evaluation."""
import argparse,hashlib,json,random,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V20"))
import expansion as e
v=e.v
SEEDS=(3240017,3270023,3300031,3330041)
POLICIES=("expand","large","memory_expand","memory_only")
STRATA=("seen_structure","new_structure","simple","interaction")
def encode(x):return json.dumps(x,separators=(",",":"),sort_keys=True)
def digest(x):return hashlib.sha256(encode(x).encode()).hexdigest()
def freeze(x):return tuple(freeze(y) for y in x) if isinstance(x,list) else x

def suite(seed):
    rng=random.Random(seed);train=[];final=[]
    used={}
    def add(dest,parts,family,stratum):
        key=(family,parts)
        coefs=tuple(rng.choice((-3,-2,-1,1,2,3)) for _ in range(3))
        while coefs in used.setdefault(key,set()):
            coefs=tuple(rng.choice((-3,-2,-1,1,2,3)) for _ in range(3))
        used[key].add(coefs)
        dest.append(dict(id=f"{seed}/{'train' if dest is train else 'final'}/{len(dest)}",
                         family=family,parts=parts,coefs=coefs,stratum=stratum))
    for family,options in (("quadratic",[(h,) for h in v.HINGES]),
                           ("double",[(a,b) for a in v.HINGES for b in v.HINGES if a[0]==0 and b[0]==1])):
        rng.shuffle(options)
        for p in options[:6]:
            add(train,p,family,"train")
            add(final,p,family,"seen_structure")
        for p in options[6:12]:add(final,p,family,"new_structure")
    for i in range(8):
        add(final,() if i<2 else (rng.choice(v.HINGES),),"linear" if i<2 else "single","simple")
    for i in range(4):
        p=(rng.choice([h for h in v.HINGES if h[0]==0]),rng.choice([h for h in v.HINGES if h[0]==1]))
        add(final,p,"interaction","interaction")
    rng.shuffle(train);rng.shuffle(final)
    return train,final

class Memory:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS skills(parts TEXT PRIMARY KEY,origin TEXT NOT NULL,sha TEXT NOT NULL)")
        self.db.commit()
    def add(self,parts,origin):
        if parts not in e.LARGE or parts in e.SMALL:return False
        s=encode(parts)
        cur=self.db.execute("INSERT OR IGNORE INTO skills VALUES(?,?,?)",(s,origin,digest([s,origin])))
        self.db.commit()
        return cur.rowcount==1
    def snapshot(self):
        out=[]
        for s,o,h in self.db.execute("SELECT parts,origin,sha FROM skills ORDER BY parts"):
            assert digest([s,o])==h
            parts=freeze(json.loads(s));assert parts in e.LARGE and parts not in e.SMALL
            out.append(parts)
        return tuple(out)
    def close(self):self.db.close()

def investigate(observed,ask,policy,learned=()):
    obs=dict(observed);trace=[];cost=0;expanded=False
    coefs=(obs[(1,0)]-obs[(0,0)],obs[(0,1)]-obs[(0,0)],obs[(0,0)])
    def filtered(hypotheses,evidence):
        nonlocal cost
        out=[]
        for h in hypotheses:
            for p,y in evidence.items():
                cost+=1
                if e.value(h,p)!=y:break
            else:out.append(h)
        return out
    def new_set(parts):return filtered(((coefs,h) for h in parts),obs)
    initial=e.LARGE if policy=="large" else tuple(dict.fromkeys((*e.SMALL,*learned))) if policy.startswith("memory") else e.SMALL
    candidates=new_set(initial);remaining=list(e.POOL)
    for i in range(e.CAP+1):
        if not candidates and policy in ("expand","memory_expand") and not expanded:
            candidates=new_set(e.LARGE);expanded=True
        if not candidates or i==e.CAP:break
        if len(candidates)>1:
            best=-1;point=None
            for p in remaining:
                groups={}
                for h in candidates:
                    pred=e.value(h,p);groups[pred]=groups.get(pred,0)+1;cost+=1
                score=len(candidates)**2-sum(n*n for n in groups.values())
                if score>best:best,point=score,p
            phase="identify"
        else:
            point=e.verify_point(remaining,trace);phase="refute"
        remaining.remove(point);response=ask(point);obs[point]=response
        before=len(candidates);candidates=filtered(candidates,{point:response})
        trace.append(dict(point=point,response=response,phase=phase,before=before,after=len(candidates)))
    candidate=candidates[0] if len(candidates)==1 else None
    return candidate,trace,cost,expanded,len(candidates)

def episode(t,policy,learned=()):
    obs={p:e.target(t,p) for p in v.INITIAL}
    start=time.perf_counter_ns()
    h,trace,cost,expanded,n=investigate(obs,lambda p:e.target(t,p),policy,learned)
    elapsed=time.perf_counter_ns()-start
    ok=h is not None and all(e.value(h,p)==e.target(t,p) for p in e.RESERVED)
    return dict(task=t,policy=policy,candidate=h,emitted=h is not None,success=ok,
                trace=trace,queries=len(trace),expanded=expanded,remaining=n,
                hypothesis_evaluations=cost,wall_ns=elapsed)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];snapshots=[]
    for seed in SEEDS:
        train,final=suite(seed);path=out/f"{seed}.sqlite3";mem=Memory(path)
        for t in train:
            rr=episode(t,"expand")
            added=rr["success"] and mem.add(rr["candidate"][1],t["id"])
            training.append(dict(seed=seed,added=added,**rr))
        learned=mem.snapshot();mem.close();mem=Memory(path)
        assert mem.snapshot()==learned
        snapshots.append(dict(seed=seed,skills=len(learned),sha=digest(learned),parts=learned))
        for t in final:
            for policy in POLICIES:rows.append(dict(seed=seed,**episode(t,policy,learned)))
        assert mem.snapshot()==learned;mem.close()
    def metric(rr):
        ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
        return dict(n=len(rr),correct=ok,wrong=em-ok,abstained=len(rr)-em,
                    queries=sum(r["queries"] for r in rr),expansions=sum(r["expanded"] for r in rr),
                    hypothesis_evaluations=sum(r["hypothesis_evaluations"] for r in rr),
                    wall_ns=sum(r["wall_ns"] for r in rr))
    result=dict(protocol="V21-persistent-structures-v1",seeds=SEEDS,snapshots=snapshots,
        training=dict(**metric(training),added=sum(r["added"] for r in training)),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_stratum=[dict(stratum=z,policy=p,**metric([r for r in rows if r["policy"]==p and r["task"]["stratum"]==z])) for z in STRATA for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s])) for s in SEEDS for p in POLICIES])
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("training",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as f:
            for rr in data:f.write(encode(rr)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_suite(self):
        for s in SEEDS:
            tr,te=suite(s);self.assertEqual((len(tr),len(te)),(12,36))
            keys={(t["family"],t["parts"]) for t in tr}
            for t in te:
                if t["stratum"]=="seen_structure":
                    self.assertIn((t["family"],t["parts"]),keys)
                    self.assertFalse(any(z["family"]==t["family"] and z["parts"]==t["parts"] and z["coefs"]==t["coefs"] for z in tr))
                if t["stratum"]=="new_structure":self.assertNotIn((t["family"],t["parts"]),keys)
    def test_controls(self):
        for t in suite(SEEDS[0])[0][:2]:
            for policy in ("expand","large"):
                r=episode(t,policy)
                base,trace,cost,expanded,n=e.investigate({p:e.target(t,p) for p in v.INITIAL},lambda p:e.target(t,p),policy)
                self.assertEqual((r["candidate"],r["trace"],r["hypothesis_evaluations"],r["expanded"],r["remaining"]),(base,trace,cost,expanded,n))
    def test_memory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.db";m=Memory(p);part=e.LARGE[25]
            self.assertTrue(m.add(part,"test"));self.assertFalse(m.add(part,"duplicate"))
            self.assertFalse(m.add(e.SMALL[0],"base"));m.close();m=Memory(p)
            self.assertEqual(m.snapshot(),(part,));m.close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V21 required")
    run(z.output)
