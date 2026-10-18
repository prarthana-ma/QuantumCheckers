"""Person C -- the voluntary-measurement (Observe) agent.

**NOVELTY PENDING GATE 5.** Nothing in this file is a validated result, and no claim
that Observe is novel may be made until the full paper and follow-up literature have
been read. See ``docs/quantum-checkers-project.md`` sections 11, 16 (Gate 5) and 18.

Owner: **Person C -- Observe and probability-aware search**. Nobody else may edit this
file or the ``observe`` branch of the engine's legality rules.

Hypothesis
----------
Giving an agent an explicit choice to resolve one of its own pieces' uncertainty --
rather than letting a capture force the resolution -- should change three measurable
things: how often collapses happen, how long games run, and the draw rate. The brief
predicts that a negative win-rate result here is an acceptable, credible outcome
(section 21, "What if the result is negative?").

Design, stated explicitly because the brief requires it
-------------------------------------------------------
* **What Observe does.** Selects one uncertain piece of the agent's own and resolves
  it using *the engine's own chance rule*. The agent never invents probabilities and
  never calls ``random`` for this: it delegates to ``engine.apply``, so the sampled
  square is logged as a real :class:`~qcheckers.engine.protocol.CollapseEvent` with
  ``cause="observe"``.
* **Cost.** Costs the turn, exactly like any other action. This is stated in
  :class:`~qcheckers.engine.protocol.ObserveAction` too, so the two never drift.
* **When it is legal.** Only when the engine was built with ``allow_observe=True`` and
  the chosen piece is genuinely spread. On a classical board there is nothing to
  observe, so the agent degenerates to the greedy move chooser.
* **What is revealed.** The full pre-collapse distribution is available to the agent
  before it decides, and both the distribution and the sampled outcome are written to
  the game log.

Current state: **implemented baseline heuristic.** The agent satisfies the
:class:`~qcheckers.agents.base.Agent` protocol and participates in the reported
experiments. Its threshold policy is deliberately simple and fixed before the ablation;
it is not presented as an optimized strategy. The research novelty assessment remains
pending because the follow-up literature search is narrow.
"""

from __future__ import annotations

from typing import Sequence

from qcheckers.agents.base import Agent, fallback_action
from qcheckers.engine.protocol import (
    Action,
    GameEngine,
    GameState,
    ObserveAction,
    Piece,
)

#: Probability below which this agent stops caring about resolving a piece.
#: Chosen as an obvious placeholder (0.5 == "coin flip"), not tuned. Changing it after
#: seeing results invalidates the ablation, so it lives here as a named constant.
UNCERTAINTY_FLOOR = 0.5


class ObserveAgent:
    """Optional-measurement agent: observe a spread piece when it is a coin flip.

    Parameters
    ----------
    engine:
        Engine to query for legality. Must be built with ``allow_observe=True`` for
        Observe moves to ever be legal.
    threshold:
        Observe when a piece's largest occupancy chance is at or below this value.
        Lowering it makes the agent more measurement-happy.
    name:
        Label written into game records.
    """

    def __init__(
        self,
        engine: GameEngine,
        *,
        threshold: float = UNCERTAINTY_FLOOR,
        name: str = "observe-agent",
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1]; got {threshold!r}")
        self.name = name
        self.threshold = float(threshold)
        self._engine = engine
        #: Counters the runner / scripts read for the usage plots.
        self.observe_moves = 0
        self.board_moves = 0

    # -- Agent protocol ----------------------------------------------------

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Observe the fuzziest own piece, else play the first legal action."""
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}"
            )

        observe_moves = [a for a in legal if isinstance(a, ObserveAction)]
        if observe_moves:
            target = self._fuzziest(state, [a.piece_id for a in observe_moves])
            if target is not None:
                for action in observe_moves:
                    if action.piece_id == target:
                        self.observe_moves += 1
                        return action

        # Declining to observe must mean declining to observe: fall back among the
        # non-Observe actions, so an Observe action cannot be selected by accident just
        # because the engine happened to list it first.
        board_actions = [a for a in legal if not isinstance(a, ObserveAction)]
        pool = board_actions or legal
        chosen = fallback_action(pool, preferred="capture")
        self.board_moves += 1
        return chosen

    # -- internals ---------------------------------------------------------

    def _fuzziest(self, state: GameState, candidates: Sequence[str]) -> str | None:
        """Piece id whose largest occupancy chance is lowest, if it is uncertain enough.

        Returns ``None`` when every candidate is already more certain than
        ``threshold``, which is the "do not spend a turn on measurement" decision.
        """
        eligible: list[Piece] = []
        for piece_id in candidates:
            try:
                piece = state.piece(piece_id)
            except KeyError:  # pragma: no cover - defensive
                continue
            if not piece.is_spread:
                continue
            if max(weight for _, weight in piece.sites) <= self.threshold:
                eligible.append(piece)
        if not eligible:
            return None
        eligible.sort(key=lambda p: (max(w for _, w in p.sites), p.piece_id))
        return eligible[0].piece_id

    def usage(self) -> dict[str, int]:
        """Counters for the quantum-move-usage plot."""
        return {"observe": self.observe_moves, "board": self.board_moves}

    def reset(self) -> None:
        """Zero the usage counters for a fresh condition."""
        self.observe_moves = 0
        self.board_moves = 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(threshold={self.threshold}, name={self.name!r})"


# Compile-time proof that the agent satisfies the shared interface.
_: type[Agent] = ObserveAgent


__all__ = ["ObserveAgent", "UNCERTAINTY_FLOOR"]
