---
name: guardrails
description: Regras completas de seguranca, testes e desenvolvimento aplicadas por este projeto, e como customizar ou desativar uma regra. Use quando o guardrails bloquear uma acao, quando houver duvida sobre qual nivel de teste escrever (unitario, integracao ou e2e Playwright/Cypress), quando aparecer falso positivo de credencial, ou quando o usuario perguntar o que o guardrails verifica.
---

# Guardrails

Regras obrigatórias para qualquer alteração de código neste repositório.
Parte é aplicada automaticamente por hooks (bloqueia). Parte é sua responsabilidade
(o hook avisa, mas quem decide é você).

## 1. Antes de escrever código

- **Leia antes de editar.** Nunca altere um arquivo sem ter lido a região que vai mudar.
- **Siga o que já existe.** Convenção de nomes, formato de erro, camadas e estilo saem do
  código vizinho, não da sua preferência.
- **Não invente dependência, API ou comando.** Se não confirmou que existe no repositório
  (`package.json`, `requirements.txt`, imports), não use. Verifique em vez de supor.
- **Escopo é contrato.** Faça o que foi pedido. Refatoração não solicitada, renomeação em
  massa e "melhoria de passagem" viram outro pedido, não um brinde.
- **Mudança grande → plano antes.** Acima de ~5 arquivos ou qualquer alteração de contrato
  público (rota, schema, tipo exportado), descreva o plano e confirme antes de executar.

## 2. Segurança

Inegociável:

- **Segredo nunca entra no código.** Nem em teste, nem em comentário, nem "temporário".
  Leia de variável de ambiente e registre apenas o **nome** em `.env.example`.
- **Nunca leia `.env` real.** O conteúdo vai para o contexto e para o transcript. Use
  `.env.example` ou consulte só os nomes das variáveis.
- **Entrada do usuário é hostil até prova em contrário.** Valide no limite da aplicação
  (zod/pydantic/DTO), não no meio da regra de negócio.
- **SQL sempre parametrizado.** Nada de f-string, template literal ou concatenação.
- **Comando de sistema sem shell.** `execFile`/`spawn` com array de argumentos;
  `subprocess.run([...])` sem `shell=True`.
- **Autorização por requisição.** Autenticado ≠ autorizado. Todo endpoint que lê ou grava
  dado de alguém verifica se o solicitante pode acessar **aquele** registro.
- **Erro não vaza detalhe interno.** Stack trace, query e caminho de arquivo ficam no log
  do servidor; o cliente recebe mensagem genérica e um id de correlação.
- **Log não registra dado sensível.** Senha, token, cartão, CPF/CNPJ e afins ficam fora.
- **Dependência nova precisa de justificativa.** Prefira o que já está no projeto ou a
  biblioteca padrão. Ao adicionar, informe: por quê, tamanho e manutenção.

## 3. Testes

**Regra base: código de produção alterado exige teste tocado.** O hook de encerramento
cobra isso. As três saídas legítimas são: escrever o teste, apontar o teste existente que
já cobre o caminho (arquivo:linha), ou dizer ao usuário por que não é testável.

### Qual ferramenta para qual nível

| Nível | O que cobre | Ferramenta |
|---|---|---|
| Unitário | Lógica pura, regra de negócio, cálculo, redutor, helper | **Jest** ou **Vitest** (JS/TS), **pytest** (Python) |
| Integração | Contrato entre camadas: rota ↔ serviço ↔ banco, com I/O real ou dublê fiel | Mesmo runner unitário, suíte separada |
| E2E | O fluxo que o usuário percorre na interface, ponta a ponta | **Playwright** (preferido: multi-browser, auto-wait, trace) ou **Cypress** (se já for o padrão do repo) |

Não misture: E2E não é lugar para validar regra de cálculo — isso é unitário, roda em
milissegundos e aponta a linha do defeito. E2E existe para provar que as peças integradas
entregam o fluxo.

### O que todo teste precisa ter

- **Falha antes, passa depois.** Se o teste passa sem a sua mudança, ele não testa nada.
- **Um comportamento por teste**, com nome que descreve o comportamento — não o método.
- **Determinístico.** Sem depender de ordem de execução, relógio real, rede externa ou
  estado deixado por outro teste. Congele tempo e aleatoriedade.
- **Assertivo de verdade.** `expect(true).toBe(true)` e teste sem `expect` são dívida.
- **Sem `.only`.** O hook bloqueia: a suíte passaria verde rodando um teste só.
- **Teste pulado é dívida declarada.** `skip`/`xit` só com comentário dizendo o que
  destrava a volta.

### Regras específicas de E2E (Playwright / Cypress)

- **Seletor estável:** `data-testid` ou papel acessível (`getByRole`). Nunca classe CSS
  ou posição no DOM — quebram no primeiro ajuste de estilo.
- **Espera por condição, nunca por tempo.** `expect(locator).toBeVisible()` (Playwright)
  ou `cy.intercept` + `cy.wait('@alias')` (Cypress). `waitForTimeout`/`cy.wait(3000)`
  é fonte de flakiness.
- **Credencial de teste vem do ambiente**, nunca literal no arquivo.
- **Nunca aponte para produção.** `baseURL` sai de variável de ambiente com padrão local.
- **Cada teste monta e limpa seu próprio estado.** Nada de depender do que o anterior deixou.

## 4. Concluído significa

1. Roda: `guardrails check` (lint + typecheck + testes) passa.
2. Nenhum segredo novo: `guardrails scan` limpo.
3. Teste correspondente escrito e falhando sem a mudança.
4. Nenhum `.only`, `debugger`, `console.log` de depuração ou TODO órfão no diff.
5. O que foi decidido, assumido ou deixado de fora está dito ao usuário — não escondido.

## 5. Git

- Uma mudança lógica por commit; mensagem no imperativo, dizendo **por quê**.
- Nunca commite ou faça push sem o usuário pedir.
- Nunca `--no-verify`: se o hook reclamou, corrija o que ele apontou.
- Nunca force push em branch protegida.
- `git reset --hard`, `git clean -f` e `git checkout .` destroem trabalho não commitado —
  peça confirmação e prefira `git stash`.

## 6. Quando o guardrail atrapalha

Ele erra às vezes. O caminho é ajustar a regra, não burlá-la:

- Falso positivo de segredo → adicione o padrão em `guardrails/rules/secrets-allow.txt`.
- Regra que não se aplica ao projeto → edite `guardrails/rules/*.txt` ou afrouxe em
  `guardrails/config.json` (`enforce.*`: `deny` | `ask` | `warn` | `off`).
- Precisa de uma sessão sem hooks → `guardrails off` (e `guardrails on` depois).

Desligar o guardrail para fazer o que ele impediu, sem falar com o usuário, não é opção.
