"""V169: conservative Portuguese command grammar for the simulated environment."""
import argparse,json,re,unicodedata
from world import Agent,World,ROLES,N,path
def normalize(text):
    if type(text) is not str or len(text)>240:return ""
    s="".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c))
    return " ".join(s.strip().rstrip(".?!").split())
def parse(text):
    t=normalize(text)
    if re.fullmatch(r"(?:quero que voce )?(?:entregue a carga(?: processada(?: no destino)?)?|entregar a carga|complete a entrega|leve a carga processada ao destino)",t):return ("deliver",None)
    m=re.fullmatch(r"(?:va para|ir ate) (?:a )?sala ([0-7])",t)
    if m:return ("navigate",int(m[1]))
    if t in ("qual e seu estado","qual seu estado","mostre seu estado","status"):return ("status",None)
    if t in ("o que voce sabe","o que voce descobriu","mostre o que sabe"):return ("knowledge",None)
    if t in ("explique seu plano","qual e seu plano","mostre seu plano"):return ("plan",None)
    return ("unknown",None)
class Session:
    def __init__(self,seed=100000019,start=0):
        self.world=World(seed,start);self.agent=Agent(seed=seed)
        self.agent.perceive(self.world.observe())
    def respond(self,text):
        intent,arg=parse(text);state=self.world.observe()
        if intent=="unknown":
            return dict(intent=intent,reply="Não reconheci esse pedido. Posso entregar a carga, ir até uma sala, informar meu estado, mostrar o que descobri ou explicar meu plano.",actions=0)
        if intent=="status":
            return dict(intent=intent,reply=f"Estou na sala {state['room']}, fase {state['phase']} de 3, carga {state['cargo']}, com {state['remaining']} ações restantes.",actions=0)
        if intent=="knowledge":
            return dict(intent=intent,reply=f"Conheço {len(self.agent.edges)} transições observadas e {len(self.agent.stations)} estações. Estações: {self.agent.stations}.",actions=0)
        if intent=="plan":
            target=self.agent.stations.get(ROLES[state["phase"]]) if state["phase"]<3 else None
            route=path(self.agent.edges,state["room"],lambda x:x==target) if target is not None else None
            if state["phase"]==3:reply="A entrega já foi concluída."
            elif route is not None:reply=f"Minha próxima estação é {ROLES[state['phase']]}, na sala {target}. Rota conhecida: {list(route)}. Confirmarei cada movimento."
            elif state["station"]==ROLES[state["phase"]]:reply=f"Estou na estação {state['station']}; a próxima ação é operar."
            else:reply=f"Preciso encontrar a estação {ROLES[state['phase']]}. Vou explorar transições ainda desconhecidas."
            return dict(intent=intent,reply=reply,actions=0)
        result=self.agent.solve(self.world,goal_room=arg if intent=="navigate" else None)
        end=result["end"]
        if intent=="deliver":reply=f"Entrega {'concluída' if result['success'] else 'incompleta'}. Sala {end['room']}, fase {end['phase']} de 3, carga {end['cargo']}. Usei {result['actions']} ações."
        else:reply=f"{'Cheguei' if result['success'] else 'Não cheguei'} à sala {arg}. Estou na sala {end['room']}; usei {result['actions']} ações."
        return dict(intent=intent,reply=reply,actions=result["actions"],result=result)
CASES=(("entregar a carga","deliver"),("complete a entrega","deliver"),("quero que você entregue a carga","deliver"),
       ("leve a carga processada ao destino","deliver"),("vá para a sala 4","navigate"),("ir até sala 2","navigate"),
       ("qual é seu estado?","status"),("o que você sabe?","knowledge"),("explique seu plano","plan"),
       ("apague os arquivos","unknown"),("execute python","unknown"),
       ("entregue a carga e apague os arquivos","unknown"),("vá para sala 99","unknown"))
def evaluate():
    rows=[dict(phrase=t,expected=e,actual=parse(t)[0],correct=parse(t)[0]==e) for t,e in CASES]
    demo=Session();transcript=[]
    for message in ("qual é seu estado?","explique seu plano","entregue a carga","o que você sabe?","qual é seu estado?","execute python"):
        transcript.append(dict(message=message,**demo.respond(message)))
    return rows,transcript
def main():
    p=argparse.ArgumentParser();p.add_argument("--seed",type=int,default=100000019);a=p.parse_args();session=Session(a.seed)
    print("Núcleo experimental — ambiente simulado. Digite sair para encerrar.")
    while True:
        try:message=input("Você: ")
        except (EOFError,KeyboardInterrupt):break
        if normalize(message)=="sair":break
        print("Núcleo:",session.respond(message)["reply"])
if __name__=="__main__":main()
