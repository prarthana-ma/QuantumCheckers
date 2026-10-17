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
]
