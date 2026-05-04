"""Post success comments on Jira issues (English)."""

from __future__ import annotations

from config import Settings
from integrations import jira_client
from models.issue_models import JiraIssue, PullRequestResult, ValidationResult


def comment_success(
    settings: Settings,
    issue: JiraIssue,
    pr: PullRequestResult,
    validation: ValidationResult,
) -> None:
    body = (
        "The AI agent generated a candidate automated fix.\n\n"
        f"PR: {pr.pr_url}\n\n"
        "Validation (in Docker):\n"
        f"- lint: {'PASS' if validation.lint_passed else 'FAIL'}\n"
        f"- tests: {'PASS' if validation.tests_passed else 'FAIL'}\n"
        f"- build: {'PASS' if validation.build_passed else 'FAIL'}\n\n"
        "Awaiting engineering review."
    )
    jira_client.add_comment(settings, issue.key, body)
