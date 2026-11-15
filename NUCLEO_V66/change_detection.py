"""Online revision of deterministic modular rules in bounded simulation."""
import argparse,json,random,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
N=17
SEEDS=tuple(8500017+30001*i for i in range(24))
MODES=("stale","rolling","reset","audited_reset")
STRATA=("stable","changed")
CUT=20
STEPS=40

def value(h,s):return (h[0]*s+h[1])%N
def fit(points):
    if len(points)!=2 or points[0][0]==points[1][0]:raise ValueError("distinct points required")
    (x,y),(u,v)=points
    a=(v-y)*pow((u-x)%N,-1,N)%N
    return a,(y-a*x)%N

class Memory:
    def __init__(self,mode):
        self.mode=mode;self.points=[];self.h=None;self.audit=0;self.epoch=0;self.alerts=[]
    def prediction(self,s):
        if self.h is None or (self.mode=="audited_reset" and self.audit<2):return None
        return value(self.h,s)
    def clear(self,step):
        self.h=None;self.points=[];self.audit=0;self.epoch+=1;self.alerts.append(step)
    def observe(self,s,t,step):
        if self.mode=="rolling":
            if self.h is not None and value(self.h,s)!=t:self.alerts.append(step)
            self.points=[p for p in self.points if p[0]!=s]+[(s,t)]
            self.points=self.points[-2:]
            if len(self.points)==2:self.h=fit(self.points)
            return
        if self.h is not None:
            if value(self.h,s)!=t:
                if self.mode!="stale":self.clear(step)
            elif self.mode=="audited_reset" and self.audit<2:self.audit+=1
            return
        self.points=[p for p in self.points if p[0]!=s]+[(s,t)]
        if len(self.points)==2:self.h=fit(self.points)

def world(seed,stratum):
    rng=random.Random(seed);first=(rng.randrange(N),rng.randrange(N))
    second=first
    while second==first:second=(rng.randrange(N),rng.randrange(N))
    stream=[]
    while len(stream)<STEPS:
        p=list(range(N));rng.shuffle(p);stream.extend(p)
    return first,second,[(s,value(second if stratum=="changed" and i>=CUT else first,s)) for i,s in enumerate(stream[:STEPS])]

def metric(rows):
    return dict(n=len(rows),correct=sum(r["prediction"]==r["target"] for r in rows),
        wrong=sum(r["prediction"] is not None and r["prediction"]!=r["target"] for r in rows),
        abstained=sum(r["prediction"] is None for r in rows),alerts=sum(r["alert"] for r in rows))

def run_case(stream,mode):
    m=Memory(mode);rows=[]
    for step,(s,t) in enumerate(stream):
        p=m.prediction(s);n=len(m.alerts)
        m.observe(s,t,step)
        rows.append(dict(step=step,state=s,target=t,prediction=p,alert=len(m.alerts)>n,epoch=m.epoch,rule=m.h,audit=m.audit))
    return rows

def recovery(rows,k):
    for i in range(CUT,len(rows)-k+1):
        if all(r["prediction"]==r["target"] for r in rows[i:i+k]):return i-CUT
    return None

def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for seed in SEEDS:
        for stratum in STRATA:
            first,second,stream=world(seed,stratum)
            for mode in MODES:
                rows=run_case(stream,mode)
                row=dict(seed=seed,stratum=stratum,mode=mode,before=metric(rows[:CUT]),after=metric(rows[CUT:]),
                    first_correct=recovery(rows,1) if stratum=="changed" else None,
                    three_correct=recovery(rows,3) if stratum=="changed" else None)
                results.append(row)
                (out/f"{seed}_{stratum}_{mode}.json").write_text(json.dumps(dict(result=row,first=first,second=second,events=rows),indent=2),encoding="utf-8")
    aggregate=[]
    for stratum in STRATA:
        for mode in MODES:
            r=[x for x in results if x["stratum"]==stratum and x["mode"]==mode]
            d=dict(stratum=stratum,mode=mode)
            for phase in ("before","after"):d[phase]={k:sum(x[phase][k] for x in r) for k in r[0][phase]}
            for key in ("first_correct","three_correct"):
                values=[x[key] for x in r if x[key] is not None]
                d[key+"_recovered"]=len(values);d[key+"_mean_delay"]=sum(values)/len(values) if values else None
            aggregate.append(d)
    (out/"summary.json").write_text(json.dumps(dict(protocol="V66-change-detection-v1",aggregate=aggregate,by_seed=results),indent=2),encoding="utf-8")
    print(json.dumps(aggregate,indent=2))

class Tests(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(fit([(2,10),(5,2)]),(3,4))
    def test_reset(self):
        m=Memory("reset");m.observe(0,1,0);m.observe(1,2,1)
        self.assertEqual(m.prediction(2),3)
        m.observe(2,8,2);self.assertIsNone(m.prediction(3));self.assertEqual(m.epoch,1)
    def test_audit(self):
        m=Memory("audited_reset")
        for s in range(4):
            self.assertIsNone(m.prediction(s));m.observe(s,s, s)
        self.assertEqual(m.prediction(4),4)
    def test_stable(self):
        _,_,s=world(SEEDS[0],"stable")
        for mode in MODES:self.assertEqual(metric(run_case(s,mode))["wrong"],0)

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V66 required")
    run(a.output.resolve())
if __name__=="__main__":main()
