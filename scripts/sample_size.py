"""Print Wilson precision and modelled minimum detectable effects by sample size."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qcheckers.experiment.stats import compare_paired, compare_rates, wilson_interval


SAMPLE_SIZES = (30, 50, 100, 170, 300, 500, 1000)
CORRELATIONS = (0.3, 0.6)
Z_ALPHA = 1.96
Z_POWER_80 = 0.8416212335729143


def _wilson_half_width(n: int, probability: float) -> float:
    successes = round(n * probability)
    low, high = wilson_interval(successes, n)
    return (high - low) / 2.0


def _excludes_zero(interval: dict[str, float | bool]) -> bool:
    return bool(interval["lower"] > 0.0 or interval["upper"] < 0.0)


def _independent_threshold(n: int) -> float:
    baseline_successes = round(n * 0.5)
    candidates = sorted(range(n + 1), key=lambda k: (abs(k / n - 0.5), k))
    for successes in candidates:
        difference = abs(successes / n - 0.5)
        if difference == 0.0:
            continue
        interval = compare_rates(successes, n, baseline_successes, n)
        if bool(interval["excludes_zero"]):
            return difference
    return math.nan


def _paired_data(
    n: int, b_successes: int, correlation: float
) -> tuple[list[int], list[int]]:
    """Build a deterministic 2x2 paired table near the requested phi correlation."""
    a_successes = round(n * 0.5)
    p_a = a_successes / n
    p_b = b_successes / n
    expected_both = n * (
        p_a * p_b
        + correlation
        * math.sqrt(p_a * (1.0 - p_a) * p_b * (1.0 - p_b))
    )
    both = round(expected_both)
    both = max(0, min(a_successes, b_successes, both))
    a_only = a_successes - both
    b_only = b_successes - both
    neither = n - both - a_only - b_only
    a = [1] * both + [1] * a_only + [0] * b_only + [0] * neither
    b = [1] * both + [0] * a_only + [1] * b_only + [0] * neither
    return a, b


def _paired_threshold(n: int, correlation: float) -> float:
    candidates = sorted(range(n + 1), key=lambda k: (abs(k / n - 0.5), k))
    for successes in candidates:
        difference = abs(successes / n - 0.5)
        if difference == 0.0:
            continue
        a, b = _paired_data(n, successes, correlation)
        interval = compare_paired(a, b)
        if _excludes_zero(interval):
            return difference
    return math.nan


def _independent_power_difference(n: int) -> float:
    # Normal approximation: delta = (z_(1-alpha/2) + z_power) *
    # sqrt((2*p*(1-p))/n), evaluated at the null p=0.5.
    return (Z_ALPHA + Z_POWER_80) * math.sqrt(0.5 / n)


def _paired_power_difference(n: int, correlation: float) -> float:
    # For paired binary outcomes at p=0.5, Var(A-B) = 0.5*(1-rho);
    # use delta = (z_(1-alpha/2) + z_power) * sqrt(Var(A-B)/n).
    return (Z_ALPHA + Z_POWER_80) * math.sqrt(0.5 * (1.0 - correlation) / n)


def _format_percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{100.0 * value:.1f}%"


def _print_table(games: Iterable[int]) -> None:
    print(
        "Modelled assumptions, not measured: baseline p=0.5; normal-approximation "
        "80% power, two-sided alpha=0.05; paired phi correlations=0.3 and 0.6."
    )
    print(
        "n/arm | Wilson half-width at p=.5 / .3 / .1 | "
        "indep. min observed | indep. 80% power | "
        "paired min obs. rho=.3 / .6 | paired 80% power rho=.3 / .6"
    )
    for n in games:
        half_widths = " / ".join(
            _format_percent(_wilson_half_width(n, probability))
            for probability in (0.5, 0.3, 0.1)
        )
        independent_threshold = _format_percent(_independent_threshold(n))
        independent_power = _format_percent(_independent_power_difference(n))
        paired_thresholds = " / ".join(
            _format_percent(_paired_threshold(n, correlation))
            for correlation in CORRELATIONS
        )
        paired_power = " / ".join(
            _format_percent(_paired_power_difference(n, correlation))
            for correlation in CORRELATIONS
        )
        print(
            f"{n:5d} | {half_widths:36s} | {independent_threshold:18s} | "
            f"{independent_power:17s} | {paired_thresholds:24s} | {paired_power}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--games",
        type=int,
        help="print only the row for this per-arm sample size",
    )
    args = parser.parse_args()
    if args.games is None:
        _print_table(SAMPLE_SIZES)
    elif args.games <= 0:
        parser.error("--games must be a positive integer")
    else:
        _print_table((args.games,))


if __name__ == "__main__":
    main()
