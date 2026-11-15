"""V39: one-shot counterexample-guided Codex repair with blind transfer."""
import argparse,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V38"))
import codex_pilot as v38
q=v38.q;l,t,m,v=q.l,q.t,q.m,q.v
MODEL=v38.MODEL
VALIDATION_SEED=5430019
MAX_REPAIR_CALLS=1
TIMEOUT=90
SCHEMA={"type":"object","properties":{"version":{"type":"string"},"repair_sha":{"type":"string"},
 "proposals":{"type":"array","items":{"type":"array","items":{"type":"string"}}}},
 "required":["version","repair_sha","proposals"],"additionalProperties":False}
VERSION="nucleo-repair-v1"

def dump(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=True),encoding="utf-8")

def original_bundle(v38_dir):
    req=json.loads((v38_dir/"request_1.json").read_text(encoding="utf-8"))
    response=json.loads((v38_dir/"response_1.json").read_text(encoding="utf-8"))
    attempt=json.loads((v38_dir/"attempt_1.json").read_text(encoding="utf-8"))
    q.validate_request(req);proposals=q.validate_response(req,response)
    if attempt.get("status")!="ok" or attempt.get("request_sha")!=req["request_sha"]:
        raise ValueError("V38 attempt not successful or not bound to request")
    packets,tasks,_,_=v38.plan()
    if req!=packets[0]:raise ValueError("V38 request differs from deterministic plan")
    goal=tasks[0]["program"]
    examples=q.validate_request(req)
    if not all(t.target(goal,x)==y for x,y in examples):
        raise ValueError("V38 examples do not match the reconstructed task")
    return req,response,attempt,goal,proposals[0]

def build_repair(req,previous):
    examples=q.validate_request(req)
    checked=[]
    for x,y in examples:
        actual=t.module(previous,x)
        checked.append(dict(input=list(x),expected=list(y),previous_output=list(actual),matches=actual==y))
    failures=[z for z in checked if not z["matches"]]
    passes=[z for z in checked if z["matches"]]
    if not failures:raise ValueError("original proposal has no counterexamples; repair unnecessary")
    body=dict(version=VERSION,original_request_sha=req["request_sha"],
        previous_proposal=list(previous),allowed_primitives=list(q.OPS),
        max_proposals=4,max_steps=3,examples=[dict(input=list(x),output=list(y)) for x,y in examples],
        counterexamples=failures[:4],consistent_examples=passes[:2])
    body["repair_sha"]=m.digest(body)
    return body,checked

def validate_repair_request(body):
    if not isinstance(body,dict):raise ValueError("repair request shape")
    raw=dict(body);sha=raw.pop("repair_sha",None)
    if raw.get("version")!=VERSION or sha!=m.digest(raw):raise ValueError("repair request hash")
    if raw.get("allowed_primitives")!=list(q.OPS):raise ValueError("primitive mismatch")
    if not 1<=len(raw.get("examples",[]))<=16:raise ValueError("example bounds")
    if not 1<=len(raw.get("counterexamples",[]))<=4:raise ValueError("counterexample bounds")
    if len(raw.get("consistent_examples",[]))>2:raise ValueError("consistent example bounds")
    for z in raw["examples"]+raw["counterexamples"]+raw["consistent_examples"]:
        if not isinstance(z,dict) or not isinstance(z.get("input"),list):raise ValueError("example schema")
    return True

def validate_repair_response(body,response):
    validate_repair_request(body)
    if not isinstance(response,dict) or set(response)!={"version","repair_sha","proposals"}:
        raise ValueError("response shape")
    if response["version"]!=VERSION or response["repair_sha"]!=body["repair_sha"]:
        raise ValueError("response binding")
    if not isinstance(response["proposals"],list) or len(response["proposals"])>4:
        raise ValueError("proposal count")
    normalized=[]
    for p in response["proposals"]:
        if not isinstance(p,list) or not 1<=len(p)<=3 or not t.valid(p):
            raise ValueError("invalid declarative proposal")
        if p not in normalized:normalized.append(p)
    return normalized

