"""Shared value types and interface for Quantum Checkers engines.

The toy and paper engines own all rule decisions. Agents, the server, and experiment
code consume this module's immutable actions and state snapshots instead of
implementing rules themselves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, Sequence, runtime_checkable

Square = tuple[int, int]
Player = Literal[0, 1]
Chance = float
CollapseCause = Literal["observe", "capture", "rejoin", "join", "decoherence"]
DEFAULT_BOARD_SIZE = 4


@dataclass(frozen=True, slots=True)
class Piece:
    """A piece and its probability distribution over candidate squares."""

    piece_id: str
    owner: Player
    sites: tuple[tuple[Square, Chance], ...]
    coherence: int | None = None

    def __post_init__(self) -> None:
        if not self.piece_id:
            raise ValueError("Piece.piece_id must be non-empty")
        if self.owner not in (0, 1):
            raise ValueError(f"Piece.owner must be 0 or 1, got {self.owner!r}")
        if not self.sites:
            raise ValueError(f"Piece {self.piece_id!r} must occupy at least one square")
        squares = [square for square, _ in self.sites]
        if len(set(squares)) != len(squares):
            raise ValueError(f"Piece {self.piece_id!r} lists a square more than once")
        weights = [weight for _, weight in self.sites]
        if any(not math.isfinite(weight) or weight <= 0 for weight in weights):
            raise ValueError(f"Piece {self.piece_id!r} weights must be finite and positive")
        total = sum(weights)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Piece {self.piece_id!r} site weights sum to {total!r}, expected 1.0"
            )
        if self.coherence is not None and self.coherence < 0:
            raise ValueError("Piece.coherence must be non-negative or None")

    @property
    def is_spread(self) -> bool:
        return len(self.sites) > 1

    @property
    def squares(self) -> tuple[Square, ...]:
        return tuple(square for square, _ in self.sites)

    def chance_at(self, square: Square) -> Chance:
        return next((weight for candidate, weight in self.sites if candidate == square), 0.0)

    def with_sites(
        self, sites: Sequence[tuple[Square, Chance]], coherence: int | None = None
    ) -> Piece:
        return Piece(
            self.piece_id,
            self.owner,
            tuple((square, float(weight)) for square, weight in sites),
            coherence,
        )


@dataclass(frozen=True, kw_only=True)
class Action:
    """Base value type shared by concrete actions and test engines."""

    kind: str
    origin: Square | None = None
    target: Square | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("Action.kind must be a non-empty string")

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for custom/test actions."""
        result: dict[str, Any] = {"kind": self.kind}
        for name in ("piece_id", "origin", "target", "jumped", "sites",
                     "other_piece_id", "captured_id", "absorbed_id"):
            if not hasattr(self, name):
                continue
            value = getattr(self, name)
            if name in ("origin", "target", "jumped") and value is not None:
                value = list(value)
            elif name == "sites":
                value = [[list(square), weight] for square, weight in value]
            result[name] = value
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveAction(Action):
    piece_id: str
    origin: Square
    target: Square
    kind: Literal["move"] = field(default="move", init=False)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "target": list(self.target)}


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureAction(Action):
    piece_id: str
    origin: Square
    jumped: Square
    target: Square
    kind: Literal["capture"] = field(default="capture", init=False)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "jumped": list(self.jumped),
                "target": list(self.target)}


@dataclass(frozen=True, slots=True, kw_only=True)
class SpreadAction(Action):
    piece_id: str = ""
    origin: Square | None = None
    sites: tuple[tuple[Square, Chance], ...] = ()
    kind: Literal["spread"] = field(default="spread", init=False)

    def __post_init__(self) -> None:
        super(SpreadAction, self).__post_init__()
        # The non-authoritative P3 fixture uses the older origin/target-only shape.
        if not self.piece_id and self.target is not None:
            object.__setattr__(self, "kind", "split")

    def to_json(self) -> dict[str, Any]:
        result = {"kind": self.kind}
        if self.piece_id:
            result["piece_id"] = self.piece_id
        if self.origin is not None:
            result["origin"] = list(self.origin)
        if self.target is not None:
            result["target"] = list(self.target)
        if self.sites:
            result["sites"] = [
                [list(square), weight] for square, weight in self.sites
            ]
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class RejoinAction(Action):
    piece_id: str
    origin: Square
    target: Square
    kind: Literal["rejoin"] = field(default="rejoin", init=False)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "target": list(self.target)}


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserveAction(Action):
    piece_id: str
    origin: Square
    kind: Literal["observe"] = field(default="observe", init=False)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin)}


@dataclass(frozen=True, slots=True, kw_only=True)
class MergeAction(Action):
    piece_id: str
    origin: Square
    other_piece_id: str
    kind: Literal["merge"] = field(default="merge", init=False)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "other_piece_id": self.other_piece_id}


