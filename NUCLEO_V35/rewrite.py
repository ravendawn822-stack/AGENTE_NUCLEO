"""V35: rewrite a bounded declarative resource investigation component."""
import argparse,itertools,json,random,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V32"))
import perception as v
m=v.m
SEEDS=(5040017,5070023,5100031,5130041)
LEAVES=("pairs","worst","distance","length","zero")
OPS=("add","sub","min","max")
BASE=("pairs","distance")
POLICIES=("baseline","mutated","installed","random","random_installed")
VERSION="nucleo-score-source-v1"
def freeze(x):return tuple(freeze(z) for z in x) if isinstance(x,list) else x

def expression_size(x,depth=0):
    if depth>3:raise ValueError("depth")
    if isinstance(x,str) and x in LEAVES:return 1
    if not isinstance(x,tuple) or len(x)!=3 or x[0] not in OPS:raise ValueError("expression")
    n=1+expression_size(x[1],depth+1)+expression_size(x[2],depth+1)
    if n>15:raise ValueError("size")
    return n

def validate(src):
    if not isinstance(src,tuple) or len(src)!=2:raise ValueError("component shape")
    return sum(expression_size(x) for x in src)

def interpret(expr,features):
    if isinstance(expr,str):return features[expr]
    op,a,b=expr
    x=interpret(a,features);y=interpret(b,features)
    if op=="add":return x+y
    if op=="sub":return x-y
    if op=="min":return min(x,y)
    if op=="max":return max(x,y)
    raise ValueError("operator")

def paths(expr):
    yield ()
    if isinstance(expr,tuple):
        for i in (1,2):
            for p in paths(expr[i]):yield (i,*p)

def replace(expr,path,term):
    if not path:return term
    i,*tail=path
    out=list(expr);out[i]=replace(out[i],tail,term)
    return tuple(out)

TERMS=(*LEAVES,*itertools.product(OPS,LEAVES,LEAVES))
def neighbors(src):
    result=set()
    for i in (0,1):
        for path in paths(src[i]):
            for term in TERMS:
                out=list(src);out[i]=replace(src[i],path,term);p=tuple(out)
                if p==src:continue
                try:validate(p)
                except ValueError:continue
                result.add(p)
    return sorted(result,key=m.enc)

def sample_source(rng):
    def expr(depth):
        if depth==3 or rng.random()<.48:return rng.choice(LEAVES)
        return (rng.choice(OPS),expr(depth+1),expr(depth+1))
    src=(expr(0),expr(0));validate(src);return src

def perceive(ids,probe,public,src):
    validate(src);model={};cost=0
    predicted={(name,x):v.t.oracle(name,x) for name in v.NAMES for x in public}
    cost+=len(predicted)
    for resource in ids:
        candidates=list(v.NAMES);remaining=list(public);observed=[];trace=[];state="unprobed"
        for _ in range(v.PROBE_CAP):
            def score(x):
                nonlocal cost
                n=len(candidates);groups={}
                for name in candidates:
                    y=predicted[name,x];groups[y]=groups.get(y,0)+1;cost+=1
                pair=1000*(n*n-sum(z*z for z in groups.values()))//(n*n)
                worst=1000*(n-max(groups.values()))//n
                distance=min(1000,10*min(v.distance(x,p) for p in observed)) if observed else 0
                length=1000 if len(x) not in {len(p) for p in observed} else 0
                features=dict(pairs=pair,worst=worst,distance=distance,length=length,zero=0)
                return interpret(src[0] if n>1 else src[1],features)
            x=max(remaining,key=score)
            remaining.remove(x);response=probe(resource,x);before=len(candidates)
            if response["status"]=="unavailable":
                candidates=[];state="unavailable"
                trace.append(dict(input=x,response=response,before=before,after=0));break
            assert response["status"]=="ok"
            observed.append(x);cost+=len(candidates)
            candidates=[name for name in candidates if predicted[name,x]==response["output"]]
            trace.append(dict(input=x,response=response,before=before,after=len(candidates)))
            state="unknown" if not candidates else "identified" if len(candidates)==1 else "ambiguous"
            if not candidates:break
        model[resource]=dict(state=state,identity=candidates[0] if state=="identified" else None,candidates=candidates,trace=trace)
    return model,cost

