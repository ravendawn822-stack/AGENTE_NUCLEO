# Migração concluída — AGENTE_NUCLEO

Repositório: https://github.com/ravendawn822-stack/AGENTE_NUCLEO — privado, branch main. Conta ravendawn822-stack confirmada pelo usuário. Git 2.56.0 e GitHub CLI 2.102.0 já estavam instalados; a conta correta estava ativa, portanto não foi necessário trocar ou renovar autenticação. A autenticação do CLI é por usuário, não uma propriedade de C:\otc-mobile; esse diretório não era um repositório Git.

## Preservação

Foram inventariados e transferidos os 178 arquivos originais, totalizando 55.889.872 bytes. O maior arquivo original tem 19.333.120 bytes. Nenhum ultrapassou 50 ou 100 MiB; Git LFS não foi necessário nem contratado. Caches e arquivos auxiliares também foram preservados, sem filtros que descartem artefatos científicos.

O Experimento 01 continua na raiz, conforme a organização original. EXPERIMENTO_02, EXPERIMENTO_03, PAINEL_01 e PAINEL_02 mantêm os caminhos e conteúdos originais. Nenhum mecanismo do agente foi modificado. A pasta da área de trabalho continua intacta. Uma cópia Git local independente está em C:\Users\Administrator\Documents\AGENTE_NUCLEO_GITHUB; outra cópia baixada do GitHub para verificação está em C:\Users\Administrator\Documents\AGENTE_NUCLEO_GITHUB_VERIFICACAO.

## SQLite e segurança

36 bancos passaram por integrity_check em cópias temporárias com WAL/SHM quando existentes. Foram produzidos backups standalone adicionais e testados novamente. Os bancos e WAL/SHM originais seguem preservados byte a byte; não houve checkpoint ou atualização sobre os originais.

A varredura heurística de todos os arquivos, inclusive binários, não encontrou os padrões pesquisados de tokens e chaves privadas. Encontrou caminhos locais em bytecode Python, mantidos pela exigência de preservação. As credenciais do GitHub CLI ficam fora do projeto e não foram copiadas. O scanner não garante ausência absoluta de qualquer informação sensível. O repositório é privado.

## Linux e Codespaces

Foi adicionada configuração devcontainer com Ubuntu 24.04, Python, SQLite, Tkinter, desktop-lite e SSH. Os .cmd Windows permanecem inalterados. O lançador multiplataforma adicional executa os painéis em cópias isoladas, sem sobrescrever bancos históricos. AGENTS.md e CONTEXTO_PROJETO.md permitem continuidade com o contexto científico e os cuidados de preservação.

Após autorização para eventual consumo de franquia/cobrança, foi criado o Codespace validacao-temporaria-agente-xr44jw9jx4g5h9v7r, máquina basicLinux32gb (dois núcleos). A validação passou em Linux 6.8/Python 3.12.3: hashes dos 178 originais e 36 backups, integridade SQLite, parsing de 27 fontes, cinco testes unitários em diretório temporário e criação/encerramento Tkinter. Nenhum runner científico foi iniciado. A árvore Git remota estava limpa antes da exclusão. O Codespace foi excluído e a API confirmou que não existe mais. Nenhum outro Codespace foi alterado.

O teste valida ambiente, fontes, núcleo por testes e Tkinter; não reexecuta os experimentos completos nem equivale a uma inspeção visual manual de todas as telas. Os verificadores históricos de preservação possuem separadores/listas antigos; a migração oferece seu próprio verificador POSIX sem reescrever as evidências antigas.

## Integridade do envio

Foi realizado um clone HTTPS novo do repositório privado, não uma cópia local. Todos os 231 arquivos do envio inicial foram comparados por SHA-256, inclusive infraestrutura e backups; os 178 arquivos da origem foram novamente conferidos. verificacao_pos_clone.json documenta esse commit inicial validado. Ao final, a mesma cópia é atualizada para o commit final e o manifesto completo é conferido novamente, incluindo os relatórios acrescentados após o teste Linux. O comprovante final externo à árvore evita autorreferência de hash/commit.

Arquivos de prova: inventario_original.json, sqlite_verificacao.json, seguranca.json, verificacao_local.json, verificacao_linux.json, verificacao_pos_clone.json e conteudo_enviado.json. Verificação reproduzível: `python3 MIGRACAO/verify_integrity.py --all` após um clone limpo.

## Custos e continuidade

Não foi utilizado LFS nem alterado plano/orçamento de cobrança. O Codespace temporário autorizado pode ter consumido franquia ou gerado cobrança proporcional; a migração não conhece o saldo ou a fatura real. Ele foi excluído para não manter armazenamento ativo. Consulte a página de billing do GitHub para os valores efetivos.

Para continuar: abra o repositório → Code → Codespaces → Create codespace on main; consulte a franquia antes. Para o painel: mantenha a porta 6080 privada e execute `python3 MIGRACAO/launch_panel.py --panel 02`. Leia CONTEXTO_PROJETO.md e AGENTS.md antes de novos trabalhos. Experimento 04 e integração com professora não foram iniciados.
