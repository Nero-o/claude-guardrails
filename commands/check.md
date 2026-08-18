---
description: Roda o gate do guardrails (lint, typecheck, testes) e explica o resultado
---

Rode `guardrails check` e reporte o resultado. Se o usuario passou `$ARGUMENTS`, repasse
como flags (`--full` inclui build e e2e; `--only lint,unit` restringe as etapas).

Depois de rodar:

1. Se passou, diga em uma linha e liste o que foi verificado.
2. Se falhou, mostre a etapa que quebrou e a saida relevante — nao o log inteiro. Diagnostique
   a causa e proponha a correcao concreta. Se for algo que voce pode corrigir, corrija e rode
   de novo.
3. Se nenhuma etapa foi detectada, rode `guardrails doctor` e explique o que falta configurar
   no projeto (script de teste, lint, CI).

Nunca declare a tarefa concluida com o gate vermelho. Se o usuario pedir para seguir mesmo
assim, diga explicitamente o que ficou quebrado.
