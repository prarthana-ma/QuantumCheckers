"""Agent protocol and shared helpers.

P1's agents and P3's baselines both implement :class:`Agent`. The protocol is
intentionally minimal so any engine-playing agent can plug into the runner.

Conventions
-----------
* ``decide(state, legal)`` receives the current state and the engine's legal-action
  list, and returns one of those actions. Returning anything else is a bug.
* Agents that need randomness receive a private, seedable RNG — never the global
  ``random`` module — so runs are reproducible.
* ``reset()`` returns the agent to a clean state between games.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from qcheckers.engine.protocol import Action, GameState


@runtime_checkable
class Agent(Protocol):
    """The common agent interface. Implementations must provide these members."""

    #: Stable label written into game records.
    name: str

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Choose one action from ``legal`` for the current ``state``."""
        ...

    def reset(self) -> None:
        """Reset any per-game state (counters, caches, RNG)."""
        ...


def fallback_action(
    pool: Sequence[Action], *, preferred: str | None = "capture"
) -> Action:
    """Pick an action from ``pool``, preferring ``preferred`` kind when present.

    Falls back to the first action of any kind. Used by agents that need a simple,
    deterministic last-resort chooser. Raises ``ValueError`` for an empty pool.
    """
    if not pool:
        raise ValueError("fallback_action received an empty action pool")
    if preferred is not None:
        for action in pool:
            if getattr(action, "kind", None) == preferred:
                return action
    return pool[0]


__all__ = ["Agent", "fallback_action"]
