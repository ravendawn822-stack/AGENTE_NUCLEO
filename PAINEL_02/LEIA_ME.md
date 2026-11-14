# Painel 02

Abra INICIAR.cmd ou execute `python panel.py`. Usa apenas Python, Tkinter e SQLite. Não há servidor, navegador, CDN, pip ou serviço externo.

- Iniciar diagnóstico: executa 12 treinos de uma sessão nova, com o agente escolhido. Não inicia nem modifica o experimento científico. Pausar e Continuar controlam o produtor de eventos, Passo libera um evento, Encerrar mantém todos os registros já confirmados. Velocidade controla o intervalo por evento. A atualização visual acontece no máximo cinco vezes por segundo e lê até mil eventos por ciclo.
- Ao vivo e grafo: mostra até 60 entidades reais registradas no banco, priorizando habilidades destacadas e eventos recentes. Arestas significam composição direta de árvores. Clique para examinar expressão, composição, estados por contexto, evidências, estatísticas e pontuação. A ausência de um nó da tela não significa que tenha sido apagado da memória ou do banco.
- Cores de preenchimento representam hipótese/candidata/validada/refutada no contexto mais recentemente observado, ou componente sem esse estado. Contornos representam selecionada, construída e adquirida. Estado de validação não é um grau de consciência. Presença e uso na construção possuem eventos distintos.
- Pontuações e memória: P/R/E/K/S efetivamente calculados por C; outros agentes não recebem pontuações fictícias. Curva mostra quantidade de habilidades ativas após os treinos diagnósticos.
- Replay: escolha uma sessão e revise os eventos confirmados. O controle deslizante e as setas mostram os registros originais e a árvore da última expressão. Sessões interrompidas continuam acessíveis. Replay não executa o agente.
- Comparação científica: clique Ler resultados científicos para consultar o SQLite do Experimento 03 em modo somente leitura. Filtre orçamento/capacidade. A/B/C/D e ORDER aparecem separados. Contagem n menor que 72 indica checkpoint ainda incompleto. Diagnósticos não são agregados. A leitura é explícita para não reler o banco inteiro a cada frame.

As sessões são gravadas em `sessions/` com eventos JSONL e SQLite; cada evento é confirmado antes de aparecer. Fechar a janela solicita cancelamento; transações já confirmadas permanecem legíveis. Tempos de diagnóstico incluem pausas, controle visual e logging; não são métricas científicas de desempenho.

O modo científico deve ser executado em outro momento, sem diagnóstico concorrente, para evitar disputa de CPU. `render_measurements.json` mede o processamento/desenho Python dos frames observados; não é medida completa do compositor do Windows. `overhead/measurements.json` mede logging SQLite/JSONL em pares com e sem instrumentação, com ordem alternada, sem atrasos humanos.
