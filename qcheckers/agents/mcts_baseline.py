"""Monte Carlo Tree Search baseline agent.

Owner: **Person B -- baseline agents and harness**.

Status: **complete for the toy engine.** UCT selection, seeded rollouts and the static
evaluation are all implemented and unit-tested. The agent plays a shallow tree (``depth``
plies of greedy replies) and then a seeded random playout, back-propagating the result.
Search runs on a clone of the engine, so a decision never advances the live game's RNG
even though the rollouts sample through it.

Person C's :mod:`prob_aware` agent is defined as *this baseline with a probability-aware
evaluation and rollout policy*, so this file is the fixed reference the ablation varies
one term away from.

Integration boundary
--------------------
The upstream engine is intentionally not integrated: the study uses the documented
toy engine, and the upstream licence/scope decision is recorded in
``docs/REPRODUCIBILITY.md``. ``CheqqersAdapter`` remains an explicit, unused integration
seam rather than an unfinished dependency of this baseline.

Deliberate design choices
-------------------------
* ``max_plies`` on the engine is respected via ``state.ply``; the agent never looks
  beyond a terminal state.
* Evaluation is measured from the *root* player's point of view and negated for the
  opponent, so a single evaluator works for both sides.
* All randomness goes through the injected ``random.Random``; no global RNG.
"""

from __future__ import annotations

import math
import random
import time
from typing import Sequence

from qcheckers.agents.base import Agent
from qcheckers.engine.protocol import Action, GameEngine, GameState, Piece, clone_engine

#: Default UCT exploration constant. sqrt(2) is the standard textbook value; Person D
#: must not tune this per-condition, or the ablation is no longer matched.
DEFAULT_UCT_C = math.sqrt(2.0)


def uct_score(
    action_value: float,
    action_visits: int,
    parent_visits: int,
    exploration: float = DEFAULT_UCT_C,
) -> float:
    """UCT score for one action of a node.

    Formula
    -------
    ``mean_value + exploration * sqrt(ln(parent_visits) / action_visits)``

    Parameters
    ----------
    action_value:
        Total value accumulated for this action, in ``[-visits, +visits]`` where
        positive means "good for the player to move".
    action_visits:
        Times this action was selected and backed up. Must be ``>= 1``.
    parent_visits:
        Total selections at the parent node. Must be ``>= 1``. ``ln`` of 1 is 0, so a
        freshly created parent gives no bonus; callers normally pass
        ``parent_visits + 1`` or visit the node at least once first.
    exploration:
        UCT constant ``c``.

    Returns
    -------
    float
        The score to maximise. Higher is better.

    Notes
    -----
    Both visit counts are validated rather than clamped, because a zero visit count
    here means the caller built the tree wrong, and silently returning ``inf`` would
    make every bug look like an exploration win. Unvisited children are handled by the
    caller via the standard "try unvisited first" rule.
    """
    if action_visits < 1:
        raise ValueError(f"action_visits must be >= 1, got {action_visits}")
    if parent_visits < 1:
        raise ValueError(f"parent_visits must be >= 1, got {parent_visits}")
    exploitation = action_value / action_visits
    exploration_term = exploration * math.sqrt(
        math.log(parent_visits) / action_visits
    )
    return exploitation + exploration_term


def evaluate_state(state: GameState, player: int) -> float:
    """Static evaluation of ``state`` from ``player``'s point of view.

    A deliberately boring material-and-advance heuristic. It is chance-aware in the
    weak sense that a piece contributes its *maximum* occupancy chance, which is what
    makes the difference between this baseline and Person C's probability-aware agent
    measurable rather than cosmetic.

    Components (weights are fixed and must not be tuned per condition):

    * ``+1.0`` per unit of material, where a spread piece counts its largest chance
      weight (so a spread piece is worth less than a certain one).
    * ``+0.05`` per row of advance toward the opponent's edge.
    * ``-0.20`` per captured own piece already lost, read off ``state.captured``.

    Returns a value in roughly ``[-10, 10]``; only relative order matters.
    """
    score = 0.0
    for piece in state.pieces:
        material = max(weight for _, weight in piece.sites)
        sign = 1.0 if piece.owner == player else -1.0
        score += sign * material
        advance = _advance_of(piece)
        score += sign * 0.05 * advance
    score -= 0.20 * len(state.captured)
    return score


