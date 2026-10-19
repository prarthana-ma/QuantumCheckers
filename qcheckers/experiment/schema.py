"""JSONL schema for experiment game records.

Defines the versioned schema for one-record-per-line experiment output. Each record
is independently parseable JSON. The schema is explicit about required vs optional
fields, uses ``None`` (never empty strings or ambiguous placeholders) for unavailable
values, and prevents non-finite numeric values from producing invalid JSON.

Schema version: "1.0". Migration rule: unknown versions are rejected loudly, never
silently coerced.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION: str = "1.0"
SUPPORTED_VERSIONS: tuple[str, ...] = ("1.0",)

VALID_OUTCOMES: tuple[str, ...] = (
    "win_p0",
    "win_p1",
    "draw",
    "error",
    "timeout",
    "invalid_action",
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "experiment_id",
    "game_id",
    "timestamp",
    "agents",
    "player_assignment",
    "seed",
    "initial_state",
    "config",
    "outcome",
    "winner",
    "draw_reason",
    "n_plies",
    "duration_seconds",
    "error",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "replay_ref",
    "metrics",
    "env",
)


def is_valid_outcome(outcome: str) -> bool:
    """Check that ``outcome`` is a recognized terminal status string."""
    return outcome in VALID_OUTCOMES


def sanitize_value(v: Any) -> Any:
    """Recursively sanitize a value for safe JSON serialization.

    - Non-finite floats (NaN, Inf) become ``None``.
    - Tuples become lists.
    - Sets become sorted lists.
    - Dicts have keys coerced to strings and values sanitized recursively.
    """
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, tuple):
        return [sanitize_value(x) for x in v]
    if isinstance(v, list):
        return [sanitize_value(x) for x in v]
    if isinstance(v, set):
        return sorted(sanitize_value(x) for x in v)
    if isinstance(v, dict):
        return {str(k): sanitize_value(val) for k, val in v.items()}
    return v


def make_record(**kwargs: Any) -> dict[str, Any]:
    """Construct a record dict with all required fields, validating presence and type.

    Raises ValueError if any required field is missing, TypeError if a field has
    a grossly wrong type.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in kwargs]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    record = {f: kwargs[f] for f in REQUIRED_FIELDS}
    for f in OPTIONAL_FIELDS:
        if f in kwargs:
            record[f] = kwargs[f]
    # Sanitize everything so non-finite values become None
    record = sanitize_value(record)
    errors = validate_record(record)
    if errors:
        raise ValueError(f"record validation failed: {errors}")
    return record


