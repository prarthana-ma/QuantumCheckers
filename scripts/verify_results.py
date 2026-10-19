"""CLI: verify that logged results regenerate from their own seeds.

Owner: **P5 -- rules, engine, harness and batches**; consumed by **Person D**
(statistics) and **Person E** (reproducibility package).

Why this exists
---------------
The brief's pass threshold includes "logs and plots regenerable from seeds". That is
easy to claim and cheap to check badly, so this script checks it the only way that means
anything: for every logged game it rebuilds the engine and the two agents from the
*log line itself* -- seed, level, `allow_observe`, board size, agent labels -- replays
the game, and requires the regenerated line to be **byte-identical** to the one on disk.

It also:

* restates each batch's rates with sample sizes and Wilson intervals, so the numbers in
  the report can be traced back to a file and an ``n``;
* fails on a record whose level the batch runner is forbidden to write (levels 3 and 4
  are game-only), which is the boundary enforced in :mod:`qcheckers.experiment.runner`;
* separates *game-client* records (the server's own log, conditions like ``L1-ai-easy``)
  from experiment records. A game-client record contains a human being's moves, so it is
  **not** seed-regenerable by design -- this script counts those records and checks their
  level instead of pretending to replay them.

What it deliberately does not do
--------------------------------
* No re-running of batches: it never writes a log, and by default only reads.
* No significance language, no p-values -- intervals only (same rule as every other
  output in this project).
* No silent skipping: an unrecognised agent label, a malformed line or a missing field is
  a failure with the file, line number and reason, not a warning.

Usage
-----
::

    python scripts/verify_results.py
    python scripts/verify_results.py --results-dir results --json results/verification.json
    python scripts/verify_results.py --stats-only     # skip the replay, rates only

Exit status: ``0`` everything checked, ``1`` a check failed, ``2`` nothing to check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Allow running as ``python scripts/verify_results.py`` from the repo root without
# installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.engine.toy import DeterministicToyEngine  # noqa: E402
from qcheckers.experiment.runner import (  # noqa: E402
    BATCHABLE_LEVELS,
    kind_for_label,
    make_agent,
    play,
)
from qcheckers.experiment.schema import record_from_json  # noqa: E402
from qcheckers.experiment.stats import summarize  # noqa: E402

#: Conditions the *game client* stamps: ``<level>-<mode>``, e.g. ``L2-ai-easy``. A record
#: in one of these came from a server room, where at least one seat was a person.
GAME_CLIENT_CONDITION = re.compile(r"^L(\d+)-")

#: Engine label the toy engine writes; a log claiming anything else cannot be verified
#: here because the upstream engine is not integrated (Gate 2).
TOY_ENGINE = "deterministic-toy"


class Failure:
    """One failed check, with enough context to fix it."""

    def __init__(self, where: str, reason: str) -> None:
        self.where = where
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.where}: {self.reason}"


def ply_cap_for(payload: dict[str, Any]) -> int:
    """The ply cap a record was played under.

    Since records started carrying ``max_plies`` this is a plain lookup, and that field
    is the reason the cap is recorded at all: ``outcome()`` treats ``ply >= max_plies``
    as terminal, so a search agent's rollouts read the cap, and a replay under a
    different one can legitimately play a different game. A log line without the cap was
    therefore not fully self-describing.

    For a log written before the field existed the cap has to be inferred from how the
    game ended, and the two cases are genuinely different:

    * ``ply_limit`` means the game was stopped *by* the cap, so the cap was exactly the
      recorded length. One ply more would let the game run on and print a different line.
    * anything else (``no_pieces``, ``no_legal_moves``, ``resign``) means the game ended
      because the engine said so, one ply after the last recorded turn, so the cap must
      be *larger* than the length or the replay stops on the cap before the engine's own
      terminal check is ever consulted.
    """
    recorded = payload.get("max_plies")
    if recorded is not None:
        return max(int(recorded), 1)
    length = max(int(payload.get("length") or 0), 1)
    if str(payload.get("termination")) == "ply_limit":
        return length
    return length + 1


def engine_for(payload: dict[str, Any]) -> DeterministicToyEngine:
    """Rebuild the engine a record was played on, from the record alone."""
    board = payload.get("final_board") or {}
    board_size = int(board.get("board_size") or 4)
    return DeterministicToyEngine(
        seed=int(payload["seed"]),
        level=int(payload["level"]),
        allow_observe=bool(payload["allow_observe"]),
        board_size=board_size,
        max_plies=ply_cap_for(payload),
    )


def replay_line(payload: dict[str, Any]) -> str:
    """Regenerate the JSON line for one record, byte for byte."""
    engine = engine_for(payload)
    seed = int(payload["seed"])
    players = payload["players"]
    agents = {}
    for seat_key, label in players.items():
        seat = int(seat_key)
        agents[seat] = make_agent(kind_for_label(str(label)), engine, seed)
    record = play(engine, agents, seed, condition=str(payload["condition"]))
    return record.to_line()


def verify_log(path: Path, *, replay: bool) -> dict[str, Any]:
    """Check one JSONL log. Returns its summary; failures are reported inside it."""
    report: dict[str, Any] = {
        "file": path.name,
        "records": 0,
        "experiment_records": 0,
        "game_client_records": 0,
        "replayed": 0,
        "levels": {},
        "failures": [],
        "stats": None,
    }
    failures: list[Failure] = report["failures"]
    texts = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payloads: list[dict[str, Any]] = []

    for number, text in enumerate(texts, start=1):
        where = f"{path.name}:{number}"
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            failures.append(Failure(where, f"invalid JSON ({exc})"))
            continue
        try:
            record_from_json(payload)
        except KeyError as exc:
            failures.append(Failure(where, f"missing required field ({exc})"))
            continue

        report["records"] += 1
        level = int(payload["level"])
        report["levels"][str(level)] = report["levels"].get(str(level), 0) + 1
        payloads.append(payload)

        client_condition = GAME_CLIENT_CONDITION.match(str(payload["condition"]))
        supported_engines = (TOY_ENGINE, "paper-quantum") if client_condition else (TOY_ENGINE,)
        if payload.get("engine") not in supported_engines:
            failures.append(
                Failure(where, f"engine {payload.get('engine')!r} cannot be verified here")
            )
            continue

        if client_condition:
            report["game_client_records"] += 1
            # A server room holds a person's moves, so the seed cannot regenerate it; the
            # level in the condition is still checkable, and that is what matters for the
            # game-only boundary.
            if int(client_condition.group(1)) != level:
                failures.append(
                    Failure(
                        where,
                        f"condition says level {client_condition.group(1)} but the record "
                        f"was played at level {level}",
                    )
                )
            continue

        report["experiment_records"] += 1
        if level not in BATCHABLE_LEVELS:
            failures.append(
                Failure(
                    where,
                    f"level {level} is not batchable (only {BATCHABLE_LEVELS} may be "
                    "logged by the runner)",
                )
            )
            continue

        if not replay:
            continue
        try:
            regenerated = replay_line(payload)
        except ValueError as exc:
            failures.append(Failure(where, f"cannot rebuild the players ({exc})"))
            continue
        if regenerated != text.strip():
            failures.append(
                Failure(
                    where,
                    f"{payload.get('game_id')!r} does not regenerate from its own seed "
                    "(the log line differs from a fresh replay)",
                )
            )
            continue
        report["replayed"] += 1

    if payloads:
        try:
            report["stats"] = summarize(payloads)
        except Exception as exc:  # pragma: no cover - defensive, reported not hidden
            failures.append(Failure(path.name, f"summarise failed ({exc})"))
    return report


def jsonable(value: Any) -> Any:
    """Plain JSON types, so the verification record can be written out.

    The statistics layer hands back :class:`~qcheckers.experiment.stats.Rate` objects for
    every metric. They carry a ``to_json`` of their own, which is what gets used here
    rather than re-deriving the interval for the record.
    """
    if isinstance(value, Failure):
        return str(value)
    if hasattr(value, "to_json"):
        return jsonable(value.to_json())
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def fmt_interval(rate: Any) -> str:
    """``point [low, high]`` for a metric, or a dash when it is undefined."""
    if rate is None:
        return "-"
    if not getattr(rate, "defined", True):
        return f"{rate.point:.3f} [undefined, n=0]"
    return f"{rate.point:.3f} [{rate.low:.3f}, {rate.high:.3f}]"


def print_report(report: dict[str, Any], *, replayed: bool) -> None:
    """One block per log: counts, levels, rates, then any failures."""
    levels = ", ".join(f"L{key}x{value}" for key, value in sorted(report["levels"].items()))
    line = (
        f"{report['file']}: {report['records']} records ({levels or 'no levels'})"
    )
    if report["game_client_records"]:
        line += f", {report['game_client_records']} from the game client"
    if replayed:
        line += f", {report['replayed']}/{report['experiment_records']} regenerated"
    print(line)

    stats = report["stats"]
    if stats and stats.get("metrics"):
        metrics = stats["metrics"]
        print(
            f"    n={stats['n_games']}  "
            f"p0 win {fmt_interval(metrics.get('win_rate_p0'))}  "
            f"draw {fmt_interval(metrics.get('draw_rate'))}  "
            f"collapse {fmt_interval(metrics.get('collapse_rate'))}"
        )
    for failure in report["failures"]:
        print(f"    FAIL {failure}")


def verify_directory(results_dir: Path, *, replay: bool) -> dict[str, Any]:
    """Verify every ``*.jsonl`` log in ``results_dir``, in a stable order."""
    logs = sorted(results_dir.glob("*.jsonl"))
    reports = [verify_log(path, replay=replay) for path in logs]
    return {
        "results_dir": str(results_dir),
        "replayed": replay,
        "logs": [report["file"] for report in reports],
        "records": sum(r["records"] for r in reports),
        "experiment_records": sum(r["experiment_records"] for r in reports),
        "game_client_records": sum(r["game_client_records"] for r in reports),
        "regenerated": sum(r["replayed"] for r in reports),
        "failures": [
            str(failure) for report in reports for failure in report["failures"]
        ],
        "per_file": reports,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Verify logged results regenerate from their own seeds.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--results-dir", default="results", help="Directory of JSONL logs to check."
    )
    parser.add_argument(
        "--json",
        default=None,
        help="Write the verification record to this path as JSON.",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Restate the rates but skip the replay comparison.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the verification; return the process exit status."""
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        print(f"nothing to verify: {results_dir} is not a directory")
        return 2

    replay = not args.stats_only
    summary = verify_directory(results_dir, replay=replay)

    if not summary["logs"]:
        print(f"nothing to verify: no *.jsonl logs in {results_dir}")
        return 2

    print("Verification of logged results")
    print(
        f"  engine: {TOY_ENGINE}   batchable levels: {BATCHABLE_LEVELS}   "
        f"replay: {'on' if replay else 'OFF (--stats-only)'}"
    )
    print("")
    for report in summary["per_file"]:
        print_report(report, replayed=replay)

    print("")
    print(
        f"{summary['records']} records in {len(summary['logs'])} logs: "
        f"{summary['regenerated']}/{summary['experiment_records']} experiment records "
        f"regenerated byte-for-byte, {summary['game_client_records']} game-client records "
        "checked for level only"
    )

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Serialised last, because the in-memory report carries Rate objects that the
        # printer needs and JSON cannot hold.
        target.write_text(
            json.dumps(jsonable(summary), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"verification record written to {target}")

    if summary["failures"]:
        print("")
        print(f"FAILED: {len(summary['failures'])} check(s) failed")
        for failure in summary["failures"]:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