def prompt(body):
    validate_repair_request(body)
    return ("Repair a failed list-processing hypothesis using the counterexamples. "
      "Infer the transformation from all examples; do not assume the previous proposal is correct. "
      "Use only listed primitives in execution order, at most three per pipeline and four proposals. "
      "Return only the required JSON object. Do not use tools, browse, inspect files or run commands. "
      "A previous proposal is shown with its observed mismatches.\nPrimitive definitions: "
      +json.dumps(v38.DEFINITIONS,separators=(",",":"))+"\nRepair request: "+m.enc(body))

def cli_env():
    return v38.cli_env()

def prepare(v38_dir,out):
    out.mkdir(parents=True,exist_ok=False)
    req,response,attempt,goal,previous=original_bundle(v38_dir)
    body,checked=build_repair(req,previous)
    dump(out/"original.json",dict(request=req,response=response,attempt=attempt,
        reconstructed_goal=goal,previous_proposal=previous,public_check=checked))
    dump(out/"repair_request.json",body)
    dump(out/"manifest.json",dict(protocol="V39-one-shot-repair-v1",model_requested=MODEL,
        validation_seed=VALIDATION_SEED,max_repair_calls=MAX_REPAIR_CALLS,
        original_request_sha=req["request_sha"],repair_sha=body["repair_sha"]))
    print(json.dumps(dict(status="prepared",repair_sha=body["repair_sha"],
        counterexamples=len(body["counterexamples"]),public_matches=sum(z["matches"] for z in checked),
        public_n=len(checked),prompt_chars=len(prompt(body))),indent=2))

def read_bundle(directory):
    manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    body=json.loads((directory/"repair_request.json").read_text(encoding="utf-8"))
    original=json.loads((directory/"original.json").read_text(encoding="utf-8"))
    validate_repair_request(body)
    q.validate_request(original["request"])
    if manifest.get("repair_sha")!=body["repair_sha"] or manifest.get("original_request_sha")!=original["request"]["request_sha"]:
        raise ValueError("manifest mismatch")
    if original["previous_proposal"]!=body["previous_proposal"]:
        raise ValueError("previous proposal mismatch")
    packets,tasks,_,_=v38.plan()
    if original["request"]!=packets[0] or original["reconstructed_goal"]!=list(tasks[0]["program"]):
        raise ValueError("original V38 bundle differs from deterministic plan")
    q.validate_response(original["request"],original["response"])
    expected_body,expected_check=build_repair(original["request"],tuple(original["previous_proposal"]))
    if expected_body!=body or expected_check!=original["public_check"]:
        raise ValueError("repair feedback differs from deterministic reconstruction")
    return manifest,body,original

def query(directory,index=1):
    if index!=1:raise ValueError("V39 has one repair request")
    manifest,body,original=read_bundle(directory)
    binary=shutil.which("codex")
    if not binary:raise RuntimeError("Codex CLI not found")
    env=cli_env()
    with tempfile.TemporaryDirectory(prefix="nucleo-v39-") as tmp:
        tmp=Path(tmp)
        status=subprocess.run([binary,"login","status"],cwd=tmp,env=env,
            capture_output=True,text=True,timeout=15,check=False)
        if status.returncode or "chatgpt" not in (status.stdout+status.stderr).lower():
            raise RuntimeError("ChatGPT CLI login not confirmed; no repair sent")
        marker=directory/"repair_attempt_1.json"
        with marker.open("x",encoding="utf-8") as f:
            json.dump(dict(index=1,model_requested=MODEL,repair_sha=body["repair_sha"],status="started"),f)
        schema=tmp/"schema.json";answer=tmp/"answer.json";dump(schema,SCHEMA)
        cmd=[binary,"-a","never","exec","--ignore-user-config","--ephemeral","--skip-git-repo-check",
             "--sandbox","read-only","--model",MODEL,"-c",'model_reasoning_effort="low"',
             "--json","--output-schema",str(schema),"--output-last-message",str(answer),"-"]
        result=dict(index=1,model_requested=MODEL,repair_sha=body["repair_sha"],status="failed",usage=None)
        start=time.monotonic()
        try:
            run=subprocess.run(cmd,input=prompt(body),cwd=tmp,env=env,capture_output=True,
                text=True,timeout=TIMEOUT,check=False)
            result["exit_code"]=run.returncode
            for line in run.stdout.splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if isinstance(event,dict) and event.get("type")=="turn.completed":
                    usage=event.get("usage",{})
                    result["usage"]={k:z for k,z in usage.items() if type(z)==int and z>=0 and k in
                        ("input_tokens","cached_input_tokens","output_tokens","reasoning_output_tokens")}
            if run.returncode==0 and answer.exists() and answer.stat().st_size<=8192:
                response=json.loads(answer.read_text(encoding="utf-8"))
                validate_repair_response(body,response)
                dump(directory/"repair_response_1.json",response)
                result["status"]="ok"
            else:result["error"]="CLI failed or no bounded answer"
        except subprocess.TimeoutExpired:result["error"]="timeout"
        except (ValueError,OSError):result["error"]="invalid response or local I/O failure"
        finally:
            result["seconds"]=round(time.monotonic()-start,3)
            dump(marker,result)
        return result

