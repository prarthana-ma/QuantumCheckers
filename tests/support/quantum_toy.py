"""Minimal quantum-checkers engine fixture for development and testing.

**NOT AUTHORITATIVE.** This is a non-authoritative development/testing engine so the
P3 infrastructure (agents, runner, schema, verification) can be integration-tested
before P5's real engine lands. It implements the :class:`~qcheckers.engine.protocol.GameEngine`
interface and follows the same constructor signature as P1's expected
``DeterministicToyEngine`` so tests can swap seamlessly.

The game: simplified checkers on an N×N board with quantum split/merge/observe
mechanics. Pieces move diagonally forward, capture by jumping, and may split into
superposition over two squares. Observation collapses a spread piece to one square.

Rules are deliberately minimal — just enough to exercise the full infrastructure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

from qcheckers.engine.protocol import (
    Action,
    CaptureAction,
    CollapseEvent,
    GameEngine,
    GameState,
    MergeAction,
    MoveAction,
    ObserveAction,
    Outcome,
    Piece,
    RejoinAction,
    SpreadAction,
    Square,
    Transition,
)


def _move_action(origin, target):
    return MoveAction(piece_id="", origin=origin, target=target)


def _capture_action(origin, target, captured_id, jumped=None):
    return _CaptureAction(origin=origin, target=target, captured_id=captured_id)


@dataclass(frozen=True, slots=True)
class _MoveAction:
    """Internal move action class for isinstance checks in tests."""

    origin: tuple[int, int]
    target: tuple[int, int]
    piece_id: str = ""
    kind: str = "move"

    def __post_init__(self) -> None:
        if not isinstance(self.origin, tuple) or len(self.origin) != 2:
            raise ValueError("origin must be a 2-tuple")
        if not isinstance(self.target, tuple) or len(self.target) != 2:
            raise ValueError("target must be a 2-tuple")


@dataclass(frozen=True, slots=True)
class _CaptureAction:
    """Internal capture action class for isinstance checks in tests."""

    origin: tuple[int, int]
    target: tuple[int, int]
    captured_id: str
    kind: str = "capture"

    def __post_init__(self) -> None:
        if not isinstance(self.origin, tuple) or len(self.origin) != 2:
            raise ValueError("origin must be a 2-tuple")
        if not isinstance(self.target, tuple) or len(self.target) != 2:
            raise ValueError("target must be a 2-tuple")
        if not isinstance(self.captured_id, str):
            raise ValueError("captured_id must be a string")


@dataclass(frozen=True, slots=True)
class _RejoinAction:
    """Internal rejoin action class for isinstance checks in tests."""

    origin: tuple[int, int]
    target: tuple[int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.origin, tuple) or len(self.origin) != 2:
            raise ValueError("origin must be a 2-tuple")
        if not isinstance(self.target, tuple) or len(self.target) != 2:
            raise ValueError("target must be a 2-tuple")


def _rejoin_action(origin, target):
    return RejoinAction(piece_id="", origin=origin, target=target)


def _merge_action(origin, target, absorbed_id):
    return MergeAction(piece_id="", origin=origin, other_piece_id=absorbed_id)


class QuantumToyEngine(GameEngine):
    """Deterministic-when-seeded quantum checkers engine for testing.

    Parameters
    ----------
    seed:
        Engine RNG seed for collapse sampling.
    level:
        Engine behavior level (0=classical only, 1=+split, 2=+observe). Matches
        P1's ``DeterministicToyEngine`` constructor signature.
    allow_observe:
        When True, Observe actions are legal.
    board_size:
        Board edge length (minimum 4).
    max_plies:
        Ply cap; reaching it ends the game as a draw.
    """

    def __init__(
        self,
        *,
        seed: int = 0,
        level: int = 2,
        allow_observe: bool = True,
        board_size: int = 4,
        max_plies: int = 120,
    ) -> None:
        if board_size < 4:
            raise ValueError(f"board_size must be >= 4, got {board_size}")
        if level not in (0, 1, 2):
            raise ValueError(f"level must be 0, 1 or 2, got {level}")
        if max_plies < 1:
            raise ValueError(f"max_plies must be >= 1, got {max_plies}")
        self.board_size = board_size
        self.level = level
        self.allow_observe = allow_observe
        self.max_plies = max_plies
        self._seed = seed
        self._rng = random.Random(seed)

    def clone(self, seed: int | None = None) -> QuantumToyEngine:
        """Return an independent copy with reset RNG."""
        return QuantumToyEngine(
            seed=self._seed if seed is None else seed,
            level=self.level,
            allow_observe=self.allow_observe,
            board_size=self.board_size,
            max_plies=self.max_plies,
        )

    def initial_state(self) -> GameState:
        pieces: list[Piece] = []
        dark_squares = [
            (r, c)
            for r in range(self.board_size)
            for c in range(self.board_size)
            if (r + c) % 2 == 1
        ]
        # One back row per player so pieces always have a clear path forward.
        p0_squares = [sq for sq in dark_squares if sq[0] == self.board_size - 1]
        p1_squares = [sq for sq in dark_squares if sq[0] == 0]
        for i, sq in enumerate(p0_squares):
            pieces.append(Piece(f"p0-{i}", 0, ((sq, 1.0),)))
        for i, sq in enumerate(p1_squares):
            pieces.append(Piece(f"p1-{i}", 1, ((sq, 1.0),)))
        return GameState(turn=0, ply=0, pieces=tuple(pieces), captured=())

    def legal_actions(self, state: GameState) -> Sequence[Action]:
        if self.outcome(state) is not None:
            return []
        return self._generate_actions(state)

    def _generate_actions(self, state: GameState) -> list[Action]:
        """Generate legal actions without terminal-state checking (breaks mutual recursion)."""
        actions: list[Action] = []
        own = state.pieces_of(state.turn)
        for piece in own:
            for square, _ in piece.sites:
                # Forward moves
                dr = -1 if state.turn == 0 else 1
                for dc in (-1, 1):
                    target = (square[0] + dr, square[1] + dc)
                    if self._in_bounds(target) and not self._occupied(target, state):
                        actions.append(_move_action(square, target))
                # Captures
                for dc in (-1, 1):
                    mid = (square[0] + dr, square[1] + dc)
                    land = (square[0] + 2 * dr, square[1] + 2 * dc)
                    if (
                        self._in_bounds(land)
                        and self._occupied_by(mid, state, 1 - state.turn)
                        and not self._occupied(land, state)
                    ):
                        captured = self._piece_at(mid, state)
                        if captured:
                            actions.append(
                                _capture_action(square, land, captured.piece_id, jumped=mid)
                            )
        # Split actions (level >= 1)
        if self.level >= 1:
            for piece in own:
                if not piece.is_spread:
                    for square, _ in piece.sites:
                        dr = -1 if state.turn == 0 else 1
                        for dc in (-1, 1):
                            target = (square[0] + dr, square[1] + dc)
                            if self._in_bounds(target) and not self._occupied(target, state):
                                actions.append(
                                    SpreadAction(piece_id="", origin=square, sites=((target, 1.0),))
                                )
        # Merge actions (level >= 1): two own pieces on adjacent squares
        if self.level >= 1:
            own_list = list(own)
            for i, a in enumerate(own_list):
                for b in own_list[i + 1 :]:
                    for sq_a, _ in a.sites:
                        for sq_b, _ in b.sites:
                            if abs(sq_a[0] - sq_b[0]) + abs(sq_a[1] - sq_b[1]) == 1:
                                actions.append(
                                    _merge_action(sq_a, sq_b, b.piece_id)
                                )
        # Observe actions (level >= 2, allow_observe)
        if self.level >= 2 and self.allow_observe:
            for piece in own:
                if piece.is_spread:
                    actions.append(
                        ObserveAction(piece_id=piece.piece_id, origin=piece.sites[0][0])
                    )
        # Rejoin action (re-form a spread piece) — simplified: always available when spread
        if self.level >= 1:
            for piece in own:
                if piece.is_spread:
                    actions.append(
                        _rejoin_action(piece.sites[0][0], piece.sites[1][0])
                    )
        # Deduplicate while preserving order
        seen: set[tuple] = set()
        unique: list[Action] = []
        for a in actions:
            key = (a.kind, a.origin, getattr(a, "target", ""), getattr(a, "piece_id", ""),
                   getattr(a, "captured_id", ""), getattr(a, "absorbed_id", ""))
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique

    def apply(self, state: GameState, action: Action) -> Transition:
        if self.is_terminal(state):
            raise ValueError("cannot apply action to terminal state")
        legal = self.legal_actions(state)
        # Build a set of full action identities for precise matching
        legal_keys = set()
        for a in legal:
            key = (
                a.kind, a.origin, getattr(a, "target", ""),
                getattr(a, "piece_id", ""),
                getattr(a, "captured_id", ""),
                getattr(a, "absorbed_id", ""),
            )
            legal_keys.add(key)
        action_key = (
            action.kind, action.origin, getattr(action, "target", ""),
            getattr(action, "piece_id", ""),
            getattr(action, "captured_id", ""),
            getattr(action, "absorbed_id", ""),
        )
        if action_key not in legal_keys:
            raise ValueError(f"illegal action {action!r} for state at ply {state.ply}")

        pieces = list(state.pieces)
        captured = list(state.captured)
        events: list[CollapseEvent] = []
        next_turn = 1 - state.turn

        if action.kind == "move":
            pieces = self._relocate(pieces, action.origin, action.target)
        elif action.kind == "capture":
            cap_id = getattr(action, "captured_id", "")
            pieces = [p for p in pieces if p.piece_id != cap_id]
            if cap_id:
                captured.append(cap_id)
            pieces = self._relocate(pieces, action.origin, action.target)
        elif action.kind == "split":
            piece = self._find_at(pieces, action.origin)
            if piece:
                w = 0.5
                new_sites = ((action.origin, w), (action.target, 1.0 - w))
                idx = pieces.index(piece)
                pieces[idx] = Piece(piece.piece_id, piece.owner, new_sites)
        elif action.kind == "merge":
            absorber = self._find_at(pieces, action.origin)
            absorbed_id = getattr(action, "absorbed_id", "")
            absorbed = next((p for p in pieces if p.piece_id == absorbed_id), None)
            if absorber and absorbed:
                # Merge: absorber takes absorbed's best square with combined weight
                all_sites = tuple(absorber.sites) + tuple(absorbed.sites)
                # Keep top-2 squares by weight, renormalized
                sorted_sites = sorted(all_sites, key=lambda s: -s[1])[: 2]
                total = sum(w for _, w in sorted_sites)
                norm = tuple((sq, w / total) for sq, w in sorted_sites)
                idx = pieces.index(absorber)
                pieces[idx] = Piece(absorber.piece_id, absorber.owner, norm)
                pieces = [p for p in pieces if p.piece_id != absorbed_id]
                captured.append(absorbed_id)
        elif action.kind == "observe":
            pid = getattr(action, "piece_id", "")
            piece = next((p for p in pieces if p.piece_id == pid), None)
            if piece and piece.is_spread:
                # Engine's chance rule: sample a site weighted by occupancy
                sites = list(piece.sites)
                weights = [w for _, w in sites]
                chosen = self._rng.choices(sites, weights=weights, k=1)[0][0]
                idx = pieces.index(piece)
                pieces[idx] = Piece(piece.piece_id, piece.owner, ((chosen, 1.0),))
                prob = next(w for sq, w in piece.sites if sq == chosen)
                events.append(CollapseEvent(
                    ply=state.ply, piece_id=pid, owner=piece.owner,
                    cause="observe", chances=tuple(piece.sites),
                    sampled=chosen, probability=prob
                ))
        elif action.kind == "rejoin":
            # Find the spread piece at the action's origin square (or first spread piece if origin is None)
            pid_piece = None
            for p in pieces:
                if p.is_spread and p.owner == state.turn:
                    if action.origin is None or action.origin in p.squares:
                        pid_piece = p
                        break
            if pid_piece:
                # Collapse to most likely square
                best = max(pid_piece.sites, key=lambda s: s[1])[0]
                idx = pieces.index(pid_piece)
                pieces[idx] = Piece(pid_piece.piece_id, pid_piece.owner, ((best, 1.0),))
                prob = next(w for sq, w in pid_piece.sites if sq == best)
                events.append(CollapseEvent(
                    ply=state.ply, piece_id=pid_piece.piece_id, owner=pid_piece.owner,
                    cause="rejoin", chances=tuple(pid_piece.sites),
                    sampled=best, probability=prob
                ))

        new_state = GameState(
            turn=next_turn,
            ply=state.ply + 1,
            pieces=tuple(pieces),
            captured=tuple(captured),
        )
        return Transition(state=new_state, events=tuple(events))

    def is_terminal(self, state: GameState) -> bool:
        return self.outcome(state) is not None

    def outcome(self, state: GameState) -> Outcome | None:
        if state.ply >= self.max_plies:
            return Outcome(winner=None, reason="ply_limit")
        p0_pieces = state.pieces_of(0)
        p1_pieces = state.pieces_of(1)
        if not p1_pieces:
            return Outcome(winner=0, reason="no_pieces")
        if not p0_pieces:
            return Outcome(winner=1, reason="no_pieces")
        # Check if current player has any legal actions
        if not self._generate_actions(state):
            return Outcome(winner=1 - state.turn, reason="no_legal_moves")
        return None

    # -- helpers ---------------------------------------------------------

    def _in_bounds(self, sq: Square) -> bool:
        return 0 <= sq[0] < self.board_size and 0 <= sq[1] < self.board_size

    def _occupied(self, sq: Square, state: GameState) -> bool:
        return any(sq in p.squares for p in state.pieces)

    def _occupied_by(self, sq: Square, state: GameState, owner: int) -> bool:
        return any(sq in p.squares for p in state.pieces_of(owner))

    def _piece_at(self, sq: Square, state: GameState) -> Piece | None:
        for p in state.pieces:
            if sq in p.squares:
                return p
        return None

    def _find_at(self, pieces: list[Piece], sq: Square) -> Piece | None:
        for p in pieces:
            if sq in p.squares:
                return p
        return None

    def _relocate(
        self, pieces: list[Piece], origin: Square, target: Square
    ) -> list[Piece]:
        for i, p in enumerate(pieces):
            if origin in p.squares:
                new_sites = tuple(
                    (target, w) if sq == origin else (sq, w) for sq, w in p.sites
                )
                pieces[i] = Piece(p.piece_id, p.owner, new_sites)
                break
        return pieces


__all__ = [
    "QuantumToyEngine",
    "CollapseEvent",
]
