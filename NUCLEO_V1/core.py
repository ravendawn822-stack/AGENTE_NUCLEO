"""NUCLEO_V1: one persistent agent, three bounded environments, no LLM."""
import argparse
import hashlib
import html
import json
import math
import random
import sqlite3
import sys
import time
import unittest
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
for folder in ("EXPERIMENTO_04","EXPERIMENTO_05","EXPERIMENTO_05B_07B","EXPERIMENTO_05C_09A","EXPERIMENTO_06_08"):
    sys.path.insert(0,str(ROOT.parent/folder))
import composition as scalar
import curriculum as sequence
import investigate as project
import transfer as teacher
from programs import FOLD,execute
SEEDS=(324161,350377,399989)
DOMAINS=("scalar","sequence","project")
POLICIES=("fixed","memory","teacher","autonomous")
STEPS=24
CHECKPOINTS=(0,24)
CAP=18
OBJECTIVE="maximize_validated_software_problem_resolution_under_bounded_resources"


def dump(obj):return json.dumps(obj,sort_keys=True,separators=(",",":"))
def digest(obj):return hashlib.sha256(dump(obj).encode()).hexdigest()
def probability(h):return (sum(h)+1)/(len(h)+2)
def blank():
    return dict(objective=OBJECTIVE,step=0,skills=[],history={d:[] for d in DOMAINS},
                teacher_requested=False,teacher_skills=[],teacher_evidence=[],consumed=[])


