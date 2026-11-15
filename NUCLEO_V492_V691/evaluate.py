import random,json,argparse,hashlib
from pathlib import Path
from pipeline import OPS,STRUCT,RED,Oracle,solve,execute,export
VAL=range(650001,650017)
TEST=range(660001,660033)
MODES=("base","random","learned","alternating")
MOTIFS=(("inc","double","neg"),("abs","inc","double"),("half","inc","neg"),("mod3","double","inc"))
def reference(p,data):
    seq,op,stage,red=p
    def struct(v):
        if op=="same":return list(v)
        if op=="reverse":return list(v)[::-1]
        if op=="sort":return sorted(v)
        if op=="unique":return [x for i,x in enumerate(v) if x not in v[:i]]
        if op=="nonnegative":return [x for x in v if x>=0]
    items=struct(list(data)) if stage=="pre" else list(data)
    for o in seq:
        if o=="inc":items=[x+1 for x in items]
        elif o=="dec":items=[x-1 for x in items]
        elif o=="double":items=[x+x for x in items]
        elif o=="neg":items=[0-x for x in items]
        elif o=="abs":items=[max(x,-x) for x in items]
        elif o=="half":items=[x//2 for x in items]
        elif o=="mod3":items=[x-3*(x//3) for x in items]
    if stage=="post":items=struct(items)
    if red=="identity":return tuple(items)
    if red=="count":return len(items)
    if red=="sum":return sum(items)
    if not items:return None
    return sorted(items)[0 if red=="min" else -1]
def cases(seed):
    rng=random.Random(seed)
    for i in range(4):
        if i<2:
            m=MOTIFS[(seed+i)%4];tail=tuple(rng.choice(OPS) for _ in range(rng.randint(1,2)));seq=m+tail if rng.randrange(2) else tail+m
        else:
            while True:
                seq=tuple(rng.choice(OPS) for _ in range(rng.randint(3,5)))
                if not any(seq[j:j+len(m)]==m for m in MOTIFS for j in range(len(seq)-len(m)+1)):break
        p=(seq,rng.choice(STRUCT[1:]),rng.choice(("pre","post")),rng.choice(RED))
        xs=[]
        while len(xs)<27:
            x=tuple(rng.randint(-12,12) for _ in range(rng.randint(2,6)))
            if x not in xs:xs.append(x)
        rows=[(x,reference(p,x)) for x in xs]
        yield dict(family="related" if i<2 else "unrelated",target=p,fit=rows[:3],pool=rows[3:15],held=rows[15:])
def run(seeds,lib,control):
    rows=[]
    for seed in seeds:
        for i,c in enumerate(cases(seed)):
            for mode in MODES:
                r=solve(c["fit"],Oracle(c["pool"]),lib,control,mode);p=r["program"]
                right=sum(p is not None and execute(p,x)==y for x,y in c["held"])
                rows.append(dict(seed=seed,index=i,mode=mode,case=c,result=r,solved=int(right==12),
                    incorrect=int(p is not None and right!=12),correct=right,wrong=12-right if p is not None else 0,abstained=12 if p is None else 0))
    return rows
def summarize(rows):
    result=[]
    for f in ("all","related","unrelated"):
        for m in MODES:
            rr=[x for x in rows if x["mode"]==m and (f=="all" or x["case"]["family"]==f)]
            d=dict(family=f,mode=m,tasks=len(rr))
            for k in ("solved","incorrect","correct","wrong","abstained"):d[k]=sum(x[k] for x in rr)
            for k in ("candidates","duplicates"):d[k]=sum(x["result"][k] for x in rr)
            d["queries"]=sum(len(x["result"]["queries"]) for x in rr);result.append(d)
    return result
def tests():
    rng=random.Random(42)
    for i in range(80):
        p=(tuple(rng.choice(OPS) for j in range(4)),rng.choice(STRUCT),rng.choice(("pre","post")),rng.choice(RED))
        x=tuple(rng.randint(-5,5) for j in range(6))
        y=reference(p,x);assert execute(p,x)==y
        ns={};exec(compile(export(p),"<fixed templates>","exec"),ns);assert ns["solve"](x)==y
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);tests()
    libdata=json.loads(Path(__file__).with_name("library.json").read_text())
    lib=libdata["library"];control=libdata["random_library"]
    v=run(VAL,lib,control);sv=summarize(v);base=sv[0]
    eligible=[x for x in sv[1:4] if x["solved"]>base["solved"] and x["incorrect"]<=base["incorrect"] and x["wrong"]<=base["wrong"]]
    chosen=max(eligible,key=lambda x:(x["solved"],-x["incorrect"],-x["wrong"],-x["candidates"],-x["queries"])) if eligible else base
    gate=dict(policy=chosen["mode"],promoted=chosen["mode"]!="base",library=lib,random_library=control)
    frozen=json.dumps(gate,sort_keys=True);(a.out/"gate.json").write_text(frozen)
    t=run(TEST,lib,control);st=summarize(t)
    for n,rr in (("validation",v),("test",t)):
        with (a.out/(n+".jsonl")).open("x") as f:
            for row in rr:f.write(json.dumps(row,separators=(",",":"))+"\n")
    summary=dict(gate=gate,gate_sha256=hashlib.sha256(frozen.encode()).hexdigest(),python_equivalence=80,validation=sv,test=st)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=="__main__":main()
