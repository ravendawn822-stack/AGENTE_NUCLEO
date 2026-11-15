"""Private SQM live panel. One worker and an explicitly bounded action budget."""
import argparse,json,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from adapter import Explorer,Remote,open_memory,position,MAX_EVENTS
HERE=Path(__file__).resolve().parent
class Controller:
    def __init__(self,remote,memory,scope):
        self.remote=remote;self.memory=Path(memory);self.scope=scope
        self.lock=threading.RLock();self.stop=threading.Event();self.pause=threading.Event()
        self.worker=None;self.status="idle";self.error=None;self.reason=None;self.completed=0;self.planned=0;self.target=None
        mem=open_memory(self.memory,scope)
        try:self.data=Explorer(mem,scope).snapshot()
        finally:mem.close()
        self.pos=None
        try:self.pos=self.remote.observe()
        except Exception as e:self.error=str(e)[:300]
    def snapshot(self):
        with self.lock:
            return dict(status=self.status,error=self.error,reason=self.reason,completed=self.completed,planned=self.planned,
                position=self.pos,target=self.target,**self.data)
    def command(self,body):
        action=body.get("action")
        with self.lock:
            busy=self.worker is not None and self.worker.is_alive()
            if action in ("start","step"):
                if busy:raise ValueError("já em execução")
                count=1 if action=="step" else body.get("count",100)
                delay=body.get("delay",0.35);mode=body.get("mode","directed")
                if type(count) is not int or not 1<=count<=2500:raise ValueError("limite de 1 a 2500 movimentos por rodada")
                if type(delay) not in (int,float) or not .15<=delay<=3:raise ValueError("intervalo de 0,15 a 3 segundos")
                if mode not in ("directed","random"):raise ValueError("estratégia inválida")
                target=None if body.get("target") is None else position(body["target"])
                if self.data["total"]+count>MAX_EVENTS:raise ValueError("limite total de registros; utilize outro arquivo de memória")
                self.stop.clear();self.pause.clear();self.status="running";self.error=None;self.reason=None
                self.completed=0;self.planned=count;self.target=target
                self.worker=threading.Thread(target=self.run,args=(count,delay,mode,target),daemon=True);self.worker.start()
            elif action=="pause" and busy and self.status=="running":self.pause.set();self.status="paused"
            elif action=="resume" and busy and self.status=="paused":self.pause.clear();self.status="running"
            elif action=="stop" and busy:self.stop.set();self.pause.clear();self.status="stopping"
            else:raise ValueError("controle indisponível")
        return self.snapshot()
    def run(self,count,delay,mode,target):
        mem=None
        try:
            mem=open_memory(self.memory,self.scope);agent=Explorer(mem,self.scope,mode,seed=123+self.data["total"])
            for _ in range(count):
                while self.pause.is_set() and not self.stop.is_set():self.stop.wait(.1)
                if self.stop.is_set():break
                event,reason,p=agent.step(self.remote,target)
                with self.lock:
                    self.pos=p;self.data=agent.snapshot();self.reason=reason
                    if event is not None:self.completed+=1
                if event is None:break
                if self.stop.wait(delay):break
            with self.lock:self.status="stopped" if self.stop.is_set() else "finished"
        except Exception as e:
            with self.lock:self.status="error";self.error=str(e)[:300]
        finally:
            if mem is not None:mem.close()
    def export(self):
        mem=open_memory(self.memory,self.scope)
        try:return dict(scope=self.scope,events=Explorer(mem,self.scope).events(MAX_EVENTS))
        finally:mem.close()
class Handler(BaseHTTPRequestHandler):
    controller=None
    def log_message(self,*args):pass
    def reply(self,status,value,mime="application/json; charset=utf-8",attachment=None):
        raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'")
        if attachment:self.send_header("Content-Disposition",'attachment; filename="sqm-nucleus.json"')
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        p=urlsplit(self.path).path
        if p=="/":return self.reply(200,(HERE/"panel.html").read_bytes(),"text/html; charset=utf-8")
        if p=="/panel.js":return self.reply(200,(HERE/"panel.js").read_bytes(),"text/javascript; charset=utf-8")
        if p=="/panel.css":return self.reply(200,(HERE/"panel.css").read_bytes(),"text/css; charset=utf-8")
        if p=="/api/state":return self.reply(200,self.controller.snapshot())
        if p=="/api/export":return self.reply(200,self.controller.export(),attachment=True)
        return self.reply(404,{"error":"não encontrado"})
    def do_POST(self):
        if urlsplit(self.path).path!="/api/control":return self.reply(404,{"error":"não encontrado"})
        if self.headers.get("X-SQM-Control")!="1" or self.headers.get("Content-Type","").split(";")[0]!="application/json":return self.reply(415,{"error":"JSON do painel obrigatório"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<=1024:raise ValueError("tamanho")
            b=json.loads(self.rfile.read(n))
            if type(b) is not dict or set(b)-{"action","count","delay","mode","target"}:raise ValueError("campos")
            return self.reply(200,self.controller.command(b))
        except (ValueError,TypeError,KeyError) as e:return self.reply(400,{"error":str(e)})
def main():
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8007);p.add_argument("--world-port",type=int,default=8082)
    p.add_argument("--memory",type=Path,default=HERE/"sqm_v216.sqlite");p.add_argument("--scope",default="sqm-original")
    p.add_argument("--host",choices=("127.0.0.1","0.0.0.0"),default="0.0.0.0");a=p.parse_args()
    if not a.scope or len(a.scope)>80:p.error("scope")
    controller=Controller(Remote(a.world_port),a.memory,"sqm:"+a.scope)
    class Bound(Handler):pass
    Bound.controller=controller
    server=ThreadingHTTPServer((a.host,a.port),Bound)
    print(f"Painel SQM NÚCLEO: porta {a.port} PRIVATE | universo HTTP 127.0.0.1:{a.world_port}",flush=True)
    try:server.serve_forever()
    finally:
        controller.stop.set();controller.pause.clear()
        if controller.worker:controller.worker.join(timeout=8)
        server.server_close()
if __name__=="__main__":main()
