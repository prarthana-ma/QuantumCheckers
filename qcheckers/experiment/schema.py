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
    "FLOAT_PRECISION",
    "GameRecord",
    "TurnRecord",
    "board_snapshot",
    "record_from_json",
]