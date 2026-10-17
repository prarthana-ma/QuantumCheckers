"""CLI: run random-agent and MCTS baseline experiments.

Provides a documented command-line workflow for baseline experiments. Uses the same
underlying runner and schema as the rest of the project.

Examples
--------
Smoke test (2 games, random vs random)::

    python scripts/run_baseline.py --smoke

Small baseline batch (10 games, random vs MCTS)::

    python scripts/run_baseline.py -n 10 --agent-a random --agent-b mcts

With config file::

    python scripts/run_baseline.py --config configs/smoke.json

Export replays::

    python scripts/run_baseline.py -n 10 --agent-a random --agent-b mcts --replays
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.experiment.config import ExperimentConfig, load_config, save_config  # noqa: E402
from qcheckers.experiment.runner import log_path, run_condition  # noqa: E402
from qcheckers.experiment.seeds import SeedManager  # noqa: E402
from tests.support.quantum_toy import QuantumToyEngine  # noqa: E402

logger = logging.getLogger(__name__)

#: Agent kinds this CLI accepts.
AGENT_KINDS = ("random", "mcts")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run QuantumCheckers baseline experiments (random and MCTS).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a JSON or TOML config file.",
    )
    parser.add_argument(
        "--agent-a",
        choices=AGENT_KINDS,
        default=None,
        help="Agent kind for player 0.",
    )
    parser.add_argument(
        "--agent-b",
        choices=AGENT_KINDS,
        default=None,
        help="Agent kind for player 1.",
    )
    parser.add_argument(
        "-n",
        "--games",
        type=int,
        default=None,
        help="Number of games.",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=None,
        help="Base seed for the experiment.",
    )
    parser.add_argument(
        "--board-size",
        type=int,
        default=None,
        help="Board edge length (>= 4).",
    )
    parser.add_argument(
        "--max-plies",
        type=int,
        default=None,
        help="Per-game ply cap.",
    )
    parser.add_argument(
        "--level",
        type=int,
        choices=(0, 1, 2),
        default=None,
        help="Engine level.",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        help="Directory for JSONL logs and replays.",
    )
    parser.add_argument(
        "--replays",
        action="store_true",
        help="Export replay JSON per game.",
    )
    parser.add_argument(
        "--no-alternate",
        action="store_true",
        help="Do not alternate seats.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a 2-game smoke test with defaults.",
    )
    parser.add_argument(
        "--output-config",
        type=str,
        default=None,
        help="Write the resolved config to this path and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        help="Experiment identifier.",
    )
    return parser.parse_args(argv)


def _make_engine_factory(config: ExperimentConfig):
    """Create an engine factory from config."""
    def factory(seed: int) -> QuantumToyEngine:
        return QuantumToyEngine(
            seed=seed,
            level=config.level,
            allow_observe=config.allow_observe,
            board_size=config.board_size,
            max_plies=config.max_plies,
        )
    return factory


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Load or build config
    if args.config:
        try:
            config = load_config(args.config)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    elif args.smoke:
        config = ExperimentConfig(
            experiment_id="smoke",
            agents=("random", "random"),
            n_games=2,
            base_seed=0,
            board_size=4,
            max_plies=60,
            level=2,
        )
    else:
        config = ExperimentConfig()

    # Apply CLI overrides
    if args.agent_a is not None:
        agents = [config.agents[0], config.agents[1]]
        agents[0] = args.agent_a
        config.agents = tuple(agents)
    if args.agent_b is not None:
        agents = [config.agents[0], config.agents[1]]
        agents[1] = args.agent_b
        config.agents = tuple(agents)
    if args.games is not None:
        config.n_games = args.games
    if args.base_seed is not None:
        config.base_seed = args.base_seed
    if args.board_size is not None:
        config.board_size = args.board_size
    if args.max_plies is not None:
        config.max_plies = args.max_plies
    if args.level is not None:
        config.level = args.level
    if args.results_dir is not None:
        config.output_dir = args.results_dir
    if args.replays:
        config.export_replays = True
    if args.no_alternate:
        config.alternate_seats = False
    if args.experiment_id is not None:
        config.experiment_id = args.experiment_id

    if config.n_games < 1:
        print("error: n_games must be >= 1", file=sys.stderr)
        return 2
    if config.board_size < 4:
        print("error: board_size must be >= 4", file=sys.stderr)
        return 2
    if config.level not in (0, 1, 2):
        print("error: level must be 0, 1 or 2", file=sys.stderr)
        return 2

    if args.output_config:
        save_config(config, args.output_config)
        print(f"config written to {args.output_config}")
        return 0

    seed_mgr = SeedManager(config.base_seed)
    seeds = seed_mgr.game_seeds(config.n_games)
    engine_factory = _make_engine_factory(config)
    output = log_path(config.experiment_id, config.output_dir)

    print(f"experiment : {config.experiment_id}")
    print(f"agents     : {config.agents[0]} vs {config.agents[1]}")
    print(f"games      : {config.n_games}")
    print(f"seeds      : {seeds[0]}..{seeds[-1]} (root {config.base_seed})")
    print(f"board      : {config.board_size}x{config.board_size}, level {config.level}")
    print(f"output     : {output}")
    print(f"replays    : {'yes' if config.export_replays else 'no'}")
    print()

    started = time.perf_counter()
    try:
        records = run_condition(
            engine_factory,
            config.agents,
            seeds,
            condition=config.experiment_id,
            output=output,
            overwrite=True,
            alternate=config.alternate_seats,
            seed_manager=seed_mgr,
            config=config,
            export_replays=config.export_replays,
            replay_dir=str(Path(config.output_dir) / "replays"),
        )
    except Exception as exc:
        print(f"error: experiment failed: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    # Summary
    from collections import Counter
    outcome_counts = Counter(r["outcome"] for r in records)
    mean_plies = sum(r["n_plies"] for r in records) / max(len(records), 1)
    mean_dur = sum(r["duration_seconds"] for r in records) / max(len(records), 1)

    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"  Games completed : {len(records)}")
    for outcome, count in sorted(outcome_counts.items()):
        print(f"    {outcome:16s}: {count}")
    print(f"  Mean plies      : {mean_plies:.1f}")
    print(f"  Mean duration   : {mean_dur:.3f}s")
    print(f"  Total elapsed   : {elapsed:.2f}s")
    if records:
        print(f"  Throughput      : {len(records)/max(elapsed, 1e-9):.1f} games/s")
    print(f"  Output          : {output}")

    # Exit code: nonzero if any errors or timeouts
    has_errors = any(
        r["outcome"] in ("error", "timeout", "invalid_action") for r in records
    )
    if has_errors:
        print("\nWARNING: some games ended in error/timeout/invalid_action.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
