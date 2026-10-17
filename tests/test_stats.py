"""Focused checks for the pure-Python experiment statistics helpers."""

import math
import json

import pytest

from qcheckers.experiment.stats import (
    METRICS,
    compare_conditions,
    compare_paired,
    compare_rates,
    format_comparison,
    paired_outcomes,
    rate,
    summarize,
    wilson_interval,
)


@pytest.mark.parametrize(
    ("successes", "n", "expected"),
    [
        # 4/10: p=.4, center=(.4+3.8416/20)/(1+3.8416/10)=.42775;
        # margin=1.96/1.38416*sqrt(.24/10+3.8416/400)=.25958.
        (4, 10, (0.1682, 0.6873)),
        # 50/100: center=.5; margin=1.96/1.038416*
        # sqrt(.25/100+3.8416/40000)=.09617.
        (50, 100, (0.4038, 0.5962)),
        # 0/10: center=3.8416/20/1.38416=.1388; margin equals center.
        (0, 10, (0.0, 0.2775)),
        # 10/10 mirrors 0/10 around .5.
        (10, 10, (0.7225, 1.0)),
    ],
)
def test_wilson_interval_hand_computed_values(
    successes: int, n: int, expected: tuple[float, float]
) -> None:
    low, high = wilson_interval(successes, n)
    assert (low, high) == pytest.approx(expected, abs=0.001)
    assert 0.0 <= low <= high <= 1.0


def test_wilson_interval_narrows_as_sample_size_increases() -> None:
    small = wilson_interval(4, 10)
    large = wilson_interval(40, 100)
    assert (small[1] - small[0]) > (large[1] - large[0])


def test_wilson_interval_empty_sample() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


@pytest.mark.parametrize(("successes", "n"), [(-1, 4), (5, 4), (1, 0)])
def test_rate_rejects_invalid_counts(successes: int, n: int) -> None:
    with pytest.raises(ValueError):
        rate(successes, n)


def test_compare_rates_identical_and_large_gap() -> None:
    same = compare_rates(40, 100, 40, 100, 1.96)
    assert same["difference"] == 0.0
    assert same["lower"] <= 0.0 <= same["upper"]

    separated = compare_rates(90, 100, 10, 100, 1.96)
    assert separated["lower"] > 0.0
    assert separated["excludes_zero"] is True


def test_compare_rates_swap_arms_flips_interval_sign() -> None:
    forward = compare_rates(70, 100, 30, 100, 1.96)
    reverse = compare_rates(30, 100, 70, 100, 1.96)
    assert reverse["difference"] == pytest.approx(-forward["difference"])
    assert reverse["lower"] == pytest.approx(-forward["upper"])
    assert reverse["upper"] == pytest.approx(-forward["lower"])


def test_compare_paired_identical_twelve_pairs_has_nonzero_interval() -> None:
    result = compare_paired([1] * 12, [1] * 12)
    assert result["lower"] == pytest.approx(-0.24, abs=0.01)
    assert result["upper"] == pytest.approx(0.24, abs=0.01)
    assert result["lower"] < result["upper"]


def test_compare_paired_single_discordance_contains_zero() -> None:
    result = compare_paired([1] * 11 + [0], [1] * 12, 1.96)
    assert result["a_only"] == 0
    assert result["b_only"] == 1
    assert result["lower"] <= 0.0 <= result["upper"]


def test_compare_paired_correlation_narrows_interval() -> None:
    a = [1, 1, 1, 0] * 20
    b = [1, 1, 0, 0] * 20
    paired = compare_paired(a, b, 1.96)
    independent = compare_rates(sum(a), len(a), sum(b), len(b), 1.96)
    assert paired["a_only"] == 20
    assert paired["b_only"] == 0
    assert paired["upper"] - paired["lower"] < (
        independent["upper"] - independent["lower"]
    )


def test_compare_paired_bounds_stay_in_difference_range() -> None:
    result = compare_paired([1, 0, 1, 0], [0, 1, 1, 0], 1.96)
    assert -1.0 <= result["lower"] <= result["upper"] <= 1.0


@pytest.mark.parametrize(
    ("a", "b"),
    [([1], [1, 0]), ([], []), ([2], [0]), ([0.0], [1])],
)
def test_compare_paired_rejects_invalid_inputs(
    a: list[int | float], b: list[int | float]
) -> None:
    with pytest.raises(ValueError):
        compare_paired(a, b)


