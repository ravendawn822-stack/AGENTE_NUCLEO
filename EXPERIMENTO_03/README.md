# Experimento 03

Execute `python tests.py` e `python -u run.py`. A execução científica roda sem interface, grava checkpoints SQLite e pode ser interrompida com Ctrl+C e retomada pelo mesmo comando. Não execute múltiplos runners simultaneamente na mesma pasta. A configuração é fixada em `results/config.json`.

`PROTOCOLO.md` define fórmulas, neutralidade, evidências, limitações e a distinção entre associação e ablação. `RELATORIO_03.md` contém tabelas da execução concluída; `CONCLUSOES.md` complementa com auditoria final, resultados por semente, referência matemática e sobrecarga. `results/experiment.sqlite3` preserva episódios, snapshots e habilidades. `results/raw.jsonl` é a exportação após conclusão. `pilot_resource` preserva a tentativa inicial maior, não incluída nas tabelas principais.

O painel é aberto por `..\PAINEL_02\INICIAR.cmd`. Sessões diagnósticas têm seus próprios bancos e nunca entram nas estatísticas científicas.
