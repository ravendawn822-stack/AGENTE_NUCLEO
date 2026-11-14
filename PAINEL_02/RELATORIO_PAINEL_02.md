# Painel 02 — observabilidade

Implementação Python/Tkinter/SQLite, sem dependências externas, serviços ou chamadas de rede. PAINEL_01 permanece intacto. O painel usa uma thread produtora para o diagnóstico; somente a thread principal acessa Tkinter. Eventos são persistidos antes da visualização. O consumidor lê lotes limitados a cada 200 ms e desenha até 60 nós reais, evitando atualizar a tela por hipótese. Controle por Condition permite pausa, continuação, cancelamento e liberação de um evento por passo. Não há execução científica acionada pelos controles visuais.

## O que é observado

Geração e refutação de hipóteses, consistência das candidatas, testes adicionais de treinamento, seleção e pontuações P/R/E/K/S, derivação com habilidades, presença sintática, aquisição e crescimento da memória. O grafo usa apenas entidades persistidas no SQLite e arestas de composição direta das expressões. Cada nó tem origem observável (episódio e sequência do primeiro registro). A inspeção apresenta evidências e estados contextuais, frequências, contextos e histórico recente. Uma hipótese refutada para um alvo não apaga a validade de uma habilidade para o contexto original.

Contadores de seleção, uso na construção e presença são separados. Utilidade agregada usa suavização de Laplace sobre associações de construção, claramente identificada; não equivale à pontuação contextual nem à contribuição causal. Sessões diagnósticas não executam ablações, portanto não apresentam provas causais inventadas. Ablações científicas ficam nos relatórios e no banco científico.

Hipóteses azuis, candidatas amarelas, validadas verdes, refutadas vermelhas e componentes cinza. Contornos distintos indicam seleção, teste, construção e aquisição. Um mesmo nó pode mudar de estado contextual durante uma sessão. Nós fora dos 60 exibidos continuam armazenados; não há inferência de desaparecimento de conhecimento a partir do recorte visual.

## Separação e sobrecarga

O runner científico não importa Tkinter nem Recorder e usa emit=None. Sessões diagnósticas têm configuração e SQLite próprios, incluindo JSONL integral. Os logs registram tempos monotônicos; pausas e velocidade mudam o tempo diagnóstico, não a avaliação científica. O replay somente lê eventos.

Comparações consultam o banco científico em modo somente leitura, sob ação explícita do usuário. Tabelas discriminam A/B/C/D e ORDER, capacidade, regime, checkpoint e quantidade de episódios. Checkpoints parciais são identificados pelo n. Resultados diagnósticos nunca entram nessa agregação.

O teste de sobrecarga alterna a ordem de 12 pares com/sem logging real SQLite/JSONL e verifica igualdade da expressão final e contagem de candidatos. Não inclui atrasos deliberados do controle. O teste de desenho mede processamento de lotes, Canvas e update_idletasks em Tkinter; não mede o compositor Windows nem interação humana completa. Números efetivamente medidos estão em VERIFICACAO.json e overhead/measurements.json.

A primeira implementação confirmou cada evento individualmente: mediana de 86,59× e desenho médio de 216,64 ms por lote de teste. As medições foram preservadas em VERIFICACAO_before_batching.json e overhead/measurements_before_batching.json. Após confirmação em lotes de até 32 eventos, cache limitado de identificadores e redução de atualizações repetidas da interface, mediu-se 55,06× e 47,59 ms. As medianas absolutas por episódio foram 6,35 ms sem logging e 385,19 ms com logging. A instrumentação detalhada continua cara; dependências leves não significam custo desprezível. Por isso não se usa logging detalhado nos experimentos científicos. Passo a passo confirma imediatamente o evento liberado; encerramento normal confirma os eventos pendentes.

## Limites

Não há representações de pensamentos, neurônios ou estados mentais. Validação tem escopo e evidências finitas. O grafo mostra composição sintática, não rede neural nem grafo causal. CPU e memória do logging podem exceder os da busca sem monitor; por isso diagnóstico não é uma fonte de tempos científicos. Fechar a janela pode interromper o produtor antes da confirmação do último evento; todos os eventos já confirmados são preservados. Replay carrega uma sessão diagnóstica em memória, adequado às sessões curtas atuais; sessões muito maiores precisarão paginação.

Teste automatizado exercita pausa/passo/cancelamento, existência dos nós no banco, sessão real, inspeção, replay, gráfico e consulta científica. Verifica também hashes dos arquivos anteriores. A interface foi testada no ambiente instalado; não se afirma benchmark em hardware Pentium específico nem revisão visual manual em todas as resoluções.
