# Migração preservativa para GitHub/Codespaces

## Preservação e verificação

Fonte local: C:\Users\Administrator\Desktop\AGENTE_NUCLEO. A cópia de migração está em C:\Users\Administrator\Documents\AGENTE_NUCLEO_GITHUB. O repositório privado usa a conta ravendawn822-stack, confirmada pelo usuário. Nenhum arquivo histórico foi reorganizado ou editado; EXPERIMENTO_01 é o conjunto de arquivos da raiz, não uma subpasta.

inventario_original.json registra tamanho e SHA-256 dos 178 arquivos originais (55.889.872 bytes). Todos estão incluídos, inclusive caches, SQLite, WAL/SHM, pilotos, resultados negativos, sessões e checkpoints. .gitattributes desativa conversão de finais de linha. sqlite_verificacao.json documenta 36 bancos e suas tabelas/contagens; sqlite_consistentes contém backups lógicos standalone adicionais. Os bytes originais permanecem nos caminhos originais. A verificação SQLite ocorreu em cópias temporárias com seus WAL/SHM, nunca abrindo os originais para escrita. A origem foi novamente comparada ao inventário após a preparação.

seguranca.json registra uma varredura heurística de texto e binários por tokens, chaves privadas, atribuições de credenciais, emails e caminhos. Não foram encontrados padrões de credenciais; foram encontrados caminhos locais em bytecode. Isso não é prova absoluta de ausência de informação sensível. O acesso deve permanecer privado.

Execute `python3 MIGRACAO/verify_integrity.py` para conferir originais e snapshots. Use `--all` para conferir também a infraestrutura adicionada contra conteudo_enviado.json. A verificação pós-clone é registrada separadamente. A cópia GitHub não é a única cópia: a área de trabalho permanece completa e intacta.

## Abrir no Codespaces

1. Entre na conta ravendawn822-stack e abra o repositório privado AGENTE_NUCLEO.
2. Selecione Code → Codespaces → Create codespace on main. Prefira a menor máquina disponível inicialmente e confira franquia/orçamento da conta.
3. Aguarde a construção de .devcontainer. Usa Ubuntu 24.04, Python do sistema, SQLite, Tkinter e desktop-lite/noVNC. Não instala dependências de IA.
4. O postCreateCommand executa checagem de hashes, parsing Python 3.12, integridade dos snapshots, os cinco testes unitários em cópia temporária e smoke test Tkinter. Nenhum runner científico é iniciado.
5. Abra a aba Ports e a porta 6080. **Mantenha a visibilidade Private**. O desktop interno dispensa senha própria e depende da proteção de acesso do Codespaces; não publique essa porta nem encaminhe 5901.
6. No terminal, execute `python3 MIGRACAO/launch_panel.py --panel 02`. A janela Tkinter aparecerá no desktop da porta 6080. O lançador copia a árvore histórica para WORKSPACES_EXECUCAO e usa backups standalone apenas nessa cópia. Novos diagnósticos ficam nessa pasta, não nas evidências originais. Use --panel 01 para a versão anterior.
7. Ao terminar, pare o Codespace. Parar reduz cobrança de computação, mas armazenamento continua existindo. Antes de excluir um Codespace, preserve mudanças e sessões novas deliberadamente no Git ou em backup.

O lançador do painel cria uma cópia completa por execução; preserve resultados úteis e gerencie essas cópias conscientemente. WORKSPACES_EXECUCAO está no .gitignore para não publicar automaticamente resultados temporários. Não execute runners históricos diretamente na árvore versionada: alguns sobrescrevem bancos e relatórios. Use uma cópia de trabalho para reexecuções autorizadas.

## Compatibilidade e limites da validação

As fontes históricas usam Python padrão e pathlib. .cmd permanece como lançador Windows; o equivalente Linux adicionado é launch_panel.py. O ambiente Linux usa Python 3.12 do Ubuntu, enquanto o bytecode histórico é CPython 3.13 Windows: bytecode é preservado como evidência, não requisito de execução. PYTHONDONTWRITEBYTECODE evita alterar caches históricos.

Os manifestos de experimentos antigos contêm chaves de caminho com separadores Windows e listas de arquivos de momentos anteriores. Seus verificadores/runners não são validadores da árvore migrada completa e podem acusar divergência em Linux ou após adições. Os arquivos não foram corrigidos retroativamente: a verificação da migração usa caminhos POSIX relativos, hashes dos bytes e snapshots consistentes. Não desative verificações de preservação silenciosamente para rodar um experimento antigo.

No computador local não foram encontrados Docker ou WSL. Após autorização explícita, foi criado um Codespace temporário de dois núcleos. O devcontainer foi construído e a checagem passou em Linux/Python 3.12.3: 27 fontes parseadas, cinco testes unitários, smoke test Tkinter, 36 snapshots íntegros e hashes preservados antes/depois. O repositório remoto ficou sem alterações de trabalho. O Codespace temporário foi excluído após o teste, com confirmação HTTP 404. Os resultados estão em verificacao_linux.json. Nenhum experimento foi iniciado nesse ambiente.

## Custos informados

Maior arquivo original: 19.333.120 bytes, abaixo de 50/100 MiB. Esta entrega usa Git normal, sem Git LFS ou compra de armazenamento. Crescimento futuro pode exigir outra estratégia. GitHub alerta acima de 50 MiB e bloqueia arquivos acima de 100 MiB: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github

Codespaces tem franquia por conta. A tabela oficial consultada informa Free pessoal: 120 core-hours e 15 GB-mês; Pro: 180 core-hours e 20 GB-mês. Uma hora em máquina de dois núcleos consome duas core-hours. Fora da franquia, dois núcleos custam US$ 0,18/h e armazenamento US$ 0,07/GB-mês; imagens customizadas também podem contar no armazenamento. A franquia restante desta conta não foi determinada e não se promete custo zero. Consulte o orçamento e uso antes de criar. Fonte: https://docs.github.com/en/billing/concepts/product-billing/github-codespaces

## Continuidade com Codex

Leia AGENTS.md, CONTEXTO_PROJETO.md e os relatórios auditados. A migração não instala Codex, não fornece credenciais e não conecta professora. A autenticação do cliente que será usado no Codespaces é independente da preservação do repositório. O contexto e as instruções do projeto estão versionados para permitir continuidade por outro ambiente/agente.
