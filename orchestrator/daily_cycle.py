"""Top-level daily (or manual) run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from config import Settings, get_settings
from integrations import jira_client
from orchestrator import issue_pipeline
from reporting.daily_reporter import DailySummary, send_summary

_file_log_sink_id: Optional[int] = None


def run_daily_cycle(settings: Optional[Settings] = None) -> None:
    global _file_log_sink_id
    settings = settings or get_settings()
    repo_root = Path(__file__).resolve().parent.parent

    (repo_root / "logs").mkdir(parents=True, exist_ok=True)
    # Avoid stacking multiple file sinks if this process runs the cycle more than once.
    if _file_log_sink_id is None:
        _file_log_sink_id = logger.add(
            repo_root / "logs" / "app.log",
            rotation="10 MB",
            retention="14 days",
            level="INFO",
        )

    summary = DailySummary()
    issues = jira_client.fetch_candidate_issues(settings)
    logger.info("Fetched {} candidate issues", len(issues))

    for issue in issues[: settings.max_daily_issues]:
        issue_pipeline.process_single_issue(settings, issue, summary, repo_root)

    send_summary(settings, summary, repo_root)