def validation_environment():
    seed=VALIDATION_SEED
    initial,pool,held=v.input_sets(seed);public=(*initial,*pool,*held)
    fi,fp,fh=l.final_inputs(seed,public);final_points=(*fi,*fp,*fh)
    points=t.teaching_points(seed,(*public,*final_points))
    return initial,pool,held,fi,fp,fh,points,final_points

def evaluate(directory):
    manifest,body,original=read_bundle(directory)
    req=original["request"];goal=tuple(original["reconstructed_goal"])
    initial,pool,held,fi,fp,fh,validation,final_points=validation_environment()
    ask=lambda x:t.target(goal,x)
    attempt=json.loads((directory/"repair_attempt_1.json").read_text()) if (directory/"repair_attempt_1.json").exists() else {"status":"not_attempted"}
    repaired=None;repair_trace=[];repair_proposals=[]
    if attempt.get("status")=="ok":
        response=json.loads((directory/"repair_response_1.json").read_text())
        repair_proposals=validate_repair_response(body,response)
        standard=dict(version=req["version"],request_sha=req["request_sha"],proposals=repair_proposals)
        repaired,repair_trace=q.choose_proposal(req,standard,validation,ask,True)
    # The original Codex response is deliberately retained only as an unverified diagnostic.
    first_proposals=q.validate_response(req,original["response"])
    first_registry={}
    if first_proposals:q.register(first_registry,first_proposals[0])
    repair_registry={}
    if repaired is not None:q.register(repair_registry,repaired)
    simulated_response,simulated_cost=q.teacher(req)
    simulated_program,simulated_trace=q.choose_proposal(req,simulated_response,validation,ask,True)
    simulated_registry={}
    if simulated_program is not None:q.register(simulated_registry,simulated_program)
    packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text(encoding="utf-8"))
    ideal_by_name={z["name"]:tuple(z["proposals"][0]) for z in packet["lessons"]}
    ideal_registry={};q.register(ideal_registry,ideal_by_name[goal[0]])
    registries={"baseline":{},"first_codex_unverified":first_registry,
        "repair_verified":repair_registry,"simulated_teacher":simulated_registry,"ideal_reference":ideal_registry}
    tasks=t.suite(VALIDATION_SEED,final_points);rows=[]
    for policy,registry in registries.items():
        before=m.digest(registry)
        for i,task in enumerate(tasks):
            row=q.attempt(task["program"],fi,fp,fh,registry,VALIDATION_SEED+i*971)
            rows.append(dict(policy=policy,task=task,**row))
        assert m.digest(registry)==before
    result=dict(protocol="V39-one-shot-repair-v1",model_requested=MODEL,validation_seed=VALIDATION_SEED,
        original_request_sha=req["request_sha"],repair_sha=body["repair_sha"],repair_attempt=attempt,
        original_public_check=original["public_check"],repair_proposals=repair_proposals,
        repair_validation=repair_trace,repair_accepted=repaired,validation_examples=len(validation),
        simulated_teacher_cost=simulated_cost,simulated_teacher_validation=simulated_trace,
        registries=registries,
        aggregate=[dict(policy=p,**q.metrics([z for z in rows if z["policy"]==p])) for p in registries],
        by_stratum=[dict(policy=p,stratum=s,**q.metrics([z for z in rows if z["policy"]==p and z["task"]["stratum"]==s]))
            for p in registries for s in ("direct","composed","basic")])
    baseline={r["task"]["id"]:r for r in rows if r["policy"]=="baseline"}
    result["paired_vs_baseline"]={}
    for policy in registries:
        if policy=="baseline":continue
        pairs=[(r,baseline[r["task"]["id"]]) for r in rows if r["policy"]==policy]
        result["paired_vs_baseline"][policy]=dict(gains=sum(a["success"] and not b["success"] for a,b in pairs),
            losses=sum(not a["success"] and b["success"] for a,b in pairs))
    dump(directory/"summary.json",result);dump(directory/"raw.json",rows)
    print(json.dumps(result,indent=2));return result

