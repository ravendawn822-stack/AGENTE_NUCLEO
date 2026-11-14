import time,random,itertools,tracemalloc
from model import *

DEFAULT=dict(candidates=1200,seconds=.012,limit=8,weights=[.45,.35,.20])
def new_skill(expr,origin,evidence):
    return dict(id=ident(expr),expr=expr,origin=origin,state='validated',scope='training_problem:'+str(origin),
        composition=[ident(c) for c in children(expr)],evidence=evidence,contexts={},selected=0,
        constructed=0,present=0,success=0,failure=0,cost_ops=0,cost_count=0,eval_seconds=0.,ablations=[])
def restore(mem):
    for s in mem:s['expr']=freeze(s['expr'])
    return mem
def solve(query,mem,agent,mode,cfg,seed,emit=None,expanded=False,forced=None):
    started=time.perf_counter(); cpu=time.process_time();tracemalloc.start()
    def event(kind,**kw):
        if emit:emit(dict(kind=kind,t=time.perf_counter()-started,**kw))
    event('episode_start',agent=agent,mode=mode,budget=cfg['candidates'])
    inputs=[(-2,-1),(-1,2),(0,0),(1,-2),(2,1),(3,2)] if expanded else list(range(-2,3))
    event('inputs_selected',inputs=inputs)
    observations=[]
    for x in inputs:
        y=query(x);observations.append((x,y));event('oracle_query',x=x,y=y)
    ys=[y for _,y in observations]; ctx=context(ys[:5]);scores=[]
    selection_start=time.perf_counter()
    if forced is not None:selected=list(forced)
    elif agent=='A':selected=[]
    elif agent=='B':selected=list(mem)
    elif agent=='D':selected=random.Random(seed).sample(mem,min(cfg['limit'],len(mem)))
    elif agent=='ORDER':selected=list(mem[:cfg['limit']])
    else:
        for s in mem:
            item=dict(id=s['id'],**score(s,ys[:5],cfg['weights'],inputs[:5]));scores.append(item);event('skill_score',**item)
        order={s['id']:i for i,s in enumerate(mem)}
        ranked=sorted(scores,key=lambda s:(-s['S'],order[s['id']]))
        byid={s['id']:s for s in mem};selected=[byid[s['id']] for s in ranked[:cfg['limit']]]
    costs={}
    for s in selected:
        tick=time.perf_counter()
        for x,y in observations:value(s['expr'],x)
        costs[s['id']]=dict(seconds=time.perf_counter()-tick,ops=size(s['expr'])*len(observations))
    retrieval=time.perf_counter()-selection_start
    for s in selected:event('skill_selected',id=s['id'],expression=s['expr'],state=s['state'],evidence=s['evidence'])
    event('stage_end',stage='selection',seconds=retrieval)
    best=None; used=(); n=0; tested=0; comparisons=0
    deadline=started+cfg['seconds'] if mode=='time' else float('inf')
    source=program_candidates(selected) if expanded else candidates(selected)
    for e,provenance in itertools.islice(source,cfg['candidates'] if mode=='candidates' else 5000):
        if time.perf_counter()>=deadline:break
        n+=1
        if emit:event('hypothesis_generated',id=ident(e),expression=e,state='hypothesis',consumed=n)
        mismatch=None;tested+=1
        for x,y in observations:
            predicted=value(e,x);comparisons+=1
            if predicted!=y:mismatch=dict(x=x,expected=y,predicted=predicted);break
        if mismatch:
            if emit:event('hypothesis_refuted',id=ident(e),expression=e,state='refuted',evidence=mismatch,scope=ctx)
        else:
            best=e;used=provenance;event('candidate_accepted',id=ident(e),expression=e,state='candidate',scope=ctx);break
    present=[s['id'] for s in selected if best and s['expr'] in set(subtrees(best))]
    for sid in used:event('skill_constructed',id=sid)
    for sid in present:event('skill_present',id=sid)
    elapsed=time.perf_counter()-started;peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    metrics=dict(candidates=n,tested=tested,comparisons=comparisons,seconds=elapsed,cpu_seconds=time.process_time()-cpu,
        selection_seconds=retrieval,peak_bytes=peak,selected=[s['id'] for s in selected],constructed=list(used),present=present,
        observations=observations,context=ctx,scores=scores,skill_costs=costs,depth=depth(best) if best else 0,size=size(best) if best else 0,
        memory=len(mem),remaining=max(0,cfg['candidates']-n) if mode=='candidates' else max(0,cfg['seconds']-elapsed))
    event('search_end',expression=best,**metrics)
    return best,metrics

def learn(mem,best,m,query,origin,cap,emit=None,expanded=False):
    def event(kind,**kw):
        if emit:emit(dict(kind=kind,**kw))
    start=time.perf_counter()
    tests=[(-4,3),(4,-3),(5,2),(-5,-2)] if expanded else [-6,6,-8,8]
    evidence=[]
    if best:
        for x in tests:evidence.append(dict(x=x,expected=query(x),predicted=value(best,x)))
    valid=bool(best) and all(e['expected']==e['predicted'] for e in evidence)
    for s in mem:
        sid=s['id']
        if sid in m['selected']:
            s['selected']+=1
            cost=m['skill_costs'][sid];s['cost_count']+=1
            s['cost_ops']+=(cost['ops']-s['cost_ops'])/s['cost_count']
            s['eval_seconds']+=cost['seconds']
        if sid in m['present']:s['present']+=1
        if sid in m['constructed']:
            s['constructed']+=1;s['success']+=int(valid);s['failure']+=int(not valid)
            stat=s['contexts'].setdefault(m['context'],dict(attempts=0,success=0))
            stat['attempts']+=1;stat['success']+=int(valid)
    if best:
        event('training_validation',id=ident(best),expression=best,state='validated' if valid else 'refuted',evidence=evidence,scope=str(origin))
    if valid and (best[0]<=3 or expanded and best[0]==30) and not any(s['expr']==best for s in mem):
        skill=new_skill(best,origin,evidence);mem.append(skill);event('skill_acquired',**skill)
        if len(mem)>cap:
            removed=mem.pop(0);event('skill_archived',id=removed['id'],reason='FIFO capacity')
    event('memory_growth',count=len(mem),origin=origin)
    event('episode_end',training_valid=valid,seconds=time.perf_counter()-start)
    return valid,evidence
