---
description: Diagnostico, gate de qualidade e customizacao do guardrails
---

Execute a acao pedida pelo usuario em `$ARGUMENTS`. Se vier vazio, rode `guardrails doctor`
e resuma o resultado.

Acoes disponiveis (a CLI `guardrails` esta no PATH desta sessao):

| Pedido do usuario | Comando |
|---|---|
| diagnostico, status, "o que ta ligado" | `guardrails doctor` |
| rodar o gate antes de concluir | `guardrails check` (ou `--full` com build e e2e) |
| procurar segredo | `guardrails scan` (`--all` para o repo inteiro) |
| listar regras e seus ids | `guardrails rules` |
| preparar customizacao do projeto | `guardrails init` |
| desligar/religar nesta pasta | `guardrails off` / `guardrails on` |
| barrar segredo no commit | `guardrails install-git-hooks` |

Depois de rodar, explique o resultado em portugues e diga o proximo passo concreto.

Se o usuario reclamar de falso positivo:
1. `guardrails rules` para achar o id da regra que disparou;
2. desative so aquela regra escrevendo o id em `.claude/guardrails/rules/disabled.txt`,
   ou adicione o padrao inocente em `.claude/guardrails/rules/secrets-allow.txt`;
3. se for a severidade que incomoda, ajuste `enforce.*` em `.claude/guardrails/config.json`.

Nunca resolva falso positivo com `guardrails off` permanente nem editando os arquivos dentro
do plugin — eles sao substituidos no proximo update.