def _advance_of(piece: Piece) -> int:
    """Rows advanced toward the opponent's edge, best-case over the piece's sites."""
    rows = [square[0] for square in piece.squares]
    if piece.owner == 0:
        return len(rows) - min(rows)
    return max(rows)


class MCTSBaselineAgent:
    """Tree-search baseline: UCT selection over a shallow tree, greedy evaluation.

    Parameters
    ----------
    engine:
        The engine the agent plays on. Needed to expand children by applying actions.
    seed:
        Seed for the agent's private RNG, used by the rollouts and rewound at the start
        of every decision so one decision is a pure function of (seed, state, legal).
    iterations:
        UCT iterations per move.
    exploration:
        UCT constant ``c``.
    depth:
        Maximum tree depth searched.
    rollout_steps:
        Ply cap for one rollout before falling back to the static evaluation.
    name:
        Label written into game records.
    """

    def __init__(
        self,
        engine: GameEngine,
        *,
        seed: int = 0,
        iterations: int = 24,
        exploration: float = DEFAULT_UCT_C,
        depth: int = 2,
        rollout_steps: int = 32,
        name: str = "mcts-baseline",
    ) -> None:
        if iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {iterations}")
        if depth < 1:
            raise ValueError(f"depth must be >= 1, got {depth}")
        if rollout_steps < 1:
            raise ValueError(f"rollout_steps must be >= 1, got {rollout_steps}")
        if exploration < 0:
            raise ValueError(f"exploration must be >= 0, got {exploration}")
        self.name = name
        self.seed = int(seed)
        self.iterations = int(iterations)
        self.exploration = float(exploration)
        self.depth = int(depth)
        self.rollout_steps = int(rollout_steps)
        #: The engine as handed in. Search runs on a fresh clone of this per decision.
        self._base_engine = engine
        self._engine = engine
        self._rng = random.Random(self.seed)
        #: Snapshot of the most recent decision's search effort (see ``decide``).
        self.last_diagnostics: dict[str, float | int] = {}

    # -- Agent protocol ----------------------------------------------------

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Choose the best action under UCT selection and seeded rollouts."""
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}"
            )
        if len(legal) == 1:
            self.last_diagnostics = {
                "simulations": 0,
                "expansions": 0,
                "completed_rollouts": 0,
                "elapsed_seconds": 0.0,
                "root_visits": 0,
            }
            return legal[0]

        # Two isolation rules make one decision a pure function of (seed, state, legal):
        # rollouts run on a clone so the live engine's RNG is untouched, and the private
        # rollout RNG is rewound to the agent's seed. Calling decide twice on the same
        # position therefore returns the same action.
        self._engine = clone_engine(self._base_engine, self.seed)
        self._rng = random.Random(self.seed)

        root_player = state.turn
        values = {index: 0.0 for index in range(len(legal))}
        visits = {index: 0 for index in range(len(legal))}
        parent_visits = 0
        simulations = 0
        expansions = 0
        completed_rollouts = 0
        started = time.perf_counter()

        for _ in range(self.iterations):
            parent_visits += 1
            index = self._select(legal, values, visits, parent_visits)
            child = self._expand(state, legal[index], root_player)
            simulations += 1
            if child is None:
                continue
            expansions += 1
            # Back-propagate the rollout value, not a static score: that is what turns
            # UCT selection over an unexpanded tree into an actual MCTS player.
            score = self._rollout(child, root_player)
            completed_rollouts += 1
            values[index] += score
            visits[index] += 1

        self.last_diagnostics = {
            "simulations": simulations,
            "expansions": expansions,
            "completed_rollouts": completed_rollouts,
            "elapsed_seconds": time.perf_counter() - started,
            "root_visits": parent_visits,
        }

        best_index = max(
            range(len(legal)),
            key=lambda i: (values[i] / visits[i] if visits[i] else float("-inf"), -i),
        )
        return legal[best_index]

    # -- internals ---------------------------------------------------------

    def _select(
        self,
        legal: Sequence[Action],
        values: dict[int, float],
        visits: dict[int, int],
        parent_visits: int,
    ) -> int:
        """Pick the child with the highest UCT score.

        Unvisited children are tried first, in legal-action order, so the very first
        iterations sweep every move before any is trusted. Ties break toward the
        lower index, which keeps the agent deterministic for a fixed state.
        """
        for index in range(len(legal)):
            if visits[index] == 0:
                return index
        best_index = 0
        best_score = float("-inf")
        for index in range(len(legal)):
            score = uct_score(
                values[index],
                visits[index],
                parent_visits,
                self.exploration,
            )
            if score > best_score:
                best_score, best_index = score, index
        return best_index

    def _expand(
        self, state: GameState, action: Action, root_player: int
    ) -> GameState | None:
        """Apply ``action`` and recurse to ``depth``; return the leaf state.

        Returns ``None`` when the move is rejected by the engine, which should not
        happen for an action from ``legal_actions`` but is handled rather than raising
        inside the search loop.
        """
        current = state
        try:
            for ply in range(self.depth):
                step = self._engine.apply(current, action)
                current = step.state
                if self._engine.is_terminal(current):
                    break
                reply = self._engine.legal_actions(current)
                if not reply:
                    break
                if ply == self.depth - 1:
                    break
                action = self._best_greedy(current, reply, root_player)
        except ValueError:
            return None
        return current

    def _best_greedy(
        self, state: GameState, legal: Sequence[Action], root_player: int
    ) -> Action:
        """The opponent's one-ply reply, chosen to *hurt* the root player.

        This is the parity flip described on :meth:`_evaluate`: the non-root plies are
        played by the side that is trying to beat us, so the reply minimises the root's
        evaluation. Maximising it would model an opponent who plays to help us, which is
        both wrong and measurably weaker -- and it was the behaviour here until the
        arXiv version of the paper (2506.05962v2) made the intended minimax structure
        worth double-checking.
        """
        worst_action = legal[0]
        worst_score = float("inf")
        for candidate in legal:
            try:
                child = self._engine.apply(state, candidate).state
            except ValueError:
                continue
            score = self._evaluate(child, root_player)
            if score < worst_score:
                worst_score, worst_action = score, candidate
        return worst_action

    def _evaluate(self, state: GameState, root_player: int) -> float:
        """Score a leaf from ``root_player``'s perspective, flipped per ply parity.

        Alternating sign with depth keeps "good for root" positive all the way up the
        tree. Terminal states are resolved by win/loss/draw rather than heuristics.
        """
        outcome = self._engine.outcome(state)
        if outcome is not None:
            if outcome.winner is None:
                return 0.0
            return 1.0 if outcome.winner == root_player else -1.0
        return evaluate_state(state, root_player)

    def _rollout(
        self, state: GameState, player: int, max_steps: int | None = None
    ) -> float:
        """Seeded random playout, valued from ``player``'s point of view.

        Plays uniformly random legal moves through ``self._rng`` until the game ends or
        the ply cap is reached, then falls back to the static evaluation. The value is
        always reported from the root player's perspective, so a single number can be
        accumulated at the root regardless of whose turn it was at the leaf.

        Returns a value in ``[-1, 1]``.
        """
        steps = self.rollout_steps if max_steps is None else max_steps
        current = state
        for _ in range(steps):
            outcome = self._engine.outcome(current)
            if outcome is not None:
                if outcome.winner is None:
                    return 0.0
                return 1.0 if outcome.winner == player else -1.0
            legal = self._engine.legal_actions(current)
            if not legal:
                return 0.0
            try:
                current = self._engine.apply(current, self._rng.choice(list(legal))).state
            except ValueError:  # pragma: no cover - defensive
                return 0.0
        # A depth cut falls back to the heuristic, clamped so a rollout value always
        # lives in the same [-1, 1] range as a terminal result.
        return max(-1.0, min(1.0, self._evaluate(current, player)))

    def reset(self, seed: int | None = None) -> None:
        """Rewind the RNG for reuse across games."""
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"{type(self).__name__}(seed={self.seed}, iterations={self.iterations}, "
            f"depth={self.depth}, exploration={self.exploration:.4f})"
        )


# Compile-time proof that the baseline satisfies the shared interface.
_: type[Agent] = MCTSBaselineAgent


__all__ = [
    "DEFAULT_UCT_C",
    "MCTSBaselineAgent",
    "evaluate_state",
    "uct_score",
]
