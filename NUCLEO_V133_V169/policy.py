"""V157–V162: offline selection of declarative policies; no executable self-modification."""
import json,hashlib
import exploration as exp
from world import MOVES
TRAIN=tuple(104000019+30001*i for i in range(16))
VAL=tuple(106000019+30001*i for i in range(16))
TEST=tuple(108000019+30001*i for i in range(24))
ORDERS=(MOVES,(1,2,0),(2,0,1))
def batch(seeds,order):
    if order not in ORDERS:raise ValueError("configuration")
    return [exp.episode(seed,"directed",order=order)[0] for seed in seeds]
def compact(rows):
    return dict(episodes=len(rows),success=sum(r["success"] for r in rows),actions=sum(r["actions"] for r in rows),
        decisions=sum(r["decisions"] for r in rows))
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def select(out):
    training=[dict(order=o,result=compact(batch(TRAIN,o))) for o in ORDERS]
    best=min(training,key=lambda p:(-p["result"]["success"],p["result"]["actions"],ORDERS.index(p["order"])))["order"]
    base=compact(batch(VAL,MOVES));candidate=compact(batch(VAL,best))
    passed=best!=MOVES and candidate["success"]>=base["success"] and candidate["actions"]<base["actions"]
    chosen=best if passed else MOVES
    p=dict(schema=1,order=chosen,validation_passed=passed)
    with out.open("xb") as f:f.write(canonical(dict(payload=p,sha256=hashlib.sha256(canonical(p)).hexdigest())))
    e=json.loads(out.read_bytes())
    if e["sha256"]!=hashlib.sha256(canonical(e["payload"])).hexdigest() or e["payload"]["schema"]!=1:raise ValueError("policy integrity")
    chosen=tuple(e["payload"]["order"])
    if chosen not in ORDERS:raise ValueError("policy")
    rows=[]
    for name,o in (("baseline",MOVES),("candidate",best),("gate",chosen)):
        for r in batch(TEST,o):r.update(policy=name,order=o);rows.append(r)
    return dict(training=training,validation=dict(baseline=base,candidate=candidate),candidate_order=best,selected_order=chosen,
        validation_passed=passed,aggregate=[dict(policy=n,**compact([r for r in rows if r["policy"]==n])) for n in ("baseline","candidate","gate")],
        deployment=False),rows
