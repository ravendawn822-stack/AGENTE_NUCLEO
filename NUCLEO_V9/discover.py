"""V9: failure-triggered discovery and registration of binary symbolic skills."""
import argparse,hashlib,itertools,json,random,sqlite3,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=(1800013,1830011,1860019)
X,Y,C=0,1,2
ABS,NEG=3,4
ADD,SUB,MUL,MOD,GT,EQ=10,11,12,13,14,15
OPS=(ADD,SUB,MUL,MOD,GT,EQ)
BASE=600
EXTRA=3000
TRAIN=24000
MAX_OPS=12
POLICIES=("base","extended","literal","new_ops")


def enc(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def freeze(x):return tuple(freeze(y) for y in x) if isinstance(x,list) else x


def vector_op(op,a,b=None):
    if op==ABS:return tuple(abs(x) for x in a)
    if op==NEG:return tuple(-x for x in a)
    if op==ADD:return tuple(x+y for x,y in zip(a,b))
    if op==SUB:return tuple(x-y for x,y in zip(a,b))
    if op==MUL:return tuple(x*y for x,y in zip(a,b))
    if op==MOD:return tuple(x%y for x,y in zip(a,b))
    if op==GT:return tuple(int(x>y) for x,y in zip(a,b))
    if op==EQ:return tuple(int(x==y) for x,y in zip(a,b))
    raise ValueError("opcode")


def apply(e,x,y,registry):
    op=e[0]
    if op==X:return x
    if op==Y:return y
    if op==C:return (e[1],)*len(x)
    a=apply(e[1],x,y,registry)
    if op in (ABS,NEG):return vector_op(op,a)
    b=apply(e[2],x,y,registry)
    if op in registry:return apply(registry[op],a,b,{})
    return vector_op(op,a,b)


def nodes(e):return 1+sum(nodes(c) for c in e[1:] if isinstance(c,tuple))
def leaves(e):
    return {e[0]} if e[0] in (X,Y,C) else set().union(*(leaves(c) for c in e[1:] if isinstance(c,tuple)))
def expand(e,registry):
    if e[0] in (X,Y,C):return e
    a=expand(e[1],registry)
    if e[0] in (ABS,NEG):return e[0],a
    b=expand(e[2],registry)
    if e[0] in registry:
        def subst(t):
            if t[0]==X:return a
            if t[0]==Y:return b
            return tuple(subst(c) if isinstance(c,tuple) else c for c in t)
        return subst(registry[e[0]])
    return e[0],a,b


def synthesize(pairs,ys,limit,registry=None,literals=()):
    registry=registry or {};xs,ys_in=zip(*pairs);target=tuple(ys)
    levels={1:[]};seen=set();tested=0
    def offer(e,v,cost):
        nonlocal tested
        tested+=1
        if v is None or any(abs(z)>10**9 for z in v):return False
        if v==target:return True
        if v not in seen:
            seen.add(v);levels[cost].append((e,v))
        return False
    for e in ((X,),(Y,),*((C,c) for c in (-2,-1,0,1,2,3)),*literals):
        if tested>=limit:return None,tested
        try:v=apply(e,xs,ys_in,registry)
        except ZeroDivisionError:v=None
        if offer(e,v,1):return e,tested
    ops=(*sorted(registry),*OPS)
    for c in range(2,10):
        levels[c]=[]
        for e,v in levels[c-1]:
            for op in (ABS,NEG):
                if tested>=limit:return None,tested
                q=(op,e)
                if offer(q,vector_op(op,v),c):return q,tested
        for k in range(1,c-1):
            for a,av in levels[k]:
                for b,bv in levels[c-k-1]:
                    for op in ops:
                        if tested>=limit:return None,tested
                        e=(op,a,b)
                        try:v=apply(registry[op],av,bv,{}) if op in registry else vector_op(op,av,bv)
                        except ZeroDivisionError:v=None
                        if offer(e,v,c):return e,tested
    return None,tested


def check(e,pairs,target,registry):
    if e is None:return False
    x,y=zip(*pairs)
    try:return apply(e,x,y,registry)==tuple(target)
    except ZeroDivisionError:return False


class Registry:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS ops(id INTEGER PRIMARY KEY,body TEXT UNIQUE,origin TEXT,evidence TEXT,sha TEXT)")
    def register(self,e,origin,pairs,answers):
        if e is None or leaves(e)!={X,Y} and leaves(e)!={X,Y,C}:return False
        if nodes(e)>25 or not check(e,pairs,answers,{}):return False
        body=enc(e);evidence=enc(dict(pairs=pairs,answers=answers))
        if self.db.execute("SELECT 1 FROM ops WHERE body=?",(body,)).fetchone():return False
        n=self.db.execute("SELECT COUNT(*) FROM ops").fetchone()[0]
        if n>=MAX_OPS:return False
        self.db.execute("INSERT INTO ops VALUES(?,?,?,?,?)",(100+n,body,origin,evidence,digest([body,origin,evidence])))
        self.db.commit();return True
    def snapshot(self):
        out={}
        for i,b,o,v,h in self.db.execute("SELECT * FROM ops ORDER BY id"):
            assert digest([b,o,v])==h
            out[i]=freeze(json.loads(b))
        return out
    def close(self):self.db.close()


# Evaluator only: no labels or formula supplied to synthesis.
MOTIFS=("absdiff","sqdiff","sqsum","sumabs","modsum","absprod","weighted","asym")
def motif(name,x,y):
    if name=="absdiff":return abs(x-y)
    if name=="sqdiff":return (x-y)**2
    if name=="sqsum":return x*x+y*y
    if name=="sumabs":return abs(x)+abs(y)
    if name=="modsum":return (x+y)%3
    if name=="absprod":return abs(x*y)
    if name=="weighted":return x*abs(y-x)
    if name=="asym":return abs(x-y)+x
    raise ValueError(name)


def target(t,x,y):
    f=t["motif"];a,b=t["shift"]
    if f=="unrelated":return (x+a)*(y+b)+x*x
    if f=="outside":return (x+a)**3+(y+b)**3
    return motif(f,x+a,y+b)


def suite(seed):
    rng=random.Random(seed)
    train=[dict(id=f"{seed}/train/{i}",motif=f,shift=(0,0),family="training") for i,f in enumerate(MOTIFS)]
    rng.shuffle(train)
    test=[];seen={tuple(target(t,x,y) for x in range(-4,5) for y in range(-4,5)) for t in train}
    for f in (*MOTIFS,"unrelated","outside"):
        count=3 if f in MOTIFS else 4
        options=list(itertools.product((-2,-1,0,1,2),repeat=2));rng.shuffle(options)
        for a,b in options:
            if (a,b)==(0,0):continue
            t=dict(id=f"{seed}/final/{len(test)}",motif=f,shift=(a,b),family="linked" if f in MOTIFS else f)
            sig=tuple(target(t,x,y) for x in range(-4,5) for y in range(-4,5))
            if sig in seen:continue
            seen.add(sig);test.append(t);count-=1
            if count==0:break
        assert count==0
    rng.shuffle(test);assert len(test)==32
    return train,test


def observations(seed):
    rng=random.Random(seed)
    obs=list(dict.fromkeys([(0,0),(1,0),(0,1),(-1,0),(0,-1),(2,3),(-3,2),(3,-2),(-2,-3),(4,4),(-4,-4)]+[(rng.randint(-6,6),rng.randint(-6,6)) for _ in range(14)]))
    reserved=[(x,y) for x in (-19,-11,-7,-2,0,3,8,13,21) for y in (-17,-9,-4,0,2,6,12,20) if (x,y) not in obs]
    return obs,reserved


def episode(t,seed,policy,registry):
    start=time.perf_counter_ns();obs,held=observations(seed)
    answers=[target(t,x,y) for x,y in obs];checks=[target(t,x,y) for x,y in held]
    used={};n=0;first=None
    if policy=="extended":e,n=synthesize(obs,answers,BASE+EXTRA)
    else:
        e,n=synthesize(obs,answers,BASE);first=e
        if e is None and policy=="train":
            e,k=synthesize(obs,answers,TRAIN);n+=k
        elif e is None and policy in ("literal","new_ops"):
            used=registry if policy=="new_ops" else {}
            e,k=synthesize(obs,answers,EXTRA,used,tuple(registry.values()) if policy=="literal" else ())
            n+=k
    elapsed=time.perf_counter_ns()-start
    correct=check(e,held,checks,used)
    body=expand(e,used) if e is not None else None
    def codes(t):
        if t is None:return []
        return ([t[0]] if t[0]>=100 else [])+[c for x in t[1:] if isinstance(x,tuple) for c in codes(x)]
    return dict(task=t,policy=policy,success=correct,emitted=e is not None,initial_failed=first is None if policy!="extended" else None,
                candidate=e,expanded=body,opcodes=codes(e),candidates=n,search_ns=elapsed,observations=list(zip(obs,answers)),validation=list(zip(held,checks)))


def metrics(rr):
    n=len(rr);c=sum(r["success"] for r in rr);e=sum(r["emitted"] for r in rr)
    return dict(n=n,correct=c,wrong=e-c,abstained=n-e,mean_candidates=sum(r["candidates"] for r in rr)/n,
                mean_search_ns=sum(r["search_ns"] for r in rr)/n,
                new_op_correct=sum(r["success"] and bool(r["opcodes"]) for r in rr))


def run(folder):
    folder.mkdir(parents=True,exist_ok=False);rows=[];memories=[]
    for seed in SEEDS:
        train,test=suite(seed);path=folder/f"registry_{seed}.sqlite3";reg=Registry(path)
        for i,t in enumerate(train):
            row=episode(t,seed+i*97,"train",{})
            accepted=False
            if row["initial_failed"] and row["success"]:
                pairs,answers=zip(*[(tuple(p),v) for p,v in row["validation"]])
                accepted=reg.register(row["candidate"],t["id"],pairs,answers)
            rows.append(dict(seed=seed,phase="train",registered=accepted,**row))
        before=digest(reg.snapshot());reg.close();reg=Registry(path);snapshot=reg.snapshot();reg.close()
        assert digest(snapshot)==before
        memories.append(dict(seed=seed,registry=snapshot,sha256=before))
        for i,t in enumerate(test):
            for p in POLICIES:
                rows.append(dict(seed=seed,phase="final",**episode(t,seed*3+i*101,p,snapshot)))
        assert digest(snapshot)==before
    final=[r for r in rows if r["phase"]=="final"];baseline={(r["seed"],r["task"]["id"]):r for r in final if r["policy"]=="extended"}
    agg=[]
    for p in POLICIES:
        rr=[r for r in final if r["policy"]==p];m=metrics(rr)
        m.update(gains_vs_extended=sum(r["success"] and not baseline[r["seed"],r["task"]["id"]]["success"] for r in rr),
                 losses_vs_extended=sum(not r["success"] and baseline[r["seed"],r["task"]["id"]]["success"] for r in rr))
        agg.append(dict(policy=p,**m))
    result=dict(protocol="V9-operation-discovery-v1",episodes=len(rows),seeds=SEEDS,aggregate=agg,
        by_family=[dict(policy=p,family=f,**metrics([r for r in final if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in ("linked","unrelated","outside")],
        acquired=sum(r.get("registered",False) for r in rows),training=[dict(seed=r["seed"],task=r["task"],initial_failed=r["initial_failed"],candidate=r["candidate"],success=r["success"],registered=r["registered"],candidates=r["candidates"]) for r in rows if r["phase"]=="train"],
        examples=[dict(task=r["task"],candidate=r["candidate"],expanded=r["expanded"],seed=r["seed"]) for r in final if r["policy"]=="new_ops" and r["success"] and r["opcodes"]][:5])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"registries.json").write_text(json.dumps(memories,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(enc(r)+"\n")
    print("SUMMARY_V9="+enc(result))


class Tests(unittest.TestCase):
    def test_composition(self):
        e=(ABS,(SUB,(X,),(Y,)));reg={100:e}
        call=(100,(ADD,(X,),(C,1)),(Y,))
        self.assertEqual(apply(call,(1,2),(4,-3),reg),(2,6))
        self.assertEqual(apply(expand(call,reg),(1,2),(4,-3),{}),(2,6))
    def test_search_bound(self):
        obs,held=observations(10)
        e,n=synthesize(obs,[999]*len(obs),17)
        self.assertLessEqual(n,17)
    def test_registry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"x.db";r=Registry(path)
            pairs=((1,2),(-3,2),(0,0));e=(ABS,(SUB,(X,),(Y,)))
            self.assertFalse(r.register(e,"negative_control",pairs,(0,0,0)))
            self.assertTrue(r.register(e,"valid",pairs,(1,5,0)))
            self.assertFalse(r.register(e,"repeat",pairs,(1,5,0)))
            d=digest(r.snapshot());r.close();r=Registry(path);self.assertEqual(d,digest(r.snapshot()));r.close()
    def test_suite(self):
        for seed in SEEDS:
            tr,te=suite(seed);self.assertEqual((len(tr),len(te)),(8,32))
    def test_no_hidden_answer(self):
        pairs=((1,2),(3,4),(-3,1),(0,0));e,n=synthesize(pairs,[a+b for a,b in pairs],BASE)
        self.assertTrue(check(e,pairs,[a+b for a,b in pairs],{}))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V9 required")
    run(a.output)
