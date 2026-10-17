"""Random baseline agent for QuantumCheckers.

A valid, reproducible baseline that selects uniformly from the engine's legal
actions. No heuristics, no lookahead — purely random. Uses an injected, seedable
RNG so runs are reproducible and independent of global random state.

Reproducibility: the same seed, initial state, and legal-action sequence produce
the same action choices. Engine-internal randomness (e.g. collapse outcomes) is
owned by the engine and may vary across engine implementations.
"""

from __future__ import annotations

import random
from typing import Sequence

from qcheckers.agents.base import Agent, fallback_action
from qcheckers.engine.protocol import Action, GameState


class RandomAgent:
    """Uniform-random legal action selector.

    Parameters
    ----------
    seed:
        Seed for the agent's private RNG. Each game should use a distinct seed for
        independence.
    name:
        Label written into game records.
    """

    def __init__(self, *, seed: int = 0, name: str = "random") -> None:
        self.name = name
        self.seed = int(seed)
        self._rng = random.Random(self.seed)

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Select uniformly at random from ``legal``.

        Raises ValueError if ``legal`` is empty (the engine should never call decide
        on a terminal state, but this is a defensive check).
        """
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}"
            )
        return self._rng.choice(list(legal))

    def reset(self, seed: int | None = None) -> None:
        """Reset the RNG for a new game. If ``seed`` is given, reseed."""
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)

    def usage(self) -> dict[str, int]:
        """No special counters for the random agent."""
        return {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(seed={self.seed}, name={self.name!r})"


# Compile-time proof that the agent satisfies the shared interface.
_: type[Agent] = RandomAgent


__all__ = ["RandomAgent"]
