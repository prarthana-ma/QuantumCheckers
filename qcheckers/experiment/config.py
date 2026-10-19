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
from typing import Any

#: Minimum games per condition justified by the brief (P1's code imports this).
MIN_GAMES_JUSTIFIED: int = 170

Z_95: float = 1.96

# TODO-confirm with P1: whether win_rate_p0 is the primary metric.
PRIMARY_METRIC: str = "win_rate_p0"
# Exploratory metrics; interpret these as secondary to PRIMARY_METRIC.
SECONDARY_METRICS: tuple[str, ...] = (
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
STOPPING_RULE: str = (
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


@dataclass(frozen=True)
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
                f"agents must agree on exactly 2 entries; got {len(self.agents)}"
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


def ablation_label(agent_a: str, agent_b: str, observe: bool) -> str:
    """Build the stable label for one supported Observe ablation cell."""
    valid_first: set[str] = {"mcts", "prob"}
    if agent_a not in valid_first:
        raise ValueError(
            f"unsupported agent kind for first position: {agent_a!r}; "
            f"expected one of {valid_first}"
        )
    if agent_b not in {"random", "mcts", "prob"} or agent_b == agent_a:
        raise ValueError(
            f"unsupported agent kind for second position: {agent_b!r}; "
            "expected random or the other of mcts/prob"
        )
    suffix = "obs" if observe else "noobs"
    return f"ablation-{agent_a}-vs-{agent_b}-{suffix}"


# Engine level numbers adopted from previous implementation.
# TODO-confirm with P1/P5 whether Rejoin is disabled when Observe is off.
CONDITIONS: tuple[ConditionConfig, ...] = (
    ConditionConfig(
        label="classical-random-vs-random",
        level=0,
        allow_observe=False,
        agent_kinds=("random", "random"),
        description="Classical baseline: random versus random.",
    ),
    ConditionConfig(
        label="classical-mcts-vs-random",
        level=0,
        allow_observe=False,
        agent_kinds=("mcts", "random"),
        description="Classical baseline: MCTS versus random.",
    ),
    ConditionConfig(
        label=ablation_label("mcts", "random", True),
        level=2,
        allow_observe=True,
        agent_kinds=("mcts", "random"),
        description="MCTS versus random with Observe enabled.",
    ),
    ConditionConfig(
        label=ablation_label("mcts", "random", False),
        level=2,
        allow_observe=False,
        agent_kinds=("mcts", "random"),
        description="MCTS versus random with Observe disabled.",
    ),
    ConditionConfig(
        label=ablation_label("prob", "random", True),
        level=2,
        allow_observe=True,
        agent_kinds=("prob", "random"),
        description="Probability-aware agent versus random with Observe enabled.",
    ),
    ConditionConfig(
        label=ablation_label("prob", "random", False),
        level=2,
        allow_observe=False,
        agent_kinds=("prob", "random"),
        description="Probability-aware agent versus random with Observe disabled.",
    ),
)


def condition_by_label(label: str) -> ConditionConfig:
    """Look up a registered condition by label."""
    for condition in CONDITIONS:
        if condition.label == label:
            return condition
    known = ", ".join(c.label for c in CONDITIONS)
    raise KeyError(f"unknown condition {label!r}; known labels: {known}")


def seed_list(base_seed: int, n: int) -> list[int]:
    """Generate deterministic consecutive seeds."""
    return [base_seed + offset for offset in range(n)]


def matched_seeds(n: int) -> tuple[list[int], list[int]]:
    """Return equal consecutive seed lists for two matched arms."""
    seeds = seed_list(0, n)
    return seeds, seeds.copy()


__all__ = [
    "ExperimentConfig",
    "MIN_GAMES_JUSTIFIED",
    "Z_95",
    "PRIMARY_METRIC",
    "SECONDARY_METRICS",
    "STOPPING_RULE",
    "ConditionConfig",
    "CONDITIONS",
    "ablation_label",
    "condition_by_label",
    "load_config",
    "save_config",
    "seed_list",
    "matched_seeds",
]
