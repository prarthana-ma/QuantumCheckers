"""Optional Discord notifications for game creation and game over.

Owner: **P5 -- rules, engine, harness and batches**.

Design rules (from the project addendum):

* Read ``DISCORD_WEBHOOK_URL`` from the environment. **Unset or empty means disabled**,
  and a disabled notifier is a no-op that never schedules anything.
* Only two events, ``game_created`` and ``game_over``. No per-move logging, no chat, no
  secrets -- the webhook URL itself is never included in a payload.
* A notification **can never delay or fail a game**. It is dispatched with
  ``loop.create_task`` from the request handler, and every exception inside the send is
  swallowed. A slow or dead webhook leaves the game completely unaffected.

Nothing here is imported by the engine, the runner or the tests' hot paths, so turning
the hook off removes even the import cost.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Mapping

#: Embed colour (matches the client's player-0 blue).
EMBED_COLOR = 0x1F5FBF

#: Fields copied into the embed, in display order. Duration and moves are only present
#: on the game-over event.
_FIELD_ORDER = (
    "level",
    "mode",
    "result",
    "reason",
    "moves",
    "duration_s",
    "seed",
    "game_id",
)


def build_embed(kind: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Turn an event plus its fields into one Discord embed (JSON-ready).

    Kept as a pure function so the payload shape is unit-testable without any network.
    """
    titles = {
        "game_created": "Quantum Checkers \u2014 game created",
        "game_over": "Quantum Checkers \u2014 game over",
    }
    lines: list[str] = []
    for key in _FIELD_ORDER:
        value = fields.get(key)
        if value is None or value == "":
            continue
        if key == "duration_s":
            lines.append(f"**duration**: {value:.1f}s")
        else:
            lines.append(f"**{key}**: {value}")
    return {
        "title": titles.get(kind, f"Quantum Checkers \u2014 {kind}"),
        "description": "\n".join(lines)[:3900] or "\u2014",
        "color": EMBED_COLOR,
    }


@dataclass
class Notifier:
    """Fire-and-forget Discord notifier.

    ``url`` empty/``None`` disables the hook entirely.
    """

    url: str | None = None

    def __post_init__(self) -> None:
        self.url = (self.url or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def game_created(self, **fields: Any) -> None:
        self.fire("game_created", fields)

    def game_over(self, **fields: Any) -> None:
        self.fire("game_over", fields)

    def fire(self, kind: str, fields: Mapping[str, Any]) -> None:
        """Schedule one notification, or do nothing when disabled.

        Never raises: no running loop, no httpx, a dead webhook, or a 4xx all leave the
        game untouched.
        """
        if not self.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # no loop (e.g. called from a sync context): skip silently
            return
        try:
            loop.create_task(self._post(kind, dict(fields)))
        except Exception:  # pragma: no cover - defensive
            return

    async def _post(self, kind: str, fields: Mapping[str, Any]) -> None:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    str(self.url), json={"embeds": [build_embed(kind, fields)]}
                )
        except Exception:
            # Swallow everything: the notification is best-effort by contract.
            return


def notifier_from_env(explicit: str | None = None) -> Notifier:
    """Build a notifier from an explicit value, else ``DISCORD_WEBHOOK_URL``.

    Passing ``""`` explicitly disables the hook even when the environment variable is
    set, which is what the tests use.
    """
    if explicit is None:
        explicit = os.environ.get("DISCORD_WEBHOOK_URL")
    return Notifier(explicit)


__all__ = ["EMBED_COLOR", "Notifier", "build_embed", "notifier_from_env"]
