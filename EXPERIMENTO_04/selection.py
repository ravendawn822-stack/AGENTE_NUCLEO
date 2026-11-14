"""04B: strategy selection, not invention. Standard library only."""
import argparse
import hashlib
import json
import math
import random
import sqlite3
import time
import unittest
from fractions import Fraction
from pathlib import Path
from pilot import CATALOG, Library, PROBES, source_hash

ROOT = Path(__file__).resolve().parent
NAMES = tuple(sorted(CATALOG))
SEEDS = (104729, 130363, 155921, 196613, 262147)
POLICIES = ("adaptive", "global", "frozen", "fixed", "random")
FAMILIES = ("constant", "periodic", "polynomial", "step", "mixed")
CHECKS = (-17,-13,-11,-8,-6,-5,5,6,8,11,13,17)
FEEDBACK = (-12,-7,7,12)
FIXTURES = {
    "constant": [(lambda x: 3, True), (lambda x: x, False)],
    "periodic": [(lambda x: x%3, True), (lambda x: x*x, False)],
    "polynomial": [(lambda x: x*x+2*x-1, True), (lambda x: x%3, False)],
}


def suite(seed, split, per_family):
    rng = random.Random(seed ^ (0x132ABC if split == "train" else 0x987DEF))
    cases = []
    for family in FAMILIES:
        for i in range(per_family):
            if family == "constant":
                data = [rng.choice(range(-80,81))]
            elif family == "periodic":
                p = rng.randint(2,5)
                data = rng.sample(range(-30,31),p)
            elif family == "polynomial":
                d = rng.randint(1,8)
                data = [rng.randint(-9,9) for _ in range(d)] + [rng.choice((-5,-3,-1,1,3,5))]
            elif family == "step":
                data = [rng.randint(-3,3)] + rng.sample(range(-30,31),2)
            else:
                data = [rng.choice((-2,-1,1,2)), rng.randint(2,5), rng.randint(-9,9)]
            cases.append((family, tuple(data)))
    rng.shuffle(cases)
    return cases


def target(case, x):
    family, data = case
    if family == "constant": return data[0]
    if family == "periodic": return data[x % len(data)]
    if family == "polynomial": return sum(a*x**i for i,a in enumerate(data))
    if family == "step": return data[1] if x < data[0] else data[2]
    return data[0]*x + x%data[1] + data[2]


def unique_sets(seed, ntrain, ntest):
    train = list(dict.fromkeys(suite(seed, "train", ntrain*2)))
    test = [c for c in dict.fromkeys(suite(seed, "test", ntest*3)) if c not in set(train)]
    def balanced(cases, n):
        counts = dict.fromkeys(FAMILIES, 0)
        result = []
        for c in cases:
            if counts[c[0]] < n:
                counts[c[0]] += 1
                result.append(c)
        if min(counts.values()) != n:
            raise ValueError("insufficient unique cases")
        return result
    return balanced(train,ntrain), balanced(test,ntest)


def context(obs):
    ys = [y for _,y in obs]
    if len(set(ys)) == 1: return "flat"
    if any(all(ys[i]==ys[i-p] for i in range(p,len(ys))) for p in range(2,6)):
        return "repeat"
    dif = ys
    for degree in range(1,5):
        dif = [b-a for a,b in zip(dif,dif[1:])]
        if len(set(dif)) == 1: return "low_degree"
    return "other"


def choose(policy, obs, stats, rng, training):
    c = context(obs)
    if policy == "random": return rng.choice(NAMES), {}
    if policy == "fixed":
        return {"flat":"constant","repeat":"periodic","low_degree":"polynomial","other":"polynomial"}[c], {}
    key = "*" if policy == "global" else c
    scores = {}
    for name in NAMES:
        n,s = stats.get((key,name),(0,0))
        score = (s+1)/(n+2)
        if training and policy != "frozen": score += .65/math.sqrt(n+1)
        scores[name] = score
    best = max(scores.values())
    return rng.choice([name for name in NAMES if scores[name]==best]), scores


def assess_predictor(pred, case, points):
    if pred is None: return False
    return all(pred(x) == target(case,x) for x in points)


def fingerprint(stats):
    return hashlib.sha256(json.dumps(sorted((k[0],k[1],v[0],v[1]) for k,v in stats.items())).encode()).hexdigest()


def episode(case, policy, stats, rng, active, training):
    start = time.perf_counter_ns()
    obs = tuple((x,target(case,x)) for x in PROBES)
    skill, scores = choose(policy,obs,stats,rng,training)
    pred = active[skill](obs)
    consistent = pred is not None and all(pred(x)==y for x,y in obs)
    # The selector has no access to the reserved target or feedback until after committing.
    search_ns = time.perf_counter_ns()-start
    check_start = time.perf_counter_ns()
    if training:
        valid = consistent and assess_predictor(pred,case,FEEDBACK)
    else:
        valid = consistent and assess_predictor(pred,case,CHECKS)
    check_ns = time.perf_counter_ns()-check_start
    update_start = time.perf_counter_ns()
    c = context(obs)
    if training and policy in ("adaptive","global"):
        key = ("*" if policy=="global" else c,skill)
        n,s = stats.get(key,(0,0))
        stats[key] = (n+1,s+int(valid))
    update_ns = time.perf_counter_ns()-update_start
    return dict(family=case[0], parameters=case[1], observations=obs, context=c, skill=skill,
                scores=scores, consistent=consistent, success=valid, abstain=not consistent,
                search_ns=search_ns, check_ns=check_ns, update_ns=update_ns,
                total_ns=time.perf_counter_ns()-start)


