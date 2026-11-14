import sqlite3,json,statistics,time,hashlib
from pathlib import Path
from run import ROOT,CONFIG,original_hashes
from model import *
from engine import restore,solve
from protocol import suite
def verify():
    db=sqlite3.connect(ROOT/'results'/'experiment.sqlite3')
    rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM episodes')]
    main=[r for r in rows if r['section']=='main'];assert len(main)==7200,len(main)
    assert len(rows)==7680,len(rows)
    for seed in CONFIG['seeds']:
        for index in range(24):
            zero=[r for r in main if r['seed']==seed and r['index']==index and r['step']==0 and r['mode']=='candidates']
            assert len({json.dumps([r['expression'],r['success'],r['candidates']]) for r in zero})==1
    for r in rows:
        assert r['memory']<= (r['capacity'] if r['section']=='main' else 64)
        if r['mode']=='candidates':assert r['candidates']<=(6000 if r['section']=='programs' else 800)
        if r['agent'] in ('C','D','ORDER'):assert len(r['selected'])<=4
        if r['expression']:assert depth(r['expression'])<=4
        for s in r['scores']:assert all(0<=s[k]<=1 for k in ('P','R','E','K','S'))
    for seed in CONFIG['seeds']:
        for cap in CONFIG['capacities']:
            for mode in ('candidates','time'):
                for a in CONFIG['agents']:
                    condition=f'{seed}:{cap}:{mode}:{a}'
                    for step in CONFIG['checkpoints']:
                        rs=[r for r in main if (r['seed'],r['capacity'],r['mode'],r['agent'],r['step'],r['phase'])==(seed,cap,mode,a,step,'evaluation')]
                        assert len(rs)==24
                        expected=0 if step==0 else len(json.loads(db.execute('select data from snapshots where id=?',(condition+f':train:{step}',)).fetchone()[0]))
                        assert all(r['memory']==expected for r in rs)
    # Recheca ablações a partir da seleção original, antes de aquisição/evicção.
    audited=[]
    for r in rows:
        if not r['ablation'] or r['section']!='main':continue
        cond=f'{r["seed"]}:{r["capacity"]}:{r["mode"]}:{r["agent"]}'
        mem=restore(json.loads(db.execute('select data from snapshots where id=?',(cond+f':train:{r["step"]-1}',)).fetchone()[0]))
        selected=[s for s in mem if s['id'] in r['selected']];sid=r['ablation']['removed']
        target=suite(r['seed'],24)[0][r['index']];query=lambda x:value(target,x)
        tick=time.perf_counter();expr,m=solve(query,mem,'C','candidates',CONFIG,0,forced=[s for s in selected if s['id']!=sid])
        valid=bool(expr) and all(value(expr,x)==query(x) for x in [-6,6,-8,8])
        result=dict(seed=r['seed'],capacity=r['capacity'],step=r['step'],removed=sid,
            baseline_valid=r['training_valid'],without_valid=valid,baseline_candidates=r['candidates'],without_candidates=m['candidates'],
            seconds=time.perf_counter()-tick,original_record=r['ablation'],changed=valid!=r['ablation']['without_valid'] or m['candidates']!=r['ablation']['without_candidates'])
        audited.append(result)
        db.execute('INSERT OR REPLACE INTO auxiliary VALUES(?,?)',(f'audited_ablation:{cond}:{r["step"]}',json.dumps(result)))
    db.commit()
    refs=[json.loads(r[0]) for r in db.execute("select data from auxiliary where id like 'interpolation:%'")];assert len(refs)==72
    saved=json.loads((ROOT/'results'/'preservation.json').read_text());assert original_hashes()==saved
    report=dict(passed=True,main_episodes=len(main),total_episodes=len(rows),original_files_unchanged=len(saved),
        interpolation_success=sum(r['success'] for r in refs),interpolation_n=len(refs),
        audited_ablations=len(audited),ablation_corrections=sum(r['changed'] for r in audited))
    (ROOT/'results'/'verification.json').write_text(json.dumps(report,indent=2))
    (ROOT/'results'/'audited_ablations.json').write_text(json.dumps(audited,indent=2))
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    (ROOT/'results'/'source_manifest.json').write_text(json.dumps(sources,indent=2))
    db.close();print(report)
if __name__=='__main__':verify()
