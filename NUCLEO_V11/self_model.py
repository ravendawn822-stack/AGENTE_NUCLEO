"""V11: empirical self-model and bounded curriculum selection.
Task labels are confined to the benchmark. All policy inputs are observations.
"""
import argparse,json,random,sys,time,unittest,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V10"))
import continuous as v10
v9=v10.v9
b=v10.b
SEEDS=(2070011,2100013,2130017)
POLICIES=("chronological","random","novelty","self_model")
LESSONS=16
TOTAL=160000
SHORT=3600
GRID=tuple((x,y) for x in range(-2,3) for y in range(-2,3))

def feature(values):
    g=dict(zip(GRID,values))
    scale=max(1,max(abs(v) for v in values))
    def avg(v):return sum(v)/len(v)
    def bounded(v):return min(1,v/scale)
    return (
        avg([g[x,y]==g[x,0]+g[0,y]-g[0,0] for x,y in GRID]),
        avg([g[x,y]==g[y,x] for x,y in GRID]),
        avg([g[x,y]==g[-x,y] for x,y in GRID]),
        avg([g[x,y]==g[x,-y] for x,y in GRID]),
        avg([g[x,y]==g[0,y] for x,y in GRID]),
        avg([g[x,y]==g[x,0] for x,y in GRID]),
        avg([v==0 for v in values]),
        avg([v>=0 for v in values]),
        bounded(avg([abs(g[x+1,y]-2*g[x,y]+g[x-1,y]) for x in (-1,0,1) for y in range(-2,3)])),
        bounded(avg([abs(g[x,y+1]-2*g[x,y]+g[x,y-1]) for x in range(-2,3) for y in (-1,0,1)])),
        bounded(avg([abs(g[x+1,y+1]-g[x+1,y]-g[x,y+1]+g[x,y]) for x in range(-2,2) for y in range(-2,2)])),
    )

def distance(a,b):
    return sum(abs(x-y) for x,y in zip(a,b))/len(a)

def coverage(f,reg):
    xs,ys=zip(*GRID);distances=[]
    for e in reg.values():
        try:v=v9.apply(e,xs,ys,{})
        except ZeroDivisionError:continue
        distances.append(distance(f,feature(v)))
    return 1-min(distances) if distances else 0.

def context(f,reg):
    return (*f,coverage(f,reg),len(reg)/v9.MAX_OPS)

def predict(ctx,history,key):
    # A deliberately simple empirical model. No hidden task class.
    # Beta(1,1) smoothing; similarity-weighted historical trials.
    eligible=[h for h in history if key!="deep_success" or not h["short_success"]]
    baseline=(1+sum(h[key] for h in eligible))/(2+len(eligible))
    weights=[1/(0.12+distance(ctx,h["context"]))**2 for h in eligible]
    local=(2*baseline+sum(w*h[key] for w,h in zip(weights,eligible)))/(2+sum(weights))
    return local,baseline

def task_view(t,seed):
    obs,held=v9.observations(seed)
    obs=list(dict.fromkeys((*GRID,*obs)))
    held=[p for p in held if p not in obs]
    answers=[b.target(t,x,y) for x,y in obs]
    return dict(observations=obs,answers=answers,feature=feature(answers[:len(GRID)])),held

def select(views,remaining,history,reg,policy,rng):
    if policy=="chronological":return remaining[0],[]
    if policy=="random":return rng.choice(remaining),[]
    ranked=[]
    for i in remaining:
        f=views[i]["feature"];ctx=context(f,reg)
        p,_=predict(ctx,history,"short_success");q,_=predict(ctx,history,"deep_success")
        # Prefer underrepresented observation profiles; no task names used.
        novelty=min((distance(f,h["context"][:len(f)]) for h in history),default=1.)
        # Need x expected learnability x novelty. Fixed developer-provided objective.
        value=novelty if policy=="novelty" else (1-p)*q*(.25+novelty)
        ranked.append(dict(index=i,priority=value,novelty=novelty,p_short=p,p_deep_given_short_failure=q))
    chosen=max(ranked,key=lambda r:(r["priority"],-r["index"]))
    return chosen["index"],ranked

