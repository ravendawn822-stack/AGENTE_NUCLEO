"""V9.1: argument binding search for the actually learned V9 operations."""
import argparse,hashlib,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V9"))
import discover as v9
SEEDS=(1890011,1920013,1950017)
POLICIES=("extended","literal","primitive_bind","learned_bind")
TRANSFORMS=tuple((k,b) for k in (1,-1,2,-2) for b in (-2,-1,0,1,2))


def transform(var,k,b):
    e=(var,)
    if k==-1:e=(v9.NEG,e)
    elif k!=1:e=(v9.MUL,e,(v9.C,k))
    if b:e=(v9.ADD,e,(v9.C,b))
    return e


def bind_search(pairs,ys,registry,limit):
    xs,ys_in=zip(*pairs);expected=tuple(ys)
    left=[transform(v9.X,k,b) for k,b in TRANSFORMS]
    right=[transform(v9.Y,k,b) for k,b in TRANSFORMS]
    left.sort(key=v9.nodes);right.sort(key=v9.nodes)
    values={e:v9.apply(e,xs,ys_in,{}) for e in left+right}
    pairs_to_try=sorted(itertools.product(left,right),key=lambda ab:v9.nodes(ab[0])+v9.nodes(ab[1]))
    ops=(*sorted(registry),*v9.OPS)
    tested=0
    for a,b in pairs_to_try:
        for op in ops:
            if tested>=limit:return None,tested
            tested+=1
            try:vec=v9.apply(registry[op],values[a],values[b],{}) if op in registry else v9.vector_op(op,values[a],values[b])
            except ZeroDivisionError:continue
            if vec==expected:return (op,a,b),tested
    return None,tested


def target(t,x,y):
    a,b,c,d=t["transform"];u=a*x+b;v=c*y+d
    f=t["motif"]
    if f=="unrelated":return u*v+x*x
    if f=="outside":return u**3+v**3
    return v9.motif(f,u,v)


def signature(f):
    return tuple(f(x,y) for x in range(-4,5) for y in range(-4,5))


def suite(seed):
    seen=set()
    for prior_seed in v9.SEEDS:
        train,test=v9.suite(prior_seed)
        for t in train+test:seen.add(signature(lambda x,y:v9.target(t,x,y)))
    rng=random.Random(seed);rows=[]
    for f in (*v9.MOTIFS,"unrelated","outside"):
        count=3 if f=="modsum" else 5 if f=="outside" else 4
        options=list(itertools.product(TRANSFORMS,repeat=2));rng.shuffle(options)
        for p,q in options:
            if p[0]==q[0]==1:continue
            t=dict(id=f"{seed}/{len(rows)}",motif=f,transform=(*p,*q),family="linked" if f in v9.MOTIFS else f)
            sig=signature(lambda x,y:target(t,x,y))
            if sig in seen:continue
            seen.add(sig);rows.append(t);count-=1
            if not count:break
        assert count==0,f
    rng.shuffle(rows)
    assert len(rows)==40
    return rows


def evaluate(t,seed,policy,registry):
    obs,held=v9.observations(seed);ys=[target(t,x,y) for x,y in obs]
    start=time.perf_counter_ns();used={}
    if policy=="extended":e,n=v9.synthesize(obs,ys,v9.BASE+v9.EXTRA)
    else:
        e,n=v9.synthesize(obs,ys,v9.BASE)
        if e is None:
            if policy=="literal":e,k=v9.synthesize(obs,ys,v9.EXTRA,{},tuple(registry.values()))
            else:
                used=registry if policy=="learned_bind" else {}
                e,k=bind_search(obs,ys,used,v9.EXTRA)
            n+=k
    elapsed=time.perf_counter_ns()-start
    answers=[target(t,x,y) for x,y in held]
    success=v9.check(e,held,answers,used)
    return dict(task=t,policy=policy,success=success,emitted=e is not None,candidate=e,
                expanded=v9.expand(e,used) if e is not None else None,
                opcodes=[e[0]] if e is not None and e[0] in used else [],
                candidates=n,search_ns=elapsed,observations=list(zip(obs,ys)),validation=list(zip(held,answers)))


def run(folder,prior):
    folder.mkdir(parents=True,exist_ok=False);rows=[]
    snapshots=json.loads(prior.read_text(encoding="utf-8"))
    assert len(snapshots)==len(SEEDS)
    for seed,snapshot in zip(SEEDS,snapshots):
        registry={int(k):v9.freeze(e) for k,e in snapshot["registry"].items()}
        assert v9.digest(registry)==snapshot["sha256"]
        before=v9.digest(registry)
        for i,t in enumerate(suite(seed)):
            for p in POLICIES:rows.append(dict(seed=seed,**evaluate(t,seed+i*131,p,registry)))
        assert v9.digest(registry)==before
    base={(r["seed"],r["task"]["id"]):r for r in rows if r["policy"]=="extended"}
    def metrics(rr):
        m=v9.metrics(rr)
        m["gains_vs_extended"]=sum(r["success"] and not base[r["seed"],r["task"]["id"]]["success"] for r in rr)
        m["losses_vs_extended"]=sum(not r["success"] and base[r["seed"],r["task"]["id"]]["success"] for r in rr)
        return m
    result=dict(protocol="V9.1-binding-v1",episodes=len(rows),seeds=SEEDS,prior_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metrics([r for r in rows if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in ("linked","unrelated","outside")],
        examples=[dict(seed=r["seed"],task=r["task"],candidate=r["candidate"],expanded=r["expanded"]) for r in rows if r["policy"]=="learned_bind" and r["success"] and r["opcodes"]][:4])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(v9.enc(r)+"\n")
    print("SUMMARY_BIND="+v9.enc(result))


class Tests(unittest.TestCase):
    def test_binding(self):
        reg={100:(v9.ADD,(v9.ABS,(v9.X,)),(v9.ABS,(v9.Y,)))}
        obs,held=v9.observations(33)
        fn=lambda x,y:abs(2*x+1)+abs(y-1)
        e,n=bind_search(obs,[fn(x,y) for x,y in obs],reg,3000)
        self.assertTrue(v9.check(e,held,[fn(x,y) for x,y in held],reg))
        self.assertLessEqual(n,3000)
    def test_cap(self):
        e,n=bind_search([(1,2),(-3,3)],[999,999],{},3)
        self.assertLessEqual(n,3)
    def test_suite(self):
        for s in SEEDS:self.assertEqual(len(suite(s)),40)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or not a.prior or ROOT not in a.output.resolve().parents:p.error("new output and archived registry required")
    run(a.output,a.prior)
