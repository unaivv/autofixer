"""Console-oriented phase logging with elapsed time (long-running steps stay visible)."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from loguru import logger


@contextmanager
def issue_phase(issue_key: str, description: str) -> Generator[None, None, None]:
    """Log start/finish (or abort) and wall time for a pipeline block."""
    logger.info("[{}] Starting — {}", issue_key, description)
    t0 = time.monotonic()
    try:
        yield
    except BaseException:
        logger.info(
            "[{}] Stopped after {:.1f}s — {}",
            issue_key,
            time.monotonic() - t0,
            description,
        )
        raise
    else:
        logger.info(
            "[{}] Done in {:.1f}s — {}",
            issue_key,
            time.monotonic() - t0,
            description,
        )
