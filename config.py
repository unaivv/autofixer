"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_workspace_root() -> str:
    """Use OS temp dir (works on Windows; avoids /tmp which is awkward there)."""
    return str(Path(tempfile.gettempdir()) / "ai_agent_runs")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    atlassian_email: str = Field(validation_alias="ATLASSIAN_EMAIL")
    atlassian_api_token: str = Field(validation_alias="ATLASSIAN_API_TOKEN")

    jira_base_url: str = Field(validation_alias="JIRA_BASE_URL")
    jira_project: str = Field(default="APP", validation_alias="JIRA_PROJECT")
    jira_issue_type: str = Field(default="Bug", validation_alias="JIRA_ISSUE_TYPE")
    jira_status: str = Field(default="To Do", validation_alias="JIRA_STATUS")
    jira_label_ai_fixable: str = Field(
        default="ai-fixable",
        validation_alias="JIRA_LABEL_AI_FIXABLE",
    )
    jira_jql: Optional[str] = Field(default=None, validation_alias="JIRA_JQL")
    jira_transition_in_review: str = Field(
        default="In Review",
        validation_alias="JIRA_TRANSITION_IN_REVIEW",
    )

    bitbucket_workspace: str = Field(validation_alias="BITBUCKET_WORKSPACE")
    bitbucket_repo_slug: str = Field(validation_alias="BITBUCKET_REPO_SLUG")
    bitbucket_git_clone_url: Optional[str] = Field(
        default=None,
        validation_alias="BITBUCKET_GIT_CLONE_URL",
    )
    # HTTPS git user: default = ATLASSIAN_EMAIL (URL-encoded). Use Bitbucket *username* with app passwords.
    # Use literal "x-token-auth" only for repository/workspace access tokens that require it.
    bitbucket_git_https_username: Optional[str] = Field(
        default=None,
        validation_alias="BITBUCKET_GIT_HTTPS_USERNAME",
    )
    # Bitbucket "Repository" / "Workspace" access token for Git HTTPS (recommended when ATATT
    # account token is rejected for git clone). User = x-token-auth, password = this token.
    bitbucket_git_access_token: Optional[str] = Field(
        default=None,
        validation_alias="BITBUCKET_GIT_ACCESS_TOKEN",
    )

    workspace_root: str = Field(
        default_factory=_default_workspace_root,
        validation_alias="WORKSPACE_ROOT",
    )
    max_daily_issues: int = Field(default=5, validation_alias="MAX_DAILY_ISSUES")
    default_branch: str = Field(default="develop", validation_alias="DEFAULT_BRANCH")
    pr_target_branch: str = Field(
        default="develop",
        validation_alias="PR_TARGET_BRANCH",
    )

    agent_command: str = Field(
        default="claude run --dangerously-skip-permissions",
        validation_alias="AGENT_COMMAND",
    )

    docker_node_image: str = Field(
        default="node:20-bookworm",
        validation_alias="DOCKER_NODE_IMAGE",
    )

    dry_run: bool = Field(default=False, validation_alias="DRY_RUN")
    slack_webhook: Optional[str] = Field(default=None, validation_alias="SLACK_WEBHOOK")

    max_files_changed: int = Field(default=50, validation_alias="MAX_FILES_CHANGED")
    max_lines_changed: int = Field(
        default=5000,
        validation_alias="MAX_LINES_CHANGED",
    )
    classifier_min_score: int = Field(
        default=60,
        validation_alias="CLASSIFIER_MIN_SCORE",
    )
    confidence_min_approve: int = Field(
        default=80,
        validation_alias="CONFIDENCE_MIN_APPROVE",
    )

    @computed_field
    @property
    def jira_rest_base(self) -> str:
        return self.jira_base_url.rstrip("/")

    @computed_field
    @property
    def bitbucket_rest_base(self) -> str:
        return "https://api.bitbucket.org/2.0"

    def built_jql(self) -> str:
        if self.jira_jql and self.jira_jql.strip():
            return self.jira_jql.strip()
        label = self.jira_label_ai_fixable.replace('"', '\\"')
        return (
            f'project = {self.jira_project} '
            f'AND issuetype = "{self.jira_issue_type}" '
            f'AND status = "{self.jira_status}" '
            f'AND labels = "{label}" '
            f"ORDER BY created ASC"
        )

    def _git_https_username_part(self) -> str:
        from urllib.parse import quote

        raw = (self.bitbucket_git_https_username or "").strip()
        if raw.lower() == "x-token-auth":
            return "x-token-auth"
        if raw:
            return quote(raw, safe="")
        # Atlassian account API tokens (ATATT…) authenticate to Bitbucket Git over HTTPS
        # like the REST API: email + token — not x-token-auth (that pattern is for other token types).
        return quote(self.atlassian_email, safe="")

    def git_clone_url(self) -> str:
        if self.bitbucket_git_clone_url:
            return self.bitbucket_git_clone_url.strip()
        from urllib.parse import quote

        # Do not use quote(..., safe="") on the token: '=' must stay literal for Atlassian API tokens.
        _token_literal = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            "-._~+/="
        )
        ws = self.bitbucket_workspace
        slug = self.bitbucket_repo_slug

        bb_git = (self.bitbucket_git_access_token or "").strip()
        if bb_git:
            tok = quote(bb_git, safe=_token_literal)
            user = "x-token-auth"
        else:
            tok = quote(self.atlassian_api_token, safe=_token_literal)
            user = self._git_https_username_part()

        return f"https://{user}:{tok}@bitbucket.org/{ws}/{slug}.git"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
