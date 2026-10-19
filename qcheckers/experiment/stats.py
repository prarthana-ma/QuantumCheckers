"""Statistics for the ablation: Wilson intervals, rate comparison, summarisation.

Owner: **Person D -- measurement, statistics and plots**. Nobody else should change
these functions: brief section 13 gives Person D ownership of metric definitions, the
interval computation, and the sample-size justification, and requires that any plot
they accept be regenerable from logged seeds.

Why Wilson and not the normal approximation
-------------------------------------------
Every rate here is a proportion from a small, fixed batch (a few hundred games at
best), and several of the interesting rates sit near 0 or 1 -- collapse frequency,
draw rate, Observe usage. The normal approximation produces intervals that run past
``[0, 1]`` and undercover badly in exactly that regime. Wilson's score interval stays
inside ``[0, 1]`` by construction and behaves sanely at ``0/n`` and ``n/n``, so it is
the default everywhere. :func:`z_for_confidence` exists so the confidence level can be
stated in a plot without anyone reaching for a different formula.

Reference for the formula: Wilson, E.B. (1927), *Probable Inference, the Law of
Succession, and Statistical Inference*, JASA 22(158):209-212.

What this module deliberately does not do
-----------------------------------------
* **No significance test by default.** :func:`compare_rates` reports a difference with
  a Newcombe-style interval built from the two Wilson intervals and lets the reader
  decide whether it excludes zero. The brief warns against optimising an agent until
  the test passes, and a p-value invites exactly that.
* **No hidden pre-registration.** The metric list is fixed by
  :data:`SUMMARIZE_KEYS`; adding a metric after seeing results is a change Person D
  must justify in the reproducibility report.

Pure stdlib: no numpy, no scipy. Wilson needs one square root and one log.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, cast

#: Two-sided 95% normal quantile. The brief's default.
Z_95 = 1.959963984540054

#: Metric names :func:`summarize` always reports, in output order. Treat this list as
#: the pre-registered metric set.
SUMMARIZE_KEYS: tuple[str, ...] = (
    "win_rate_p0",
    "win_rate_p1",
    "draw_rate",
    "collapse_rate",
    "mean_length",
    "mean_collapses",
    "observe_usage",
    "spread_usage",
)


# ---------------------------------------------------------------------------
# Wilson score interval
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rate:
    """A proportion with its Wilson interval attached.

    Attributes
    ----------
    successes:
        Numerator.
    n:
        Denominator.
    point:
        ``successes / n``, or ``0.0`` when ``n == 0``.
    low, high:
        Wilson interval bounds, clamped to ``[0, 1]``. Both are ``0.0`` when ``n == 0``
        and the interval is reported as undefined via :attr:`defined`.
    z:
        The normal quantile used.
    """

    successes: int
    n: int
    point: float
    low: float
    high: float
    z: float

    @property
    def defined(self) -> bool:
        """False when ``n == 0``, in which case the bounds carry no information."""
        return self.n > 0

    @property
    def width(self) -> float:
        return self.high - self.low

    def to_json(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "n": self.n,
            "point": self.point,
            "low": self.low,
            "high": self.high,
            "z": self.z,
            "defined": self.defined,
        }

    def __str__(self) -> str:
        if not self.defined:
            return "n=0 (undefined)"
        return (
            f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}] "
            f"({self.successes}/{self.n})"
        )


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Formula
    -------
    With ``p = successes / n``::

        centre = (p + z^2 / (2n)) / (1 + z^2 / n)
        margin = z / (1 + z^2 / n) * sqrt(p(1 - p) / n + z^2 / (4 n^2))
        (low, high) = (centre - margin, centre + margin)

    Parameters
    ----------
    successes:
        Number of events, ``0 <= successes <= n``.
    n:
        Sample size, ``>= 0``.
    z:
        Two-sided normal quantile. Use :func:`z_for_confidence` to pick one from a
        confidence level.

    Returns
    -------
    tuple[float, float]
        ``(low, high)`` clamped to ``[0.0, 1.0]``. ``(0.0, 0.0)`` when ``n == 0``.

    Raises
    ------
    ValueError
        If ``n < 0``, ``successes < 0``, ``successes > n``, or ``z <= 0``.

    Notes
    -----
    At ``successes == 0`` the interval is ``[0, z^2/(n + z^2)]``, strictly positive at
    the top end -- which is the correct behaviour, since zero observed events is not
    evidence of zero probability.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0; got {n}")
    if successes < 0:
        raise ValueError(f"successes must be >= 0; got {successes}")
    if successes > n:
        raise ValueError(f"successes ({successes}) cannot exceed n ({n})")
    if z <= 0:
        raise ValueError(f"z must be > 0; got {z}")
    if n == 0:
        return (0.0, 0.0)

    p = successes / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator
    margin = (z / denominator) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    low = max(0.0, centre - margin)
    high = min(1.0, centre + margin)
    return (low, high)


def rate(successes: int, n: int, z: float = Z_95) -> Rate:
    """:func:`wilson_interval` packaged with the point estimate."""
    if n == 0:
        if successes < 0:
            raise ValueError(f"successes must be >= 0; got {successes}")
        if successes > 0:
            raise ValueError(f"successes ({successes}) cannot exceed n ({n})")
        return Rate(0, 0, 0.0, 0.0, 0.0, z)
    low, high = wilson_interval(successes, n, z)
    return Rate(successes, n, successes / n, low, high, z)


def normal_cdf(z: float) -> float:
    """Standard normal CDF, via ``math.erfc``.

    ``P(Z <= z) = 0.5 * erfc(-z / sqrt(2))``. Exact to double precision, stdlib only.
    """
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def z_for_confidence(confidence: float = 0.95) -> float:
    """Two-sided normal quantile for a confidence level, without scipy.

    Inverts :func:`normal_cdf` by bisection. Bisection rather than a closed-form
    approximation because ``math.erfc`` is already available: a rational
    approximation would buy speed nobody needs and a second source of error to audit.

    Parameters
    ----------
    confidence:
        Confidence level in ``(0, 1)``, e.g. ``0.95``.

    Returns
    -------
    float
        ``z`` such that ``P(|Z| <= z) == confidence``, i.e. the two-sided quantile
        ``Phi^-1(1 - (1 - confidence) / 2)``.

    Raises
    ------
    ValueError
        If ``confidence`` is outside ``(0, 1)``.

    Examples
    --------
    >>> round(z_for_confidence(0.95), 4)
    1.96
    >>> round(z_for_confidence(0.99), 4)
    2.5758
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1); got {confidence!r}")

    target = 1.0 - (1.0 - confidence) / 2.0
    low, high = 0.0, 10.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if normal_cdf(middle) < target:
            low = middle
        else:
            high = middle
        if high - low < 1e-15:
            break
    return (low + high) / 2.0


