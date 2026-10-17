"""Replay export for QuantumCheckers.

Produces self-contained JSON replay payloads for P4's browser viewer. The payload
contains ordered actions, resulting states, events, and metadata — everything the
viewer needs without requiring Python runtime objects.

Replay format version: "1.0".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from qcheckers.engine.protocol import (
    Action,
    CollapseEvent,
    GameState,
    Outcome,
    Transition,
)

REPLAY_VERSION: str = "1.0"
SUPPORTED_REPLAY_VERSIONS: tuple[str, ...] = ("1.0",)


@dataclass(frozen=True)
class ReplayPiece:
    """A piece in a replay snapshot."""
    piece_id: str
    owner: int
    sites: list  # [[[row, col], weight], ...]


@dataclass(frozen=True)
class ReplayAction:
    """One action in a replay."""
    ply: int
    player: int
    kind: str
    origin: list | None = None  # [row, col]
    target: list | None = None  # [row, col]
    piece_id: str | None = None
    captured_id: str | None = None


@dataclass(frozen=True)
class ReplayEvent:
    """A collapse/measurement event."""
    ply: int
    kind: str
    piece_id: str
    resolved_to: list  # [row, col]
    cause: str


@dataclass(frozen=True)
class ReplayPayload:
    """Complete replay of one game."""
    replay_version: str
    experiment_id: str
    game_id: str
    seed: int
    board_size: int
    agents: dict  # {"0": name, "1": name}
    initial_pieces: list  # list of dicts
    actions: list  # list of ReplayAction dicts, in order
    events: list  # list of ReplayEvent dicts
    final_state: dict  # {"pieces": [...], "captured": [...], "outcome": str}
    outcome: str
    winner: int | None
    n_plies: int
    config_ref: str | None = None


def _square_to_list(sq: tuple[int, ...] | None) -> list | None:
    """Convert a Square tuple to a [row, col] list, or None."""
    if sq is None:
        return None
    return list(sq)


def state_to_pieces(state: GameState) -> list[dict[str, Any]]:
    """Convert a GameState's pieces to JSON-safe dicts."""
    result = []
    for piece in state.pieces:
        sites = [[_square_to_list(sq), w] for sq, w in piece.sites]
        result.append({
            "piece_id": piece.piece_id,
            "owner": piece.owner,
            "sites": sites,
        })
    return result


def action_to_replay(action: Action, ply: int, player: int) -> ReplayAction:
    """Convert an engine Action to a ReplayAction."""
    piece_id = getattr(action, "piece_id", None)
    captured_id = getattr(action, "captured_id", None)
    return ReplayAction(
        ply=ply,
        player=player,
        kind=action.kind,
        origin=_square_to_list(action.origin),
        target=_square_to_list(action.target),
        piece_id=piece_id,
        captured_id=captured_id,
    )


def event_to_replay(event: CollapseEvent, ply: int) -> ReplayEvent:
    """Convert a CollapseEvent to a ReplayEvent."""
    return ReplayEvent(
        ply=ply,
        kind="collapse",
        piece_id=event.piece_id,
        resolved_to=_square_to_list(event.resolved_to),
        cause=event.cause,
    )


def build_replay(
    *,
    experiment_id: str,
    game_id: str,
    seed: int,
    board_size: int,
    agents: dict[str, str],
    initial_state: GameState,
    transitions: Sequence[tuple[Action, Transition]],
    final_state: GameState,
    outcome: Outcome,
    config_ref: str | None = None,
) -> ReplayPayload:
    """Build a complete replay payload from a game's transition history."""
    actions: list[ReplayAction] = []
    events: list[ReplayEvent] = []
    for i, (action, transition) in enumerate(transitions):
        ply = i + 1
        player = 1 - transition.state.turn  # the player who just moved
        actions.append(action_to_replay(action, ply, player))
        for event in transition.events:
            events.append(event_to_replay(event, ply))

    outcome_str: str
    if outcome.winner is None:
        outcome_str = "draw"
    elif outcome.winner == 0:
        outcome_str = "win_p0"
    else:
        outcome_str = "win_p1"

    final_pieces = state_to_pieces(final_state)
    final_state_dict = {
        "pieces": final_pieces,
        "captured": list(final_state.captured),
        "outcome": outcome_str,
    }

    return ReplayPayload(
        replay_version=REPLAY_VERSION,
        experiment_id=experiment_id,
        game_id=game_id,
        seed=seed,
        board_size=board_size,
        agents=dict(agents),
        initial_pieces=state_to_pieces(initial_state),
        actions=actions,
        events=events,
        final_state=final_state_dict,
        outcome=outcome_str,
        winner=outcome.winner,
        n_plies=len(transitions),
        config_ref=config_ref,
    )


