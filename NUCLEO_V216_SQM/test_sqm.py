"""Offline tests with a separate HTTP fixture matching the original SQM contract."""
import json,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from adapter import Explorer,Remote,open_memory
from panel import Controller
class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data):
        raw=json.dumps(data).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.reply(dict(position=self.server.pos))
    def do_POST(self):
        a=json.loads(self.rfile.read(int(self.headers["Content-Length"])))["action"]
        delta=dict(north=(0,-1),east=(1,0),south=(0,1),west=(-1,0))[a]
        before=self.server.pos
        candidate=tuple(x+y for x,y in zip(before,delta))
        if all(0<=n<5 for n in candidate) and candidate!=(2,1):self.server.pos=candidate
        self.reply(dict(position=self.server.pos,requested=a,moved=self.server.pos!=before))
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"test.sqlite"
        self.server=HTTPServer(("127.0.0.1",0),Fixture);self.server.pos=(2,2)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.remote=Remote(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.tmp.cleanup()
    def test_explore(self):
        mem=open_memory(self.path,"sqm:test");a=Explorer(mem,"sqm:test")
        for _ in range(200):
            event,reason,p=a.step(self.remote)
            if event is None:break
        data=a.snapshot();self.assertEqual(len(data["visited"]),24)
        self.assertEqual(data["transitions"],96)
        self.assertTrue(any(e["moved"]==False for e in a.events(200)))
        self.assertTrue(any(e["prediction_correct"] is False for e in a.events(200)))
        self.assertEqual(a.predict((2,2),"north")[0],(2,2));mem.close()
        mem=open_memory(self.path,"sqm:test");b=Explorer(mem,"sqm:test")
        self.assertEqual(len(b.edges),96)
        for _ in range(12):
            event,reason,p=b.step(self.remote,(4,4))
            if event is None:break
        self.assertEqual(self.remote.observe(),(4,4));mem.close()
    def test_controller(self):
        c=Controller(self.remote,self.path,"sqm:test")
        self.assertEqual(c.snapshot()["position"],(2,2))
        with self.assertRaises(ValueError):c.command(dict(action="start",count=2501))
        c.command(dict(action="step",delay=.15));c.worker.join(5)
        s=c.snapshot();self.assertEqual(s["completed"],1);self.assertEqual(s["status"],"finished")
        self.assertEqual(len(c.export()["events"]),1)
        resumed=Controller(self.remote,self.path,"sqm:test");self.assertEqual(resumed.snapshot()["total"],1)
    def test_goal_no_action(self):
        mem=open_memory(self.path,"sqm:test");a=Explorer(mem,"sqm:test")
        self.assertIsNone(a.step(self.remote,(2,2))[0]);self.assertEqual(a.count(),0);mem.close()
if __name__=="__main__":unittest.main()
