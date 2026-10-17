"""JSONL schema for experiment game records.

Defines the versioned schema for one-record-per-line experiment output. Each record
is independently parseable JSON. The schema is explicit about required vs optional
fields, uses ``None`` (never empty strings or ambiguous placeholders) for unavailable
values, and prevents non-finite numeric values from producing invalid JSON.

Schema version: "1.0". Migration rule: unknown versions are rejected loudly, never
silently coerced.
"""Game-record schema -- the JSONL contract every experiment writes.

Owner: **Person B -- baseline agents and harness**. The JSONL format is Person B's
deliverable per the brief (section 13); Person D consumes it for statistics and Person
E consumes it for the replay viewer.

Design rules
------------
1. **One JSON object per line, one file per condition.** Append-only, so a batch that
   dies halfway is still analysable.
2. **Enough to recompute every metric without re-running the game.** Each turn stores
   the full board snapshot *after* the move plus the collapse events that turn
   produced. Win rate, draw rate, collapse frequency, game length and move-usage
   counts are all derivable from that.
3. **Deterministic serialisation.** ``to_json`` returns plain dicts/lists/floats in a
   fixed key order, and floats are rounded, so the same seed yields a byte-identical
   line. ``tests/test_runner.py`` asserts this.
4. **Honest provenance.** Every record carries ``engine`` and ``toy_engine`` flags so
   nobody later mistakes toy-engine numbers for reproduced upstream numbers.

Rounding is applied at serialisation time only. In-memory values keep full precision,
so statistics computed from the dataclasses are not degraded by formatting choices.
"""

from __future__ import annotations

import json
import math
import sys
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


def env_metadata() -> dict[str, str]:
    """Return environment metadata dict for embedding in records."""
    import platform

    return {
        "python": _python_version(),
        "platform": platform.platform(),
from dataclasses import dataclass, field
from typing import Any

from qcheckers.engine.protocol import Action, GameState

#: Decimal places kept in serialised floats. Ten is far below any reporting precision
#: and well above float noise, so records stay byte-stable.
FLOAT_PRECISION = 10


def _round(value: float) -> float:
    """Round a float for stable serialisation, normalising ``-0.0`` to ``0.0``."""
    rounded = round(float(value), FLOAT_PRECISION)
    return 0.0 if rounded == 0.0 else rounded


def _squares(pairs: Any) -> list[list[float]]:
    """``[(square, weight), ...]`` -> ``[[row, col, weight], ...]``.

    Flattening to a 3-element list keeps JSONL compact and makes the viewer's parsing
    trivial, at the cost of a little explicitness.
    """
    return [[s[0], s[1], _round(w)] for s, w in pairs]


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One ply of one game.

    Attributes
    ----------
    ply:
        Zero-based ply index; matches ``GameState.ply`` before the action.
    player:
        Who moved.
    action:
        The action taken.
    board_after:
        Board snapshot after the action and any collapses it forced, in the
        ``engine.render`` shape (pieces with ``sites`` as ``[row, col, weight]``).
    events:
        Collapse events produced by this turn, each with its cause.
    """

    ply: int
    player: int
    action: Action
    board_after: dict[str, Any]
    events: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "ply": self.ply,
            "player": self.player,
            "action": self.action.to_json(),
            "board_after": self.board_after,
            "events": [dict(event) for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class GameRecord:
    """A complete game, ready to be analysed or replayed.

    Attributes
    ----------
    game_id:
        Stable identifier, ``"<condition>-<seed>"`` by convention. Unique within a file.
    seed:
        The seed that reproduces this game from a fresh engine.
    condition:
        Experimental condition label (see :mod:`qcheckers.experiment.config`). This is
        Person C's condition vocabulary and must stay stable once frozen.
    engine:
        Engine name string, e.g. ``"deterministic-toy"``.
    level:
        Engine level used.
    allow_observe:
        Whether the voluntary-measurement condition was on.
    max_plies:
        The ply cap the game was played under. Recorded because the cap is a *terminal
        condition* of this engine: a search agent's rollouts consult it, so a replay
        under a different cap can legitimately choose different moves. Without this
        field a log line would not be fully self-describing.
    players:
        ``{player_id: agent_label}`` so a log is interpretable without the script.
    winner:
        Winning player, or ``None`` for a draw.
    termination:
        Why the game ended.
    length:
        Number of plies played.
    collapses:
        Total collapse events across the game (count, not detail; detail is per turn).
    collapse_pieces:
        Pieces that were collapsed at least once.
    observe_moves:
        How many turns were spent on the Observe action.
    spread_moves:
        How many spread actions were taken.
    capture_moves:
        How many captures were taken.
    board_moves:
        How many ordinary moves were taken.
    rejoin_moves:
        How many rejoin actions were taken.
    final_board:
        Terminal board snapshot.
    turns:
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
    turns: tuple[TurnRecord, ...] = field(default=())

    # -- serialisation -----------------------------------------------------

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
            "toy_engine": self.engine.startswith("deterministic-toy"),
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
        return json.dumps(self.to_json(), sort_keys=False, separators=(",", ":"))

    # -- metrics -----------------------------------------------------------

    def is_draw(self) -> bool:
        return self.winner is None

    def collapsed(self) -> bool:
        """Whether any collapse happened at all -- the numerator for collapse rate."""
        return self.collapses > 0

    def winner_player(self) -> int | None:
        return self.winner


def record_from_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip helper: validate that a decoded JSON line has the expected keys.

    Full reconstruction back into :class:`GameRecord` objects is deliberately not
    provided -- analysis code works on the decoded dicts, and a half-honest
    ``from_json`` that silently drops fields would be worse than none. This function
    exists so tests and log readers can assert the shape cheaply.

    Returns the payload unchanged, so it can be used inline.

    Raises
    ------
    KeyError
        If a required field is missing.
    """
    required = (
        "game_id",
        "seed",
        "condition",
        "engine",
        "level",
        "allow_observe",
        "max_plies",
        "players",
        "winner",
        "termination",
        "length",
        "turns",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise KeyError(f"game record missing fields: {missing}")
    return payload


def board_snapshot(engine: Any, state: GameState) -> dict[str, Any]:
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
                "sites": _squares(p.sites),
                "uncertain": p.is_spread,
            }
            for p in state.pieces
        ],
        "captured": list(state.captured),
        "certainty": _round(state.certainty()),
    }


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
]
    "FLOAT_PRECISION",
    "GameRecord",
    "TurnRecord",
    "board_snapshot",
    "record_from_json",
]
