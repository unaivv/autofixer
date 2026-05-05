"""Jira Cloud REST client (search, comments, transitions)."""

from __future__ import annotations

import json
from typing import Any

import requests
from loguru import logger

from config import Settings
from models.issue_models import JiraIssue


def _auth(settings: Settings) -> tuple[str, str]:
    return settings.atlassian_email, settings.atlassian_api_token


def _adf_to_plain(adf: Any) -> str:
    if adf is None:
        return ""
    if isinstance(adf, str):
        return adf
    if not isinstance(adf, dict):
        return str(adf)
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and "text" in node:
                parts.append(str(node["text"]))
            for c in node.get("content") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(adf.get("content"))
    return "\n".join(parts).strip() or json.dumps(adf)[:8000]


def _parse_issue(fields: dict[str, Any], raw_issue: dict[str, Any]) -> JiraIssue:
    desc = fields.get("description")
    description = desc if isinstance(desc, str) else _adf_to_plain(desc)

    comment_bodies: list[str] = []
    c_raw = fields.get("comment")
    if isinstance(c_raw, dict):
        iterable = c_raw.get("comments") or []
    elif isinstance(c_raw, list):
        iterable = c_raw
    else:
        iterable = []
    for c in iterable:
        if not isinstance(c, dict):
            continue
        body = c.get("body")
        if isinstance(body, str):
            comment_bodies.append(body)
        else:
            comment_bodies.append(_adf_to_plain(body))

    priority = (fields.get("priority") or {}).get("name") or ""
    components = [c.get("name", "") for c in (fields.get("components") or [])]
    labels = list(fields.get("labels") or [])
    att = fields.get("attachment") or []
    if isinstance(att, list):
        attachments = [a.get("filename", "") for a in att if isinstance(a, dict)]
    else:
        attachments = []

    return JiraIssue(
        key=raw_issue.get("key", ""),
        summary=fields.get("summary") or "",
        description=description,
        comments=comment_bodies,
        labels=labels,
        priority=priority,
        components=components,
        attachments=attachments,
        raw=raw_issue,
    )


def fetch_candidate_issues(settings: Settings) -> list[JiraIssue]:
    """Use enhanced JQL search; legacy GET /rest/api/3/search returns 410 Gone on Jira Cloud."""
    jql = settings.built_jql()
    url = f"{settings.jira_rest_base}/rest/api/3/search/jql"
    params = {
        "jql": jql,
        "maxResults": settings.max_daily_issues,
        "fields": "summary,description,comment,labels,priority,components",
    }
    logger.info("Jira enhanced search JQL: {}", jql)
    logger.info("Jira: GET {} ...", url)
    resp = requests.get(url, params=params, auth=_auth(settings), timeout=120)
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("issues")
    if rows is None:
        logger.warning("Unexpected Jira search payload keys: {}", list(data.keys()))
        rows = []
    issues: list[JiraIssue] = []
    for item in rows:
        fields = item.get("fields") or {}
        issues.append(_parse_issue(fields, item))
    return issues


def add_comment(settings: Settings, issue_key: str, body: str) -> None:
    url = f"{settings.jira_rest_base}/rest/api/3/issue/{issue_key}/comment"
    payload = {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}]}}
    resp = requests.post(url, json=payload, auth=_auth(settings), timeout=60)
    resp.raise_for_status()


def transition_issue(settings: Settings, issue_key: str, target_status_name: str) -> None:
    t_url = f"{settings.jira_rest_base}/rest/api/3/issue/{issue_key}/transitions"
    r = requests.get(t_url, auth=_auth(settings), timeout=60)
    r.raise_for_status()
    transitions = (r.json().get("transitions")) or []
    tid = None
    target_lower = target_status_name.strip().lower()
    for t in transitions:
        name = (t.get("to") or {}).get("name") or t.get("name") or ""
        if name.strip().lower() == target_lower:
            tid = t.get("id")
            break
    if not tid:
        names = [(t.get("to") or {}).get("name") for t in transitions]
        raise RuntimeError(
            f"No transition found to '{target_status_name}'. Available targets: {names}"
        )
    p_url = f"{settings.jira_rest_base}/rest/api/3/issue/{issue_key}/transitions"
    payload = {"transition": {"id": tid}}
    pr = requests.post(p_url, json=payload, auth=_auth(settings), timeout=60)
    pr.raise_for_status()
    logger.info("Jira {} transitioned toward '{}'", issue_key, target_status_name)
