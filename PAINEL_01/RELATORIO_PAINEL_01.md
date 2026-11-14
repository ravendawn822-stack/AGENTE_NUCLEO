# Observabilidade local do AGENTE_NUCLEO

Interface desktop Tkinter, usando exclusivamente a biblioteca padrão Python. Foi escolhida para dispensar servidor, navegador e dependências. O desenho usa abas, tabelas, gráfico Canvas e árvore de expressão com no máximo 15 nós nos candidatos usuais. Há relações sintáticas em texto entre habilidades selecionadas; não há layout de grafo global pesado.

## Fontes e preservação

O painel lê `raw.jsonl` e abre `memory.sqlite3` do Experimento 02 em modo SQLite somente leitura. Apenas execuções históricas com `verification.json` entram na lista. Tentativas interrompidas não são misturadas. Os arquivos do Experimento 01 são preservados, mas seu esquema antigo não é importado nesta versão. Toda gravação nova fica em PAINEL_01. O verificador compara hashes de todos os arquivos externos a essa pasta antes e depois dos testes.

## Histórico e novos eventos

Os históricos oferecem métricas por episódio, observações, expressão final e resultado da validação. Não oferecem cronologia de hipóteses. O replay histórico é explicitamente parcial: mostra a ordem das observações e o resumo final, sem inventar candidatos ou tempos intermediários.

O diagnóstico importa o núcleo original sem gerar bytecode em sua pasta e usa `sys.settrace` para observar a execução real de `solve`. Os ganchos reconhecem as linhas de teste e escolha de entradas do código original; se o núcleo mudar, a instrumentação deve ser revalidada. Cada candidato contado gera um evento; candidatos de um lote após a solução podem ter sido gerados sem ter sido testados. São eventos diferentes.

Há eventos de início/fim, entradas, consultas, candidatos gerados/testados, rejeição com primeiro contraexemplo, aceitação por consistência com o treino, habilidades consultadas/reutilizadas/adquiridas, etapas de busca/validação/memória e falhas na validação reservada. O problema é identificado pelo episódio/index e pela configuração da suíte. Tempos monotônicos são registrados por episódio. O orçamento consumido corresponde ao contador real de candidatos do núcleo.

Descartes são anotados a partir da expressão efetivamente testada e da primeira divergência aritmética em suas observações. Esse cálculo observacional é repetido pelo monitor e não interfere na decisão do núcleo. A validação é feita após o retorno do agente, sem oferecer respostas reservadas à busca. Aquisição segue a regra original de consistência no treino, mesmo quando a validação falha; não esconde essa limitação.

## Interpretação

“Aceita” significa compatível com as consultas do treino, não demonstração universal. “Descoberta” significa expressão inserida pela regra de armazenamento. “Reuso” é presença de subárvore na expressão aceita. Usos históricos são derivados comparando soluções posteriores à aquisição com as árvores SQLite: não são contadores instrumentados antigos. A tabela também conta em quantos acertos há essa presença, mas não estima quanto uma habilidade causou o acerto. Relações exibidas são sintáticas, não estados mentais ou pensamentos.

A taxa de sucesso da visão geral usa apenas avaliação no último checkpoint selecionado; não mistura treino e avaliação nem checkpoints. Sessões diagnósticas são identificadas como treino, sem substituir taxas científicas. A memória por episódio é a quantidade registrada no início da busca; a tabela de habilidades é o estado final. O pico de memória histórico mede alocações Python, não RAM total. Tempos e orçamentos históricos mantêm a definição do experimento.

Rastreamento detalhado custa CPU, memória e disco. Tempos de diagnóstico não podem ser comparados aos tempos científicos. Usa-se apenas o orçamento de hipóteses nessa modalidade, para não mudar resultados pela sobrecarga temporal. A equivalência de expressões, contagens e observações é testada em 12 episódios cumulativos. O monitor não constitui isolamento de segurança entre agente e avaliador.

## Limites operacionais

Não há comunicação externa. Dados são carregados ao selecionar uma execução; o painel não vigia processos científicos externos. A barra acompanha o diagnóstico iniciado pelo próprio painel, e o replay completo fica disponível quando termina. O volume atual (12.600 episódios) cabe em memória; para históricos muito maiores será necessário paginar e indexar. A compatibilidade com o Python/Tkinter instalado foi testada; não foi feito benchmark específico em um Pentium E2140.

Resultados dos testes estão em VERIFICACAO.json. O teste de interface instancia as abas, troca fonte, seleciona replay e aplica filtro. Não substitui avaliação visual manual em todas as escalas de tela.
