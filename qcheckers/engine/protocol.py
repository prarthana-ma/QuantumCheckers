"""Engine protocol — the shared contract between agents, runner, and engines.

This module contains ONLY interfaces and value types. It holds no game rules and no
authoritative engine logic. The authoritative engine is owned by **P5 (Prarthana)**,
which implements :class:`GameEngine` against these definitions.

Existing agents (P1) and the experiment runner (P3) already import from this module,
so the names and signatures here are part of the project's integration surface.

Conventions
-----------
* All actions are immutable value objects with a ``kind`` string.
* States are treated as immutable snapshots; ``engine.apply`` returns a new state.
* Outcomes use ``winner is None`` for a draw and ``winner in (0, 1)`` for a win.
* Randomness is owned by the engine; agents never call the global ``random`` module
  for engine transitions (they may use an injected RNG for their own search).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence, runtime_checkable

#: A board square, e.g. ``(row, col)``. Engages no quantum semantics by itself.
Square = tuple[int, int]


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    """Base class for every engine action.

    Subclasses add their own fields. ``kind`` is a stable string identifier used by
    agents to classify actions (``"move"``, ``"capture"``, ``"split"``, ``"rejoin"``,
    ``"observe"``). ``origin`` and ``target`` are present on positional actions and
    ``None`` otherwise; use ``getattr(action, "origin", None)`` when unsure.
    """

    kind: str
    origin: Square | None = None
    target: Square | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("Action.kind must be a non-empty string")


@dataclass(frozen=True)
class ObserveAction(Action):
    """Voluntary measurement: resolve one of the agent's own spread pieces.

    Costs the turn exactly like any other action. Only legal when the engine was
    built with ``allow_observe=True`` and the named piece is genuinely spread.
    """

    piece_id: str = ""
    kind: str = field(default="observe", init=False)


@dataclass(frozen=True)
class SpreadAction(Action):
    """Split a piece so it occupies two squares with complementary chances."""

    kind: str = field(default="split", init=False)


# ---------------------------------------------------------------------------
# Pieces and state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """A single checkers piece, possibly spread over several squares.

    ``sites`` pairs each occupied ``Square`` with its occupancy weight in ``(0, 1]``.
    Weights across a piece's sites sum to 1. A piece with one site at weight 1 is
    *classical* (not spread). ``chance_at`` returns the weight for a square, or 0.0
    if the piece is not on that square.
    """

    piece_id: str
    owner: int
    sites: tuple[tuple[Square, float], ...]

    def __post_init__(self) -> None:
        if not self.piece_id:
            raise ValueError("Piece.piece_id must be non-empty")
        if self.owner not in (0, 1):
            raise ValueError(f"Piece.owner must be 0 or 1, got {self.owner!r}")
        if not self.sites:
            raise ValueError(f"Piece {self.piece_id!r} must occupy at least one square")
        total = sum(w for _, w in self.sites)
        if not 0.99 <= total <= 1.01:
            raise ValueError(
                f"Piece {self.piece_id!r} site weights sum to {total!r}, expected 1.0"
            )

    @property
    def is_spread(self) -> bool:
        """True when the piece occupies more than one square."""
        return len(self.sites) > 1

    @property
    def squares(self) -> tuple[Square, ...]:
        """All squares this piece occupies, in declared order."""
        return tuple(sq for sq, _ in self.sites)

    def chance_at(self, square: Square) -> float:
        """Occupancy weight of this piece on ``square`` (0.0 if absent)."""
        for site, weight in self.sites:
            if site == square:
                return weight
        return 0.0


@dataclass(frozen=True)
class GameState:
    """An immutable snapshot of the game at one ply.

    ``turn`` is the player to move (0 or 1). ``ply`` counts completed plies from the
    initial position. ``captured`` lists piece ids removed from the board. Engines may
    attach additional read-only metadata via ``info``; it never affects transitions.
    """

    turn: int
    ply: int
    pieces: tuple[Piece, ...]
    captured: tuple[str, ...] = ()
    info: dict[str, Any] = field(default_factory=dict, compare=False)

    def piece(self, piece_id: str) -> Piece:
        """Return the piece with ``piece_id``; raises ``KeyError`` if absent."""
        for piece in self.pieces:
            if piece.piece_id == piece_id:
                return piece
        raise KeyError(f"no piece {piece_id!r} on the board")

    def pieces_of(self, owner: int) -> tuple[Piece, ...]:
        """All pieces owned by ``owner``."""
        return tuple(p for p in self.pieces if p.owner == owner)

    @property
    def is_terminal(self) -> bool:
        """Convenience: engines define terminality via ``outcome``; this is a shortcut."""
        return False  # engines override via is_terminal()


@dataclass(frozen=True)
class Outcome:
    """Terminal result. ``winner is None`` means a draw."""

    winner: int | None
    reason: str = ""


@dataclass(frozen=True)
class Transition:
    """Result of applying an action: the successor state plus logged events."""

    state: GameState
    events: tuple[Any, ...] = ()


@dataclass(frozen=True)
class CollapseEvent:
    """Logged when a spread piece is resolved to a single square."""

    piece_id: str
    resolved_to: Square
    cause: str  # e.g. "observe", "capture", "measurement"


# ---------------------------------------------------------------------------
# Engine interface
# ---------------------------------------------------------------------------


class GameEngine(ABC):
    """Authoritative game engine. P5 owns the concrete implementation.

    Agents and the runner must only use these methods — never reimplement rules here.
    """

    #: Board edge length (engines must expose this for heuristic evaluations).
    board_size: int

    @abstractmethod
    def initial_state(self) -> GameState:
        """The starting position for a fresh game."""

    @abstractmethod
    def legal_actions(self, state: GameState) -> Sequence[Action]:
        """Legal actions for ``state.turn``. Empty sequence means no moves available."""

    @abstractmethod
    def apply(self, state: GameState, action: Action) -> Transition:
        """Apply ``action``; raises ``ValueError`` for illegal actions."""

    @abstractmethod
    def is_terminal(self, state: GameState) -> bool:
        """True when the game has ended."""

    @abstractmethod
    def outcome(self, state: GameState) -> Outcome | None:
        """The terminal outcome, or ``None`` if the game is not over."""


def clone_engine(engine: GameEngine, seed: int | None = None) -> GameEngine:
    """Clone ``engine`` for isolated search, using its own ``clone`` method.

    Raises ``TypeError`` if the engine does not support cloning. This is the only
    sanctioned way agents obtain a simulation sandbox; it keeps randomness ownership
    inside the engine.
    """
    clone = getattr(engine, "clone", None)
    if clone is None:
        raise TypeError(
            f"{type(engine).__name__} does not support clone(); "
            "agents cannot run isolated search against it"
        )
    return clone(seed)


__all__ = [
    "Action",
    "CollapseEvent",
    "GameEngine",
    "GameState",
    "ObserveAction",
    "Outcome",
    "Piece",
    "SpreadAction",
    "Square",
    "Transition",
    "clone_engine",
]
