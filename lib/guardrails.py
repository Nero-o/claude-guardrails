#!/usr/bin/env python3
"""Guardrails — nucleo dos hooks e da CLI.

Principios:
  1. Falha aberta em erro de infraestrutura (nunca trava a sessao por bug proprio).
  2. Falha fechada em risco detectado (bloqueia o que as regras marcam como perigoso).
  3. Nunca bloqueia infinitamente: cada checagem tem limite de bloqueios por sessao.
"""
from __future__ import annotations

import fnmatch
import hashlib
from collections import namedtuple
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or HERE.parent).resolve()
RULES_DIR = BASE / "rules"          # regras base, substituidas a cada update
OVERLAY_REL = ".claude/guardrails"  # customizacao do projeto, nunca sobrescrita

sys.path.insert(0, str(HERE))
try:
    import stack as stackmod
except Exception:
    stackmod = None

SEP = ":::"
Rule = namedtuple("Rule", "pattern msg rid source")
PathRule = namedtuple("PathRule", "sev pattern msg rid source")

STRICTNESS = {
    "permissivo": {"code_smells": "off", "stop_requires_tests": "off",
                   "post_edit_lint": False, "test_only_markers": "ask"},
    "padrao": {},
    "estrito": {"code_smells": "deny", "stop_requires_tests": "deny",
                "write_secrets": "deny", "write_sensitive_paths": "deny",
                "post_edit_lint": True, "test_only_markers": "deny"},
}


def rule_id(pattern: str) -> str:
    return hashlib.sha1(pattern.encode("utf-8")).hexdigest()[:6]


def overlay_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / OVERLAY_REL


def disabled_ids(root: Path | None = None) -> set:
    f = overlay_dir(root) / "rules" / "disabled.txt"
    if not f.exists():
        return set()
    out = set()
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.add(line.split()[0])
    return out
# caminhos onde credencial falsa e legitima: heuristicas nao valem, tokens reais valem
FIXTURE_RE = re.compile(
    r"(^|/)(tests?|__tests__|__mocks__|spec|specs|e2e|cypress|fixtures?|mocks?|"
    r"stubs?|factories|seeds?|examples?|docs?|samples?)/"
    r"|\.(test|spec|example|sample|template|md|mdx)\b"
    r"|(^|/)conftest\.py$",
    re.IGNORECASE,
)
MAX_BLOCKS = {"tests": 1, "secrets": 2, "only": 2, "debug": 1, "smells": 2, "lint": 3}


# --------------------------------------------------------------------------- infra
def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    if stackmod:
        return stackmod.project_root()
    return Path.cwd().resolve()


