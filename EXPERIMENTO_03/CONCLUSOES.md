# Conclusões auditadas — Experimento 03

Execução principal concluída. As tabelas abaixo são calculadas dos registros reais; não houve seleção de pesos ou problemas por desempenho final. RELATORIO_03.md contém todos os checkpoints e PROTOCOLO.md define as métricas.

|Regime|Capacidade|Agente|Acertos finais /72|Tempo total médio ms|Seleção média ms|Candidatos médios|
|---|---:|---|---:|---:|---:|---:|
|candidates|8|A|19|64.842|0.013|631.6|
|candidates|8|B|41|58.490|0.761|463.7|
|candidates|8|C|40|59.068|5.139|464.2|
|candidates|8|D|36|57.374|0.507|499.0|
|candidates|8|ORDER|36|54.953|0.355|480.3|
|candidates|24|A|19|69.337|0.013|631.6|
|candidates|24|B|51|56.926|1.527|389.6|
|candidates|24|C|41|57.746|9.359|429.2|
|candidates|24|D|34|61.417|0.526|491.1|
|candidates|24|ORDER|37|58.315|0.372|482.1|
|time|8|A|12|11.330|0.013|156.2|
|time|8|B|21|11.334|0.710|120.1|
|time|8|C|19|12.333|4.913|84.3|
|time|8|D|20|11.747|0.511|131.8|
|time|8|ORDER|22|11.252|0.353|128.8|
|time|24|A|13|11.309|0.013|156.3|
|time|24|B|20|11.880|0.931|116.8|
|time|24|C|15|12.852|6.050|72.6|
|time|24|D|18|11.979|0.504|130.8|
|time|24|ORDER|23|11.805|0.329|132.9|

## Variação entre sementes
|Semente|Capacidade|Agente|Sucesso final candidatos %|
|---:|---:|---|---:|
|104729|8|A|29.17|
|104729|8|B|54.17|
|104729|8|C|54.17|
|104729|8|D|45.83|
|104729|8|ORDER|45.83|
|104729|24|A|29.17|
|104729|24|B|70.83|
|104729|24|C|58.33|
|104729|24|D|54.17|
|104729|24|ORDER|58.33|
|130363|8|A|25.00|
|130363|8|B|66.67|
|130363|8|C|62.50|
|130363|8|D|62.50|
|130363|8|ORDER|58.33|
|130363|24|A|25.00|
|130363|24|B|79.17|
|130363|24|C|70.83|
|130363|24|D|50.00|
|130363|24|ORDER|66.67|
|155921|8|A|25.00|
|155921|8|B|50.00|
|155921|8|C|50.00|
|155921|8|D|41.67|
|155921|8|ORDER|45.83|
|155921|24|A|25.00|
|155921|24|B|62.50|
|155921|24|C|41.67|
|155921|24|D|37.50|
|155921|24|ORDER|29.17|

## Referência matemática
Interpolação racional exata: 72/72 alvos. Nove consultas, média de 17.249 ms incluindo teste externo. Não comparável diretamente ao tempo de busca, que exclui teste externo. A referência usa a hipótese conhecida de polinômio de grau ≤8 e não aprende uma biblioteca de árvores.

## Ablações rechecadas
10 ablações; 0 diferiram do registro preliminar. Evidência local de necessidade: 4. Solução válida com e sem: 6. Registros finais em results/audited_ablations.json. Os números auditados substituem a contagem preliminar de ablação em RELATORIO_03.md.
A rechecagem usa a seleção antes da atualização FIFO. O registro preliminar de parte da execução usava a memória após atualização, podendo retirar mais de uma habilidade. Ablações preliminares fora da seção principal também são excluídas: a rotina de ablação aritmética não era apropriada para a expansão. Esses erros não afetam as soluções principais, as pontuações ou os acertos, porque ablações são executadas após busca/treino e não entram no cálculo de seleção. Custos extras permanecem registrados. Dados preliminares são mantidos para auditoria.

## Aprendizagem das estatísticas
Maior número de tentativas de construção em um contexto: 2. A fórmula atualiza P e E quando há uso real em construção; mera seleção não ganha crédito. A pontuação não estima efeito causal. A evidência por contexto é escassa: o experimento não isola o benefício de aprender P/E do benefício das regras fixas R/K. Não foi demonstrado aprendizado robusto de quando usar conhecimento.

## Expansão em direção à programação
|Memória aritmética anterior|Acertos /90|Tempo médio ms|Candidatas contendo if /90|Acertos contendo if /90|
|---|---:|---:|---:|---:|
|False|14|1094.859|18|4|
|True|16|1127.184|18|4|

A expansão é uma busca de pequenas funções, não desenvolvimento de software geral. Uma solução pode dispensar if por equivalência do alvo no conjunto testado. Validação em grade finita não é prova universal; veja dados brutos para casos refutados e falhas. A diferença de apenas dois acertos (16 contra 14) não sustenta uma alegação forte de transferência para programação.

## Orçamentos e limites
Máximo de tempo de busca no regime temporal: 16.583 ms. O prazo é cooperativo, inclui seleção e pode ser ultrapassado. A execução foi sequencial; tempos curtos têm ruído e não permitem precisão excessiva.
Não há evidência de que a fórmula proposta seja ótima ou que adquirir mais habilidades sempre ajude. Comparações com D e ORDER são necessárias para atribuir benefício à seleção adaptativa em vez de apenas limitar a memória. Ganhos devem ser avaliados por orçamento, capacidade e semente.
O piloto de recursos foi excluído da grade principal e preservado integralmente. Foram verificadas contagens, limites, tamanho da memória nas avaliações e hashes dos arquivos anteriores. A retomada foi exercitada; não se testou queda abrupta de energia.

## Sobrecarga do painel
Mediana logging/sem logging em 12 pares: 55.06×. Expressões e contagens equivalentes nos pares. Tempo médio de processamento/desenho Tkinter por lote de teste: 47.59 ms. São medições separadas: não representam soma exata do custo de um uso humano com pausas. Instrumentação visual não é habilitada nas avaliações científicas.

## Interpretação central
Com capacidade 24 e orçamento de candidatos, C acertou 41/72, contra 34/72 de D, 37/72 de ORDER e 51/72 de B. Com prazo de 12 ms, C acertou 15/72, contra 18/72 de D, 23/72 de ORDER e 20/72 de B. O custo de seleção de C consumiu parte substancial do prazo. A fórmula proposta não foi superior em todas as condições, e sua vantagem em candidatos não demonstra redução geral do custo computacional.