def validate_record(record: dict[str, Any]) -> list[str]:
    """Validate a record dict. Return a list of error strings (empty = valid)."""
    errors: list[str] = []

    for f in REQUIRED_FIELDS:
        if f not in record:
            errors.append(f"missing required field: {f}")

    if "schema_version" in record:
        if record["schema_version"] not in SUPPORTED_VERSIONS:
            errors.append(
                f"unsupported schema_version {record['schema_version']!r}; "
                f"supported: {SUPPORTED_VERSIONS}"
            )

    if "experiment_id" in record:
        if not isinstance(record["experiment_id"], str) or not record["experiment_id"]:
            errors.append("experiment_id must be a non-empty string")

    if "game_id" in record:
        if not isinstance(record["game_id"], str) or not record["game_id"]:
            errors.append("game_id must be a non-empty string")

    if "timestamp" in record:
        if not isinstance(record["timestamp"], str) or not record["timestamp"]:
            errors.append("timestamp must be a non-empty string")

    if "outcome" in record:
        if not is_valid_outcome(record["outcome"]):
            errors.append(
                f"invalid outcome {record['outcome']!r}; valid: {VALID_OUTCOMES}"
            )

    if "winner" in record:
        w = record["winner"]
        if w is not None and w not in (0, 1):
            errors.append(f"winner must be 0, 1, or None, got {w!r}")

    # Outcome/winner consistency
    if "outcome" in record and "winner" in record:
        outcome, winner = record["outcome"], record["winner"]
        if outcome == "win_p0" and winner != 0:
            errors.append(f"outcome=win_p0 requires winner=0, got {winner!r}")
        elif outcome == "win_p1" and winner != 1:
            errors.append(f"outcome=win_p1 requires winner=1, got {winner!r}")
        elif outcome == "draw" and winner is not None:
            errors.append(f"outcome=draw requires winner=None, got {winner!r}")
        elif outcome in ("error", "timeout", "invalid_action") and winner is not None:
            errors.append(
                f"outcome={outcome} requires winner=None, got {winner!r}"
            )

    if "n_plies" in record:
        if not isinstance(record["n_plies"], int) or record["n_plies"] < 0:
            errors.append(f"n_plies must be a non-negative int, got {record['n_plies']!r}")

    if "duration_seconds" in record:
        d = record["duration_seconds"]
        if not isinstance(d, (int, float)) or d < 0 or not math.isfinite(d):
            errors.append(
                f"duration_seconds must be a non-negative finite number, got {d!r}"
            )

    if "seed" in record:
        s = record["seed"]
        if not isinstance(s, int) or s < 0:
            errors.append(f"seed must be a non-negative int, got {s!r}")

    if "agents" in record:
        a = record["agents"]
        if not isinstance(a, dict) or "0" not in a or "1" not in a:
            errors.append('agents must be a dict with keys "0" and "1"')

    if "player_assignment" in record:
        pa = record["player_assignment"]
        if not isinstance(pa, dict) or "0" not in pa or "1" not in pa:
            errors.append('player_assignment must be a dict with keys "0" and "1"')

    if "draw_reason" in record and record["draw_reason"] is not None:
        if not isinstance(record["draw_reason"], str):
            errors.append("draw_reason must be a string or None")

    if "error" in record and record["error"] is not None:
        if not isinstance(record["error"], str):
            errors.append("error must be a string or None")

    return errors


