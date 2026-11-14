# Experimento 02 — aprendizagem cumulativa

Auditoria inicial detalhada: [AUDITORIA_01.md](AUDITORIA_01.md). O resultado anterior tinha erro de contagem (2.001 registrados, 2.000 testados), avaliador dentro do agente, aquisição durante avaliação e desafio N01 explicitamente composto a partir de T01. A profundidade expandida de N01 era 4, dentro do limite de A. Essas falhas impedem tratar a comparação anterior como evidência controlada de generalização.

Execução: run_20261114_172735. Três sementes; 100 treinos e 100 alvos inéditos por semente; 50 relacionados e 50 sem subárvore operacional idêntica ao treino. A seleção não consulta desempenho dos agentes.
C aprende nas primeiras 10 experiências e congela. No ponto zero todos estão vazios. Cada modalidade tem treinamento próprio. Avaliação não altera memória. Limite expandido 4 para todos; memória contém árvores expandidas.
Contagem inclui candidatos utilizados na seleção de consultas. Tempo inclui busca e tracemalloc, exclui avaliador e gravação; limite cooperativo pode ultrapassar um pouco. Pico mede alocações Python por chamada, não RSS total. Reuso conta subárvores da solução presentes na memória; não prova causalidade.

|Orçamento|Experiências|Agente|Sucesso %|Hipóteses médias|ms médios|Pico KiB médio|Habilidades médias|Reusos médios|Profundidade média*|Nós médios*|
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
|hypotheses|0|A|11.3|1915.2|62.52|166.6|0.0|0.00|0.34|0.57|
|hypotheses|0|B|11.3|1915.2|60.17|166.3|0.0|0.00|0.34|0.57|
|hypotheses|0|C|11.3|1915.2|61.03|166.3|0.0|0.00|0.34|0.57|
|hypotheses|10|A|11.3|1915.2|60.37|166.3|0.0|0.00|0.34|0.57|
|hypotheses|10|B|31.3|1544.7|53.96|131.0|7.7|0.55|1.18|2.31|
|hypotheses|10|C|31.3|1544.7|54.18|131.0|7.7|0.55|1.18|2.31|
|hypotheses|25|A|11.3|1915.2|64.31|166.3|0.0|0.00|0.34|0.57|
|hypotheses|25|B|48.3|1319.3|50.38|112.5|18.3|1.07|1.84|3.79|
|hypotheses|25|C|31.3|1544.7|55.11|131.0|7.7|0.55|1.18|2.31|
|hypotheses|50|A|11.3|1915.2|62.56|166.3|0.0|0.00|0.34|0.57|
|hypotheses|50|B|62.0|1142.7|47.00|98.0|40.0|1.68|2.41|5.21|
|hypotheses|50|C|31.3|1544.7|55.47|131.0|7.7|0.55|1.18|2.31|
|hypotheses|75|A|11.3|1915.2|61.53|166.3|0.0|0.00|0.34|0.57|
|hypotheses|75|B|65.0|1113.3|45.99|96.7|58.7|1.72|2.52|5.39|
|hypotheses|75|C|31.3|1544.7|57.56|131.0|7.7|0.55|1.18|2.31|
|hypotheses|100|A|11.3|1915.2|66.46|166.3|0.0|0.00|0.34|0.57|
|hypotheses|100|B|66.7|1077.7|46.99|91.4|78.0|1.73|2.60|5.46|
|hypotheses|100|C|31.3|1544.7|55.16|131.0|7.7|0.55|1.18|2.31|
|time|0|A|1.0|366.3|12.43|43.5|0.0|0.00|0.03|0.05|
|time|0|B|1.3|368.6|12.43|43.6|0.0|0.00|0.04|0.07|
|time|0|C|1.3|369.7|12.41|44.2|0.0|0.00|0.04|0.07|
|time|10|A|1.0|374.2|12.42|44.2|0.0|0.00|0.03|0.05|
|time|10|B|10.7|329.6|12.09|40.7|6.3|0.20|0.37|0.73|
|time|10|C|11.0|331.7|12.09|41.2|6.3|0.21|0.38|0.75|
|time|25|A|1.3|365.5|12.46|42.5|0.0|0.00|0.04|0.07|
|time|25|B|16.0|315.3|11.93|37.6|14.0|0.27|0.57|1.03|
|time|25|C|10.0|326.9|12.15|39.6|6.3|0.19|0.35|0.67|
|time|50|A|1.3|375.1|12.42|43.8|0.0|0.00|0.04|0.07|
|time|50|B|15.7|291.7|11.68|36.7|28.3|0.28|0.60|1.04|
|time|50|C|11.0|330.9|12.06|40.8|6.3|0.21|0.38|0.75|
|time|75|A|1.3|373.8|12.45|43.3|0.0|0.00|0.04|0.07|
|time|75|B|15.7|286.3|11.66|34.8|38.7|0.29|0.60|1.04|
|time|75|C|11.0|333.6|12.05|41.2|6.3|0.21|0.38|0.75|
|time|100|A|1.3|359.1|12.45|41.0|0.0|0.00|0.04|0.07|
|time|100|B|16.3|282.4|11.62|32.3|47.7|0.31|0.64|1.11|
|time|100|C|11.0|331.4|12.05|40.7|6.3|0.21|0.38|0.75|

