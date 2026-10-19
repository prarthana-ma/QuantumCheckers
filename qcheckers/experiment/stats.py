"""Pure-Python statistical summaries for experiment game records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


Z_95 = 1.959963984540054


class GameLike(Protocol):
    """Fields consumed from a game record by the statistics helpers."""

    seed: int
    winner: int | None
    plies: int
    collapses: int
    observe_moves: int
    spread_moves: int


METRICS: tuple[str, ...] = (
    "win_rate_p0",
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


@dataclass(frozen=True, slots=True)
class Rate:
    """A binomial proportion and its Wilson interval."""

    p: float
    low: float
    high: float
    n: int

    @property
    def point(self) -> float:
        """Alias for the point estimate used by the ablation script."""
        return self.p

    @property
    def defined(self) -> bool:
        """Whether this rate has observations."""
        return self.n > 0


def _validate_z(z: float) -> None:
    if not math.isfinite(z) or z <= 0:
        raise ValueError(f"z must be finite and > 0; got {z!r}")


def _validate_counts(successes: int, n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError(f"n must be an integer; got {n!r}")
    if not isinstance(successes, int) or isinstance(successes, bool):
        raise ValueError(f"successes must be an integer; got {successes!r}")
    if n < 0:
        raise ValueError(f"n must be >= 0; got {n}")
    if successes < 0:
        raise ValueError(f"successes must be >= 0; got {successes}")
    if successes > n:
        raise ValueError(f"successes ({successes}) cannot exceed n ({n})")


def wilson_interval(
    successes: int, n: int, z: float = 1.96
) -> tuple[float, float]:
    """Compute the two-sided Wilson score interval for a binomial proportion."""
    _validate_counts(successes, n)
    _validate_z(z)
    if n == 0:
        return (0.0, 1.0)

    p = successes / n
    z_squared = z * z
    denominator = 1.0 + z_squared / n
    center = (p + z_squared / (2.0 * n)) / denominator
    margin = (z / denominator) * math.sqrt(
        p * (1.0 - p) / n + z_squared / (4.0 * n * n)
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def rate(successes: int, n: int, z: float = 1.96) -> Rate:
    """Return the proportion and Wilson bounds as a small :class:`Rate` result."""
    _validate_counts(successes, n)
    low, high = wilson_interval(successes, n, z)
    return Rate(successes / n if n else 0.0, low, high, n)


def compare_rates(
    a_succ: int, a_n: int, b_succ: int, b_n: int, z: float = 1.96
) -> dict[str, float | bool]:
    """Compare independent proportions with Newcombe method 10 bounds."""
    a = rate(a_succ, a_n, z)
    b = rate(b_succ, b_n, z)
    difference = a.p - b.p
    lower = difference - math.sqrt((a.p - a.low) ** 2 + (b.high - b.p) ** 2)
    upper = difference + math.sqrt((a.high - a.p) ** 2 + (b.p - b.low) ** 2)
    lower = max(-1.0, lower)
    upper = min(1.0, upper)
    return {
        "difference": difference,
        "lower": lower,
        "upper": upper,
        "excludes_zero": not (lower <= 0.0 <= upper),
    }


def compare_paired(
    a_outcomes: Sequence[int | bool],
    b_outcomes: Sequence[int | bool],
    z: float = 1.96,
) -> dict[str, float | bool | int]:
    """Compare matched binary outcomes with Newcombe method 10 and phi correction."""
    if len(a_outcomes) != len(b_outcomes):
        raise ValueError(
            f"outcome lengths differ: {len(a_outcomes)} != {len(b_outcomes)}"
        )
    if not a_outcomes:
        raise ValueError("paired outcomes must not be empty")
    _validate_z(z)

    checked_a: list[int] = []
    checked_b: list[int] = []
    for index, (a_value, b_value) in enumerate(zip(a_outcomes, b_outcomes)):
        if not isinstance(a_value, (int, bool)) or a_value not in (0, 1):
            raise ValueError(f"A outcome at index {index} is not binary: {a_value!r}")
        if not isinstance(b_value, (int, bool)) or b_value not in (0, 1):
            raise ValueError(f"B outcome at index {index} is not binary: {b_value!r}")
        checked_a.append(int(a_value))
        checked_b.append(int(b_value))

    n = len(checked_a)
    a_only = sum(a == 1 and b == 0 for a, b in zip(checked_a, checked_b))
    b_only = sum(a == 0 and b == 1 for a, b in zip(checked_a, checked_b))
    both = sum(a == 1 and b == 1 for a, b in zip(checked_a, checked_b))
    neither = n - a_only - b_only - both
    p_a = (a_only + both) / n
    p_b = (b_only + both) / n
    difference = p_a - p_b

    variance_product = p_a * (1.0 - p_a) * p_b * (1.0 - p_b)
    correlation = 0.0
    if a_only + b_only > 0 and variance_product > 0.0:
        correlation = (both / n - p_a * p_b) / math.sqrt(variance_product)

    a_low, a_high = wilson_interval(a_only + both, n, z)
    b_low, b_high = wilson_interval(b_only + both, n, z)
    lower_a = p_a - a_low
    lower_b = b_high - p_b
    upper_a = a_high - p_a
    upper_b = p_b - b_low
    lower_margin_sq = (
        lower_a * lower_a + lower_b * lower_b - 2.0 * correlation * lower_a * lower_b
    )
    upper_margin_sq = (
        upper_a * upper_a + upper_b * upper_b - 2.0 * correlation * upper_a * upper_b
    )
    lower = max(-1.0, difference - math.sqrt(max(0.0, lower_margin_sq)))
    upper = min(1.0, difference + math.sqrt(max(0.0, upper_margin_sq)))
    return {
        "difference": difference,
        "lower": lower,
        "upper": upper,
        "excludes_zero": not (lower <= 0.0 <= upper),
        "n": n,
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "neither": neither,
    }


def _record_mapping(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    to_json = getattr(record, "to_json", None)
    if callable(to_json):
        result = to_json()
        if isinstance(result, Mapping):
            return result
    return {}


def _field(record: Any, *names: str) -> Any:
    data = _record_mapping(record)
    for name in names:
        if name in data:
            return data[name]
        if hasattr(record, name):
            return getattr(record, name)
    raise ValueError(f"game record is missing required field {names[0]!r}")


def _count_field(record: Any, name: str, *aliases: str) -> int:
    data = _record_mapping(record)
    value: Any = None
    found = False
    for field_name in (name, *aliases):
        if field_name in data:
            value = data[field_name]
            found = True
            break
        if hasattr(record, field_name):
            value = getattr(record, field_name)
            found = True
            break
    if not found:
        metrics = data.get("metrics")
        if not isinstance(metrics, Mapping):
            metrics = getattr(record, "metrics", None)
        if isinstance(metrics, Mapping):
            for field_name in (name, *aliases):
                if field_name in metrics:
                    value = metrics[field_name]
                    found = True
                    break
    if not found:
        raise ValueError(f"game record is missing required field {name!r}")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"game record field {name!r} must be a non-negative integer")
    return value


def _seed(record: Any) -> Any:
    return _field(record, "seed")


def _winner(record: Any) -> Any:
    return _field(record, "winner")


def _plies(record: Any) -> int:
    return _count_field(record, "length", "plies", "n_plies")


def _collapses(record: Any) -> int:
    return _count_field(record, "collapses")


def _observe_moves(record: Any) -> int:
    return _count_field(record, "observe_moves")


def _spread_moves(record: Any) -> int:
    return _count_field(record, "spread_moves")


def _binary_outcome(record: Any, metric_index: int) -> int:
    if metric_index in (0, 1):
        winner = _winner(record)
        if winner is not None and winner not in (0, 1):
            raise ValueError(f"winner must be 0, 1, or None; got {winner!r}")
        return int(winner == metric_index)
    if metric_index == 2:
        return int(_winner(record) is None)
    count_by_metric = (_collapses, _observe_moves, _spread_moves)
    return int(count_by_metric[metric_index - 3](record) > 0)


def paired_outcomes(
    a_records: Sequence[GameLike],
    b_records: Sequence[GameLike],
    metric: str,
) -> tuple[list[int], list[int]]:
    """Match unique seeds and extract paired binary outcomes for a named metric."""
    try:
        metric_index = METRICS.index(metric)
    except ValueError as exc:
        raise ValueError(f"unsupported paired binary metric: {metric!r}") from exc
    if metric_index >= 6:
        raise ValueError(f"metric is not a paired binary metric: {metric!r}")

    def index_records(records: Sequence[GameLike], arm: str) -> dict[Any, GameLike]:
        indexed: dict[Any, GameLike] = {}
        for record in records:
            seed = _seed(record)
            if seed is None:
                raise ValueError(f"{arm} record is missing a usable seed")
            try:
                if seed in indexed:
                    raise ValueError(f"{arm} records contain duplicate seed {seed!r}")
                indexed[seed] = record
            except TypeError as exc:
                raise ValueError(f"{arm} record has an unhashable seed: {seed!r}") from exc
        return indexed

    a_by_seed = index_records(a_records, "A")
    b_by_seed = index_records(b_records, "B")
    if a_by_seed.keys() != b_by_seed.keys():
        raise ValueError("A and B records must contain the same seeds exactly once")
    seeds = list(a_by_seed)
    return (
        [_binary_outcome(a_by_seed[seed], metric_index) for seed in seeds],
        [_binary_outcome(b_by_seed[seed], metric_index) for seed in seeds],
    )


def _mean(values: Sequence[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_sd(values: Sequence[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def summarize(
    records: Sequence[GameLike], z: float = 1.96, reference_player: int = 0
) -> dict[str, Any]:
    """Summarize game outcomes, event incidences, and per-game descriptive statistics."""
    _validate_z(z)
    if reference_player not in (0, 1):
        raise ValueError(f"reference_player must be 0 or 1; got {reference_player!r}")
    games = list(records)
    n = len(games)
    counts = [0] * 6
    lengths: list[int] = []
    collapse_counts: list[int] = []
    observe_counts: list[int] = []
    spread_counts: list[int] = []

    for record in games:
        winner = _winner(record)
        if winner is not None and winner not in (0, 1):
            raise ValueError(f"winner must be 0, 1, or None; got {winner!r}")
        for metric_index in range(6):
            counts[metric_index] += _binary_outcome(record, metric_index)
        lengths.append(_plies(record))
        collapse_counts.append(_collapses(record))
        observe_counts.append(_observe_moves(record))
        spread_counts.append(_spread_moves(record))

    metric_results = {
        METRICS[index]: rate(counts[index], n, z) for index in range(6)
    }
    means = (
        _mean(lengths),
        _sample_sd(lengths),
        _mean(collapse_counts),
        _mean(observe_counts),
        _mean(spread_counts),
    )
    descriptive = {METRICS[index + 6]: means[index] for index in range(5)}
    return {
        "n_games": n,
        "reference_player": reference_player,
        "metrics": metric_results,
        "rates": descriptive,
    }


def compare_conditions(
    a_records: Sequence[GameLike],
    b_records: Sequence[GameLike],
    *,
    metrics: Sequence[str] = ("win_rate_p0", "draw_rate", "collapse_rate"),
    z: float = Z_95,
) -> dict[str, Any]:
    """Summarize two conditions and compare each requested binary rate."""
    summary_a = summarize(a_records, z)
    summary_b = summarize(b_records, z)

    def has_unique_seeds(records: Sequence[GameLike]) -> bool:
        seeds: set[Any] = set()
        for record in records:
            try:
                seed = _seed(record)
                if seed is None or seed in seeds:
                    return False
                seeds.add(seed)
            except (TypeError, ValueError):
                return False
        return bool(records)

    paired = (
        has_unique_seeds(a_records)
        and has_unique_seeds(b_records)
        and {_seed(record) for record in a_records}
        == {_seed(record) for record in b_records}
    )
    comparisons: dict[str, Any] = {}
    for metric in metrics:
        rate_a: Rate = summary_a["metrics"][metric]
        rate_b: Rate = summary_b["metrics"][metric]
        if paired:
            outcomes_a, outcomes_b = paired_outcomes(a_records, b_records, metric)
            result = compare_paired(outcomes_a, outcomes_b, z)
            method = "paired"
        else:
            metric_index = METRICS.index(metric)
            successes_a = sum(_binary_outcome(record, metric_index) for record in a_records)
            successes_b = sum(_binary_outcome(record, metric_index) for record in b_records)
            result = compare_rates(
                successes_a, rate_a.n, successes_b, rate_b.n, z
            )
            method = "unpaired"
        comparisons[metric] = {
            "metric": metric,
            "a": rate_a,
            "b": rate_b,
            "difference": result["difference"],
            "diff_low": result["lower"],
            "diff_high": result["upper"],
            "excludes_zero": result["excludes_zero"],
            "method": method,
        }
    return {
        "a": summary_a,
        "b": summary_b,
        "comparisons": comparisons,
    }


def format_comparison(
    label_a: str, label_b: str, comparison: Mapping[str, Any]
) -> str:
    """Format a metric's difference and interval without significance claims."""
    return (
        f"{comparison['metric']}: {label_a} - {label_b} "
        f"{comparison['difference']:+.3f} "
        f"[{comparison['diff_low']:+.3f}, {comparison['diff_high']:+.3f}]"
    )


__all__ = [
    "GameLike",
    "METRICS",
    "Rate",
    "Z_95",
    "compare_conditions",
    "compare_paired",
    "compare_rates",
    "format_comparison",
    "paired_outcomes",
    "rate",
    "summarize",
    "wilson_interval",
]
