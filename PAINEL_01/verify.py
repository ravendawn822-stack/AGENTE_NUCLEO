import json,time
from data import *
from diagnostic import episode,core,run
before=hashes()
suite=json.loads((PROJECT/'EXPERIMENTO_02'/'run_20261114_172735'/'suite_104729.json').read_text())
skills=[]; cfg=dict(hypotheses=2000,seconds=.012,safety_cap=20000)
for target in suite['training'][:12]:
    target=freeze(target); events=[]
    a,m=core.solve(lambda x:core.value(target,x),skills,'hypotheses',cfg)
    b,n=episode(target,skills,events.append,cfg)
    assert a==b and m['hypotheses']==n['hypotheses'] and m['observations']==n['observations']
    assert sum(e['kind']=='hypothesis_generated' for e in events)==m['hypotheses']
    for e in events:
        if e['kind']=='hypothesis_discarded': assert e['mismatch'][1]!=e['mismatch'][2]
    if a:
        for s in subs(a):
            if s not in skills:skills.append(s)
path=run(print)
rows,stored=load(path); assert len(rows)==12
events=[json.loads(s) for s in (path/'events.jsonl').read_text().splitlines()]
for i in range(12):
    es=[e for e in events if e['episode']==i]
    assert es[0]['kind']=='episode_start' and es[-1]['kind']=='episode_end'
    assert all(a['t']<=b['t'] for a,b in zip(es,es[1:]))
# Fixture exclusivamente de teste: coincide com x em todas as consultas,
# diverge fora delas. Não entra nos dados científicos ou na sessão demonstrativa.
_,probe=core.solve(lambda x:x,[],'hypotheses',cfg)
product=(10,1)
for x,y in probe['observations']: product=(3,product,(2,(11,0),(10,x)))
fixture=(1,(11,0),product); failures=[]
_,result=episode(fixture,[],failures.append,cfg)
assert not result['success']
assert any(e['kind']=='validation_failed' and e['reason']=='held_out_mismatch' for e in failures)
import tkinter as tk
from panel import Panel
root=tk.Tk(); root.withdraw(); app=Panel(root); root.update()
assert len(app.filtered)==12
app.step(1); root.update(); app.select_skill()
app.source.current(0); app.load(); root.update()
assert len(app.rows)==12600
app.filters['agent'].set('C'); app.refresh(); root.update()
assert all(r['agent']=='C' for _,r in app.filtered)
root.destroy()
after=hashes(); assert before==after,'Original artifacts changed'
result=dict(passed=True,original_files_unchanged=len(before),equivalent_episodes=12,
    diagnostic_episodes=len(rows),events=len(events),skills=len(stored),tk_smoke='passed')
(ROOT/'VERIFICACAO.json').write_text(json.dumps(result,indent=2))
print(result)
