"""Post-validation approval gate."""

from __future__ import annotations

from config import Settings
from models.issue_models import ClaudeExecutionResult, ValidationResult


def approve(
    settings: Settings,
    claude_result: ClaudeExecutionResult,
    validation: ValidationResult,
) -> bool:
    score = 0
    if validation.tests_passed:
        score += 30
    if validation.lint_passed:
        score += 20
    if validation.build_passed:
        score += 20
    if validation.files_changed <= 3:
        score += 10
    elif validation.files_changed <= 8:
        score += 5
    if validation.lines_changed <= 150:
        score += 10
    elif validation.lines_changed <= 400:
        score += 5
    if claude_result.confidence >= 80:
        score += 10
    elif claude_result.confidence >= 60:
        score += 5

    return score >= settings.confidence_min_approve
