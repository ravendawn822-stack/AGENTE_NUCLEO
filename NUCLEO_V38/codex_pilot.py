"""V38: three-call, operator-mediated Codex teaching pilot. CI is offline."""
import argparse,json,os,re,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V33"))
import teaching_protocol as q
l,t,m,v=q.l,q.t,q.m,q.v
SEED=5400017
MODEL="gpt-6-luna"
MAX_CALLS=3
TIMEOUT=90
DEFINITIONS={
 "abs":"absolute value of each element","neg":"negate each element","inc":"add 1 to each",
 "positive":"keep >0","even":"keep even elements","reverse":"reverse sequence","sort":"ascending",
 "unique":"keep first occurrence","take2":"first two","drop1":"remove first","rotate":"left rotate by one",
 "difference":"successive next minus previous","sum":"singleton sum","scan":"prefix cumulative sums",
 "count":"singleton length","bounds":"[min,max], empty -> [0,0]","maximum":"singleton max, empty -> [0]"}
SCHEMA={"type":"object","properties":{"version":{"type":"string"},"request_sha":{"type":"string"},
 "proposals":{"type":"array","items":{"type":"array","items":{"type":"string"}}}},
 "required":["version","request_sha","proposals"],"additionalProperties":False}

def dump(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=True),encoding="utf-8")

def plan():
    initial,pool,held=v.input_sets(SEED);points=(*initial,*pool,*held)
    fi,fp,fh=l.final_inputs(SEED,points)
    teaching=t.teaching_points(SEED,(*points,*fi,*fp,*fh))
    tasks=[z for z in q.acquisition(SEED,points) if z["stratum"]=="direct"][:MAX_CALLS]
    packets=[]
    for task in tasks:
        goal=task["program"];ask=lambda x:t.target(goal,x)
        row=q.attempt(goal,initial,pool,held,{},SEED)
        assert not row["emitted"]
        observed=tuple(ask(x) for x in initial)
        examples,extra=q.supplement(initial,observed,row["trace"],pool,ask)
        packets.append(q.request(examples,{}))
    assert len(packets)==MAX_CALLS
    return packets,tasks,teaching,(fi,fp,fh)

def prepare(directory):
    directory.mkdir(parents=True,exist_ok=False)
    packets,*_=plan()
    for i,req in enumerate(packets,1):dump(directory/f"request_{i}.json",req)
    dump(directory/"manifest.json",dict(seed=SEED,model=MODEL,cap=MAX_CALLS,
        request_hashes=[p["request_sha"] for p in packets]))
    return packets

def read_request(directory,index):
    packets,*_=plan()
    if not 1<=index<=MAX_CALLS:raise ValueError("query index")
    manifest=json.loads((directory/"manifest.json").read_text())
    if manifest!=dict(seed=SEED,model=MODEL,cap=MAX_CALLS,request_hashes=[p["request_sha"] for p in packets]):
        raise ValueError("manifest mismatch")
    req=json.loads((directory/f"request_{index}.json").read_text())
    if req!=packets[index-1]:raise ValueError("request mismatch")
    return req

def prompt(req):
    q.validate_request(req)
    return ("Solve a small synthetic list function inference problem. "
      "Use ONLY the permitted primitive names, in execution order, at most three per sequence "
      "and at most four sequences. Every operation maps a list to a list. "
      "Return JSON with version and request_sha copied exactly, and proposals, or an empty array. "
      "Do not use tools, inspect files, browse, or run commands.\nDefinitions: "
      +json.dumps(DEFINITIONS,separators=(",",":"))+"\nRequest: "+m.enc(req))

def cli_env():
    # Keep normal CLI authentication location; never pass API keys or unrelated Codespace secrets.
    keys=("PATH","HOME","USER","LOGNAME","SHELL","LANG","LC_ALL","TERM","TMPDIR","CODEX_HOME",
          "SSL_CERT_FILE","SSL_CERT_DIR","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME")
    return {k:os.environ[k] for k in keys if k in os.environ}

