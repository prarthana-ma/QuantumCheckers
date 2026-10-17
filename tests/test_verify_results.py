"""The results verifier is a tool the report cites, so it gets tested too.

Owner: **P5 -- rules, engine, harness and batches**.

The verifier is a CLI, so these tests drive it as one (subprocess, exit status, files on
disk) rather than importing its internals: the claim in the report is "this command
checks the logs", and that is the interface that has to work.

What is covered:

* a freshly written batch verifies, and the record it writes agrees with what was checked;
* a tampered line is caught, and the failure names the file and line;
* a level the batch runner is forbidden to write is caught even when the JSON is
  otherwise well formed (the game-only boundary);
* a game-client record (a server room, where a person played a seat) is counted and
  level-checked but never replayed, because a human's moves are not seed-regenerable;
* an empty results directory is reported as nothing to verify, not as a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.experiment.runner import run_condition, write_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_results.py"

#: A batch small enough to replay in the tests but big enough to walk a whole game.
SEEDS = (0, 1, 2)


def _write_batch(path: Path, *, level: int = 2, observe: bool = True) -> list[str]:
    """Write a real (tiny) batch of games and return its exact lines."""
    records = run_condition(
        lambda seed: DeterministicToyEngine(
            seed=seed, level=level, allow_observe=observe, max_plies=60
        ),
        ("random", "random"),
        SEEDS,
        condition="verify-smoke",
    )
    write_jsonl(path, records)
    return [record.to_line() for record in records]


def _run(results_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run the verifier over ``results_dir`` and capture everything."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--results-dir", str(results_dir), *extra],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_a_fresh_batch_verifies_and_the_record_agrees(tmp_path: Path) -> None:
    """Every record in a freshly written batch must regenerate byte-for-byte."""
    lines = _write_batch(tmp_path / "verify-smoke.jsonl")
    record = tmp_path / "verification.json"

    result = _run(tmp_path, "--json", str(record))
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["records"] == len(lines)
    assert payload["experiment_records"] == len(lines)
    assert payload["regenerated"] == len(lines)
    assert payload["failures"] == []


def test_a_tampered_line_is_caught_and_named(tmp_path: Path) -> None:
    """A record that no longer matches its own seed must fail, with file and line."""
    path = tmp_path / "verify-smoke.jsonl"
    lines = _write_batch(path)
    # Flip the winner on the first line: still valid JSON, still schema-shaped, and now
    # unreproducible. This is exactly the corruption the check exists to catch.
    payload = json.loads(lines[0])
    payload["winner"] = None if payload["winner"] is not None else 0
    path.write_text(
        "\n".join([json.dumps(payload), *lines[1:]]) + "\n", encoding="utf-8"
    )

    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAILED" in result.stdout
    assert "verify-smoke.jsonl:1" in result.stdout


def test_a_non_batchable_level_is_refused(tmp_path: Path) -> None:
    """Level 3 (merge) must never appear in an experiment log, and is caught here."""
    path = tmp_path / "verify-smoke.jsonl"
    lines = _write_batch(path)
    payload = json.loads(lines[0])
    payload["level"] = 3
    path.write_text(
        "\n".join([json.dumps(payload), *lines[1:]]) + "\n", encoding="utf-8"
    )

    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not batchable" in result.stdout


@pytest.mark.parametrize("engine", ["deterministic-toy", "paper-quantum"])
def test_a_game_client_record_is_counted_but_not_replayed(tmp_path: Path, engine: str) -> None:
    """Server rooms hold a person's moves, so they are level-checked and left alone."""
    path = tmp_path / "game-client.jsonl"
    line = json.loads(_write_batch(tmp_path / "tmp-batch.jsonl")[0])
    line["condition"] = "L2-local"
    line["engine"] = engine
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    (tmp_path / "tmp-batch.jsonl").unlink()

    record = tmp_path / "verification.json"
    result = _run(tmp_path, "--json", str(record))
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["game_client_records"] == 1
    assert payload["experiment_records"] == 0
    assert payload["regenerated"] == 0


def test_paper_engine_experiments_are_not_claimed_as_replayed(tmp_path: Path) -> None:
    path = tmp_path / "verify-smoke.jsonl"
    payload = json.loads(_write_batch(path)[0])
    payload["engine"] = "paper-quantum"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "cannot be verified here" in result.stdout


def test_a_mismatched_game_client_level_is_caught(tmp_path: Path) -> None:
    """A room condition that disagrees with the recorded level is a failure."""
    path = tmp_path / "game-client.jsonl"
    line = json.loads(_write_batch(tmp_path / "tmp-batch.jsonl")[0])
    line["condition"] = "L4-local"  # claims level 4, record says level 2
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    (tmp_path / "tmp-batch.jsonl").unlink()

    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "condition says level 4" in result.stdout


def test_stats_only_skips_the_replay(tmp_path: Path) -> None:
    """``--stats-only`` restates the rates and says the replay is off."""
    _write_batch(tmp_path / "verify-smoke.jsonl")

    result = _run(tmp_path, "--stats-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OFF (--stats-only)" in result.stdout
    assert "n=3" in result.stdout


def test_an_empty_results_directory_is_not_a_pass(tmp_path: Path) -> None:
    """Nothing to verify must exit 2, so CI cannot read silence as success."""
    result = _run(tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "nothing to verify" in result.stdout

    missing = _run(tmp_path / "does-not-exist")
    assert missing.returncode == 2
    assert "not a directory" in missing.stdout
