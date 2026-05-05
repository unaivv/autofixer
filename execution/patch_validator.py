"""Diff guardrails + Node/npm validation inside Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from loguru import logger

from config import Settings
from execution.docker_runner import run_in_docker
from models.issue_models import ValidationResult


def _diff_changed_paths(repo: str) -> list[str]:
    cp = subprocess.run(
        ["git", "-C", repo, "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [ln.strip().replace("\\", "/") for ln in (cp.stdout or "").splitlines() if ln.strip()]


def _repo_has_turbo(root: Path) -> bool:
    return (root / "turbo.json").is_file() or (root / "turbo.jsonc").is_file()


def _scoped_turbo_package_names(repo: str) -> list[str] | None:
    """
    Map git diff paths to workspace package `name` fields for turbo --filter.
    Returns None when the diff touches the repo root workspace or unmapped paths — caller should run the full graph.
    """
    root = Path(repo).resolve()
    rpj = root / "package.json"
    if not rpj.is_file():
        return None
    try:
        root_data = json.loads(rpj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    is_workspace_root = bool(root_data.get("workspaces"))

    names: set[str] = set()
    for rel_s in _diff_changed_paths(repo):
        cand = Path(rel_s)
        if cand.is_absolute():
            continue
        full = root / cand
        if full.is_file():
            d = full.resolve().parent
        else:
            d = (root / cand).resolve().parent
        cur = d
        matched = False
        while True:
            pj = cur / "package.json"
            if pj.is_file():
                try:
                    data = json.loads(pj.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    return None
                name = data.get("name")
                if not name:
                    return None
                if cur.resolve() == root and is_workspace_root:
                    return None
                names.add(str(name))
                matched = True
                break
            if cur.resolve() == root:
                break
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
        if not matched:
            return None
    return sorted(names) if names else None


def _turbo_pm_prefix(pm: str) -> str:
    if pm == "pnpm":
        return "pnpm exec turbo"
    if pm == "yarn":
        return "yarn exec turbo"
    return "npx turbo"


def _diff_against_head(repo: str) -> tuple[int, int, str]:
    cp = subprocess.run(
        ["git", "-C", repo, "diff", "--stat", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    stat = (cp.stdout or "").strip()
    cp2 = subprocess.run(
        ["git", "-C", repo, "diff", "--numstat", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    files = 0
    lines = 0
    for line in (cp2.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        try:
            a = int(parts[0]) if parts[0] != "-" else 0
            b = int(parts[1]) if parts[1] != "-" else 0
        except ValueError:
            a, b = 0, 0
        lines += a + b
    return files, lines, stat


def _detect_pm_install(root: Path, data: dict) -> tuple[str, str]:
    """
    Pick package manager + install line for monorepos (Turborepo often needs pnpm in PATH).
    Order: lockfiles first, then packageManager field.
    """
    pkg_pm = (data.get("packageManager") or "").strip().lower()
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm", "pnpm install --frozen-lockfile"
    if pkg_pm.startswith("pnpm@"):
        return "pnpm", "pnpm install"
    if (root / "yarn.lock").is_file():
        return "yarn", "yarn install --frozen-lockfile"
    if pkg_pm.startswith("yarn@"):
        return "yarn", "yarn install"
    if (root / "package-lock.json").is_file() or (root / "npm-shrinkwrap.json").is_file():
        return "npm", "npm ci"
    return "npm", "npm install --no-audit --no-fund"


def _npm_script_chain(repo: str, turbo_filter_changed: bool) -> tuple[list[str], str]:
    pkg_path = Path(repo) / "package.json"
    if not pkg_path.is_file():
        return [], "No package.json — skipping npm steps."
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    scripts = data.get("scripts") or {}
    order = ["lint", "test", "build"]
    wanted: list[str] = [name for name in order if name in scripts]
    if not wanted:
        return [], "package.json has no lint/test/build scripts — skipping npm steps."

    root = Path(repo)
    pm, install = _detect_pm_install(root, data)
    run_lines = [f"{pm} run {name}" for name in wanted]

    scoped: list[str] | None = None
    if turbo_filter_changed and _repo_has_turbo(root):
        scoped = _scoped_turbo_package_names(repo)
    if scoped:
        filters = " ".join(f"--filter={n}" for n in scoped)
        tasks = " ".join(wanted)
        turbo_line = f"{_turbo_pm_prefix(pm)} run {tasks} {filters}"
        run_lines = [turbo_line]

    # corepack: makes pnpm/yarn shims available when package.json declares "packageManager"
    script = "\n".join(
        [
            "set -euo pipefail",
            "corepack enable",
            install,
            *run_lines,
        ]
    )
    return wanted, script


def validate(settings: Settings, workspace_path: str) -> ValidationResult:
    files, lines, stat = _diff_against_head(workspace_path)
    logs: list[str] = [stat, "", f"files_changed={files} lines_changed={lines}", ""]

    if files > settings.max_files_changed or lines > settings.max_lines_changed:
        msg = (
            f"Diff too large for policy: files={files} (max {settings.max_files_changed}), "
            f"lines={lines} (max {settings.max_lines_changed})"
        )
        logs.append(msg)
        logger.warning(msg)
        return ValidationResult(
            lint_passed=False,
            tests_passed=False,
            build_passed=False,
            logs="\n".join(logs),
            files_changed=files,
            lines_changed=lines,
        )

    wanted, docker_script = _npm_script_chain(
        workspace_path,
        settings.validation_turbo_filter_changed,
    )
    logs.append("## npm plan")
    logs.append(docker_script)

    if not wanted:
        logger.info("No npm validation scripts; diff guardrails only.")
        return ValidationResult(
            lint_passed=True,
            tests_passed=True,
            build_passed=True,
            logs="\n".join(logs),
            files_changed=files,
            lines_changed=lines,
        )

    ok, out = run_in_docker(settings, workspace_path, docker_script)
    logs.append("## docker output")
    logs.append(out)

    lint_ok = ("lint" not in wanted) or ok
    test_ok = ("test" not in wanted) or ok
    build_ok = ("build" not in wanted) or ok

    return ValidationResult(
        lint_passed=lint_ok,
        tests_passed=test_ok,
        build_passed=build_ok,
        logs="\n".join(logs),
        files_changed=files,
        lines_changed=lines,
    )
