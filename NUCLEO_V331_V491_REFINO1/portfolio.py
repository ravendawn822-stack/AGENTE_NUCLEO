"""Fixed-budget type-aware portfolio; no evaluator data in solver."""
import argparse,sys,json,hashlib
from pathlib import Path
from collections import Counter,deque
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V331_V491"))
from skills import OPS,RED,CAP,MAX_LEN,execute,Oracle
from experiment import cases,assess
VAL=range(550001,550017)
TEST=range(560001,560033)
MODES=("base","random","learned","portfolio","adaptive")
def stream(macros,reds):
    ts=tuple(dict.fromkeys(tuple(tuple(m) for m in macros)+tuple((o,) for o in OPS)))
    q=deque([()]);seen={()}
    while q:
        p=q.popleft()
        for tok in ts:
            seq=p+tok
            if len(seq)>MAX_LEN or seq in seen:continue
            seen.add(seq)
            for r in reds:yield (seq,r)
            if len(seq)<MAX_LEN:q.append(seq)
def solve(fit,oracle,lib,control,mode):
    kinds={type(y) for x,y in fit}
    if kinds=={tuple}:reds=("identity",)
    elif kinds=={int}:reds=("sum","min","max")
    else:raise ValueError("inconsistent types")
    base=stream((),reds);learned=stream(lib,reds);rand=stream(control,reds)
    streams=dict(base=base,learned=learned,random=rand)
    tried=set();ok=[];dup=0;draws=Counter();strategy=None
    def choose():
        nonlocal strategy
        n=len(tried)
        if mode in ("base","learned","random"):return mode
        if mode=="portfolio":return ("base","learned")[n%2]
        if n<240:return "learned"
        if strategy is None:strategy="alternate" if ok else "fallback"
        if strategy=="fallback":return "base"
        return ("base","learned")[n%2]
    while len(tried)<CAP:
        name=choose()
        try:p=next(streams[name])
        except StopIteration:break
        if p in tried:
            dup+=1;continue
        tried.add(p);draws[name]+=1
        if all(execute(p,x)==y for x,y in fit):ok.append(p)
    remaining=list(oracle.pool);trace=[]
    while ok and remaining and len(trace)<oracle.limit:
        def disagreement(x):
            n=len(ok);hist=Counter(execute(p,x) for p in ok)
            return n*n-sum(v*v for v in hist.values())
        x=max(remaining,key=disagreement);remaining.remove(x);y=oracle.ask(x)
        n=len(ok);ok=[p for p in ok if execute(p,x)==y]
        trace.append(dict(input=x,output=y,before=n,after=len(ok)))
    return dict(program=min(ok,key=lambda p:(len(p[0]),p)) if ok else None,
        candidates=len(tried),duplicates=dup,draws=dict(draws),remaining=len(ok),queries=trace,strategy=strategy)
def evaluate(seeds,lib,control):
    rows=[]
    for s in seeds:
        for i,(f,c) in enumerate(cases(s)):
            for mode in MODES:
                result=solve(c["fit"],Oracle(c["pool"]),lib,control,mode)
                rows.append(dict(seed=s,index=i,family=f,mode=mode,case=c,result=result,assessment=assess(c,result)))
    return rows
def summary(rows):
    out=[]
    for family in ("all","related","unrelated"):
        for mode in MODES:
            rs=[r for r in rows if r["mode"]==mode and (family=="all" or r["family"]==family)]
            d=dict(family=family,mode=mode,tasks=len(rs))
            for k in ("solved","incorrect","correct","wrong","abstained"):d[k]=sum(r["assessment"][k] for r in rs)
            d["candidates"]=sum(r["result"]["candidates"] for r in rs)
            d["duplicates"]=sum(r["result"]["duplicates"] for r in rs)
            d["queries"]=sum(len(r["result"]["queries"]) for r in rs)
            d["fallbacks"]=sum(r["result"]["strategy"]=="fallback" for r in rs)
            out.append(d)
    return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);ap.add_argument("--library",type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    frozen=json.loads(a.library.read_text());lib=tuple(tuple(m) for m in frozen["library"]);control=tuple(tuple(m) for m in frozen["random_library"])
    v=evaluate(VAL,lib,control);sv=summary(v);base=sv[0]
    eligible=[x for x in sv[1:len(MODES)] if x["solved"]>base["solved"] and x["incorrect"]<=base["incorrect"] and x["wrong"]<=base["wrong"]]
    selected=max(eligible,key=lambda x:(x["solved"],-x["incorrect"],-x["wrong"],-x["candidates"],-x["queries"])) if eligible else base
    gate=dict(policy=selected["mode"],promoted=selected["mode"]!="base",library=lib,random_library=control)
    g=json.dumps(gate,sort_keys=True);(a.out/"gate.json").write_text(g)
    t=evaluate(TEST,lib,control);st=summary(t)
    for name,rs in (("validation",v),("test",t)):
        with (a.out/(name+".jsonl")).open("x") as f:
            for row in rs:f.write(json.dumps(row,separators=(",",":"))+"\n")
    res=dict(gate=gate,gate_sha256=hashlib.sha256(g.encode()).hexdigest(),validation=sv,test=st)
    (a.out/"summary.json").write_text(json.dumps(res,indent=2));print(json.dumps(res))
if __name__=="__main__":main()