# ---------------------------------------------------------------------------
# Comparing two rates
# ---------------------------------------------------------------------------


def compare_rates(
    a_successes: int,
    a_n: int,
    b_successes: int,
    b_n: int,
    z: float = Z_95,
) -> dict[str, Any]:
    """Compare two independent proportions and report the difference with an interval.

    The interval is Newcombe's hybrid-score method: the difference of the two point
    estimates, with bounds assembled from each Wilson interval. It inherits Wilson's
    behaviour near 0 and 1, which a plain Wald interval on the difference does not.

    Parameters
    ----------
    a_successes, a_n:
        Condition A's successes and sample size.
    b_successes, b_n:
        Condition B's successes and sample size.
    z:
        Two-sided normal quantile.

    Returns
    -------
    dict
        ``{"a": Rate, "b": Rate, "difference": float, "diff_low": float,
        "diff_high": float, "excludes_zero": bool, "z": float}``.

        ``difference`` is ``a - b``. ``excludes_zero`` is ``True`` when the interval
        does not straddle zero; it is *not* a p-value and carries no multiplicity
        correction across the metric set.

    Notes
    -----
    With ``a_n == 0`` or ``b_n == 0`` the difference interval is ``(0.0, 0.0)`` and
    ``excludes_zero`` is ``False``, so an undersized condition cannot be presented as
    a difference. Person D should treat that as "run more games", not as "no effect".
    """
    rate_a = rate(a_successes, a_n, z)
    rate_b = rate(b_successes, b_n, z)
    difference = rate_a.point - rate_b.point

    if not (rate_a.defined and rate_b.defined):
        return {
            "a": rate_a,
            "b": rate_b,
            "difference": difference,
            "diff_low": 0.0,
            "diff_high": 0.0,
            "excludes_zero": False,
            "z": z,
        }

    diff_low = difference - math.sqrt(
        (rate_a.point - rate_a.low) ** 2 + (rate_b.high - rate_b.point) ** 2
    )
    diff_high = difference + math.sqrt(
        (rate_a.high - rate_a.point) ** 2 + (rate_b.point - rate_b.low) ** 2
    )
    diff_low = max(-1.0, diff_low)
    diff_high = min(1.0, diff_high)

    return {
        "a": rate_a,
        "b": rate_b,
        "difference": difference,
        "diff_low": diff_low,
        "diff_high": diff_high,
        "excludes_zero": not (diff_low <= 0.0 <= diff_high),
        "z": z,
    }


