"""Invoke external coding agent CLI via subprocess."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from config import Settings
from models.issue_models import ClaudeExecutionResult, WorkspaceContext

_CONF_RE = re.compile(r"CONFIDENCE:\s*(\d{1,3})", re.IGNORECASE)


def _resolve_agent_argv(argv: list[str]) -> list[str]:
    """Ensure argv[0] exists and is executable; raise with setup hints if not."""
    if not argv:
        raise RuntimeError("AGENT_COMMAND is empty")
    exe = argv[0]
    if os.sep in exe or (os.altsep is not None and os.altsep in exe):
        path = os.path.expanduser(exe)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path] + argv[1:]
        raise RuntimeError(
            f"AGENT_COMMAND starts with {exe!r} but that file is missing or not executable. "
            "Fix the path or install the CLI."
        )
    resolved = shutil.which(exe)
    if resolved:
        return [resolved] + argv[1:]
    # Official / npm installs often expose `claude`, not `claude-code`.
    if exe in ("claude-code", "claude.cmd"):
        alt = shutil.which("claude")
        if alt:
            logger.warning(
                "{!r} not on PATH; using {!r} (same args). Override AGENT_COMMAND if needed.",
                exe,
                alt,
            )
            return [alt] + argv[1:]
    raise RuntimeError(
        f"AGENT_COMMAND starts with {exe!r}, which is not on PATH.\n"
        "If `claude` works in your terminal, set e.g.:\n"
        "  AGENT_COMMAND=claude run --dangerously-skip-permissions\n"
        "Or use the full path from `where claude` (Windows) / `which claude` (macOS/Linux) — "
        "IDEs and `python main.py` sometimes inherit a smaller PATH than your shell."
    )


def _git_diff_stats(repo: str) -> tuple[int, int]:
    """Return (files_changed, lines_changed) from working tree vs HEAD."""
    cp = subprocess.run(
        ["git", "-C", repo, "diff", "--numstat", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        return 0, 0
    files = 0
    lines = 0
    for line in cp.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        try:
            add = int(parts[0]) if parts[0] != "-" else 0
            rem = int(parts[1]) if parts[1] != "-" else 0
        except ValueError:
            add, rem = 0, 0
        lines += add + rem
    return files, lines


def _parse_confidence(text: str) -> int:
    m = _CONF_RE.search(text)
    if not m:
        return 0
    v = int(m.group(1))
    return max(0, min(100, v))


def run_fix(
    settings: Settings,
    context_file: str,
    workspace: WorkspaceContext,
    extra_prompt_suffix: str = "",
) -> ClaudeExecutionResult:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    master = (prompts_dir / "master_fix_prompt.md").read_text(encoding="utf-8")
    ctx = Path(context_file).read_text(encoding="utf-8")
    combined = master + "\n\n--- ISSUE CONTEXT ---\n\n" + ctx
    if extra_prompt_suffix:
        combined += "\n\n--- ADDITIONAL ---\n\n" + extra_prompt_suffix

    prompt_path = Path(workspace.local_path) / "_agent_prompt.txt"
    prompt_path.write_text(combined, encoding="utf-8")

    cmd = _resolve_agent_argv(shlex.split(settings.agent_command))

    logger.info("Agent cwd={} argv={}", workspace.local_path, cmd)
    logger.info(
        "Agent subprocess started (stdout/stderr captured — no live stream until it exits; timeout 3600s)."
    )
    # Default: feed full prompt on stdin (equivalent to `agent < prompt.txt`).
    try:
        # Windows defaults to cp1252 for subprocess pipes; Jira/context often has UTF-8/emoji.
        proc = subprocess.run(
            cmd,
            cwd=workspace.local_path,
            input=combined,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Failed to execute agent command {cmd!r}: {e}. "
            "Set AGENT_COMMAND to the full path of your CLI."
        ) from e
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    logger.info("Agent subprocess finished with exit code {}", proc.returncode)
    combined_out = stdout + "\n" + stderr
    confidence = _parse_confidence(combined_out)
    files_changed, lines_changed = _git_diff_stats(workspace.local_path)
    success = proc.returncode == 0
    return ClaudeExecutionResult(
        success=success,
        stdout=stdout,
        stderr=stderr,
        confidence=confidence,
        files_changed=files_changed,
        lines_changed=lines_changed,
    )