class Tests(unittest.TestCase):
    def test_feedback(self):
        packets,tasks,_,_=v38.plan();req=packets[0];goal=tasks[0]["program"]
        self.assertTrue(all(t.target(goal,x)==y for x,y in q.validate_request(req)))
        body,checked=build_repair(req,("abs","sum"))
        self.assertEqual(sum(z["matches"] for z in checked),2)
        self.assertEqual(len(body["counterexamples"]),4)
        self.assertNotIn("goal",body)
        self.assertTrue(validate_repair_request(body))
        with self.assertRaises(ValueError):validate_repair_request(dict(body,repair_sha="bad"))
    def test_validation(self):
        *_,points,final_points=validation_environment()
        self.assertEqual(len(points),24);self.assertEqual(len(final_points),116)
        self.assertFalse(set(points)&set(final_points))
        self.assertTrue(all(t.module(("bounds","difference"),x)==t.oracle(("span",),x) for x in points))
        self.assertFalse(all(t.module(("abs","sum"),x)==t.oracle(("span",),x) for x in points))
    def test_response(self):
        packets,tasks,_,_=v38.plan();body,_=build_repair(packets[0],("abs","sum"))
        response=dict(version=VERSION,repair_sha=body["repair_sha"],proposals=[["bounds","difference"]])
        self.assertEqual(validate_repair_response(body,response),[["bounds","difference"]])
        bad=dict(response,repair_sha="wrong")
        with self.assertRaises(ValueError):validate_repair_response(body,bad)
    def test_offline_eval(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            v38_dir=Path(tmp)/"v38";v38_dir.mkdir()
            reqs,tasks,_,_=v38.plan()
            dump(v38_dir/"request_1.json",reqs[0])
            dump(v38_dir/"response_1.json",dict(version=reqs[0]["version"],request_sha=reqs[0]["request_sha"],proposals=[["abs","sum"]]))
            dump(v38_dir/"attempt_1.json",dict(status="ok",request_sha=reqs[0]["request_sha"]))
            out=Path(tmp)/"v39";prepare(v38_dir,out)
            dump(out/"repair_attempt_1.json",dict(status="not_attempted"))
            result=evaluate(out)
            self.assertEqual(len(result["aggregate"]),5)
            self.assertEqual(result["repair_accepted"],None)

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--self-test",action="store_true")
    sub=parser.add_subparsers(dest="action")
    p=sub.add_parser("prepare");p.add_argument("--v38-dir",type=Path,required=True);p.add_argument("--dir",type=Path,required=True)
    for action in ("repair","evaluate"):
        p=sub.add_parser(action);p.add_argument("--dir",type=Path,required=True)
        if action=="repair":p.add_argument("--index",type=int,choices=(1,),default=1)
    args=parser.parse_args()
    if args.self_test:
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.action=="prepare":prepare(args.v38_dir.resolve(),args.dir.resolve())
    elif args.action=="repair":
        result=query(args.dir.resolve(),args.index);print(json.dumps(result,indent=2))
        if result["status"]!="ok":raise SystemExit(1)
    elif args.action=="evaluate":evaluate(args.dir.resolve())
    else:parser.error("choose prepare, repair or evaluate")
if __name__=="__main__":main()
