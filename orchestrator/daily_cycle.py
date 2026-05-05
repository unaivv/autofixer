"""Top-level daily (or manual) run."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from config import Settings, get_settings
from integrations import jira_client
from orchestrator import issue_pipeline
from reporting.daily_reporter import DailySummary, send_summary

_logging_configured: bool = False


def _ensure_logging(repo_root: Path) -> None:
    """Readable console timestamps + full detail in app.log (configure once)."""
    global _logging_configured
    if _logging_configured:
        return
    (repo_root / "logs").mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
        colorize=True,
    )
    logger.add(
        repo_root / "logs" / "app.log",
        rotation="10 MB",
        retention="14 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
    )
    _logging_configured = True


def run_daily_cycle(settings: Optional[Settings] = None) -> None:
    settings = settings or get_settings()
    repo_root = Path(__file__).resolve().parent.parent
    _ensure_logging(repo_root)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except OSError:
            pass

    summary = DailySummary()
    logger.info("Requesting candidate issues from Jira (HTTP, up to ~120s timeout)...")
    issues = jira_client.fetch_candidate_issues(settings)
    logger.info("Fetched {} candidate issue(s) from Jira", len(issues))

    batch = issues[: settings.max_daily_issues]
    total = len(batch)
    for i, issue in enumerate(batch, start=1):
        logger.info("=== Issue {} of {}: {} — {} ===", i, total, issue.key, issue.summary[:80])
        issue_pipeline.process_single_issue(settings, issue, summary, repo_root)

    send_summary(settings, summary, repo_root)