def validate_jsonl_line(line: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse and validate one JSONL line.

    Returns ``(record, errors)``. For empty lines returns ``(None, [])``. For
    malformed JSON returns ``(None, [error])``. For valid JSON that fails schema
    validation returns ``(record, errors)``.
    """
    stripped = line.strip()
    if not stripped:
        return None, []
    try:
        record = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, [f"malformed JSON: {exc}"]
    if not isinstance(record, dict):
        return None, [f"JSON value is not an object: {type(record).__name__}"]
    errors = validate_record(record)
    return record, errors


def write_record(f: Any, record: dict[str, Any]) -> None:
    """Write one record as a JSON line to an open text file handle.

    Uses ``allow_nan=False`` so non-finite values raise rather than producing
    invalid JSON. The record is sanitized before writing.
    """
    safe = sanitize_value(record)
    f.write(json.dumps(safe, allow_nan=False) + "\n")


def read_records(path: str | Path) -> list[tuple[dict[str, Any] | None, list[str]]]:
    """Read all records from a JSONL file.

    Returns a list of ``(record, errors)`` tuples, one per non-empty line.
    Empty lines produce ``(None, [])``. Raises FileNotFoundError if path missing.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"records file not found: {p}")
    results: list[tuple[dict[str, Any] | None, list[str]]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        record, errors = validate_jsonl_line(line)
        results.append((record, errors))
    return results


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def board_snapshot(engine: Any, state: Any) -> dict[str, Any]:
    """Board snapshot in the shape stored on disk.

    Thin wrapper over ``engine.render`` so that the ``sites`` layout is produced in
    exactly one place. Falls back to a minimal snapshot if an engine lacks ``render``.
    """
    if hasattr(engine, "render"):
        return dict(engine.render(state))
    return {
        "engine": type(engine).__name__,
        "ply": state.ply,
        "turn": state.turn,
        "pieces": [
            {
                "piece_id": p.piece_id,
                "owner": p.owner,
                "sites": p.sites,
                "uncertain": p.is_spread,
            }
            for p in state.pieces
        ],
        "captured": list(state.captured),
        "certainty": state.certainty(),
    }


def env_metadata() -> dict[str, str]:
    """Return environment metadata dict for embedding in records."""
    import platform

    return {
        "python": _python_version(),
        "platform": platform.platform(),
    }


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One ply of one game.

    Attributes
    ----------
    ply : int
        Zero-based ply index; matches ``GameState.ply`` before the action.
    player : int
        Who moved.
    action : Action
        The action taken.
    board_after : dict[str, Any]
        Board snapshot after the action and any collapses it forced, in the
        ``engine.render`` shape (pieces with ``sites`` as ``[row, col, weight]``).
    events : tuple[dict[str, Any], ...] = ()
        Collapse events produced by this turn, each with its cause.
    """

    ply: int
    player: int
    action: Any
    board_after: dict[str, Any]
    events: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "ply": self.ply,
            "player": self.player,
            "action": {
                "kind": self.action.kind,
                "piece_id": getattr(self.action, "piece_id", ""),
                "origin": list(getattr(self.action, "origin", ())),
                "target": list(getattr(self.action, "target", ())),
            },
            "board_after": self.board_after,
            "events": [dict(event) for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class GameRecord:
    """A complete game record, ready for JSONL output or analysis.

    Attributes
    ----------
    game_id : str
        Stable identifier, ``"<condition>-<seed>"`` by convention.
    seed : int
        The seed that reproduces this game from a fresh engine.
    condition : str
        Experimental condition label.
    engine : str
        Engine name string, e.g. ``"deterministic-toy"``.
    level : int
        Engine level used.
    allow_observe : bool
        Whether the voluntary-measurement condition was on.
    max_plies : int
        The ply cap the game was played under.
    players : dict[int, str]
        ``{player_id: agent_label}`` so a log is interpretable without the script.
    winner : int | None
        Winning player, or ``None`` for a draw.
    termination : str
        Why the game ended.
    length : int
        Number of plies played.
    collapses : int
        Total collapse events across the game.
    collapse_pieces : tuple[str, ...]
        Pieces that were collapsed at least once.
    observe_moves : int
        How many turns were spent on the Observe action.
    spread_moves : int
        How many spread actions were taken.
    capture_moves : int
        How many captures were taken.
    board_moves : int
        How many ordinary moves were taken.
    rejoin_moves : int
        How many rejoin actions were taken.
    final_board : dict[str, Any]
        Terminal board snapshot.
    turns : tuple[TurnRecord, ...] = ()
        Per-turn detail, enough to replay the game in the viewer.
    """

    game_id: str
    seed: int
    condition: str
    engine: str
    level: int
    allow_observe: bool
    max_plies: int
    players: dict[int, str]
    winner: int | None
    termination: str
    length: int
    collapses: int
    collapse_pieces: tuple[str, ...]
    observe_moves: int
    spread_moves: int
    capture_moves: int
    board_moves: int
    rejoin_moves: int
    final_board: dict[str, Any]
    turns: tuple["TurnRecord", ...] = ()

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict with deterministic key order."""
        return {
            "game_id": self.game_id,
            "seed": self.seed,
            "condition": self.condition,
            "engine": self.engine,
            "level": self.level,
            "allow_observe": self.allow_observe,
            "max_plies": self.max_plies,
            "players": {str(key): self.players[key] for key in sorted(self.players)},
            "winner": self.winner,
            "termination": self.termination,
            "length": self.length,
            "collapses": self.collapses,
            "collapse_pieces": list(self.collapse_pieces),
            "observe_moves": self.observe_moves,
            "spread_moves": self.spread_moves,
            "capture_moves": self.capture_moves,
            "board_moves": self.board_moves,
            "rejoin_moves": self.rejoin_moves,
            "final_board": self.final_board,
            "turns": [turn.to_json() for turn in self.turns],
        }

    def to_line(self) -> str:
        """Serialise to a single JSONL line, with no trailing newline."""
        import json

        return json.dumps(self.to_json(), sort_keys=False, separators=(",", ":"))


__all__ = [
    "OPTIONAL_FIELDS",
    "REQUIRED_FIELDS",
    "SCHEMA_VERSION",
    "SUPPORTED_VERSIONS",
    "VALID_OUTCOMES",
    "env_metadata",
    "is_valid_outcome",
    "make_record",
    "read_records",
    "sanitize_value",
    "validate_jsonl_line",
    "validate_record",
    "write_record",
    "GameRecord",
]
