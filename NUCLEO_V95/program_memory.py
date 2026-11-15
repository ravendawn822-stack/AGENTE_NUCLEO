"""Acquire validated finite program fragments and compare frozen vocabularies."""
import hashlib,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V94"))
from audit import assess
from synthesis import seq,case,search,matches,aggregate,DOMAIN,CAP,execute
from language import validate,OPS
TRAIN=tuple(46000019+30001*i for i in range(8))
TEST=tuple(48000019+30001*i for i in range(24))
MOTIFS=(seq("inc","double"),seq("neg","inc","double"),seq("half","inc","double"),
        seq("abs","inc"),seq("mod3","neg"),seq("inc","half"),seq("double","inc","neg"),seq("double","inc"))
MODES=("primitive","structured","learned","random")
def acquire():
    library=[];ledger=[]
    for seed,target in zip(TRAIN,MOTIFS):
        c=case(seed,target,"training");r=search(c["fit"])
        a=assess(c,r);p=a["program"]
        accepted=p is not None and a["solved"]==1
        if accepted and p and p not in library:library.append(p)
        ledger.append(dict(seed=seed,case=c,search=r,assessment=a,accepted=accepted))
    rng=random.Random(95001)
    control=tuple(seq(*(rng.choice(OPS) for _ in p)) for p in library)
    return tuple(library),control,ledger
def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":")).encode("utf-8")
def save(path,library,control):
    payload=dict(schema=1,library=library,control=control)
    with path.open("xb") as f:f.write(canonical(dict(payload=payload,sha256=hashlib.sha256(canonical(payload)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    e=json.loads(raw);p=e["payload"]
    if p["schema"]!=1 or e["sha256"]!=hashlib.sha256(canonical(p)).hexdigest():raise ValueError("integrity")
    if len(p["library"])!=len(p["control"]) or len(p["library"])>8:raise ValueError("library")
    library=tuple(validate(x) for x in p["library"]);control=tuple(validate(x) for x in p["control"])
    if len(set(library))!=len(library) or any(not p for p in library+control):raise ValueError("invalid macro")
    return library,control
def cases(seed):
    targets=(MOTIFS[0]+MOTIFS[3]+seq("neg"),MOTIFS[2]+MOTIFS[7],
             MOTIFS[6]+MOTIFS[5]+seq("inc"),MOTIFS[4]+MOTIFS[1]+seq("abs"))
    return [case(seed+997*j,p,"composition") for j,p in enumerate(targets)]
def options(mode,library,control):
    if mode not in MODES:raise ValueError("mode")
    return mode!="primitive",library if mode=="learned" else control if mode=="random" else ()
def experiment(library,control):
    rows=[]
    for seed in TEST:
        for i,c in enumerate(cases(seed)):
            for mode in MODES:
                structured,macros=options(mode,library,control)
                r=search(c["fit"],structured,macros)
                rows.append(dict(seed=seed,task=i,mode=mode,case=c,search=r,**assess(c,r)))
    return rows
def redundancy(macros):
    return len(macros)-len({tuple(execute(p,x) for x in DOMAIN) for p in macros})