def validate(e,reg,held,expected):
    return v9.check(e,held,expected,reg)

def trial(view,reg,cap,expected,held,train):
    # Inputs to the solver are observations only; expected is evaluator feedback.
    obs,answers=view["observations"],view["answers"]
    e,m=v10.solve(obs,answers,reg,min(SHORT,cap))
    short_e=e;short_ok=validate(e,reg,held,expected)
    stages=[dict(attempt="short",**m)];spent=m["candidates"]
    if train and e is None and cap>spent:
        e,m=v10.solve(obs,answers,reg,cap-spent)
        spent+=m["candidates"];stages.append(dict(attempt="deep",**m))
    ok=validate(e,reg,held,expected)
    assert spent<=cap
    def codes(t):
        if t is None:return []
        return ([t[0]] if t[0] in reg else [])+[k for c in t[1:] if isinstance(c,tuple) for k in codes(c)]
    return dict(candidate=e,expanded=v9.expand(e,reg) if e is not None else None,
        short_success=short_ok,short_emitted=short_e is not None,success=ok,emitted=e is not None,
        candidates=spent,stages=stages,opcodes=codes(e),cap=cap,
        diagnosis="verified_on_training_or_final_cases" if ok else "candidate_refuted" if e is not None else "no_candidate_in_budget")

def metric(rr):
    n=len(rr);ok=sum(r["success"] for r in rr);em=sum(r["emitted"] for r in rr)
    return dict(n=n,correct=ok,wrong=em-ok,abstained=n-em,
        candidates=sum(r["candidates"] for r in rr),acquired=sum(r.get("acquired",False) for r in rr),
        brier_model=sum((r["p_short"]-r["short_success"])**2 for r in rr)/n,
        brier_global=sum((r["p_global"]-r["short_success"])**2 for r in rr)/n,
        mean_prediction=sum(r["p_short"] for r in rr)/n)

