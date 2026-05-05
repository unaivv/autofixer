"""Single-issue processing pipeline."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from analysis import confidence_engine, context_builder, issue_classifier
from config import Settings
from execution import patch_validator, retry_engine
from integrations import bitbucket_client, claude_runner, jira_client
from models.issue_models import JiraIssue
from orchestrator.progress import issue_phase
from reporting.audit_logger import AuditLogger
from reporting.daily_reporter import DailySummary
from reporting.jira_commenter import comment_success
from workspace import repo_manager


def _validation_ok(v) -> bool:
    return bool(v.lint_passed and v.tests_passed and v.build_passed)


def _operator_alert(settings: Settings, audit: AuditLogger, title: str, detail: str) -> None:
    msg = f"{title}\n\n{detail}"
    logger.error(msg)
    print(f"\n*** OPERATOR ALERT ***\n{msg}\n")
    audit.write("OPERATOR_ALERT.txt", msg)


def process_single_issue(
    settings: Settings,
    issue: JiraIssue,
    summary: DailySummary,
    repo_root: Path,
) -> None:
    audit = AuditLogger(repo_root, issue.key)
    audit.write_json("jira_issue.json", issue.model_dump())
    summary.processed.append(issue.key)

    with issue_phase(issue.key, "Classifier (eligibility + score)"):
        classification = issue_classifier.classify(settings, issue)
        audit.write("classification.txt", classification.model_dump_json(indent=2))
    if not classification.eligible:
        logger.info(
            "Skipping {} — classifier score {} (< {}). Reasons: {}",
            issue.key,
            classification.score,
            settings.classifier_min_score,
            "; ".join(classification.reasons),
        )
        summary.skipped.append(issue.key)
        return

    try:
        with issue_phase(issue.key, "Workspace: git clone + checkout default branch"):
            workspace = repo_manager.prepare_workspace(settings, issue)
    except Exception as e:
        _operator_alert(settings, audit, f"Workspace prep failed for {issue.key}", repr(e))
        summary.failed.append(issue.key)
        return

    audit.write("workspace.txt", workspace.model_dump_json())

    try:
        with issue_phase(
            issue.key,
            "Context: issue_context.md (tree, commits, tests, keyword search — slow on large monorepos)",
        ):
            ctx_path = context_builder.build(issue, workspace)
            audit.write("issue_context.md", Path(ctx_path).read_text(encoding="utf-8"))
    except Exception as e:
        _operator_alert(settings, audit, f"Context build failed for {issue.key}", repr(e))
        summary.failed.append(issue.key)
        return

    try:
        with issue_phase(issue.key, "Agent: coding CLI (live stream if AGENT_STREAM_OUTPUT=true)"):
            claude_result = claude_runner.run_fix(
                settings,
                ctx_path,
                workspace,
                recall_seed=f"{issue.key} {issue.summary}",
            )
    except (RuntimeError, FileNotFoundError, OSError) as e:
        _operator_alert(settings, audit, f"Agent launcher failed for {issue.key}", str(e))
        summary.failed.append(issue.key)
        return
    audit.write("agent_stdout.txt", claude_result.stdout)
    audit.write("agent_stderr.txt", claude_result.stderr)
    audit.write_json("agent_result.json", claude_result.model_dump())

    with issue_phase(issue.key, "Docker: lint / test / build in Node container (often several minutes)"):
        validation = patch_validator.validate(settings, workspace.local_path)
    audit.write("validation_logs.txt", validation.logs)

    if not _validation_ok(validation):
        with issue_phase(issue.key, "Retry: second agent pass + Docker validation"):
            claude_result, validation = retry_engine.retry(
                settings, issue, workspace, ctx_path, validation
            )
        audit.write("retry_agent_stdout.txt", claude_result.stdout)
        audit.write("retry_agent_stderr.txt", claude_result.stderr)
        audit.write("retry_validation_logs.txt", validation.logs)

    if not _validation_ok(validation):
        _operator_alert(
            settings,
            audit,
            f"Validation failed for {issue.key}",
            validation.logs[-8000:],
        )
        summary.failed.append(issue.key)
        return

    if not confidence_engine.approve(settings, claude_result, validation):
        _operator_alert(
            settings,
            audit,
            f"Confidence gate rejected {issue.key}",
            claude_result.model_dump_json(),
        )
        summary.failed.append(issue.key)
        return

    if validation.files_changed == 0:
        _operator_alert(
            settings,
            audit,
            f"No code changes produced for {issue.key}",
            "The agent did not modify tracked files vs HEAD.",
        )
        summary.failed.append(issue.key)
        return

    branch = bitbucket_client.branch_name_for_issue(issue)
    try:
        with issue_phase(issue.key, "Publish: git branch, commit, push, Bitbucket pull request"):
            pr = bitbucket_client.publish_pr(
                settings,
                issue,
                workspace.local_path,
                branch,
                claude_result,
                validation,
            )
    except Exception as e:
        _operator_alert(
            settings,
            audit,
            f"PR publish failed for {issue.key}",
            repr(e),
        )
        summary.failed.append(issue.key)
        return

    audit.write_json("pull_request.json", pr.model_dump())
    summary.prs.append(pr.pr_url)

    if settings.dry_run:
        logger.info("DRY_RUN: skipping Jira success comment and transition for {}", issue.key)
        return

    with issue_phase(issue.key, "Jira: comment on issue + workflow transition"):
        try:
            comment_success(settings, issue, pr, validation)
        except Exception as e:
            _operator_alert(
                settings,
                audit,
                f"Jira comment failed for {issue.key} (PR exists: {pr.pr_url})",
                repr(e),
            )

        try:
            jira_client.transition_issue(
                settings,
                issue.key,
                settings.jira_transition_in_review,
            )
        except Exception as e:
            _operator_alert(
                settings,
                audit,
                f"Jira transition failed for {issue.key}",
                repr(e),
            )
