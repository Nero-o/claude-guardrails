"""Deteccao de stack — descobre gerenciador, linter, typecheck e runners de teste.

Sem dependencias externas. Funciona em monorepo (varios package.json) e em
projetos poliglotas (JS + Python no mesmo repo).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

MANIFESTS = [
    "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml", "package-lock.json",
    "yarn.lock", "bun.lockb", "pyproject.toml", "requirements.txt", "Pipfile",
    "go.mod", "Cargo.toml", "composer.json", "Gemfile", "pom.xml", "build.gradle",
]

PM_BY_LOCKFILE = {
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
}

# nome do script no package.json -> chave canonica
SCRIPT_ALIASES = {
    "lint": ["lint", "eslint", "lint:check"],
    "format": ["format", "fmt", "prettier", "format:check"],
    "typecheck": ["typecheck", "type-check", "tsc", "types", "check-types"],
    "unit": ["test:unit", "test", "jest", "vitest", "unit"],
    "e2e": ["e2e", "test:e2e", "cypress:run", "playwright", "test:integration"],
    "build": ["build", "compile"],
}

TEST_DEPS = {
    "jest": "jest",
    "vitest": "vitest",
    "@playwright/test": "playwright",
    "playwright": "playwright",
    "cypress": "cypress",
    "mocha": "mocha",
    "@testing-library/react": "testing-library",
    "@testing-library/vue": "testing-library",
}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def project_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return cur


def _pick(scripts: dict, keys: list[str]) -> str | None:
    for k in keys:
        if k in scripts:
            return k
    return None


def _js_packages(root: Path, ignore: set[str]) -> list[dict]:
    """Encontra package.json ate 3 niveis de profundidade."""
    out = []
    for pkg_path in sorted(root.glob("package.json")) + sorted(root.glob("*/package.json")) \
            + sorted(root.glob("*/*/package.json")) + sorted(root.glob("*/*/*/package.json")):
        rel = pkg_path.relative_to(root)
        if any(part in ignore for part in rel.parts):
            continue
        data = _read_json(pkg_path)
        if not data:
            continue
        scripts = data.get("scripts") or {}
        deps = {}
        deps.update(data.get("dependencies") or {})
        deps.update(data.get("devDependencies") or {})
        frameworks = sorted({v for k, v in TEST_DEPS.items() if k in deps})
        entry = {
            "dir": str(rel.parent) if str(rel.parent) != "." else ".",
            "name": data.get("name") or str(rel.parent),
            "frameworks": frameworks,
            "scripts": {},
            "is_root": str(rel.parent) == ".",
            "workspaces": bool(data.get("workspaces")),
        }
        for canon, aliases in SCRIPT_ALIASES.items():
            found = _pick(scripts, aliases)
            if found:
                entry["scripts"][canon] = found
        out.append(entry)
    return out


def _python_info(root: Path) -> dict | None:
    py_files = ["pyproject.toml", "requirements.txt", "requirements-dev.txt", "Pipfile", "setup.py", "tox.ini"]
    present = [f for f in py_files if (root / f).exists()]
    nested = [str(p.relative_to(root).parent) for f in ("pyproject.toml", "requirements.txt")
              for p in root.glob(f"*/{f}")] + \
             [str(p.relative_to(root).parent) for f in ("pyproject.toml", "requirements.txt")
              for p in root.glob(f"*/*/{f}")]
    if not present and not nested:
        return None
    blob = ""
    for f in present:
        try:
            blob += (root / f).read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    for d in set(nested):
        for f in ("pyproject.toml", "requirements.txt"):
            p = root / d / f
            if p.exists():
                try:
                    blob += p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    low = blob.lower()
    info = {
        "dirs": sorted(set(nested)) or ["."],
        "test": "pytest" if "pytest" in low else None,
        "lint": "ruff check" if "ruff" in low else ("flake8" if "flake8" in low else None),
        "format": "ruff format" if "ruff" in low else ("black" if "black" in low else None),
        "typecheck": "mypy" if "mypy" in low else ("pyright" if "pyright" in low else None),
    }
    return info


def detect(root: Path, ignore: set[str] | None = None) -> dict:
    ignore = ignore or {"node_modules", "dist", "build", ".venv", "venv", "vendor", ".git", "coverage"}
    pm = None
    for lock, name in PM_BY_LOCKFILE.items():
        hits = [root / lock] if (root / lock).exists() else []
        if not hits:
            hits = list(root.glob(f"*/{lock}")) + list(root.glob(f"*/*/{lock}"))
            hits = [h for h in hits if not any(part in ignore for part in h.relative_to(root).parts)]
        if hits:
            pm = name
            break
    if pm is None and (root / "package.json").exists():
        pm = "npm"

    packages = _js_packages(root, ignore)
    frameworks = sorted({f for p in packages for f in p["frameworks"]})

    # configs soltos denunciam framework mesmo sem dep declarada no manifesto lido
    for glob, fw in (("playwright.config.*", "playwright"), ("cypress.config.*", "cypress"),
                     ("jest.config.*", "jest"), ("vitest.config.*", "vitest")):
        if any(root.glob(glob)) or any(root.glob(f"*/{glob}")) or any(root.glob(f"*/*/{glob}")):
            if fw not in frameworks:
                frameworks.append(fw)

    info = {
        "root": str(root),
        "package_manager": pm,
        "js_packages": packages,
        "js_frameworks": sorted(frameworks),
        "python": _python_info(root),
        "go": (root / "go.mod").exists(),
        "rust": (root / "Cargo.toml").exists(),
        "has_git": (root / ".git").exists(),
        "ci": sorted(p.name for p in (root / ".github" / "workflows").glob("*.y*ml")) if (root / ".github" / "workflows").is_dir() else [],
    }
    info["commands"] = _commands(info)
    return info


def _run_prefix(pm: str | None, pkg_dir: str) -> str:
    """Prefixo para rodar um script npm dentro do diretorio do pacote."""
    pm = pm or "npm"
    runner = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}[pm]
    if pkg_dir in (".", ""):
        return runner
    return f"{runner} --prefix {pkg_dir}" if pm == "npm" else f"{runner} -C {pkg_dir}"


def _commands(info: dict) -> dict:
    """Comandos canonicos que o gate local e o CI devem rodar."""
    pm = info["package_manager"]
    cmds = {"lint": [], "typecheck": [], "unit": [], "e2e": [], "format": [], "build": []}
    for pkg in info["js_packages"]:
        if pkg.get("workspaces") and not pkg["scripts"]:
            continue
        prefix = _run_prefix(pm, pkg["dir"])
        for canon in cmds:
            script = pkg["scripts"].get(canon)
            if script:
                cmds[canon].append(f"{prefix} {script}")
    py = info.get("python")
    if py:
        for d in py["dirs"]:
            cd = "" if d in (".", "") else f"cd {d} && "
            if py["test"]:
                cmds["unit"].append(f'{cd}{py["test"]} -m "not e2e"')
            if py["lint"]:
                cmds["lint"].append(f'{cd}{py["lint"]} .')
            if py["typecheck"]:
                cmds["typecheck"].append(f'{cd}{py["typecheck"]} .')
            if py["format"]:
                cmds["format"].append(f'{cd}{py["format"]} --check .' if "ruff" in py["format"] else f'{cd}{py["format"]} --check .')
    if info.get("go"):
        cmds["unit"].append("go test ./...")
        cmds["lint"].append("go vet ./...")
    if info.get("rust"):
        cmds["unit"].append("cargo test")
        cmds["lint"].append("cargo clippy -- -D warnings")
    return {k: v for k, v in cmds.items() if v}


def fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for name in MANIFESTS:
        for p in sorted(root.glob(name)) + sorted(root.glob(f"*/{name}")) + sorted(root.glob(f"*/*/{name}")):
            try:
                h.update(name.encode())
                h.update(str(p.stat().st_mtime_ns).encode())
                h.update(str(p.stat().st_size).encode())
            except Exception:
                pass
    return h.hexdigest()[:16]


def load(root: Path, state_dir: Path, force: bool = False) -> dict:
    """Detecta com cache invalidado por mudanca nos manifestos."""
    cache = state_dir / "stack.json"
    fp = fingerprint(root)
    if not force and cache.exists():
        data = _read_json(cache)
        if data and data.get("_fingerprint") == fp:
            return data
    info = detect(root)
    info["_fingerprint"] = fp
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(info, indent=2), encoding="utf-8")
    except Exception:
        pass
    return info


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None
