"""04C/D: fixed composition template and finite-evidence abstention."""
import argparse
import json
import random
import time
import unittest
from fractions import Fraction
from pathlib import Path
from pilot import CATALOG, PROBES, polynomial, periodic

ROOT=Path(__file__).resolve().parent
SEEDS=(104729,130363,155921,196613,262147)
FAMILIES=("constant","periodic","poly","mixed","step","cubic_mixed","exponential","hidden_bump")
POLICIES=("single","portfolio","composition","guard_fixed","guard_disagreement")
GUARD_POOL=(-15,-12,-10,-8,-6,-5,5,6,8,10,12,15)
FIXED=(-10,-6,6,10)
FINAL=(-31,-23,-19,-16,-13,-11,11,13,16,19,23,31)


def make_cases(seed,n=20):
    rng=random.Random(seed)
    rows=[]
    for family in FAMILIES:
        seen=set()
        while len(seen)<n:
            if family=="constant": a=(rng.randint(-100,100),)
            elif family=="periodic": a=tuple(rng.sample(range(-20,21),rng.randint(2,5)))
            elif family=="poly": a=tuple(rng.randint(-5,5) for _ in range(rng.randint(1,7)))+(rng.choice((-3,-2,1,2)),)
            elif family in ("mixed","cubic_mixed"): a=(rng.choice((-3,-2,-1,1,2,3)),*rng.sample(range(-12,13),rng.randint(2,5)))
            elif family=="step": a=(rng.randint(-3,3),*rng.sample(range(-30,31),2))
            elif family=="exponential": a=(rng.choice((2,3)),rng.choice((-3,-2,-1,1,2,3)),rng.randint(-8,8))
            else: a=(rng.choice((-3,-2,-1,1,2,3)),rng.randint(-8,8),rng.choice((-19,19)),rng.choice((-9,-5,5,9)))
            if a not in seen: seen.add(a); rows.append((family,a))
    rng.shuffle(rows)
    return rows


def target(case,x):
    f,a=case
    if f=="constant": return a[0]
    if f=="periodic": return a[x%len(a)]
    if f=="poly": return sum(c*x**i for i,c in enumerate(a))
    if f=="mixed": return a[0]*x+a[1+x%(len(a)-1)]
    if f=="cubic_mixed": return a[0]*x**3+a[1+x%(len(a)-1)]
    if f=="step": return a[1] if x<a[0] else a[2]
    if f=="exponential": return a[1]*a[0]**abs(x)+a[2]
    return a[0]*x+a[1]+(a[3] if x==a[2] else 0)


def composed(obs):
    # The developer supplies this template; the unknown slope/residual are inferred.
    by_x=dict(obs)
    for p in range(2,6):
        dif=[Fraction(by_x[x+p]-y,p) for x,y in obs if x+p in by_x]
        if not dif or len(set(dif))!=1: continue
        slope=dif[0]
        line=polynomial(((0,0),(1,slope)))
        residual=periodic(tuple((x,y-line(x)) for x,y in obs))
        if residual is not None:
            def predict(x, line=line, residual=residual):
                return line(x)+residual(x)
            if all(predict(x)==y for x,y in obs): yield "affine+periodic:p"+str(p),predict


def select_candidates(obs,policy):
    names=("constant","periodic","polynomial")
    result=[]
    if policy=="single":
        ys=[y for _,y in obs]
        if len(set(ys))==1: name="constant"
        elif any(all(ys[i]==ys[i-p] for i in range(p,len(ys))) for p in range(2,6)): name="periodic"
        else: name="polynomial"
        names=(name,)
    for name in names:
        if name=="polynomial" and policy in ("composition","guard_fixed","guard_disagreement"):
            result.extend(composed(obs))
        fn=CATALOG[name][0](obs)
        if fn is not None and all(fn(x)==y for x,y in obs): result.append((name,fn))
    return result


def disagreement(candidates,pool):
    def score(x):
        return (len({fn(x) for _,fn in candidates}),abs(x),x)
    return max(pool,key=score)


def solve(query,policy):
    start=time.perf_counter_ns()
    obs=tuple((x,query(x)) for x in PROBES)
    candidates=select_candidates(obs,policy)
    initial=[name for name,_ in candidates]
    probes=[]
    if policy in ("guard_fixed","guard_disagreement"):
        pool=list(GUARD_POOL)
        for i in range(4):
            if not candidates: break
            x=FIXED[i] if policy=="guard_fixed" else disagreement(candidates,pool)
            pool.remove(x)
            y=query(x)
            before=len(candidates)
            candidates=[(name,fn) for name,fn in candidates if fn(x)==y]
            probes.append([x,y,before,len(candidates)])
    name,fn=candidates[0] if candidates else (None,None)
    return name,fn,dict(observations=obs,initial_candidates=initial,guard=probes,
                        queries=len(obs)+len(probes),search_ns=time.perf_counter_ns()-start)


def run(folder):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    rows=[]
    for seed in SEEDS:
        for i,case in enumerate(make_cases(seed)):
            for policy in POLICIES:
                name,fn,m=solve(lambda x:target(case,x),policy)
                ok=fn is not None and all(fn(x)==target(case,x) for x in FINAL)
                rows.append(dict(seed=seed,index=i,family=case[0],parameters=case[1],policy=policy,
                                 skill=name,success=ok,abstain=fn is None,**m))
    result=[]
    families=[]
    for p in POLICIES:
        rr=[x for x in rows if x["policy"]==p]
        def summarize(xs):
            return dict(n=len(xs),correct=sum(x["success"] for x in xs),
                        abstained=sum(x["abstain"] for x in xs),
                        wrong_answer=sum(not x["success"] and not x["abstain"] for x in xs),
                        mean_queries=sum(x["queries"] for x in xs)/len(xs),
                        mean_search_ns=sum(x["search_ns"] for x in xs)/len(xs))
        result.append(dict(policy=p,**summarize(rr)))
        for f in FAMILIES: families.append(dict(policy=p,family=f,**summarize([x for x in rr if x["family"]==f])))
    summary=dict(protocol="04CD-v1",seeds=SEEDS,episodes=len(rows),aggregate=result,by_family=families)
    (folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row)+"\n")
    print("SUMMARY_04CD="+json.dumps(summary))


class Tests(unittest.TestCase):
    def test_composition(self):
        case=("mixed",(2,1,-3,5))
        name,fn,m=solve(lambda x:target(case,x),"composition")
        self.assertTrue(name.startswith("affine+periodic"))
        self.assertTrue(all(fn(x)==target(case,x) for x in FINAL))
    def test_guard_abstains(self):
        name,fn,m=solve(lambda x: -3 if x<0 else 9,"guard_disagreement")
        self.assertIsNone(fn)
    def test_sets_and_counterexample(self):
        self.assertFalse(set(FINAL)&(set(PROBES)|set(GUARD_POOL)))
        case=("hidden_bump",(2,3,19,5))
        name,fn,m=solve(lambda x:target(case,x),"guard_disagreement")
        self.assertIsNotNone(fn)
        self.assertNotEqual(fn(19),target(case,19))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test: raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents: p.error("new output inside EXPERIMENTO_04 required")
    run(a.output)
