# Continuidade do AGENTE_NUCLEO

Leia CONTEXTO_PROJETO.md e MIGRACAO/README.md antes de qualquer ação.

- Os 178 arquivos de inventario_original.json são evidência histórica: preserve bytes, resultados negativos, bancos, logs, fontes e checkpoints.
- EXPERIMENTO_01 está na raiz; não reorganize nem crie uma duplicata que pareça ser um experimento diferente.
- Não execute run_experiment.py: ele apaga/recria resultados do Experimento 01. Não rode runners/verificadores históricos diretamente nesta árvore, pois podem gravar nos arquivos científicos.
- Os mecanismos de inteligência não foram alterados na migração. Não inicie Experimento 04 ou integração com professora sem solicitação explícita.
- Diagnóstico visual: python3 MIGRACAO/launch_panel.py --panel 02. Ele cria cópia de execução isolada; não misture diagnósticos e avaliações científicas.
- Checagem segura: python3 MIGRACAO/check_portability.py (exige display para Tk). Integridade: python3 MIGRACAO/verify_integrity.py.
- Não trate associação, seleção, presença sintática e contribuição causal como equivalentes. Estados de validade têm contexto.
- Use pastas novas para trabalhos futuros autorizados. Registre sementes, orçamento total, configuração, falhas, retomadas e hashes. Não ajuste parâmetros usando o conjunto final.
- Não registre tokens, senhas ou credenciais. Mantenha repositório e porta 6080 privados. Não inicie recursos pagos sem esclarecer custos.
- SQLite: inspecione snapshots em MIGRACAO/sqlite_consistentes em modo somente leitura. Os bancos históricos e seus WAL/SHM são arquivos de preservação; para execução, use cópias.
