"""V145–V150: acquire declarative routes from observed transitions, freeze and replay."""
import hashlib,json
from pathlib import Path
from world import N,MOVES,ROLES,path
import exploration as exp
def acquire(edges):
    tools={}
    for source in range(N):
        for target in range(N):
            route=path(edges,source,lambda x:x==target)
            if route and 2<=len(route)<=N:tools[source,target]=route
    return tools
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def payload(edges,stations,tools):
    return dict(schema=1,edges=[[s,a,t] for (s,a),t in sorted(edges.items())],
        stations=stations,tools=[[s,t,list(route)] for (s,t),route in sorted(tools.items())])
def save(file,edges,stations,tools):
    p=payload(edges,stations,tools)
    with file.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(file):
    with file.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    e=json.loads(raw);p=e["payload"]
    if p["schema"]!=1 or e["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    def room(x):return type(x) is int and 0<=x<N
    edges={};stations=p["stations"];tools={}
    if len(p["edges"])>N*len(MOVES) or len(p["tools"])>N*(N-1):raise ValueError("size")
    for s,a,t in p["edges"]:
        if not room(s) or not room(t) or type(a) is not int or a not in MOVES or (s,a) in edges:raise ValueError("edge")
        edges[s,a]=t
    if not set(stations)<=set(ROLES) or any(not room(s) for s in stations.values()) or len(set(stations.values()))!=len(stations):raise ValueError("stations")
    for s,t,route in p["tools"]:
        if not room(s) or not room(t) or s==t or (s,t) in tools or not 2<=len(route)<=N:raise ValueError("tool")
        at=s
        for a in route:
            if type(a) is not int or a not in MOVES or (at,a) not in edges:raise ValueError("unobserved path")
            at=edges[at,a]
        if at!=t:raise ValueError("destination")
        tools[s,t]=tuple(route)
    return edges,stations,tools
def run(out):
    out.mkdir();training=[];rows=[]
    for seed in exp.SEEDS:
        train,agent=exp.episode(seed,"directed")
        learned=acquire(agent.edges)
        f=out/f"{seed}.json";save(f,agent.edges,agent.stations,learned)
        edges,stations,tools=load(f)
        training.append(dict(seed=seed,success=train["success"],actions=train["actions"],coverage=len(edges),tools=len(tools),bytes=f.stat().st_size))
        for changed in (False,True):
            for m in ("cold","map","macro"):
                result,_=exp.episode(seed,"directed",changed,edges if m!="cold" else None,
                    stations if m!="cold" else None,tools if m=="macro" else None,start_room=(exp.start(seed)+3)%N)
                result["mode"]=m;rows.append(result)
    return training,rows
