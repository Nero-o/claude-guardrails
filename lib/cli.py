#!/usr/bin/env python3
"""CLI do guardrails: check, scan, doctor, detect, on/off, install-git-hooks."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import guardrails as G  # noqa: E402
import stack as stackmod  # noqa: E402

BOLD, RED, GRN, YEL, DIM, RST = "\033[1m", "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    BOLD = RED = GRN = YEL = DIM = RST = ""


def hr(t=""):
    print(f"{DIM}{'-' * 66}{RST}" + (f" {t}" if t else ""))


# ------------------------------------------------------------------ scan
def cmd_scan(args, root: Path, cfg: dict) -> int:
    rules = G.load_rules("secrets.txt")
    allow = G.load_rules("secrets-allow.txt")
    smells = G.load_rules("code-smells.txt")

    if args.all:
        tracked = (G.git(root, ["ls-files"]) or "").split()
        files = [f for f in tracked if not G.is_ignored(f, cfg)]
    elif args.staged:
        files = [f for f in (G.git(root, ["diff", "--cached", "--name-only"]) or "").split()
                 if not G.is_ignored(f, cfg)]
    else:
        files = [f for f in G.changed_files(root) if not G.is_ignored(f, cfg)]

    cap = int(cfg.get("limits", {}).get("max_file_scan_bytes", 2000000))
    n_secret = n_smell = 0
    for f in files[: int(cfg.get("limits", {}).get("max_diff_files_scanned", 400))]:
        p = root / f
        if not p.is_file():
            continue
        try:
            if p.stat().st_size > cap:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        hits = G.scan_text(text, rules, allow, limit=10)
        if hits:
            n_secret += len(hits)
            print(f"{RED}SEGREDO{RST} {f}")
            for ln, msg, snip in hits:
                print(f"   {ln}: {msg}\n     {DIM}{snip}{RST}")
        if args.smells:
            sh = G.scan_text(text, smells, limit=10)
            if sh:
                n_smell += len(sh)
                print(f"{YEL}RISCO{RST}   {f}")
                for ln, msg, snip in sh:
                    print(f"   {ln}: {msg}\n     {DIM}{snip}{RST}")

    scope = "todo o repo" if args.all else ("staged" if args.staged else "working tree")
    print()
    if n_secret:
        print(f"{RED}{n_secret} possivel(is) credencial(is){RST} em {len(files)} arquivo(s) ({scope}).")
        print(f"{DIM}Falso positivo? adicione o padrao em guardrails/rules/secrets-allow.txt{RST}")
        return 1
    print(f"{GRN}Nenhuma credencial detectada{RST} em {len(files)} arquivo(s) ({scope})."
          + (f" {YEL}{n_smell} aviso(s) de risco.{RST}" if n_smell else ""))
    return 0


# ------------------------------------------------------------------ check
def _run(cmd: str, root: Path, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return 124, f"timeout apos {timeout}s"
    except Exception as e:
        return 1, repr(e)


def cmd_check(args, root: Path, cfg: dict) -> int:
    info = stackmod.load(root, G.state_dir(root), force=args.refresh)
    cmds = info.get("commands", {})
    stages = ["lint", "typecheck", "unit"]
    if args.full:
        stages += ["build", "e2e"]
    if args.only:
        stages = [s for s in stages if s in args.only.split(",")]

    results = []
    t0 = time.time()

    hr()
    print(f"{BOLD}guardrails check{RST}  {DIM}{root}{RST}")
    hr()

    rc_scan = cmd_scan(argparse.Namespace(all=False, staged=False, smells=False), root, cfg)
    results.append(("scan-segredos", rc_scan, ""))

    for stage in stages:
        for cmd in cmds.get(stage, []):
            print(f"\n{BOLD}▸ {stage}{RST} {DIM}$ {cmd}{RST}")
            timeout = 1800 if stage in ("e2e", "build") else 600
            rc, out = _run(cmd, root, timeout)
            tail = "\n".join(out.strip().splitlines()[-25:])
            if rc == 0:
                print(f"{GRN}  ok{RST}")
            else:
                print(f"{RED}  falhou (exit {rc}){RST}\n{DIM}{tail}{RST}")
            results.append((f"{stage}: {cmd}", rc, tail))

    hr()
    failed = [r for r in results if r[1] != 0]
    dur = int(time.time() - t0)
    for name, rc, _ in results:
        print(f"  {(GRN + 'PASS' + RST) if rc == 0 else (RED + 'FAIL' + RST)}  {name}")
    hr()
    if not results[1:]:
        print(f"{YEL}Nenhum comando de teste/lint detectado.{RST} Rode 'guardrails doctor' "
              f"e adicione scripts no package.json ou pyproject.")
    print(f"{BOLD}{'FALHOU' if failed else 'OK'}{RST} — {len(results) - len(failed)}/{len(results)} etapas em {dur}s")
    return 1 if failed else 0


# ------------------------------------------------------------------ doctor
def cmd_doctor(args, root: Path, cfg: dict) -> int:
    info = stackmod.load(root, G.state_dir(root), force=True)
    hr()
    print(f"{BOLD}guardrails doctor{RST}")
    hr()
    ov = G.overlay_dir(root)
    print(f"  raiz do projeto : {root}")
    print(f"  base (plugin)   : {G.BASE}")
    print(f"  overlay projeto : {ov}" + ("" if ov.is_dir() else f"  {DIM}(ausente — rode: guardrails init){RST}"))
    lvl = os.environ.get("CLAUDE_PLUGIN_OPTION_STRICTNESS") or "padrao"
    print(f"  rigor           : {lvl}")
    print(f"  estado          : {G.state_dir(root)}")
    print(f"  ativo           : {(RED + 'NAO (desligado)' + RST) if G.disabled(root) else GRN + 'sim' + RST}")
    print()
    for f in ("bash-deny.txt", "bash-ask.txt", "secrets.txt", "secrets-generic.txt",
              "secrets-allow.txt", "code-smells.txt"):
        rs = G.load_rules(f)
        own = sum(1 for r in rs if r.source == "projeto")
        print(f"  regras {f:<22} {len(rs):>3}" + (f"  ({own} do projeto)" if own else ""))
    print(f"  regras {'paths.txt':<22} {len(G.load_path_rules()):>3}")
    if G.BAD_RULES:
        print()
        print(f"  {RED}REGRAS INVALIDAS (ignoradas silenciosamente ate corrigir):{RST}")
        for fname, ln, pat, err in G.BAD_RULES:
            print(f"    {fname}:{ln}  {err}\n      {DIM}{pat}{RST}")
    print()
    print(f"  gerenciador     : {info.get('package_manager') or '-'}")
    print(f"  frameworks JS   : {', '.join(info.get('js_frameworks') or []) or '-'}")
    py = info.get("python")
    print(f"  python          : {(py or {}).get('test') or '-'} | lint={(py or {}).get('lint') or '-'}")
    print(f"  CI              : {', '.join(info.get('ci') or []) or '-'}")
    print()
    print(f"  {BOLD}comandos detectados{RST}")
    cmds = info.get("commands", {})
    if not cmds:
        print(f"    {YEL}nenhum{RST}")
    for k, v in cmds.items():
        for c in v:
            print(f"    {k:<10} {c}")
    print()
    fw = set(info.get("js_frameworks") or [])
    unit_fw = fw & {"jest", "vitest", "mocha"}
    e2e_fw = fw & {"playwright", "cypress"}
    missing = []
    if not cmds.get("unit"):
        missing.append(
            f"{'/'.join(sorted(unit_fw))} instalado, mas sem script de teste no package.json"
            if unit_fw else "nenhum runner de teste unitario (jest/vitest/pytest)")
    if not cmds.get("e2e"):
        missing.append(
            f"{'/'.join(sorted(e2e_fw))} instalado, mas sem script e2e no package.json"
            if e2e_fw else "nenhum runner e2e (playwright/cypress)")
    if not cmds.get("lint"):
        missing.append("nenhum lint")
    if not info.get("ci"):
        missing.append("nenhum workflow de CI")
    if not G.overlay_dir(root).is_dir():
        missing.append("customizacao do projeto nao iniciada (guardrails init)")
    for m in missing:
        print(f"  {YEL}faltando{RST}: {m}")
    if missing:
        print(f"\n  {DIM}templates prontos em {G.BASE / 'templates'}{RST}")
    return 0


# ------------------------------------------------------------------ misc
def cmd_detect(args, root: Path, cfg: dict) -> int:
    info = stackmod.load(root, G.state_dir(root), force=True)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_toggle(args, root: Path, cfg: dict) -> int:
    flag = G.state_dir(root) / "disabled"
    if args.cmd == "off":
        flag.write_text(str(int(time.time())), encoding="utf-8")
        print(f"{YEL}guardrails DESLIGADO{RST} para {root}. Religue com: guardrails on")
    else:
        flag.unlink(missing_ok=True)
        print(f"{GRN}guardrails ligado{RST} para {root}")
    return 0


GIT_HOOK = """#!/usr/bin/env bash
# instalado por guardrails install-git-hooks
set -uo pipefail
GR="__GR__"
if [ -x "$GR" ]; then
  "$GR" scan --staged || {
    echo "" >&2
    echo "commit bloqueado: credencial detectada nos arquivos staged." >&2
    echo "para ignorar (nao recomendado): git commit --no-verify" >&2
    exit 1
  }
