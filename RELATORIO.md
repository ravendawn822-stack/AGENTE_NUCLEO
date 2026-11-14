# Relatório — Experimento 01: Nascimento

## Escopo

Executado em 2026-11-14 17:22:56 com Python e SQLite, sem LLM, API externa ou rede neural. O avaliador mantém árvores ocultas e expõe somente `query(entrada)`. O agente conhece apenas variáveis, constantes -2..2 e soma, subtração e multiplicação.

## Arquitetura

- `expressions.py`: árvores com identificadores numéricos, avaliação e composição limitada.
- `agent.py`: percepção por consultas, geração enumerativa limitada, comparação, refutação e armazenamento de árvores confirmadas.
- `memory.py`: memória persistente SQLite de habilidades, episódios e eventos.
- `oracle.py`: caixa-preta independente, sem método para o agente acessar o código oculto.
- `run_experiment.py`: protocolo fixo, métricas, log e relatório.

## Protocolo

    Os dois agentes receberam o mesmo conjunto de entradas candidatas, validação e orçamento de 2.000 hipóteses. Cada agente escolheu quatro entradas de treino por desacordo entre previsões candidatas, sem observar respostas antes da consulta. A separação A/B foi feita por memória: A não reutiliza habilidades; B persiste árvores confirmadas entre problemas. Os problemas `N01..N03` foram reservados para avaliação inédita.

| Agente/fase | Acertos | Problemas | Consultas | Hipóteses |
|---|---:|---:|---:|---:|
| A treino | 2 | 3 | 3950 | 3900 |
| A inédito | 1 | 3 | 6126 | 6000 |
| B treino | 3 | 3 | 2917 | 2852 |
| B inédito | 2 | 3 | 2481 | 2431 |

## O que foi demonstrado

O programa executou busca simbólica, rejeitou hipóteses incompatíveis com observações e persistiu resultados confirmados em SQLite. A comparação de sucesso em problemas inéditos permite observar se a memória ajudou neste protocolo específico.

## Limitações e interpretação

Este primeiro experimento não demonstra inteligência geral, autonomia ou compreensão semântica. A gramática é pequena, o espaço de busca é enumerativo e as funções ocultas foram construídas com as mesmas primitivas conhecidas. A ordem dos candidatos e a seleção dos desafios influenciam fortemente os resultados. A memória armazena expressões confirmadas; isso é reutilização estrutural, não aprendizado não supervisionado amplo. Resultados negativos devem ser considerados válidos.

## Artefatos

Resultados por linha: `resultados/resultados_brutos.csv`; banco persistente: `memoria.sqlite3`; log de execução: `logs/experimento.log`; configuração: `config.json`. A reabertura após reinício foi verificada: 12 habilidades continuaram disponíveis e 6 episódios foram preservados.
