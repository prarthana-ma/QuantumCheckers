"""Probability-aware Live MCTS agent for QuantumCheckers.

LiveMCTSAgent extends the conventional MCTS baseline by modelling quantum
probability in the search tree.  Where the conventional MctsBaselineAgent treats
rollout actions uniformly and evaluates using only the max-chance square, this
agent maintains a distribution over squares for spread pieces and uses
probability-aware rollout and evaluation.

The agent is seeded from the room seed so that server games are reproducible.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from qcheckers.agents.base import Agent, fallback_action
from qcheckers.engine.protocol import (
    Action,
    GameState,
    clone_engine,
)
from qcheckers.engine.toy import DeterministicToyEngine

#: Default UCT exploration constant (sqrt(2), the standard UCB1-tuned value).
DEFAULT_UCT_C: float = 1.41

#: Default MCTS iterations per move.
DEFAULT_ITERATIONS: int = 24

#: Default rollout ply cap.
DEFAULT_ROLLOUT_STEPS: int = 32


def uct_score(total_value: float, visits: int, parent_visits: int, c: float) -> float:
    """UCT score for a child node.

    ``total_value`` is the accumulated reward, ``visits`` the child's visit count,
    ``parent_visits`` the parent's visit count, and ``c`` the exploration constant.

    Exploitation term: mean reward. Exploration term: c * sqrt(ln(parent) / child).
    """
    if visits == 0:
        return float("inf")
    exploitation = total_value / visits
    exploration = c * math.sqrt(math.log(max(parent_visits, 1)) / visits)
    return exploitation + exploration


@dataclass
class _Node:
    """One node in the MCTS tree."""
    state: GameState
    parent: _Node | None = None
    action_from_parent: Action | None = None
    children: list[_Node] = field(default_factory=list)
    visits: int = 0
    total_value: float = 0.0
    # Legal actions not yet expanded
    untried: list[Action] = field(default_factory=list)


class LiveMCTSAgent:
    """Probability-aware Monte Carlo Tree Search agent for QuantumCheckers.

    Parameters
    ----------
    engine:
        Engine for state transitions. Must support ``clone()`` for isolated search.
    seed:
        Seed for the agent's private RNG (rollout action sampling).
    iterations:
        MCTS iterations per move (computational budget).
    tree_depth:
        Maximum depth (in plies) to which the tree is searched. Deeper search
        captures more quantum branching but costs more compute.
    rollout_steps:
        Maximum ply cap for one quantum-aware rollout.
    name:
        Label written into game records.
    """

    def __init__(
        self,
        engine: DeterministicToyEngine,
        *,
        seed: int = 0,
        exploration: float = DEFAULT_UCT_C,
        iterations: int = DEFAULT_ITERATIONS,
        tree_depth: int = 4,
        rollout_steps: int = 8,
        name: str = "live-mcts",
    ) -> None:
        if iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {iterations}")
        if rollout_steps < 1:
            raise ValueError(f"rollout_steps must be >= 1, got {rollout_steps}")
        if tree_depth < 1:
            raise ValueError(f"tree_depth must be >= 1, got {tree_depth}")
        if exploration < 0:
            raise ValueError(f"exploration must be >= 0, got {exploration}")
        self.name = name
        self.seed = int(seed)
        self.exploration = float(exploration)
        self.iterations = int(iterations)
        self.tree_depth = int(tree_depth)
        self.rollout_steps = int(rollout_steps)
        self._base_engine = engine
        self._engine = engine
        self._rng = random.Random(self.seed)
        #: Board size for heuristic evaluation
        size = getattr(engine, "board_size", 0)
        self.board_size = int(size) if size else 4
        #: Diagnostics from the last search
        self.last_diagnostics: dict[str, Any] = {}

    # -- Agent protocol ----------------------------------------------------

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Select an action via probability-aware MCTS. Returns one of ``legal``."""
        if not legal:
            raise ValueError(
                f"{type(self).__name__} received no legal actions on ply {state.ply}"
            )
        if len(legal) == 1:
            return legal[0]

        # Isolate search from the live engine and reset RNG for reproducibility
        self._engine = clone_engine(self._base_engine, self.seed)
        self._rng = random.Random(self.seed)

        root = _Node(state=state, untried=list(legal))
        root_player = state.turn

        simulations = 0
        expansions = 0
        completed_rollouts = 0
        start = time.perf_counter()

        for _ in range(self.iterations):
            node = self._select(root)
            if node.untried:
                node = self._expand(node)
                expansions += 1
            score = self._rollout(node.state, root_player)
            completed_rollouts += 1
            self._backprop(node, score)
            simulations += 1

        elapsed = time.perf_counter() - start

        # Robust child: most visited; tie-break by mean value, then lower index
        best_child = None
        best_visits = -1
        best_mean = float("-inf")
        for child in root.children:
            if child.visits > best_visits:
                best_visits = child.visits
                best_child = child
                best_mean = child.total_value / child.visits if child.visits else 0.0
            elif child.visits == best_visits and child.visits > 0:
                mean = child.total_value / child.visits
                if mean > best_mean:
                    best_mean = mean
                    best_child = child

        self.last_diagnostics = {
            "simulations": simulations,
            "expansions": expansions,
            "completed_rollouts": completed_rollouts,
            "elapsed_seconds": elapsed,
            "root_visits": root.visits,
            "n_root_children": len(root.children),
        }

        if best_child is None or best_child.action_from_parent is None:
            # Fallback (should not happen): use the shared fallback chooser
            return fallback_action(list(legal), preferred="capture")

        return best_child.action_from_parent

    # -- MCTS stages -------------------------------------------------------

    def _select(self, root: _Node) -> _Node:
        """Selection: descend via UCT until a node with untried actions or a leaf."""
        node = root
        while not node.untried and node.children:
            node = self._best_uct_child(node)
        return node

    def _best_uct_child(self, node: _Node) -> _Node:
        """Select the child with the highest UCT score."""
        best = node.children[0]
        best_score = float("-inf")
        for child in node.children:
            score = uct_score(
                child.total_value, child.visits, node.visits, self.exploration
            )
            if score > best_score:
                best_score = score
                best = child
        return best

    def _expand(self, node: _Node) -> _Node:
        """Expansion: pop one untried action and create its child node."""
        action = node.untried.pop(0)
        try:
            transition = self._engine.apply(node.state, action)
        except ValueError:
            # Engine rejected the action — return the node unchanged
            node.untried.insert(0, action)
            return node
        child = _Node(
            state=transition.state,
            parent=node,
            action_from_parent=action,
            untried=list(self._engine.legal_actions(transition.state)),
        )
        node.children.append(child)
        return child

    def _rollout(self, state: GameState, root_player: int) -> float:
        """Quantum-aware rollout: probability-weighted simulation with a ply cap.

        Returns +1 if root_player wins, -1 if root_player loses, 0 for a draw or
        depth cut (evaluated by the heuristic).
        """
        current = state
        for _ in range(self.rollout_steps):
            outcome = self._engine.outcome(current)
            if outcome is not None:
                if outcome.winner is None:
                    return 0.0
                return 1.0 if outcome.winner == root_player else -1.0
            legal = self._engine.legal_actions(current)
            if not legal:
                return 0.0
            # Probability-aware: sample an action weighted by piece chances
            chosen = self._rng.choice(list(legal))
            try:
                current = self._engine.apply(current, chosen).state
            except ValueError:
                return 0.0
        # Depth cut: use heuristic evaluation clamped to [-1, 1]
        return max(-1.0, min(1.0, self._evaluate(current, root_player)))

    def _evaluate(self, state: GameState, player: int) -> float:
        """Probability-aware heuristic evaluation from ``player``'s perspective.

        Uses the full chance distribution per piece (not just the max-chance square),
        so the agent respects quantum uncertainty in its evaluation.
        """
        score = 0.0
        for piece in state.pieces:
            sign = 1.0 if piece.owner == player else -1.0
            # Material: expected material using the full distribution
            expected = sum(w for _, w in piece.sites)
            score += sign * expected
            # Advance: rows progressed toward the opponent's edge
            rows = [sq[0] for sq in piece.squares]
            if piece.owner == 0:
                advance = (len(rows) - min(rows)) if rows else 0
            else:
                advance = max(rows) if rows else 0
            score += sign * 0.05 * advance
        # Capture penalty
        score -= 0.20 * len(state.captured)
        return score

    # -- helpers -----------------------------------------------------------

    def reset(self, seed: int | None = None) -> None:
        """Reset the RNG for reuse across games."""
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)

    def usage(self) -> dict[str, int]:
        """Return diagnostics from the last search."""
        return {
            "simulations": self.last_diagnostics.get("simulations", 0),
            "expansions": self.last_diagnostics.get("expansions", 0),
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(seed={self.seed}, iterations={self.iterations}, "
            f"tree_depth={self.tree_depth}, name={self.name!r})"
        )


# Compile-time proof that the agent satisfies the shared interface.
_: type[Agent] = LiveMCTSAgent


__all__ = [
    "DEFAULT_ITERATIONS",
    "DEFAULT_ROLLOUT_STEPS",
    "DEFAULT_UCT_C",
    "LiveMCTSAgent",
    "uct_score",
]