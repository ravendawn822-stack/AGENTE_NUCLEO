"""V36: limited declarative component monitoring and atomic rollback."""
import argparse,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V35"))
import rewrite as v
m=v.m
SEEDS=(5160017,5190023,5220031,5250041)
POLICIES=("immutable","unconditional","monitored")
UPDATES=(
    ("equivalent",(("add","pairs","zero"),"distance")),
    ("equivalent",("pairs",("add","distance","zero"))),
    ("constant",("zero","zero")),
    ("constant",(("max","zero","zero"),"zero")),
    ("inverted",(("sub","zero","pairs"),"distance")),
    ("inverted",("pairs",("sub","zero","distance"))),
)

def write_atomic(directory,src):
    active=directory/"active.json";pending=directory/"pending.json"
    v.validate(src)
    pending.write_text(v.serialize(src),encoding="utf-8")
    assert v.load(pending)==src
    pending.replace(active)
    assert v.load(active)==src
    return m.digest(src)

def monitor(previous,candidate,monitor_seeds):
    before=v.metrics(v.episodes(previous,monitor_seeds,"monitor_before"))
    after=v.metrics(v.episodes(candidate,monitor_seeds,"monitor_after"))
    reasons=[]
    if after["score"]<before["score"]:reasons.append("score")
    if after["wrong"]>before["wrong"]:reasons.append("wrong")
    if after["false_identity"]>before["false_identity"]:reasons.append("false_identity")
    return before,after,reasons

def monitored_update(directory,candidate,seeds,audit):
    previous=v.load(directory/"active.json")
    previous_hash=m.digest(previous)
    backup=directory/"previous.json"
    backup.write_text(v.serialize(previous),encoding="utf-8")
    assert v.load(backup)==previous
    try:v.validate(candidate)
    except ValueError:
        record=dict(previous=previous,previous_sha=previous_hash,proposed=candidate,
            status="invalid",active=previous,active_sha=previous_hash,reasons=["schema"])
        audit.append(record)
        return previous,record
    installed_hash=write_atomic(directory,candidate)
    installed=v.load(directory/"active.json")
    assert installed==candidate
    before,after,reasons=monitor(previous,installed,seeds)
    if reasons:
        restored=v.load(backup)
        assert restored==previous and m.digest(restored)==previous_hash
        write_atomic(directory,restored)
    active=v.load(directory/"active.json")
    record=dict(previous=previous,previous_sha=previous_hash,proposed=candidate,
        installed_sha=installed_hash,active=active,active_sha=m.digest(active),
        status="reverted" if reasons else "accepted",reasons=reasons,
        monitor_before=before,monitor_after=after,monitor_seeds=list(seeds))
    if reasons:assert active==previous and record["active_sha"]==previous_hash
    else:assert active==candidate and record["active_sha"]==installed_hash
    audit.append(record)
    return active,record

def experiment(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[];events=[];schedules=[]
    for seed in SEEDS:
        directory=out/str(seed);directory.mkdir()
        v.install(directory/"monitored",v.BASE)
        updates=list(UPDATES)
        random.Random(seed^0x3611).shuffle(updates)
        seeds=[seed+1009*i for i in range(1,49)]
        assert len(set(seeds))==48
        schedules.append(dict(replica=seed,updates=updates,seeds=seeds))
        for stage,(kind,src) in enumerate(updates):
            block=seeds[8*stage:8*(stage+1)]
            canary,final=block[:3],block[3:]
            trace=[]
            active,event=monitored_update(directory/"monitored",src,canary,trace)
            assert len(trace)==1
            events.append(dict(replica=seed,stage=stage,kind=kind,**event))
            for policy,source in zip(POLICIES,(v.BASE,src,active)):
                results=v.episodes(source,final,policy)
                rows.extend(dict(replica=seed,stage=stage,kind=kind,**r) for r in results)
            assert v.load(directory/"monitored"/"active.json")==active
    aggregate=[dict(policy=p,**v.metrics([r for r in rows if r["policy"]==p])) for p in POLICIES]
    result=dict(protocol="V36-controlled-regression-monitor-v1",schedules=schedules,events=events,
        aggregate=aggregate,
        by_kind=[dict(policy=p,kind=k,**v.metrics([r for r in rows if r["policy"]==p and r["kind"]==k]))
                 for p in POLICIES for k in ("equivalent","constant","inverted")],
        by_replica=[dict(replica=s,policy=p,**v.metrics([r for r in rows if r["replica"]==s and r["policy"]==p]))
                    for s in SEEDS for p in POLICIES],
        recovery=dict(updates=len(events),reverted=sum(e["status"]=="reverted" for e in events),
            accepted=sum(e["status"]=="accepted" for e in events),
            verified_restorations=sum(e["status"]=="reverted" and e["active_sha"]==e["previous_sha"] for e in events),
            extra_monitor_probes=sum(e["monitor_before"]["probes"]+e["monitor_after"]["probes"] for e in events)))
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    with (out/"raw.jsonl").open("w",encoding="utf-8") as f:
        for r in rows:f.write(m.enc(r)+"\n")
    with (out/"events.jsonl").open("w",encoding="utf-8") as f:
        for e in events:f.write(m.enc(e)+"\n")
    print(json.dumps(result,indent=2))

class Tests(unittest.TestCase):
    def test_sources(self):
        for _,src in UPDATES:self.assertLessEqual(v.validate(src),30)
        self.assertEqual(len({s+1009*i for s in SEEDS for i in range(1,49)}),192)
    def test_restore(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"component";v.install(p,v.BASE)
            candidate=("zero","zero");trace=[]
            with patch(__name__+".monitor",return_value=({}, {}, ["score"])):
                active,record=monitored_update(p,candidate,[1,2,3],trace)
            self.assertEqual(active,v.BASE)
            self.assertEqual(record["status"],"reverted")
            self.assertEqual(record["active_sha"],record["previous_sha"])
            self.assertEqual(v.load(p/"active.json"),v.BASE)
    def test_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"component";v.install(p,v.BASE)
            active,event=monitored_update(p,("unknown","zero"),[],[])
            self.assertEqual(active,v.BASE);self.assertEqual(event["status"],"invalid")
            self.assertEqual(v.load(p/"active.json"),v.BASE)
    def test_real_monitor(self):
        a,b,reasons=monitor(v.BASE,v.BASE,[SEEDS[0]])
        self.assertFalse(reasons);self.assertEqual(a["score"],b["score"])
        self.assertEqual(a["correct"],b["correct"])

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--output",type=Path)
    z=p.parse_args()
    if z.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not z.output or ROOT not in z.output.resolve().parents:p.error("new output inside V36 required")
    experiment(z.output)
