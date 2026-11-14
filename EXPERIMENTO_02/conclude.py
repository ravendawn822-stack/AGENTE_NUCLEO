import json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
path=sorted(ROOT.glob('run_*/raw.jsonl'))[-1]
rows=[json.loads(s) for s in path.read_text().splitlines()]
lines=['','## Interpretação dos resultados','']
for mode in ('hypotheses','time'):
    lines.append('Modalidade '+mode+':')
    for agent in 'ABC':
        rates=[]
        for step in (0,10,25,50,75,100):
            subset=[r for r in rows if r['mode']==mode and r['phase']=='evaluation' and r['agent']==agent and r['step']==step]
            rates.append(round(100*statistics.mean(r['success'] for r in subset),2))
        lines.append('- '+agent+': '+str(rates)+'% nos seis checkpoints.')
    lines.append('')
over=[r['seconds'] for r in rows if r['mode']=='time']
lines+=['Máximo observado de duração no regime temporal: '+str(round(max(over)*1000,3))+' ms. O limite de 12 ms é verificado entre candidatos e pode exceder por um lote, consulta ou preparação. O comparador temporal é aproximado, não um corte rígido.',
    'A sequência completa permite testar melhoria progressiva: quedas locais devem ser preservadas. Reuso e maior taxa de sucesso são evidência de transferência dentro desta gramática; não estabelecem inteligência geral nem generalização para programação.',
    'O estrato relacionado incorpora motivos aleatórios do treino (profundidade 3); o estrato sem relação exclui subárvores compartilhadas de profundidade >=3. Isso cria oportunidades deliberadas de transferência, independentes do sucesso dos agentes. Não significa ausência de operações ou regularidades matemáticas compartilhadas.',
    'A procura de candidatos e a regra de armazenamento são programadas. As expressões específicas são adquiridas das observações. A memória pode guardar hipóteses incorretas: nenhuma resposta reservada é usada para corrigi-las. O congelamento de C e as falhas mostram efeitos além de simplesmente acrescentar regras úteis.',
    'Os 100 alvos são semanticamente distintos do treino em cada semente, mas reaparecem nos checkpoints. As taxas entre checkpoints são pareadas, não 600 problemas independentes. Três sementes não sustentam estimativas populacionais precisas.',
    'Verificação automática em verification.json: 12.600 episódios, limites de hipóteses e profundidade, congelamento de C, memória constante durante avaliação e hashes do Experimento 01. A reabertura SQLite em outro processo verifica persistência dos registros; não testa recuperação após falha abrupta.',
    'As tentativas interrompidas do gerador permanecem nas pastas anteriores; somente a execução indicada no início deste relatório compõe as tabelas. A contagem de hipóteses inclui candidatos considerados em lotes, mesmo quando uma solução aparece antes do fim do lote. Não é contagem de operações aritméticas. Consultas estão em experiments; observações completas estão em raw.jsonl.']
with (ROOT/'RELATORIO_02.md').open('a',encoding='utf-8') as f: f.write('\n'.join(lines))
print('\n'.join(lines[:12]))
