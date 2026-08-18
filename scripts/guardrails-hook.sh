#!/usr/bin/env bash
# Dispatcher dos hooks. Falha aberta: sem python3, a sessao segue normalmente.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python || true)"
[ -z "${PY}" ] && exit 0
exec "${PY}" "${DIR}/../lib/guardrails.py" "${1:-}"
