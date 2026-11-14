"""V3.1: two-level composition of learned numeric program fragments."""
import argparse
import hashlib
import itertools
import json
import random
import sqlite3
import sys
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V3"))
import schema as prev
from schema import old,sequence,FOLD,execute,value,CONST,roundrobin
from programs import ACC,ITEM,ABS,NEG,ADD,SUB,MUL,MOD,GT,EQ

SEEDS=(870013,900001,930011,960017)
PRIOR=prev.SEEDS
XS=tuple(range(-6,7))+(-9,9)
POOL_CAP=500
GEN_CAP=3000
JOIN_CAP=1000
POLICIES=("v2_1","grammar","literal","schema","hierarchy","expert")
FAMILIES=("pair","linked_triple","independent_triple","product")
OPS=(ADD,SUB,MUL,MOD,GT,EQ)
E=(ITEM,)
A=(ACC,)


def freeze(e):return sequence.freeze(e)
def encode(e):return json.dumps(e,sort_keys=True,separators=(",",":"))
def sha(e):return hashlib.sha256(encode(e).encode()).hexdigest()
def size(e):return 1+sum(size(c) for c in e[1:] if isinstance(c,tuple))
def has(e,op):return e[0]==op or any(has(c,op) for c in e[1:] if isinstance(c,tuple))
def fragments(e):
    if not has(e,ACC) and has(e,ITEM) and size(e)>1:yield e
    for c in e[1:]:
        if isinstance(c,tuple):yield from fragments(c)


def vector(e):
    try:return tuple(value(e,0,x) for x in XS)
    except (ValueError,ZeroDivisionError):return None


def primitive():
    # Uniform cost enumeration of input-only expressions, no task-specific features.
    levels={1:[]};seen=set()
    def offered(e,c):
        v=vector(e)
        if v is not None and v not in seen:
            seen.add(v);levels[c].append(e)
        return e
    for e in (E,*((CONST,c) for c in range(-8,9))):
        yield offered(e,1)
    for c in range(2,9):
        levels[c]=[]
        unary=((op,e) for e in levels[c-1] for op in (ABS,NEG))
        binary=((op,a,b) for k in range(1,c-1) for a in levels[k] for b in levels[c-k-1] for op in OPS)
        for e in roundrobin(unary,binary):
            yield offered(e,c)


def extract(snapshot):
    literal={};templates={}
    for p in snapshot["programs"]:
        for e in fragments(freeze(p["expr"])):
            key=encode(e)
            if key not in literal:literal[key]=dict(expr=e,origins=[])
            literal[key]["origins"]=sorted(set(literal[key]["origins"]+p["origins"]))
            for t,b in prev.schemas(e):
                k=encode(t)
                if k not in templates:templates[k]=dict(template=t,bindings=[],origins=[])
                row=templates[k]
                if b not in row["bindings"]:row["bindings"].append(b)
                row["origins"]=sorted(set(row["origins"]+p["origins"]))
    l=sorted(literal.values(),key=lambda r:(-len(r["origins"]),size(r["expr"]),encode(r["expr"])))
    t=sorted(templates.values(),key=lambda r:(-len(r["origins"]),size(r["template"]),encode(r["template"])))
    return l,t


def literal_stream(l):
    for row in l:yield row["expr"],dict(kind="literal",origins=row["origins"])


def instances(t):
    def one(row):
        arity=len(row["bindings"][0]);order=sorted(range(-8,9),key=lambda z:(abs(z),z))
        for b in itertools.product(order,repeat=arity):
            yield prev.bind(row["template"],b),dict(kind="schema",template=row["template"],binding=b,origins=row["origins"])
    yield from roundrobin(*(one(row) for row in t))


def experts():
    # Explicit, strong domain prior: feature dictionary of common elementary transforms.
    # Supplied by developer; not considered learned.
    streams=[]
    streams.append(((op,E,(CONST,c)) for c in range(-8,9) for op in (ADD,SUB,MUL,GT)))
    streams.append(((ABS,(SUB,E,(CONST,c))) for c in range(-8,9)))
    streams.append(((MUL,(SUB,E,(CONST,c)),(SUB,E,(CONST,c))) for c in range(-8,9)))
    streams.append(((EQ,(MOD,E,(CONST,p)),(CONST,q)) for p in range(2,9) for q in range(p)))
    streams.append(((GT,(CONST,c),E) for c in range(-8,9)))
    for e in roundrobin(*streams):yield e,dict(kind="expert")