def compare_paired(
    a_outcomes: Sequence[int | bool],
    b_outcomes: Sequence[int | bool],
    z: float = Z_95,
) -> dict[str, Any]:
    """Compare matched binary outcomes using Newcombe's paired method 10.

    The Wilson score intervals for each marginal proportion are combined with the
    phi-type correlation correction for paired outcomes. If the correlation is
    undefined because a marginal is 0 or 1 or there are no discordant pairs, its
    correction is set to zero, reducing the bounds to the unpaired Wilson-based
    difference interval. This is an interval estimate, not a p-value.
    """
    if len(a_outcomes) != len(b_outcomes):
        raise ValueError(
            f"outcome lengths differ: {len(a_outcomes)} != {len(b_outcomes)}"
        )
    if not a_outcomes:
        raise ValueError("paired outcomes must not be empty")
    if z <= 0:
        raise ValueError(f"z must be > 0; got {z}")

    differences: list[int] = []
    for index, (a_outcome, b_outcome) in enumerate(zip(a_outcomes, b_outcomes)):
        if not isinstance(a_outcome, (int, bool)) or a_outcome not in (0, 1):
            raise ValueError(f"A outcome at index {index} is not binary: {a_outcome!r}")
        if not isinstance(b_outcome, (int, bool)) or b_outcome not in (0, 1):
            raise ValueError(f"B outcome at index {index} is not binary: {b_outcome!r}")
        differences.append(int(a_outcome) - int(b_outcome))

    n = len(differences)
    b_only = sum(value == -1 for value in differences)
    a_only = sum(value == 1 for value in differences)
    both = sum(a == 1 and b == 1 for a, b in zip(a_outcomes, b_outcomes))
    neither = sum(a == 0 and b == 0 for a, b in zip(a_outcomes, b_outcomes))
    p_a = (a_only + both) / n
    p_b = (b_only + both) / n
    difference = p_a - p_b

    correlation = 0.0
    variance_product = p_a * (1.0 - p_a) * p_b * (1.0 - p_b)
    if a_only + b_only > 0 and variance_product > 0.0:
        correlation = (both / n - p_a * p_b) / math.sqrt(variance_product)

    a_low, a_high = wilson_interval(a_only + both, n, z)
    b_low, b_high = wilson_interval(b_only + both, n, z)
    lower_margin_sq = (
        (p_a - a_low) ** 2
        + (b_high - p_b) ** 2
        - 2.0 * correlation * (p_a - a_low) * (b_high - p_b)
    )
    upper_margin_sq = (
        (a_high - p_a) ** 2
        + (p_b - b_low) ** 2
        - 2.0 * correlation * (a_high - p_a) * (p_b - b_low)
    )
    lower = max(-1.0, difference - math.sqrt(max(0.0, lower_margin_sq)))
    upper = min(1.0, difference + math.sqrt(max(0.0, upper_margin_sq)))

    return {
        "difference": difference,
        "lower": lower,
        "upper": upper,
        "diff_low": lower,
        "diff_high": upper,
        "excludes_zero": not (lower <= 0.0 <= upper),
        "z": z,
        "n": n,
        "b_only": b_only,
        "a_only": a_only,
        "both": both,
        "neither": neither,
    }