*Falhas sem expressão entram como zero. Ver dados brutos para análises condicionais.

|Orçamento|Semente|Agente em 100|Relacionados %|Sem relação %|
|---|---:|---|---:|---:|
|hypotheses|104729|A|16.0|8.0|
|hypotheses|104729|B|70.0|60.0|
|hypotheses|104729|C|50.0|26.0|
|hypotheses|130363|A|10.0|10.0|
|hypotheses|130363|B|70.0|66.0|
|hypotheses|130363|C|38.0|28.0|
|hypotheses|155921|A|14.0|10.0|
|hypotheses|155921|B|66.0|68.0|
|hypotheses|155921|C|32.0|14.0|
|time|104729|A|2.0|0.0|
|time|104729|B|22.0|14.0|
|time|104729|C|24.0|10.0|
|time|130363|A|2.0|0.0|
|time|130363|B|10.0|8.0|
|time|130363|C|8.0|6.0|
|time|155921|A|2.0|2.0|
|time|155921|B|24.0|20.0|
|time|155921|C|12.0|6.0|

## Limitações
Amostra pequena de sementes; avaliações periódicas reutilizam os mesmos alvos, com memória congelada durante cada avaliação. Relação estrutural significa igualdade sintática, não independência matemática. Funções são polinômios univariados de grau máximo 8: nove pontos distintos identificam equivalência neste domínio. A checagem usa 34 pontos externos. O treinamento usa até seis consultas, portanto pode armazenar hipóteses incorretas; não recebe correção do avaliador. O custo de memória crescente faz parte do tratamento. Não há prova de inteligência geral, aprendizado de programação ou melhoria monotônica. Execução sequencial e relógio têm ruído; 12 ms é um limite curto. Python padrão, sem dependências ou instruções específicas de CPU; compatibilidade física com Pentium não foi testada aqui.

Preservação do Experimento 01 confirmada por hashes de todos os arquivos originais. Dados incluem observações, soluções, métricas por tarefa e sementes; SQLite registra origem de cada habilidade.
## Interpretação dos resultados

Modalidade hypotheses:
- A: [11.33, 11.33, 11.33, 11.33, 11.33, 11.33]% nos seis checkpoints.
- B: [11.33, 31.33, 48.33, 62.0, 65.0, 66.67]% nos seis checkpoints.
- C: [11.33, 31.33, 31.33, 31.33, 31.33, 31.33]% nos seis checkpoints.

Modalidade time:
- A: [1.0, 1.0, 1.33, 1.33, 1.33, 1.33]% nos seis checkpoints.
- B: [1.33, 10.67, 16.0, 15.67, 15.67, 16.33]% nos seis checkpoints.
- C: [1.33, 11.0, 10.0, 11.0, 11.0, 11.0]% nos seis checkpoints.

Máximo observado de duração no regime temporal: 15.449 ms. O limite de 12 ms é verificado entre candidatos e pode exceder por um lote, consulta ou preparação. O comparador temporal é aproximado, não um corte rígido.
A sequência completa permite testar melhoria progressiva: quedas locais devem ser preservadas. Reuso e maior taxa de sucesso são evidência de transferência dentro desta gramática; não estabelecem inteligência geral nem generalização para programação.
O estrato relacionado incorpora motivos aleatórios do treino (profundidade 3); o estrato sem relação exclui subárvores compartilhadas de profundidade >=3. Isso cria oportunidades deliberadas de transferência, independentes do sucesso dos agentes. Não significa ausência de operações ou regularidades matemáticas compartilhadas.
A procura de candidatos e a regra de armazenamento são programadas. As expressões específicas são adquiridas das observações. A memória pode guardar hipóteses incorretas: nenhuma resposta reservada é usada para corrigi-las. O congelamento de C e as falhas mostram efeitos além de simplesmente acrescentar regras úteis.
Os 100 alvos são semanticamente distintos do treino em cada semente, mas reaparecem nos checkpoints. As taxas entre checkpoints são pareadas, não 600 problemas independentes. Três sementes não sustentam estimativas populacionais precisas.
Verificação automática em verification.json: 12.600 episódios, limites de hipóteses e profundidade, congelamento de C, memória constante durante avaliação e hashes do Experimento 01. A reabertura SQLite em outro processo verifica persistência dos registros; não testa recuperação após falha abrupta.
As tentativas interrompidas do gerador permanecem nas pastas anteriores; somente a execução indicada no início deste relatório compõe as tabelas. A contagem de hipóteses inclui candidatos considerados em lotes, mesmo quando uma solução aparece antes do fim do lote. Não é contagem de operações aritméticas. Consultas estão em experiments; observações completas estão em raw.jsonl.
