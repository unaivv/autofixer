"""Clone and refresh a single Bitbucket repository per issue run."""

from __future__ import annotations

import errno
import os
import shutil
import stat
import subprocess
import tempfile
import time
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


def _chmod_bits() -> int:
    """Flags for os.chmod; Windows needs write (+ read/exec for dirs) to drop read-only from git."""
    if os.name == "nt":
        return stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC
    return stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO


def _avoid_cwd_inside_tree(path: Path) -> None:
    """Windows: rmtree fails if the process cwd is inside the directory being removed."""
    if os.name != "nt":
        return
    try:
        target = path.resolve()
        cwd = Path.cwd().resolve()
    except OSError:
        return
    if cwd == target or target in cwd.parents:
        try:
            os.chdir(tempfile.gettempdir())
        except OSError:
            try:
                os.chdir(str(Path.home()))
            except OSError:
                pass


def _transient_rmtree_exc(exc: OSError) -> bool:
    """True if retrying the whole rmtree may succeed (locks, indexer, antivirus)."""
    if os.name == "nt":
        we = getattr(exc, "winerror", None)
        if we in (32, 33):  # sharing / lock violation
            return True
        if we == 5:  # access denied — often transient when another handle closes
            return True
    return exc.errno in (errno.EACCES, errno.EPERM, errno.EBUSY, errno.EAGAIN)


def _force_rmtree(path: Path, *, max_attempts: int = 6) -> None:
    """Remove a tree; Windows: read-only git files, cwd-inside-tree, transient file locks."""

    def _chmod_and_retry(func, p, _exc_info):
        try:
            os.chmod(p, _chmod_bits())
            func(p)
        except OSError:
            raise

    if not path.exists():
        return
    path = path.resolve()
    logger.debug("Removing tree {}", path)
    last: OSError | None = None
    for attempt in range(max_attempts):
        _avoid_cwd_inside_tree(path)
        try:
            shutil.rmtree(path, onerror=_chmod_and_retry)
            return
        except OSError as e:
            last = e
            if _transient_rmtree_exc(e) and attempt + 1 < max_attempts:
                time.sleep(0.35 * (attempt + 1))
                continue
            raise
    if last:
        raise last


def clone_repo(settings: Settings, repo_url: str, issue_key: str) -> str:
    base = Path(settings.workspace_root).expanduser().resolve() / issue_key / "repo"
    if base.exists():
        logger.info("Removing previous clone at {}", base)
        _force_rmtree(base)
    base.parent.mkdir(parents=True, exist_ok=True)
    logger.info("git clone -> {} (quiet; network speed dominates)", base)
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
    logger.info("git fetch origin (quiet)...")
    subprocess.run(
        ["git", "-C", path, "fetch", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info("git checkout {} + reset --hard origin/{}", b, b)
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
