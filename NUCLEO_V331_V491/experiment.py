"""Independent evaluator; fixed train, validation and test cohorts."""
import argparse,json,random,itertools,hashlib
from pathlib import Path
from collections import Counter
from skills import OPS,RED,CAP,Oracle,synthesize,execute,random_macros,export_python
MOTIFS=(("inc","double","neg"),("abs","inc","double"),("half","inc","neg"),("mod3","double","inc"))
TRAIN=range(510001,510017)
VAL=range(520001,520017)
TEST=range(530001,530033)
MODES=("base","random","learned","active")
def reference(seq,red,x):
    # Independent arithmetic implementation, not the interpreter under test.
    def f(z):
        for o in seq:
            if o=="inc":z+=1
            elif o=="dec":z-=1
            elif o=="double":z+=z
            elif o=="neg":z=0-z
            elif o=="abs":z=max(z,-z)
            elif o=="half":z=z//2
            elif o=="mod3":z=z-3*(z//3)
            else:raise ValueError("reference")
        return z
    if red=="scalar":return f(x)
    ys=tuple(f(v) for v in x)
    return {"identity":lambda:ys,"sum":lambda:sum(ys),"min":lambda:min(ys),"max":lambda:max(ys)}[red]()
def example(seq,red,r):
    if red=="scalar":xs=r.sample(range(-13,14),27)
    else:
        xs=[]
        while len(xs)<27:
            x=tuple(r.randint(-12,12) for _ in range(r.randint(1,5)))
            if x not in xs:xs.append(x)
    rows=[(x,reference(seq,red,x)) for x in xs]
    return dict(fit=rows[:3],pool=rows[3:15],held=rows[15:],target=(seq,red))
def assess(case,result):
    p=result["program"];held=case["held"]
    n=len(held);correct=0 if p is None else sum(execute(p,x)==y for x,y in held)
    wrong=0 if p is None else n-correct
    return dict(solved=int(correct==n),incorrect=int(wrong>0),correct=correct,wrong=wrong,abstained=n if p is None else 0)
def acquire():
    lib=[];rows=[]
    for seed in TRAIN:
        r=random.Random(seed)
        for seq in MOTIFS:
            c=example(seq,"scalar",r)
            result=synthesize(c["fit"],Oracle(c["pool"]),active=True,kind="scalar")
            a=assess(c,result);p=result["program"]
            added=bool(a["solved"] and p and 2<=len(p[0])<=3 and p[0] not in lib and len(lib)<12)
            if added:lib.append(p[0])
            rows.append(dict(seed=seed,case=c,result=result,assessment=a,accepted=added))
    return tuple(lib),rows
def cases(seed):
    r=random.Random(seed);out=[]
    for i in range(4):
        if i<2:
            motif=MOTIFS[(seed+i)%len(MOTIFS)]
            tail=tuple(r.choice(OPS) for _ in range(r.randint(1,2)))
            s=motif+tail if r.randrange(2) else tail+motif
        else:
            while True:
                s=tuple(r.choice(OPS) for _ in range(r.randint(3,5)))
                if not any(m==s[j:j+len(m)] for m in MOTIFS for j in range(len(s)-len(m)+1)):break
        c=example(s,r.choice(RED),r)
        out.append((("related" if i<2 else "unrelated"),c))
    return out
def evaluate(seeds,lib,control):
    rows=[]
    for seed in seeds:
        for i,(family,c) in enumerate(cases(seed)):
            for mode in MODES:
                macros=lib if mode in ("learned","active") else control if mode=="random" else ()
                result=synthesize(c["fit"],Oracle(c["pool"]),macros,mode=="active")
                assessment=assess(c,result)
                # Count explicit macro presence; not causal use.
                p=result["program"];present=bool(p and any(m==p[0][j:j+len(m)] for m in macros for j in range(len(p[0])-len(m)+1)))
                rows.append(dict(seed=seed,index=i,family=family,mode=mode,case=c,result=result,assessment=assessment,macro_present=present))
    return rows
def summarize(rows):
    out=[]
    for f in ("all","related","unrelated"):
        for m in MODES:
            rr=[x for x in rows if (f=="all" or f==x["family"]) and m==x["mode"]]
            d=dict(family=f,mode=m,tasks=len(rr))
            for k in ("solved","incorrect","correct","wrong","abstained"):d[k]=sum(x["assessment"][k] for x in rr)
            d["candidates"]=sum(x["result"]["candidates"] for x in rr)
            d["queries"]=sum(len(x["result"]["queries"]) for x in rr)
            d["macro_present"]=sum(x["macro_present"] for x in rr)
            out.append(d)
    return out
def write_rows(path,rows):
    with path.open("x") as f:
        for x in rows:f.write(json.dumps(x,separators=(",",":"))+"\n")
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",required=True,type=Path);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    lib,train=acquire();control=random_macros(lib,888331)
    write_rows(a.out/"acquire.jsonl",train)
    v=evaluate(VAL,lib,control);vs=summarize(v)
    base=vs[0]
    eligible=[x for x in vs[1:4] if x["solved"]>base["solved"] and x["incorrect"]<=base["incorrect"]]
    selected=max(eligible,key=lambda x:(x["solved"],-x["incorrect"],-x["candidates"],-x["queries"])) if eligible else base
    gate=dict(policy=selected["mode"],promoted=selected["mode"]!="base",library=lib,random_library=control)
    frozen=json.dumps(gate,sort_keys=True);(a.out/"gate.json").write_text(frozen)
    t=evaluate(TEST,lib,control);ts=summarize(t)
    write_rows(a.out/"validation.jsonl",v);write_rows(a.out/"test.jsonl",t)
    summary=dict(acquisition=dict(tasks=len(train),solved=sum(x["assessment"]["solved"] for x in train),wrong=sum(x["assessment"]["incorrect"] for x in train),candidates=sum(x["result"]["candidates"] for x in train),queries=sum(len(x["result"]["queries"]) for x in train),macros=lib),
        gate=gate,gate_sha256=hashlib.sha256(frozen.encode()).hexdigest(),validation=vs,test=ts)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