fi
"""


def cmd_git_hooks(args, root: Path, cfg: dict) -> int:
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        print(f"{RED}.git/hooks nao encontrado{RST}")
        return 1
    target = hooks / "pre-commit"
    body = GIT_HOOK.replace("__GR__", str(G.BASE / "bin" / "guardrails"))
    if target.exists() and "guardrails" not in target.read_text(encoding="utf-8", errors="replace"):
        backup = target.with_suffix(".pre-guardrails")
        backup.write_text(target.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        print(f"{YEL}pre-commit existente salvo em {backup.name}{RST}")
    target.write_text(body, encoding="utf-8")
    os.chmod(target, 0o755)
    print(f"{GRN}pre-commit instalado{RST} em {target}")
    return 0


OVERLAY_README = """# Customizacao local do guardrails

Este diretorio pertence ao SEU projeto e **nunca e sobrescrito** quando o plugin
guardrails e atualizado. Versione-o no git (menos config.local.json).

- `config.json`          severidade das verificacoes so deste projeto
- `config.local.json`    ajuste da sua maquina (fora do git)
- `rules/<arquivo>.txt`  regras extras, no mesmo formato do plugin: `regex ::: mensagem`
- `rules/disabled.txt`   ids de regras base a desligar (veja `guardrails rules`)
- `rules/CORE.md`        instrucoes extras injetadas no inicio de cada sessao

