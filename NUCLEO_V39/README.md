# NUCLEO V39 — correção guiada por contraexemplos

V39 usa exatamente uma chamada Codex para corrigir a primeira proposta rejeitada da V38. A IA recebe somente os exemplos públicos e contraexemplos derivados deles. Os 24 exemplos cegos e as 24 tarefas finais são gerados localmente e nunca são enviados ao modelo.

## Atualizar o clone existente

```bash
cd /workspaces/AGENTE_NUCLEO
git pull --ff-only origin nucleo-v12
```

## Testes sem IA

```bash
python3 NUCLEO_V39/feedback_learning.py --self-test
```

## Preparar o pedido de reparo

A pasta V38 deve conter `request_1.json`, `response_1.json` e `attempt_1.json`.

```bash
python3 NUCLEO_V39/feedback_learning.py prepare \
  --v38-dir /tmp/nucleo-v38-pilot \
  --dir /tmp/nucleo-v39-pilot
```

Esse comando não chama o Codex.

## Fazer uma única chamada de reparo

```bash
python3 NUCLEO_V39/feedback_learning.py repair --dir /tmp/nucleo-v39-pilot --index 1
```

Modelo solicitado: `gpt-6-luna`, raciocínio `low`. O script não tenta novamente e não troca de modelo. A autenticação ChatGPT do Codex CLI é reutilizada. A execução usa diretório temporário e sandbox read-only. Isso limita escrita, mas não garante isolamento absoluto contra leituras de outros caminhos acessíveis ao Codex. Execute somente em Codespace sem outros dados sensíveis acessíveis.

## Avaliar sem IA

```bash
python3 NUCLEO_V39/feedback_learning.py evaluate --dir /tmp/nucleo-v39-pilot
```

A avaliação compara baseline, primeira proposta não verificada, reparo aprovado por 24 testes cegos, professor enumerativo e referência ideal. A referência ideal é apenas um teto comparativo, não aprendizagem do agente.

Não compartilhe tokens, arquivos de autenticação, variáveis de ambiente ou logs completos do Codex.