def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    rows=[];agents=[];frozen=[]
    for seed in SEEDS:
        pool,final=v10.suite(seed)
        views=[];holds=[]
        for i,t in enumerate(pool):
            view,held=task_view(t,seed+i*701);views.append(view);holds.append(held)
        for policy in POLICIES:
            path=folder/f"{seed}_{policy}.sqlite3";mem=v9.Registry(path)
            db=mem.db
            db.execute("CREATE TABLE history(step INTEGER PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL)")
            db.commit()
            remaining=list(range(len(pool)));history=[];budget=TOTAL;rng=random.Random(seed^0xE413)
            for step in range(LESSONS):
                reg=mem.snapshot();i,ranking=select(views,remaining,history,reg,policy,rng)
                remaining.remove(i);view=views[i];t=pool[i];held=holds[i]
                ctx=context(view["feature"],reg);p,global_p=predict(ctx,history,"short_success")
                cap=min(v10.MAX_TASK,2*(budget//(LESSONS-step)),budget-SHORT*(LESSONS-step-1))
                assert cap>=SHORT
                expected=[b.target(t,x,y) for x,y in held]
                rr=trial(view,reg,cap,expected,held,True);budget-=rr["candidates"]
                acquired=False
                if rr["success"] and not rr["opcodes"] and v9.nodes(rr["expanded"])>=4:
                    acquired=mem.register(rr["expanded"],t["id"],held,expected)
                entry=dict(context=ctx,short_success=rr["short_success"],deep_success=rr["success"] and not rr["short_emitted"],
                    acquired=acquired,spent=rr["candidates"],index=i)
                history.append(entry)
                payload=v9.enc(entry)
                db.execute("INSERT INTO history VALUES(?,?,?)",(step,payload,v9.digest(entry)));db.commit()
                rows.append(dict(seed=seed,policy=policy,phase="train",step=step,task=t,context=ctx,
                    p_short=p,p_global=global_p,acquired=acquired,budget=budget,ranking=ranking,**rr))
                if step==7:
                    snap=v9.digest(mem.snapshot());mem.close();mem=v9.Registry(path);db=mem.db
                    restored=[json.loads(s) for s,h in db.execute("SELECT payload,sha FROM history ORDER BY step") if v9.digest(json.loads(s))==h]
                    assert v9.digest(restored)==v9.digest(history) and v9.digest(mem.snapshot())==snap
                    history=restored
            reg=mem.snapshot();mem.close()
            assert budget>=0
            agents.append(dict(seed=seed,policy=policy,skills=len(reg),remaining=budget,selected=[h["index"] for h in history],
                history_sha=v9.digest(history),registry_sha=v9.digest(reg)))
            frozen.append((seed,policy,reg,history,final))
    # All curricula and models frozen before the evaluator releases a single final outcome.
    for seed,policy,reg,history,final in frozen:
        snap=v9.digest([reg,history])
        for i,t in enumerate(final):
            view,held=task_view(t,seed*17+i*971);ctx=context(view["feature"],reg)
            p,g=predict(ctx,history,"short_success")
            expected=[b.target(t,x,y) for x,y in held]
            rr=trial(view,reg,SHORT,expected,held,False)
            rows.append(dict(seed=seed,policy=policy,phase="final",task=t,context=ctx,p_short=p,p_global=g,**rr))
        assert snap==v9.digest([reg,history])
    # Common empty-memory baseline, evaluated only after all curricula are frozen.
    for seed in SEEDS:
        final=v10.suite(seed)[1]
        for i,t in enumerate(final):
            view,held=task_view(t,seed*17+i*971);expected=[b.target(t,x,y) for x,y in held]
            rr=trial(view,{},SHORT,expected,held,False)
            rows.append(dict(seed=seed,policy="empty",phase="final",task=t,p_short=.5,p_global=.5,**rr))
    result=dict(protocol="V11-self-model-v1",seeds=SEEDS,episodes=len(rows),agents=agents,
        aggregate=[dict(policy=p,**metric([r for r in rows if r["phase"]=="final" and r["policy"]==p])) for p in (*POLICIES,"empty")],
        training=[dict(policy=p,**metric([r for r in rows if r["phase"]=="train" and r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metric([r for r in rows if r["phase"]=="final" and r["policy"]==p and r["task"]["family"]==f])) for p in POLICIES for f in ("linked","unrelated","outside")])
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (folder/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(v9.enc(r)+"\n")
    print("SUMMARY_V11="+v9.enc(result))

class Tests(unittest.TestCase):
    def test_features(self):
        f=feature([x+y for x,y in GRID]);self.assertEqual(f[0],1);self.assertEqual(f[1],1)
        self.assertEqual(distance(f,f),0)
    def test_predict(self):
        f=(0.,)*13
        r=[dict(context=f,short_success=True,deep_success=False)]
        self.assertGreater(predict(f,r,"short_success")[0],.5)
        self.assertEqual(predict(f,r,"deep_success"),(.5,.5))
    def test_selection(self):
        views=[dict(feature=(0.,)*11),dict(feature=(1.,)*11)]
        h=[dict(context=(0.,)*13,short_success=True,deep_success=False)]
        self.assertEqual(select(views,[0,1],h,{},"novelty",random.Random(1))[0],1)
    def test_budget(self):
        budget=TOTAL
        for left in range(LESSONS,0,-1):
            cap=min(v10.MAX_TASK,2*(budget//left),budget-SHORT*(left-1))
            self.assertGreaterEqual(cap,SHORT);budget-=cap
        self.assertGreaterEqual(budget,0)
    def test_suite(self):
        for s in SEEDS:self.assertEqual(tuple(map(len,v10.suite(s))),(32,32))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output inside V11 required")
    run(a.output)
