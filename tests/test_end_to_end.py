"""End-to-end test: run a complete experiment, verify results, validate replays.

This test exercises the full P3 pipeline: config -> runner -> schema -> verify.
It uses the non-authoritative QuantumToyEngine fixture (P5's engine not yet available).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from qcheckers.experiment.config import ExperimentConfig
from qcheckers.experiment.runner import run_experiment
from qcheckers.experiment.schema import read_records
from tests.support.quantum_toy import QuantumToyEngine


def _engine_factory(seed: int) -> QuantumToyEngine:
    return QuantumToyEngine(
        seed=seed, level=2, board_size=4, max_plies=80, allow_observe=True
    )


class TestEndToEnd:
    def test_full_pipeline(self, tmp_path):
        """Run experiment, write JSONL, verify with verify_results.py."""
        config = ExperimentConfig(
            experiment_id="e2e-test",
            agents=("random", "mcts"),
            n_games=6,
            base_seed=123,
            board_size=4,
            max_plies=80,
            level=2,
            output_dir=str(tmp_path),
            export_replays=True,
            alternate_seats=True,
        )

        # Run the experiment
        records = run_experiment(config, _engine_factory)
        assert len(records) == 6

        # Verify records exist and are valid
        from qcheckers.experiment.schema import validate_record
        for r in records:
            errors = validate_record(r)
            assert errors == [], f"record {r['game_id']} has errors: {errors}"

        # Verify output file
        output = tmp_path / "e2e-test.jsonl"
        assert output.exists()
        read_results = read_records(output)
        assert len(read_results) == 6

        # Run verification script as subprocess
        verify_script = Path(__file__).resolve().parents[1] / "scripts" / "verify_results.py"
        result = subprocess.run(
            [sys.executable, str(verify_script), str(output)],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        # Verification should pass (exit code 0)
        assert result.returncode == 0, (
            f"verification failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify replay files
        replay_dir = tmp_path / "replays"
        assert replay_dir.exists()
        replay_files = list(replay_dir.glob("*.replay.json"))
        assert len(replay_files) == 6

        # Validate each replay
        from qcheckers.experiment.replay import import_replay, validate_replay
        for rf in replay_files:
            payload = import_replay(rf)
            errors = validate_replay(payload)
            assert errors == [], f"replay {rf.name} has errors: {errors}"

    def test_seeded_reproducibility(self, tmp_path):
        """Same config + same seeds => same outcomes."""
        def run_once():
            config = ExperimentConfig(
                experiment_id="repro-test",
                agents=("random", "random"),
                n_games=4,
                base_seed=99,
                board_size=4,
                max_plies=60,
                output_dir=str(tmp_path),
            )
            records = run_experiment(config, _engine_factory)
            return [(r["outcome"], r["winner"], r["n_plies"]) for r in records]

        outcomes1 = run_once()
        outcomes2 = run_once()
        assert outcomes1 == outcomes2

    def test_cli_smoke(self, tmp_path):
        """The baseline CLI smoke test should work end-to-end."""
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_baseline.py"
        result = subprocess.run(
            [sys.executable, str(script), "--smoke", "--results-dir", str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0, (
            f"CLI failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Check output file exists
        assert (tmp_path / "smoke.jsonl").exists()

    def test_verify_detects_corruption(self, tmp_path):
        """Verification should catch a corrupted record."""
        from qcheckers.experiment.schema import write_record, validate_record

        good = {
            "schema_version": "1.0",
            "experiment_id": "corrupt-test",
            "game_id": "corrupt-g0001",
            "timestamp": "2026-10-17T12:00:00",
            "agents": {"0": "random", "1": "mcts"},
            "player_assignment": {"0": "random", "1": "mcts"},
            "seed": 1,
            "initial_state": {"pieces": 8, "board_size": 4},
            "config": {},
            "outcome": "win_p0",
            "winner": 0,
            "draw_reason": None,
            "n_plies": 10,
            "duration_seconds": 1.0,
            "error": None,
        }

        p = tmp_path / "corrupt.jsonl"
        with open(p, "w") as f:
            write_record(f, good)
            # Write a corrupted record (bad outcome/winner consistency)
            bad = dict(good)
            bad["game_id"] = "corrupt-g0002"
            bad["outcome"] = "win_p0"
            bad["winner"] = 1  # inconsistent!
            write_record(f, bad)

        verify_script = Path(__file__).resolve().parents[1] / "scripts" / "verify_results.py"
        result = subprocess.run(
            [sys.executable, str(verify_script), str(p)],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        # Should fail (nonzero exit) due to inconsistent record
        assert result.returncode != 0