class Agent:
    def __init__(self,path,policy,seed):
        self.policy=policy;self.seed=seed
        self.db=sqlite3.connect(path)
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,sha TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,kind TEXT,step INTEGER,payload TEXT);
          CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY,phase TEXT,checkpoint INTEGER,uid TEXT,payload TEXT,
            UNIQUE(phase,checkpoint,uid));
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        """)
        identity=dump([policy,seed,OBJECTIVE])
        old=self.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
        if old and old[0]!=identity:raise ValueError("state belongs to another agent")
        if not old:self.db.execute("INSERT INTO meta VALUES('identity',?)",(identity,))
        row=self.db.execute("SELECT payload,sha FROM state WHERE id=1").fetchone()
        if row:
            self.state=json.loads(row[0])
            if digest(self.state)!=row[1]:raise ValueError("invalid persistent state")
        else:
            self.state=blank();self.persist()
        self.db.commit()
    def persist(self):
        self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?,?)",(dump(self.state),digest(self.state)))
    def event(self,kind,**payload):
        self.db.execute("INSERT INTO events(kind,step,payload) VALUES(?,?,?)",
                        (kind,self.state["step"],dump(payload)))
    def close(self):self.db.close()
    def capabilities(self):
        return {d:dict(attempts=len(h),successes=sum(h),estimate=probability(h)) for d,h in self.state["history"].items()}
    def goal(self,available):
        # Only resource availability and previous outcomes reach the scheduler.
        step=self.state["step"]
        if self.policy!="autonomous":
            chosen=next(DOMAINS[(step+i)%len(DOMAINS)] for i in range(len(DOMAINS)) if available[DOMAINS[(step+i)%len(DOMAINS)]])
            return chosen,{}
        scores={}
        for d in DOMAINS:
            if not available[d]:continue
            h=self.state["history"][d]
            recent=h[-4:];past=h[-8:-4]
            gain=max(0,probability(recent)-probability(past))
            scores[d]=gain+.4/math.sqrt(len(h)+1)+(.25 if not h else 0)
        rng=random.Random(self.seed+step*7919)
        best=max(scores.values())
        return rng.choice([d for d,s in scores.items() if s==best]),scores
    def memory_expressions(self):
        return [sequence.freeze(x["expr"]) for x in self.state["skills"]+self.state["teacher_skills"]]
    def decide(self,view):
        start=time.perf_counter_ns();domain=view["domain"];query=view["query"]
        metrics={"domain":domain}
        if domain=="scalar":
            name,fn,m=scalar.solve(query,"guard_fixed")
            metrics.update(m,method=name,emitted=fn is not None,candidates=len(m["initial_candidates"]))
            prediction=fn
        elif domain=="sequence":
            init,pairs,ys,q,consistent=sequence.transitions(query,sequence.observation_sequences(view["seed"]))
            mem=self.memory_expressions() if self.policy!="fixed" else []
            plan=[("cold",[],3600)] if not mem else [("cold",[],1800),("memory",mem,1800)]
            attempts=[];expr=None
            if consistent:
                for name,macros,cap in plan:
                    expr,n=sequence.synthesize(pairs,ys,macros,limit=cap)
                    attempts.append(dict(channel=name,candidates=n,limit=cap,found=expr is not None))
                    if expr is not None:break
            program=(FOLD,init,expr) if expr is not None else None
            def prediction(x):
                try:return execute(program,x)
                except (ValueError,ZeroDivisionError):return None
            metrics.update(method=attempts[-1]["channel"] if attempts else None,emitted=program is not None,
                           candidates=sum(x["candidates"] for x in attempts),queries=q,
                           attempts=attempts,program=program,observations=list(zip(pairs,ys)))
            if program is None:prediction=None
        elif domain=="project":
            patch,emitted,expr,m=project.investigate(project.VirtualProject(view["files"]),view["entry"],query,"graph_active",view["seed"])
            metrics.update(m,method="graph_active",emitted=emitted,patch=patch,
                           oracle_queries=len(m["queries"]))
            prediction=(lambda x:project.evaluate(expr,view["entry"],x,patch)) if emitted else None
        else:raise ValueError("unknown task interface")
        metrics["decision_ns"]=time.perf_counter_ns()-start
        metrics["capability_estimate"]=self.capabilities()[domain]["estimate"]
        if domain=="scalar":metrics["oracle_queries"]=metrics["queries"]
        elif domain=="sequence":metrics["oracle_queries"]=metrics["queries"]
        return prediction,metrics
    def acquire_teacher(self):
        # An offline, explicit source with bounded DSL proposals and no external requests.
        p=ROOT.parent/"EXPERIMENTO_05C_09A"/"TEACHER_PROPOSALS.json"
        proposals=json.loads(p.read_text(encoding="utf-8"))
        mem,records=teacher.verify_teacher(proposals)
        self.state["teacher_requested"]=True
        self.state["teacher_evidence"]=records
        accepted={dump(r["expr"]):r for r in records if r["accepted"]}
        self.state["teacher_skills"]=[dict(expr=e,origin="offline_teacher",id=accepted[dump(e)]["id"]) for e in mem]
        self.event("teacher_request",reason="failed_sequence_training",source="offline_proposal_pack",sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        self.event("teacher_validated",accepted=[r["id"] for r in records if r["accepted"]],
                   rejected=[r["id"] for r in records if not r["accepted"]])
    def train(self,task,scores):
        # Feedback comes from a separate environment after a decision.
        if task["uid"] in self.state["consumed"]:raise ValueError("training task already consumed")
        started=time.perf_counter_ns()
        self.event("goal_selected",domain=task["domain"],scores=scores,objective=OBJECTIVE)
        pred,m=self.decide(view_of(task))
        result=assess(task,pred)
        d=task["domain"];self.state["history"][d].append(int(result["success"]))
        self.event("decision",uid=task["uid"],domain=d,method=m.get("method"),emitted=m["emitted"],
                   candidates=m["candidates"],queries=m["oracle_queries"],decision_ns=m["decision_ns"])
        self.event("training_feedback",uid=task["uid"],success=result["success"],emitted=m["emitted"])
        if d=="sequence" and result["success"] and self.policy!="fixed":
            existing={dump(s["expr"]) for s in self.state["skills"]}
            p=sequence.freeze(m["program"])
            for e in sequence.subtrees(p[2]):
                if dump(e) not in existing:
                    self.state["skills"].append(dict(expr=e,origin=task["uid"]))
                    existing.add(dump(e));self.event("skill_acquired",origin=task["uid"],expr=e)
                    if len(self.state["skills"])>CAP:
                        removed=self.state["skills"].pop(0);self.event("skill_archived",origin=removed["origin"],expr=removed["expr"])
        if d=="sequence" and not result["success"] and self.policy in ("teacher","autonomous") and not self.state["teacher_requested"]:
            self.acquire_teacher()
        self.state["consumed"].append(task["uid"]);self.state["step"]+=1
        row=dict(uid=task["uid"],phase="training",policy=self.policy,seed=self.seed,checkpoint=self.state["step"],
                 goal_scores=scores,**m,**result,skills=len(self.state["skills"]),teacher_skills=len(self.state["teacher_skills"]),
                 total_ns=time.perf_counter_ns()-started)
        self.db.execute("INSERT INTO episodes(phase,checkpoint,uid,payload) VALUES(?,?,?,?)",
                        ("training",self.state["step"],task["uid"],dump(row)))
        self.persist();self.db.commit()
        return row
    def evaluate(self,tasks):
        before=digest(self.state);rows=[]
        for task in tasks:
            start=time.perf_counter_ns()
            pred,m=self.decide(view_of(task));result=assess(task,pred)
            row=dict(uid=task["uid"],phase="evaluation",policy=self.policy,seed=self.seed,checkpoint=self.state["step"],
                 **m,**result,skills=len(self.state["skills"]),teacher_skills=len(self.state["teacher_skills"]),
                 total_ns=time.perf_counter_ns()-start)
            rows.append(row)
            self.db.execute("INSERT INTO episodes(phase,checkpoint,uid,payload) VALUES(?,?,?,?)",
                           ("evaluation",self.state["step"],task["uid"],dump(row)))
        assert before==digest(self.state)
        assert before==self.db.execute("SELECT sha FROM state WHERE id=1").fetchone()[0]
        self.event("evaluation_complete",checkpoint=self.state["step"],n=len(rows),
                   correct=sum(x["success"] for x in rows),state_sha=before)
        self.db.commit()
        return rows


def suite(seed):
    train={d:[] for d in DOMAINS};test=[]
    counters={}
    for case in scalar.make_cases(seed,4):
        f=case[0];idx=counters.get(f,0);counters[f]=idx+1
        kind="training" if idx<2 else "evaluation"
        t=dict(domain="scalar",uid=f"{seed}/scalar/{f}/{idx}",case=case,seed=seed+idx)
        (train["scalar"] if kind=="training" else test).append(t)
    seqtrain,seqtest=sequence.task_pool(seed)
    for i,case in enumerate(c for f in sequence.FAMILIES for c in seqtrain[f]):
        train["sequence"].append(dict(domain="sequence",uid=f"{seed}/sequence/train/{i}",case=case,seed=seed*17+i))
    for i,case in enumerate(seqtest):
        test.append(dict(domain="sequence",uid=f"{seed}/sequence/test/{i}",case=case,seed=seed*31+i))
    for i in range(24):
        family=project.FAMILIES[i%3]
        files,clean,entry,changes=project.build(seed,i,family)
        t=dict(domain="project",uid=f"{seed}/project/{i}",files=files,clean=clean,entry=entry,changes=changes,
               seed=seed*43+i,family=family)
        (train["project"] if i<12 else test).append(t)
    rng=random.Random(seed)
    for v in train.values():rng.shuffle(v)
    rng.shuffle(test)
    assert len(test)==52
    assert not {t["uid"] for t in test}&{t["uid"] for v in train.values() for t in v}
    return train,test


def view_of(task):
    d=task["domain"]
    if d=="scalar":q=lambda x:scalar.target(task["case"],x)
    elif d=="sequence":q=lambda x:sequence.oracle(task["case"],x)
    else:
        truth,_=project.perceive(project.VirtualProject(task["clean"]),task["entry"],"graph")
        q=lambda x:project.evaluate(truth,task["entry"],x)
    view=dict(domain=d,query=q,seed=task["seed"])
    if d=="project":view.update(files=dict(task["files"]),entry=task["entry"])
    return view


def assess(task,predict):
    d=task["domain"]
    points=scalar.FINAL if d=="scalar" else sequence.check_sequences(task["seed"]) if d=="sequence" else project.FINAL
    q=view_of(task)["query"];checks=[]
    if predict is not None:
        for x in points:
            expected=q(x);observed=predict(x)
            # Fractions are stored exactly as strings, equality is evaluated before serialization.
            checks.append(dict(input=x,expected=str(expected),observed=str(observed),match=expected==observed))
    return dict(success=predict is not None and all(x["match"] for x in checks),checks=checks,abstained=predict is None)


def summarize(rows):
    n=len(rows);correct=sum(x["success"] for x in rows);abstain=sum(x["abstained"] for x in rows)
    return dict(n=n,correct=correct,abstained=abstain,wrong=n-correct-abstain,
                mean_queries=sum(x["oracle_queries"] for x in rows)/n,mean_candidates=sum(x["candidates"] for x in rows)/n,
                mean_decision_ns=sum(x["decision_ns"] for x in rows)/n,mean_total_ns=sum(x["total_ns"] for x in rows)/n,
                brier=sum((x["capability_estimate"]-int(x["success"]))**2 for x in rows)/n)


def report(folder,summary):
    # Static, local, escaped HTML derived exclusively from recorded metrics.
    def table(rows,cols):
        return "<table><thead><tr>"+"".join("<th>"+html.escape(c)+"</th>" for c in cols)+"</tr></thead><tbody>"+"".join(
          "<tr>"+"".join("<td>"+html.escape(str(row.get(c,"")))+"</td>" for c in cols)+"</tr>" for row in rows)+"</tbody></table>"
    def fmt(r):
        x=dict(r);x["mean_ms"]=round(r["mean_decision_ns"]/1e6,3);x["brier"]=round(r["brier"],4);return x
    s='<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>NUCLEO V1</title><style>body{background:#101822;color:#e6edf3;font:15px system-ui;margin:2rem}table{border-collapse:collapse;width:100%;margin:1rem 0 2rem}td,th{padding:8px;text-align:left;border-bottom:1px solid #394b60}th{color:#84c5ff}h1,h2{color:#9ad5ff}small{color:#b8c9d5}</style><h1>NUCLEO_V1 — execução registrada</h1>'
    s+="<p>Episódios: "+str(summary["episodes"])+" · sementes: "+html.escape(str(summary["seeds"]))+"</p>"
    cols=["policy","checkpoint","n","correct","wrong","abstained","mean_ms","brier"]
    s+="<h2>Avaliação global</h2>"+table([fmt(x) for x in summary["evaluation"]],cols)
    s+="<h2>Por domínio</h2>"+table([fmt(x) for x in summary["by_domain"]],["domain",*cols])
    s+="<h2>Memória e objetivos finais</h2>"+table(summary["agents"],["seed","policy","skills","teacher_skills","teacher_requested","training_by_domain"])
    s+="<small>Relatório estático, não simulação nem monitoramento ao vivo. Avaliação de tarefas sintéticas; Brier é erro quadrático da estimativa de capacidade.</small></html>"
    (folder/"painel.html").write_text(s,encoding="utf-8")


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    allrows=[];states=[];alltasks=[]
    for seed in SEEDS:
        train,test=suite(seed)
        alltasks.extend(dict(phase="training",**t) for v in train.values() for t in v)
        alltasks.extend(dict(phase="evaluation",**t) for t in test)
        for policy in POLICIES:
            pool={d:list(v) for d,v in train.items()}
            path=folder/f"{policy}_{seed}.sqlite3"
            agent=Agent(path,policy,seed)
            try:
                allrows.extend(agent.evaluate(test))
                for step in range(STEPS):
                    d,scores=agent.goal({k:bool(v) for k,v in pool.items()})
                    task=pool[d].pop(0);allrows.append(agent.train(task,scores))
                    if step==11:
                        sha=digest(agent.state);agent.close();agent=Agent(path,policy,seed)
                        assert digest(agent.state)==sha
                        agent.event("persistent_state_reopened",sha256=sha);agent.db.commit()
                allrows.extend(agent.evaluate(test))
                states.append(dict(seed=seed,policy=policy,skills=len(agent.state["skills"]),
                    teacher_skills=len(agent.state["teacher_skills"]),teacher_requested=agent.state["teacher_requested"],
                    training_by_domain={d:len(h) for d,h in agent.state["history"].items()},sha256=digest(agent.state),
                    capabilities=agent.capabilities()))
            finally:agent.close()
    ev=[x for x in allrows if x["phase"]=="evaluation"]
    aggregate=[dict(policy=p,checkpoint=c,**summarize([x for x in ev if x["policy"]==p and x["checkpoint"]==c])) for p in POLICIES for c in CHECKPOINTS]
    bydomain=[dict(policy=p,checkpoint=c,domain=d,**summarize([x for x in ev if x["policy"]==p and x["checkpoint"]==c and x["domain"]==d])) for p in POLICIES for c in CHECKPOINTS for d in DOMAINS]
    for file,items in (("raw.jsonl",allrows),("tasks.jsonl",alltasks)):
        with (folder/file).open("w",encoding="utf-8") as f:
            for row in items:f.write(dump(row)+"\n")
    summary=dict(protocol="NUCLEO_V1-v1",seeds=SEEDS,episodes=len(allrows),evaluation=aggregate,by_domain=bydomain,agents=states)
    (folder/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    report(folder,summary)
    print("SUMMARY_NUCLEO="+dump(summary))


class Tests(unittest.TestCase):
    def test_suite(self):
        for seed in SEEDS:
            a,b=suite(seed);self.assertEqual(len(b),52)
            self.assertEqual({t["domain"] for t in b},set(DOMAINS))
    def test_single_entity_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"a.db";a=Agent(p,"teacher",SEEDS[0])
            train,test=suite(SEEDS[0]);a.evaluate(test[:2]);self.assertEqual(a.state,blank())
            t=train["sequence"][0];a.train(t,{})
            sha=digest(a.state);a.close();a=Agent(p,"teacher",SEEDS[0])
            self.assertEqual(digest(a.state),sha)
            self.assertEqual(a.state["step"],1);a.close()
    def test_goal_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Agent(Path(tmp)/"a.db","autonomous",1)
            self.assertEqual(a.goal(dict(scalar=False,sequence=True,project=False))[0],"sequence");a.close()
    def test_teacher_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Agent(Path(tmp)/"a.db","teacher",1);a.acquire_teacher();a.persist();a.db.commit()
            self.assertEqual(len(a.state["teacher_skills"]),6)
            self.assertEqual(sum(not x["accepted"] for x in a.state["teacher_evidence"]),2);a.close()
    def test_abstention(self):
        t=dict(domain="scalar",case=("constant",(1,)),seed=1)
        self.assertEqual(assess(t,None),dict(success=False,checks=[],abstained=True))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output directory inside NUCLEO_V1 required")
    run(a.output)
