"""Clone and refresh a single Bitbucket repository per issue run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from config import Settings
from models.issue_models import JiraIssue, WorkspaceContext


def _redact_clone_url(url: str) -> str:
    """Strip userinfo from logged clone URL (may contain credentials)."""
    if "@" not in url or "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _userinfo, _, hostpath = rest.partition("@")
    return f"{scheme}://***@{hostpath}"


def resolve_repo(settings: Settings, _issue: JiraIssue) -> str:
    return settings.git_clone_url()


def clone_repo(settings: Settings, repo_url: str, issue_key: str) -> str:
    base = Path(settings.workspace_root) / issue_key / "repo"
    if base.exists():
        shutil.rmtree(base)
    base.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning into {}", base)
    cp = subprocess.run(
        ["git", "clone", repo_url, str(base)],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        err = (cp.stderr or "").strip() or (cp.stdout or "").strip()
        logger.error(
            "git clone failed for {} (exit {}). URL: {}\n{}",
            issue_key,
            cp.returncode,
            _redact_clone_url(repo_url),
            err[:8000],
        )
        raise subprocess.CalledProcessError(
            cp.returncode,
            ["git", "clone", _redact_clone_url(repo_url), str(base)],
            output=cp.stdout,
            stderr=cp.stderr,
        )
    return str(base.resolve())


def checkout_default_branch(settings: Settings, path: str) -> None:
    b = settings.default_branch
    subprocess.run(
        ["git", "-C", path, "fetch", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", path, "checkout", b],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", path, "reset", "--hard", f"origin/{b}"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", path, "clean", "-fd"],
        check=True,
        capture_output=True,
        text=True,
    )


def prepare_workspace(settings: Settings, issue: JiraIssue) -> WorkspaceContext:
    url = resolve_repo(settings, issue)
    path = clone_repo(settings, url, issue.key)
    checkout_default_branch(settings, path)
    return WorkspaceContext(
        repo_url=url,
        local_path=path,
        default_branch=settings.default_branch,
    )
