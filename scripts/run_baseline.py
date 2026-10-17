"""CLI: run a seeded baseline batch and write JSONL logs.

Owner: **Person B -- baseline agents and harness**. Person D consumes the output;
P4 uses it for the viewer and the reproducibility report.

What it does
------------
Plays the requested number of games for one condition, writes
``results/<condition>.jsonl``, prints a short summary table with Wilson intervals, and
optionally writes a replay payload for the viewer.

What it deliberately does not do
--------------------------------
* No agent tuning, no threshold search.
* No condition chosen for you: ``--condition`` picks from the frozen list in
  :data:`qcheckers.experiment.config.CONDITIONS`, so a run cannot quietly diverge from
  the ablation definition.
* No significance claim in the output. It prints rates and intervals only.

Examples
--------
Smoke run on the toy engine::

    python scripts/run_baseline.py --condition classical-mcts-vs-random -n 20

Pilot with the Observe condition, appending to an existing log::

    python scripts/run_baseline.py --condition quantum-observe-vs-random -n 20 --append

Full toy-engine batch (still small; see ``MIN_GAMES_JUSTIFIED`` in config.py)::

    python scripts/run_baseline.py --condition quantum-observe-vs-random -n 170
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as ``python scripts/run_baseline.py`` from the repo root without
# installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.engine.toy import DeterministicToyEngine  # noqa: E402
from qcheckers.experiment.config import (  # noqa: E402
    CONDITIONS,
    MIN_GAMES_JUSTIFIED,
    ConditionConfig,
    condition_by_label,
)
from qcheckers.experiment.runner import (  # noqa: E402
    log_path,
    read_jsonl,
    run_condition,
)
from qcheckers.experiment.stats import summarize, wilson_interval  # noqa: E402
from qcheckers.viz.replay import build_replay, replay_to_json  # noqa: E402

#: Engine used until the upstream Cheqqers engine is integrated (Gate 2 pending).
ENGINE_LABEL = "deterministic-toy"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run seeded baseline games and write a JSONL log.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--condition",
        default="classical-mcts-vs-random",
        choices=[c.label for c in CONDITIONS],
        help="Experimental condition to run.",
    )
    parser.add_argument(
        "-n",
        "--games",
        type=int,
        default=10,
        help="Number of games to play.",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=0,
        help="First seed; game i uses base_seed + i.",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=None,
        help="Override the condition's engine level (0, 1 or 2).",
    )
    parser.add_argument(
        "--allow-observe",
        dest="allow_observe",
        action="store_true",
        default=None,
        help="Force the voluntary-measurement condition on.",
    )
    parser.add_argument(
        "--no-observe",
        dest="allow_observe",
        action="store_false",
        help="Force the voluntary-measurement condition off.",
    )
    parser.add_argument("--board-size", type=int, default=4, help="Board edge length.")
    parser.add_argument(
        "--max-plies", type=int, default=120, help="Per-game ply cap."
    )
    parser.add_argument(
        "--results-dir", default="results", help="Directory for JSONL logs."
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the log instead of replacing it.",
    )
    parser.add_argument(
        "--replay",
        default=None,
        help="Also write a replay payload for the first game to this JSON path.",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Only print the final summary line."
    )
    return parser.parse_args(argv)


def resolve_condition(args: argparse.Namespace) -> ConditionConfig:
    """Apply any CLI overrides to the named condition."""
    base = condition_by_label(args.condition)
    level = base.level if args.level is None else args.level
    allow = (
        base.allow_observe if args.allow_observe is None else bool(args.allow_observe)
    )
    label = base.label
    if level != base.level or allow != base.allow_observe:
        # Overrides change the condition, so the label must change too -- otherwise a
        # later analysis cannot tell the two runs apart.
        label = f"{base.label}-L{level}{'-obs' if allow else '-noobs'}"
    return ConditionConfig(
        label=label,
        level=level,
        allow_observe=allow,
        agent_kinds=base.agent_kinds,
        description=base.description,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)
    if args.games < 1:
        print("error: --games must be at least 1", file=sys.stderr)
        return 2
    if args.board_size < 4:
        print("error: --board-size must be at least 4", file=sys.stderr)
        return 2

    condition = resolve_condition(args)
    seeds = tuple(args.base_seed + offset for offset in range(args.games))
    output = log_path(condition.label, args.results_dir)

    def engine_factory(seed: int) -> DeterministicToyEngine:
        return DeterministicToyEngine(
            seed=seed,
            level=condition.level,
            allow_observe=condition.allow_observe,
            board_size=args.board_size,
            max_plies=args.max_plies,
        )

    if not args.quiet:
        print(f"engine        : {ENGINE_LABEL} (upstream Cheqqers NOT integrated)")
        print(f"condition     : {condition.label}")
        print(f"  description : {condition.description}")
        print(f"  level       : {condition.level}")
        print(f"  observe     : {condition.allow_observe}")
        print(f"  agents      : p0={condition.agent_kinds[0]}  p1={condition.agent_kinds[1]}")
        print(f"games         : {args.games} (brief target >= {MIN_GAMES_JUSTIFIED} per condition)")
        print(f"seeds         : {seeds[0]}..{seeds[-1]}")
        print(f"log           : {output}")
        print("")

    started = time.perf_counter()
    records = run_condition(
        engine_factory,
        condition.agent_kinds,
        seeds,
        condition=condition.label,
        output=output,
        overwrite=not args.append,
    )
    elapsed = time.perf_counter() - started

    summary = summarize(records)

    if not args.quiet:
        print(f"games/second  : {args.games / elapsed:.2f}  (Gate 4 games-per-hour measurement)")
        print("")

    print_summary(condition, summary)

    if args.replay:
        payload = build_replay(records[0].to_json())
        replay_path = Path(args.replay)
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        replay_path.write_text(replay_to_json(payload, indent=2), encoding="utf-8")
        print(f"\nreplay payload: {replay_path} (game {records[0].game_id})")

    # Sanity read-back: the log on disk must parse and match what we just played.
    written = read_jsonl(output)
    if len(written) < len(records):
        print(
            f"warning: log holds {len(written)} records but {len(records)} were played",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nlog verified : {len(written)} records re-read from {output} "
        f"({written[0]['game_id']} .. {written[-1]['game_id']})"
    )
    return 0


def print_summary(condition: ConditionConfig, summary: dict) -> None:
    """Print a rates table with Wilson intervals for one condition."""
    total = summary["n_games"]
    metrics = summary["metrics"]
    win_p0 = metrics["win_rate_p0"]
    win_p1 = metrics["win_rate_p1"]
    draw = metrics["draw_rate"]
    collapse = metrics["collapse_rate"]
    low, high = wilson_interval(win_p0.successes, win_p0.n)

    print(f"condition     : {condition.label}  (n = {total})")
    print(f"win rate p0   : {win_p0.point:.3f}  95% CI [{low:.3f}, {high:.3f}]")
    print(
        f"win rate p1   : {win_p1.point:.3f}  95% CI "
        f"[{win_p1.low:.3f}, {win_p1.high:.3f}]"
    )
    print(
        f"draw rate     : {draw.point:.3f}  95% CI "
        f"[{draw.low:.3f}, {draw.high:.3f}]"
    )
    print(
        f"collapse rate : {collapse.point:.3f}  95% CI "
        f"[{collapse.low:.3f}, {collapse.high:.3f}]"
    )
    print(
        f"game length   : mean {summary['rates']['mean_length']:.2f}  "
        f"sd {summary['rates']['stdev_length']:.2f}  plies"
    )
    print(
        f"move usage    : observe {summary['rates']['mean_observe_moves']:.2f}/game  "
        f"spread {summary['rates']['mean_spread_moves']:.2f}/game"
    )
    print(
        f"terminations  : "
        + ", ".join(
            f"{key}={value}" for key, value in summary["termination_counts"].items()
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
