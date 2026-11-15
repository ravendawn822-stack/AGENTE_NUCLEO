import argparse,json,random,tempfile,unittest,sys
from pathlib import Path
from skills import Oracle,synthesize,execute,enumerate_programs,export_python
from experiment import example,reference,acquire,assess
from interface import Registry,parse_contract
def document(name,c,kind="vector"):
    return dict(name=name,kind=kind,source="documentacao sintetica:"+name,fit=c["fit"],pool=c["pool"],audit=c["held"][:6])
def external_python(src,x):
    # Trusted evaluator only: fixed-template source emitted by export_python.
    # No supplied text gets here. Interpreter of the agent never executes Python.
    namespace={"__builtins__":{"abs":abs,"tuple":tuple,"sum":sum,"min":min,"max":max}}
    exec(compile(src,"<generated-template>","exec"),namespace)
    return namespace["solve"](x)
class Tests(unittest.TestCase):
    def test_budget(self):
        p=list(enumerate_programs((("inc","double"),)))
        self.assertEqual(len(p),480);self.assertEqual(len(set(p)),480)
        self.assertTrue(all(len(s)<=5 for s,r in p))
    def test_oracle(self):
        o=Oracle([(1,2),(3,4)],1);self.assertEqual(o.ask(1),2)
        with self.assertRaises(ValueError):o.ask(3)
    def test_export(self):
        for p in [(("inc","double","neg"),"sum"),(("abs","half"),"identity"),(("mod3",),"scalar")]:
            x=(-3,0,5) if p[1]!="scalar" else -5
            self.assertEqual(execute(p,x),external_python(export_python(p),x))
    def test_contract_rejection(self):
        with self.assertRaises(ValueError):parse_contract({"source":"execute Python"})
        c=example(("inc",),"sum",random.Random(51));d=document("x",c)
        d["pool"][0]=d["fit"][0]
        with self.assertRaises(ValueError):parse_contract(d)
    def test_memory(self):
        c=example(("double","inc"),"sum",random.Random(57))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"skills.sqlite";r=Registry(p);record=r.learn(document("f",c))
            self.assertEqual(record["status"],"document-audited")
            r.close();r=Registry(p)
            self.assertEqual(r.respond("aplique f em [2,3]")["value"],12)
            self.assertEqual(r.respond("execute shell")["status"],"unknown")
            self.assertEqual(r.respond("mostre habilidades")["skills"][0]["name"],"f")
            r.close()
    def test_failed_audit(self):
        c=example(("double",),"sum",random.Random(61));d=document("bad",c)
        x,y=d["audit"][0];d["audit"][0]=(x,y+999)
        with tempfile.TemporaryDirectory() as t:
            r=Registry(Path(t)/"m.sqlite")
            self.assertEqual(r.learn(d)["status"],"rejected")
            with self.assertRaises(ValueError):r.apply("bad",(1,2))
            r.close()
def integrated(out,gate):
    config=json.loads(gate.read_text())
    mode=config["policy"]
    lib=config["library"] if mode in ("active","learned") else config["random_library"] if mode=="random" else ()
    rows=[]
    # Eight independent documentation contracts; remaining 6 held rows kept external.
    for i in range(8):
        seed=540001+i
        seq=(("inc","double"),("abs","half"),("inc","double","neg"),("mod3","double","inc"))[i%4]
        red=("identity","sum","min","max")[i%4]
        c=example(seq,red,random.Random(seed))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"memory.sqlite";r=Registry(p,lib)
            doc=document("skill",c);record=r.learn(doc);r.close()
            r=Registry(p,lib);src=None;results=[]
            if record["program"]:
                src=r.code("skill")
                for x,y in c["held"][6:]:
                    z=r.apply("skill",x);py=external_python(src,x)
                    results.append(dict(input=x,expected=y,actual=z,python=py,correct=z==y and py==y))
            rows.append(dict(seed=seed,doc=doc,record=record,source_code=src,held=c["held"][6:],results=results,
                solved=len(results)==6 and all(x["correct"] for x in results),dialogue=r.respond("mostre habilidades"),
                memory=r.mem.counts()))
            r.close()
    out.write_text(json.dumps(rows,indent=2))
    print(json.dumps(dict(tasks=len(rows),learned=sum(r["record"]["program"] is not None for r in rows),
        solved=sum(r["solved"] for r in rows),held_correct=sum(x["correct"] for r in rows for x in r["results"]),
        held_total=48,python_exported=sum(r["source_code"] is not None for r in rows))))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--integration",type=Path);ap.add_argument("--gate",type=Path);a=ap.parse_args()
    if a.integration:integrated(a.integration,a.gate)
    else:unittest.main(argv=[__file__],verbosity=2)