def run(folder,ntrain=40,ntest=20,seeds=SEEDS):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    lib=Library(folder/"memory.sqlite3")
    acquisition_start=time.perf_counter_ns()
    for name,fixtures in FIXTURES.items():
        if not lib.acquire(name,fixtures): raise RuntimeError("failed acquisition")
    acquisition_ns=time.perf_counter_ns()-acquisition_start
    lib.close()
    lib=Library(folder/"memory.sqlite3")
    active=lib.active()
    assert set(active)==set(NAMES)
    lib.db.executescript("""
      CREATE TABLE episodes(seed INTEGER, policy TEXT, phase TEXT, idx INTEGER, payload TEXT,
      PRIMARY KEY(seed,policy,phase,idx));
      CREATE TABLE strategy_stats(seed INTEGER, policy TEXT, context TEXT, skill TEXT, attempts INTEGER, successes INTEGER,
      PRIMARY KEY(seed,policy,context,skill));
    """)
    summary=[]
    try:
        for seed in seeds:
            training,evaluation=unique_sets(seed,ntrain,ntest)
            assert not set(training)&set(evaluation)
            for pi,policy in enumerate(POLICIES):
                stats={}
                rng=random.Random(seed+pi*9391)
                eval_rows=[]
                for phase,cases in (("train",training),("test",evaluation)):
                    before=fingerprint(stats)
                    for i,case in enumerate(cases):
                        row=episode(case,policy,stats,rng,active,phase=="train")
                        lib.db.execute("INSERT INTO episodes VALUES(?,?,?,?,?)",(seed,policy,phase,i,json.dumps(row)))
                        if phase=="test": eval_rows.append(row)
                    if phase=="test": assert before==fingerprint(stats),"evaluation changed memory"
                    lib.db.commit()
                for (c,skill),(n,s) in stats.items():
                    lib.db.execute("INSERT INTO strategy_stats VALUES(?,?,?,?,?,?)",(seed,policy,c,skill,n,s))
                lib.db.commit()
                summary.append(dict(seed=seed,policy=policy,n=len(eval_rows),
                    correct=sum(r["success"] for r in eval_rows),
                    supported_correct=sum(r["success"] for r in eval_rows if r["family"] in FAMILIES[:3]),
                    supported=sum(r["family"] in FAMILIES[:3] for r in eval_rows),
                    unsupported_accepted=sum(r["success"] for r in eval_rows if r["family"] in FAMILIES[3:]),
                    abstain=sum(r["abstain"] for r in eval_rows),
                    wrong_nonabstain=sum(not r["success"] and not r["abstain"] for r in eval_rows),
                    mean_total_ns=sum(r["total_ns"] for r in eval_rows)/len(eval_rows),
                    mean_search_ns=sum(r["search_ns"] for r in eval_rows)/len(eval_rows),
                    training_attempts=sum(v[0] for v in stats.values()),memory_sha256=fingerprint(stats)))
        with (folder/"raw.jsonl").open("w",encoding="utf-8") as out:
            for seed,policy,phase,idx,payload in lib.db.execute("SELECT * FROM episodes ORDER BY seed,policy,phase,idx"):
                out.write(json.dumps(dict(seed=seed,policy=policy,phase=phase,index=idx,**json.loads(payload)))+"\n")
    finally:
        lib.close()
    aggregate=[]
    for policy in POLICIES:
        rows=[r for r in summary if r["policy"]==policy]
        aggregate.append(dict(policy=policy, n=sum(r["n"] for r in rows),correct=sum(r["correct"] for r in rows),
            supported_correct=sum(r["supported_correct"] for r in rows),supported=sum(r["supported"] for r in rows),
            wrong_nonabstain=sum(r["wrong_nonabstain"] for r in rows),
            abstain=sum(r["abstain"] for r in rows),
            mean_total_ns=sum(r["mean_total_ns"] for r in rows)/len(rows),
            training_attempts=sum(r["training_attempts"] for r in rows)))
    result=dict(protocol="04B-v1",seeds=list(seeds),train_per_family=ntrain,test_per_family=ntest,
                acquisition_ns=acquisition_ns,versions={n:source_hash(fn) for n,fn in active.items()},
                aggregate=aggregate,by_seed=summary)
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
    return result


class Tests(unittest.TestCase):
    def test_splits(self):
        for seed in SEEDS:
            a,b=unique_sets(seed,40,20)
            self.assertEqual((len(a),len(b)),(200,100))
            self.assertFalse(set(a)&set(b))
    def test_frozen_evaluation(self):
        active={n:f for n,(f,_) in CATALOG.items()}
        stats={}
        case=("constant",(6,))
        rng=random.Random(1)
        for _ in range(10): episode(case,"adaptive",stats,rng,active,True)
        before=fingerprint(stats)
        episode(case,"adaptive",stats,rng,active,False)
        self.assertEqual(before,fingerprint(stats))
        self.assertEqual(sum(v[0] for v in stats.values()),10)
    def test_context_and_no_label(self):
        obs=tuple((x,3) for x in PROBES)
        self.assertEqual(context(obs),"flat")
        self.assertEqual(choose("fixed",obs,{},random.Random(1),False)[0],"constant")
    def test_reference(self):
        active={n:f for n,(f,_) in CATALOG.items()}
        r=episode(("polynomial",(3,-2,4)),"fixed",{},random.Random(1),active,False)
        self.assertTrue(r["success"])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.output is None or ROOT not in args.output.resolve().parents:
        p.error("--output must be a new directory inside EXPERIMENTO_04")
    run(args.output)
