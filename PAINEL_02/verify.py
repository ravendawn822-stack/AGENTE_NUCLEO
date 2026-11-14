import time,threading,queue,json,sqlite3,tkinter as tk,statistics
from backend import *
from panel import Panel
from run import original_hashes
before=original_hashes()
# Controle de pausa/passo/cancelamento, sem depender do relógio para autorização.
c=Control();c.change('pause');done=threading.Event()
t=threading.Thread(target=lambda:(c.gate(),done.set()));t.start()
assert not done.wait(.05);c.change('step');assert done.wait(1);t.join()
c.change('stop')
try:c.gate();raise AssertionError('Cancellation ignored')
except Cancelled:pass
# Sessão real curta; os testes não criam métricas fictícias no banco.
q=queue.Queue();control=Control();diagnose(control,q,'C',episodes=4)
messages=[]
while not q.empty():messages.append(q.get())
assert not any(k=='error' for k,_ in messages),messages
path=Path(next(v for k,v in messages if k=='done'));events=[];last=0
while True:
    batch=read_events(path,last,2000)
    if not batch:break
    events+=batch;last=batch[-1]['seq']
assert sum(e['kind']=='episode_start' for e in events)==4
assert sum(e['kind']=='episode_end' for e in events)==4
db=sqlite3.connect((path/'diagnostic.sqlite3').as_uri()+'?mode=ro',uri=True)
ids={r[0] for r in db.execute('select id from entities')};db.close()
assert all(e['id'] in ids for e in events if e.get('expression'))
root=tk.Tk();root.withdraw();p=Panel(root);p.path=path
durations=[]
for start in range(0,len(events),500):
    tick=time.perf_counter()
    for e in events[start:start+500]:p.process(e)
    p.draw();root.update_idletasks();durations.append(time.perf_counter()-tick)
assert p.nodes and p.history
p.inspect(next(iter(p.nodes)));p.list_sessions();p.sessions.current(len(p.session_paths)-1);p.load_replay();p.move(1)
p.compare();root.update_idletasks();root.destroy()
measurements=overhead()
assert before==original_hashes()
result=dict(passed=True,events=len(events),entities=len(ids),control_tests='passed',tk_smoke='passed',
    render_mean_seconds=statistics.mean(durations),render_max_seconds=max(durations),
    overhead_median_ratio=statistics.median(r['ratio'] for r in measurements),
    equivalence_pairs=len(measurements),original_files=len(before))
(ROOT/'VERIFICACAO.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
