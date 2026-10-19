"""Core game protocol and value types for the Quantum Checkers study.

Owner: **Person A -- rules and engine guardian**. Person A owns this file and
``toy.py``. Per the team plan, no one else may change core rule
logic or these types without Person A's agreement.

Everything in this module is stdlib-only and side-effect free: no numpy, no global
``random``. An engine instance owns its own seeded RNG (see
:class:`qcheckers.engine.toy.DeterministicToyEngine`), so two engines constructed with
the same seed produce the same game.

Vocabulary note (deliberately careful, per the project brief): "spread", "chance",
"collapse" and "rejoin" describe a *probability-carrying* board model. Whether the
published game uses true amplitudes and phases, or classical probabilities only, is
still **UNVERIFIED** until the paper and the upstream code are read (Gate 5). The toy
engine implements the probability-only reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence, runtime_checkable

# ---------------------------------------------------------------------------
# Board value types
# ---------------------------------------------------------------------------

#: A square is a ``(row, col)`` pair, both zero-based integers.
Square = tuple[int, int]

#: Player identifiers. Player ``0`` moves first and toward decreasing rows.
Player = Literal[0, 1]

#: Chance weights attached to a square. Weights of one piece always sum to 1.0.
Chance = float


@dataclass(frozen=True, slots=True)
class Piece:
    """One piece and the distribution of squares it currently occupies.

    A *certain* piece occupies exactly one square with chance ``1.0``. A *spread*
    piece occupies two or three squares with weights that sum to ``1.0``. The brief
    calls this "superposition"; here it is only a probability distribution.

    ``coherence`` is the **game-only** Level-4 counter: how many unmeasured turns a
    spread piece has left before it collapses on its own. It is ``None`` for certain
    pieces and for every game that does not enable decoherence, so the research paths
    never see it (see the engine's ``decoherence`` flag).
    """

    piece_id: str
    owner: int
    sites: tuple[tuple[Square, Chance], ...]
    coherence: int | None = None

    def __post_init__(self) -> None:
        if not self.sites:
            raise ValueError(f"piece {self.piece_id!r} must occupy at least one square")
        total = sum(weight for _, weight in self.sites)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"piece {self.piece_id!r} chance weights must sum to 1.0, got {total!r}"
            )
        squares = [square for square, _ in self.sites]
        if len(set(squares)) != len(squares):
            raise ValueError(f"piece {self.piece_id!r} lists a square twice: {squares}")

    @property
    def is_spread(self) -> bool:
        """True when the piece occupies more than one square."""
        return len(self.sites) > 1

    @property
    def squares(self) -> tuple[Square, ...]:
        return tuple(square for square, _ in self.sites)

    def chance_at(self, square: Square) -> Chance:
        """Chance weight of ``square`` for this piece (0.0 when absent)."""
        for candidate, weight in self.sites:
            if candidate == square:
                return weight
        return 0.0

    def with_sites(
        self, sites: Sequence[tuple[Square, Chance]], coherence: int | None = None
    ) -> "Piece":
        """Return a copy of this piece occupying ``sites``.

        ``coherence`` defaults to ``None`` because changing a piece's sites produces a
        fresh distribution: the engine sets the counter explicitly when decoherence is
        on, and leaves it ``None`` everywhere else.
        """
        return Piece(
            self.piece_id,
            self.owner,
            tuple((s, float(w)) for s, w in sites),
            coherence,
        )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MoveAction:
    """Ordinary checkers step: one square diagonally forward."""

    piece_id: str
    origin: Square
    target: Square
    kind: Literal["move"] = "move"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
            "target": list(self.target),
        }


@dataclass(frozen=True, slots=True)
class CaptureAction:
    """Jump over an adjacent opponent piece onto the empty square beyond."""

    piece_id: str
    origin: Square
    jumped: Square
    target: Square
    kind: Literal["capture"] = "capture"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
            "jumped": list(self.jumped),
            "target": list(self.target),
        }


@dataclass(frozen=True, slots=True)
class SpreadAction:
    """Quantum-like move: give a piece a *distribution* over candidate squares.

    Available from level 1 onward. This is the reproduction-side mechanic; the exact
    published rule is **UNVERIFIED** (Gate 5).
    """

    piece_id: str
    origin: Square
    sites: tuple[tuple[Square, Chance], ...]
    kind: Literal["spread"] = "spread"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
            "sites": [[list(s), w] for s, w in self.sites],
        }


@dataclass(frozen=True, slots=True)
class RejoinAction:
    """Collapse a spread piece onto one of its own candidate squares.

    Available from level 2 onward. Costs the turn; the chosen square is always
    taken, so this is a *choice* rather than a sample. This distinction is the whole
    point of the extension study.
    """

    piece_id: str
    origin: Square
    target: Square
    kind: Literal["rejoin"] = "rejoin"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
            "target": list(self.target),
        }


@dataclass(frozen=True, slots=True)
class ObserveAction:
    """Person C's candidate voluntary-measurement action.

    The engine samples the named piece's distribution using the engine's chance rule
    and turns it into a certain piece. Whether this costs a turn is a design decision
    recorded here explicitly: **it costs a turn**, matching the brief's requirement to
    state the cost. Legality is decided by the engine (``allow_observe`` flag), the
    policy is owned by :mod:`qcheckers.agents.observe_agent`.

    **NOVELTY PENDING GATE 5** -- must not be described as novel until the full paper
    and follow-up literature are read.
    """

    piece_id: str
    origin: Square
    kind: Literal["observe"] = "observe"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
        }


@dataclass(frozen=True, slots=True)
class MergeAction:
    """Level 3: combine two of your own pieces into one probability-carrying piece.

    The inverse of a split: merging two *certain* pieces yields a piece spread 50/50
    over their two squares. Available only from level 3 onward. Phase here is the
    game's *turn phase* only -- interference and quantum phase are **not** modelled by
    the toy engine (brief section 16; the viewer says so plainly).
    """

    piece_id: str
    origin: Square
    other_piece_id: str
    kind: Literal["merge"] = "merge"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "piece_id": self.piece_id,
            "origin": list(self.origin),
            "other_piece_id": self.other_piece_id,
        }


Action = (
    MoveAction | CaptureAction | SpreadAction | RejoinAction | ObserveAction | MergeAction
)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

#: Why a distribution was resolved. ``decoherence`` is the game-only Level-4 expiry.
CollapseCause = Literal["observe", "capture", "rejoin", "join", "decoherence"]

#: Why a game ended.
TerminationReason = Literal["no_pieces", "no_legal_moves", "ply_limit"]


@dataclass(frozen=True, slots=True)
class CollapseEvent:
    """One resolution of a spread piece into a single definite square.

    ``chances`` is the pre-collapse distribution and ``probability`` is the chance of
    the sampled square, so the log is enough to recompute every metric later without
    re-running the game.
    """

    ply: int
    piece_id: str
    owner: int
    cause: CollapseCause
    chances: tuple[tuple[Square, Chance], ...]
    sampled: Square
    probability: Chance

    def to_json(self) -> dict[str, Any]:
        return {
            "ply": self.ply,
            "piece_id": self.piece_id,
            "owner": self.owner,
            "cause": self.cause,
            "chances": [[list(s), w] for s, w in self.chances],
            "sampled": list(self.sampled),
            "probability": self.probability,
        }


# ---------------------------------------------------------------------------
# State and outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable game state.

    Immutability matters: the runner hashes states for determinism tests, and agents
    must not be able to mutate history by holding a reference.
    """

    turn: int
    ply: int
    pieces: tuple[Piece, ...]
    captured: tuple[str, ...] = ()
    last_event: CollapseEvent | None = None
    history: tuple[Action, ...] = ()

    def piece(self, piece_id: str) -> Piece:
        for candidate in self.pieces:
            if candidate.piece_id == piece_id:
                return candidate
        raise KeyError(piece_id)

    def pieces_of(self, owner: int) -> tuple[Piece, ...]:
        return tuple(p for p in self.pieces if p.owner == owner)

    def occupancy(self) -> dict[Square, tuple[int, Chance]]:
        """Map every square to ``(owner, chance)`` for the most likely owner.

        When two pieces of different owners claim a square, the higher chance wins;
        exact ties go to the lower owner index. Ties are possible only in states the
        engine would not produce, but the viewer must not crash on them.
        """
        table: dict[Square, tuple[int, Chance]] = {}
        for piece in self.pieces:
            for square, weight in piece.sites:
                current = table.get(square)
                if current is None or weight > current[1]:
                    table[square] = (piece.owner, weight)
        return table

    def spread_pieces(self) -> tuple[Piece, ...]:
        return tuple(p for p in self.pieces if p.is_spread)

    def certainty(self) -> float:
        """Mean chance weight over all pieces -- a crude "how fuzzy is the board"."""
        if not self.pieces:
            return 0.0
        return sum(max(weight for _, weight in p.sites) for p in self.pieces) / len(
            self.pieces
        )

    def clone(self, **changes: Any) -> "GameState":
        data: dict[str, Any] = {
            "turn": self.turn,
            "ply": self.ply,
            "pieces": self.pieces,
            "captured": self.captured,
            "last_event": self.last_event,
            "history": self.history,
        }
        data.update(changes)
        return GameState(**data)


@dataclass(frozen=True, slots=True)
class GameOutcome:
    """Terminal result: the winning player, or ``None`` for a draw."""

    winner: int | None
    reason: TerminationReason

    def to_json(self) -> dict[str, Any]:
        return {"winner": self.winner, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class Step:
    """Result of applying one action: the next state plus the events it produced."""

    state: GameState
    events: tuple[CollapseEvent, ...] = ()


# Backwards-compatible aliases: fixtures and modules written before the
# GameOutcome/Step rename keep importing the old names.
Outcome = GameOutcome
Transition = Step


# ---------------------------------------------------------------------------
# Engine protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class GameEngine(Protocol):
    """Everything the runner, the agents and the viewer need from a game engine.

    Contract:

    * ``initial_state()`` must be a pure function of the engine's configuration.
    * ``legal_actions(state)`` must be deterministic and return actions in a stable
      order, so that a seeded game is byte-reproducible.
    * ``apply(state, action)`` must reject illegal actions -- the runner and the
      agents rely on that, and it is what Person A's legality tests check.
    * ``allow_observe`` is False until Person C's Observe action is wired through
      after Gate 6.
    """

    name: str
    level: int
    allow_observe: bool
    max_plies: int

    def initial_state(self) -> GameState: ...

    def legal_actions(self, state: GameState) -> tuple[Action, ...]: ...

    def apply(self, state: GameState, action: Action) -> Step: ...

    def is_terminal(self, state: GameState) -> bool: ...

    def outcome(self, state: GameState) -> GameOutcome | None: ...

    def render(self, state: GameState) -> dict[str, Any]:
        """JSON-ready board description for the replay viewer (Person E)."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def clone_engine(engine: GameEngine, seed: int) -> GameEngine:
    """Return an independent engine for search and simulation.

    A rollout applies actions, and applying an action that resolves a distribution
    (a voluntary Observe, or a Level-4 decoherence expiry) samples the engine's RNG.
    Doing that on the engine that is playing the real game would advance its RNG and
    change the game the agent is only *thinking* about. Search agents therefore run on
    a clone.

    ``GameEngine`` does not require a clone, so an engine that lacks one is returned
    unchanged: the search still works, but it shares RNG state with the live game. The
    toy engine provides ``clone``, so the tests and the shipped agents are isolated.
    """
    clone = getattr(engine, "clone", None)
    if callable(clone):
        return clone(int(seed))
    return engine


def uncertain_pieces(state: GameState, owner: int | None = None) -> tuple[Piece, ...]:
    """Pieces occupying more than one square, optionally filtered by owner.

    The cheap predicate Person C's Observe policy and Person D's metrics both need.
    """
    pieces = state.pieces if owner is None else state.pieces_of(owner)
    return tuple(piece for piece in pieces if piece.is_spread)


def board_size_of(state: GameState) -> int:
    """Board size implied by a state: one past the largest coordinate, else 4.

    :class:`GameState` carries no engine reference on purpose, so this is an
    inference. Engines keep :attr:`GameEngine.board_size` authoritative and pass it
    to the viewer explicitly; this helper exists for convenience and tests.
    """
    size = 0
    for piece in state.pieces:
        for square, _ in piece.sites:
            size = max(size, square[0] + 1, square[1] + 1)
    return size or DEFAULT_BOARD_SIZE


#: Fallback board size when a state has no pieces at all.
DEFAULT_BOARD_SIZE = 4


def board_chances(state: GameState, size: int | None = None) -> list[list[float]]:
    """Flattened occupancy chances for a compact per-square display.

    Layout is one ``[owner_0_chance, owner_1_chance]`` pair per square in row-major
    order. Pass ``size`` to use the engine's real board size instead of the inferred
    one.
    """
    extent = size if size is not None else board_size_of(state)
    table = state.occupancy()
    chances: list[list[float]] = []
    for row in range(extent):
        for col in range(extent):
            pair = [0.0, 0.0]
            entry = table.get((row, col))
            if entry is not None:
                pair[entry[0]] = entry[1]
            chances.append(pair)
    return chances


def describe_state(state: GameState) -> dict[str, Any]:
    """JSON-ready state summary, shared by the runner log and the replay viewer."""
    return {
        "ply": state.ply,
        "turn": state.turn,
        "pieces": [
            {
                "piece_id": p.piece_id,
                "owner": p.owner,
                "sites": [[list(s), w] for s, w in p.sites],
            }
            for p in state.pieces
        ],
        "captured": list(state.captured),
        "certainty": state.certainty(),
    }