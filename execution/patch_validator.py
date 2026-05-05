"""Diff guardrails + Node/npm validation inside Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from loguru import logger

from config import Settings
from execution.docker_runner import run_in_docker
from models.issue_models import ValidationResult


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


def _npm_script_chain(repo: str) -> tuple[list[str], str]:
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

    wanted, docker_script = _npm_script_chain(workspace_path)
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