def test_paired_outcomes_matches_seeded_records_and_rejects_mismatch() -> None:
    arm_a = [
        {"seed": 7, "winner": 0, "collapses": 1},
        {"seed": 3, "winner": None, "collapses": 0},
    ]
    arm_b = [
        {"seed": 3, "winner": 1, "collapses": 1},
        {"seed": 7, "winner": 1, "collapses": 0},
    ]
    assert paired_outcomes(arm_a, arm_b, "win_rate_p0") == ([1, 0], [0, 0])
    assert paired_outcomes(arm_a, arm_b, "draw_rate") == ([0, 1], [0, 0])
    with pytest.raises(ValueError, match="same seeds"):
        paired_outcomes([{"seed": 1, "winner": 0}], [{"seed": 2, "winner": 0}], "draw_rate")


def test_paired_outcomes_rejects_duplicate_seeds() -> None:
    arm = [{"seed": 1, "winner": 0}, {"seed": 1, "winner": 1}]
    with pytest.raises(ValueError, match="duplicate seed"):
        paired_outcomes(arm, arm, "draw_rate")


def _record(
    seed: int,
    winner: int | None,
    length: int = 10,
    collapses: int = 0,
    observe_moves: int = 0,
    spread_moves: int = 0,
) -> dict[str, int | None]:
    return {
        "seed": seed,
        "winner": winner,
        "length": length,
        "collapses": collapses,
        "observe_moves": observe_moves,
        "spread_moves": spread_moves,
    }


def test_summarize_keeps_draws_in_win_denominator() -> None:
    summary = summarize(
        [
            _record(1, 0),
            _record(2, 1),
            _record(3, None),
            _record(4, None),
        ],
        1.96,
    )
    assert summary["metrics"]["win_rate_p0"].p == pytest.approx(0.25)
    assert summary["metrics"]["win_rate_p0"].n == 4
    assert summary["metrics"]["win_rate_p1"].p == pytest.approx(0.25)
    assert summary["metrics"]["draw_rate"].p == pytest.approx(0.5)


def test_summarize_sample_standard_deviation_uses_n_minus_one() -> None:
    summary = summarize([_record(1, 0, length=8), _record(2, 1, length=12)], 1.96)
    assert summary["rates"]["stdev_length"] == pytest.approx(2.0 * math.sqrt(2.0))


def test_summarize_parsed_old_jsonl_record() -> None:
    record = json.loads(
        '{"game_id":"sample-7","seed":7,"winner":1,'
        '"termination":"no_legal_moves","length":8,"collapses":1,'
        '"observe_moves":2,"spread_moves":3,"turns":[]}'
    )

    summary = summarize([record])

    assert summary["n_games"] == 1
    assert summary["metrics"]["win_rate_p1"].p == pytest.approx(1.0)
    assert summary["rates"]["mean_length"] == pytest.approx(8.0)
    assert summary["rates"]["mean_collapses"] == pytest.approx(1.0)
    assert summary["rates"]["mean_observe_moves"] == pytest.approx(2.0)
    assert summary["rates"]["mean_spread_moves"] == pytest.approx(3.0)


def test_summarize_empty_input_and_metrics_registry() -> None:
    summary = summarize([], 1.96)
    assert summary["n_games"] == 0
    assert set(summary["metrics"]) | set(summary["rates"]) == set(METRICS)
    assert all(metric.n == 0 for metric in summary["metrics"].values())
    assert summary["rates"]["stdev_length"] == 0.0


def test_compare_conditions_uses_paired_comparison_for_matching_seeds() -> None:
    arm_a = [_record(1, 0), _record(2, None)]
    arm_b = [_record(2, None), _record(1, 1)]

    result = compare_conditions(arm_a, arm_b, metrics=("win_rate_p0",))
    comparison = result["comparisons"]["win_rate_p0"]

    assert comparison["method"] == "paired"
    assert comparison["difference"] == pytest.approx(0.5)


def test_compare_conditions_uses_unpaired_comparison_for_unmatched_seeds() -> None:
    arm_a = [_record(1, 0), _record(2, 1)]
    arm_b = [_record(3, 0), _record(4, None)]

    result = compare_conditions(arm_a, arm_b, metrics=("draw_rate",))

    assert result["comparisons"]["draw_rate"]["method"] == "unpaired"


def test_compare_conditions_identical_arms_have_zero_difference_in_interval() -> None:
    arm = [_record(1, 0), _record(2, None)]

    comparison = compare_conditions(arm, arm)["comparisons"]["win_rate_p0"]

    assert comparison["difference"] == 0.0
    assert comparison["diff_low"] <= 0.0 <= comparison["diff_high"]


def test_format_comparison_contains_both_labels() -> None:
    comparison = compare_conditions(
        [_record(1, 0)], [_record(2, 1)], metrics=("win_rate_p0",)
    )["comparisons"]["win_rate_p0"]

    formatted = format_comparison("condition A", "condition B", comparison)

    assert "condition A" in formatted
    assert "condition B" in formatted
