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
    config = ExperimentConfig("smoke", condition, (1, 2), 2)

    with pytest.raises(FrozenInstanceError):
        config.n_games = 3  # type: ignore[misc]
    with pytest.raises(ValueError, match="agree"):
        ExperimentConfig("invalid", condition, (1,), 2)
    with pytest.raises(ValueError, match="level"):
        ConditionConfig("invalid", 3, False, ("random", "random"), "")


def test_experiment_metadata_constants() -> None:
    assert MIN_GAMES_JUSTIFIED == 170
    assert PRIMARY_METRIC == "win_rate_p0"
    assert "exploratory" not in SECONDARY_METRICS
    assert "no early stopping" in STOPPING_RULE
