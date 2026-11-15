"""V192–207: actual data dependencies, synthetic CSV tasks, independent scoring."""
import csv,io,random
from collections import Counter
from fractions import Fraction
import list_synthesis as synth
import nucleus
import vm
def get(rows,i):return next(r for r in rows if r["id"]==i)
def episode(seed,mode,library):
    c=synth.cases(seed)[0];rng=random.Random(seed^0x19201)
    core=nucleus.Nucleus(seed=seed,mode=mode,library=library,start=rng.randrange(8))
    ids={}
    ids["delivery"]=core.add("deliver")
    ids["solve"]=core.add("list_solve",dict(fit=c["fit"],audit=c["audit"]))
    xs=tuple(rng.randrange(-5,6) for _ in range(4))
    ids["apply"]=core.add("list_apply",dict(program=ids["solve"],cargo=ids["delivery"],input=xs),(ids["solve"],ids["delivery"]))
    ids["stats"]=core.add("stats",dict(source=ids["apply"]),(ids["apply"],))
    ac=nucleus.amb.lab.cases(seed)[0]
    ids["arithmetic"]=core.add("arithmetic",dict(fit=ac["fit"],audit=ac["audit"],seed=seed))
    rows=core.run()
    delivery=get(rows,ids["delivery"]);solved=get(rows,ids["solve"]);applied=get(rows,ids["apply"]);stat=get(rows,ids["stats"]);arith=get(rows,ids["arithmetic"])
    expected=synth.reference(c["target"],xs+(4,))
    output_correct=applied["status"]=="done" and vm.value(applied["result"]["value"])==expected
    assess=synth.assess(c,solved["result"]) if solved["status"]=="done" else dict(solved=0,incorrect=0)
    exp_values=(expected,) if type(expected) is int else expected
    n=len(exp_values);total=sum(exp_values);mean=Fraction(total,n) if n else None
    expected_stats=dict(count=n,total=total,mean=[mean.numerator,mean.denominator] if n else None,
        frequencies={str(k):v for k,v in sorted(Counter(exp_values).items())})
    stat_correct=stat["status"]=="done" and stat["result"]==expected_stats
    arithmetic_correct=arith["status"]=="done" and nucleus.amb.s.score(arith["result"]["program"],ac["held"])["solved"]
    result=dict(seed=seed,mode=mode,goals=rows,knowledge=core.mem.counts(),case=c,expected=expected,
        solved=int(assess["solved"]),incorrect=int(assess["incorrect"]),output_correct=int(output_correct),
        stats_correct=int(stat_correct),arithmetic_correct=int(arithmetic_correct),
        success=int(delivery["status"]=="done" and assess["solved"] and output_correct and stat_correct and arithmetic_correct),
        blocked=sum(g["status"]=="blocked" for g in rows),actions=delivery["result"].get("actions",0),
        candidates=solved["result"].get("candidates",0)+arith["result"].get("candidates",0))
    core.mem.close();return result
def parse_csv(text):
    if type(text) is not str or len(text)>4096:raise ValueError("CSV size")
    reader=csv.reader(io.StringIO(text),strict=True)
    if next(reader,None)!=["value","category"]:raise ValueError("header")
    values=[];categories=[]
    for row in reader:
        if len(row)!=2 or len(values)>=32 or len(row[0])>8 or row[1] not in ("A","B","C"):raise ValueError("row")
        v=int(row[0]);vm.value(v);values.append(v);categories.append(row[1])
    return tuple(values),categories
def csv_episode(seed,mode,library):
    c=synth.cases(seed)[0];rng=random.Random(seed^0x20001)
    raw=[(rng.randrange(-5,6),rng.choice(("A","B","C"))) for _ in range(5)]
    text="value,category\n"+"".join(f"{v},{k}\n" for v,k in raw)
    xs,cats=parse_csv(text);r=synth.solve(c["fit"],c["audit"],mode,library)
    a=synth.assess(c,r);output=vm.run_pipeline(r["program"],xs) if r["program"] is not None else None
    expected=synth.reference(c["target"],[v for v,k in raw])
    stats=nucleus.stats(xs);stats["categories"]={k:cats.count(k) for k in sorted(set(cats))}
    mean=Fraction(sum(v for v,k in raw),len(raw));ref=dict(count=len(raw),total=sum(v for v,k in raw),
        mean=[mean.numerator,mean.denominator],frequencies={str(k):v for k,v in sorted(Counter(v for v,k in raw).items())},
        categories=dict(sorted(Counter(k for v,k in raw).items())))
    return dict(seed=seed,mode=mode,case=c,csv=text,search=r,output=output,expected=expected,
        transformed=int(output==expected),stats_correct=int(stats==ref),stats=stats,stats_expected=ref,**a)
def aggregate(rows,keys):
    return [dict(mode=m,tasks=sum(r["mode"]==m for r in rows),**{k:sum(r[k] for r in rows if r["mode"]==m) for k in keys})
        for m in sorted({r["mode"] for r in rows})]
def invalid_csv():
    cases=("value,bad\n1,A\n","value,category\nxyz,A\n","value,category\n1,Z\n","value,category\n1,A,other\n")
    rows=[]
    for x in cases:
        try:parse_csv(x);ok=False
        except (ValueError,csv.Error):ok=True
        rows.append(dict(input=x,rejected=ok))
    return rows
