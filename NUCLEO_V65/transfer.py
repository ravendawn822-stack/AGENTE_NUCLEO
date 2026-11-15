"""Contextual transfer of family priorities in fixed modular DSL."""
import argparse,json,random,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
N=17
SEEDS=tuple(8400017+30001*i for i in range(12))
FAMILIES=(1,2,3)
MODES=("fixed","reverse","learned","swap")
CONTEXTS=("A","B")

def predict(h,s):
    return sum(v*pow(s,i,N) for i,v in enumerate(h))%N

def interpolate(points,degree):
    # Unique polynomial of degree at most degree from degree+1 distinct points.
    rows=[[pow(s,i,N) for i in range(degree+1)]+[t] for s,t in points[:degree+1]]
    for i in range(degree+1):
        pivot=next(j for j in range(i,degree+1) if rows[j][i])
        rows[i],rows[pivot]=rows[pivot],rows[i]
        inv=pow(rows[i][i],-1,N);rows[i]=[(x*inv)%N for x in rows[i]]
        for j in range(degree+1):
            if j!=i:
                f=rows[j][i];rows[j]=[(x-f*y)%N for x,y in zip(rows[j],rows[i])]
    return tuple(row[-1] for row in rows)

def discover(points,order,cap):
    probes=0
    for degree in order[:cap]:
        probes+=1
        h=interpolate(points[:4],degree)
        if degree>1 and h[-1]==0:continue
        if not all(predict(h,s)==t for s,t in points[:4]):continue
        if all(predict(h,s)==t for s,t in points[4:]):return degree,h,probes
    return None,None,probes

def tasks(seed,context,phase):
    rng=random.Random(seed^(0x6501 if context=="A" else 0x6502)^(0x650000 if phase=="test" else 0))
    families=[1 if context=="A" else 2]*6+[3]*2;rng.shuffle(families)
    out=[]
    for degree in families:
        h=tuple(rng.randrange(N) for i in range(degree))+(rng.randrange(1,N),)
        sample=rng.sample(range(N),6);points=[(s,predict(h,s)) for s in sample]
        out.append(dict(degree=degree,coefficients=h,points=points))
    return out

def priority(rows):
    counts={d:0 for d in FAMILIES}
    for task in rows:
        d,h,n=discover(task["points"],FAMILIES,3)
        if d is not None:counts[d]+=1
    return tuple(sorted(FAMILIES,key=lambda d:(-counts[d],d))),counts

def evaluate(task,order):
    degree,h,probes=discover(task["points"],order,2)
    seen={s for s,t in task["points"]};rows=[]
    for s in range(N):
        if s not in seen:
            p=predict(h,s) if h is not None else None
            rows.append(dict(state=s,prediction=p,target=predict(task["coefficients"],s)))
    return dict(degree=degree,h=h,probes=probes,correct=sum(x["prediction"]==x["target"] for x in rows),
        wrong=sum(x["prediction"] is not None and x["prediction"]!=x["target"] for x in rows),
        abstained=sum(x["prediction"] is None for x in rows),rows=rows)

def run(out):
    out.mkdir(parents=True,exist_ok=False);records=[]
    for seed in SEEDS:
        train={c:tasks(seed,c,"train") for c in CONTEXTS};prior={c:priority(t) for c,t in train.items()}
        for context in CONTEXTS:
            test=tasks(seed,context,"test");other="B" if context=="A" else "A"
            orders={"fixed":FAMILIES,"reverse":tuple(reversed(FAMILIES)),"learned":prior[context][0],"swap":prior[other][0]}
            for mode,order in orders.items():
                rows=[evaluate(task,order) for task in test]
                row=dict(seed=seed,context=context,mode=mode,order=order,tasks=len(rows),
                    solved=sum(r["degree"] is not None for r in rows),
                    **{k:sum(r[k] for r in rows) for k in ("probes","correct","wrong","abstained")})
                records.append(row)
                (out/f"{seed}_{context}_{mode}.json").write_text(json.dumps(dict(result=row,train=train,prior=prior,test=test,rows=rows),indent=2),encoding="utf-8")
    aggregate=[dict(context=c,mode=m,**{k:sum(r[k] for r in records if r["context"]==c and r["mode"]==m)
        for k in ("tasks","solved","probes","correct","wrong","abstained")}) for c in CONTEXTS for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V65-context-transfer-v1",aggregate=aggregate,by_seed=records),indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_interpolation(self):
        for h in ((4,0),(4,2),(1,2,3),(1,2,3,4)):
            points=[(s,predict(h,s)) for s in (2,7,12,1,8,15)]
            d,p,n=discover(points,FAMILIES,3);self.assertEqual(p,h)
    def test_budget(self):
        points=[(s,predict((1,2,3,4),s)) for s in range(6)]
        self.assertEqual(discover(points,FAMILIES,2),(None,None,2))
    def test_priority(self):
        for c in CONTEXTS:
            order,counts=priority(tasks(SEEDS[0],c,"train"))
            self.assertEqual(order[0],1 if c=="A" else 2);self.assertEqual(sum(counts.values()),8)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V65 required")
    run(a.output.resolve())
if __name__=="__main__":main()
