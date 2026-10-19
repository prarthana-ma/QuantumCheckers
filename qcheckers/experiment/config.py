"""Experiment configuration.

Owner: **Person D -- measurement, statistics and plots**, with **Person B** owning the
fields the runner reads. Person C owns the condition *labels* as the extension
vocabulary; this module is where those labels become executable config.

Why config-as-data
------------------
The ablation (brief section 11) must hold everything fixed except the studied feature.
Describing each condition as a frozen dataclass instead of a hand-written script makes
that checkable at a glance and makes the label strings that appear in plots come from
exactly one place.

Two rules for this file, straight from the brief:

* **Do not tune per condition.** Every field except the studied feature must be equal
  across the conditions of one comparison.
* **Sample size is a decision, not a default.** ``n_games`` defaults to 0 games on
  purpose: a real batch must state its size, and the brief asks for at least 170 games
  per condition *if justified*, after a pilot variance check. The
  :data:`MIN_GAMES_JUSTIFIED` constant records that number so it is visible in code
  rather than buried in a slide.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

#: Brief section 11 target: "at least 170 games per condition if statistically
#: justified". Not a default -- :attr:`ExperimentConfig.n_games` starts at 0 so a
#: batch has to be sized deliberately.
MIN_GAMES_JUSTIFIED = 170

#: Confidence level behind the default ``z`` in the Wilson interval: 1.96 is the
#: two-sided 95% normal quantile.
Z_95 = 1.96


@dataclass(frozen=True, slots=True)
class ConditionConfig:
    """One experimental condition: the unit of the ablation.

    Attributes
    ----------
    label:
        Condition identifier, used as the JSONL filename stem and the plot legend.
        Must stay stable once the ablation is frozen, because existing logs key off it.
    level:
        Engine level. ``0`` classical, ``1`` adds spread, ``2`` adds rejoin.
    allow_observe:
        The studied feature: is voluntary measurement available?
    agent_kinds:
        ``(player_0, player_1)`` agent kinds, e.g. ``("prob", "random")``.
    description:
        One line for the report and for the plot subtitle.
    """

    label: str
    level: int
    allow_observe: bool
    agent_kinds: tuple[str, str]
    description: str = ""

    def __post_init__(self) -> None:
        if self.level not in (0, 1, 2):
            raise ValueError(f"level must be 0, 1 or 2; got {self.level!r}")
        if len(self.agent_kinds) != 2:
            raise ValueError(
                f"agent_kinds must name two players; got {self.agent_kinds!r}"
            )

    @property
    def filename(self) -> str:
        return f"{self.label}.jsonl"

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "level": self.level,
            "allow_observe": self.allow_observe,
            "agent_kinds": list(self.agent_kinds),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Everything needed to run one experiment reproducibly.

    Attributes
    ----------
    name:
        Experiment name; used in output paths and plot titles.
    condition:
        The single condition to run.
    seeds:
        Explicit seed list. Explicit beats a seed *count* here: the exact seeds are
        part of the reproducibility record, and a regenerated batch must use the same
        ones.
    n_games:
        Number of games planned. ``0`` means "not yet sized" -- the default forces a
        deliberate choice.
    time_budget_s:
        Optional wall-clock budget per game, in seconds, used by the CLI scripts to
        stop a batch that is clearly too slow (brief Gate 4).
    board_size:
        Board edge length passed to the engine.
    max_plies:
        Per-game ply cap.
    z:
        Two-sided normal quantile for confidence intervals.
    notes:
        Free-text provenance, e.g. "toy engine, Gate 2 pending".
    """

    name: str = "unnamed"
    condition: ConditionConfig | None = None
    seeds: tuple[int, ...] = ()
    n_games: int = 0
    time_budget_s: float | None = None
    board_size: int = 4
    max_plies: int = 200
    z: float = Z_95
    notes: str = ""

    def __post_init__(self) -> None:
        if self.n_games < 0:
            raise ValueError(f"n_games must be >= 0; got {self.n_games}")
        if self.seeds and self.n_games and len(self.seeds) != self.n_games:
            raise ValueError(
                f"seeds ({len(self.seeds)}) and n_games ({self.n_games}) disagree"
            )
        if self.z <= 0:
            raise ValueError(f"z must be > 0; got {self.z}")

    # -- derived views -----------------------------------------------------

    @property
    def games(self) -> int:
        """Games actually to be played: the explicit seeds, else ``n_games``."""
        return len(self.seeds) if self.seeds else self.n_games

    def seed_list(self, base_seed: int = 0) -> tuple[int, ...]:
        """Return ``n_games`` seeds starting at ``base_seed``.

        Used when a run wants generated seeds instead of an explicit list. The result
        is deterministic in ``(base_seed, n_games)``.
        """
        if self.seeds:
            return self.seeds
        return tuple(base_seed + offset for offset in range(self.n_games))

    def engine_kwargs(self) -> Mapping[str, Any]:
        """Kwargs for the engine constructor for this configuration."""
        if self.condition is None:
            raise ValueError(f"experiment {self.name!r} has no condition set")
        return {
            "level": self.condition.level,
            "allow_observe": self.condition.allow_observe,
            "board_size": self.board_size,
            "max_plies": self.max_plies,
        }

    def with_seeds(self, seeds: tuple[int, ...]) -> "ExperimentConfig":
        """Copy with a different seed list, keeping ``n_games`` consistent."""
        return replace(self, seeds=tuple(seeds), n_games=len(seeds))

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "condition": self.condition.to_json() if self.condition else None,
            "seeds": list(self.seeds),
            "n_games": self.n_games,
            "games": self.games,
            "time_budget_s": self.time_budget_s,
            "board_size": self.board_size,
            "max_plies": self.max_plies,
            "z": self.z,
            "notes": self.notes,
            "min_games_justified": MIN_GAMES_JUSTIFIED,
        }


