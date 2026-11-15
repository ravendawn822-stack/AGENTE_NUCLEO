"""V151–V156: synthesize inert arithmetic AST and apply to a cargo in a real state chain."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for v in (109,115,124):sys.path.insert(0,str(ROOT/f"NUCLEO_V{v}"))
import value_information as vi
import ambiguity as amb
from world import Agent,World
import exploration as exp
s=amb.s
SEEDS=tuple(102000019+30001*i for i in range(24))
MODES=("pool_active","expand_active","split_random2")
def episode(seed,i,c,mode):
    oracle=amb.Oracle(c["audit"],2)
    synthesized=vi.solve(c["fit"],oracle,mode,seed+997*i)
    p=synthesized["program"]
    # Input is a simulated physical payload. Its required output is evaluator-only.
    x,y=c["held"][0]
    w=World(seed+997*i,exp.start(seed+997*i),cargo=x,programming=True)
    a=Agent(seed=seed+997*i)
    acted=a.solve(w,program=p)
    held=s.score(p,c["held"])
    delivered=acted["success"];right=delivered and acted["end"]["cargo"]==y
    return dict(seed=seed,task=i,kind=c["kind"],mode=mode,fit=c["fit"],audit=c["audit"],held=c["held"],
        synthesis=synthesized,execution=acted,delivered=int(delivered),correct_cargo=int(right),
        wrong_cargo=int(delivered and not right),full_success=int(right and held["solved"]),
        program_correct=held["solved"],program_wrong=int(p is not None and not held["solved"]),
        actions=acted["actions"],candidates=synthesized["candidates"],queries=len(synthesized["queries"]),**{k:held[k] for k in ("correct","wrong","abstained")})
def run():
    rows=[episode(seed,i,c,m) for seed in SEEDS for i,c in enumerate(amb.lab.cases(seed)) for m in MODES]
    return rows
def summarize(rows):
    return [dict(mode=m,tasks=sum(r["mode"]==m for r in rows),**{k:sum(r[k] for r in rows if r["mode"]==m)
        for k in ("delivered","correct_cargo","wrong_cargo","full_success","program_correct","program_wrong","actions","candidates","queries","correct","wrong","abstained")}) for m in MODES]
