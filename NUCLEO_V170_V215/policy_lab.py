"""V184–191: bounded declarative proposals, frozen validation gate."""
import hashlib,json
import list_synthesis as synth
MODES=("direct","learned","retry")
def select(rows):
    table={r["mode"]:r for r in synth.aggregate(rows)}
    return min(MODES,key=lambda m:(-table[m]["utility"],table[m]["candidates"],MODES.index(m)))
def run(out,library):
    train=synth.batch(synth.TRAIN,MODES,library);candidate=select(train)
    validation=synth.batch(synth.VAL,tuple(dict.fromkeys(("direct",candidate))),library)
    table={r["mode"]:r for r in synth.aggregate(validation)}
    base=table["direct"];new=table[candidate]
    passed=(candidate!="direct" and new["utility"]>base["utility"] and new["incorrect"]<=base["incorrect"] and new["solved"]>=base["solved"])
    chosen=candidate if passed else "direct"
    payload=dict(schema=1,candidate=candidate,selected=chosen,validation_passed=passed,library=library,deployment=False)
    def canon(p):return json.dumps(p,sort_keys=True,separators=(",",":")).encode()
    with out.open("xb") as f:f.write(canon(dict(payload=payload,sha256=hashlib.sha256(canon(payload)).hexdigest())))
    loaded=json.loads(out.read_bytes())
    if hashlib.sha256(canon(loaded["payload"])).hexdigest()!=loaded["sha256"]:raise ValueError("policy integrity")
    if loaded["payload"]["selected"] not in MODES:raise ValueError("policy")
    final=synth.batch(synth.TEST,synth.MODES,library)
    summary=dict(candidate=candidate,selected=chosen,validation_passed=passed,deployment=False,
        training=synth.aggregate(train),validation=synth.aggregate(validation),test=synth.aggregate(final))
    return summary,train,validation,final
