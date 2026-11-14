import json,sqlite3,statistics
from run import ROOT,CONFIG
def main():
    db=sqlite3.connect((ROOT/'results'/'experiment.sqlite3').as_uri()+'?mode=ro',uri=True)
    rows=[json.loads(r[0]) for r in db.execute('select data from episodes')]
    refs=[json.loads(r[0]) for r in db.execute("select data from auxiliary where id like 'interpolation:%'")]
    ab=json.loads((ROOT/'results'/'audited_ablations.json').read_text())
    lines=['# Conclusões auditadas — Experimento 03','',
    'Execução principal concluída. As tabelas abaixo são calculadas dos registros reais; não houve seleção de pesos ou problemas por desempenho final. RELATORIO_03.md contém todos os checkpoints e PROTOCOLO.md define as métricas.',
    '', '|Regime|Capacidade|Agente|Acertos finais /72|Tempo total médio ms|Seleção média ms|Candidatos médios|',
    '|---|---:|---|---:|---:|---:|---:|']
    for mode in ['candidates','time']:
        for cap in [8,24]:
            for a in CONFIG['agents']:
                rs=[r for r in rows if r['section']=='main' and r['phase']=='evaluation' and r['step']==24 and r['mode']==mode and r['capacity']==cap and r['agent']==a]
                lines.append(f'|{mode}|{cap}|{a}|{sum(r["success"] for r in rs)}|{1000*statistics.mean(r["total_seconds"] for r in rs):.3f}|{1000*statistics.mean(r["selection_seconds"] for r in rs):.3f}|{statistics.mean(r["candidates"] for r in rs):.1f}|')
    lines+=['','## Variação entre sementes','|Semente|Capacidade|Agente|Sucesso final candidatos %|','|---:|---:|---|---:|']
    for seed in CONFIG['seeds']:
        for cap in [8,24]:
            for a in CONFIG['agents']:
                rs=[r for r in rows if r['section']=='main' and r['seed']==seed and r['phase']=='evaluation' and r['step']==24 and r['mode']=='candidates' and r['capacity']==cap and r['agent']==a]
                lines.append(f'|{seed}|{cap}|{a}|{100*statistics.mean(r["success"] for r in rs):.2f}|')
    lines+=['','## Referência matemática',f'Interpolação racional exata: {sum(r["success"] for r in refs)}/{len(refs)} alvos. Nove consultas, média de {1000*statistics.mean(r["seconds"] for r in refs):.3f} ms incluindo teste externo. Não comparável diretamente ao tempo de busca, que exclui teste externo. A referência usa a hipótese conhecida de polinômio de grau ≤8 e não aprende uma biblioteca de árvores.',
    '', '## Ablações rechecadas',f'{len(ab)} ablações; {sum(r["changed"] for r in ab)} diferiram do registro preliminar. Evidência local de necessidade: {sum(r["baseline_valid"] and not r["without_valid"] for r in ab)}. Solução válida com e sem: {sum(r["baseline_valid"] and r["without_valid"] for r in ab)}. Registros finais em results/audited_ablations.json. Os números auditados substituem a contagem preliminar de ablação em RELATORIO_03.md.',
    'A rechecagem usa a seleção antes da atualização FIFO. O registro preliminar de parte da execução usava a memória após atualização, podendo retirar mais de uma habilidade. Ablações preliminares fora da seção principal também são excluídas: a rotina de ablação aritmética não era apropriada para a expansão. Esses erros não afetam as soluções principais, as pontuações ou os acertos, porque ablações são executadas após busca/treino e não entram no cálculo de seleção. Custos extras permanecem registrados. Dados preliminares são mantidos para auditoria.',
    '', '## Aprendizagem das estatísticas']
    snapshots=[json.loads(r[0]) for r in db.execute('select data from snapshots')]
    max_attempts=max((v['attempts'] for mem in snapshots for s in mem for v in s['contexts'].values()),default=0)
    lines.append(f'Maior número de tentativas de construção em um contexto: {max_attempts}. A fórmula atualiza P e E quando há uso real em construção; mera seleção não ganha crédito. A pontuação não estima efeito causal. A evidência por contexto é escassa: o experimento não isola o benefício de aprender P/E do benefício das regras fixas R/K. Não foi demonstrado aprendizado robusto de quando usar conhecimento.')
    lines+=['','## Expansão em direção à programação','|Memória aritmética anterior|Acertos /90|Tempo médio ms|Candidatas contendo if /90|Acertos contendo if /90|','|---|---:|---:|---:|---:|']
    for prior in [False,True]:
        rs=[r for r in rows if r['section']=='programs' and r['phase']=='evaluation' and r['prior']==prior]
        has_if=lambda r:bool(r['expression']) and any(e[0]==30 for e in __import__('model').subtrees(r['expression']))
        lines.append(f'|{prior}|{sum(r["success"] for r in rs)}|{1000*statistics.mean(r["seconds"] for r in rs):.3f}|{sum(has_if(r) for r in rs)}|{sum(r["success"] and has_if(r) for r in rs)}|')
    lines+=['','A expansão é uma busca de pequenas funções, não desenvolvimento de software geral. Uma solução pode dispensar if por equivalência do alvo no conjunto testado. Validação em grade finita não é prova universal; veja dados brutos para casos refutados e falhas. A diferença de apenas dois acertos (16 contra 14) não sustenta uma alegação forte de transferência para programação.',
    '', '## Orçamentos e limites',f'Máximo de tempo de busca no regime temporal: {1000*max(r["seconds"] for r in rows if r["mode"]=="time"):.3f} ms. O prazo é cooperativo, inclui seleção e pode ser ultrapassado. A execução foi sequencial; tempos curtos têm ruído e não permitem precisão excessiva.',
    'Não há evidência de que a fórmula proposta seja ótima ou que adquirir mais habilidades sempre ajude. Comparações com D e ORDER são necessárias para atribuir benefício à seleção adaptativa em vez de apenas limitar a memória. Ganhos devem ser avaliados por orçamento, capacidade e semente.',
    'O piloto de recursos foi excluído da grade principal e preservado integralmente. Foram verificadas contagens, limites, tamanho da memória nas avaliações e hashes dos arquivos anteriores. A retomada foi exercitada; não se testou queda abrupta de energia.']
    db.close()
    p=ROOT.parent/'PAINEL_02'/'VERIFICACAO.json'
    if p.exists():
        v=json.loads(p.read_text());lines+=['','## Sobrecarga do painel',f'Mediana logging/sem logging em {v["equivalence_pairs"]} pares: {v["overhead_median_ratio"]:.2f}×. Expressões e contagens equivalentes nos pares. Tempo médio de processamento/desenho Tkinter por lote de teste: {1000*v["render_mean_seconds"]:.2f} ms. São medições separadas: não representam soma exata do custo de um uso humano com pausas. Instrumentação visual não é habilitada nas avaliações científicas.']
    lines+=['','## Interpretação central','Com capacidade 24 e orçamento de candidatos, C acertou 41/72, contra 34/72 de D, 37/72 de ORDER e 51/72 de B. Com prazo de 12 ms, C acertou 15/72, contra 18/72 de D, 23/72 de ORDER e 20/72 de B. O custo de seleção de C consumiu parte substancial do prazo. A fórmula proposta não foi superior em todas as condições, e sua vantagem em candidatos não demonstra redução geral do custo computacional.']
    (ROOT/'CONCLUSOES.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join(lines[:25]))
if __name__=='__main__':main()
