"""Print Wilson-width and approximate detectable-effect calculations.

Run from the repository root with ``python scripts/sample_size.py``. The script is
read-only and uses only the standard library plus ``qcheckers.experiment.stats``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.experiment.stats import compare_rates, wilson_interval  # noqa: E402

Z_95 = 1.959963984540054
SAMPLE_SIZES = (30, 50, 100, 170, 300, 500, 1000)
CORRELATIONS = (0.3, 0.6)


def normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def independent_power(n: int, difference: float) -> float:
    """Two-sided normal power with pooled null and unpooled alternative variance."""
    p0, p1 = 0.5, 0.5 + difference
    pooled = (p0 + p1) / 2.0
    # SE_null^2=2*p_bar*(1-p_bar)/n, SE_alt^2=(p0*(1-p0)+p1*(1-p1))/n;
    # power = Phi((-c-delta)/SE_alt) + 1-Phi((c-delta)/SE_alt), c=1.96*SE_null.
    null_se = math.sqrt(2.0 * pooled * (1.0 - pooled) / n)
    alternative_se = math.sqrt(
        (p0 * (1.0 - p0) + p1 * (1.0 - p1)) / n
    )
    cutoff = Z_95 * null_se
    return normal_cdf((-cutoff - difference) / alternative_se) + 1.0 - normal_cdf(
        (cutoff - difference) / alternative_se
    )


def paired_variance_per_pair(difference: float, rho: float) -> float:
    """Variance of paired binary difference under fixed within-pair correlation."""
    p0, p1 = 0.5, 0.5 + difference
    v0, v1 = p0 * (1.0 - p0), p1 * (1.0 - p1)
    covariance = rho * math.sqrt(v0 * v1)
    return v0 + v1 - 2.0 * covariance


def paired_power(n: int, difference: float, rho: float) -> float:
    """Normal-approximation two-sided paired power at alpha=.05."""
    null_se = math.sqrt(0.5 * (1.0 - rho) / n)
    alternative_se = math.sqrt(paired_variance_per_pair(difference, rho) / n)
    cutoff = Z_95 * null_se
    return normal_cdf((-cutoff - difference) / alternative_se) + 1.0 - normal_cdf(
        (cutoff - difference) / alternative_se
    )


def solve_detectable_difference(power_function, n: int, *args: float) -> float:
    """Find the smallest positive difference with the requested approximate power."""
    low, high = 0.0, 0.5
    for _ in range(100):
        middle = (low + high) / 2.0
        if power_function(n, middle, *args) >= 0.80:
            high = middle
        else:
            low = middle
    return high


def smallest_independent_ci_difference(n: int) -> float:
    baseline_successes = round(0.5 * n)
    baseline = baseline_successes / n
    for successes in range(baseline_successes + 1, n + 1):
        if compare_rates(successes, n, baseline_successes, n)["excludes_zero"]:
            return successes / n - baseline
    return math.nan


def smallest_paired_ci_difference(n: int, rho: float) -> float:
    baseline = 0.5
    for successes in range(round(baseline * n) + 1, n + 1):
        difference = successes / n - baseline
        variance = paired_variance_per_pair(difference, rho)
        if difference > Z_95 * math.sqrt(variance / n):
            return difference
    return math.nan


def main() -> None:
    print("Wilson 95% half-widths use the nearest integer success count to each target p.")
    print(
        "Independent CI column: smallest upward observed difference from the rounded "
        "0.5 baseline whose repository compare_rates interval excludes zero."
    )
    print(
        "Power columns use two-sided alpha=.05 normal approximations and solve for 80% "
        "power. Independent alternative p values are 0.5 and 0.5+delta."
    )
    print(
        "Paired scenarios assume binary outcomes with within-pair correlation rho "
        "fixed at 0.3 or 0.6; the paired null variance is 0.5*(1-rho)/n."
    )
    print(
        "Power formula: Phi((-c-delta)/SE_alt) + 1-Phi((c-delta)/SE_alt), "
        "where c=1.96*SE_null and Phi is the standard normal CDF."
    )
    print(
        "n | Wilson hw p=.5 | p=.3 | p=.1 | independent CI min | independent 80% "
        "| paired rho=.3 CI min | paired rho=.3 80% | paired rho=.6 CI min "
        "| paired rho=.6 80%"
    )

    rows: list[tuple[int, float, float]] = []
    for n in SAMPLE_SIZES:
        half_widths = []
        for p in (0.5, 0.3, 0.1):
            successes = round(p * n)
            low, high = wilson_interval(successes, n)
            half_widths.append((high - low) / 2.0)

        independent_min = smallest_independent_ci_difference(n)
        independent_detectable = solve_detectable_difference(independent_power, n)
        paired_results = [
            (
                smallest_paired_ci_difference(n, rho),
                solve_detectable_difference(paired_power, n, rho),
            )
            for rho in CORRELATIONS
        ]
        rows.append((n, half_widths[0], independent_detectable))

        values = (
            n,
            *(f"{value * 100:.1f}%" for value in half_widths),
            f"{independent_min * 100:.1f}%",
            f"{independent_detectable * 100:.1f}%",
            f"{paired_results[0][0] * 100:.1f}%",
            f"{paired_results[0][1] * 100:.1f}%",
            f"{paired_results[1][0] * 100:.1f}%",
            f"{paired_results[1][1] * 100:.1f}%",
        )
        print(" | ".join(map(str, values)))

    n170 = next(row for row in rows if row[0] == 170)
    if not 0.073 <= n170[1] <= 0.075 or not 0.14 <= n170[2] <= 0.16:
        raise AssertionError(
            f"n=170 sanity check failed: Wilson half-width={n170[1]:.4f}, "
            f"independent detectable difference={n170[2]:.4f}"
        )


if __name__ == "__main__":
    main()
