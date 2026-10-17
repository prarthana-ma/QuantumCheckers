"""Standalone verification tool for completed experiment outputs.

Validates JSONL syntax, schema conformance, unique game IDs, outcome/winner
consistency, seed metadata, replay references, and aggregate counts. Returns a
nonzero exit code when verification detects failures that invalidate the output.

This tool NEVER repairs, deletes, or rewrites source results. It only reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Allow running as a script from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qcheckers.experiment.schema import (  # noqa: E402
    SUPPORTED_VERSIONS,
    read_records,
    validate_record,
)
from qcheckers.experiment.replay import validate_replay, import_replay  # noqa: E402


def verify_file(
    path: str | Path,
    *,
    check_replays: bool = True,
    expected_count: int | None = None,
    expected_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Verify one JSONL results file. Returns a verification report dict."""
    p = Path(path)
    report: dict[str, Any] = {
        "file": str(p),
        "errors": [],
        "warnings": [],
        "info": [],
        "n_records": 0,
        "n_valid": 0,
        "n_invalid": 0,
        "game_ids": [],
        "outcome_counts": {},
        "winner_counts": {},
        "agent_pair": None,
        "experiment_id": None,
        "schema_versions": set(),
    }

    if not p.exists():
        report["errors"].append(f"file not found: {p}")
        return report

    try:
        raw_lines = p.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        report["errors"].append(f"cannot read file: {exc}")
        return report

    records: list[dict[str, Any]] = []
    game_ids: list[str] = []
    outcome_counter: Counter[str] = Counter()
    winner_counter: Counter[str] = Counter()
    agent_pair: set[tuple[str, str]] = set()
    experiment_ids: set[str] = set()
    schema_versions: set[str] = set()

    for line_num, line in enumerate(raw_lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            report["errors"].append(f"line {line_num}: malformed JSON: {exc}")
            report["n_invalid"] += 1
            continue

        if not isinstance(record, dict):
            report["errors"].append(
                f"line {line_num}: JSON value is not an object"
            )
            report["n_invalid"] += 1
            continue

        errors = validate_record(record)
        if errors:
            for err in errors:
                report["errors"].append(f"line {line_num}: {err}")
            report["n_invalid"] += 1
            continue

        report["n_valid"] += 1
        records.append(record)
        game_ids.append(record["game_id"])
        outcome_counter[record["outcome"]] += 1
        winner_counter[str(record["winner"])] += 1
        agent_pair.add(
            (
                record.get("player_assignment", {}).get("0", "?"),
                record.get("player_assignment", {}).get("1", "?"),
            )
        )
        experiment_ids.add(record["experiment_id"])
        schema_versions.add(record["schema_version"])

        # Check replay reference
        if check_replays and record.get("replay_ref"):
            replay_path = Path(record["replay_ref"])
            if not replay_path.is_absolute():
                replay_path = p.parent / replay_path
            if not replay_path.exists():
                report["warnings"].append(
                    f"line {line_num}: replay file not found: {record['replay_ref']}"
                )
            else:
                try:
                    payload = import_replay(replay_path)
                    replay_errors = validate_replay(payload)
                    if replay_errors:
                        for err in replay_errors:
                            report["errors"].append(
                                f"line {line_num}: replay {record['replay_ref']}: {err}"
                            )
                    # Cross-check outcome consistency
                    if payload.outcome != record["outcome"]:
                        report["errors"].append(
                            f"line {line_num}: replay outcome {payload.outcome!r} "
                            f"does not match record outcome {record['outcome']!r}"
                        )
                    if payload.winner != record["winner"]:
                        report["errors"].append(
                            f"line {line_num}: replay winner {payload.winner!r} "
                            f"does not match record winner {record['winner']!r}"
                        )
                except Exception as exc:
                    report["errors"].append(
                        f"line {line_num}: replay {record['replay_ref']}: {exc}"
                    )

    report["n_records"] = report["n_valid"]
    report["game_ids"] = game_ids
    report["outcome_counts"] = dict(outcome_counter)
    report["winner_counts"] = dict(winner_counter)
    report["schema_versions"] = list(schema_versions)

    if len(agent_pair) == 1:
        report["agent_pair"] = list(agent_pair)[0]
    elif len(agent_pair) > 1:
        report["warnings"].append(
            f"multiple agent pairs found: {agent_pair}"
        )

    if len(experiment_ids) == 1:
        report["experiment_id"] = list(experiment_ids)[0]
    elif len(experiment_ids) > 1:
        report["warnings"].append(
            f"multiple experiment IDs found: {experiment_ids}"
        )

    # Unique game IDs
    seen: set[str] = set()
    duplicates: set[str] = set()
    for gid in game_ids:
        if gid in seen:
            duplicates.add(gid)
        seen.add(gid)
    if duplicates:
        report["errors"].append(f"duplicate game IDs: {sorted(duplicates)}")

    # Expected count
    if expected_count is not None:
        if report["n_valid"] != expected_count:
            report["errors"].append(
                f"expected {expected_count} records, found {report['n_valid']}"
            )

    # Expected experiment ID
    if expected_experiment_id is not None:
        if report["experiment_id"] and report["experiment_id"] != expected_experiment_id:
            report["errors"].append(
                f"expected experiment_id {expected_experiment_id!r}, "
                f"found {report['experiment_id']!r}"
            )

    # Schema version compatibility
    for sv in schema_versions:
        if sv not in SUPPORTED_VERSIONS:
            report["errors"].append(f"unsupported schema version: {sv}")

    return report


def verify_directory(
    dir_path: str | Path,
    *,
    check_replays: bool = True,
) -> dict[str, Any]:
    """Verify all .jsonl files in a directory."""
    d = Path(dir_path)
    all_reports: dict[str, Any] = {"files": {}, "total_errors": 0, "total_warnings": 0}
    if not d.exists():
        all_reports["errors"] = [f"directory not found: {d}"]
        return all_reports
    for f in sorted(d.glob("*.jsonl")):
        report = verify_file(f, check_replays=check_replays)
        all_reports["files"][str(f)] = report
        all_reports["total_errors"] += len(report["errors"])
        all_reports["total_warnings"] += len(report["warnings"])
    return all_reports


def format_report(report: dict[str, Any], *, verbose: bool = False) -> str:
    """Format a verification report as human-readable text."""
    lines: list[str] = []
    lines.append(f"File: {report.get('file', 'N/A')}")
    lines.append(f"  Records: {report.get('n_records', 0)} valid, "
                 f"{report.get('n_invalid', 0)} invalid")
    if report.get("experiment_id"):
        lines.append(f"  Experiment: {report['experiment_id']}")
    if report.get("agent_pair"):
        lines.append(f"  Agent pair: {report['agent_pair'][0]} vs {report['agent_pair'][1]}")
    if report.get("outcome_counts"):
        lines.append(f"  Outcomes: {report['outcome_counts']}")
    if report.get("winner_counts"):
        lines.append(f"  Winners: {report['winner_counts']}")
    if report.get("schema_versions"):
        lines.append(f"  Schema versions: {report['schema_versions']}")

    if report.get("errors"):
        lines.append(f"  ERRORS ({len(report['errors'])}):")
        for err in report["errors"]:
            lines.append(f"    - {err}")
    if report.get("warnings"):
        lines.append(f"  WARNINGS ({len(report['warnings'])}):")
        for warn in report["warnings"]:
            lines.append(f"    - {warn}")
    if not report.get("errors") and not report.get("warnings"):
        lines.append("  PASS: no errors or warnings detected.")
    elif not report.get("errors"):
        lines.append("  PASS (with warnings).")
    else:
        lines.append("  FAIL: errors detected.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 1 on verification failure."""
    parser = argparse.ArgumentParser(
        description="Verify QuantumCheckers experiment JSONL outputs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="JSONL files or directories to verify.",
    )
    parser.add_argument(
        "--no-replays",
        action="store_true",
        help="Skip replay validation.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="Expected number of valid records per file.",
    )
    parser.add_argument(
        "--expected-experiment-id",
        default=None,
        help="Expected experiment_id value.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON summary.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output.",
    )
    args = parser.parse_args(argv)

    all_ok = True
    any_output = False

    for path_str in args.paths:
        p = Path(path_str)
        if p.is_dir():
            reports = verify_directory(p, check_replays=not args.no_replays)
            for fpath, report in reports["files"].items():
                any_output = True
                if args.json:
                    print(json.dumps({"file": fpath, **report}, indent=2, default=str))
                else:
                    print(format_report(report, verbose=args.verbose))
                    print()
                if report.get("errors"):
                    all_ok = False
            if not args.json and reports.get("total_errors"):
                all_ok = False
        elif p.is_file():
            report = verify_file(
                p,
                check_replays=not args.no_replays,
                expected_count=args.expected_count,
                expected_experiment_id=args.expected_experiment_id,
            )
            any_output = True
            if args.json:
                print(json.dumps({"file": str(p), **report}, indent=2, default=str))
            else:
                print(format_report(report, verbose=args.verbose))
            if report.get("errors"):
                all_ok = False
        else:
            print(f"error: path not found: {p}", file=sys.stderr)
            all_ok = False

    if not any_output:
        print("error: no files to verify", file=sys.stderr)
        return 2

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