def episodes(src,seeds,policy):
    rows=[]
    for seed in seeds:
        a,b,held=v.v.input_sets(seed);public=(*a,*b)
        env=v.Environment(seed,public,held)
        start=time.perf_counter_ns()
        model,cost=perceive(env.list_resources(),env.probe,public,src)
        elapsed=time.perf_counter_ns()-start
        resources,goals=v.evaluate(env,model,held,seed,policy)
        rows.append(dict(seed=seed,source=src,policy=policy,probes=env.probe_count,cost=cost,wall_ns=elapsed,
            classified=sum(r["correct"] for r in resources),false_identity=sum(r["false_identity"] for r in resources),
            resources=resources,goals=goals,model=model))
    return rows

def metrics(rows):
    goals=[g for row in rows for g in row["goals"]]
    d=v.metric(goals)
    d.update(environments=len(rows),probes=sum(r["probes"] for r in rows),
        classified=sum(r["classified"] for r in rows),false_identity=sum(r["false_identity"] for r in rows),
        cost=sum(r["cost"] for r in rows),wall_ns=sum(r["wall_ns"] for r in rows))
    d["score"]=100*d["correct"]-200*d["wrong"]+10*d["appropriate_abstention"]-d["probes"]
    return d

def rank(src,rows):return (-metrics(rows)["score"],validate(src),m.digest(src))
def search(evaluate,seed,random_control=False,count=0):
    rng=random.Random(seed);cache={BASE:evaluate(BASE)};incumbent=BASE;trail=[]
    if random_control:
        while len(cache)<count+1:
            p=sample_source(rng)
            if p not in cache:cache[p]=evaluate(p)
        incumbent=min(cache,key=lambda p:rank(p,cache[p]))
        trail.append(dict(chosen=incumbent,tested=list(cache)))
    else:
        for i in range(2):
            options=[p for p in neighbors(incumbent) if p not in cache]
            chosen=rng.sample(options,min(4,len(options)))
            previous=incumbent
            for p in chosen:cache[p]=evaluate(p)
            incumbent=min((incumbent,*chosen),key=lambda p:rank(p,cache[p]))
            trail.append(dict(round=i,previous=previous,tested=chosen,chosen=incumbent))
    return incumbent,cache,trail

def approved(candidate,base,proposal):
    a,b=metrics(base),metrics(proposal)
    return candidate if b["score"]>a["score"] and b["wrong"]<=a["wrong"] else BASE

def serialize(src):
    validate(src)
    record=dict(version=VERSION,source=src)
    record["sha"]=m.digest(record)
    return m.enc(record)

def load(path):
    record=json.loads(path.read_text(encoding="utf-8"))
    if set(record)!={"version","source","sha"}:raise ValueError("source schema")
    sha=record.pop("sha")
    if record["version"]!=VERSION or sha!=m.digest(record):raise ValueError("source integrity")
    src=freeze(record["source"]);validate(src);return src

