# V216 — Núcleo no mundo SQM
Integração de exploração da V133–169 (busca de rotas no grafo observado) e armazenamento SQLite V170–215, com o servidor autoritativo original de ravendawn822-stack/autonomous-sqm-lab (branch main, world.py, GET /observation, POST /action). Não é a V5 Qwen/Codex, nem executa todos os mecanismos V215: a tarefa específica é navegação/descoberta. O agente nunca recebe o mapa de dimensões ocultas, código do servidor ou posição de obstáculos. O painel é separado, para observador, com grade original 50x50. O servidor original verificado não contém saída nem obstáculos internos; o teste automatizado utiliza um mundo experimental menor com obstáculo, mesmo contrato HTTP.
## Instalar
No Codespace onde ambos os projetos estão em /workspaces, pare a autonomia de V3/V4/V5 antes de iniciar qualquer movimento. Confirme que o mundo responde: `curl -fsS http://127.0.0.1:8082/observation`. Se estiver desligado, no diretório /workspaces/autonomous-sqm-lab execute `bash start-world.sh` uma única vez. Nunca execute dois controladores sobre o mesmo mundo simultaneamente.
```bash
git -C /workspaces/AGENTE_NUCLEO fetch origin nucleo-v12
git -C /workspaces/AGENTE_NUCLEO worktree add --detach /workspaces/nucleo-sqm-v216 FETCH_HEAD
cd /workspaces/nucleo-sqm-v216
PYTHONDONTWRITEBYTECODE=1 python3 NUCLEO_V216_SQM/panel.py --memory /workspaces/sqm-nucleo-v216.sqlite
```
Abra PORTS → 8007 → Open in Browser, mantendo PRIVATE. O painel não tem login próprio. Não é preciso ligar o servidor de modelo. Se a worktree já existir, reutilize o diretório existente em vez de recriá-la. Não alterar main nem os bancos históricos. O novo SQLite é isolado. Ctrl+C encerra o painel. Para outro mundo realmente distinto, use outro arquivo de memória e escopo.
## Controles
Escolha 100 ações e 0,35 s, iniciar. O objetivo padrão é explorar transições; opcionalmente informar X/Y para procurar uma coordenada. Cada ação tem observação própria, previsão (ou abstinência), motivo, resultado, registro persistente e eventual revisão. A busca usa BFS para uma fronteira conhecida ou rota para objetivo. Controle aleatório disponível, mas comparar exige memórias e estados iniciais separados; alternar modos no painel sem reset não é teste causal. Pausar/parar entre ações; cada requisição HTTP tem timeout de 3 s. Em erro de comunicação, não repete ação incerta automaticamente. A posição do observador é a última observada pelo agente. Limites 2500 movimentos/rodada e 10000 registros/escopo. A visualização não prevê ações futuras nem cria movimentos fictícios.
## Testes
`PYTHONDONTWRITEBYTECODE=1 python3 NUCLEO_V216_SQM/test_sqm.py -v`. Fixture HTTP 5x5 com obstáculo; verificar 24 células alcançáveis, 96 transições, retomada, planejamento e controle. Não equivale a execução no Codespace original nem prova de inteligência geral. Sem acesso a Codex/Qwen/serviços externos, sem novas dependências.
