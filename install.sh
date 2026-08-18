#!/usr/bin/env bash
# Instalacao SEM plugin (fallback). O caminho recomendado e:
#   /plugin marketplace add Nero-o/claude-guardrails
#   /plugin install guardrails@claude-guardrails
#
# Use este script quando o cliente nao usa plugin, ou para CI/servidor:
#   ./install.sh                  -> instala no repo atual
#   ./install.sh --target /caminho
#   ./install.sh --with-git-hooks -> tambem instala o pre-commit anti-segredo
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""; GIT_HOOKS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --with-git-hooks) GIT_HOOKS=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "opcao desconhecida: $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "erro: python3 e necessario" >&2; exit 1; }

[ -n "$TARGET" ] || TARGET="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ROOT="$(cd "$TARGET" && pwd)"
DEST="$ROOT/.claude/guardrails-plugin"     # copia do plugin (substituida a cada update)
SETTINGS="$ROOT/.claude/settings.json"

echo "==> instalando guardrails (modo sem plugin)"
echo "    origem : $SRC"
echo "    destino: $DEST"
mkdir -p "$DEST" "$(dirname "$SETTINGS")"

for item in lib bin scripts rules templates hooks commands skills config.json GUARDRAILS.md README.md; do
  [ -e "$SRC/$item" ] || continue
  rm -rf "${DEST:?}/$item"
  cp -R "$SRC/$item" "$DEST/$item"
done
chmod +x "$DEST/bin/guardrails" "$DEST/scripts/guardrails-hook.sh" 2>/dev/null || true

python3 - "$SETTINGS" "$DEST/hooks/hooks.json" '${CLAUDE_PROJECT_DIR}/.claude/guardrails-plugin' <<'PYEOF'
import json, sys
from pathlib import Path
settings_path, hooks_path, base = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        bak = settings_path.with_suffix(".json.bak")
        bak.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"    settings.json invalido; backup em {bak.name}")
new_hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
for entries in new_hooks.values():
    for entry in entries:
        for h in entry.get("hooks", []):
            h["command"] = h["command"].replace("${CLAUDE_PLUGIN_ROOT}", base)
existing = settings.setdefault("hooks", {})
added = replaced = 0
for event, entries in new_hooks.items():
    bucket, kept = existing.setdefault(event, []), []
    for e in bucket:
        e["hooks"] = [h for h in e.get("hooks", []) if "guardrails-hook" not in json.dumps(h)]
        if e["hooks"]:
            kept.append(e)
    replaced += len(bucket) - len(kept)
    kept.extend(entries); existing[event] = kept; added += len(entries)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"    hooks registrados: {added} (substituidos: {replaced})")
PYEOF

# nesta modalidade nao ha injecao automatica das regras: importa no CLAUDE.md
MEM="$ROOT/CLAUDE.md"
if [ -f "$MEM" ] && grep -q "guardrails-plugin/GUARDRAILS.md" "$MEM"; then
  echo "    CLAUDE.md ja importa as regras"
else
  { echo ""; echo "## Guardrails"; echo ""; echo "@.claude/guardrails-plugin/GUARDRAILS.md"; } >> "$MEM"
  echo "    import adicionado em CLAUDE.md"
fi

grep -qxF ".claude/guardrails-plugin/.state/" "$ROOT/.gitignore" 2>/dev/null \
  || echo ".claude/guardrails-plugin/.state/" >> "$ROOT/.gitignore"

"$DEST/bin/guardrails" init || true
[ "$GIT_HOOKS" = "1" ] && "$DEST/bin/guardrails" install-git-hooks || true
echo ""
"$DEST/bin/guardrails" doctor || true
echo ""
echo "==> pronto. Reinicie a sessao do Claude Code."
echo "    Customize em .claude/guardrails/ (essa pasta sobrevive a atualizacoes)."
