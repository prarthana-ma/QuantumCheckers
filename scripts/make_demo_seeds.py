"""CLI: write the three demo replay payloads the report and the demo point at.

Owner: **Person E -- replay viewer and reproducibility package**.

Three seeds, one per thing the project is trying to show, each a replay payload the
static viewer (`viewer/index.html`) can step through with no server and no build step:

``demo-classical.json``
    A level-0 game: ordinary checkers on the toy engine, no uncertainty at all. This is
    the classical arm, and it exists so the quantum files have something to be compared
    against.
``demo-observe.json``
    A level-2 game in which the voluntary measurement fires (the research condition).
    Taken from the logged batch by seed, so it is a *recorded* game, not a re-run.
``demo-decoherence.json``
    A level-4 game in which a split piece runs out of coherence and collapses on its own.
    Played here as a **single game**: the batch runner refuses level 3 and level 4, which
    is the whole point of the boundary, and a demo is not a batch. The level-4 file is the
    team's own outreach mechanic and is unevaluated -- the viewer and the report both say
    so, and the payload carries the flag for it.

The two logged demos are looked up by seed in `results/*.jsonl`, so this script never
re-runs an experiment: if the log is missing it tells you which command to run first.

Usage::

    python scripts/make_demo_seeds.py
    python scripts/make_demo_seeds.py --results-dir results
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.agents.random_agent import RandomAgent  # noqa: E402
from qcheckers.engine.toy import DeterministicToyEngine  # noqa: E402
from qcheckers.experiment.runner import play, read_jsonl  # noqa: E402
from qcheckers.viz.replay import build_replay, replay_to_json  # noqa: E402

#: Level-4 games are searched here for one that ends with a piece expiring. Single games
#: only: `run_condition` refuses a level-4 batch by design.
DECOHERENCE_SEEDS = range(0, 60)
DECOHERENCE_MAX_PLIES = 80


def _write(payload: dict[str, Any], path: Path) -> None:
    path.write_text(replay_to_json(payload, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.name}  ({payload['header']['length']} plies, "
          f"{payload['header']['condition']}, level {payload['header']['level']})")


def _logged_record(
    results_dir: Path, condition: str, *, want_collapse: bool
) -> dict[str, Any]:
    """The first record in a logged batch that shows a collapse, else the first record."""
    path = results_dir / f"{condition}.jsonl"
    if not path.exists():
        raise SystemExit(
            f"missing {path}; run:\n"
            f"    python scripts/run_baseline.py --condition {condition} -n 170"
        )
    records = read_jsonl(path)
    if not records:
        raise SystemExit(f"{path} is empty; re-run the batch for that condition")
    if want_collapse:
        for record in records:
            if int(record.get("collapses") or 0) > 0:
                return record
        raise SystemExit(
            f"{path} contains no collapse at all, so it cannot demo a measurement"
        )
    return records[0]


def _decoherence_record() -> dict[str, Any]:
    """Play single level-4 games until one contains an automatic expiry."""
    for seed in DECOHERENCE_SEEDS:
        engine = DeterministicToyEngine(
            seed=seed,
            level=4,
            allow_observe=True,
            decoherence=True,
            max_plies=DECOHERENCE_MAX_PLIES,
        )
        agents = {0: RandomAgent(seed), 1: RandomAgent(seed + 1000)}
        record = play(engine, agents, seed, condition="demo-decoherence")
        causes = [
            event.get("cause") for turn in record.turns for event in turn.events
        ]
        if "decoherence" in causes:
            return record.to_json()
    raise SystemExit(
        f"no seed in {DECOHERENCE_SEEDS} produced a decoherence expiry within "
        f"{DECOHERENCE_MAX_PLIES} plies"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Write the three demo replay payloads.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--results-dir", default="results", help="Directory holding the JSONL logs."
    )
    parser.add_argument(
        "--out-dir", default=None, help="Where to write the payloads (default: results)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Write all three demo files; return the process exit status."""
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    out_dir = Path(args.out_dir) if args.out_dir else results_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Demo replay payloads")

    classical = _logged_record(results_dir, "classical-random-vs-random", want_collapse=False)
    _write(build_replay(classical), out_dir / "demo-classical.json")

    observe = _logged_record(results_dir, "quantum-observe-vs-random", want_collapse=True)
    _write(build_replay(observe), out_dir / "demo-observe.json")

    decoherence = _decoherence_record()
    _write(build_replay(decoherence), out_dir / "demo-decoherence.json")

    print("")
    print("These are the files the demo loads. Level 4 is game-only and unevaluated;")
    print("the two logged demos are records from the batches, not re-runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
