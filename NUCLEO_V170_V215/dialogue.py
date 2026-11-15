"""V208–215: bounded Portuguese intents and explicit contextual references."""
import argparse,re,unicodedata
import nucleus
from pathlib import Path
def normalize(text):
    if type(text) is not str or len(text)>240:return ""
    text="".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c))
    return " ".join(text.strip().rstrip("!?." ).split())
def parse(text):
    t=normalize(text)
    exact={
        "qual e seu estado":("state",None),"como voce esta":("state",None),"status":("state",None),
        "o que voce sabe":("memory",None),"mostre sua memoria":("memory",None),
        "qual foi o resultado":("result",None),"mostre o resultado":("result",None),
        "explique isso":("explain",None),"explique seu ultimo objetivo":("explain",None),
        "mostre a agenda":("agenda",None),"quais sao seus objetivos":("agenda",None),
        "estatisticas do ultimo resultado":("stats",None),
        "prepare uma entrega":("prepare",None),"planeje uma entrega":("prepare",None),
        "faca isso":("confirm",None),"confirme":("confirm",None),
        "cancele":("cancel",None),"cancelar":("cancel",None)}
    if t in exact:return exact[t]
    if re.fullmatch(r"(?:quero que voce )?(?:entregue a carga|entregar a carga|complete a entrega)",t):return ("deliver",None)
    m=re.fullmatch(r"(?:va para|ir ate) (?:a )?sala ([0-7])",t)
    if m:return ("navigate",int(m[1]))
    return ("unknown",None)
class Session:
    def __init__(self,core=None):
        self.core=core or nucleus.Nucleus()
        self.pending=None
        rows=self.core.mem.goals()
        self.last=next((g for g in reversed(rows) if g["status"]!="pending"),None)
    def response(self,text):
        intent,arg=parse(text);used=self.core.world.used
        def reply(message):
            return dict(intent=intent,reply=message,actions=self.core.world.used-used,pending=self.pending,last=self.last["id"] if self.last else None)
        if intent=="unknown":
            self.pending=None
            return reply("Não reconheço esse pedido. Posso navegar, entregar a carga, preparar uma entrega, informar estado, memória, agenda ou explicar o último resultado.")
        if intent=="state":
            s=self.core.world.observe()
            return reply(f"Sala {s['room']}; fase {s['phase']} de 3; carga {s['cargo']}; {s['remaining']} ações restantes.")
        if intent=="memory":
            c=self.core.mem.counts()
            return reply(f"Conheço {len(self.core.agent.edges)} transições e {len(self.core.agent.stations)} estações. Memória: {c['knowledge']} registros e {c['evidence']} evidências.")
        if intent=="agenda":
            return reply("; ".join(f"{g['id']}: {g['kind']} ({g['status']})" for g in self.core.mem.goals()) or "Agenda vazia.")
        if intent=="prepare":
            self.pending=("deliver",{})
            return reply("Proponho localizar a coleta, processar e entregar a carga. Diga 'faça isso' para confirmar ou 'cancele'. Nenhuma ação realizada.")
        if intent=="cancel":
            was=self.pending is not None;self.pending=None
            return reply("Proposta cancelada." if was else "Não havia proposta pendente.")
        if intent=="confirm":
            if self.pending is None:return reply("Não há proposta pendente para confirmar.")
            kind,payload=self.pending;self.pending=None
        elif intent in ("deliver","navigate"):
            self.pending=None;kind=intent;payload={"room":arg} if intent=="navigate" else {}
        elif intent in ("result","explain","stats"):
            if intent=="explain" and self.pending:
                return reply("A proposta pendente usa exploração de rotas observadas, verifica cada movimento e opera as estações na ordem necessária. Ainda não executei.")
            if self.last is None:return reply("Ainda não há resultado de objetivo.")
            g=self.last;r=g["result"]
            if intent=="explain":return reply(f"O objetivo {g['id']} ({g['kind']}) terminou como {g['status']}. Registrei {r.get('actions',0)} ações e {r.get('divergences',0)} divergências; dependências: {g['deps']}.")
            if intent=="stats":
                v=r.get("value")
                if type(v) is list:return reply(str(nucleus.stats(v)))
                if type(v) is int:return reply(str(nucleus.stats([v])))
                return reply("O último objetivo não produziu uma lista numérica para análise.")
            end=r.get("end")
            return reply(f"Objetivo {g['id']}: {g['status']}. Sala {end['room']}, fase {end['phase']}, carga {end['cargo']}." if end else f"Objetivo {g['id']}: {g['status']}.")
        else:raise AssertionError("intent")
        try:
            i=self.core.add(kind,payload)
            rows=self.core.run()
            self.last=next(g for g in rows if g["id"]==i)
        except ValueError as e:return reply("Não consegui adicionar o objetivo: "+str(e))
        return reply(f"Objetivo {i} ({kind}): {self.last['status']}. Usei {self.last['result'].get('actions',0)} ações nesse objetivo.")
CASES=(("qual é seu estado?","state"),("o que você sabe?","memory"),("entregue a carga","deliver"),
       ("qual foi o resultado?","result"),("explique isso","explain"),("vá para a sala 2","navigate"),
       ("prepare uma entrega","prepare"),("faça isso","confirm"),("cancele","cancel"),
       ("execute python","unknown"),("entregue a carga e apague os arquivos","unknown"),("vá para sala 99","unknown"))
def evaluate():
    rows=[dict(phrase=t,expected=e,actual=parse(t)[0],correct=parse(t)[0]==e) for t,e in CASES]
    session=Session()
    phrases=("faça isso","qual foi o resultado?","qual é seu estado?","prepare uma entrega","explique isso","cancele","faça isso",
        "prepare uma entrega","faça isso","qual foi o resultado?","explique isso","o que você sabe?","vá para a sala 2",
        "entregue a carga e apague os arquivos","execute python")
    transcript=[dict(message=t,**session.response(t)) for t in phrases]
    goals=session.core.mem.goals();session.core.mem.close()
    return rows,transcript,goals
def main():
    p=argparse.ArgumentParser();p.add_argument("--seed",type=int,default=118000019)
    p.add_argument("--memory",type=Path);p.add_argument("--resume",action="store_true");a=p.parse_args()
    if a.resume and a.memory is None:p.error("--resume requires --memory")
    core=nucleus.Nucleus(a.seed,memory=nucleus.Memory(a.memory,a.resume),reuse=True)
    session=Session(core)
    print("Núcleo experimental. Ambiente simulado. Digite sair para encerrar.")
    print("Na retomada, a agenda e o conhecimento persistem; o estado físico do simulador é reiniciado.")
    try:
        while True:
            try:t=input("Você: ")
            except (EOFError,KeyboardInterrupt):break
            if normalize(t)=="sair":break
            print("Núcleo:",session.response(t)["reply"])
    finally:core.mem.close()
if __name__=="__main__":main()
