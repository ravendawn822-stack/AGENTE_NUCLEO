# PAINEL_01 — uso local

Abra `INICIAR.cmd` com duplo clique, ou execute `python panel.py` nesta pasta. Requer Python com Tkinter (incluído no instalador padrão para Windows). Nenhuma instalação por pip, navegador, serviço, CDN ou internet é necessária. Feche a janela para encerrar.

1. Escolha a execução na lista superior. As execuções verificadas do Experimento 02 são históricas; as sessões diagnósticas são novas execuções.
2. Filtre agente, orçamento e semente. A visão geral apresenta taxa e tempo do último checkpoint de avaliação disponível. A tabela lista episódios; selecionar uma linha prepara o replay.
3. Na aba Execução e replay, use as setas, o controle deslizante ou Reproduzir/pausar. O registro mostra o evento, o orçamento registrado até aquele ponto e a árvore da última expressão observada.
4. Na aba Memória, consulte origem, profundidade, expressão e usos derivados. Selecione uma habilidade para ver componentes armazenados relacionados. A lista apresenta o banco final da execução, não a memória em cada instante do replay.
5. Comparações reúne A/B/C por checkpoint, respeitando semente e orçamento. O filtro de agente não restringe essa aba, para manter a comparação. O gráfico mostra sucesso; a tabela inclui tempo, candidatos, habilidades e pico de alocações Python.
6. Novo diagnóstico executa B nos primeiros 12 problemas de treinamento da semente 104729, a partir de memória vazia. O trabalho acontece em uma thread e a barra informa o problema atual. Ao terminar, a sessão é selecionada automaticamente para replay. Fechar a janela durante a execução pode deixar uma sessão parcial; ela não é um experimento concluído.

Os logs detalhados são carregados após a conclusão, sem atualizar milhares de linhas gráficas durante a busca. Novas sessões ficam em `sessions/AAAAmmdd_HHMMSS/`, com `raw.jsonl`, `events.jsonl`, `memory.sqlite3` e configuração. Não entram nas estatísticas históricas.

`python diagnostic.py` executa o diagnóstico sem interface. `python verify.py` verifica equivalência de resultados com/sem rastreamento, instrumentação, leitura do banco, controles Tkinter e preservação por hashes; gera uma nova sessão demonstrativa.

O botão de diagnóstico não inicia o Experimento 02 completo. Não execute os scripts antigos para abrir o painel: o executor do Experimento 01 sobrescreve seus próprios resultados.
