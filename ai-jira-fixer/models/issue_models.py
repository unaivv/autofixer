from __future__ import annotations

from pydantic import BaseModel, Field


class JiraIssue(BaseModel):
    key: str
    summary: str
    description: str
    comments: list[str]
    labels: list[str]
    priority: str
    components: list[str]
    attachments: list[str]
    raw: dict = Field(default_factory=dict, repr=False)


class ClassificationResult(BaseModel):
    eligible: bool
    score: int
    reasons: list[str]


class WorkspaceContext(BaseModel):
    repo_url: str
    local_path: str
    default_branch: str


class ClaudeExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    confidence: int
    files_changed: int
    lines_changed: int


class ValidationResult(BaseModel):
    lint_passed: bool
    tests_passed: bool
    build_passed: bool
    logs: str
    files_changed: int
    lines_changed: int


class PullRequestResult(BaseModel):
    pr_url: str
    branch_name: str
    commit_hash: str
