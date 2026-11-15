"""Bounded alternative searches over known examples; no access to hidden targets."""
import sys
from pathlib import Path
for v in (97,112,115,116):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
import weighted as w
import compose as cm
import hypotheses as hyp
import ambiguity as amb
s=amb.s
def expand(known,cap):
    if type(cap) is not int or not 0<=cap<=s.CAP:raise ValueError("cap")
    left=cap;pool=[];seen=set();ledger=[];evals=0
    for name in ("split","weighted"):
        allot=left//2 if name=="split" else left
        if not allot:continue
        r=cm.split_search(known,allot) if name=="split" else w.search(known,cap=allot)
        left-=r["candidates"];ledger.append(dict(method=name,search=r))
        p=r["program"]
        if p is None or not s.matches(p,known):continue
        try:
            vals=tuple(s.execute(p,x) for x in s.DOMAIN);evals+=len(s.DOMAIN)
        except w.Invalid:continue
        if vals in seen:continue
        seen.add(vals);pool.append(dict(program=p,values=vals,kind="expanded"))
    return dict(pool=pool,candidates=cap-left,ledger=ledger,signature_evaluations=evals)
