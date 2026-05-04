"""Heuristic eligibility scoring for Jira issues."""

from __future__ import annotations

import re

from config import Settings
from models.issue_models import ClassificationResult, JiraIssue

_STACK_HINTS = re.compile(
    r"(traceback|stack trace|exception|error:|at \w+\.\w+\(|Caused by:)",
    re.IGNORECASE,
)
_REPRO_HINTS = re.compile(
    r"(steps to reproduce|reproduc|actual result|expected result)",
    re.IGNORECASE,
)
_DB_KEYWORDS = re.compile(
    r"\b(migration|migrate|schema change|alter table)\b",
    re.IGNORECASE,
)
_SECURITY_KEYWORDS = re.compile(
    r"\b(auth|login|password|permission|rbac|oauth|token leak|security)\b",
    re.IGNORECASE,
)
_BLACKLIST = re.compile(
    r"(billing critical|production outage|permissions escalation)",
    re.IGNORECASE,
)


def classify(settings: Settings, issue: JiraIssue) -> ClassificationResult:
    reasons: list[str] = []
    score = 0
    blob = "\n".join(
        [issue.summary, issue.description, *issue.comments],
    )

    if _BLACKLIST.search(blob):
        return ClassificationResult(
            eligible=False,
            score=0,
            reasons=["Matched conservative blacklist phrase"],
        )

    if _STACK_HINTS.search(blob):
        score += 20
        reasons.append("stacktrace-like signal (+20)")
    if _REPRO_HINTS.search(blob):
        score += 15
        reasons.append("repro hints (+15)")

    # Single-repo product: treat as one repo match (+20)
    score += 20
    reasons.append("single configured repository (+20)")

    if not _DB_KEYWORDS.search(blob):
        score += 20
        reasons.append("no DB migration keywords (+20)")
    else:
        reasons.append("DB migration keywords detected (no +20)")

    if not _SECURITY_KEYWORDS.search(blob):
        score += 20
        reasons.append("no obvious security/auth keywords (+20)")
    else:
        reasons.append("security/auth keywords detected (no +20)")

    # crude scope estimate: tolerate more path-like strings (web tickets often list files)
    pathish = len(re.findall(r"[/\\][\w.\-/\\]+\.\w+", blob))
    if pathish < 15:
        score += 15
        reasons.append("small scope heuristic (+15)")
    else:
        reasons.append("many path-like strings (no +15)")

    eligible = score >= settings.classifier_min_score
    return ClassificationResult(eligible=eligible, score=score, reasons=reasons)