def install(directory,src):
    # Executor-owned fixed paths, never selected by the synthesized component.
    directory.mkdir(parents=True,exist_ok=False)
    original=directory/"original.json";active=directory/"active.json";pending=directory/"pending.json"
    original.write_text(serialize(BASE),encoding="utf-8")
    active.write_text(serialize(BASE),encoding="utf-8")
    pending.write_text(serialize(src),encoding="utf-8");assert load(pending)==src
    pending.replace(active);assert load(active)==src and load(original)==BASE
    return load(active)

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[];training=[];decisions=[]
    for seed in SEEDS:
        seeds=tuple(seed+1009*i for i in range(1,19));p,g,f=seeds[:5],seeds[5:10],seeds[10:]
        mutated,mc,mt=search(lambda src:episodes(src,p,"mutation_proposal"),seed^0x3501)
        rnd,rc,rt=search(lambda src:episodes(src,p,"random_proposal"),seed^0x3502,True,len(mc)-1)
        base_gate=episodes(BASE,g,"baseline_gate")
        mut_gate=episodes(mutated,g,"mutation_gate")
        rnd_gate=episodes(rnd,g,"random_gate")
        chosen=approved(mutated,base_gate,mut_gate);random_chosen=approved(rnd,base_gate,rnd_gate)
        installed=install(out/f"{seed}_mutation",chosen)
        random_installed=install(out/f"{seed}_random",random_chosen)
        dev=[r for rr in mc.values() for r in rr]+[r for rr in rc.values() for r in rr]+base_gate+mut_gate+rnd_gate
        training.extend(dict(replica=seed,**r) for r in dev)
        decisions.append(dict(replica=seed,mutation=mutated,installed=installed,random=rnd,random_installed=random_installed,
            mutation_trials=len(mc),random_trials=len(rc),mutation_trail=mt,random_trail=rt,
            source_sha=m.digest(installed),development_sha=m.digest(dev),baseline_gate=metrics(base_gate),
            mutation_gate=metrics(mut_gate),random_gate=metrics(rnd_gate),development_cost=metrics(dev)))
        for policy,src in zip(POLICIES,(BASE,mutated,installed,rnd,random_installed)):
            rows.extend(dict(replica=seed,**r) for r in episodes(src,f,policy))
        assert load(out/f"{seed}_mutation"/"active.json")==installed
        assert load(out/f"{seed}_random"/"active.json")==random_installed
    result=dict(protocol="V35-declarative-source-rewrite-v1",seeds=SEEDS,decisions=decisions,
        aggregate=[dict(policy=p,**metrics([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_replica=[dict(replica=s,policy=p,**metrics([r for r in rows if r["replica"]==s and r["policy"]==p])) for s in SEEDS for p in POLICIES])
    ref={(r["replica"],r["seed"],g["goal"]):g for r in rows if r["policy"]=="baseline" for g in r["goals"]}
    result["paired_vs_baseline"]={}
    for p in POLICIES[1:]:
        pairs=[(g,ref[r["replica"],r["seed"],g["goal"]]) for r in rows if r["policy"]==p for g in r["goals"]]
        result["paired_vs_baseline"][p]=dict(gains=sum(a["success"] and not b["success"] for a,b in pairs),
            losses=sum(not a["success"] and b["success"] for a,b in pairs))
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    for name,data in (("raw",rows),("development",training)):
        with (out/(name+".jsonl")).open("w",encoding="utf-8") as fp:
            for r in data:fp.write(m.enc(r)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_language(self):
        self.assertEqual(interpret(("add","pairs","distance"),dict(pairs=5,distance=8)),13)
        with self.assertRaises(ValueError):validate(("import","zero"))
        with self.assertRaises(ValueError):validate((("add","zero",("add","zero",("add","zero",("add","zero","zero")))),"zero"))
        self.assertTrue(all(validate(p)<=30 for p in neighbors(BASE)))
    def test_install_restore(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)/"component";src=(("add","pairs","worst"),"distance")
            self.assertEqual(install(directory,src),src)
            original=directory/"original.json";pending=directory/"pending.json";active=directory/"active.json"
            pending.write_text(original.read_text(encoding="utf-8"),encoding="utf-8")
            self.assertEqual(load(pending),BASE);pending.replace(active)
            self.assertEqual(load(active),BASE)
            active.write_text('{"source":"invalid"}',encoding="utf-8")
            with self.assertRaises(ValueError):load(active)
    def test_environment(self):
        r=episodes(BASE,[SEEDS[0]],"test")[0]
        self.assertLessEqual(r["probes"],40)
        self.assertEqual(len(r["resources"]),10)
        self.assertEqual(len(r["goals"]),8)
        self.assertEqual(sum(g["present"] for g in r["goals"]),6)
    def test_disjoint(self):
        s=[seed+1009*i for seed in SEEDS for i in range(1,19)]
        self.assertEqual(len(set(s)),72)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V35 required")
    run(z.output)
