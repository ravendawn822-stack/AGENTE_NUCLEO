# Experimento 02

Execute `python -u run.py` nesta pasta. Cada execução cria uma pasta timestamp; nada é sobrescrito no Experimento 01. `RELATORIO_02.md` apresenta a execução mais recente. Os arquivos raw.jsonl são logs completos por problema e conservam resultados negativos.

Protocolo: três sementes, 100 treinos e 100 avaliações únicas por semente, dois orçamentos, três agentes e seis checkpoints. C congela após dez treinos. Avaliações são feitas sobre a mesma bateria nos seis checkpoints; nenhuma grava habilidade. As habilidades são hipóteses compatíveis com as consultas de treino, sem aprovação do avaliador.

Relação estrutural: presença de uma subárvore de profundidade >=3 idêntica a alguma árvore/subárvore do treino. Metade dos alvos incorpora um motivo sorteado do treino e metade é sorteada com rejeição dessas relações. Essa estratificação deliberada mede transferência e sua ausência, e favorece por construção oportunidades de transferência no estrato relacionado: não representa distribuição universal de tarefas. Todos os agentes recebem os mesmos alvos e limites. Nenhuma seleção usa habilidades que B conseguiu aprender.

Foram preservadas tentativas interrompidas de desenvolvimento do gerador: inicialmente a exigência de complexidade fixa podia esgotar funções rasas; depois a rejeição por relações simples dificultou a amostragem. Pastas sem conclusão não entram no relatório. As tentativas não foram usadas para ajustar desempenho dos agentes.

Memória Python: pico incremental medido por tracemalloc, não memória total do processo. Limite temporal cooperativo inclui instrumentação; tarefas muito curtas têm ruído relativo elevado. Profundidade máxima e limites de tamanho são avaliados nas árvores totalmente expandidas (máximo 15 nós para profundidade 4).
