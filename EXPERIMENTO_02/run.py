import json, random, hashlib, sqlite3, time, collections, statistics, platform
from pathlib import Path
from core import *
ROOT=Path(__file__).resolve().parent
CONFIG=dict(seeds=[104729,130363,155921],checkpoints=[0,10,25,50,75,100],
    hypotheses=2000,seconds=0.012,safety_cap=20000,max_depth=4,initial_training=10)
def signature(e): return tuple(value(e,x) for x in range(-4,5))
def tree(r,d):
    if d==1 or r.random()<0.15: return r.choice(BASE)
    return (r.choice((1,2,3)),tree(r,d-1),tree(r,d-1))
def suite(seed):
    r=random.Random(seed); seen=set(); train=[]; test=[]
    while len(train)<100:
        e=tree(r,r.choice((2,3,4))); sig=signature(e)
        if sig in seen or len(set(sig))==1: continue
        seen.add(sig); train.append(e)
    shared=set(s for e in train for s in subs(e) if depth(s)>=3)
    counts=collections.Counter()
    while len(test)<100:
        if counts['related']<50:
            motif=r.choice(sorted(s for s in shared if depth(s)==3))
            e=(r.choice((1,2,3)),motif,tree(r,2))
        else:
            e=tree(r,2+r.randrange(3))
        sig=signature(e)
        group='related' if any(s in shared for s in subs(e)) else 'unrelated'
        if sig in seen or len(set(sig))==1 or counts[group]>=50: continue
        seen.add(sig); test.append((e,group)); counts[group]+=1
    return train,test
