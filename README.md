# Guardrails

Plugin do Claude Code que trava, em qualquer projeto, os três erros que mais custam caro:
**comando destrutivo**, **credencial no código** e **código entregue sem teste**.

Detecta o stack sozinho — npm/pnpm/yarn/bun, Jest, Vitest, Playwright, Cypress, pytest,
ruff, Go, Rust — e usa os comandos reais do seu repositório. Não precisa configurar nada
para começar.

## Instalação

```
/plugin marketplace add Nero-o/claude-guardrails
/plugin install guardrails@claude-guardrails
```

Para valer para o time inteiro (fica versionado no `.claude/settings.json` do projeto):

```bash
claude plugin install guardrails@claude-guardrails --scope project
```

No nível de rigor, escolha `permissivo`, `padrao` ou `estrito`:

```bash
claude plugin install guardrails@claude-guardrails --config strictness=estrito
```

Requisito único: `python3`. Sem `pip install`, sem dependência externa, sem chamada de rede.

Depois de instalar, rode `guardrails init` uma vez no projeto: cria `.claude/guardrails/`,
onde ficam suas customizações. Essa pasta é sua e **nunca é sobrescrita por atualizações**.

## O que ele faz

| Momento | Bloqueia | Pede confirmação | Avisa |
|---|---|---|---|
| Antes do comando | `rm -rf /`, `curl \| sh`, `--no-verify`, `DROP TABLE`, force push em branch protegida, `chmod 777`, token na linha | `git reset --hard`, `git clean -f`, ler `.env`, deploy, `sudo`, instalar global, banco remoto | |
| Antes de escrever arquivo | credencial hardcoded, `.env`/`.pem`/`.ssh`, `.only()` em teste | lockfile, workflow de CI, migration | SQL por f-string, `shell=True`, `innerHTML`, `verify=False`, CORS `*`, `cy.wait(3000)` |
| Depois de escrever | | | formata (prettier/ruff/gofmt) e roda o linter no arquivo, devolvendo o erro para correção imediata |
| Ao encerrar a resposta | código de produção alterado sem teste tocado; segredo, `.only` ou `debugger` no diff | | |
| Ao iniciar a sessão | | | injeta as regras do time e os comandos reais de lint/test/e2e do projeto |

Dois princípios de projeto: **falha aberta** em erro interno (bug do guardrail nunca trava
sua sessão) e **falha fechada** em risco detectado. Todo bloqueio de encerramento tem limite
por sessão — nunca vira loop.

## CLI

Instalado como plugin, `guardrails` fica direto no PATH:

```bash
guardrails check          # lint + typecheck + testes: o gate antes de concluir
guardrails check --full   # inclui build e e2e
guardrails scan           # procura credencial no working tree (--all = repo inteiro)
guardrails doctor         # o que está ligado, stack detectado, o que falta no projeto
guardrails rules          # lista as regras ativas e seus ids
guardrails init           # cria a pasta de customização do projeto
guardrails off / on       # desliga/religa nesta pasta
guardrails install-git-hooks   # pre-commit que barra segredo
```

## Customização

Tudo do cliente mora em `.claude/guardrails/`, versionado no **seu** repositório e imune a
atualizações do plugin:

```
.claude/guardrails/
├── config.json           severidade das verificações neste projeto
├── config.local.json     ajuste só da sua máquina (fora do git)
└── rules/
    ├── disabled.txt      ids de regras base que não se aplicam aqui
    ├── secrets-allow.txt padrões que não são segredo neste projeto
    ├── bash-deny.txt     regras próprias, mesmo formato do plugin
    └── CORE.md           instruções extras injetadas no início da sessão
```

**Adicionar uma regra** — um regex por linha, no formato `regex ::: mensagem`:

```
(?i)\bdeploy-manual\.sh\b ::: Deploy manual foi proibido: use a esteira
```

**Desligar uma regra base** — pegue o id em `guardrails rules` e escreva em `disabled.txt`:

```
6031b4  # force push liberado: o time trabalha com rebase em branch própria
```

**Mudar severidade** — em `config.json`, cada verificação aceita `deny`, `ask`, `warn` ou `off`:

```json
{ "enforce": { "code_smells": "off", "stop_requires_tests": "deny" },
  "protected_branches": ["main", "homolog"] }
```

Regra com regex inválido é denunciada por `guardrails doctor` — nunca some em silêncio.

## Política de testes

O guardrail cobra teste, mas quem escolhe o nível é você:

| Nível | Cobre | Ferramenta |
|---|---|---|
| Unitário | Lógica pura, regra de negócio, cálculo | Jest, Vitest, pytest |
| Integração | Contrato entre camadas: rota ↔ serviço ↔ banco | Mesmo runner, suíte separada |
| E2E | O fluxo que o usuário percorre na tela | Playwright (preferido) ou Cypress |

Regra de cálculo não se valida em E2E. Templates prontos em `templates/`: configs de
Playwright e Cypress já com seletor `data-testid`, espera por condição, credencial vinda do
ambiente e guarda contra apontar para produção — além de um workflow de CI que roda o mesmo
gate do hook local.

Detalhe completo das regras: skill `guardrails` (ou `GUARDRAILS.md`).

## Atualização

```bash
claude plugin update guardrails@claude-guardrails
```

Suas regras, severidades e desativações continuam valendo. O que muda são as regras base e o
motor. Veja `CHANGELOG.md` antes de subir de versão major.

## Falso positivo

É o preço de uma rede que pega coisa de verdade. O caminho é ajustar, nunca burlar:
`guardrails rules` para achar o id, `disabled.txt` para desligar aquela regra,
`secrets-allow.txt` para o padrão inocente, `config.json` para a severidade. `guardrails off`
existe para uma sessão específica — não para esconder o que o guardrail apontou.
