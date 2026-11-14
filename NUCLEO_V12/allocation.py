"""V12: bounded allocation of extra investigation after an initial failure."""
import argparse, json, random, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NUCLEO_V11"))
import self_model as m
v10, v9, b = m.v10, m.v9, m.b
SEEDS = (2160013, 2190017, 2220023, 2250031)
SHORT, EXTRA, SLOTS = 3600, 8400, 12
POLICIES = ("short_only", "chronological", "random", "novelty", "self_model")

def choose(items, policy, seed):
    if policy == "short_only":
        return []
    if policy == "chronological":
        seq = sorted(items, key=lambda a: a["i"])
    elif policy == "random":
        seq = list(items)
        random.Random(seed ^ 0xA129).shuffle(seq)
    elif policy == "novelty":
        seq = sorted(items, key=lambda a: (-a["novelty"], a["i"]))
    elif policy == "self_model":
        seq = sorted(items, key=lambda a: (-a["q"], a["i"]))
    else:
        raise ValueError(policy)
    return [a["i"] for a in seq[:SLOTS]]

def run(folder):
    folder.mkdir(parents=True, exist_ok=False)
    rows, trained = [], []
    for seed in SEEDS:
        pool, final = v10.suite(seed)
        history = []
        path = folder / f"{seed}.sqlite3"
        mem = v9.Registry(path)
        for i,t in enumerate(pool):
            reg = mem.snapshot()
            view,held = m.task_view(t,seed+i*701)
            ctx = m.context(view["feature"],reg)
            expected = [b.target(t,x,y) for x,y in held]
            rr = m.trial(view,reg,SHORT+EXTRA,expected,held,True)
            acquired = False
            if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"]) >= 4:
                acquired = mem.register(rr["expanded"],t["id"],held,expected)
            history.append(dict(context=ctx,short_success=rr["short_success"],
                deep_success=rr["success"] and not rr["short_emitted"],
                acquired=acquired,spent=rr["candidates"]))
        reg = mem.snapshot()
        mem.close()
        trained.append(dict(seed=seed,skills=len(reg),history=history,
                            registry_sha=v9.digest(reg)))
        frozen = v9.digest([reg,history])
        initial, eligible = [], []
        for i,t in enumerate(final):
            view,held = m.task_view(t,seed*17+i*971)
            ctx = m.context(view["feature"],reg)
            q,g = m.predict(ctx,history,"deep_success")
            novelty = min((m.distance(view["feature"],h["context"][:11])
                           for h in history),default=1.)
            e,meta = v10.solve(view["observations"],view["answers"],reg,SHORT)
            rec = dict(i=i,q=q,global_q=g,novelty=novelty)
            initial.append((t,view,held,e,meta,rec))
            if e is None:
                eligible.append(rec)
        # Freeze all allocations before evaluating any final outcome.
        plans = {p:choose(eligible,p,seed) for p in POLICIES}
        assert all(len(x)<=SLOTS and len(x)==len(set(x)) for x in plans.values())
        deep = {}
        for i in sorted(set().union(*map(set,plans.values()))):
            _,view,_,_,_,_ = initial[i]
            deep[i] = v10.solve(view["observations"],view["answers"],reg,EXTRA)
        for policy,plan in plans.items():
            cost = 0
            for i,(t,view,held,e,meta,rec) in enumerate(initial):
                used = meta["candidates"]
                escalated = i in plan
                if escalated:
                    e,dmeta = deep[i]
                    used += dmeta["candidates"]
                expected = [b.target(t,x,y) for x,y in held]
                ok = v9.check(e,held,expected,reg)
                rows.append(dict(seed=seed,policy=policy,task=t,**rec,
                    escalated=escalated,success=ok,emitted=e is not None,
                    candidates=used,candidate=e))
                cost += used
            assert cost <= len(final)*SHORT + SLOTS*EXTRA
        assert frozen == v9.digest([reg,history])
    def metric(rr):
        n=len(rr); ok=sum(r["success"] for r in rr); em=sum(r["emitted"] for r in rr)
        return dict(n=n,correct=ok,wrong=em-ok,abstained=n-em,
            candidates=sum(r["candidates"] for r in rr),
            escalated=sum(r["escalated"] for r in rr),
            escalated_correct=sum(r["escalated"] and r["success"] for r in rr))
    result=dict(protocol="V12-allocation-v1",seeds=SEEDS,training=trained,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_seed=[dict(seed=s,policy=p,**metric([r for r in rows if r["policy"]==p and r["seed"]==s]))
                 for s in SEEDS for p in POLICIES])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for row in rows:
            f.write(v9.enc(row)+"\n")
    print(json.dumps(result["aggregate"],indent=2))

class Tests(unittest.TestCase):
    def test_choose(self):
        items=[dict(i=i,q=i/20,novelty=(19-i)/20) for i in range(20)]
        self.assertEqual(choose(items,"self_model",1),list(range(19,7,-1)))
        self.assertEqual(choose(items,"novelty",1),list(range(12)))
        self.assertEqual(choose(items,"short_only",1),[])
        self.assertEqual(choose(items,"random",1),choose(items,"random",1))
        for p in POLICIES:
            self.assertEqual(len(set(choose(items,p,1))),len(choose(items,p,1)))
            self.assertLessEqual(len(choose(items[:3],p,1)),3)
    def test_seeds(self):
        self.assertTrue(set(SEEDS).isdisjoint(m.SEEDS))
        self.assertTrue(set(SEEDS).isdisjoint(v10.SEEDS))
        for s in SEEDS:
            a,c=v10.suite(s)
            self.assertEqual((len(a),len(c)),(32,32))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--output",type=Path)
    a=parser.parse_args()
    if a.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:
        parser.error("new output inside V12 required")
    run(a.output)