def query(directory,index):
    req=read_request(directory,index)
    binary=shutil.which("codex")
    if not binary:raise RuntimeError("Codex CLI not found")
    env=cli_env()
    with tempfile.TemporaryDirectory(prefix="nucleo-v38-") as tmp:
        tmp=Path(tmp)
        status=subprocess.run([binary,"login","status"],cwd=tmp,env=env,
            capture_output=True,text=True,timeout=15,check=False)
        if status.returncode or "chatgpt" not in (status.stdout+status.stderr).lower():
            raise RuntimeError("ChatGPT CLI login not confirmed; no query sent")
        marker=directory/f"attempt_{index}.json"
        # No retry of an attempted request, even after failure.
        with marker.open("x",encoding="utf-8") as f:
            json.dump(dict(index=index,model=MODEL,request_sha=req["request_sha"],status="started"),f)
        schema=tmp/"schema.json";answer=tmp/"answer.json";dump(schema,SCHEMA)
        cmd=[binary,"-a","never","exec","--ignore-user-config","--ephemeral","--skip-git-repo-check",
             "--sandbox","read-only","--model",MODEL,"-c",'model_reasoning_effort="low"',
             "--json","--output-schema",str(schema),"--output-last-message",str(answer),"-"]
        result=dict(index=index,model=MODEL,request_sha=req["request_sha"],status="failed",usage=None)
        start=time.monotonic()
        try:
            run=subprocess.run(cmd,input=prompt(req),cwd=tmp,env=env,capture_output=True,
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
                q.validate_response(req,response)
                dump(directory/f"response_{index}.json",response)
                result["status"]="ok"
            else:result["error"]="CLI failed or no bounded answer"
        except subprocess.TimeoutExpired:result["error"]="timeout"
        except (ValueError,OSError):result["error"]="invalid response or local I/O failure"
        finally:
            result["seconds"]=round(time.monotonic()-start,3)
            dump(marker,result)
        return result

def evaluate(directory):
    packets,tasks,teaching,final=plan()
    verified={};simulated={};ideal={};evidence=[]
    ideal_packet=json.loads((ROOT.parent/"NUCLEO_V29"/"teacher.json").read_text())
    ideal_by_name={z["name"]:tuple(z["proposals"][0]) for z in ideal_packet["lessons"]}
    for i,(packet,task) in enumerate(zip(packets,tasks),1):
        req=read_request(directory,i);goal=task["program"];ask=lambda x:t.target(goal,x)
        q.register(ideal,ideal_by_name[goal[0]])
        response,cost=q.teacher(req)
        p,sim_trace=q.choose_proposal(req,response,teaching,ask,True)
        if p is not None:q.register(simulated,p)
        marker=directory/f"attempt_{i}.json";response_file=directory/f"response_{i}.json"
        event=json.loads(marker.read_text()) if marker.exists() else {"status":"not_attempted"}
        trace=[];accepted=None
        if event.get("status")=="ok" and response_file.exists():
            if response_file.stat().st_size>8192:raise ValueError("response too large")
            reply=json.loads(response_file.read_text())
            accepted,trace=q.choose_proposal(req,reply,teaching,ask,True)
            if accepted is not None:q.register(verified,accepted)
        evidence.append(dict(index=i,attempt=event,accepted=accepted,validation=trace,simulated=sim_trace))
    registries={"none":{},"codex":verified,"simulated":simulated,"ideal_three":ideal}
    rows=[]
    fi,fp,fh=final
    tasks_final=t.suite(SEED,(*fi,*fp,*fh))
    for policy,registry in registries.items():
        before=m.digest(registry)
        for i,task in enumerate(tasks_final):
            row=q.attempt(task["program"],fi,fp,fh,registry,SEED+i*971)
            rows.append(dict(policy=policy,task=task,**row))
        assert m.digest(registry)==before
    summary=dict(protocol="V38-codex-pilot-v1",model_requested=MODEL,seed=SEED,
      attempted=sum(z["attempt"]["status"]!="not_attempted" for z in evidence),
      successful_responses=sum(z["attempt"]["status"]=="ok" for z in evidence),
      accepted=len(verified),evidence=evidence,registries=registries,
      aggregate=[dict(policy=p,**q.metrics([z for z in rows if z["policy"]==p])) for p in registries],
      by_stratum=[dict(policy=p,stratum=s,**q.metrics([z for z in rows if z["policy"]==p and z["task"]["stratum"]==s]))
        for p in registries for s in ("direct","composed","basic")])
    dump(directory/"summary.json",summary)
    dump(directory/"raw.json",rows)
    print(json.dumps(summary,indent=2))
    return summary

class Tests(unittest.TestCase):
    def test_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"pilot";packets=prepare(p)
            self.assertEqual(len(packets),3)
            for i,req in enumerate(packets,1):
                self.assertEqual(read_request(p,i),req)
                self.assertLessEqual(len(prompt(req)),7000)
                self.assertNotIn("goal",req)
            self.assertEqual(set(DEFINITIONS),set(q.OPS))
    def test_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"pilot";prepare(p)
            summary=evaluate(p)
            self.assertEqual(summary["attempted"],0)
            self.assertEqual(summary["successful_responses"],0)
            self.assertEqual(summary["accepted"],0)
            self.assertTrue(all(z["n"]==24 for z in summary["aggregate"]))
    def test_env(self):
        self.assertNotIn("OPENAI_API_KEY",cli_env())
        self.assertNotIn("CODEX_API_KEY",cli_env())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    sub=parser.add_subparsers(dest="action")
    for action in ("prepare","query","evaluate"):
        p=sub.add_parser(action);p.add_argument("--dir",type=Path,required=True)
        if action=="query":p.add_argument("--index",type=int,choices=(1,2,3),required=True)
    args=parser.parse_args()
    if args.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if args.action=="prepare":prepare(args.dir.resolve());print("Three requests saved; no model contacted.")
    elif args.action=="query":
        result=query(args.dir.resolve(),args.index);print(json.dumps(result,indent=2))
        if result["status"]!="ok":raise SystemExit(1)
    elif args.action=="evaluate":evaluate(args.dir.resolve())
    else:parser.error("choose prepare, query or evaluate")
if __name__=="__main__":main()
