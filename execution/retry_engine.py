"""Single retry path after failed validation."""

from __future__ import annotations

from pathlib import Path

from config import Settings
from integrations import claude_runner
from models.issue_models import ClaudeExecutionResult, JiraIssue, ValidationResult, WorkspaceContext
from execution import patch_validator


def retry(
    settings: Settings,
    issue: JiraIssue,
    workspace: WorkspaceContext,
    context_file: str,
    validation: ValidationResult,
) -> tuple[ClaudeExecutionResult, ValidationResult]:
    retry_prompt = Path(__file__).resolve().parent.parent / "prompts" / "retry_fix_prompt.md"
    scope_block = ""
    if validation.turbo_validation_packages:
        pkgs = ", ".join(validation.turbo_validation_packages)
        scope_block = (
            "## Which packages failed CI here\n\n"
            f"Docker only ran lint/test/build for: **{pkgs}** (Turborepo `--filter`). "
            "Fix the failures **in those workspace packages** (source + their tests under the same tree). "
            "Do **not** chase unrelated apps (for example `apps/web`) unless the log line names that package "
            "as the failing task **and** your diff already touches it.\n\n"
        )
    suffix = (
        retry_prompt.read_text(encoding="utf-8")
        + "\n\n"
        + scope_block
        + "## Validation logs\n\n"
        + validation.logs
    )
    try:
        cr = claude_runner.run_fix(
            settings,
            context_file,
            workspace,
            extra_prompt_suffix=suffix,
            recall_seed=f"{issue.key} {issue.summary}",
        )
    except (RuntimeError, FileNotFoundError, OSError) as e:
        cr = ClaudeExecutionResult(
            success=False,
            stdout="",
            stderr=str(e),
            confidence=0,
            files_changed=0,
            lines_changed=0,
            quota_or_rate_limited=claude_runner.agent_output_suggests_quota_or_rate_limit(str(e)),
        )
    if cr.quota_or_rate_limited:
        return cr, validation
    val = patch_validator.validate(settings, workspace.local_path)
    return cr, val
