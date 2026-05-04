"""End-of-run summary to console and optional Slack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from loguru import logger

from config import Settings
from integrations.slack_client import post_message


@dataclass
class DailySummary:
    processed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    prs: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "AI BUGFIX RUN SUMMARY",
            f"Processed: {len(self.processed)}",
            f"Skipped (classifier): {len(self.skipped)}",
            f"Failed / no PR: {len(self.failed)}",
            f"PRs created: {len(self.prs)}",
            "",
            "PR links:" if self.prs else "No PRs this run.",
        ]
        lines.extend(self.prs)
        return "\n".join(lines)


def send_summary(settings: Settings, summary: DailySummary, repo_root: Path) -> None:
    text = summary.render()
    # One multi-line copy for humans (stdout); loguru stays one-line to avoid double blocks in the terminal.
    print(text, flush=True)
    summary_path = repo_root / "logs" / f"run_summary_{date.today().isoformat()}.txt"
    summary_path.write_text(text + "\n", encoding="utf-8")
    logger.info(
        "Run finished — processed={} skipped={} failed={} prs={} (summary file: {})",
        len(summary.processed),
        len(summary.skipped),
        len(summary.failed),
        len(summary.prs),
        summary_path.name,
    )
    post_message(settings.slack_webhook, text)
