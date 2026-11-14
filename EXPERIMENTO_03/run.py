import json,sqlite3,hashlib,time,sys,statistics,platform
from pathlib import Path
from model import *
from engine import *
from protocol import suite,check,interpolation,programs
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parent
CONFIG=dict(seeds=[104729,130363,155921],capacities=[8,24],checkpoints=[0,8,16,24],
    train=24,test=24,agents=['A','B','C','D','ORDER'],candidates=800,seconds=.012,limit=4,
    weights=[.45,.35,.20],dev_seed=99001,sensitivity=[[.6,.2,.2],[.2,.6,.2],[.45,.35,.2]],
    expansion_train=30,expansion_test=30,expansion_budget=6000)
def original_hashes():
    return {str(p.relative_to(PROJECT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in PROJECT.rglob('*')
            if p.is_file() and not any(part in ('EXPERIMENTO_03','PAINEL_02') for part in p.relative_to(PROJECT).parts)}
def connect():
    out=ROOT/'results';out.mkdir(exist_ok=True)
    db=sqlite3.connect(out/'experiment.sqlite3')
    db.executescript('''CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,data TEXT);
    CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,data TEXT);
    CREATE TABLE IF NOT EXISTS skills(condition TEXT,id TEXT,data TEXT,PRIMARY KEY(condition,id));
    CREATE TABLE IF NOT EXISTS auxiliary(id TEXT PRIMARY KEY,data TEXT);''');return db
def put(db,table,key,obj): db.execute('INSERT OR REPLACE INTO '+table+' VALUES(?,?)',(key,json.dumps(obj)));db.commit()
def get(db,table,key):
    r=db.execute('SELECT data FROM '+table+' WHERE id=?',(key,)).fetchone();return json.loads(r[0]) if r else None
def save_mem(db,key,mem):
    for s in mem:db.execute('INSERT OR REPLACE INTO skills VALUES(?,?,?)',(key,s['id'],json.dumps(s)))
    db.commit()
def trial(db,key,target,mem,agent,mode,cfg,seed,meta,training=False,cap=64,expanded=False):
    previous=get(db,'episodes',key)
    if previous is not None:
        if training:mem[:]=restore(get(db,'snapshots',key))
        return previous
    start=time.perf_counter();query=lambda x:value(target,x)
    before=json.dumps(mem,sort_keys=True)
    best,m=solve(query,mem,agent,mode,cfg,seed,expanded=expanded)
    selected_before=[s for s in mem if s['id'] in m['selected']]
    learning_valid=None; evidence=[];ablation=None
    if training:
        # A recebe os mesmos testes adicionais mas não retém habilidades.
        learning_valid,evidence=learn(mem,best,m,query,meta['step'],cap,expanded=expanded)
        if agent=='A':mem.clear()
        if agent=='C' and mode=='candidates' and meta['section']=='main' and meta['step']%8==0 and m['constructed']:
            sid=m['constructed'][0];selected=[s for s in selected_before if s['id']!=sid]
            t=time.perf_counter();other,om=solve(query,mem,agent,mode,cfg,seed,forced=selected)
            valid=bool(other) and all(value(other,x)==query(x) for x in [-6,6,-8,8])
            ablation=dict(removed=sid,baseline_valid=learning_valid,without_valid=valid,
                baseline_candidates=m['candidates'],without_candidates=om['candidates'],seconds=time.perf_counter()-t,
                meaning='conditional_on_selected_set_and_budget')
            for s in mem:
                if s['id']==sid:s['ablations'].append(ablation)
    else:assert json.dumps(mem,sort_keys=True)==before
    total=time.perf_counter()-start
    # Avaliador externo à busca: seu resultado NÃO é fornecido a learn.
    t=time.perf_counter();success=check(best,target,expanded);evaluator_seconds=time.perf_counter()-t
    row=dict(meta,agent=agent,mode=mode,expression=best,success=success,training_valid=learning_valid,
        training_evidence=evidence,ablation=ablation,total_seconds=total,evaluator_seconds=evaluator_seconds,**m)
    # Episódio e snapshot são atômicos para retomada.
    db.execute('INSERT INTO episodes VALUES(?,?)',(key,json.dumps(row)))
    if training:db.execute('INSERT INTO snapshots VALUES(?,?)',(key,json.dumps(mem)))
    db.commit();return row
def main():
    root=ROOT/'results';root.mkdir(exist_ok=True)
    manifest=root/'preservation.json'
    if not manifest.exists():manifest.write_text(json.dumps(original_hashes(),indent=2))
    assert original_hashes()==json.loads(manifest.read_text()),'Prior artifacts changed'
    config=root/'config.json'
    if config.exists():assert json.loads(config.read_text())==CONFIG,'Configuration changed: use a new run directory'
    else:config.write_text(json.dumps(CONFIG,indent=2))
    (root/'environment.json').write_text(json.dumps(dict(python=sys.version,platform=platform.platform())))
    db=connect()
    for seed in CONFIG['seeds']:
        train,test=suite(seed,CONFIG['train'])
        (root/f'suite_{seed}.json').write_text(json.dumps(dict(training=train,evaluation=test)))
        for cap in CONFIG['capacities']:
            for mode in ('candidates','time'):
                for agent in CONFIG['agents']:
                    condition=f'{seed}:{cap}:{mode}:{agent}';mem=[]
                    for step in range(CONFIG['train']+1):
                        if step:
                            meta=dict(seed=seed,capacity=cap,step=step,phase='training',index=step-1,section='main')
                            trial(db,condition+f':train:{step}',train[step-1],mem,agent,mode,CONFIG,seed+step,meta,True,cap)
                        if step in CONFIG['checkpoints']:
                            frozen=json.dumps(mem,sort_keys=True)
                            for i,target in enumerate(test):
                                meta=dict(seed=seed,capacity=cap,step=step,phase='evaluation',index=i,section='main')
                                trial(db,condition+f':eval:{step}:{i}',target,mem,agent,mode,CONFIG,seed+10000+i,meta)
                            assert frozen==json.dumps(mem,sort_keys=True)
                            save_mem(db,condition,mem)
                            print(condition,'checkpoint',step,'memory',len(mem),flush=True)
    # Sensibilidade somente em conjunto de desenvolvimento, pesos não escolhidos pelo final.
    train,dev=suite(CONFIG['dev_seed'],20)
    for wi,weights in enumerate(CONFIG['sensitivity']):
        mem=[];cfg=dict(CONFIG,weights=weights)
        for i,target in enumerate(train+dev):
            training=i<20;meta=dict(seed=CONFIG['dev_seed'],capacity=64,step=min(i+1,20),phase='training' if training else 'evaluation',index=i,section='sensitivity',weights=weights)
            trial(db,f'dev:{wi}:{i}',target,mem,'C','candidates',cfg,CONFIG['dev_seed']+i,meta,training)
    # Referência matemática independente, nove consultas e aritmética racional exata.
    for seed in CONFIG['seeds']:
        _,test=suite(seed,CONFIG['train'])
        for i,target in enumerate(test):
            key=f'interpolation:{seed}:{i}'
            if get(db,'auxiliary',key) is None:
                t=time.perf_counter();ok=interpolation(target)
                put(db,'auxiliary',key,dict(kind='interpolation',seed=seed,index=i,success=ok,queries=9,seconds=time.perf_counter()-t))
    # Expansão separada, iniciada somente após a avaliação aritmética.
    for seed in CONFIG['seeds']:
        train,test=programs(seed)
        (root/f'program_suite_{seed}.json').write_text(json.dumps(dict(training=train,evaluation=test)))
        for prior in (False,True):
            if prior:
                key=f'{seed}:24:candidates:C:train:24';mem=restore(get(db,'snapshots',key))
            else:mem=[]
            label='prior' if prior else 'empty';cfg=dict(CONFIG,candidates=CONFIG['expansion_budget'])
            for i,target in enumerate(train+test):
                training=i<30;meta=dict(seed=seed,capacity=64,step=min(i+1,30),phase='training' if training else 'evaluation',index=i,section='programs',prior=prior)
                trial(db,f'program:{seed}:{label}:{i}',target,mem,'C','candidates',cfg,seed+i,meta,training,64,True)
    assert original_hashes()==json.loads(manifest.read_text())
    rows=[json.loads(r[0]) for r in db.execute('select data from episodes order by id')]
    with (root/'raw.jsonl').open('w',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r)+'\n')
    db.close();report(rows);print('COMPLETE',len(rows),flush=True)
def report(rows):
    lines=['# Experimento 03 — resultados reais','',
    'Ver PROTOCOLO.md para definições, isolamento, orçamentos e limites. SQLite é a fonte transacional; raw.jsonl é sua exportação. C é adaptativo, D aleatório, ORDER ordem de aquisição. B usa toda a memória ativa. Capacidade FIFO é idêntica entre agentes com memória.',
    '', '|Regime|Capacidade|Checkpoint|Agente|n|Sucesso %|Candidatos|Busca ms|Seleção ms|Pico KiB|Memória|Construção|Presença|',
    '|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode in ('candidates','time'):
        for cap in CONFIG['capacities']:
            for step in CONFIG['checkpoints']:
                for a in CONFIG['agents']:
                    rs=[r for r in rows if r['section']=='main' and r['phase']=='evaluation' and r['mode']==mode and r['capacity']==cap and r['step']==step and r['agent']==a]
                    mean=lambda k:statistics.mean(r[k] for r in rs)
                    lines.append(f'|{mode}|{cap}|{step}|{a}|{len(rs)}|{100*mean("success"):.2f}|{mean("candidates"):.1f}|{1000*mean("seconds"):.3f}|{1000*mean("selection_seconds"):.3f}|{mean("peak_bytes")/1024:.1f}|{mean("memory"):.1f}|{statistics.mean(len(r["constructed"]) for r in rs):.2f}|{statistics.mean(len(r["present"]) for r in rs):.2f}|')
    lines+=['','## Sensibilidade no desenvolvimento','|Pesos|Sucesso %|Busca ms|','|---|---:|---:|']
    for weights in CONFIG['sensitivity']:
        rs=[r for r in rows if r['section']=='sensitivity' and r['phase']=='evaluation' and r['weights']==weights]
        lines.append(f'|{weights}|{100*statistics.mean(r["success"] for r in rs):.2f}|{1000*statistics.mean(r["seconds"] for r in rs):.2f}|')
    lines+=['','## Expansão condicional','|Conhecimento anterior|n|Sucesso %|Candidatos|','|---|---:|---:|---:|']
    for prior in (False,True):
        rs=[r for r in rows if r['section']=='programs' and r['phase']=='evaluation' and r['prior']==prior]
        lines.append(f'|{prior}|{len(rs)}|{100*statistics.mean(r["success"] for r in rs):.2f}|{statistics.mean(r["candidates"] for r in rs):.1f}|')
    ab=[r['ablation'] for r in rows if r['ablation'] and r['section']=='main']
    lines+=['',f'Ablações de treinamento realizadas: {len(ab)}. Evidência de necessidade sob orçamento (válida com, inválida sem): {sum(a["baseline_valid"] and not a["without_valid"] for a in ab)}. Casos com solução válida em ambas: {sum(a["baseline_valid"] and a["without_valid"] for a in ab)}.',
    'Ablação remove uma habilidade da seleção, sem retreinar o histórico. Não demonstra causalidade universal e seu custo é suplementar, separado do orçamento principal.',
    '', 'Resultados negativos são mantidos. Três sementes e uma gramática pequena limitam a generalização. O mecanismo matemático e os pesos são hipóteses de projeto; ganhos ou perdas devem ser lidos por condição. Não se demonstrou programação geral, autonomia aberta ou aprendizagem com professora.']
    (ROOT/'RELATORIO_03.md').write_text('\n'.join(lines),encoding='utf-8')
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Interrompido. Execute novamente para retomar os episódios confirmados.',flush=True)
