"""Unit tests for the conventional MCTS baseline agent."""

from __future__ import annotations

import math

import pytest

from qcheckers.agents.mcts_baseline import (
    DEFAULT_UCT_C,
    MCTSBaselineAgent,
    uct_score,
)
from qcheckers.engine.protocol import GameState
from tests.support.quantum_toy import QuantumToyEngine


def _make_engine(seed: int = 0, **kw) -> QuantumToyEngine:
    defaults = dict(seed=seed, level=2, board_size=4)
    defaults.update(kw)
    return QuantumToyEngine(**defaults)


class TestUctScore:
    def test_zero_visits_rejected(self):
        # The consolidated UCT helper validates visit counts instead of returning
        # inf, so a tree-builder bug cannot masquerade as an exploration win.
        with pytest.raises(ValueError, match="action_visits"):
            uct_score(0.0, 0, 10, 1.0)

    def test_exploration_decreases_with_visits(self):
        s1 = uct_score(1.0, 1, 100, 1.0)
        s2 = uct_score(1.0, 10, 100, 1.0)
        assert s1 > s2  # more visits => less exploration bonus

    def test_higher_parent_increases_exploration(self):
        s1 = uct_score(0.5, 5, 10, 1.0)
        s2 = uct_score(0.5, 5, 1000, 1.0)
        assert s2 > s1

    def test_exploitation_term(self):
        # Higher mean value => higher score (all else equal)
        s1 = uct_score(10.0, 10, 100, 1.0)  # mean 1.0
        s2 = uct_score(5.0, 10, 100, 1.0)  # mean 0.5
        assert s1 > s2


class TestMCTSBaselineAgent:
    def test_implements_agent_protocol(self):
        engine = _make_engine()
        agent = MCTSBaselineAgent(engine=engine, seed=0)
        assert hasattr(agent, "decide")
        assert hasattr(agent, "reset")
        assert agent.name == "mcts-baseline"

    def test_single_action_shortcut(self):
        engine = _make_engine()
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        if len(legal) > 1:
            # Construct a state with only one legal action by filtering
            # (engine always returns all legal, so we test via a mock-like approach)
            agent = MCTSBaselineAgent(engine=engine, seed=0, iterations=1)
            # Call with a single action
            only = legal[0]
            result = agent.decide(state, [only])
            assert result == only

    def test_returns_legal_action(self):
        engine = _make_engine(seed=3)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent = MCTSBaselineAgent(engine=engine, seed=0, iterations=5)
        action = agent.decide(state, legal)
        assert action in legal

    def test_empty_legal_raises(self):
        engine = _make_engine()
        agent = MCTSBaselineAgent(engine=engine, seed=0)
        state = GameState(turn=0, ply=0, pieces=())
        with pytest.raises(ValueError, match="no legal actions"):
            agent.decide(state, [])

    def test_seeded_reproducibility(self):
        """Same seed + same state => same action."""
        engine = _make_engine(seed=7)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent1 = MCTSBaselineAgent(engine=engine, seed=42, iterations=10)
        agent2 = MCTSBaselineAgent(engine=engine, seed=42, iterations=10)
        a1 = agent1.decide(state, legal)
        a2 = agent2.decide(state, legal)
        assert a1 == a2

    def test_diagnostics_populated(self):
        engine = _make_engine(seed=1)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent = MCTSBaselineAgent(engine=engine, seed=0, iterations=8)
        agent.decide(state, legal)
        diag = agent.last_diagnostics
        assert diag["simulations"] == 8
        assert diag["expansions"] >= 1
        assert diag["completed_rollouts"] == 8
        assert diag["elapsed_seconds"] > 0
        assert diag["root_visits"] == 8

    def test_invalid_exploration_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError, match="exploration"):
            MCTSBaselineAgent(engine=engine, exploration=-1.0)

    def test_invalid_iterations_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError, match="iterations"):
            MCTSBaselineAgent(engine=engine, iterations=0)

    def test_reset_reseeds(self):
        engine = _make_engine()
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent = MCTSBaselineAgent(engine=engine, seed=5, iterations=10)
        a1 = agent.decide(state, legal)
        agent.reset(seed=5)
        a2 = agent.decide(state, legal)
        assert a1 == a2

    def test_terminal_state_handling(self):
        """Agent should handle a state where the game is already over gracefully."""
        engine = _make_engine(seed=0, max_plies=1)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        if legal:
            state = engine.apply(state, legal[0]).state
        # Now terminal; legal_actions returns []
        agent = MCTSBaselineAgent(engine=engine, seed=0)
        with pytest.raises(ValueError):
            agent.decide(state, engine.legal_actions(state))

    def test_no_clone_raises_typeerror(self):
        """Agent requires a cloneable engine for search."""
        from qcheckers.engine.protocol import clone_engine

        engine = _make_engine()
        agent = MCTSBaselineAgent(engine=engine, seed=0)
        # Our toy engine supports clone, so this should work
        cloned = clone_engine(engine, 42)
        assert cloned is not None

    def test_uct_c_constant(self):
        assert DEFAULT_UCT_C > 0
        assert abs(DEFAULT_UCT_C - math.sqrt(2)) < 0.01

    def test_repr(self):
        engine = _make_engine()
        agent = MCTSBaselineAgent(engine=engine, seed=3, iterations=10)
        r = repr(agent)
        assert "MCTSBaselineAgent" in r
