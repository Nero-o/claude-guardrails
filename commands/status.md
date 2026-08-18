---
description: Mostra o que o guardrails aplica neste projeto e como ajustar regra ou falso positivo
---

Rode `guardrails doctor` e resuma para o usuario: nivel de rigor, stack detectado, comandos
que serao usados e o que falta no projeto.

Se o usuario mencionou uma regra especifica ou um bloqueio que sofreu em `$ARGUMENTS`, rode
tambem `guardrails rules --grep "<trecho>"` para achar o id.

Como resolver atrito (nesta ordem):

1. **Falso positivo de credencial** — adicione o padrao inocente em
   `.claude/guardrails/rules/secrets-allow.txt`.
2. **Regra que nao se aplica a este projeto** — pegue o id em `guardrails rules` e escreva em
   `.claude/guardrails/rules/disabled.txt`, com um comentario dizendo por que.
3. **Severidade incomoda** — ajuste `enforce.*` em `.claude/guardrails/config.json`
   (`deny` | `ask` | `warn` | `off`).
4. **Regra propria do time** — acrescente em `.claude/guardrails/rules/bash-deny.txt` no
   formato `regex ::: mensagem`.

Se `.claude/guardrails/` nao existir, rode `guardrails init` antes.

Nunca resolva atrito com `guardrails off` permanente, nem editando arquivos dentro do plugin:
eles sao substituidos no proximo update. `guardrails off` serve para uma sessao pontual, e o
usuario precisa saber que a rede inteira fica desligada enquanto isso.
