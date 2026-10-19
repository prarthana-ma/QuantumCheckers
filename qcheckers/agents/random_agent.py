"""Seeded random baseline agent.

Owner: **Person B -- baseline agents and harness**.

This is the floor baseline the whole study is measured against: a uniform random legal
move, drawn from a private seeded ``random.Random``. It is deliberately *not* using the
global ``random`` module, because every experiment in this repo must be reproducible
from a seed alone.
"""

from __future__ import annotations

import random
from typing import Sequence

from qcheckers.agents.base import Agent
from qcheckers.engine.protocol import Action, GameState


class RandomAgent:
    """Uniformly random over the legal actions.

    Parameters
    ----------
    seed:
        Seed for this agent's private RNG. Two agents with the same seed and the same
        legal-action list produce the same move sequence.
    name:
        Label written into every :class:`~qcheckers.experiment.schema.GameRecord`.
    """

    def __init__(self, seed: int = 0, *, name: str = "random") -> None:
        self.name = name
        self.seed = int(seed)
        self._rng = random.Random(self.seed)
        self._usage: dict[str, int] = {}

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Return one uniformly chosen legal action."""
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}; "
                "the runner should have stopped the game already"
            )
        action = self._rng.choice(list(legal))
        kind = getattr(action, "kind", "unknown")
        self._usage[kind] = self._usage.get(kind, 0) + 1
        return action

    def usage(self) -> dict[str, int]:
        """Action-kind counts observed across this agent's decisions."""
        return dict(self._usage)

    def reset(self, seed: int | None = None) -> None:
        """Rewind the RNG so an agent can be reused for a fresh game."""
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)
        self._usage.clear()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(seed={self.seed}, name={self.name!r})"


# Compile-time proof that the baseline satisfies the shared interface.
_: type[Agent] = RandomAgent


__all__ = ["RandomAgent"]