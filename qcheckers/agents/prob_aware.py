"""Person C -- probability-aware search agent.

**NOVELTY PENDING GATE 5.** Do not present this as new work, and do not claim generic
tree search or probability display as novel (brief sections 7 and 11). The only
candidate contribution is the probability-aware *modification* under the
voluntary-measurement condition, and only if the literature search finds no overlap.

Owner: **Person C**. Nobody else may edit this file.

Hypothesis
----------
A baseline that scores a board by treating uncertain pieces as if they were on their
most likely square will systematically mis-evaluate positions where a spread piece
matters. Scoring instead by the *expected* outcome over the distribution should produce
measurably different move choices, and under the Observe condition it should change
collapse frequency and draw rate.

What "probability-aware" means here, concretely
-----------------------------------------------
Three things that are all different from :mod:`qcheckers.agents.mcts_baseline`, and
nothing else:

1. :func:`expected_evaluation` replaces the baseline's max-chance material term with the
   weighted sum over every site a piece occupies. Advance weight and capture penalty are
   byte-identical, so the ablation isolates exactly one changed term.
2. The **rollout policy samples from the engine's chance rule** rather than uniformly:
   an action is drawn with weight equal to ``Piece.chance_at`` on the acting square, so
   a piece that is only 25% likely to be on a square is only 25% as likely to act from
   it. The paper's stated open problem (section VII: "simply averages over the rollouts")
   is exactly this averaging choice.
3. Terminal leaves inside a rollout are valued with :func:`expected_evaluation`, so the
   search never falls back to the uncertainty-ignoring heuristic.

The game-tier Hard policy
-------------------------
The browser game's Hard tier needs to *demonstrably* use the voluntary Observe action,
so :class:`ProbAwareAgent` accepts two documented, off-by-default options:
``observe_threshold`` (resolve a coin-flip ghost when no capture is available) and
``split_eager`` (open with a split so there is something to observe). Both are
**disabled in every research condition** -- the ablation constructs its agents without
them -- so the measured `prob` arm stays the plain probability-aware search. The server
enables them only for ``ai-hard``.
"""

from __future__ import annotations

import random
from typing import Sequence

from qcheckers.agents.base import Agent
from qcheckers.agents.mcts_baseline import DEFAULT_UCT_C, uct_score
from qcheckers.engine.protocol import (
    Action,
    GameEngine,
    GameState,
    ObserveAction,
    Piece,
    SpreadAction,
    Square,
    clone_engine,
)

#: Weight of the advance term. Identical to the baseline's 0.05 on purpose.
ADVANCE_WEIGHT = 0.05

#: Weight of the lost-piece term. Identical to the baseline's 0.20 on purpose.
CAPTURE_PENALTY = 0.20

#: Default observe eagerness for the **game-tier** Hard policy. 0.5 means "a coin flip
#: is not worth keeping"; it is a named constant so it cannot drift silently, and it is
#: never used by a research condition.
HARD_OBSERVE_FLOOR = 0.5

#: Depth of the shallow greedy search used inside one UCT expansion.
DEFAULT_DEPTH = 2

#: Ply cap for one rollout.
DEFAULT_ROLLOUT_STEPS = 32


def _square_value(square: Square, owner: int, board_size: int) -> float:
    """Heuristic value of occupying ``square`` for ``owner``.

    Linear in advance toward the opponent's edge, normalised to ``[0, 1]`` so that a
    one-row step is worth the same 0.05 everywhere on the board.
    """
    row = square[0]
    if owner == 0:
        progress = (board_size - 1 - row) / max(board_size - 1, 1)
    else:
        progress = row / max(board_size - 1, 1)
    return progress


def expected_material(state: GameState, owner: int, board_size: int) -> float:
    """Chance-weighted sum of ``owner``'s positions.

    For each piece, sum ``weight * advance_value(square)`` over all its sites. A piece
    split between two squares contributes the weighted average of both, which is
    strictly between the two certain-piece values -- the property Person C's ablation
    depends on, and the reason this is not just a rename of the baseline heuristic.

    Sign is positive for ``owner``; callers compare across owners, so this returns the
    signed contribution of ``owner``'s pieces only.
    """
    total = 0.0
    for piece in state.pieces_of(owner):
        for square, weight in piece.sites:
            total += weight * _square_value(square, owner, board_size)
    return total


