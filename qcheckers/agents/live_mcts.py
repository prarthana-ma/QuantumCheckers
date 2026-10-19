"""Seeded, state-tree UCT agent for the live paper-based engine.

The live search treats each sampled successor returned by ``engine.apply`` as a
separate chance branch below its action. Values are always stored from the root
player's point of view; selection maximizes on the root player's turns and minimizes
on the opponent's turns. This also handles same-player capture continuations.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Sequence

from qcheckers.engine.paper import BranchLimitError


@dataclass
class _ActionStats:
    visits: int = 0
    value_sum: float = 0.0
    outcomes: dict[Any, "_Node"] = field(default_factory=dict)
    blocked: bool = False


@dataclass
class _Node:
    state: Any
    actions: tuple[Any, ...]
    stats: dict[Any, _ActionStats] = field(default_factory=dict)
    visits: int = 0


def _freeze(value: Any) -> Any:
    """Build a stable state key for hashable or ordinary value-object states."""
    try:
        hash(value)
    except (TypeError, ValueError):
        pass
    else:
        return value
    if is_dataclass(value):
        return (type(value).__qualname__, tuple((f.name, _freeze(getattr(value, f.name))) for f in fields(value)))
    if isinstance(value, dict):
        return tuple(sorted((_freeze(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    if hasattr(value, "__dict__"):
        return (type(value).__qualname__, _freeze(vars(value)))
    return repr(value)


def _branch_count(state: Any) -> int:
    """Estimate sparse-state work from a paper engine's retained amplitudes."""
    branches = getattr(state, "amplitudes", None)
    if branches is None:
        branches = getattr(state, "branches", None)
    try:
        return max(1, len(branches))
    except TypeError:
        return 1


def evaluate_state(state: Any, player: int, *, board_size: int) -> float:
    """Return bounded zero-sum material/progress value in ``player``'s perspective.

    Piece value is summed over site probabilities, so a piece's contribution shrinks
    with its survival probability. King promotion and normalized forward progress
    provide small positional terms. Captured-history metadata is deliberately ignored.
    """
    if board_size < 2:
        raise ValueError("board_size must be at least 2")
    totals = [0.0, 0.0]
    for piece in getattr(state, "pieces", ()):
        owner = int(piece.owner)
        for square, chance in piece.sites:
            row = int(square[0])
            progress = (board_size - 1 - row) / (board_size - 1) if owner == 0 else row / (board_size - 1)
            king_chance = None
            king_at = getattr(piece, "king_chance_at", None)
            if callable(king_at):
                king_chance = float(king_at(square))
            elif bool(getattr(piece, "is_king", False)):
                king_chance = float(chance)
            else:
                king_sites = dict(getattr(piece, "king_sites", ()))
                king_chance = float(king_sites.get(square, 0.0))
            # Clamp malformed marginals defensively; engines should supply valid values.
            weight = max(0.0, float(chance))
            king_weight = min(weight, max(0.0, king_chance))
            totals[owner] += weight * (1.0 + 0.25 * (king_weight / weight if weight else 0.0) + 0.08 * progress)
    material = totals[0] + totals[1]
    if material <= 1e-12:
        return 0.0
    p0_value = max(-1.0, min(1.0, (totals[0] - totals[1]) / material))
    return p0_value if player == 0 else -p0_value


