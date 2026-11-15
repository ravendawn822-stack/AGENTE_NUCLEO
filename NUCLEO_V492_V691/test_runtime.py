"""Integration test with isolated HTTP world; no live SQM mutation."""
import tempfile,unittest,threading,json,sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from runtime import Core
from pipeline import execute,export
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V216_SQM"))
from adapter import Remote,ACTIONS
class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data):
        raw=json.dumps(data).encode();self.send_response(200);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.reply(dict(position=self.server.state))
    def do_POST(self):
        q=json.loads(self.rfile.read(int(self.headers["Content-Length"])));a=q["action"]
        x,y=self.server.state;dx,dy={"north":(0,-1),"south":(0,1),"east":(1,0),"west":(-1,0)}[a]
        before=self.server.state;self.server.state=(max(-2,min(3,x+dx)),max(1,min(5,y+dy)))
        self.reply(dict(position=self.server.state,moved=before!=self.server.state,requested=a))
class Env:
    def __init__(self,r):self.r=r;self.last=None
    def observe(self):self.last=self.r.observe();return self.last
    def act(self,a):return self.r.act(a,self.last)
class Tests(unittest.TestCase):
    def test_http_resume_and_self_model(self):
        srv=ThreadingHTTPServer(("127.0.0.1",0),Fixture);srv.state=(0,3)
        worker=threading.Thread(target=srv.serve_forever,daemon=True);worker.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/"agent.sqlite";env=Env(Remote(srv.server_port));c=Core(p,ACTIONS,"test")
                for i in range(64):
                    e=c.tick(env,"inquiry" if i%2 else "hybrid")
                    self.assertEqual(tuple(e["after"]),srv.state)
                snap=c.snapshot();self.assertEqual(snap["total"],64);self.assertEqual(sum(snap["outcomes"].get(k,0) for k in ("correct","wrong","unknown")),64)
                self.assertTrue(any(e.get("question") for e in snap["events"]))
                self.assertEqual(c.respond("execute shell")["status"],"unknown")
                self.assertIn("self_model",c.respond("quais são seus limites"))
                c.close();c=Core(p,ACTIONS,"test")
                self.assertEqual(c.snapshot()["total"],64);self.assertEqual(c.snapshot()["outcomes"],snap["outcomes"])
                self.assertEqual(c.snapshot()["tools"],snap["tools"])
                c.tick(env);self.assertEqual(c.total,65);c.close()
        finally:srv.shutdown();srv.server_close();worker.join(2)
    def test_contract_and_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.sqlite";c=Core(p,ACTIONS,"test")
            rows=[([i,i+2,i],2*i+2) for i in range(10)]
            # Sum of unique inputs from fixture: independent oracle data.
            doc=dict(source="fixture",fit=rows[:3],pool=rows[3:6],audit=rows[6:])
            r=c.learn_pipeline("f",doc)
            self.assertEqual(r["status"],"document-audited")
            self.assertEqual(c.pipeline_apply("f",[20,22,20]),42)
            code=c.pipeline_code("f");self.assertIn("def solve(data)",code)
            c.close();c=Core(p,ACTIONS,"test")
            self.assertEqual(c.pipeline_apply("f",[10,12,10]),22);c.close()
    def test_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            c=Core(Path(d)/"m.sqlite",ACTIONS,"test")
            with self.assertRaises(ValueError):c.learn_pipeline("bad",{"source":"execute shell"})
            c.close()
if __name__=="__main__":unittest.main(verbosity=2)