def expected_evaluation(state: GameState, player: int, board_size: int) -> float:
    """Chance-aware static evaluation of ``state`` from ``player``'s point of view.

    Compared to :func:`qcheckers.agents.mcts_baseline.evaluate_state`, exactly one
    term differs: material uses the weighted mean over a piece's sites rather than its
    single largest chance. Everything else -- advance weight, capture penalty -- is
    held constant so the ablation is single-variable.
    """
    score = 0.0
    for piece in state.pieces:
        sign = 1.0 if piece.owner == player else -1.0
        # Chance-aware material: weight each site by its probability.
        material = sum(
            weight * (1.0 + _square_value(square, piece.owner, board_size))
            for square, weight in piece.sites
        )
        score += sign * material
        rows = [square[0] for square in piece.squares]
        advance = (len(rows) - min(rows)) if piece.owner == 0 else max(rows)
        score += sign * ADVANCE_WEIGHT * advance
    score -= CAPTURE_PENALTY * len(state.captured)
    return score


class ProbAwareAgent:
    """Probability-aware UCT search agent.

    Parameters
    ----------
    engine:
        Engine used to expand and evaluate child states.
    seed:
        Seed for the agent's private RNG (rollout action sampling).
    exploration:
        UCT constant carried over from the baseline so the two agents stay matched.
    iterations:
        UCT iterations per move.
    depth:
        Maximum tree depth searched before the rollout starts.
    rollout_steps:
        Ply cap for one rollout.
    name:
        Label written into game records.
    observe_threshold:
        **Game-tier only.** When not ``None``, resolve an own spread piece whose largest
        chance is at or below this value, provided no capture is available. Research
        conditions leave it ``None``.
    split_eager:
        **Game-tier only.** When true and the agent has no spread piece, prefer a split
        over a quiet move so the Observe policy has something to work with. Research
        conditions leave it false.
    """

    def __init__(
        self,
        engine: GameEngine,
        *,
        seed: int = 0,
        exploration: float = DEFAULT_UCT_C,
        iterations: int = 24,
        depth: int = DEFAULT_DEPTH,
        rollout_steps: int = DEFAULT_ROLLOUT_STEPS,
        name: str = "prob-aware",
        observe_threshold: float | None = None,
        split_eager: bool = False,
    ) -> None:
        if iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {iterations}")
        if depth < 1:
            raise ValueError(f"depth must be >= 1, got {depth}")
        if rollout_steps < 1:
            raise ValueError(f"rollout_steps must be >= 1, got {rollout_steps}")
        if observe_threshold is not None and not 0.0 <= observe_threshold <= 1.0:
            raise ValueError(
                f"observe_threshold must be in [0, 1] or None; got {observe_threshold!r}"
            )
        self.name = name
        self.seed = int(seed)
        self.exploration = float(exploration)
        self.iterations = int(iterations)
        self.depth = int(depth)
        self.rollout_steps = int(rollout_steps)
        self.observe_threshold = observe_threshold
        self.split_eager = bool(split_eager)
        #: The engine as handed in. Search runs on a fresh clone of this per decision,
        #: so a rollout can never advance the live game's RNG (see clone_engine).
        self._base_engine = engine
        self._engine = engine
        self._rng = random.Random(self.seed)
        #: Board size used by the evaluator; engines expose ``board_size``, the
        #: attribute is declared on :class:`~qcheckers.engine.protocol.GameEngine`'s
        #: implementations but not on the protocol, hence the guarded lookup.
        size = getattr(engine, "board_size", 0)
        self.board_size = int(size) if size else 4

    # -- Agent protocol ----------------------------------------------------

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Pick an action: the game-tier policy first, else a probability-aware search."""
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}"
            )
        if len(legal) == 1:
            return legal[0]

        policy = self._game_tier_choice(state, legal)
        if policy is not None:
            return policy

        # Isolate search from the live engine and rewind the rollout RNG, so one
        # decision is a pure function of (seed, state, legal) and calling decide twice
        # on the same position returns the same action.
        self._engine = clone_engine(self._base_engine, self.seed)
        self._rng = random.Random(self.seed)

        return self._search(state, legal, state.turn)

    # -- game-tier policies (off in research conditions) --------------------

    def _game_tier_choice(
        self, state: GameState, legal: Sequence[Action]
    ) -> Action | None:
        """Observe a coin-flip ghost, or open with a split -- only when configured.

        Both branches are inert for a research agent (``observe_threshold is None`` and
        ``split_eager is False``), which is what keeps the ablation's ``prob`` arm the
        plain probability-aware search.
        """
        captures = [action for action in legal if action.kind == "capture"]

        if self.observe_threshold is not None and not captures:
            observes = [action for action in legal if isinstance(action, ObserveAction)]
            if observes:
                target = self._fuzziest_observe(state, observes)
                if target is not None:
                    return target

        if self.split_eager and not captures:
            if not any(piece.is_spread for piece in state.pieces_of(state.turn)):
                spreads = [action for action in legal if isinstance(action, SpreadAction)]
                if spreads:
                    return spreads[0]
        return None

    def _fuzziest_observe(
        self, state: GameState, observes: Sequence[ObserveAction]
    ) -> Action | None:
        """The observe action for the least-certain own piece, if it is uncertain enough."""
        eligible: list[Piece] = []
        for action in observes:
            try:
                piece = state.piece(action.piece_id)
            except KeyError:  # pragma: no cover - defensive
                continue
            if not piece.is_spread:
                continue
            if max(weight for _, weight in piece.sites) <= float(self.observe_threshold):
                eligible.append(piece)
        if not eligible:
            return None
        eligible.sort(key=lambda p: (max(w for _, w in p.sites), p.piece_id))
        chosen_id = eligible[0].piece_id
        for action in observes:
            if action.piece_id == chosen_id:
                return action
        return None  # pragma: no cover - defensive

    # -- search ------------------------------------------------------------

    def _search(self, state: GameState, legal: Sequence[Action], root_player: int) -> Action:
        """UCT over the legal actions, valued by probability-aware rollouts.

        Unvisited actions are swept first (in the engine's stable order), then UCT
        balances exploitation against exploration exactly as the baseline does. Ties
        break toward the lower index, so a fixed seed and position give a fixed move.
        """
        values = {index: 0.0 for index in range(len(legal))}
        visits = {index: 0 for index in range(len(legal))}
        parent_visits = 0

        for _ in range(self.iterations):
            parent_visits += 1
            index = self._select(legal, values, visits, parent_visits)
            leaf = self._expand(state, legal[index], root_player)
            if leaf is None:
                continue
            score = self._rollout(leaf, root_player)
            values[index] += score
            visits[index] += 1

        best_index = max(
            range(len(legal)),
            key=lambda i: (values[i] / visits[i] if visits[i] else float("-inf"), -i),
        )
        return legal[best_index]

    def _select(
        self,
        legal: Sequence[Action],
        values: dict[int, float],
        visits: dict[int, int],
        parent_visits: int,
    ) -> int:
        for index in range(len(legal)):
            if visits[index] == 0:
                return index
        best_index = 0
        best_score = float("-inf")
        for index in range(len(legal)):
            score = uct_score(values[index], visits[index], parent_visits, self.exploration)
            if score > best_score:
                best_score, best_index = score, index
        return best_index

    def _expand(
        self, state: GameState, action: Action, root_player: int
    ) -> GameState | None:
        """Apply ``action``, then ``depth`` plies of greedy likely replies."""
        current = state
        try:
            for ply in range(self.depth):
                current = self._engine.apply(current, action).state
                if self._engine.is_terminal(current):
                    break
                reply = self._engine.legal_actions(current)
                if not reply:
                    break
                if ply == self.depth - 1:
                    break
                action = self._best_probable(current, reply, root_player)
        except ValueError:
            return None
        return current

    def _best_probable(
        self, state: GameState, legal: Sequence[Action], root_player: int
    ) -> Action:
        """The opponent's one-ply reply, minimising the root's chance-aware score.

        Structurally identical to the baseline's ``_best_greedy`` -- only the evaluator
        differs, which is what keeps the ablation single-variable. A reply that
        maximised the root's score would model the opponent as cooperating.
        """
        worst = legal[0]
        worst_score = float("inf")
        for candidate in legal:
            try:
                child = self._engine.apply(state, candidate).state
            except ValueError:  # pragma: no cover - defensive
                continue
            score = self._evaluate(child, root_player)
            if score < worst_score:
                worst_score, worst = score, candidate
        return worst

    def _rollout(self, state: GameState, player: int) -> float:
        """Play out with a chance-weighted policy; value the result for ``player``."""
        current = state
        for _ in range(self.rollout_steps):
            outcome = self._engine.outcome(current)
            if outcome is not None:
                if outcome.winner is None:
                    return 0.0
                return 1.0 if outcome.winner == player else -1.0
            legal = self._engine.legal_actions(current)
            if not legal:
                return 0.0
            try:
                chosen = self._rollout_policy(current, legal)
                current = self._engine.apply(current, chosen).state
            except ValueError:  # pragma: no cover - defensive
                return 0.0
        # A depth cut falls back to the chance-aware heuristic, clamped so every rollout
        # value shares the terminal range.
        return max(-1.0, min(1.0, self._evaluate(current, player)))

    @staticmethod
    def _chance_square(action: Action) -> Square | None:
        """The square whose occupancy chance matters for this action.

        A move, capture or split can only happen if the piece really is on its origin;
        a rejoin picks a target, so what matters is the chance *there*; a merge keeps
        the acting piece's origin. Observe has no positional dependency (the engine
        samples the whole distribution), so it stays at a neutral weight.
        """
        if action.kind == "rejoin":
            return action.target
        if isinstance(action, ObserveAction):
            return None
        return getattr(action, "origin", None)

    def _rollout_policy(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Sample an action with weight ``chance_at`` of :meth:`_chance_square`.

        This is the paper's stated open problem made concrete: instead of averaging
        uniformly, a move is drawn in proportion to how likely the piece is to be able
        to make it. Certain pieces all weigh ``1.0``, so a classical board behaves
        exactly like a uniform rollout; the difference appears precisely when a piece
        is spread, which is the only case the ablation cares about.
        """
        weights: list[float] = []
        for action in legal:
            square = self._chance_square(action)
            weight = 1.0
            if square is not None:
                try:
                    weight = max(state.piece(action.piece_id).chance_at(square), 1e-9)
                except KeyError:  # pragma: no cover - defensive
                    weight = 1.0
            weights.append(weight)
        if len(set(weights)) == 1:
            return self._rng.choice(list(legal))
        return self._rng.choices(list(legal), weights=weights, k=1)[0]

    def _evaluate(self, state: GameState, player: int) -> float:
        """Chance-aware evaluation, with terminal states resolved by outcome."""
        outcome = self._engine.outcome(state)
        if outcome is not None:
            if outcome.winner is None:
                return 0.0
            return 1.0 if outcome.winner == player else -1.0
        return expected_evaluation(state, player, self.board_size)

    # -- helpers -----------------------------------------------------------

    def spread_pieces_of(self, state: GameState, owner: int) -> tuple[Piece, ...]:
        """Own uncertain pieces -- convenience for Person C's unit tests."""
        return tuple(p for p in state.pieces_of(owner) if p.is_spread)

    def reset(self, seed: int | None = None) -> None:
        """Rewind the RNG for reuse across games."""
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"{type(self).__name__}(seed={self.seed}, board_size={self.board_size}, "
            f"iterations={self.iterations}, name={self.name!r})"
        )


# Compile-time proof that the agent satisfies the shared interface.
_: type[Agent] = ProbAwareAgent


__all__ = [
    "ADVANCE_WEIGHT",
    "CAPTURE_PENALTY",
    "DEFAULT_DEPTH",
    "DEFAULT_ROLLOUT_STEPS",
    "HARD_OBSERVE_FLOOR",
    "ProbAwareAgent",
    "expected_evaluation",
    "expected_material",
]