def main():
    out=ROOT/('run_'+time.strftime('%Y%m%d_%H%M%S')); out.mkdir()
    original={str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in ROOT.parent.rglob('*') if p.is_file() and ROOT not in p.parents}
    (out/'original_hashes.json').write_text(json.dumps(original,indent=2))
    (out/'config.json').write_text(json.dumps(dict(CONFIG,python=platform.python_version(),platform=platform.platform()),indent=2))
    db=sqlite3.connect(out/'memory.sqlite3'); db.execute('create table skills(seed,mode,agent,experience,expression)')
    rows=[]
    with (out/'raw.jsonl').open('w',encoding='utf-8') as f:
        def trial(seed,mode,agent,step,phase,index,e,group,skills):
            best,m=solve(lambda x:value(e,x),skills,mode,CONFIG)
            # Avaliacao ocorre APOS solve; respostas e sucesso nao retornam ao agente.
            xs=list(range(7,24))+list(range(-23,-6))
            success=best is not None and all(value(best,x)==value(e,x) for x in xs)
            row=dict(seed=seed,mode=mode,agent=agent,step=step,phase=phase,index=index,
                group=group,success=success,expression=best,target_depth=depth(e),target_size=size(e),**m)
            f.write(json.dumps(row)+'\n'); rows.append(row)
            return best
        for seed in CONFIG['seeds']:
            train,test=suite(seed)
            (out/f'suite_{seed}.json').write_text(json.dumps(dict(training=train,evaluation=test)))
            for mode in ('hypotheses','time'):
                memories={'A':[], 'B':[], 'C':[]}
                for step in range(101):
                    if step:
                        for agent in ('A','B','C'):
                            skills=memories[agent]
                            best=trial(seed,mode,agent,step,'training',step-1,train[step-1],'training',skills)
                            if best and (agent=='B' or agent=='C' and step<=10):
                                for s in subs(best):
                                    if s not in skills:
                                        skills.append(s)
                                        db.execute('insert into skills values(?,?,?,?,?)',(seed,mode,agent,step,json.dumps(s)))
                    if step in CONFIG['checkpoints']:
                        for agent in ('A','B','C'):
                            before=tuple(memories[agent])
                            for i,(e,group) in enumerate(test):
                                trial(seed,mode,agent,step,'evaluation',i,e,group,memories[agent])
                            assert before==tuple(memories[agent])
                        db.commit(); f.flush()
                        print(seed,mode,step, {k:len(v) for k,v in memories.items()},flush=True)
    db.close()
    assert all(hashlib.sha256((ROOT.parent/p).read_bytes()).hexdigest()==h for p,h in original.items())
    report=['# Experimento 02 — aprendizagem cumulativa','',
        'Execução: '+out.name+'. Três sementes; 100 treinos e 100 alvos inéditos por semente; 50 relacionados e 50 sem subárvore operacional idêntica ao treino. A seleção não consulta desempenho dos agentes.',
        'C aprende nas primeiras 10 experiências e congela. No ponto zero todos estão vazios. Cada modalidade tem treinamento próprio. Avaliação não altera memória. Limite expandido 4 para todos; memória contém árvores expandidas.',
        'Contagem inclui candidatos utilizados na seleção de consultas. Tempo inclui busca e tracemalloc, exclui avaliador e gravação; limite cooperativo pode ultrapassar um pouco. Pico mede alocações Python por chamada, não RSS total. Reuso conta subárvores da solução presentes na memória; não prova causalidade.',
        '', '|Orçamento|Experiências|Agente|Sucesso %|Hipóteses médias|ms médios|Pico KiB médio|Habilidades médias|Reusos médios|Profundidade média*|Nós médios*|',
        '|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode in ('hypotheses','time'):
        for step in CONFIG['checkpoints']:
            for agent in ('A','B','C'):
                rs=[r for r in rows if r['phase']=='evaluation' and r['mode']==mode and r['step']==step and r['agent']==agent]
                mean=lambda k:statistics.mean(r[k] for r in rs)
                report.append(f'|{mode}|{step}|{agent}|{100*mean("success"):.1f}|{mean("hypotheses"):.1f}|{1000*mean("seconds"):.2f}|{mean("peak_bytes")/1024:.1f}|{mean("skills"):.1f}|{mean("reuse"):.2f}|{mean("depth"):.2f}|{mean("size"):.2f}|')
    report+=['','*Falhas sem expressão entram como zero. Ver dados brutos para análises condicionais.', '', '|Orçamento|Semente|Agente em 100|Relacionados %|Sem relação %|','|---|---:|---|---:|---:|']
    for mode in ('hypotheses','time'):
        for seed in CONFIG['seeds']:
            for agent in ('A','B','C'):
                rs=[r for r in rows if r['phase']=='evaluation' and r['mode']==mode and r['seed']==seed and r['step']==100 and r['agent']==agent]
                rates=[100*statistics.mean(r['success'] for r in rs if r['group']==g) for g in ('related','unrelated')]
                report.append(f'|{mode}|{seed}|{agent}|{rates[0]:.1f}|{rates[1]:.1f}|')
    report+=['','## Limitações','Amostra pequena de sementes; avaliações periódicas reutilizam os mesmos alvos, com memória congelada durante cada avaliação. Relação estrutural significa igualdade sintática, não independência matemática. Funções são polinômios univariados de grau máximo 8: nove pontos distintos identificam equivalência neste domínio. A checagem usa 34 pontos externos. O treinamento usa até seis consultas, portanto pode armazenar hipóteses incorretas; não recebe correção do avaliador. O custo de memória crescente faz parte do tratamento. Não há prova de inteligência geral, aprendizado de programação ou melhoria monotônica. Execução sequencial e relógio têm ruído; 12 ms é um limite curto. Python padrão, sem dependências ou instruções específicas de CPU; compatibilidade física com Pentium não foi testada aqui.', '', 'Preservação do Experimento 01 confirmada por hashes de todos os arquivos originais. Dados incluem observações, soluções, métricas por tarefa e sementes; SQLite registra origem de cada habilidade.']
    (ROOT/'RELATORIO_02.md').write_text('\n'.join(report),encoding='utf-8')
    print('DONE',out,flush=True)
if __name__=='__main__': main()