@dataclass(frozen=True, slots=True)
class CollapseEvent:
    """A sampled resolution; legacy `resolved_to` is kept for replay fixtures."""

    piece_id: str
    resolved_to: Square | None = None
    cause: CollapseCause | str = "observe"
    ply: int = 0
    owner: Player = 0
    chances: tuple[tuple[Square, Chance], ...] = ()
    sampled: Square | None = None
    probability: Chance = 1.0

    def __post_init__(self) -> None:
        if self.sampled is None and self.resolved_to is not None:
            object.__setattr__(self, "sampled", self.resolved_to)
        elif self.resolved_to is None and self.sampled is not None:
            object.__setattr__(self, "resolved_to", self.sampled)

    def to_json(self) -> dict[str, Any]:
        return {
            "ply": self.ply,
            "piece_id": self.piece_id,
            "owner": self.owner,
            "cause": self.cause,
            "chances": [[list(square), weight] for square, weight in self.chances],
            "sampled": list(self.sampled) if self.sampled is not None else None,
            "probability": self.probability,
        }


@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable game snapshot shared by engines, agents, and replay code."""

    turn: Player
    ply: int
    pieces: tuple[Piece, ...]
    captured: tuple[str, ...] = ()
    info: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    last_event: CollapseEvent | None = None
    history: tuple[Action, ...] = ()

    def piece(self, piece_id: str) -> Piece:
        for piece in self.pieces:
            if piece.piece_id == piece_id:
                return piece
        raise KeyError(f"no piece {piece_id!r} on the board")

    def pieces_of(self, owner: int) -> tuple[Piece, ...]:
        return tuple(piece for piece in self.pieces if piece.owner == owner)

    def spread_pieces(self) -> tuple[Piece, ...]:
        return tuple(piece for piece in self.pieces if piece.is_spread)

    def occupancy(self) -> dict[Square, tuple[Player, Chance]]:
        """Map each possible square to its highest-probability owning piece."""
        table: dict[Square, tuple[Player, Chance]] = {}
        for piece in self.pieces:
            for square, weight in piece.sites:
                current = table.get(square)
                if current is None or weight > current[1]:
                    table[square] = (piece.owner, weight)
        return table

    def certainty(self) -> float:
        if not self.pieces:
            return 0.0
        return sum(max(weight for _, weight in piece.sites) for piece in self.pieces) / len(
            self.pieces
        )

    @property
    def is_terminal(self) -> bool:
        """Compatibility convenience; engines are authoritative for terminality."""
        return False

    def clone(self, **changes: Any) -> GameState:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class GameOutcome:
    """Terminal result; `winner=None` represents a draw."""

    winner: Player | None
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {"winner": self.winner, "reason": self.reason}


Outcome = GameOutcome


@dataclass(frozen=True, slots=True)
class Step:
    """Successor state and any collapse events produced by an action."""

    state: GameState
    events: tuple[CollapseEvent, ...] = ()


Transition = Step


@runtime_checkable
class GameEngine(Protocol):
    """Methods and metadata required by agents, server, and experiment runner."""

    name: str
    level: int
    allow_observe: bool
    max_plies: int
    board_size: int

    def initial_state(self) -> GameState: ...
    def legal_actions(self, state: GameState) -> tuple[Action, ...]: ...
    def apply(self, state: GameState, action: Action) -> Step: ...
    def is_terminal(self, state: GameState) -> bool: ...
    def outcome(self, state: GameState) -> GameOutcome | None: ...
    def render(self, state: GameState) -> dict[str, Any]: ...


def clone_engine(engine: GameEngine, seed: int | None = None) -> GameEngine:
    """Return an isolated engine clone or fail clearly if cloning is unsupported."""
    clone = getattr(engine, "clone", None)
    if not callable(clone):
        raise TypeError(
            f"{type(engine).__name__} does not support clone(); "
            "agents cannot run isolated search against it"
        )
    return clone(seed)


def uncertain_pieces(state: GameState, owner: int | None = None) -> tuple[Piece, ...]:
    pieces = state.pieces if owner is None else state.pieces_of(owner)
    return tuple(piece for piece in pieces if piece.is_spread)


def board_size_of(state: GameState) -> int:
    size = max(
        (max(row, col) + 1 for piece in state.pieces
         for (row, col), _ in piece.sites),
        default=0,
    )
    return size or DEFAULT_BOARD_SIZE


def board_chances(state: GameState, size: int | None = None) -> list[list[float]]:
    extent = size if size is not None else board_size_of(state)
    table = state.occupancy()
    chances: list[list[float]] = []
    for row in range(extent):
        for col in range(extent):
            entry = table.get((row, col))
            chances.append(
                [entry[1] if entry is not None and entry[0] == owner else 0.0
                 for owner in (0, 1)]
            )
    return chances


def describe_state(state: GameState) -> dict[str, Any]:
    return {
        "ply": state.ply,
        "turn": state.turn,
        "pieces": [
            {
                "piece_id": piece.piece_id,
                "owner": piece.owner,
                "sites": [[list(square), weight] for square, weight in piece.sites],
            }
            for piece in state.pieces
        ],
        "captured": list(state.captured),
        "certainty": state.certainty(),
    }


__all__ = [
    "Action", "CaptureAction", "Chance", "CollapseCause", "CollapseEvent",
    "DEFAULT_BOARD_SIZE", "GameEngine", "GameOutcome", "GameState", "MergeAction",
    "MoveAction", "ObserveAction", "Outcome", "Piece", "Player", "RejoinAction",
    "SpreadAction", "Square", "Step", "Transition", "board_chances",
    "board_size_of", "clone_engine", "describe_state", "uncertain_pieces",
]
