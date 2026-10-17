"""Tests for the JSONL schema."""

from __future__ import annotations

import json
import math

import pytest

from qcheckers.experiment.schema import (
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    SUPPORTED_VERSIONS,
    is_valid_outcome,
    make_record,
    read_records,
    sanitize_value,
    validate_jsonl_line,
    validate_record,
    write_record,
)


def _valid_record():
    return {
        "schema_version": "1.0",
        "experiment_id": "test",
        "game_id": "test-g0001",
        "timestamp": "2026-10-17T12:00:00",
        "agents": {"0": "random", "1": "mcts"},
        "player_assignment": {"0": "random", "1": "mcts"},
        "seed": 42,
        "initial_state": {"pieces": 8, "board_size": 4},
        "config": {"n_games": 10},
        "outcome": "win_p0",
        "winner": 0,
        "draw_reason": None,
        "n_plies": 25,
        "duration_seconds": 1.5,
        "error": None,
    }


class TestValidateRecord:
    def test_valid_record(self):
        errors = validate_record(_valid_record())
        assert errors == []

    def test_missing_required(self):
        r = _valid_record()
        del r["seed"]
        errors = validate_record(r)
        assert any("seed" in e for e in errors)

    def test_bad_schema_version(self):
        r = _valid_record()
        r["schema_version"] = "9.9"
        errors = validate_record(r)
        assert any("schema_version" in e for e in errors)

    def test_inconsistent_outcome_winner(self):
        r = _valid_record()
        r["outcome"] = "win_p0"
        r["winner"] = 1
        errors = validate_record(r)
        assert any("winner" in e for e in errors)

    def test_draw_with_winner(self):
        r = _valid_record()
        r["outcome"] = "draw"
        r["winner"] = 0
        errors = validate_record(r)
        assert any("draw" in e for e in errors)

    def test_negative_n_plies(self):
        r = _valid_record()
        r["n_plies"] = -1
        errors = validate_record(r)
        assert any("n_plies" in e for e in errors)

    def test_nan_duration(self):
        r = _valid_record()
        r["duration_seconds"] = float("nan")
        errors = validate_record(r)
        assert any("duration" in e for e in errors)

    def test_inf_duration(self):
        r = _valid_record()
        r["duration_seconds"] = float("inf")
        errors = validate_record(r)
        assert any("duration" in e for e in errors)

    def test_bad_outcome(self):
        r = _valid_record()
        r["outcome"] = "something_else"
        errors = validate_record(r)
        assert any("outcome" in e for e in errors)

    def test_agents_missing_key(self):
        r = _valid_record()
        r["agents"] = {"0": "random"}
        errors = validate_record(r)
        assert any("agents" in e for e in errors)

    def test_error_with_valid_outcome(self):
        r = _valid_record()
        r["outcome"] = "win_p0"
        r["error"] = "some error"
        errors = validate_record(r)
        # error field is allowed to be non-null even for valid outcomes
        # (it's informational), so this should pass
        assert errors == []


class TestMakeRecord:
    def test_constructs_valid(self):
        r = make_record(**_valid_record())
        assert r["game_id"] == "test-g0001"

    def test_missing_raises(self):
        with pytest.raises(ValueError, match="missing"):
            make_record(schema_version="1.0")


class TestSanitizeValue:
    def test_nan_to_none(self):
        assert sanitize_value(float("nan")) is None

    def test_inf_to_none(self):
        assert sanitize_value(float("inf")) is None

    def test_finite_float_preserved(self):
        assert sanitize_value(1.5) == 1.5

    def test_tuple_to_list(self):
        result = sanitize_value((1, 2))
        assert result == [1, 2]
        assert isinstance(result, list)

    def test_nested(self):
        result = sanitize_value({"a": (float("nan"), 1.0)})
        assert result == {"a": [None, 1.0]}


class TestJsonlLine:
    def test_valid_line(self):
        line = json.dumps(_valid_record())
        record, errors = validate_jsonl_line(line)
        assert record is not None
        assert errors == []

    def test_malformed_json(self):
        record, errors = validate_jsonl_line("{bad json")
        assert record is None
        assert len(errors) > 0

    def test_non_dict_json(self):
        record, errors = validate_jsonl_line("[1, 2, 3]")
        assert record is None
        assert len(errors) > 0

    def test_empty_line(self):
        record, errors = validate_jsonl_line("")
        assert record is None
        assert errors == []

    def test_whitespace_only(self):
        record, errors = validate_jsonl_line("   \n  ")
        assert record is None
        assert errors == []

    def test_truncated_record(self):
        line = json.dumps(_valid_record())[:-10]  # cut off last 10 chars
        record, errors = validate_jsonl_line(line)
        # Either malformed JSON or missing fields
        assert record is None or len(errors) > 0


class TestWriteRead:
    def test_round_trip(self, tmp_path):
        r = _valid_record()
        p = tmp_path / "test.jsonl"
        with open(p, "w") as f:
            write_record(f, r)
        results = read_records(p)
        assert len(results) == 1
        record, errors = results[0]
        assert errors == []
        assert record["game_id"] == "test-g0001"

    def test_multiple_records(self, tmp_path):
        p = tmp_path / "multi.jsonl"
        with open(p, "w") as f:
            for i in range(5):
                r = _valid_record()
                r["game_id"] = f"g{i}"
                write_record(f, r)
        results = read_records(p)
        assert len(results) == 5

    def test_read_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_records(tmp_path / "nonexistent.jsonl")

    def test_write_prevents_nan(self, tmp_path):
        p = tmp_path / "nan.jsonl"
        r = _valid_record()
        r["duration_seconds"] = float("nan")
        with open(p, "w") as f:
            write_record(f, r)
        # Should not contain NaN literal
        text = p.read_text()
        assert "NaN" not in text


class TestIsValidOutcome:
    def test_valid(self):
        assert is_valid_outcome("win_p0")
        assert is_valid_outcome("win_p1")
        assert is_valid_outcome("draw")
        assert is_valid_outcome("error")

    def test_invalid(self):
        assert not is_valid_outcome("victory")
        assert not is_valid_outcome("")
