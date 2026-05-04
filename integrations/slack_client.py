"""Optional Slack incoming webhook."""

from __future__ import annotations

from typing import Optional

import requests
from loguru import logger


def post_message(webhook_url: Optional[str], text: str) -> None:
    if not webhook_url:
        return
    try:
        r = requests.post(webhook_url, json={"text": text}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        logger.warning("Slack webhook failed: {}", e)
