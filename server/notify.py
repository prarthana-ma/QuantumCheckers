"""Optional, non-blocking Discord notifications for game lifecycle events."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
_DELIVERY_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qcheckers-notify")
_DELIVERY_TIMEOUT_SECONDS = 3.0


def build_embed(event: str, details: Mapping[str, Any]) -> dict[str, Any]:
    """Build a credential-free Discord embed for a game lifecycle event."""
    game_id = str(details.get("game_id", "unknown"))
    if event == "game_created":
        description = (
            f"Game `{game_id}` created "
            f"(level {details.get('level', 'unknown')}, "
            f"mode {details.get('mode', 'unknown')}, "
            f"seed {details.get('seed', 'unknown')})."
        )
        fields: list[dict[str, Any]] = []
        color = 0x5865F2
        label = "Game created"
    elif event == "game_over":
        winner = details.get("result")
        result = "Draw" if winner is None else f"Player {winner} won"
        try:
            duration = f"{float(details.get('duration_s', 0.0)):.1f}s"
        except (TypeError, ValueError, OverflowError):
            duration = "unknown"
        description = (
            f"{result} in `{game_id}` after {details.get('moves', 0)} moves "
            f"({duration})."
        )
        fields = [
            {"name": "Level", "value": str(details.get("level", "unknown")), "inline": True},
            {"name": "Mode", "value": str(details.get("mode", "unknown")), "inline": True},
            {"name": "Reason", "value": str(details.get("reason", "unknown")), "inline": True},
            {"name": "Seed", "value": str(details.get("seed", "unknown")), "inline": True},
        ]
        color = 0x57F287 if winner is not None else 0xFEE75C
        label = "Game over"
    else:
        raise ValueError(f"unsupported notification event {event!r}")

    embed: dict[str, Any] = {
        "title": f"Quantum Checkers — {label}",
        "description": description,
        "color": color,
    }
    if fields:
        embed["fields"] = fields
    return embed


class Notifier:
    """Fire-and-forget Discord webhook delivery with bounded network waits."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = (webhook_url or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    def game_created(self, **details: Any) -> None:
        self._submit("game_created", details)

    def game_over(self, **details: Any) -> None:
        self._submit("game_over", details)

    def _submit(self, event: str, details: Mapping[str, Any]) -> None:
        if not self.enabled:
            return
        payload = {"embeds": [build_embed(event, details)]}
        _DELIVERY_POOL.submit(self._deliver, payload)

    def _deliver(self, payload: Mapping[str, Any]) -> None:
        request = Request(
            self._webhook_url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "QuantumCheckers/1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=_DELIVERY_TIMEOUT_SECONDS) as response:
                if not 200 <= response.status < 300:
                    logger.warning(
                        "Discord notification returned HTTP status %s", response.status
                    )
        except (OSError, URLError, TimeoutError) as error:
            logger.warning(
                "Discord notification delivery failed (%s)", type(error).__name__
            )


def notifier_from_env(webhook_url: str | None = None) -> Notifier:
    """Use an explicit URL when provided, otherwise read the server environment."""
    configured_url = (
        webhook_url if webhook_url is not None else os.environ.get("DISCORD_WEBHOOK_URL", "")
    )
    return Notifier(configured_url)


__all__ = ["Notifier", "build_embed", "notifier_from_env"]
