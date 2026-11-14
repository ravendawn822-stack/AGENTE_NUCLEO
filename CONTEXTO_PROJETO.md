# AGENTE_NUCLEO — contexto para continuidade

## Objetivo

Investigar um núcleo matemático capaz de adquirir, selecionar, compor e aperfeiçoar habilidades persistentes. O objetivo de longo prazo é um agente autônomo especializado em programação; as tarefas matemáticas atuais são ensaios de mecanismos fundamentais. Uma IA professora é uma possibilidade futura, não implementada nem autorizada nesta etapa.

Restrições: Python/biblioteca padrão, SQLite, Tkinter, baixo consumo, Windows 10/Pentium E2140 como referência de restrição. Sem LLM, redes neurais ou APIs de inteligência no agente. A migração adiciona infraestrutura Linux/Codespaces, sem mudar mecanismos científicos.

## Organização preservada

- Raiz: **Experimento 01** (`agent.py`, `expressions.py`, `oracle.py`, `memory.py`, `run_experiment.py`, banco, logs e relatório). Não havia pasta EXPERIMENTO_01; os arquivos continuam em seus lugares.
- EXPERIMENTO_02: aprendizagem cumulativa A/B/C, sementes, diagnósticos iniciais interrompidos, execução completa, dados e auditoria.
- PAINEL_01: observabilidade local e sessões de rastreamento, preservadas.
- EXPERIMENTO_03: memória adaptativa, cinco estratégias, avaliação aritmética, desenvolvimento, expansão condicional, referência matemática, ablações e piloto de recursos.
- PAINEL_02: monitoramento real, grafo, pontuações, controle diagnóstico, replay, medições de sobrecarga antes/depois de otimização.
- MIGRACAO e .devcontainer: adições de infraestrutura, inventário, verificação e cópias SQLite consistentes. Não são experimentos científicos novos.

## Arquitetura

Expressões são árvores/tuplas com identificadores numéricos para primitivas e entidades. Busca limitada enumera composições. Memória SQLite e snapshots persistem expressões, contextos, evidências, origens, seleção, uso na construção e presença. Avaliadores externos verificam previsões em entradas reservadas. Há separação funcional de dados, não sandbox de segurança contra introspecção maliciosa.

No Experimento 03, hipótese é uma expressão gerada; candidata passou pelas consultas iniciais; validada passou por testes adicionais de treino; refutada encontrou contradição no contexto declarado. Somente raízes operacionais validadas entram como habilidades. Uma validade contextual não é verdade universal.

## Experimento 01 e auditoria

Primeiro protótipo: A sem reuso e B persistente. Na execução final registrada, A acertou 3/6, B 5/6. Esses números não constituem uma comparação controlada de generalização. A auditoria do Experimento 02 encontrou contagem 2.001 para 2.000 candidatos efetivamente testados, validação dentro do agente, aprendizagem durante avaliação, armazenamento condicionado a best em vez de success e N01 explicitamente construído a partir de T01. A árvore reutilizada em N01 tinha profundidade expandida 4, sem vantagem oculta de profundidade. Os originais e as conclusões antigas estão preservados; consultar a auditoria antes de interpretá-los.

## Experimento 02

Três sementes; 100 treinos e 100 problemas inéditos por semente; checkpoints 0/10/25/50/75/100. A sem reuso, B cumulativo e C congelado após dez treinos. Avaliação não atualiza memória. No orçamento de 2.000 candidatos, sucesso final médio: A 11,33%, B 66,67%, C 31,33%. No regime nominal de 12 ms: A 1,33%, B 16,33%, C 11%. A melhora temporal de B não foi monotônica. Foram 12.600 episódios. Os problemas relacionados foram construídos com motivos do treino; o estrato sem relação excluía subárvores idênticas de profundidade ≥3, não toda relação matemática.

## Experimento 03

A sem reutilização; B usa toda memória ativa; C seleção adaptativa; D seleção aleatória; ORDER seleção por aquisição. C/D/ORDER selecionam até quatro habilidades. Capacidade FIFO 8 ou 24. Três sementes, 24 treinos e 24 avaliações por semente, checkpoints 0/8/16/24. Limites de 800 candidatos ou 12 ms cooperativos. A grade foi reduzida após piloto de custo, preservado separadamente. Total 7.680 episódios: 7.200 principais, 120 de sensibilidade, 360 da expansão.

S(h,c)=(0,45P+0,35R+0,20E)/(1+K). P=(sucessos+1)/(tentativas+2), E=1/sqrt(1+tentativas). R compara características observáveis de diferenças, crescimento e simetrias; K combina complexidade e custo histórico normalizado de operações. Tempos reais são medidos separadamente. Tentativas e sucessos são associados ao uso efetivo em construção, não automaticamente à seleção. Pesos são hipótese de projeto; sensibilidade usa dados de desenvolvimento, sem escolher pesos pela avaliação final.

Na capacidade 24, acertos finais /72 por candidatos: A 19, B 51, C 41, D 34, ORDER 37. Sob 12 ms: A 13, B 20, C 15, D 18, ORDER 23. C superou D em candidatos, mas não B; sob tempo, o custo da seleção prejudicou C. Houve no máximo duas tentativas de construção por contexto: não se demonstrou aprendizado robusto de quando usar conhecimento, nem se isolou benefício de aprender P/E das regras fixas R/K.

Dez ablações principais auditadas: quatro perderam a solução ao retirar uma habilidade; seis resolveram com e sem. Isso é evidência local sob orçamento, não causalidade universal. Uma ablação preliminar fora da seção principal foi excluída da interpretação, mas preservada. A rechecagem das dez principais não alterou seus resultados. Interpolação racional, referência separada para polinômios de grau ≤8, acertou 72/72 com nove consultas.

A expansão introduziu comparações, booleanos, if e x/y. Foram 30 treinos e 30 avaliações por semente, comparando memória aritmética anterior com vazia. Acertos /90: 16 com anterior, 14 sem. Diferença pequena e teste em grade finita não demonstram transferência robusta para programação ou equivalência universal de funções.

## Observabilidade

Painel 01: histórico com replay parcial; diagnósticos novos registram eventos reais. Painel 02: SQLite/JSONL, grafo de entidades persistidas e relações de composição, pontuações, evidências, estados contextuais, pausa/passo/velocidade/cancelamento e comparação científica em modo somente leitura. Atualização máxima de cinco vezes por segundo, até 60 nós no recorte visual.

Sobrecarga detalhada foi medida: mediana logging/sem logging caiu de 86,59× para 55,06× após lotes/cache; processamento/desenho médio caiu de 216,64 para 47,59 ms por lote. Logging continua caro e não deve ser usado para tempos científicos. Medições anteriores, sessões e falhas de desenvolvimento foram mantidas.

## Limitações e próximos passos, dependentes de autorização

Não há inteligência geral, programação aberta ou professora integrada. Busca, gramática, retenção e função de seleção são regras programadas; as árvores específicas são descobertas por consultas. Poucas sementes/contextos, retenção FIFO e ordem de enumeração limitam conclusões. Limites temporais são cooperativos; memória medida por tracemalloc não é RSS. Não houve benchmark físico específico no Pentium.

Possíveis próximos trabalhos: ampliar evidência por contexto, separar efeito das estatísticas aprendidas do ranking fixo, reduzir custo de seleção, estudar retenção, ampliar testes condicionais e revisar protocolos antes de novos experimentos. Nenhum desses trabalhos foi iniciado na migração. Para continuar com Codex, ler este documento, AGENTS.md, PROTOCOLO.md e CONCLUSOES.md; conferir hashes e trabalhar em uma nova pasta autorizada.