def state_dir(root: Path) -> Path:
    """Estado por projeto (funciona tambem com instalacao global em ~/.claude)."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data:
        d = Path(data) / "state" / hashlib.sha256(str(root).encode()).hexdigest()[:12]
    else:
        d = BASE / ".state"
        if not str(BASE).startswith(str(root)):
            d = d / hashlib.sha256(str(root).encode()).hexdigest()[:12]
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_config(root: Path | None = None) -> dict:
    """Camadas, da menor para a maior precedencia:
    1. config.json do plugin        (base; trocado a cada update)
    2. strictness do plugin.json    (escolha do cliente na instalacao)
    3. .claude/guardrails/config.json        (do projeto, versionado)
    4. .claude/guardrails/config.local.json  (da maquina, fora do git)
    """
    cfg = _read_json(BASE / "config.json")
    level = (os.environ.get("CLAUDE_PLUGIN_OPTION_STRICTNESS") or "").strip().lower()
    if level in STRICTNESS and STRICTNESS[level]:
        cfg = _merge(cfg, {"enforce": STRICTNESS[level]})
    ov = overlay_dir(root)
    for f in (ov / "config.json", ov / "config.local.json"):
        if f.exists():
            cfg = _merge(cfg, _read_json(f))
    return cfg


def disabled(root: Path) -> bool:
    if os.environ.get("GUARDRAILS_OFF") in ("1", "true", "yes"):
        return True
    return (state_dir(root) / "disabled").exists()


BAD_RULES: list[tuple[str, int, str, str]] = []  # (arquivo, linha, padrao, erro)


def _parse_rules(path: Path, source: str, skip: set) -> list:
    out = []
    if not path.exists():
        return out
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if SEP in line:
            pat, _, msg = line.partition(SEP)
        else:
            pat, msg = line, ""
        pat = pat.strip()
        rid = rule_id(pat)
        if rid in skip:
            continue
        try:
            out.append(Rule(re.compile(pat), msg.strip(), rid, source))
        except re.error as e:
            BAD_RULES.append((f"{source}:{path.name}", n, pat[:80], str(e)))
    return out


def load_rules(name: str, root: Path | None = None) -> list:
    """Regras base do plugin + regras proprias do projeto, menos as desativadas."""
    skip = disabled_ids(root)
    out = _parse_rules(RULES_DIR / name, "base", skip)
    out += _parse_rules(overlay_dir(root) / "rules" / name, "projeto", skip)
    return out


def _parse_path_rules(path: Path, source: str, skip: set) -> list:
    out = []
    if not path.exists():
        return out
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(SEP)]
        if len(parts) < 2:
            continue
        sev, pat = parts[0], parts[1]
        msg = parts[2] if len(parts) > 2 else ""
        rid = rule_id(pat)
        if rid in skip:
            continue
        try:
            out.append(PathRule(sev, re.compile(pat), msg, rid, source))
        except re.error as e:
            BAD_RULES.append((f"{source}:paths.txt", n, pat[:80], str(e)))
    return out


def load_path_rules(root: Path | None = None) -> list:
    skip = disabled_ids(root)
    out = _parse_path_rules(RULES_DIR / "paths.txt", "base", skip)
    out += _parse_path_rules(overlay_dir(root) / "rules" / "paths.txt", "projeto", skip)
    return out


# --------------------------------------------------------------------------- saida
def emit(payload: dict, code: int = 0):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(code)


def decide(event: str, decision: str, reason: str):
    emit({"hookSpecificOutput": {
        "hookEventName": event,
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }})


def allow_quiet():
    sys.exit(0)


def context(event: str, text: str):
    emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def block_stop(event: str, reason: str):
    """Impede o encerramento e devolve a razao para o agente agir."""
    sys.stderr.write(reason)
    sys.exit(2)


# --------------------------------------------------------------------------- estado
def session_state(root: Path, sid: str) -> tuple[Path, dict]:
    f = state_dir(root) / f"session-{re.sub(r'[^A-Za-z0-9_-]', '', sid or 'anon')[:40]}.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    return f, data


def bump(f: Path, data: dict, key: str) -> int:
    data[key] = int(data.get(key, 0)) + 1
    data["_ts"] = int(time.time())
    try:
        f.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
    return data[key]


# --------------------------------------------------------------------------- scan
def is_ignored(rel: str, cfg: dict) -> bool:
    r = rel.replace("\\", "/")
    # o proprio kit contem os padroes que procura: nunca se auto-escaneia
    if "/guardrails/rules/" in "/" + r or r.startswith("guardrails/") or "/.claude/guardrails/" in "/" + r:
        return True
    parts = Path(rel).parts
    ig = set(cfg.get("ignore_paths", []))
    if any(p in ig for p in parts):
        return True
    return any(r.startswith(i.rstrip("/") + "/") or r == i for i in ig)


def looks_like_test(rel: str, cfg: dict) -> bool:
    pats = cfg.get("test_patterns", [])
    r = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(r, p) or fnmatch.fnmatch("/" + r, p) for p in pats)


def is_source(rel: str, cfg: dict) -> bool:
    exts = set(cfg.get("source_extensions", []))
    return Path(rel).suffix in exts and not looks_like_test(rel, cfg) and not is_ignored(rel, cfg)


def secret_rules(rel: str = "") -> list[tuple[re.Pattern, str]]:
    """Regras de segredo aplicaveis ao caminho: fixtures ficam so com alta confianca."""
    rules = load_rules("secrets.txt")
    if not rel or not FIXTURE_RE.search(rel.replace(chr(92), "/")):
        rules += load_rules("secrets-generic.txt")
    return rules


def scan_text(text: str, rules, allow_rules=None, limit: int = 20) -> list[tuple[int, str, str]]:
    """Retorna [(linha, mensagem, trecho)] para cada regra que casar."""
    hits = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, 1):
        if len(line) > 4000:
            line = line[:4000]
        for pat, msg, *_ in rules:
            if pat.search(line):
                if allow_rules and any(a[0].search(line) for a in allow_rules):
                    continue
                snippet = line.strip()[:120]
                hits.append((idx, msg, snippet))
                break
        if len(hits) >= limit:
            break
    return hits


def fmt_hits(title: str, hits, path: str = "") -> str:
    head = f"{title}{f' em {path}' if path else ''}:"
    body = "\n".join(f"  linha {n}: {msg}\n    > {snip}" for n, msg, snip in hits)
    return f"{head}\n{body}"


# --------------------------------------------------------------------------- hooks
def push_targets(cmd: str, root: Path) -> set:
    """Branches que um `git push` realmente atinge.

    Com refspec explicito, vale o refspec — a branch atual e irrelevante.
    Sem refspec, o push vai para a branch em que se esta.
    """
    m = re.search(r"(?i)\bgit\s+push\b(.*)$", cmd)
    if not m:
        return set()
    tail = re.split(r"[;&|]", m.group(1))[0]
    pos = [t for t in tail.split() if not t.startswith("-")]
    refs = pos[1:]  # pos[0] e o remote
    if not refs:
        cur = (git(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
        return {cur} if cur else set()
    out = set()
    for r in refs:
        r = r.lstrip("+")
        dst = r.split(":")[-1]                       # local:remoto -> remoto
        out.add(dst.replace("refs/heads/", "").strip())
    return {o for o in out if o}


def hook_pre_bash(payload: dict, cfg: dict, root: Path):
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd.strip():
        allow_quiet()
    enf = cfg.get("enforce", {})

    if enf.get("bash_deny", True):
        for pat, msg, *_ in load_rules("bash-deny.txt"):
            if pat.search(cmd):
                decide("PreToolUse", "deny",
                       f"[guardrails] Comando bloqueado.\nMotivo: {msg}\n"
                       f"Comando: {cmd[:400]}\n"
                       f"Se for realmente necessario, explique ao usuario e peca que ele execute.")

    # force push em branch protegida e sempre deny (nao apenas ask).
    # Desative ajustando protected_branches em .claude/guardrails/config.json.
    prot = set(cfg.get("protected_branches", []))
    if prot and re.search(r"(?i)\bgit\s+push\b.*(--force|(\s|^)-f)(\s|$)", cmd):
        names = push_targets(cmd, root)
        hit = names & prot
        if hit:
            decide("PreToolUse", "deny",
                   f"[guardrails] Force push em branch protegida ({', '.join(sorted(hit))}). "
                   f"Reescrever historico compartilhado quebra o repositorio de todo mundo.")

    if enf.get("bash_ask", True):
        for pat, msg, *_ in load_rules("bash-ask.txt"):
            if pat.search(cmd):
                decide("PreToolUse", "ask",
                       f"[guardrails] Confirmacao necessaria.\nMotivo: {msg}\nComando: {cmd[:400]}")

    # segredo digitado direto na linha de comando
    hits = scan_text(cmd, load_rules("secrets.txt"), load_rules("secrets-allow.txt"), limit=3)
    if hits:
        decide("PreToolUse", "deny",
               "[guardrails] O comando contem o que parece ser uma credencial real. "
               "Ela ficaria gravada no historico do shell e no transcript. "
               f"Use variavel de ambiente.\n{fmt_hits('Achados', hits)}")
    allow_quiet()


def _edit_payload(ti: dict) -> tuple[str, str]:
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    chunks = []
    for key in ("content", "new_string", "new_source"):
        v = ti.get(key)
        if isinstance(v, str):
            chunks.append(v)
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            chunks.append(e["new_string"])
    return path, "\n".join(chunks)


def hook_pre_write(payload: dict, cfg: dict, root: Path):
    ti = payload.get("tool_input") or {}
    path, content = _edit_payload(ti)
    if not path:
        allow_quiet()
    try:
        rel = str(Path(path).resolve().relative_to(root))
    except Exception:
        rel = path
    rel = rel.replace("\\", "/")
    enf = cfg.get("enforce", {})

    # 1. caminho sensivel
    for sev, pat, msg, *_ in load_path_rules():
        if pat.search(rel):
            mode = enf.get("write_sensitive_paths", "deny")
            if mode == "off":
                break
            decision = "deny" if (sev == "deny" and mode == "deny") else "ask"
            decide("PreToolUse", decision,
                   f"[guardrails] Caminho protegido: {rel}\nMotivo: {msg}")

    if not content.strip():
        allow_quiet()

    # 2. segredo no conteudo
    if enf.get("write_secrets", "deny") != "off":
        hits = scan_text(content, secret_rules(rel), load_rules("secrets-allow.txt"), limit=5)
        if hits:
            decide("PreToolUse", "deny" if enf.get("write_secrets") == "deny" else "ask",
                   f"[guardrails] Credencial hardcoded bloqueada.\n{fmt_hits('Achados', hits, rel)}\n"
                   f"Correcao: leia de variavel de ambiente e registre o NOME dela em .env.example.")

    # 3. marcador que desliga a suite de testes
    if enf.get("test_only_markers", "deny") != "off":
        only = scan_text(content, [(re.compile(r"(?i)\b(it|test|describe|context)\.only\s*\("), "only() isola o teste e mascara o resto da suite"),
                                   (re.compile(r"(?i)\b(fdescribe|fit)\s*\("), "fdescribe/fit isola o teste")], limit=3)
        if only:
            decide("PreToolUse", "deny",
                   f"[guardrails] Marcador de teste exclusivo.\n{fmt_hits('Achados', only, rel)}\n"
                   f"Rode o teste isolado pela CLI (ex.: vitest run caminho -t 'nome') em vez de gravar .only no arquivo.")

    # 4. padroes inseguros / frageis
    mode = enf.get("code_smells", "warn")
    if mode != "off":
        hits = scan_text(content, load_rules("code-smells.txt"), limit=6)
        if hits:
            if mode == "deny":
                decide("PreToolUse", "deny", f"[guardrails] Padrao inseguro.\n{fmt_hits('Achados', hits, rel)}")
            context("PreToolUse",
                    f"[guardrails] Aviso (nao bloqueia) em {rel}:\n{fmt_hits('Padroes de risco', hits)}\n"
                    f"Justifique no codigo ou corrija antes de concluir.")
    allow_quiet()


def find_bin(name: str, start: Path, root: Path) -> str | None:
    """Resolve binario local (node_modules/.bin, .venv/bin) sem tocar na rede."""
    cur = start if start.is_dir() else start.parent
    for _ in range(8):
        for sub in ("node_modules/.bin", ".venv/bin", "venv/bin", ".venv/Scripts"):
            cand = cur / sub / name
            if cand.exists() and os.access(cand, os.X_OK):
                return str(cand)
        if cur == root or cur == cur.parent:
            break
        cur = cur.parent
    import shutil
    return shutil.which(name)


def hook_post_edit(payload: dict, cfg: dict, root: Path):
    if not cfg.get("enforce", {}).get("post_edit_lint", True):
        allow_quiet()
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path:
        allow_quiet()
    p = Path(path)
    if not p.exists():
        allow_quiet()
    try:
        rel = str(p.resolve().relative_to(root))
    except Exception:
        allow_quiet()
        return
    if is_ignored(rel, cfg):
        allow_quiet()
    po = cfg.get("post_edit", {})
    try:
        if p.stat().st_size > int(po.get("max_file_bytes", 400000)):
            allow_quiet()
    except Exception:
        allow_quiet()

    ext = p.suffix.lower()
    timeout = int(po.get("timeout_seconds", 45))
    jobs: list[tuple[str, list[str], bool]] = []  # (bin, args, is_lint)

    if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"):
        jobs.append(("prettier", ["--write", str(p)], False))
        jobs.append(("eslint", ["--fix", str(p)], True))
    elif ext == ".py":
        jobs.append(("ruff", ["format", str(p)], False))
        jobs.append(("ruff", ["check", "--fix", str(p)], True))
        jobs.append(("black", [str(p)], False))
    elif ext == ".go":
        jobs.append(("gofmt", ["-w", str(p)], False))
    elif ext == ".rs":
        jobs.append(("rustfmt", [str(p)], False))
    elif ext in (".json", ".md", ".yml", ".yaml", ".css", ".scss", ".html"):
        jobs.append(("prettier", ["--write", str(p)], False))

    problems = []
    ran_formatter = False
    for name, args, is_lint in jobs:
        if name == "black" and ran_formatter:
            continue
        exe = find_bin(name, p.parent, root)
        if not exe:
            continue
        try:
            r = subprocess.run([exe, *args], cwd=str(root), capture_output=True,
                               text=True, timeout=timeout)
        except Exception:
            continue
        if not is_lint:
            ran_formatter = True
            continue
        if r.returncode != 0:
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            if out:
                problems.append(f"$ {name} {' '.join(args[:-1])} {rel}\n{out[:2500]}")

    if problems and po.get("block_on_lint_error", True):
        sys.stderr.write("[guardrails] Lint falhou no arquivo que voce acabou de editar. "
                         "Corrija antes de seguir:\n\n" + "\n\n".join(problems))
        sys.exit(2)
    allow_quiet()


def git(root: Path, args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def changed_files(root: Path) -> list[str]:
    out = []
    st = git(root, ["status", "--porcelain=v1", "-uall"]) or ""
    for line in st.splitlines():
        if len(line) < 4:
            continue
        name = line[3:].strip()
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        out.append(name.strip('"'))
    return out


def added_lines(root: Path, files: list[str], cfg: dict) -> str:
    """Conteudo adicionado (diff + arquivos novos), para varredura."""
    chunks = []
    diff = git(root, ["diff", "HEAD", "--unified=0", "--no-color", "--", *files[:200]]) or ""
    chunks.append("\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")))
    tracked = set((git(root, ["ls-files"]) or "").split())
    cap = int(cfg.get("limits", {}).get("max_file_scan_bytes", 2000000))
    for f in files:
        if f in tracked:
            continue
        p = root / f
        if not p.is_file() or is_ignored(f, cfg):
            continue
        try:
            if p.stat().st_size > cap:
                continue
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
    return "\n".join(chunks)


def hook_stop(payload: dict, cfg: dict, root: Path):
    enf = cfg.get("enforce", {})
    sid = payload.get("session_id") or ""
    sf, sdata = session_state(root, sid)
    files = [f for f in changed_files(root) if not is_ignored(f, cfg)]
    if not files:
        allow_quiet()

    reasons = []

    # 1. segredo no que esta prestes a virar commit
    if enf.get("stop_scans_diff", True):
        blob = added_lines(root, files, cfg)
        hits = scan_text(blob, load_rules("secrets.txt"), load_rules("secrets-allow.txt"), limit=5)
        if hits and sdata.get("secrets", 0) < MAX_BLOCKS["secrets"]:
            bump(sf, sdata, "secrets")
            reasons.append("[guardrails] Credencial detectada nas alteracoes do working tree:\n"
                           + fmt_hits("Achados", hits)
                           + "\nRemova o valor, troque por variavel de ambiente e rode "
                             "`guardrails scan` para confirmar. Se for falso positivo, "
                             "adicione o padrao em guardrails/rules/secrets-allow.txt.")
        only = scan_text(blob, [(re.compile(r"(?i)\b(it|test|describe|context)\.only\s*\("), ".only() ficou no codigo")], limit=3)
        if only and sdata.get("only", 0) < MAX_BLOCKS["only"]:
            bump(sf, sdata, "only")
            reasons.append("[guardrails] Marcador .only() nas alteracoes — a suite passaria verde "
                           "rodando um teste so:\n" + fmt_hits("Achados", only))
        debug = scan_text(blob, [
            (re.compile(r"(?i)\b(debugger|pdb\.set_trace|binding\.pry|var_dump\()"), "breakpoint/debug esquecido"),
        ], limit=3)
        if debug and sdata.get("debug", 0) < MAX_BLOCKS["debug"]:
            bump(sf, sdata, "debug")
            reasons.append("[guardrails] Debug esquecido:\n" + fmt_hits("Achados", debug))

    # 2. codigo mudou sem teste correspondente
    mode = enf.get("stop_requires_tests", "warn")
    if mode != "off":
        src = [f for f in files if is_source(f, cfg)]
        tests = [f for f in files if looks_like_test(f, cfg)]
        if src and not tests and sdata.get("tests", 0) < MAX_BLOCKS["tests"]:
            bump(sf, sdata, "tests")
            listing = "\n".join(f"  - {f}" for f in src[:12])
            msg = ("[guardrails] Codigo de producao alterado sem nenhum teste tocado:\n" + listing +
                   "\n\nAntes de encerrar, escolha um:\n"
                   "  a) escreva o teste que falha sem a sua mudanca e passa com ela;\n"
                   "  b) aponte o teste existente que ja cobre esse caminho (cite arquivo:linha);\n"
                   "  c) diga explicitamente ao usuario por que este caso nao e testavel.\n"
                   "Nivel do teste: logica pura/regra de negocio -> unitario (jest/vitest/pytest); "
                   "contrato entre camadas -> integracao; fluxo que o usuario percorre na tela -> "
                   "e2e (playwright/cypress).")
            if mode == "deny":
                reasons.append(msg)
            else:
                reasons.append(msg)

    if reasons:
        block_stop("Stop", "\n\n".join(reasons))
    allow_quiet()


def hook_session_start(payload: dict, cfg: dict, root: Path):
    if not cfg.get("enforce", {}).get("session_start_context", True):
        allow_quiet()
    if not stackmod:
        allow_quiet()
    try:
        info = stackmod.load(root, state_dir(root))
    except Exception:
        allow_quiet()
        return
    cmds = info.get("commands", {})
    if not cmds:
        allow_quiet()
    lines = ["[guardrails] Stack detectado neste repositorio — use estes comandos, nao invente outros:"]
    for k in ("lint", "typecheck", "unit", "e2e", "build"):
        for c in cmds.get(k, []):
            lines.append(f"  {k:<9} {c}")
    fw = info.get("js_frameworks") or []
    if fw:
        lines.append(f"  frameworks JS: {', '.join(fw)}")
    if info.get("python"):
        lines.append(f"  python: {info['python'].get('test') or 'sem runner detectado'}")
    cli = BASE / "bin" / "guardrails"
    try:
        cli_disp = str(cli.relative_to(root))
    except Exception:
        cli_disp = str(cli)
    lines.append(f"  Gate obrigatorio antes de concluir: {cli_disp} check")
    lines.append(f"  Varredura de segredos: {cli_disp} scan")

    # nucleo de regras: injetado a cada sessao para nao depender de edicao do CLAUDE.md
    core = RULES_DIR / "CORE.md"
    ov_core = overlay_dir(root) / "rules" / "CORE.md"
    parts = ["\n".join(lines)]
    for f in (core, ov_core):
        if f.exists():
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace").strip())
            except Exception:
                pass
    context("SessionStart", "\n\n".join(parts))


HOOKS = {
    "pre-bash": hook_pre_bash,
    "pre-write": hook_pre_write,
    "post-edit": hook_post_edit,
    "stop": hook_stop,
    "session-start": hook_session_start,
}


def run_hook(event: str):
    root = project_root()
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if disabled(root):
        sys.exit(0)
    cfg = load_config(root)
    fn = HOOKS.get(event)
    if not fn:
        sys.exit(0)
    try:
        fn(payload, cfg, root)
    except SystemExit:
        raise
    except Exception as e:  # falha aberta
        if os.environ.get("GUARDRAILS_DEBUG"):
            sys.stderr.write(f"[guardrails] erro interno: {e!r}\n")
        sys.exit(0)


if __name__ == "__main__":
    run_hook(sys.argv[1] if len(sys.argv) > 1 else "")
