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


def _npm_script_chain(repo: str) -> tuple[list[str], str]:
    pkg_path = Path(repo) / "package.json"
    if not pkg_path.is_file():
        return [], "No package.json — skipping npm steps."
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    scripts = data.get("scripts") or {}
    order = ["lint", "test", "build"]
    cmds: list[str] = []
    for name in order:
        if name in scripts:
            cmds.append(f"npm run {name}")
    if not cmds:
        return [], "package.json has no lint/test/build scripts — skipping npm steps."
    root = Path(repo)
    has_lock = (root / "package-lock.json").is_file() or (
        root / "npm-shrinkwrap.json"
    ).is_file()
    install = "npm ci" if has_lock else "npm install --no-audit --no-fund"
    script = "set -euo pipefail\n" + install + "\n" + "\n".join(cmds)
    return cmds, script


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

    cmds, npm_script = _npm_script_chain(workspace_path)
    logs.append("## npm plan")
    logs.append(npm_script)

    if not cmds:
        logger.info("No npm validation scripts; diff guardrails only.")
        return ValidationResult(
            lint_passed=True,
            tests_passed=True,
            build_passed=True,
            logs="\n".join(logs),
            files_changed=files,
            lines_changed=lines,
        )

    ok, out = run_in_docker(settings, workspace_path, npm_script)
    logs.append("## docker output")
    logs.append(out)

    # If chain ran, assume order lint, test, build for those present
    wanted = [k for k in ("lint", "test", "build") if f"npm run {k}" in npm_script]
    lint_ok = True
    test_ok = True
    build_ok = True
    if "lint" in wanted:
        lint_ok = ok
    if "test" in wanted:
        test_ok = ok
    if "build" in wanted:
        build_ok = ok
    if not ok:
        lint_ok = test_ok = build_ok = False

    return ValidationResult(
        lint_passed=lint_ok,
        tests_passed=test_ok,
        build_passed=build_ok,
        logs="\n".join(logs),
        files_changed=files,
        lines_changed=lines,
    )
