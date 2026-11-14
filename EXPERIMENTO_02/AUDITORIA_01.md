# Auditoria do Experimento 01

Os números anteriores são resultados reais da execução, mas não sustentam uma comparação científica controlada de generalização.

- A contagem incrementava antes de verificar o limite. O registro 2001 corresponde a 2000 candidatos testados e um candidato gerado mas não avaliado. A seleção de entradas ainda gerava outros candidatos fora desse contador.
- `experiments` contava comparações candidato/observação, não experimentos no oráculo. A tabela do relatório rotulava incorretamente essas comparações como consultas.
- `solve` recebia entradas de validação e consultava suas respostas. Não usava essas respostas para procurar outra expressão, mas a separação do avaliador era inexistente. `_hidden` era acessível no objeto Python. Não há leitura desse atributo pelo agente no código inspecionado.
- B adquiria habilidades também nos problemas inéditos, contaminando a comparação dos problemas seguintes. O armazenamento dependia de `best`, não de `success`; a alegação de que apenas soluções validadas entravam no banco era incorreta.
- T01 gerou `(1-(-2*x))` na posição 1139. O programa inseriu a árvore inteira e suas subárvores em SQLite. N01 gerou `(x*(1-(-2*x)))` na posição 197 para B: a árvore de T01 foi oferecida como componente inicial, combinada com x. Isso é reuso sintático programado. N01 foi explicitamente construído como composição de T01 com x, portanto o desenho favorecia transferência desse treino e não demonstra generalização ampla.
- A profundidade é recursiva sobre a árvore expandida. T01 tem profundidade 3 e N01 profundidade 4. Nenhuma macro opaca reduz artificialmente a profundidade. O gerador verifica <=4 nas composições; habilidades iniciais não são revalidadas, mas as habilidades produzidas nessa execução obedecem ao limite.
- A seleção escolhia todas as quatro entradas disponíveis: só mudava a ordem. Número de previsões distintas não é o cálculo de ganho esperado de informação.
- As 12 entradas no banco incluem primitivas e não representam 12 habilidades novas. A tabela de eventos vazia e o contador uses não atualizado impedem uma trilha histórica detalhada. A origem acima é uma reconstrução do fluxo determinístico e das expressões registradas, não um evento histórico instrumentado.
- A reabertura do banco mostrou persistência de dados; não foi um teste de desempenho após reinício completo. O orçamento foi aumentado após observar os primeiros resultados, e os desafios inéditos foram inspecionados durante a calibração. O conjunto tem apenas três alvos de avaliação.

O Experimento 02 mantém os arquivos anteriores intactos e corrige a separação funcional do avaliador, a contagem e a aquisição durante avaliações. Não há sandbox de segurança entre módulos: a independência é de fluxo de dados, com solve recebendo somente uma função de consulta, habilidades e configuração. Os fontes são auditáveis; não se alega proteção contra um agente malicioso.
