import csv, json, logging, os, sqlite3, time
from pathlib import Path
from expressions import Expr
from memory import Memory
from agent import Agent
from oracle import training_problems, novel_problems

ROOT = Path(__file__).resolve().parent
DB = ROOT / "memoria.sqlite3"
LOG = ROOT / "logs" / "experimento.log"
RESULT = ROOT / "resultados" / "resultados_brutos.csv"
logging.basicConfig(filename=str(LOG), level=logging.INFO, format="%(asctime)s %(message)s")

def run():
    if DB.exists(): DB.unlink()
    if RESULT.exists(): RESULT.unlink()
    rows = []
    # A não recebe memória entre problemas; B recebe a mesma classe de memória.
    for label, persistent in (("A_sem_reuso", False), ("B_com_memoria", True)):
        mem = Memory(str(DB)) if persistent else None
        agent = Agent(label, mem, max_depth=4, budget=2000)
        for phase, boxes in (("treino", training_problems()), ("inedito", novel_problems())):
            for box in boxes:
                r = agent.solve(box, [-3, -1, 0, 2], [1, 3, 5])
                r.update(agent=label, phase=phase, problem=box.name)
                rows.append(r); logging.info(json.dumps(r, ensure_ascii=False))
                if mem: mem.episode(label, box.name, r["success"], r["experiments"], r["hypotheses"], r["seconds"], r["peak_kb"])
        if mem: mem.close()
    with RESULT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["agent","phase","problem","success","expr","experiments","hypotheses","seconds","peak_kb","calls"])
        writer.writeheader(); writer.writerows(rows)
    build_report(rows)
    print(json.dumps(rows, indent=2, ensure_ascii=False))

def build_report(rows):
    def stats(agent, phase):
        xs = [r for r in rows if r["agent"] == agent and r["phase"] == phase]
        return (sum(r["success"] for r in xs), len(xs), sum(r["experiments"] for r in xs), sum(r["hypotheses"] for r in xs))
    a_t, a_n, b_t, b_n = stats("A_sem_reuso","treino"), stats("A_sem_reuso","inedito"), stats("B_com_memoria","treino"), stats("B_com_memoria","inedito")
    report = f'''# Relatório — Experimento 01: Nascimento

## Escopo

Executado em {time.strftime("%Y-%m-%d %H:%M:%S")} com Python e SQLite, sem LLM, API externa ou rede neural. O avaliador mantém árvores ocultas e expõe somente `query(entrada)`. O agente conhece apenas variáveis, constantes -2..2 e soma, subtração e multiplicação.

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
| A treino | {a_t[0]} | {a_t[1]} | {a_t[2]} | {a_t[3]} |
| A inédito | {a_n[0]} | {a_n[1]} | {a_n[2]} | {a_n[3]} |
| B treino | {b_t[0]} | {b_t[1]} | {b_t[2]} | {b_t[3]} |
| B inédito | {b_n[0]} | {b_n[1]} | {b_n[2]} | {b_n[3]} |

## O que foi demonstrado

O programa executou busca simbólica, rejeitou hipóteses incompatíveis com observações e persistiu resultados confirmados em SQLite. A comparação de sucesso em problemas inéditos permite observar se a memória ajudou neste protocolo específico.

## Limitações e interpretação

Este primeiro experimento não demonstra inteligência geral, autonomia ou compreensão semântica. A gramática é pequena, o espaço de busca é enumerativo e as funções ocultas foram construídas com as mesmas primitivas conhecidas. A ordem dos candidatos e a seleção dos desafios influenciam fortemente os resultados. A memória armazena expressões confirmadas; isso é reutilização estrutural, não aprendizado não supervisionado amplo. Resultados negativos devem ser considerados válidos.

## Artefatos

Resultados por linha: `resultados/resultados_brutos.csv`; banco persistente: `memoria.sqlite3`; log de execução: `logs/experimento.log`. O banco pode ser reaberto após reinício para inspecionar as habilidades de B.
'''
    (ROOT / "RELATORIO.md").write_text(report, encoding="utf-8")

if __name__ == "__main__": run()

