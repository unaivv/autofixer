"""Named pipeline states for logging and future persistence."""

from __future__ import annotations

from enum import Enum


class PipelineState(str, Enum):
    IDLE = "IDLE"
    FETCH_JIRA_ISSUES = "FETCH_JIRA_ISSUES"
    CLASSIFY_ISSUE = "CLASSIFY_ISSUE"
    PREPARE_WORKSPACE = "PREPARE_WORKSPACE"
    BUILD_CONTEXT = "BUILD_CONTEXT"
    RUN_AGENT_FIX = "RUN_AGENT_FIX"
    VALIDATE_PATCH = "VALIDATE_PATCH"
    RETRY_FIX = "RETRY_FIX"
    CONFIDENCE_CHECK = "CONFIDENCE_CHECK"
    CREATE_BRANCH_AND_PR = "CREATE_BRANCH_AND_PR"
    COMMENT_JIRA = "COMMENT_JIRA"
    REPORT_RESULTS = "REPORT_RESULTS"
    END = "END"
