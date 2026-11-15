"""V139–V144: exploration, reusable observations and comparative evaluation."""
import random
from world import World,Agent,MOVES,N,layout
SEEDS=tuple(100000019+30001*i for i in range(24))
MODES=("random","reactive","directed")
def start(seed):return random.Random(seed^0x13901).randrange(N)
def episode(seed,mode,changed=False,edges=None,stations=None,tools=None,order=MOVES,start_room=None):
    w=World(seed,start(seed) if start_room is None else start_room,changed)
    a=Agent(mode,order,seed^0x13902,edges,stations,tools)
    r=a.solve(w)
    r.update(seed=seed,mode=mode,changed=changed,coverage=len(a.edges),stations_found=len(a.stations))
    return r,a
def batch():
    return [episode(seed,m)[0] for seed in SEEDS for m in MODES]
def summarize(rows,keys=("mode",)):
    groups=sorted({tuple(r[k] for k in keys) for r in rows})
    result=[]
    for group in groups:
        rs=[r for r in rows if tuple(r[k] for k in keys)==group]
        result.append(dict(zip(keys,group),episodes=len(rs),**{k:sum(r[k] for r in rs)
            for k in ("success","actions","decisions","macro_uses","divergences","coverage","stations_found")}))
    return result