Formato de `rules/disabled.txt` (um id por linha, `#` comenta):

    a1b2c3   # regra que nao se aplica: explique aqui o porque
"""


def cmd_init(args, root: Path, cfg: dict) -> int:
    ov = G.overlay_dir(root)
    (ov / "rules").mkdir(parents=True, exist_ok=True)
    created = []
    files = {
        "README.md": OVERLAY_README,
        "config.json": json.dumps({"enforce": {}, "protected_branches":
                                   cfg.get("protected_branches", ["main", "master"])},
                                  indent=2, ensure_ascii=False) + "\n",
        "rules/disabled.txt": "# ids de regras base desligadas neste projeto (guardrails rules mostra os ids)\n",
        "rules/secrets-allow.txt": "# padroes que NAO sao segredo neste projeto (mata falso positivo)\n",
        "rules/bash-deny.txt": "# regras extras de comando bloqueado: regex ::: motivo\n",
    }
    for rel, body in files.items():
        f = ov / rel
        if f.exists():
            continue
        f.write_text(body, encoding="utf-8")
        created.append(rel)

    gi = root / ".gitignore"
    line = ".claude/guardrails/config.local.json"
    try:
        cur = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if line not in cur:
            gi.write_text(cur + ("" if cur.endswith("\n") or not cur else "\n") + line + "\n", encoding="utf-8")
    except Exception:
        pass

    print(f"{GRN}overlay pronto{RST} em {ov}")
    for c in created:
        print(f"  criado  {c}")
    if not created:
        print(f"  {DIM}nada a criar: ja existia{RST}")
    print(f"\n{DIM}Versione esta pasta. Update do plugin nunca a sobrescreve.{RST}")
    return 0


def cmd_rules(args, root: Path, cfg: dict) -> int:
    files = ["bash-deny.txt", "bash-ask.txt", "secrets.txt", "secrets-generic.txt",
             "secrets-allow.txt", "code-smells.txt"]
    dis = G.disabled_ids(root)
    term = (args.grep or "").lower()
    total = 0
    for f in files:
        rs = G.load_rules(f, root)
        rows = [r for r in rs if not term or term in r.msg.lower() or term in r.pattern.pattern.lower()]
        if not rows:
            continue
        print(f"\n{BOLD}{f}{RST}")
        for r in rows:
            tag = f"{DIM}[{r.source}]{RST}" if r.source == "projeto" else ""
            print(f"  {YEL}{r.rid}{RST} {tag} {r.msg[:78] or r.pattern.pattern[:78]}")
            total += 1
    for r in G.load_path_rules(root):
        if term and term not in r.msg.lower():
            continue
        print(f"  {YEL}{r.rid}{RST} [paths/{r.sev}] {r.msg[:70]}")
        total += 1
    print(f"\n{total} regra(s) ativa(s)." + (f" {len(dis)} desligada(s) neste projeto." if dis else ""))
    print(f"{DIM}Para desligar uma: escreva o id em .claude/guardrails/rules/disabled.txt{RST}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guardrails", description="Guardrails portatil de seguranca e qualidade")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check", help="roda o gate completo (lint, typecheck, testes)")
    s.add_argument("--full", action="store_true", help="inclui build e e2e")
    s.add_argument("--only", help="etapas separadas por virgula (lint,typecheck,unit,e2e,build)")
    s.add_argument("--refresh", action="store_true", help="redetecta o stack")

    s = sub.add_parser("scan", help="procura credenciais no codigo")
    s.add_argument("--all", action="store_true", help="todo o repositorio")
    s.add_argument("--staged", action="store_true", help="apenas arquivos staged")
    s.add_argument("--smells", action="store_true", help="inclui padroes inseguros")

    sub.add_parser("doctor", help="diagnostico da instalacao e do stack")
    sub.add_parser("init", help="cria a pasta de customizacao do projeto (nao some no update)")
    sr = sub.add_parser("rules", help="lista as regras ativas e seus ids")
    sr.add_argument("--grep", help="filtra por texto")
    sub.add_parser("detect", help="imprime o stack detectado em JSON")
    sub.add_parser("off", help="desliga os hooks neste projeto")
    sub.add_parser("on", help="religa os hooks neste projeto")
    sub.add_parser("install-git-hooks", help="instala pre-commit que barra segredos")

    args = p.parse_args(argv)
    root = G.project_root()
    cfg = G.load_config(root)
    table = {
        "check": cmd_check, "scan": cmd_scan, "doctor": cmd_doctor, "detect": cmd_detect,
        "off": cmd_toggle, "on": cmd_toggle, "install-git-hooks": cmd_git_hooks,
        "init": cmd_init, "rules": cmd_rules,
    }
    return table[args.cmd](args, root, cfg)


if __name__ == "__main__":
    sys.exit(main())
