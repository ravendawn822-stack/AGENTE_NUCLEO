# Protocolo e decisões matemáticas

## Escopo e grade

Experimento de seleção de conhecimento em gramática simbólica, sem professora, rede ou modelo de linguagem. Não é um agente de programação geral. Todos os arquivos anteriores são preservados por SHA-256. A grade principal usa três sementes (104729,130363,155921), 24 treinos e 24 funções inéditas por semente, checkpoints 0/8/16/24, capacidades FIFO 8/24, cinco estratégias, limite de 800 candidatos ou 12 ms de busca. C, D e ORDER escolhem até quatro habilidades. B usa toda a memória ativa; A nenhuma. As constantes -2,-1,0,1,2, variável x e operações +,-,* são comuns. Profundidade expandida máxima 4 (15 nós); macros não ocultam complexidade.

Uma grade inicial maior foi executada parcialmente como piloto de recursos. Em 1.238 episódios mediu média de 0,171585 s de busca. A grade foi reduzida por esse custo, antes de comparar taxas; o piloto está integralmente preservado em pilot_resource, separado dos resultados principais. Correções de desenvolvimento na expansão condicional foram feitas antes de executá-la. Houve interrupções para testar retomada e corrigir a ablação: a seleção anterior à atualização da memória deve ser usada para remover exatamente uma habilidade. Ablações finais são rechecadas separadamente; registros preliminares são preservados.

## Consulta e relevância

As consultas iniciais são x=-2,-1,0,1,2 para todos. São fixas para tornar a seleção comparável; este experimento não testa aprendizado da escolha de entradas. Nenhuma expressão oculta, categoria secreta ou resposta reservada entra na seleção.

Para observações y, define-se q=1+max|y|; d são primeiras diferenças e dd segundas diferenças. O vetor é [média(d)/q, média(|dd|)/(2q), soma de dois pares |y_i-y_(4-i)|/(4q), soma dos dois pares |y_i+y_(4-i)|/(4q), y_2/q]. Captura crescimento, curvatura, simetria par/ímpar e deslocamento. R=max(0,min(1,1-distância L1 entre vetores/10)). A previsão da habilidade é calculada nas mesmas entradas observadas. Não é uma prova de relevância; é uma hipótese de projeto explícita.

Contexto = vetor quantizado por round(2*f_i). Essas fronteiras são fixadas antes da avaliação, não rótulos manuais de habilidades boas. P=(sucessos+1)/(tentativas+2), E=1/sqrt(1+tentativas). Tentativas contam construções que efetivamente usaram a habilidade; acertos contam validações adicionais de treino dessas construções. Seleção sem construção é contada separadamente e não recebe crédito de sucesso. Ausência de experiência implica P=0,5, E=1.

K=0,5*min(1,nós/15)+0,5*min(1,custo histórico de operações/75); sem medição o segundo componente é 0,5. Custo de operações é nós expandidos vezes consultas de sondagem, média histórica, uma aproximação determinística (condicionais podem executar apenas um ramo). Tempo real dessas sondagens é registrado separadamente. A escolha evita rankings instáveis por microssegundos de ruído. Todos P,R,E,K e S ficam entre 0 e 1. Pesos principais [0,45,0,35,0,20]; sensibilidades [0,60,0,20,0,20] e [0,20,0,60,0,20] são avaliadas em outra semente com 20 treinos e 20 problemas de desenvolvimento. Não se escolhem pesos pela avaliação final.

## Conhecimento e evidência

B conserva o princípio do Experimento 02 (reutilizar toda a memória ativa, sem ranqueamento), mas não reproduz seus resultados numericamente: agora a promoção exige validação adicional, apenas raízes validadas entram como habilidades e há limite FIFO. Essas regras são comuns a B/C/D/ORDER. Subárvores continuam sendo entidades de composição, sem promoção automática a habilidades validadas. Taxas entre experimentos não são diretamente comparáveis.

