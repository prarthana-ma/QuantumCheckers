"""Tests for experiment configuration."""

from __future__ import annotations

import json
import pytest

from qcheckers.experiment.config import (
    MIN_GAMES_JUSTIFIED,
    ExperimentConfig,
    load_config,
    save_config,
)


class TestExperimentConfig:
    def test_defaults(self):
        c = ExperimentConfig()
        assert c.experiment_id == "default"
        assert c.n_games == 10
        assert c.board_size == 4
        assert c.level == 2
        assert c.alternate_seats is True

    def test_runner_style_fields_construct(self):
        c = ExperimentConfig(
            experiment_id="runner-style",
            agents=("random", "mcts"),
            base_seed=42,
            n_games=4,
            board_size=6,
            max_plies=80,
            level=1,
            allow_observe=False,
        )
        assert c.experiment_id == "runner-style"
        assert c.agents == ("random", "mcts")
        assert c.base_seed == 42
        assert c.n_games == 4
        assert c.board_size == 6
        assert c.max_plies == 80
        assert c.level == 1
        assert c.allow_observe is False

    def test_min_games_justified(self):
        assert isinstance(MIN_GAMES_JUSTIFIED, int)
        assert MIN_GAMES_JUSTIFIED > 0

    def test_invalid_n_games(self):
        with pytest.raises(ValueError, match="n_games"):
            ExperimentConfig(n_games=0)

    def test_invalid_board_size(self):
        with pytest.raises(ValueError, match="board_size"):
            ExperimentConfig(board_size=3)

    def test_invalid_level(self):
        with pytest.raises(ValueError, match="level"):
            ExperimentConfig(level=3)

    def test_invalid_timeout(self):
        with pytest.raises(ValueError, match="timeout"):
            ExperimentConfig(timeout_seconds=-1)

    def test_invalid_experiment_id(self):
        with pytest.raises(ValueError, match="experiment_id"):
            ExperimentConfig(experiment_id="")

    def test_from_dict_round_trip(self):
        c = ExperimentConfig(
            experiment_id="test",
            agents=("random", "mcts"),
            n_games=5,
            base_seed=42,
        )
        d = c.to_dict()
        c2 = ExperimentConfig.from_dict(d)
        assert c2.experiment_id == "test"
        assert list(c2.agents) == ["random", "mcts"]
        assert c2.n_games == 5
        assert c2.base_seed == 42

    def test_from_dict_ignores_unknown(self):
        c = ExperimentConfig.from_dict({"unknown_key": 123, "n_games": 7})
        assert c.n_games == 7

    def test_from_dict_agents_list_to_tuple(self):
        c = ExperimentConfig.from_dict({"agents": ["random", "mcts"]})
        assert isinstance(c.agents, tuple)
        assert len(c.agents) == 2

    def test_save_load_json(self, tmp_path):
        c = ExperimentConfig(experiment_id="roundtrip", n_games=3)
        p = tmp_path / "config.json"
        save_config(c, p)
        c2 = load_config(p)
        assert c2.experiment_id == "roundtrip"
        assert c2.n_games == 3

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json")
        with pytest.raises(ValueError):
            load_config(p)
"""Focused checks for immutable experiment configuration."""

from dataclasses import FrozenInstanceError

import pytest

from qcheckers.experiment.config import (
    CONDITIONS,
    MIN_GAMES_JUSTIFIED,
    PRIMARY_METRIC,
    SECONDARY_METRICS,
    STOPPING_RULE,
    ConditionConfig,
    ExperimentConfig,
    ablation_label,
    condition_by_label,
    matched_seeds,
    seed_list,
)


def test_registry_contains_four_ablation_cells_and_two_references() -> None:
    labels = {condition.label for condition in CONDITIONS}
    assert labels == {
        "ablation-mcts-vs-random-obs",
        "ablation-mcts-vs-random-noobs",
        "ablation-prob-vs-random-obs",
        "ablation-prob-vs-random-noobs",
        "classical-random-vs-random",
        "classical-mcts-vs-random",
    }


@pytest.mark.parametrize(
    ("agent", "observe", "expected"),
    [
        ("mcts", True, "ablation-mcts-vs-random-obs"),
        ("mcts", False, "ablation-mcts-vs-random-noobs"),
        ("prob", True, "ablation-prob-vs-random-obs"),
        ("prob", False, "ablation-prob-vs-random-noobs"),
    ],
)
def test_ablation_label(agent: str, observe: bool, expected: str) -> None:
    assert ablation_label(agent, "random", observe) == expected
    assert condition_by_label(expected).label == expected


def test_ablation_label_rejects_unsupported_pair() -> None:
    with pytest.raises(ValueError):
        ablation_label("observe", "random", True)


def test_seed_helpers_are_deterministic_and_matched() -> None:
    assert seed_list(-2, 4) == [-2, -1, 0, 1]
    seeds_a, seeds_b = matched_seeds(3)
    assert seeds_a == seeds_b == [0, 1, 2]
    assert seeds_a is not seeds_b


def test_configuration_is_frozen_and_validates_fields() -> None:
    condition = condition_by_label("classical-random-vs-random")

    with pytest.raises(FrozenInstanceError):
        condition.level = 1  # type: ignore[misc]
    with pytest.raises(ValueError, match="level"):
        ConditionConfig("invalid", 3, False, ("random", "random"), "")


def test_experiment_metadata_constants() -> None:
    assert MIN_GAMES_JUSTIFIED == 170
    assert PRIMARY_METRIC == "win_rate_p0"
    assert "exploratory" not in SECONDARY_METRICS
    assert "no early stopping" in STOPPING_RULE