def paired_outcomes(
    a_records: Sequence[Any],
    b_records: Sequence[Any],
    metric: str,
) -> tuple[list[int], list[int]]:
    """Match records by seed and extract paired binary outcomes for a metric.

    Supported metrics use the same event definitions as :func:`summarize`: wins by
    player, draws, games containing a collapse, and games with Observe or spread use.
    """
    metric_fields = {
        "win_rate_p0": ("winner", 0),
        "win_rate_p1": ("winner", 1),
        "draw_rate": ("winner", None),
        "collapse_rate": ("collapses", None),
        "observe_usage": ("observe_moves", None),
        "spread_usage": ("spread_moves", None),
    }
    if metric not in metric_fields:
        raise ValueError(f"unsupported paired binary metric: {metric!r}")

    def records_by_seed(records: Sequence[Any], arm: str) -> dict[Any, Any]:
        indexed: dict[Any, Any] = {}
        for record in records:
            data = _as_mapping(record)
            if "seed" not in data or data["seed"] is None:
                raise ValueError(f"{arm} record is missing a seed")
            seed = data["seed"]
            try:
                if seed in indexed:
                    raise ValueError(f"{arm} records contain duplicate seed {seed!r}")
                indexed[seed] = record
            except TypeError as exc:
                raise ValueError(f"{arm} record has an unhashable seed: {seed!r}") from exc
        return indexed

    a_by_seed = records_by_seed(a_records, "A")
    b_by_seed = records_by_seed(b_records, "B")
    if len(a_by_seed) != len(b_by_seed) or a_by_seed.keys() != b_by_seed.keys():
        raise ValueError("A and B records must contain the same seeds exactly once")

    field, expected = metric_fields[metric]

    def outcome(record: Any) -> int:
        value = _record_field(record, field)
        if metric.startswith("win_rate_"):
            return int(value == expected)
        if metric == "draw_rate":
            return int(value is None)
        if metric == "collapse_rate":
            return int(int(value or 0) > 0)
        return int(int(value or 0) > 0)

    seeds = list(a_by_seed)
    return (
        [outcome(a_by_seed[seed]) for seed in seeds],
        [outcome(b_by_seed[seed]) for seed in seeds],
    )


# ---------------------------------------------------------------------------
# Summarising a batch
# ---------------------------------------------------------------------------


def _as_mapping(record: Any) -> Mapping[str, Any]:
    """Coerce a record to a read-only mapping.

    Accepts a decoded dict straight from
    :func:`qcheckers.experiment.runner.read_jsonl`, or a
    :class:`~qcheckers.experiment.schema.GameRecord` (via ``to_json``). Supporting both
    means a caller can summarise freshly played records without a round-trip through
    JSON, while still working on a log written by an older run.
    """
    if isinstance(record, Mapping):
        return record
    to_json = getattr(record, "to_json", None)
    if callable(to_json):
        return cast(dict[str, Any], to_json())
    raise TypeError(
        f"cannot read a game record from {type(record).__name__}; expected a dict or "
        "a GameRecord"
    )


def _record_field(record: Any, name: str, default: Any = None) -> Any:
    """Read a field from a decoded record, tolerating logs written before a field."""
    data = _as_mapping(record)
    if name in data:
        return data[name]
    return default


def summarize(
    records: Sequence[Any],
    z: float = Z_95,
    *,
    reference_player: int = 0,
) -> dict[str, Any]:
    """Summarise a batch of decoded game records.

    Works on the plain dicts :func:`qcheckers.experiment.runner.read_jsonl` returns,
    not on :class:`~qcheckers.experiment.schema.GameRecord` objects, because Person D's
    analysis must be able to read a log written by an older run.

    Reported metrics (see :data:`SUMMARIZE_KEYS`):

    * ``win_rate_p0`` / ``win_rate_p1`` -- decisive wins per player, with Wilson
      intervals. Draws are in the denominator and are not counted as wins, which is the
      honest treatment: a draw is not evidence of a win.
    * ``draw_rate`` -- fraction of games with ``winner is None``.
    * ``collapse_rate`` -- fraction of games containing at least one collapse.
    * ``mean_length`` -- mean ply count, with a sample standard deviation.
    * ``mean_collapses`` -- mean collapse count per game.
    * ``observe_usage`` / ``spread_usage`` -- mean per game, and the fraction of games
      that used the action at all. The fraction is what the usage plot needs: a mean
      over games that never used Observe hides the difference between conditions.

    Parameters
    ----------
    records:
        Decoded records. An empty sequence is legal and yields zero counts with every
        interval marked undefined.
    z:
        Two-sided normal quantile.
    reference_player:
        Which player the "p0"/"p1" labels are anchored to. Present so a future
        asymmetric condition can be reported without renaming fields.

    Returns
    -------
    dict
        ``{"n_games": int, "condition": str | None, "metrics": {...}, "rates":
        {...}, "termination_counts": {...}}`` where every entry of ``metrics`` is a
        :class:`Rate` and ``rates`` carries the raw counts.

    Raises
    ------
    ValueError
        If ``reference_player`` is not 0 or 1.
    """
    if reference_player not in (0, 1):
        raise ValueError(f"reference_player must be 0 or 1; got {reference_player!r}")

    total = len(records)
    wins = {0: 0, 1: 0}
    draws = 0
    games_with_collapse = 0
    games_with_observe = 0
    games_with_spread = 0
    total_collapses = 0
    total_observe = 0
    total_spread = 0
    lengths: list[int] = []
    terminations: dict[str, int] = {}

    for record in records:
        winner = _record_field(record, "winner")
        if winner is None:
            draws += 1
        elif winner in wins:
            wins[int(winner)] += 1

        collapses = int(_record_field(record, "collapses", 0) or 0)
        total_collapses += collapses
        if collapses > 0:
            games_with_collapse += 1

        observe_moves = int(_record_field(record, "observe_moves", 0) or 0)
        total_observe += observe_moves
        if observe_moves > 0:
            games_with_observe += 1

        spread_moves = int(_record_field(record, "spread_moves", 0) or 0)
        total_spread += spread_moves
        if spread_moves > 0:
            games_with_spread += 1

        lengths.append(int(_record_field(record, "length", 0) or 0))
        termination = str(_record_field(record, "termination", "unknown"))
        terminations[termination] = terminations.get(termination, 0) + 1

    opponent = 1 - reference_player
    metrics: dict[str, Rate] = {
        f"win_rate_p{reference_player}": rate(wins[reference_player], total, z),
        f"win_rate_p{opponent}": rate(wins[opponent], total, z),
        "draw_rate": rate(draws, total, z),
        "collapse_rate": rate(games_with_collapse, total, z),
        "observe_usage": rate(games_with_observe, total, z),
        "spread_usage": rate(games_with_spread, total, z),
    }

    conditions = {_record_field(r, "condition") for r in records}
    condition_label = conditions.pop() if len(conditions) == 1 else None

    return {
        "n_games": total,
        "condition": condition_label,
        "z": z,
        "metrics": metrics,
        "rates": {
            "wins": dict(wins),
            "draws": draws,
            "games_with_collapse": games_with_collapse,
            "mean_length": _mean(lengths),
            "stdev_length": _stdev(lengths),
            "mean_collapses": (total_collapses / total) if total else 0.0,
            "mean_observe_moves": (total_observe / total) if total else 0.0,
            "mean_spread_moves": (total_spread / total) if total else 0.0,
        },
        "termination_counts": dict(sorted(terminations.items())),
    }