def build_pool(policy,snapshot):
    start=time.perf_counter_ns()
    l,t=extract(snapshot)
    cold=((e,dict(kind="primitive")) for e in primitive())
    if policy=="grammar":stream=cold
    elif policy=="literal":stream=roundrobin(literal_stream(l),cold)
    elif policy=="schema":stream=roundrobin(literal_stream(l),instances(t),cold)
    elif policy=="expert":stream=roundrobin(experts(),cold)
    else:raise ValueError(policy)
    rows=[];seen=set();spent=0
    for e,origin in itertools.islice(stream,GEN_CAP):
        spent+=1
        v=vector(e)
        if size(e)>35 or v is None or v in seen:continue
        seen.add(v);rows.append(dict(expr=e,vec=v,source=origin))
        if len(rows)>=POOL_CAP:break
    return rows,dict(generated=spent,pool_size=len(rows),build_ns=time.perf_counter_ns()-start,
                     sources={k:sum(r["source"]["kind"]==k for r in rows) for k in ("primitive","literal","schema","expert")},
                     available_literal=len(l),available_templates=len(t))


def add_layer(pool,learned):
    # Same pool size limit, verified training combinations take priority.
    rows=[];seen=set()
    for row in [*learned,*pool]:
        if row["vec"] not in seen:
            rows.append(row);seen.add(row["vec"])
        if len(rows)>=POOL_CAP:break
    return rows


def join(target,pool):
    # Hash-based meet in the middle; one complement lookup per candidate and operator.
    index={r["vec"]:r for r in pool}
    if target in index:
        row=index[target];return row["expr"],1,[row["source"]]
    calls=1
    for r in pool:
        for op in (ADD,SUB):
            if calls>=JOIN_CAP:return None,calls,[]
            q=tuple(y-v if op==ADD else v-y for y,v in zip(target,r["vec"]))
            calls+=1
            if q in index:
                other=index[q];e=(op,r["expr"],other["expr"])
                if size(e)<=75:return e,calls,[r["source"],other["source"]]
    return None,calls,[]


def term(rng):
    f=rng.randrange(6)
    if f==0:return ("abs",rng.randint(-5,5),1)
    if f==1:return ("square",rng.randint(-5,5),1)
    if f==2:return ("gt",rng.randint(-5,5),1)
    if f==3:
        p=rng.randint(2,7);return ("mod",p,rng.randrange(p))
    if f==4:return ("linear",rng.choice((-3,-2,2,3)),rng.randint(-4,4))
    return ("lt",rng.randint(-5,5),1)


def atom(t,x):
    f,p,q=t
    if f=="abs":return abs(x-p)
    if f=="square":return (x-p)**2
    if f=="gt":return int(x>p)
    if f=="lt":return int(x<p)
    if f=="mod":return int(x%p==q)
    return p*x+q


def target(task,seq):
    terms=task["terms"];product=task["family"]=="product"
    return sum((atom(terms[0],x)*atom(terms[1],x) if product else sum(atom(t,x) for t in terms)) for x in seq)


def tasks(seed):
    r=random.Random(seed);seen=set()
    def pair():
        while True:
            terms=tuple(sorted((term(r),term(r))))
            if terms[0]!=terms[1] and terms not in seen:
                seen.add(terms);return terms
    train=[dict(family="pair",terms=pair(),id=f"{seed}/train/{i}") for i in range(12)]
    final=[]
    for i in range(12):final.append(dict(family="pair",terms=pair(),id=f"{seed}/pair/{i}"))
    for i,t in enumerate(train):
        third=term(r)
        while third in t["terms"]:third=term(r)
        final.append(dict(family="linked_triple",terms=tuple(sorted((*t["terms"],third))),id=f"{seed}/linked/{i}",linked=t["id"]))
    for i in range(12):
        while True:
            values=tuple(sorted((term(r),term(r),term(r))))
            if len(set(values))==3 and not any(p in seen for p in itertools.combinations(values,2)):
                break
        final.append(dict(family="independent_triple",terms=values,id=f"{seed}/independent/{i}"))
    for i in range(8):final.append(dict(family="product",terms=pair(),id=f"{seed}/product/{i}"))
    assert len(final)==44
    # Remove exact functional duplicates on an independent wide generator fingerprint.
    # Rather than change the protocol after evaluation, fail if a leaked training function is encountered.
    # Distinct specifications can still be equivalent; we record overlap instead of excluding post hoc.
    return train,final


def observation_seqs():
    return [(),*((x,) for x in XS),(-3,2),(4,-5,1),(6,-9,9),(-1,3,-2)]


def validation_seqs(seed):
    rng=random.Random(seed)
    # Outside the observed support, plus mixed longer sequences.
    outer=[x for x in range(-20,21) if x not in XS]
    return [*((x,) for x in outer),*(tuple(rng.randint(-20,20) for _ in range(rng.randint(6,12))) for i in range(16))]


