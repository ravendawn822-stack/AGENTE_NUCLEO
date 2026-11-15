"""Extract small fragments from externally verified training solutions."""
import collections,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V97"))
import weighted as w
syn=w.syn
from language import validate,Invalid
TRAIN=tuple(54000019+30001*i for i in range(16))
MOTIFS=(syn.seq("inc","double","neg"),syn.seq("abs","inc","double"),
        syn.seq("mod3","neg","inc"),syn.seq("inc","half","double"),
        syn.seq("double","inc","neg"),syn.seq("neg","inc","double"),
        syn.seq("half","inc","double"),syn.seq("abs","inc","neg"))
def signature(p):return tuple(syn.execute(p,x) for x in syn.DOMAIN)
def acquire():
    ledger=[];support=collections.defaultdict(set)
    for i,seed in enumerate(TRAIN):
        p=MOTIFS[i%len(MOTIFS)]
        target=p if i<8 else p+syn.seq("inc" if i%2==0 else "neg")
        c=syn.case(seed,target,"training");r=w.search(c["fit"]);q=r["program"]
        accepted=q is not None and syn.matches(q,c["audit"]) and syn.matches(q,c["held"])
        ledger.append(dict(seed=seed,case=c,search=r,accepted=accepted))
        if accepted:
            for size in (2,3):
                for j in range(len(q)-size+1):
                    f=validate(q[j:j+size]);support[f].add(i)
    library=[];seen={signature(()),*(signature(a) for a in w.atoms(False))}
    provenance=[]
    for p,ids in sorted(support.items(),key=lambda z:(-len(z[1]),len(z[0]),repr(z[0]))):
        try:s=signature(p)
        except Invalid:continue
        if s in seen:continue
        seen.add(s);library.append(p);provenance.append(dict(program=p,sources=sorted(ids)))
        if len(library)==8:break
    return tuple(library),ledger,provenance