class LiveMCTSAgent:
    """UCT search with chance-specific state branches and random legal rollouts."""

    def __init__(
        self,
        engine: Any,
        *,
        seed: int = 0,
        iterations: int = 200,
        tree_depth: int = 8,
        rollout_steps: int = 48,
        branch_work_budget: int = 1024,
        exploration: float = math.sqrt(2.0),
        name: str = "live-mcts",
    ) -> None:
        if iterations < 1:
            raise ValueError("iterations must be positive")
        if tree_depth < 1 or rollout_steps < 0:
            raise ValueError("tree_depth must be positive and rollout_steps non-negative")
        if branch_work_budget < 1:
            raise ValueError("branch_work_budget must be positive")
        if exploration < 0:
            raise ValueError("exploration must be non-negative")
        self.engine = engine
        self.seed = int(seed)
        self.iterations = int(iterations)
        self.tree_depth = int(tree_depth)
        self.rollout_steps = int(rollout_steps)
        self.branch_work_budget = int(branch_work_budget)
        self.exploration = float(exploration)
        self.name = name

    def _private_engine(self) -> Any:
        clone_method = getattr(self.engine, "clone", None)
        if not callable(clone_method):
            raise TypeError("live MCTS requires an engine with clone(seed=...) support")
        try:
            clone = clone_method(seed=self.seed)
        except TypeError:
            clone = clone_method(self.seed)
        if clone is self.engine:
            raise TypeError("engine.clone must return an independent simulation engine")
        # Engine clones should drop hardware samplers. Enforce this where the sampler
        # is a normal mutable attribute, so simulation can never schedule live jobs.
        if hasattr(clone, "sampler"):
            clone.sampler = None
        return clone

    def _terminal_value(self, engine: Any, state: Any, root_player: int) -> float | None:
        outcome = engine.outcome(state)
        if outcome is None:
            return None
        winner = outcome.winner
        if winner is None:
            return 0.0
        return 1.0 if winner == root_player else -1.0

    def _new_node(self, engine: Any, state: Any) -> _Node:
        return _Node(state, tuple(engine.legal_actions(state)))

    def _rollout(
        self,
        engine: Any,
        state: Any,
        root_player: int,
        rng: random.Random,
        *,
        branch_work_remaining: int,
    ) -> float:
        current = state
        for _ in range(self.rollout_steps):
            terminal = self._terminal_value(engine, current, root_player)
            if terminal is not None:
                return terminal
            actions = tuple(engine.legal_actions(current))
            if not actions:
                # Well-formed engines report no-move losses through outcome().
                return evaluate_state(current, root_player, board_size=engine.board_size)
            candidates = list(actions)
            rng.shuffle(candidates)
            for action in candidates:
                work = _branch_count(current)
                if work > branch_work_remaining:
                    return evaluate_state(current, root_player, board_size=engine.board_size)
                branch_work_remaining -= work
                try:
                    current = engine.apply(current, action).state
                    break
                except BranchLimitError:
                    # A capped transition is unavailable to this simulation. Try
                    # another offered move; if every move is capped, stop at this state.
                    continue
            else:
                return evaluate_state(current, root_player, board_size=engine.board_size)
        terminal = self._terminal_value(engine, current, root_player)
        if terminal is not None:
            return terminal
        return evaluate_state(current, root_player, board_size=engine.board_size)

    def _select(self, node: _Node, rng: random.Random, root_player: int) -> Any:
        unvisited = [
            action for action in node.actions
            if not node.stats[action].blocked and node.stats[action].visits == 0
        ]
        if unvisited:
            return rng.choice(unvisited)
        maximizing = node.state.turn == root_player
        log_parent = math.log(max(1, node.visits))
        best_score = -math.inf
        best: list[Any] = []
        for action in node.actions:
            stats = node.stats[action]
            if stats.blocked:
                continue
            mean = stats.value_sum / stats.visits
            exploit = mean if maximizing else -mean
            score = exploit + self.exploration * math.sqrt(log_parent / stats.visits)
            if score > best_score + 1e-12:
                best_score, best = score, [action]
            elif abs(score - best_score) <= 1e-12:
                best.append(action)
        return rng.choice(best)

    def decide(self, state: Any, legal: Sequence[Any]) -> Any:
        offered = tuple(legal)
        if not offered:
            raise ValueError("no legal actions: game should have been terminal")
        root_player = int(state.turn)
        engine = self._private_engine()
        rng = random.Random(self.seed)
        root = _Node(state, offered, {action: _ActionStats() for action in offered})
        for _ in range(self.iterations):
            node = root
            path: list[tuple[_Node, _ActionStats]] = []
            depth = 0
            branch_work_used = 0
            branch_work_limit = max(self.branch_work_budget, _branch_count(state))
            value = self._terminal_value(engine, node.state, root_player)
            while value is None and node.actions and depth < self.tree_depth:
                if len(node.actions) != len(node.stats):
                    for action in node.actions:
                        node.stats.setdefault(action, _ActionStats())
                action = self._select(node, rng, root_player)
                stats = node.stats[action]
                work = _branch_count(node.state)
                if branch_work_used + work > branch_work_limit:
                    value = evaluate_state(node.state, root_player, board_size=engine.board_size)
                    break
                branch_work_used += work
                try:
                    next_state = engine.apply(node.state, action).state
                except BranchLimitError:
                    stats.blocked = True
                    node.actions = tuple(candidate for candidate in node.actions if candidate != action)
                    value = evaluate_state(node.state, root_player, board_size=engine.board_size)
                    break
                path.append((node, stats))
                depth += 1
                value = self._terminal_value(engine, next_state, root_player)
                key = _freeze(next_state)
                child = stats.outcomes.get(key)
                if child is None:
                    child = self._new_node(engine, next_state)
                    stats.outcomes[key] = child
                    node = child
                    if value is None:
                        value = self._rollout(
                            engine,
                            next_state,
                            root_player,
                            rng,
                            branch_work_remaining=branch_work_limit - branch_work_used,
                        )
                    break
                node = child
            if value is None:
                value = self._rollout(
                    engine,
                    node.state,
                    root_player,
                    rng,
                    branch_work_remaining=branch_work_limit - branch_work_used,
                )
            for parent, stats in path:
                parent.visits += 1
                stats.visits += 1
                stats.value_sum += value

        # Selection prioritizes untried edges, subject to the simulation budget.
        # Retain a legal deterministic fallback defensively.
        ranked = [
            (action, root.stats[action])
            for action in offered
            if not root.stats[action].blocked
        ]
        if not ranked:
            # All offered transitions exceeded the configured exact-state cap. Keep
            # the protocol contract in this degenerate case; with alternatives, only
            # the successfully simulated root actions above are eligible.
            return offered[0]
        return max(ranked, key=lambda pair: (pair[1].visits, pair[1].value_sum / pair[1].visits if pair[1].visits else -math.inf))[0]


__all__ = ["LiveMCTSAgent", "evaluate_state"]