#: The four conditions of the core ablation, in reporting order.
#:
#: The comparison that matters is classical vs. quantum-enabled at *matched* agent
#: strength, with and without the Observe option. Everything except ``level`` and
#: ``allow_observe`` is held constant, which is the whole point of listing them
#: side by side.
CONDITIONS: tuple[ConditionConfig, ...] = (
    ConditionConfig(
        label="classical-random-vs-random",
        level=0,
        allow_observe=False,
        agent_kinds=("random", "random"),
        description="Classical baseline: random vs random, no uncertainty mechanics.",
    ),
    ConditionConfig(
        label="classical-mcts-vs-random",
        level=0,
        allow_observe=False,
        agent_kinds=("mcts", "random"),
        description="Classical baseline: tree search vs random, no uncertainty mechanics.",
    ),
    ConditionConfig(
        label="quantum-observe-vs-random",
        level=2,
        allow_observe=True,
        agent_kinds=("observe", "random"),
        description="Quantum-enabled with voluntary Observe vs random.",
    ),
    ConditionConfig(
        label="quantum-prob-vs-random",
        level=2,
        allow_observe=False,
        agent_kinds=("prob", "random"),
        description="Quantum-enabled, probability-aware search vs random, no Observe.",
    ),
)


def condition_by_label(label: str) -> ConditionConfig:
    """Look up a condition in :data:`CONDITIONS` by label.

    Raises
    ------
    KeyError
        If the label is unknown -- a typo must not silently run the wrong condition.
    """
    for condition in CONDITIONS:
        if condition.label == label:
            return condition
    known = ", ".join(c.label for c in CONDITIONS)
    raise KeyError(f"unknown condition {label!r}; known labels: {known}")


__all__ = [
    "CONDITIONS",
    "MIN_GAMES_JUSTIFIED",
    "Z_95",
    "ConditionConfig",
    "ExperimentConfig",
    "condition_by_label",
]