Hipótese = expressão produzida. Candidata = consistente com as consultas iniciais. Validada = passa também por quatro consultas adicionais de treinamento (-6,6,-8,8). Refutada = uma previsão contradita no problema/contexto correspondente. A validade não é universal. O estado de uma expressão pode diferir entre problemas. Componentes são entidades aritméticas; não recebem automaticamente validade para a função alvo. Somente raízes operacionais validadas são promovidas a habilidades reutilizáveis. Cada uma tem hash identificador, origem, composição, evidências, contagens e estatísticas por contexto. Snapshots preservam estados antigos, inclusive habilidades removidas da memória ativa.

O gerador propaga os identificadores das habilidades empregadas na derivação de cada candidato. Isso define construção. Presença sintática procura árvores idênticas na solução expandida, podendo divergir da derivação efetiva. Nenhuma delas é causalidade. Ablações removem uma habilidade usada e repetem a busca sob orçamento idêntico e o restante da seleção fixo. São feitas no treino de C, no regime de candidatos, em checkpoints múltiplos de oito quando existe habilidade usada. A evidência causal é local à ordem de busca, contexto, seleção e limite. O custo suplementar não é ocultado no orçamento principal, e não há ajuste de pesos por ablação.

## Avaliação, orçamentos e retomada

A avaliação consulta o alvo para as observações, mas nunca chama learn. O avaliador verifica 34 entradas externas (±10..±26) após a busca. Alvos e candidatos são polinômios de grau máximo 8; nove igualdades distintas seriam suficientes dentro desse domínio. A bateria inédita é a mesma em cada checkpoint; são medidas pareadas, não novos problemas independentes a cada checkpoint. O controle é de fluxo de dados, não um sandbox contra introspecção maliciosa.

O orçamento de candidatos conta cada hipótese testada. Sondagens de seleção têm custo adicional registrado; igualdade de candidatos não implica igualdade de operações. O limite temporal inclui consulta, seleção, recuperação, sondagens e busca; é cooperativo entre candidatos, com teto de segurança 5.000 candidatos. Preparação e um candidato podem exceder o prazo. Tempo total por episódio inclui atualização de treino e eventual ablação; validação científica externa é registrada separadamente. Tracemalloc mede pico incremental Python, não RSS. Instrumentação resumida é comum a todos. Não há rastreamento detalhado ou interface no processo científico.

SQLite confirma episódio e snapshot na mesma transação. `python -u run.py` retoma a mesma configuração, saltando episódios já confirmados e restaurando snapshots. Ctrl+C encerra; não apaga resultados. O processo foi retomado durante desenvolvimento. results/config.json fixa a configuração; mudar essa configuração exige uma nova pasta de execução. Exportação raw.jsonl ocorre após conclusão; antes disso os dados completos estão no SQLite. Arquivos de configuração e suítes são preservados.

## Referência e expansão

Interpolação de Lagrange com Fraction, nove amostras e teste nos mesmos pontos externos é uma referência matemática forte e separada. Pressupõe polinômio de grau ≤8, não possui o mesmo orçamento de consultas ou objetivo de descobrir árvores reutilizáveis. Seu algoritmo não é oferecido ao agente.

A expansão é executada depois da avaliação aritmética. Introduz variáveis x,y, booleanos, <, == e if. Busca tipada enumera predicados e ramos em ordem diagonal, com limite 6.000 candidatos, profundidade 4 e tamanho 31. Há três sementes com 30 treinos e 30 avaliações, comparando memória vazia com a memória C/capacidade24/candidatos após treino aritmético. Ambos podem aprender durante os 30 treinos. A seleção usa as mesmas entradas observadas, mas as diferenças na sequência multivariada já não representam derivadas univariadas; isso limita a interpretação da relevância. A validação externa cobre uma grade finita 5x5 e não prova equivalência global de programas condicionais. Alvos são sorteados antes da busca, sem escolha por desempenho.

## Limitações previstas

Conjuntos pequenos, poucos seeds, uma gramática e uma ordenação de busca. O método de retenção FIFO pode remover conhecimentos úteis. Seleção por associação pode ser inferior à aleatória ou por aquisição. Estes resultados devem ser conservados. O custo temporal depende do hardware e de processos concorrentes; não há controle de frequência de CPU. Python padrão é compatível com Windows/Tkinter e não usa instruções especiais; não se alega benchmark físico em Pentium E2140.
