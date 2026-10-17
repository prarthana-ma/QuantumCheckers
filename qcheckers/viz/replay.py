"""Game record -> replay payload for the static viewer.

Owner: **P4 -- replay viewer and reproducibility package**.

This is a **pure function**: same record in, same payload out, no file or network I/O,
no randomness. That matters because the viewer is a debugging tool for the log format,
so it must not be able to disagree with the log.

What the payload contains
-------------------------
* A header: game id, seed, condition, engine, level, players, winner, termination.
* A ``frames`` list, one per ply, each with the action taken, the board *after* that
  ply, and any collapse events with their cause.
* A ``summary`` block: counts of collapses, Observe uses, spread moves and captures,
  plus the final board.

Phase and amplitude
-------------------
The payload carries a top-level ``amplitude_display: false`` with an explanatory note.
The brief requires that if the published game's state is probability-only, the viewer
says so plainly rather than implying quantum phases exist. P4E must flip this only
after verifying against the paper and upstream code (Gate 5). Right now it is false
because the toy engine stores chance weights, not amplitudes.

No dependencies: pure stdlib, JSON-ready output only.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

#: Board edge length assumed when a record carries no board size.
DEFAULT_BOARD_SIZE = 4

AMPLITUDE_DISPLAY_NOTE = (
    "This payload stores occupancy CHANCES only. Whether the published game uses "
    "complex amplitudes and phases, or classical probabilities alone, is UNVERIFIED "
    "until the full paper and upstream code are read (Gate 5). Nothing here implies "
    "a phase display."
)


def _board_size(payload: Mapping[str, Any]) -> int:
    """Recover the board size from a record, falling back to the default."""
    for board in (
        payload.get("final_board"),
        *(
            turn.get("board_after", {})
            for turn in payload.get("turns", [])
            if isinstance(turn, Mapping)
        ),
    ):
        if isinstance(board, Mapping):
            size = board.get("board_size")
            if isinstance(size, int) and size > 0:
                return size
    return DEFAULT_BOARD_SIZE


def _site_triple(site: Sequence[Any]) -> tuple[int, int, float]:
    """Normalise a board site entry to ``(row, col, weight)``.

    Two encodings reach this module and both must work:

    * ``[[row, col], weight]`` -- what ``GameEngine.render`` emits and what therefore
      ends up in a record's ``board_after`` and ``final_board``.
    * ``[row, col, weight]`` -- the flattened form used for collapse-event chances in
      :mod:`qcheckers.experiment.schema`.

    Normalising in one place is what keeps the viewer from silently rendering an empty
    board when only one of the two shapes is handled.
    """
    if len(site) == 2 and isinstance(site[0], Sequence):
        row, col = int(site[0][0]), int(site[0][1])
        return row, col, float(site[1])
    if len(site) == 3:
        return int(site[0]), int(site[1]), float(site[2])
    raise ValueError(f"unrecognised site encoding: {site!r}")


def _cells(board: Mapping[str, Any], size: int) -> list[dict[str, Any]]:
    """Flatten a board snapshot into ``size * size`` viewer cells.

    One cell per square, with ``owner_chances`` holding a chance per player. A square
    that is genuinely ambiguous (two different owners both claiming it) keeps both
    entries, so the viewer can highlight it rather than silently picking one.
    """
    claims: dict[tuple[int, int], list[float]] = {
        (row, col): [0.0, 0.0] for row in range(size) for col in range(size)
    }
    for piece in board.get("pieces", []):
        owner = int(piece.get("owner", 0))
        for site in piece.get("sites", []):
            row, col, weight = _site_triple(site)
            if 0 <= row < size and 0 <= col < size:
                claims[(row, col)][owner] = max(claims[(row, col)][owner], weight)

    cells: list[dict[str, Any]] = []
    for row in range(size):
        for col in range(size):
            chances = claims[(row, col)]
            cells.append(
                {
                    "row": row,
                    "col": col,
                    "chances": chances,
                    "occupied": max(chances) > 0.0,
                    "uncertain": 0.0 < max(chances) < 1.0 - 1e-9,
                    "ambiguous": chances[0] > 0.0 and chances[1] > 0.0,
                }
            )
    return cells


def _event_frames(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalise collapse events into ``[row, col, weight]`` triples."""
    frames: list[dict[str, Any]] = []
    for event in events:
        chances = [list(_site_triple(entry)) for entry in event.get("chances", [])]
        sampled = event.get("sampled", [])
        frames.append(
            {
                "piece_id": event.get("piece_id"),
                "owner": event.get("owner"),
                "cause": event.get("cause"),
                "chances": chances,
                "sampled": (
                    [int(sampled[0]), int(sampled[1])] if len(sampled) == 2 else None
                ),
                "probability": event.get("probability"),
            }
        )
    return frames


def build_replay(record: Mapping[str, Any]) -> dict[str, Any]:
    """Turn one decoded game record into a viewer payload.

    Parameters
    ----------
    record:
        A decoded JSONL record, as returned by
        :func:`qcheckers.experiment.runner.read_jsonl`, or a plain dict with the same
        fields.

    Returns
    -------
    dict
        JSON-ready payload with ``header``, ``summary`` and ``frames``.

    Raises
    ------
    KeyError
        If ``game_id`` or ``seed`` is absent -- without those the viewer cannot label
        or reproduce the replay.
    """
    for required in ("game_id", "seed"):
        if required not in record:
            raise KeyError(f"record missing {required!r}; cannot build a replay")

    size = _board_size(record)
    turns = list(record.get("turns", []))

    frames: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        board = turn.get("board_after", {})
        frames.append(
            {
                "index": index,
                "ply": int(turn.get("ply", index)),
                "player": turn.get("player"),
                "action": turn.get("action", {}),
                "cells": _cells(board, size),
                "collapsed": bool(turn.get("events")),
                "events": _event_frames(list(turn.get("events", []))),
                "captured": list(board.get("captured", [])),
            }
        )

    return {
        "schema": "qcheckers-replay/1",
        "header": {
            "game_id": record.get("game_id"),
            "seed": record.get("seed"),
            "condition": record.get("condition"),
            "engine": record.get("engine"),
            "level": record.get("level"),
            "allow_observe": bool(record.get("allow_observe", False)),
            "toy_engine": bool(record.get("toy_engine", False)),
            "players": record.get("players", {}),
            "winner": record.get("winner"),
            "termination": record.get("termination"),
            "length": record.get("length"),
        },
        "board_size": size,
        "amplitude_display": False,
        "amplitude_note": AMPLITUDE_DISPLAY_NOTE,
        "summary": {
            "collapses": record.get("collapses", 0),
            "collapse_pieces": list(record.get("collapse_pieces", [])),
            "observe_moves": record.get("observe_moves", 0),
            "spread_moves": record.get("spread_moves", 0),
            "rejoin_moves": record.get("rejoin_moves", 0),
            "capture_moves": record.get("capture_moves", 0),
            "board_moves": record.get("board_moves", 0),
            "final_board": record.get("final_board", {}),
        },
        "frames": frames,
    }


def replay_to_json(payload: Mapping[str, Any], *, indent: int | None = None) -> str:
    """Serialise a replay payload to JSON text.

    ``indent=None`` (default) gives one compact line, which is what the CLI scripts
    write next to the JSONL log.
    """
    return json.dumps(payload, separators=(",", ":") if indent is None else None, indent=indent)


__all__ = [
    "AMPLITUDE_DISPLAY_NOTE",
    "DEFAULT_BOARD_SIZE",
    "build_replay",
    "replay_to_json",
]