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
    suffix = retry_prompt.read_text(encoding="utf-8") + "\n\n## Validation logs\n\n" + validation.logs
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
        )
    val = patch_validator.validate(settings, workspace.local_path)
    return cr, val
