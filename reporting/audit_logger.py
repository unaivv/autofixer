"""Structured filesystem audit trail per issue and per day."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from loguru import logger


class AuditLogger:
    def __init__(self, root: Path, issue_key: str) -> None:
        day = date.today().isoformat()
        self.base = root / "logs" / day / issue_key
        self.base.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, content: str) -> Path:
        p = self.base / name
        p.write_text(content, encoding="utf-8")
        logger.debug("audit {}", p)
        return p

    def write_json(self, name: str, obj: object) -> Path:
        p = self.base / name
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return p
