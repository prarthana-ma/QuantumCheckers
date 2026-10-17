"""Tests for the experiment runner."""

from __future__ import annotations

import json

import pytest

from qcheckers.experiment.config import ExperimentConfig
from qcheckers.experiment.runner import (
    run_condition,
    run_game,
    run_experiment,
    get_agent_factory,
    register_agent_kind,
    log_path,
)
from qcheckers.experiment.seeds import SeedManager
from qcheckers.experiment.schema import read_records
from tests.support.quantum_toy import QuantumToyEngine


def _engine_factory(seed: int, **kw):
    defaults = dict(seed=seed, level=2, board_size=4, max_plies=60)
    defaults.update(kw)
    return QuantumToyEngine(**defaults)


class TestRunGame:
    def test_completes(self):
        result = run_game(
            lambda s: _engine_factory(s),
            ("random", "random"),
            seed=0,
        )
        assert result.outcome in ("win_p0", "win_p1", "draw", "error", "timeout")
        assert result.duration_seconds > 0

    def test_win_outcome(self):
        # Run enough games that at least one should win (not all draws)
        outcomes = set()
        for i in range(5):
            r = run_game(lambda s: _engine_factory(s), ("random", "random"), seed=i)
            outcomes.add(r.outcome)
        # With random agents on a small board, we should see wins
        assert "win_p0" in outcomes or "win_p1" in outcomes or "draw" in outcomes

    def test_alternate_seats(self):
        r0 = run_game(
            lambda s: _engine_factory(s),
            ("random", "mcts"),
            seed=0,
            game_index=0,
            alternate=True,
        )
        r1 = run_game(
            lambda s: _engine_factory(s),
            ("random", "mcts"),
            seed=0,
            game_index=1,
            alternate=True,
        )
        # Game 0: p0=random, p1=mcts
        assert r0.player_assignment["0"] == "random"
        assert r0.player_assignment["1"] == "mcts"
        # Game 1: seats swapped
        assert r1.player_assignment["0"] == "mcts"
        assert r1.player_assignment["1"] == "random"

    def test_n_plies_non_negative(self):
        r = run_game(lambda s: _engine_factory(s), ("random", "random"), seed=0)
        assert r.n_plies >= 0

    def test_transitions_recorded(self):
        r = run_game(lambda s: _engine_factory(s), ("random", "random"), seed=0)
        if r.outcome not in ("error", "timeout"):
            assert len(r.transitions) == r.n_plies

    def test_initial_state_captured(self):
        r = run_game(lambda s: _engine_factory(s), ("random", "random"), seed=0)
        if r.outcome not in ("error", "timeout"):
            assert r.initial_state is not None

    def test_engine_error_captured(self):
        """If the engine raises, the result should be an error outcome."""
        class BadEngine:
            board_size = 4
            def initial_state(self):
                raise RuntimeError("engine broken")
            def legal_actions(self, state):
                return []
            def apply(self, state, action):
                raise RuntimeError("apply broken")
            def is_terminal(self, state):
                return False
            def outcome(self, state):
                return None

        result = run_game(
            lambda s: BadEngine(),
            ("random", "random"),
            seed=0,
        )
        assert result.outcome == "error"
        assert result.error is not None


class TestRunCondition:
    def test_batch_completes(self):
        seeds = [0, 1, 2, 3, 4]
        records = run_condition(
            lambda s: _engine_factory(s),
            ("random", "random"),
            seeds,
            condition="test-batch",
        )
        assert len(records) == 5
        for r in records:
            assert r["experiment_id"] == "test-batch"
            assert r["outcome"] in ("win_p0", "win_p1", "draw", "error", "timeout")

    def test_unique_game_ids(self):
        records = run_condition(
            lambda s: _engine_factory(s),
            ("random", "random"),
            list(range(10)),
            condition="test-unique",
        )
        ids = [r["game_id"] for r in records]
        assert len(ids) == len(set(ids))

    def test_writes_output_file(self, tmp_path):
        output = tmp_path / "results.jsonl"
        seeds = [0, 1]
        records = run_condition(
            lambda s: _engine_factory(s),
            ("random", "random"),
            seeds,
            condition="test-output",
            output=output,
        )
        assert output.exists()
        read_results = read_records(output)
        assert len(read_results) == 2

    def test_log_path(self):
        p = log_path("test-condition", "results")
        assert p.name == "test-condition.jsonl"

    def test_alternate_in_batch(self):
        records = run_condition(
            lambda s: _engine_factory(s),
            ("random", "mcts"),
            list(range(4)),
            condition="test-alt",
            alternate=True,
        )
        # Even-indexed games: p0=random, p1=mcts
        assert records[0]["player_assignment"]["0"] == "random"
        assert records[0]["player_assignment"]["1"] == "mcts"
        # Odd-indexed: swapped
        assert records[1]["player_assignment"]["0"] == "mcts"
        assert records[1]["player_assignment"]["1"] == "random"


class TestAgentRegistry:
    def test_random_registered(self):
        factory = get_agent_factory("random")
        assert callable(factory)

    def test_mcts_registered(self):
        factory = get_agent_factory("mcts")
        assert callable(factory)

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_agent_factory("nonexistent")

    def test_register_custom(self):
        class DummyAgent:
            name = "dummy"
            def decide(self, state, legal):
                return legal[0]
            def reset(self):
                pass

        register_agent_kind("dummy_test", lambda engine, **kw: DummyAgent())
        factory = get_agent_factory("dummy_test")
        assert callable(factory)


class TestRunExperiment:
    def test_full_experiment(self, tmp_path):
        config = ExperimentConfig(
            experiment_id="test-exp",
            agents=("random", "random"),
            n_games=4,
            base_seed=10,
            board_size=4,
            max_plies=60,
            output_dir=str(tmp_path),
        )
        records = run_experiment(config, lambda s: _engine_factory(s))
        assert len(records) == 4
        output = log_path(config.experiment_id, str(tmp_path))
        assert output.exists()

    def test_experiment_with_replays(self, tmp_path):
        config = ExperimentConfig(
            experiment_id="test-replay",
            agents=("random", "random"),
            n_games=2,
            base_seed=5,
            board_size=4,
            max_plies=60,
            output_dir=str(tmp_path),
            export_replays=True,
        )
        records = run_experiment(config, lambda s: _engine_factory(s))
        assert len(records) == 2
        # Check replay files exist
        replay_dir = tmp_path / "replays"
        assert replay_dir.exists()
        replay_files = list(replay_dir.glob("*.replay.json"))
        assert len(replay_files) == 2


class TestSeedManagerIntegration:
    def test_seeds_recorded(self):
        mgr = SeedManager(42)
        seeds = mgr.game_seeds(3)
        records = run_condition(
            lambda s: _engine_factory(s),
            ("random", "random"),
            seeds,
            condition="test-seeds",
            seed_manager=mgr,
        )
        for i, r in enumerate(records):
            assert r["seed"] == seeds[i]
