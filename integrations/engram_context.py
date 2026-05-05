"""Optional Engram REST preload for the agent prompt (local engram-serve)."""

from __future__ import annotations

import requests
from loguru import logger

from config import Settings


def _base_url(settings: Settings) -> str:
    raw = (settings.engram_rest_url or "").strip()
    return raw.rstrip("/")


def build_agent_prompt_addon(settings: Settings, *, recall_seed: str) -> str:
    """
    Fetch briefing + semantic recall from Engram's HTTP API and return markdown to append
    to the agent prompt. Empty string if disabled or server unreachable.

    Requires a running local server, e.g. `npx engram-serve` (default http://127.0.0.1:3800).
    """
    if not settings.engram_prompt_injection:
        return ""
    base = _base_url(settings)
    if not base:
        return ""

    try:
        h = requests.get(f"{base}/health", timeout=2)
        if h.status_code != 200:
            logger.debug("Engram health check non-200 at {}; skipping preload", base)
            return ""
    except requests.RequestException:
        logger.info(
            "Engram not reachable at {} (start `npx engram-serve` or set ENGRAM_REST_URL); "
            "continuing without memory preload.",
            base,
        )
        return ""

    sections: list[str] = []

    try:
        br = requests.get(f"{base}/v1/briefing", timeout=20)
        if br.ok:
            data = br.json()
            briefing = (data.get("briefing") or "").strip()
            if briefing:
                sections.append(
                    "### Session briefing (Engram)\n\n"
                    + briefing[:12000]
                    + ("\n\n_(truncated)_" if len(briefing) > 12000 else "")
                )
    except requests.RequestException as e:
        logger.warning("Engram /v1/briefing failed: {}", e)

    seed = (recall_seed or "").strip()[:2000]
    if seed:
        try:
            rc = requests.get(
                f"{base}/v1/memories/recall",
                params={"context": seed, "limit": 10},
                timeout=20,
            )
            if rc.ok:
                mems = rc.json().get("memories") or []
                if mems:
                    lines = []
                    for m in mems:
                        typ = m.get("type") or "?"
                        content = (m.get("content") or "").strip().replace("\r\n", "\n")
                        if not content:
                            continue
                        lines.append(f"- **{typ}**: {content[:900]}")
                    if lines:
                        body = "\n".join(lines[:15])
                        sections.append(
                            "### Relevant memories for this issue (Engram recall)\n\n"
                            + body
                            + ("\n\n_(truncated)_" if len(lines) > 15 else "")
                        )
        except requests.RequestException as e:
            logger.warning("Engram /v1/memories/recall failed: {}", e)

    if not sections:
        return ""

    intro = (
        "The following comes from **Engram** (persistent memory). "
        "Prefer facts here when they apply to this codebase or team conventions. "
        "If your Claude session also has Engram MCP tools, use them to **remember** "
        "important outcomes after you finish.\n\n"
    )
    return intro + "\n\n".join(sections)
