"""Assemble independently searched subprograms within an identical candidate cap."""
import sys
from pathlib import Path
for v in (109,110,111):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import limits as lab
from partition import options
from partial import solve_parts
s=lab.s;w=lab.w
SEEDS=tuple(72000019+30001*i for i in range(24))
MODES=("weighted","generalized","all_known","split","split_known")
def split_search(rows,cap=s.CAP):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    opts=options(rows);left=cap;events=[]
    for i,op in enumerate(opts):
        allot=left//(len(opts)-i)
        result=solve_parts(op,allot);left-=result["spent"]
        event=dict(predicate=op["predicate"],sizes=[len(op["yes"]),len(op["no"])],parts=result["parts"],spent=result["spent"],assembled=False)
        events.append(event)
        if result["programs"] is None:continue
        if left<=0:raise AssertionError("assembly budget")
        p=(("if",op["predicate"],*result["programs"]),);left-=1;event["spent"]+=1
        try:p=w.validate(p)
        except w.Invalid:continue
        if s.matches(p,rows):
            event["assembled"]=True
            return dict(program=p,candidates=cap-left,events=events)
    return dict(program=None,candidates=cap-left,events=events)
def search(fit,audit,mode,library,novel,cap=s.CAP):
    if mode in ("weighted","generalized"):
        return lab.ins.search(fit,mode,library,novel,(),cap)
    if mode=="all_known":return w.search(fit+audit,cap=cap)
    if mode=="split":return split_search(fit,cap)
    if mode=="split_known":return split_search(fit+audit,cap)
    raise ValueError("mode")
def evaluate(c,r):
    a=lab.assess(c,r)
    return dict(no_candidate=int(r["program"] is None),**a)