def serialize_replay(payload: ReplayPayload) -> str:
    """Serialize a ReplayPayload to a JSON string."""
    return json.dumps(asdict(payload), allow_nan=False, indent=2)


def deserialize_replay(data: str) -> ReplayPayload:
    """Parse a JSON string back into a ReplayPayload.

    Raises ValueError for invalid JSON or missing required fields.
    """
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid replay JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("replay JSON is not an object")
    required = [
        "replay_version", "experiment_id", "game_id", "seed",
        "board_size", "agents", "initial_pieces", "actions",
        "events", "final_state", "outcome", "winner", "n_plies",
    ]
    missing = [f for f in required if f not in obj]
    if missing:
        raise ValueError(f"replay missing required fields: {missing}")
    return ReplayPayload(
        replay_version=obj["replay_version"],
        experiment_id=obj["experiment_id"],
        game_id=obj["game_id"],
        seed=obj["seed"],
        board_size=obj["board_size"],
        agents=obj["agents"],
        initial_pieces=obj["initial_pieces"],
        actions=[ReplayAction(**a) for a in obj["actions"]],
        events=[ReplayEvent(**e) for e in obj["events"]],
        final_state=obj["final_state"],
        outcome=obj["outcome"],
        winner=obj["winner"],
        n_plies=obj["n_plies"],
        config_ref=obj.get("config_ref"),
    )


def export_replay(payload: ReplayPayload, path: str | Path) -> None:
    """Write a serialized replay to a file (pretty-printed JSON)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(serialize_replay(payload), encoding="utf-8")


def import_replay(path: str | Path) -> ReplayPayload:
    """Read and deserialize a replay file. Raises FileNotFoundError if missing."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"replay file not found: {p}")
    return deserialize_replay(p.read_text(encoding="utf-8"))


def validate_replay(payload: ReplayPayload) -> list[str]:
    """Validate a replay payload. Return list of error strings (empty = valid)."""
    errors: list[str] = []
    if payload.replay_version not in SUPPORTED_REPLAY_VERSIONS:
        errors.append(
            f"unsupported replay_version {payload.replay_version!r}; "
            f"supported: {SUPPORTED_REPLAY_VERSIONS}"
        )
    if not payload.experiment_id:
        errors.append("experiment_id must be non-empty")
    if not payload.game_id:
        errors.append("game_id must be non-empty")
    if payload.seed < 0:
        errors.append(f"seed must be >= 0, got {payload.seed}")
    if payload.board_size < 4:
        errors.append(f"board_size must be >= 4, got {payload.board_size}")
    if not isinstance(payload.agents, dict) or "0" not in payload.agents or "1" not in payload.agents:
        errors.append('agents must be a dict with keys "0" and "1"')
    if not isinstance(payload.initial_pieces, list):
        errors.append("initial_pieces must be a list")
    if not isinstance(payload.actions, list):
        errors.append("actions must be a list")
    for a in payload.actions:
        if a.ply < 0:
            errors.append(f"action ply must be >= 0, got {a.ply}")
        if a.player not in (0, 1):
            errors.append(f"action player must be 0 or 1, got {a.player}")
        if not a.kind:
            errors.append("action kind must be non-empty")
    for e in payload.events:
        if e.ply < 0:
            errors.append(f"event ply must be >= 0, got {e.ply}")
    if payload.n_plies != len(payload.actions):
        errors.append(
            f"n_plies ({payload.n_plies}) does not match actions length ({len(payload.actions)})"
        )
    # Outcome/winner consistency
    if payload.outcome == "win_p0" and payload.winner != 0:
        errors.append(f"outcome=win_p0 requires winner=0, got {payload.winner!r}")
    elif payload.outcome == "win_p1" and payload.winner != 1:
        errors.append(f"outcome=win_p1 requires winner=1, got {payload.winner!r}")
    elif payload.outcome == "draw" and payload.winner is not None:
        errors.append(f"outcome=draw requires winner=None, got {payload.winner!r}")
    return errors


def replay_to_viewer_json(payload: ReplayPayload) -> str:
    """Produce the final JSON string for the browser viewer."""
    return serialize_replay(payload)


__all__ = [
    "REPLAY_VERSION",
    "SUPPORTED_REPLAY_VERSIONS",
    "ReplayAction",
    "ReplayEvent",
    "ReplayPiece",
    "ReplayPayload",
    "action_to_replay",
    "build_replay",
    "deserialize_replay",
    "event_to_replay",
    "export_replay",
    "import_replay",
    "replay_to_viewer_json",
    "serialize_replay",
    "state_to_pieces",
    "validate_replay",
]
