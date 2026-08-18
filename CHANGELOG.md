# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento semântico — regra nova que **bloqueia** sempre entra como minor, no mínimo.

## [1.0.1] — 2026-08-18

### Corrigido
- Plugin nao carregava (`failed to load`): `plugin.json` declarava `hooks: ./hooks/hooks.json`,
  mas esse caminho ja e carregado por convencao — o carregamento duplicado derruba o plugin.
  O campo `hooks` no manifesto serve apenas para arquivos ADICIONAIS de hook.
  **Nao use a v1.0.0**: ela instala mas nenhum hook entra em vigor.

## [1.0.0] — 2026-08-18

Primeira versão.

### Adicionado
- Hooks: `PreToolUse` (Bash e escrita), `PostToolUse` (format + lint), `Stop` (teste e diff),
  `SessionStart` (regras do time + stack detectado).
- 28 regras de comando bloqueado, 27 de confirmação, 18 de credencial, 30 de padrão inseguro,
  13 de caminho protegido.
- Detecção automática de stack: npm/pnpm/yarn/bun, Jest, Vitest, Playwright, Cypress, pytest,
  ruff, mypy, Go, Rust; monorepo e projeto poliglota.
- CLI `guardrails`: `check`, `scan`, `doctor`, `rules`, `init`, `on/off`, `install-git-hooks`.
- Customização em camadas por projeto em `.claude/guardrails/`, imune a atualizações.
- `userConfig.strictness`: `permissivo`, `padrao`, `estrito`.
- Templates: workflow de CI, configs de Playwright e Cypress, testes de exemplo.
