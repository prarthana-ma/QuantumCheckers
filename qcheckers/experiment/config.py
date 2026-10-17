"""Experiment configuration for QuantumCheckers.

Validated configuration schema for experiment runs. Coordinates with P2 (Vrinda)
on the statistical fields and with the runner on execution parameters.

Configuration format: JSON or TOML. The schema is versioned via ``version``.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Sequence

#: Minimum games per condition justified by the brief (P1's code imports this).
MIN_GAMES_JUSTIFIED: int = 20


@dataclass
class ExperimentConfig:
    """Complete configuration for an experiment run.

    All fields are validated on construction. Use :meth:`from_dict` for lenient
    loading (unknown keys ignored) or construct directly for strict validation.
    """

    experiment_id: str = "default"
    version: str = "1"
    agents: tuple[str, str] = ("random", "mcts")
    agent_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    n_games: int = 10
    base_seed: int = 0
    board_size: int = 4
    max_plies: int = 120
    level: int = 2
    allow_observe: bool = True
    alternate_seats: bool = True
    engine_kind: str = "toy"
    output_dir: str = "results"
    export_replays: bool = False
    log_level: str = "INFO"
    timeout_seconds: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        if self.n_games < 1:
            raise ValueError(f"n_games must be >= 1, got {self.n_games}")
        if self.board_size < 4:
            raise ValueError(f"board_size must be >= 4, got {self.board_size}")
        if self.max_plies < 1:
            raise ValueError(f"max_plies must be >= 1, got {self.max_plies}")
        if self.level not in (0, 1, 2):
            raise ValueError(f"level must be 0, 1 or 2, got {self.level}")
        if self.base_seed < 0:
            raise ValueError(f"base_seed must be >= 0, got {self.base_seed}")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be > 0 or None, got {self.timeout_seconds}"
            )
        if len(self.agents) != 2:
            raise ValueError(
                f"agents must have exactly 2 entries, got {len(self.agents)}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        """Construct from a dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        # agents comes as a list from JSON/TOML — convert to tuple
        if "agents" in kwargs and isinstance(kwargs["agents"], list):
            kwargs["agents"] = tuple(kwargs["agents"])
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        result: dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, tuple):
                val = list(val)
            result[f.name] = val
        return result


def load_config(path: str | Path) -> ExperimentConfig:
    """Load configuration from a JSON or TOML file.

    Raises FileNotFoundError if the path does not exist, ValueError for parse errors
    or invalid configuration values.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".toml":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid TOML in {p}: {exc}") from exc
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {p}: {exc}") from exc
    return ExperimentConfig.from_dict(data)


def save_config(config: ExperimentConfig, path: str | Path) -> None:
    """Save configuration to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")


__all__ = [
    "ExperimentConfig",
    "MIN_GAMES_JUSTIFIED",
    "load_config",
    "save_config",
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
    # TODO-confirm the board-size default with P5.
    board_size: int = 4
    # TODO-confirm the max_plies default with P5.
    max_plies: int = 120
    z: float = Z_95
    notes: str = (
        "TODO-confirm with P1/P5 whether Rejoin is disabled when Observe is off; "
        "TODO-confirm engine level numbering with P5."
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


# TODO-confirm with P5 what these engine level numbers mean.
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
        "MCTS versus random with Observe enabled; level semantics TODO-confirm with P5.",
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
        "TODO-confirm with P5.",
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