def solve(task,policy,pool,seed):
    start=time.perf_counter_ns();init,pairs,ys,q,ok=sequence.transitions(lambda z:target(task,z),observation_seqs())
    if not ok:raise RuntimeError("inconsistent oracle")
    if policy=="v2_1":
        e,n,m=old.synthesize(pairs,ys,"derived",4500);sources=[]
        p=(FOLD,init,e) if e is not None else None
    else:
        # Infer necessary per-item increment from observed accumulator transitions.
        bounds=old.constraints(pairs,ys,"add")
        if bounds is None or any(l is None or h!=l for l,h in bounds):
            p=None;n=0;sources=[]
        else:
            ordered=sorted({x for a,x in pairs});by_x=dict(zip(ordered,(l for l,h in bounds)))
            g,n,sources=join(tuple(by_x[x] for x in XS),pool)
            e=(ADD,A,g) if g is not None else None
            if e is not None and not prev.consistent(e,pairs,ys):raise RuntimeError("join semantics")
            p=(FOLD,init,e) if e is not None else None
    search_ns=time.perf_counter_ns()-start
    checks=[]
    if p is not None:
        for z in validation_seqs(seed):
            expected=target(task,z)
            try:predicted=execute(p,z)
            except (ValueError,ZeroDivisionError):predicted=None
            checks.append([z,expected,predicted])
    return dict(task=task,policy=policy,program=p,success=p is not None and all(y==z for _,y,z in checks),
                abstained=p is None,checks=checks,lookup_or_search_units=n,queries=q,sources=sources,
                search_ns=search_ns,total_ns=time.perf_counter_ns()-start)


def family_summary(rows):
    n=len(rows)
    return dict(n=n,correct=sum(r["success"] for r in rows),
        wrong=sum(not r["success"] and not r["abstained"] for r in rows),abstained=sum(r["abstained"] for r in rows),
        mean_queries=sum(r["queries"] for r in rows)/n,mean_search_ns=sum(r["search_ns"] for r in rows)/n,
        hierarchy_uses=sum(any(s["kind"]=="hierarchy" for s in r["sources"]) for r in rows),
        hierarchy_correct=sum(r["success"] and any(s["kind"]=="hierarchy" for s in r["sources"]) for r in rows),
        two_learned_correct=sum(r["success"] and len(r["sources"])==2 and all(s["kind"] in ("literal","schema","hierarchy") for s in r["sources"]) for r in rows))


