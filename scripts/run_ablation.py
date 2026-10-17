"""CLI: compare two agent configurations and print rates with Wilson intervals.

Owner: **Person D -- measurement, statistics and plots**. Person B owns the harness this
drives; P4 copies the numbers into the reproducibility report.

What it does
------------
Runs two matched conditions on the toy engine with identical seeds, board size, ply cap
and agent pair, then prints a side-by-side rate table with Wilson intervals and a
per-metric difference interval (Newcombe-style, built from the two Wilson intervals).

The default comparison is the one the brief cares about most: probability-aware search
versus the uncertainty-ignoring baseline, at matched strength, with and without the
voluntary Observe action.

Controls that matter
--------------------
* **Same seeds on both sides.** Differences then come from the condition, not from luck
  of the draw. ``--seed-offset`` is available but off by default for that reason.
* **Same opponent.** ``--opponent`` fixes the opposing agent so both conditions are
  pitted against an identical baseline.
* **No p-values.** The output says whether the difference interval excludes zero and
  nothing more. Reporting a p-value invites optimising until it passes, which the brief
  explicitly warns against.
* **Sample size warning.** If fewer than ``MIN_GAMES_JUSTIFIED`` games were played, the
  script says so on stdout. A small pilot is a pilot, not a result.

Examples
--------
Default ablation (probability-aware vs baseline, Observe off vs on)::

    python scripts/run_ablation.py -n 20

Compare the Observe agent against a matched random opponent::

    python scripts/run_ablation.py --agent-a observe --agent-b random -n 20
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.engine.toy import DeterministicToyEngine  # noqa: E402
from qcheckers.experiment.config import MIN_GAMES_JUSTIFIED  # noqa: E402
from qcheckers.experiment.runner import log_path, run_condition  # noqa: E402
from qcheckers.experiment.stats import (  # noqa: E402
    Rate,
    compare_conditions,
    format_comparison,
)

#: Agent kinds ``--agent-a`` / ``--agent-b`` accept.
AGENT_KINDS = ("random", "mcts", "observe", "prob")

#: Metrics compared, in print order.
METRICS = ("win_rate_p0", "win_rate_p1", "draw_rate", "collapse_rate")

ENGINE_LABEL = "deterministic-toy"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare two agent configurations with Wilson intervals (toy engine).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--agent-a", default="prob", choices=AGENT_KINDS, help="Agent for player 0, condition A."
    )
    parser.add_argument(
        "--agent-b", default="random", choices=AGENT_KINDS, help="Opponent shared by both conditions."
    )
    parser.add_argument(
        "-n", "--games", type=int, default=10, help="Games per condition."
    )
    parser.add_argument("--base-seed", type=int, default=0, help="First seed.")
    parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="Offset applied to condition B's seeds. Leave at 0 for a matched comparison.",
    )
    parser.add_argument("--board-size", type=int, default=4, help="Board edge length.")
    parser.add_argument("--max-plies", type=int, default=120, help="Per-game ply cap.")
    parser.add_argument(
        "--level",
        type=int,
        default=2,
        help="Engine level used for both conditions.",
    )
    parser.add_argument(
        "--results-dir", default="results", help="Directory for JSONL logs."
    )
    parser.add_argument(
        "--write-logs",
        action="store_true",
        help="Write the JSONL logs. Off by default: this script is for comparison, not batching.",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Only print the comparison block."
    )
    return parser.parse_args(argv)


def run_side(
    label: str,
    agent_kind: str,
    opponent: str,
    seeds: Sequence[int],
    args: argparse.Namespace,
    *,
    allow_observe: bool,
) -> list:
    """Play one condition and return its records.

    Board size, ply cap, opponent and seeds are shared with the other side; only
    ``allow_observe`` and the player-0 agent differ.
    """

    def engine_factory(seed: int) -> DeterministicToyEngine:
        return DeterministicToyEngine(
            seed=seed,
            level=args.level,
            allow_observe=allow_observe,
            board_size=args.board_size,
            max_plies=args.max_plies,
        )

    output = log_path(label, args.results_dir) if args.write_logs else None
    return run_condition(
        engine_factory,
        (agent_kind, opponent),
        seeds,
        condition=label,
        output=output,
        overwrite=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)
    if args.games < 1:
        print("error: --games must be at least 1", file=sys.stderr)
        return 2
    if args.level not in (0, 1, 2):
        print("error: --level must be 0, 1 or 2", file=sys.stderr)
        return 2
    if args.board_size < 4:
        print("error: --board-size must be at least 4", file=sys.stderr)
        return 2

    seeds_a = tuple(args.base_seed + offset for offset in range(args.games))
    seeds_b = tuple(
        args.base_seed + args.seed_offset + offset for offset in range(args.games)
    )

    label_a = f"ablation-{args.agent_a}-vs-{args.agent_b}-obs"
    label_b = f"ablation-{args.agent_a}-vs-{args.agent_b}-noobs"

    if not args.quiet:
        print(f"engine     : {ENGINE_LABEL} (upstream Cheqqers NOT integrated)")
        print(f"condition A: {label_a}   (observe=True)")
        print(f"condition B: {label_b}   (observe=False)")
        print(f"player 0   : {args.agent_a} in both conditions")
        print(f"opponent   : {args.agent_b} in both conditions")
        print(f"level      : {args.level}")
        print(f"games      : {args.games} per condition")
        if args.seed_offset == 0:
            print(f"seeds      : matched ({seeds_a[0]}..{seeds_a[-1]}) on both sides")
        else:
            print(
                f"seeds      : UNMATCHED (A {seeds_a[0]}..{seeds_a[-1]}, "
                f"B {seeds_b[0]}..{seeds_b[-1]}) -- differences may be seed luck"
            )
        print("")

    started = time.perf_counter()
    records_a = run_side(
        label_a, args.agent_a, args.agent_b, seeds_a, args, allow_observe=True
    )
    records_b = run_side(
        label_b, args.agent_a, args.agent_b, seeds_b, args, allow_observe=False
    )
    elapsed = time.perf_counter() - started

    result = compare_conditions(records_a, records_b, metrics=METRICS)

    print_rates(label_a, label_b, result)
    print_differences(label_a, label_b, result)

    if not args.quiet:
        total_games = args.games * 2
        print(
            f"\nelapsed    : {elapsed:.2f}s for {total_games} games "
            f"({total_games / elapsed:.1f} games/second)"
        )
    print_power_note(args.games)
    return 0


def print_rates(label_a: str, label_b: str, result: dict) -> None:
    """Print the per-condition rate table."""
    summary_a = result["a"]
    summary_b = result["b"]
    # Long condition labels would wrap and misalign the columns, so shorten them for
    # the table and keep the full labels for the difference block below.
    short_a = _short_label(label_a)
    short_b = _short_label(label_b)
    print(f"{'metric':<20} {'A: ' + short_a:>22}   {'B: ' + short_b:>22}")
    print("-" * 72)
    for metric in METRICS:
        rate_a: Rate = summary_a["metrics"][metric]
        rate_b: Rate = summary_b["metrics"][metric]
        print(f"{metric:<16} {_cell(rate_a):>24}   {_cell(rate_b):>24}")
    print(f"{'games':<16} {summary_a['n_games']:>24}   {summary_b['n_games']:>24}")
    print(f"{'mean length':<16} {_num(summary_a['rates']['mean_length']):>24}   "
          f"{_num(summary_b['rates']['mean_length']):>24}")
    print(
        f"{'collapses/game':<16} {_num(summary_a['rates']['mean_collapses']):>24}   "
        f"{_num(summary_b['rates']['mean_collapses']):>24}"
    )
    print(
        f"{'observe moves/game':<16} "
        f"{_num(summary_a['rates']['mean_observe_moves']):>24}   "
        f"{_num(summary_b['rates']['mean_observe_moves']):>24}"
    )
    print()


def print_differences(label_a: str, label_b: str, result: dict) -> None:
    """Print the per-metric difference intervals."""
    print("difference in rates (A - B), Newcombe interval from the two Wilson intervals:")
    for metric in METRICS:
        comparison = result["comparisons"][metric]
        print(f"  {metric:<16} {format_comparison(label_a, label_b, comparison)}")
    print()


def print_power_note(games: int) -> None:
    """State the sample-size caveat plainly. A pilot is not a finding."""
    if games < MIN_GAMES_JUSTIFIED:
        print(
            f"NOTE: {games} games per condition is below the brief's "
            f"{MIN_GAMES_JUSTIFIED}-per-condition target. Treat this as a pilot and "
            "do not claim an effect."
        )
    else:
        print(
            f"NOTE: {games} games per condition meets the brief's "
            f"{MIN_GAMES_JUSTIFIED}-per-condition target."
        )


def _short_label(label: str) -> str:
    """Trim a condition label for table columns, keeping the informative part.

    ``ablation-prob-vs-random-obs`` -> ``prob-vs-random-obs``. Falls back to the tail
    of the label if the ``ablation-`` prefix is absent, so a custom label still reads
    sensibly.
    """
    trimmed = label[len("ablation-") :] if label.startswith("ablation-") else label
    return trimmed if len(trimmed) <= 20 else "..." + trimmed[-17:]


def _cell(rate: Rate) -> str:
    if not rate.defined:
        return "n=0"
    return f"{rate.point:.3f} [{rate.low:.3f},{rate.high:.3f}]"


def _num(value: float) -> str:
    return f"{value:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
