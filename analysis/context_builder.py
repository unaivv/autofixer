"""Build issue_context.md for the coding agent."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from models.issue_models import JiraIssue, WorkspaceContext


def scan_repo_tree(path: str, max_entries: int = 200) -> str:
    lines: list[str] = []
    root = Path(path)
    count = 0
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if any(part in {".git", "node_modules", "dist", "build", ".next"} for part in rel.parts):
            continue
        lines.append(str(rel))
        count += 1
        if count >= max_entries:
            lines.append("... (truncated)")
            break
    return "\n".join(lines)


_SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next"}
_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2",
    ".zip", ".tar", ".gz", ".pdf", ".exe", ".dll", ".so", ".dylib",
}


def _grep_python(root: str, term: str, max_lines: int = 20) -> str:
    """Fallback when ripgrep/grep are not installed (typical on Windows)."""
    lines_out: list[str] = []
    root_path = Path(root).resolve()
    count = 0
    term_lower = term.lower()
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if count >= max_lines:
                break
            fp = Path(dirpath) / fn
            if fp.suffix.lower() in _BINARY_EXT:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if term_lower not in text.lower():
                continue
            rel = fp.relative_to(root_path)
            for i, line in enumerate(text.splitlines(), 1):
                if term_lower in line.lower() and count < max_lines:
                    lines_out.append(f"{rel}:{i}:{line[:240]}")
                    count += 1
                    if count >= max_lines:
                        break
        if count >= max_lines:
            break
    return "\n".join(lines_out)


def _grep_one_term(path: str, term: str) -> str:
    rg = shutil.which("rg")
    if rg:
        cp = subprocess.run(
            [rg, "--line-number", "--max-count", "20", term, path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return (cp.stdout or "").strip()
    grep_bin = shutil.which("grep")
    if grep_bin:
        cp = subprocess.run(
            [grep_bin, "-RIn", "--max-count=20", term, path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return (cp.stdout or "").strip()
    return _grep_python(path, term, max_lines=20)


def grep_keywords(path: str, issue: JiraIssue, max_hits: int = 80) -> str:
    terms: list[str] = []
    for chunk in (issue.summary, issue.description):
        for w in chunk.split():
            w = w.strip(".,:;()[]{}`'\"")
            if len(w) >= 5 and w.isalnum():
                terms.append(w)
    terms = list(dict.fromkeys(terms))[:12]
    if not terms:
        return "(no keywords for search)"
    hits: list[str] = []
    for t in terms:
        block = _grep_one_term(path, t)
        if block:
            hits.append(f"## matches for `{t}`\n```\n{block[:8000]}\n```")
        if len(hits) * 20 >= max_hits:
            break
    return "\n\n".join(hits) if hits else "(no keyword search hits)"


def collect_recent_commits(path: str, limit: int = 30) -> str:
    cp = subprocess.run(
        ["git", "-C", path, "log", f"-{limit}", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (cp.stdout or "").strip()


def locate_tests(path: str) -> str:
    patterns = ("**/*.test.*", "**/*.spec.*", "**/__tests__/**", "**/test/**")
    found: list[str] = []
    root = Path(path)
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file() and "node_modules" not in p.parts:
                found.append(str(p.relative_to(root)))
        if len(found) > 120:
            break
    return "\n".join(found[:120]) if found else "(no obvious test files found)"


def build(issue: JiraIssue, workspace: WorkspaceContext) -> str:
    path = workspace.local_path
    ctx = Path(path) / "issue_context.md"
    body = [
        "# Jira issue",
        f"Key: {issue.key}",
        f"Summary: {issue.summary}",
        "",
        "## Description",
        issue.description or "(empty)",
        "",
        "## Comments",
        "\n\n".join(issue.comments) if issue.comments else "(none)",
        "",
        "## Labels / priority / components",
        f"- labels: {issue.labels}",
        f"- priority: {issue.priority}",
        f"- components: {issue.components}",
        "",
        "## Repository snapshot",
        "### Tree (partial)",
        "```",
        scan_repo_tree(path),
        "```",
        "",
        "### Recent commits",
        "```",
        collect_recent_commits(path),
        "```",
        "",
        "### Likely tests",
        "```",
        locate_tests(path),
        "```",
        "",
        "### Keyword search",
        grep_keywords(path, issue),
        "",
        "## Raw issue JSON (truncated)",
        "```json",
        json.dumps(issue.raw, indent=2)[:12000],
        "```",
    ]
    text = "\n".join(body)
    ctx.write_text(text, encoding="utf-8")
    logger.info("Wrote {}", ctx)
    return str(ctx)