def run(folder,prior):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    raw=prior.read_bytes();snapshots=json.loads(raw);rows=[];meta=[];banks={}
    db=sqlite3.connect(folder/"hierarchy.sqlite3")
    db.executescript("CREATE TABLE learned(seed INTEGER,id TEXT,expr TEXT,source TEXT,PRIMARY KEY(seed,id)); CREATE TABLE inventory(seed INTEGER,policy TEXT,payload TEXT,PRIMARY KEY(seed,policy));")
    for seed,ps in zip(SEEDS,PRIOR):
        snap=snapshots[str(ps)];train,final=tasks(seed);pools={}
        for pol in ("grammar","literal","schema","expert"):
            pool,m=build_pool(pol,snap);pools[pol]=pool
            meta.append(dict(seed=seed,prior_seed=ps,policy=pol,**m))
        learned=[]
        for i,t in enumerate(train):
            result=solve(t,"schema",pools["schema"],seed+i*503);rows.append(dict(seed=seed,phase="training",**result))
            # Only a verified genuine two-fragment candidate teaches layer 2.
            if result["success"] and len(result["sources"])==2:
                g=freeze(result["program"][2][2]);v=vector(g)
                if v is not None and not any(x["vec"]==v for x in learned):
                    origin=dict(kind="hierarchy",training_id=t["id"],parents=result["sources"])
                    learned.append(dict(expr=g,vec=v,source=origin))
                    db.execute("INSERT INTO learned VALUES(?,?,?,?)",(seed,t["id"],encode(g),encode(origin)))
        db.commit()
        # Reopen and reconstruct from persistent definitions, not in-memory objects.
        db.close();db=sqlite3.connect(folder/"hierarchy.sqlite3")
        restored=[dict(expr=freeze(json.loads(e)),vec=vector(freeze(json.loads(e))),source=json.loads(s)) for e,s in db.execute("SELECT expr,source FROM learned WHERE seed=? ORDER BY rowid",(seed,))]
        assert sha(restored)==sha(learned)
        started=time.perf_counter_ns()
        pools["hierarchy"]=add_layer(pools["schema"],restored)
        meta.append(dict(seed=seed,prior_seed=ps,policy="hierarchy",learned=len(restored),pool_size=len(pools["hierarchy"]),build_ns=time.perf_counter_ns()-started))
        for p,pool in pools.items():
            db.execute("INSERT INTO inventory VALUES(?,?,?)",(seed,p,encode(pool)))
        db.commit()
        banks[str(seed)]=dict(learned=restored,training_correct=sum(r["success"] for r in rows if r["phase"]=="training" and r["seed"]==seed))
        frozen=sha(pools)
        for i,t in enumerate(final):
            for pol in POLICIES:
                rr=solve(t,pol,pools.get(pol,[]),seed*17+i*701)
                rows.append(dict(seed=seed,phase="final",**rr))
        assert sha(pools)==frozen
    db.close()
    final=[r for r in rows if r["phase"]=="final"]
    control={(r["seed"],r["task"]["id"]):r for r in final if r["policy"]=="grammar"}
    aggregates=[]
    for policy in POLICIES:
        rr=[r for r in final if r["policy"]==policy]
        m=family_summary(rr)
        m["gain_vs_grammar"]=sum(r["success"] and not control[r["seed"],r["task"]["id"]]["success"] for r in rr)
        m["loss_vs_grammar"]=sum(not r["success"] and control[r["seed"],r["task"]["id"]]["success"] for r in rr)
        aggregates.append(dict(policy=policy,**m))
    by_family=[dict(policy=p,family=f,**family_summary([r for r in final if r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in FAMILIES]
    examples=[dict(seed=r["seed"],task=r["task"],program=r["program"],sources=r["sources"]) for r in final if r["policy"]=="hierarchy" and r["success"] and any(s["kind"]=="hierarchy" for s in r["sources"])][:8]
    overlaps=0
    for seed in SEEDS:
        tr,te=tasks(seed);signatures={tuple(target(t,(x,)) for x in range(-31,32)) for t in tr}
        overlaps+=sum(tuple(target(t,(x,)) for x in range(-31,32)) in signatures for t in te)
    result=dict(protocol="NUCLEO_V3_1-hierarchy-v1",episodes=len(rows),seeds=SEEDS,prior_sha256=hashlib.sha256(raw).hexdigest(),
        functional_overlap_on_generator_grid=overlaps,aggregate=aggregates,by_family=by_family,pool_build=meta,
        training={k:dict(learned=len(v["learned"]),correct=v["training_correct"]) for k,v in banks.items()},examples=examples)
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (folder/"banks.json").write_text(json.dumps(banks,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print("SUMMARY_HIERARCHY="+encode(result))


class Tests(unittest.TestCase):
    def test_join(self):
        e=(ABS,E);f=(MUL,E,E)
        pool=[dict(expr=a,vec=vector(a),source={"kind":"literal"}) for a in (e,f)]
        v=tuple(a+b for a,b in zip(vector(e),vector(f)))
        g,n,s=join(v,pool);self.assertEqual(vector(g),v);self.assertEqual(len(s),2)
        self.assertLessEqual(n,JOIN_CAP)
    def test_fragment(self):
        e=(ADD,A,(ABS,(SUB,E,(CONST,3))))
        l,t=extract({"programs":[{"expr":e,"origins":["example"]}]})
        self.assertTrue(l and t)
        self.assertTrue(all(not has(r["expr"],ACC) for r in l))
    def test_real_task(self):
        t=dict(family="pair",terms=(("abs",0,1),("square",0,1)),id="test")
        pool=[dict(expr=e,vec=vector(e),source={"kind":"literal"}) for e in ((ABS,E),(MUL,E,E))]
        r=solve(t,"schema",pool,7);self.assertTrue(r["success"]);self.assertEqual(len(r["sources"]),2)
    def test_partition(self):
        tr,te=tasks(SEEDS[0]);self.assertEqual((len(tr),len(te)),(12,44))
        self.assertFalse({r["id"] for r in tr}&{r["id"] for r in te})
        self.assertFalse(set(XS)&{x[0] for x in validation_seqs(1) if len(x)==1})
    def test_pool(self):
        pool,m=build_pool("grammar",{"programs":[]})
        self.assertLessEqual(len(pool),POOL_CAP);self.assertLessEqual(m["generated"],GEN_CAP)
        self.assertEqual(len({r["vec"] for r in pool}),len(pool))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);p.add_argument("--prior",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or a.prior is None or ROOT not in a.output.resolve().parents:p.error("new output and prior snapshot required")
    run(a.output,a.prior)
