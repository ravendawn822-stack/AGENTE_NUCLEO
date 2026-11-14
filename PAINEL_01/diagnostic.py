"""Execução nova do núcleo original com observação de linhas Python; não altera fontes."""
import sys, importlib.util, json, time, sqlite3
from data import ROOT, PROJECT, freeze, subs, text
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('original_core',PROJECT/'EXPERIMENTO_02'/'core.py')
core=importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

def episode(target,skills,emit,config):
    start=time.perf_counter(); last_n=0; previous=None; stage='start'
    def event(kind,**payload): emit(dict(kind=kind,t=time.perf_counter()-start,**payload))
    def flush_test(best=None):
        nonlocal previous
        if previous is None: return
        h,obs=previous
        mismatch=next(((x,y,core.value(h,x)) for x,y in obs if core.value(h,x)!=y),None)
        event('hypothesis_discarded' if mismatch else 'hypothesis_accepted',expression=h,
              reason='prediction_mismatch' if mismatch else 'consistent_with_training_observations',mismatch=mismatch)
        previous=None
    def trace(frame,ev,arg):
        nonlocal last_n,previous
        if frame.f_code is not core.solve.__code__: return None
        v=frame.f_locals
        if ev=='line':
            n=v.get('n',0)
            if n>last_n:
                event('hypothesis_generated',expression=v['e'],consumed=n,remaining=config['hypotheses']-n)
                last_n=n
            # A linha que executa all(...) é identificada pelo texto, não por número fixo.
            line=lines.get(frame.f_lineno,'')
            if 'if all(value(h,x)==y' in line:
                flush_test(); previous=(v['h'],list(v['observations']))
                event('hypothesis_tested',expression=v['h'])
            if 'observations=[(x,query(x))' in line:
                event('inputs_selected',inputs=v['inputs'])
        elif ev=='return': flush_test()
        return trace
    import inspect
    source,offset=inspect.getsourcelines(core.solve)
    lines={offset+i:l for i,l in enumerate(source)}
    event('episode_start',budget=config['hypotheses'])
    event('skills_consulted',expressions=skills)
    def query(x):
        t=time.perf_counter(); y=core.value(target,x)
        event('oracle_query',x=x,y=y,seconds=time.perf_counter()-t); return y
    old=sys.gettrace()
    try:
        sys.settrace(trace)
        best,metrics=core.solve(query,skills,'hypotheses',config)
    finally: sys.settrace(old)
    event('stage_end',stage='search',seconds=metrics['seconds'],consumed=metrics['hypotheses'])
    for s in subs(best):
        if s in skills: event('skill_reused',expression=s,meaning='syntactic_subtree_in_accepted_expression')
    t=time.perf_counter()
    failures=[]
    if best:
        for x in list(range(7,24))+list(range(-23,-6)):
            actual,predicted=core.value(target,x),core.value(best,x)
            if actual!=predicted: failures.append(dict(x=x,expected=actual,predicted=predicted))
    success=best is not None and not failures
    if not success: event('validation_failed',reason='no_solution' if not best else 'held_out_mismatch',failures=failures)
    event('stage_end',stage='validation',seconds=time.perf_counter()-t,success=success)
    return best,dict(metrics,success=success)

def run(progress=lambda s:None):
    path=ROOT/'sessions'/time.strftime('%Y%m%d_%H%M%S'); path.mkdir(parents=True)
    cfg=dict(hypotheses=2000,seconds=.012,safety_cap=20000)
    source=PROJECT/'EXPERIMENTO_02'/'run_20261114_172735'/'suite_104729.json'
    suite=json.loads(source.read_text()); skills=[]
    db=sqlite3.connect(path/'memory.sqlite3'); db.execute('create table skills(seed,mode,agent,experience,expression)')
    (path/'config.json').write_text(json.dumps(dict(cfg,diagnostic=True,source=str(source),note='traced; times not scientifically comparable')))
    with (path/'raw.jsonl').open('w',encoding='utf-8') as raw, (path/'events.jsonl').open('w',encoding='utf-8') as events:
        for i,target in enumerate(suite['training'][:12]):
            progress('Diagnóstico B · problema '+str(i+1)+'/12')
            episode_start=time.perf_counter()
            def emit(e):
                e.update(episode=i,t=time.perf_counter()-episode_start); events.write(json.dumps(e)+'\n')
            best,m=episode(freeze(target),skills,emit,cfg)
            t=time.perf_counter()
            if best:
                for s in subs(best):
                    if s not in skills:
                        skills.append(s); db.execute('insert into skills values(?,?,?,?,?)',(104729,'hypotheses','B',i+1,json.dumps(s)))
                        emit(dict(kind='skill_discovered',t=m['seconds'],expression=s,origin=i,criterion='training_consistency_only'))
            emit(dict(kind='stage_end',stage='memory',t=m['seconds'],seconds=time.perf_counter()-t))
            emit(dict(kind='episode_end',t=m['seconds'],success=m['success'],consumed=m['hypotheses']))
            raw.write(json.dumps(dict(seed=104729,mode='hypotheses',agent='B',step=i+1,phase='training',index=i,group='diagnostic',expression=best,**m))+'\n')
            db.commit(); raw.flush(); events.flush()
    db.close(); return path
if __name__=='__main__': print(run(print))
