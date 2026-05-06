"""Optional Engram preload for the agent prompt — same data as Cursor MCP when using the Engram CLI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import requests
from loguru import logger

from config import Settings


def _cli_exe(settings: Settings) -> str | None:
    raw = (settings.engram_cli_path or "").strip()
    if raw and Path(raw).expanduser().is_file():
        return str(Path(raw).expanduser().resolve())
    return shutil.which("engram") or shutil.which("engram.exe")


def _project_name(settings: Settings) -> str:
    return (settings.engram_project or settings.bitbucket_repo_slug or "").strip()


def _run_cli(argv: list[str], *, cwd: str, timeout: float = 45.0) -> str:
    try:
        cp = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("Engram CLI {} failed: {}", argv[:3], e)
        return ""
    out = (cp.stdout or "").strip()
    if cp.returncode != 0 and not out:
        err = (cp.stderr or "").strip()
        if err and "Update available" not in err:
            logger.debug("Engram CLI stderr: {}", err[:500])
        return ""
    return out


def _addon_from_cli(settings: Settings, *, recall_seed: str, workspace_path: str) -> str:
    exe = _cli_exe(settings)
    if not exe:
        return ""

    project = _project_name(settings)
    sections: list[str] = []

    ctx_cmd = [exe, "context"]
    if project:
        ctx_cmd.append(project)
    ctx_out = _run_cli(ctx_cmd, cwd=workspace_path)
    if ctx_out and "No previous session memories found" not in ctx_out:
        sections.append(
            "### Recent session context (Engram CLI)\n\n```\n"
            + ctx_out[:12000]
            + ("\n```\n\n_(truncated)_" if len(ctx_out) > 12000 else "\n```")
        )

    seed = (recall_seed or "").strip()[:2000]
    if seed:
        search_cmd = [exe, "search", seed, "--limit", "10"]
        if project:
            search_cmd.extend(["--project", project])
        search_out = _run_cli(search_cmd, cwd=workspace_path)
        if search_out and "No memories found" not in search_out:
            sections.append(
                "### Search hits for this issue (Engram CLI)\n\n```\n"
                + search_out[:12000]
                + ("\n```\n\n_(truncated)_" if len(search_out) > 12000 else "\n```")
            )

    if not sections:
        return ""
    logger.info("Engram: loaded {} section(s) via CLI ({})", len(sections), exe)
    return "\n\n".join(sections)


def _base_url(settings: Settings) -> str:
    return (settings.engram_rest_url or "").strip().rstrip("/")


def _addon_from_http(settings: Settings, *, recall_seed: str) -> str:
    base = _base_url(settings)
    if not base:
        return ""

    try:
        h = requests.get(f"{base}/health", timeout=2)
        if h.status_code != 200:
            return ""
    except requests.RequestException:
        return ""

    sections: list[str] = []

    try:
        br = requests.get(f"{base}/v1/briefing", timeout=20)
        if br.ok:
            data = br.json()
            briefing = (data.get("briefing") or "").strip()
            if briefing:
                sections.append(
                    "### Session briefing (Engram HTTP)\n\n"
                    + briefing[:12000]
                    + ("\n\n_(truncated)_" if len(briefing) > 12000 else "")
                )
    except requests.RequestException as e:
        logger.warning("Engram /v1/briefing failed: {}", e)

    seed = (recall_seed or "").strip()[:2000]
    if seed:
        try:
            rc = requests.get(
                f"{base}/v1/memories/recall",
                params={"context": seed, "limit": 10},
                timeout=20,
            )
            if rc.ok:
                mems = rc.json().get("memories") or []
                if mems:
                    lines = []
                    for m in mems:
                        typ = m.get("type") or "?"
                        content = (m.get("content") or "").strip().replace("\r\n", "\n")
                        if not content:
                            continue
                        lines.append(f"- **{typ}**: {content[:900]}")
                    if lines:
                        body = "\n".join(lines[:15])
                        sections.append(
                            "### Relevant memories (Engram HTTP recall)\n\n"
                            + body
                            + ("\n\n_(truncated)_" if len(lines) > 15 else "")
                        )
        except requests.RequestException as e:
            logger.warning("Engram /v1/memories/recall failed: {}", e)

    if not sections:
        return ""
    logger.info("Engram: loaded {} section(s) via HTTP {}", len(sections), base)
    return "\n\n".join(sections)


def build_agent_prompt_addon(
    settings: Settings,
    *,
    recall_seed: str,
    workspace_path: str,
) -> str:
    """
    Append persistent-memory text to the agent prompt.

    1) **Engram CLI** (`engram` on PATH) — same vault Cursor uses for MCP; runs in ``workspace_path``
       so project detection matches the cloned repo. No `engram serve` required.
    2) If that yields nothing and ``ENGRAM_REST_URL`` is set, try the **HTTP** API (npm-style server).
    """
    if not settings.engram_prompt_injection:
        return ""

    body = _addon_from_cli(settings, recall_seed=recall_seed, workspace_path=workspace_path)
    if not body:
        body = _addon_from_http(settings, recall_seed=recall_seed)
    if not body:
        if _cli_exe(settings):
            logger.debug("Engram CLI ran but returned no context/search hits for this run.")
        elif _base_url(settings):
            logger.debug("Engram HTTP not reachable or empty at {}.", _base_url(settings))
        else:
            logger.info(
                "Engram preload skipped: install `engram` CLI on PATH or set ENGRAM_REST_URL "
                "(see .env.example)."
            )
        return ""

    intro = (
        "The following comes from **Engram** (persistent memory — same store as your IDE when using "
        "the Engram CLI/MCP). Prefer aligning your fix with these facts when they clearly apply. "
        "If Claude Code also has Engram MCP enabled, you can **save** important outcomes after the fix.\n\n"
    )
    return intro + body
