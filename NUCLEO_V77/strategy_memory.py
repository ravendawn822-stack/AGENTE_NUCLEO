"""Fixed-family strategy memory, local JSON only."""
import argparse,hashlib,json,random,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V75"))
from investigation import N,predict,probe,score
TRAIN=tuple(30000019+30001*i for i in range(16))
TEST=tuple(29000019+30001*i for i in range(24))
FAMILIES=(1,2,3)
CONTEXTS=("A","B")
MODES=("fixed","reverse","learned","swap","global")

def tasks(seed,context):
    rng=random.Random(seed^(0x7701 if context=="A" else 0x7702))
    degrees=([1]*8+[2]*3+[3]) if context=="A" else ([1]+[2]*3+[3]*8)
    rng.shuffle(degrees);result=[]
    for d in degrees:
        h=tuple(rng.randrange(N) for _ in range(d))+(rng.randrange(1,N),)
        xs=rng.sample(range(N),6)
        result.append(dict(degree=d,points=[(s,predict(h,s)) for s in xs],
                           held=[(s,predict(h,s)) for s in range(N) if s not in xs]))
    return result

def identify(points,order,cap):
    for i,d in enumerate(order[:cap],1):
        h=probe(points,d)
        if h is not None:return d,h,i
    return None,None,min(cap,len(order))

def train():
    counts={c:{d:0 for d in FAMILIES} for c in CONTEXTS}
    for seed in TRAIN:
        for c in CONTEXTS:
            for t in tasks(seed,c):
                d,h,n=identify(t["points"],FAMILIES,3)
                if h is not None:counts[c][d]+=1
    return {c:tuple(counts[c][d] for d in FAMILIES) for c in CONTEXTS}

def priority(counts,context):
    values=tuple(sum(counts[c][i] for c in CONTEXTS) for i in range(3)) if context=="global" else counts[context]
    return tuple(sorted(FAMILIES,key=lambda d:(-values[d-1],d)))

def canonical(p):return json.dumps(p,sort_keys=True,separators=(",",":")).encode("utf-8")
def save(path,counts):
    p=dict(schema=1,counts=counts)
    with path.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
def load(path):
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("size")
    a=json.loads(raw);p=a["payload"]
    if a["sha256"]!=hashlib.sha256(canonical(p)).hexdigest() or p["schema"]!=1:raise ValueError("integrity")
    if set(p["counts"])!=set(CONTEXTS):raise ValueError("context")
    if any(len(v)!=3 or any(type(x) is not int or x<0 for x in v) for v in p["counts"].values()):raise ValueError("counts")
    return {c:tuple(p["counts"][c]) for c in CONTEXTS}

def run(out):
    out.mkdir(parents=True,exist_ok=False);counts=train();path=out/"memory.json";save(path,counts);counts=load(path);rows=[]
    for seed in TEST:
        for c in CONTEXTS:
            data=tasks(seed,c);other="B" if c=="A" else "A"
            orders={"fixed":FAMILIES,"reverse":tuple(reversed(FAMILIES)),"learned":priority(counts,c),
                    "swap":priority(counts,other),"global":priority(counts,"global")}
            for mode,order in orders.items():
                results=[]
                for t in data:
                    d,h,n=identify(t["points"],order,2)
                    results.append(dict(degree=d,model=h,probes=n,**score(t,h)))
                row=dict(seed=seed,context=c,mode=mode,order=order,solved=sum(x["model"] is not None for x in results),
                    **{k:sum(x[k] for x in results) for k in ("probes","correct","wrong","abstained")})
                row["utility"]=row["correct"]-4*row["wrong"];rows.append(row)
                (out/f"{seed}_{c}_{mode}.json").write_text(json.dumps(dict(result=row,tasks=data,results=results),indent=2),encoding="utf-8")
    agg=[dict(context=c,mode=m,**{k:sum(r[k] for r in rows if r["context"]==c and r["mode"]==m)
        for k in ("solved","probes","correct","wrong","abstained","utility")}) for c in CONTEXTS for m in MODES]
    (out/"summary.json").write_text(json.dumps(dict(protocol="V77-strategy-memory-v1",counts=counts,aggregate=agg,by_seed=rows),indent=2),encoding="utf-8");print(json.dumps(agg,indent=2))

class Tests(unittest.TestCase):
    def test_memory(self):
        counts={"A":(8,3,1),"B":(1,3,8)}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.json";save(p,counts);self.assertEqual(load(p),counts)
            with self.assertRaises(FileExistsError):save(p,counts)
            a=json.loads(p.read_bytes());a["payload"]["counts"]["A"][0]=0;p.write_bytes(canonical(a))
            with self.assertRaises(ValueError):load(p)
        self.assertEqual(priority(counts,"A"),(1,2,3));self.assertEqual(priority(counts,"B"),(3,2,1))
    def test_split(self):self.assertFalse(set(TRAIN)&set(TEST))
    def test_identify(self):
        p=[(s,predict((1,2,3,4),s)) for s in range(6)]
        self.assertEqual(identify(p,FAMILIES,2),(None,None,2))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output directory inside V77 required")
    run(a.output.resolve())
if __name__=="__main__":main()