def compare_conditions(
    a_records: Sequence[Any],
    b_records: Sequence[Any],
    *,
    metrics: Iterable[str] = ("win_rate_p0", "draw_rate", "collapse_rate"),
    z: float = Z_95,
) -> dict[str, Any]:
    """Run :func:`compare_rates` across several metrics for two conditions.

    Convenience wrapper for :mod:`scripts.run_ablation`. Metric names must exist in the
    summary; an unknown name raises ``KeyError`` so a typo cannot silently drop a
    comparison the report claims to contain.
    """
    summary_a = summarize(a_records, z)
    summary_b = summarize(b_records, z)
    comparisons: dict[str, Any] = {}
    for metric in metrics:
        rate_a: Rate = summary_a["metrics"][metric]
        rate_b: Rate = summary_b["metrics"][metric]
        comparisons[metric] = compare_rates(
            rate_a.successes, rate_a.n, rate_b.successes, rate_b.n, z
        )
    return {
        "a": summary_a,
        "b": summary_b,
        "comparisons": comparisons,
    }


def format_comparison(label_a: str, label_b: str, comparison: Mapping[str, Any]) -> str:
    """One-line human summary of a :func:`compare_rates` result.

    Reports the interval and whether it excludes zero, and never prints the word
    "significant" -- that framing is what the brief warns against.
    """
    rate_a: Rate = comparison["a"]
    rate_b: Rate = comparison["b"]
    if not (rate_a.defined and rate_b.defined):
        return (
            f"{label_a} vs {label_b}: undefined (one condition has no games)"
        )
    marker = "excludes zero" if comparison["excludes_zero"] else "includes zero"
    return (
        f"{label_a} {rate_a.point:.3f} "
        f"[{rate_a.low:.3f}, {rate_a.high:.3f}] vs "
        f"{label_b} {rate_b.point:.3f} "
        f"[{rate_b.low:.3f}, {rate_b.high:.3f}]  "
        f"diff {comparison['difference']:+.3f} "
        f"[{comparison['diff_low']:+.3f}, {comparison['diff_high']:+.3f}] ({marker})"
    )


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (``ddof = 1``). 0.0 for fewer than two values."""
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


__all__ = [
    "SUMMARIZE_KEYS",
    "Z_95",
    "Rate",
    "compare_conditions",
    "compare_paired",
    "compare_rates",
    "format_comparison",
    "normal_cdf",
    "paired_outcomes",
    "rate",
    "summarize",
    "wilson_interval",
    "z_for_confidence",
]