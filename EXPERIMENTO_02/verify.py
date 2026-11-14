import json, sqlite3, hashlib
from pathlib import Path
from core import depth, size
ROOT=Path(__file__).resolve().parent
def freeze(e): return tuple(freeze(x) if isinstance(x,list) else x for x in e)
def verify(path):
    rows=[json.loads(s) for s in (path/'raw.jsonl').read_text().splitlines()]
    assert len(rows)==12600, len(rows)
    for r in rows:
        if r['mode']=='hypotheses': assert r['hypotheses']<=2000
        if r['expression']:
            e=freeze(r['expression']); assert depth(e)<=4 and size(e)<=15
    for seed in (104729,130363,155921):
        for mode in ('hypotheses','time'):
            evaluation=[r for r in rows if r['seed']==seed and r['mode']==mode and r['phase']=='evaluation']
            for agent in ('A','B','C'):
                for step in (0,10,25,50,75,100):
                    subset=[r for r in evaluation if r['agent']==agent and r['step']==step]
                    assert len(subset)==100
                    assert len({r['skills'] for r in subset})==1
            frozen={r['skills'] for r in evaluation if r['agent']=='C' and r['step']>=10}
            assert len(frozen)==1
    db=sqlite3.connect('file:'+str(path/'memory.sqlite3')+'?mode=ro',uri=True)
    assert db.execute("select count(*) from skills where agent='A' or (agent='C' and experience>10)").fetchone()[0]==0
    skills=db.execute('select count(*) from skills').fetchone()[0]; db.close()
    hashes=json.loads((path/'original_hashes.json').read_text())
    assert all(hashlib.sha256((ROOT.parent/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    result={'rows':len(rows),'persisted_skills':skills,'original_files_unchanged':len(hashes),'checks':'passed'}
    (path/'verification.json').write_text(json.dumps(result,indent=2)); print(result)
if __name__=='__main__':
    import sys
    verify(Path(sys.argv[1]))
