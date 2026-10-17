"""Unit tests for the random baseline agent."""

from __future__ import annotations

import random

import pytest

from qcheckers.agents.random_agent import RandomAgent
from qcheckers.engine.protocol import Action, GameState, Piece
from tests.support.quantum_toy import QuantumToyEngine


def _make_engine(seed: int = 0, **kwargs) -> QuantumToyEngine:
    defaults = dict(seed=seed, level=2, board_size=4)
    defaults.update(kwargs)
    return QuantumToyEngine(**defaults)


class TestRandomAgent:
    def test_implements_agent_protocol(self):
        agent = RandomAgent(seed=0)
        assert hasattr(agent, "decide")
        assert hasattr(agent, "reset")
        assert agent.name == "random"

    def test_selects_from_legal_actions(self):
        engine = _make_engine()
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent = RandomAgent(seed=42)
        action = agent.decide(state, legal)
        assert action in legal

    def test_empty_legal_raises(self):
        agent = RandomAgent(seed=0)
        state = GameState(turn=0, ply=0, pieces=())
        with pytest.raises(ValueError, match="no legal actions"):
            agent.decide(state, [])

    def test_seeded_reproducibility(self):
        """Same seed + same state + same legal sequence => same action."""
        engine = _make_engine(seed=7)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent1 = RandomAgent(seed=123)
        agent2 = RandomAgent(seed=123)
        # Draw several times to exercise the RNG
        for _ in range(20):
            a1 = agent1.decide(state, legal)
            a2 = agent2.decide(state, legal)
            assert a1 == a2

    def test_different_seeds_diverge(self):
        """Different seeds should produce different choice sequences."""
        engine = _make_engine(seed=7)
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent1 = RandomAgent(seed=1)
        agent2 = RandomAgent(seed=999)
        seq1 = [agent1.decide(state, legal) for _ in range(30)]
        seq2 = [agent2.decide(state, legal) for _ in range(30)]
        # Sequences should differ at some point (different RNG streams)
        assert seq1 != seq2 or len(legal) <= 1

    def test_no_global_random_state(self):
        """Agent must use its own RNG, not the global random module."""
        import random as global_random
        engine = _make_engine()
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        # Perturb global state
        global_random.seed(0)
        before = [global_random.random() for _ in range(5)]
        global_random.seed(0)
        agent = RandomAgent(seed=77)
        agent.decide(state, legal)
        after = [global_random.random() for _ in range(5)]
        assert before == after  # global RNG untouched

    def test_reset_reseeds(self):
        engine = _make_engine()
        state = engine.initial_state()
        legal = list(engine.legal_actions(state))
        agent = RandomAgent(seed=5)
        seq1 = [agent.decide(state, legal) for _ in range(10)]
        agent.reset(seed=5)
        seq2 = [agent.decide(state, legal) for _ in range(10)]
        assert seq1 == seq2

    def test_usage_returns_dict(self):
        agent = RandomAgent(seed=0)
        assert isinstance(agent.usage(), dict)

    def test_terminal_state_no_legal(self):
        """Engine returns no legal actions on terminal state; agent raises."""
        engine = _make_engine(seed=0, max_plies=1)
        state = engine.initial_state()
        # Play one ply to reach the cap
        legal = list(engine.legal_actions(state))
        if legal:
            state = engine.apply(state, legal[0]).state
        agent = RandomAgent(seed=0)
        with pytest.raises(ValueError):
            agent.decide(state, engine.legal_actions(state))

    def test_repr(self):
        agent = RandomAgent(seed=3, name="rand")
        r = repr(agent)
        assert "RandomAgent" in r
        assert "seed=3" in r
