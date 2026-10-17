"""Reproducible experiment configuration and condition registry."""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_GAMES_JUSTIFIED = 170
"""A target that needs the sample-size justification, not a guarantee."""

Z_95 = 1.96

# TODO-confirm with P1: whether win_rate_p0 is the primary metric.
PRIMARY_METRIC = "win_rate_p0"
# Exploratory metrics; interpret these as secondary to PRIMARY_METRIC.
SECONDARY_METRICS = (
    "win_rate_p1",
    "draw_rate",
    "collapse_rate",
    "observe_usage",
    "spread_usage",
    "mean_length",
    "stdev_length",
    "mean_collapses",
    "mean_observe_moves",
    "mean_spread_moves",
)
STOPPING_RULE = (
    "Fixed planned n; no early stopping; each game is subject to the per-game "
    "max_plies cap."
)


@dataclass(frozen=True, slots=True)
class ConditionConfig:
    """One experimental condition and the agents assigned to its players."""

    label: str
    level: int
    allow_observe: bool
    agent_kinds: tuple[str, str]
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("label must be a non-empty string")
        if not isinstance(self.level, int) or isinstance(self.level, bool):
            raise ValueError("level must be an integer")
        if self.level not in (0, 1, 2):
            raise ValueError(f"level must be 0, 1 or 2; got {self.level!r}")
        if not isinstance(self.allow_observe, bool):
            raise ValueError("allow_observe must be a bool")
        if not isinstance(self.agent_kinds, tuple) or len(self.agent_kinds) != 2:
            raise ValueError("agent_kinds must be a two-item tuple")
        if any(not isinstance(agent, str) or not agent for agent in self.agent_kinds):
            raise ValueError("agent_kinds must contain non-empty strings")
        if not isinstance(self.description, str):
            raise ValueError("description must be a string")


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Immutable settings for a reproducible batch of games."""

    name: str
    condition: ConditionConfig
    seeds: tuple[int, ...] = ()
    n_games: int = 0
    # Board-size default adopted from previous implementation.
    board_size: int = 4
    # Max-plies default adopted from previous implementation.
    max_plies: int = 200
    z: float = Z_95
    notes: str = (
        "TODO-confirm with P1/P5 whether Rejoin is disabled when Observe is off; "
        "engine level numbering adopted from previous implementation."
    )

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.condition, ConditionConfig):
            raise ValueError("condition must be a ConditionConfig")
        if not isinstance(self.seeds, tuple):
            raise ValueError("seeds must be a tuple")
        if any(not isinstance(seed, int) or isinstance(seed, bool) for seed in self.seeds):
            raise ValueError("seeds must contain integers")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        if not isinstance(self.n_games, int) or isinstance(self.n_games, bool):
            raise ValueError("n_games must be an integer")
        if self.n_games < 0:
            raise ValueError(f"n_games must be >= 0; got {self.n_games}")
        if self.seeds and self.n_games and len(self.seeds) != self.n_games:
            raise ValueError("seeds length and n_games must agree")
        if not isinstance(self.board_size, int) or isinstance(self.board_size, bool):
            raise ValueError("board_size must be an integer")
        if self.board_size < 4:
            raise ValueError(f"board_size must be at least 4; got {self.board_size}")
        if not isinstance(self.max_plies, int) or isinstance(self.max_plies, bool):
            raise ValueError("max_plies must be an integer")
        if self.max_plies < 1:
            raise ValueError(f"max_plies must be >= 1; got {self.max_plies}")
        if not isinstance(self.z, (int, float)) or isinstance(self.z, bool):
            raise ValueError("z must be numeric")
        if not math.isfinite(self.z) or self.z <= 0:
            raise ValueError(f"z must be finite and > 0; got {self.z!r}")
        if not isinstance(self.notes, str):
            raise ValueError("notes must be a string")


def ablation_label(agent_a: str, agent_b: str, observe: bool) -> str:
    """Build the stable label for one supported Observe ablation cell."""
    if agent_a not in ("mcts", "prob") or agent_b != "random":
        raise ValueError("ablation labels require mcts/prob against random")
    if not isinstance(observe, bool):
        raise ValueError("observe must be a bool")
    suffix = "obs" if observe else "noobs"
    return f"ablation-{agent_a}-vs-{agent_b}-{suffix}"


# Engine level numbers adopted from previous implementation.
# TODO-confirm with P1/P5 whether Rejoin is disabled when Observe is off.
CONDITIONS: tuple[ConditionConfig, ...] = (
    ConditionConfig(
        "classical-random-vs-random",
        0,
        False,
        ("random", "random"),
        "Classical baseline: random versus random.",
    ),
    ConditionConfig(
        "classical-mcts-vs-random",
        0,
        False,
        ("mcts", "random"),
        "Classical baseline: MCTS versus random.",
    ),
    ConditionConfig(
        ablation_label("mcts", "random", True),
        2,
        True,
        ("mcts", "random"),
        "MCTS versus random with Observe enabled; level semantics adopted from "
        "previous implementation.",
    ),
    ConditionConfig(
        ablation_label("mcts", "random", False),
        2,
        False,
        ("mcts", "random"),
        "MCTS versus random with Observe disabled; Rejoin behavior TODO-confirm with P1/P5.",
    ),
    ConditionConfig(
        ablation_label("prob", "random", True),
        2,
        True,
        ("prob", "random"),
        "Probability-aware agent versus random with Observe enabled; level semantics "
        "adopted from previous implementation.",
    ),
    ConditionConfig(
        ablation_label("prob", "random", False),
        2,
        False,
        ("prob", "random"),
        "Probability-aware agent versus random with Observe disabled; Rejoin behavior "
        "TODO-confirm with P1/P5.",
    ),
)


def condition_by_label(label: str) -> ConditionConfig:
    """Look up a registered condition by label."""
    for condition in CONDITIONS:
        if condition.label == label:
            return condition
    known = ", ".join(condition.label for condition in CONDITIONS)
    raise KeyError(f"unknown condition {label!r}; known labels: {known}")


def seed_list(base_seed: int, n: int) -> list[int]:
    """Generate deterministic consecutive seeds without using global randomness."""
    if not isinstance(base_seed, int) or isinstance(base_seed, bool):
        raise ValueError("base_seed must be an integer")
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("n must be a non-negative integer")
    return [base_seed + offset for offset in range(n)]


def matched_seeds(n: int) -> tuple[list[int], list[int]]:
    """Return equal consecutive seed lists for two matched arms."""
    seeds = seed_list(0, n)
    return seeds, seeds.copy()


__all__ = [
    "CONDITIONS",
    "MIN_GAMES_JUSTIFIED",
    "PRIMARY_METRIC",
    "SECONDARY_METRICS",
    "STOPPING_RULE",
    "Z_95",
    "ConditionConfig",
    "ExperimentConfig",
    "ablation_label",
    "condition_by_label",
    "matched_seeds",
    "seed_list",
]
