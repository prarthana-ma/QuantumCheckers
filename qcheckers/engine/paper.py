"""Paper-based quantum checkers engine.

This module is intentionally separate from :mod:`qcheckers.engine.toy`: paper-based
states retain complex amplitudes over complete labelled board configurations.  The
state is sparse, but it is not a probability-only approximation.  A configurable
branch cap refuses an operation before returning a partial state.

The paper specifies the split operator's source column, but not a complete matrix for
all basis states.  We complete that column to a unitary with a simple orthonormal
extension (documented in :data:`_SPLIT_U`); merge applies its adjoint.  This makes the
published split amplitudes exact and gives merge a norm-preserving, interference-
sensitive definition while making the otherwise-unspecified columns explicit.

Promotion is a deterministic change in the visible piece type, which can identify
previously orthogonal man and king basis states.  We retain the old type in a private
which-path ancilla entry when a man is promoted.  This is a unitary dilation of the
classical type update: the ancilla has no board square, is never rendered, and remains
part of the joint state so amplitudes from distinct promotion paths cannot be merged.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Sequence

from qcheckers.engine.protocol import (
    CollapseEvent,
    GameOutcome,
    Square,
    Step,
)

Complex = complex
Configuration = tuple[tuple[str, Square | None, bool], ...]
Sampler = Callable[[tuple[tuple[Square, float], ...]], tuple[Square, float]]
_ANCILLA_PREFIX = "@promotion:"

_A = (1 + 1j) / 2
_B = (1 - 1j) / 2
# Rows and columns are ordered source, target-a, target-b.  The first column is
# exactly the Appendix's |source> -> a|target-a> + b|target-b>.  The remaining two
# columns are an orthonormal completion, selected explicitly because the paper gives
# only the source column. Merge uses the Hermitian adjoint of this matrix.
_SPLIT_U: tuple[tuple[Complex, ...], ...] = (
    (0j, 1 + 0j, 0j),
    (_A, 0j, -_B.conjugate()),
    (_B, 0j, _A.conjugate()),
)


class PaperRuleError(ValueError):
    """A requested paper-engine operation is illegal or cannot be resolved."""


class BranchLimitError(PaperRuleError):
    """The exact state would exceed the configured sparse-branch cap."""


@dataclass(frozen=True, slots=True)
class PaperMoveAction:
    piece_id: str
    origin: Square
    target: Square
    kind: str = "move"

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "target": list(self.target)}


@dataclass(frozen=True, slots=True)
class PaperCaptureAction:
    piece_id: str
    origin: Square
    jumped: Square
    target: Square
    kind: str = "capture"

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "jumped": list(self.jumped),
                "target": list(self.target)}


@dataclass(frozen=True, slots=True)
class PaperSplitAction:
    piece_id: str
    origin: Square
    targets: tuple[Square, Square]
    kind: str = "spread"

    @property
    def sites(self) -> tuple[tuple[Square, float], ...]:
        """UI preview marginal for a fresh split (the source is emptied)."""
        return tuple(sorted(((self.targets[0], 0.5), (self.targets[1], 0.5))))

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "targets": [list(s) for s in self.targets],
                "sites": [[list(s), p] for s, p in self.sites]}


@dataclass(frozen=True, slots=True)
class PaperMergeAction:
    piece_id: str
    origin: Square
    other_origin: Square
    target: Square
    kind: str = "merge"

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin), "other_origin": list(self.other_origin),
                "target": list(self.target)}


@dataclass(frozen=True, slots=True)
class PaperObserveAction:
    piece_id: str
    origin: Square
    kind: str = "observe"

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "piece_id": self.piece_id,
                "origin": list(self.origin)}


PaperAction = PaperMoveAction | PaperCaptureAction | PaperSplitAction | PaperMergeAction | PaperObserveAction


@dataclass(frozen=True, slots=True)
class PaperPiece:
    piece_id: str
    owner: int
    sites: tuple[tuple[Square, float], ...]
    king_sites: tuple[tuple[Square, float], ...] = ()
    survival_probability: float = 1.0

    @property
    def squares(self) -> tuple[Square, ...]:
        return tuple(square for square, _ in self.sites)

    @property
    def is_spread(self) -> bool:
        return self.survival_probability > 1e-9 and (
            len(self.sites) > 1 or self.survival_probability < 1 - 1e-9
        )

    @property
    def king_probability(self) -> float:
        return sum(probability for _, probability in self.king_sites)

    @property
    def is_king(self) -> bool:
        return self.survival_probability > 0 and self.king_probability >= self.survival_probability - 1e-9

    def chance_at(self, square: Square) -> float:
        return next((probability for candidate, probability in self.sites if candidate == square), 0.0)

    def king_chance_at(self, square: Square) -> float:
        return next((probability for candidate, probability in self.king_sites if candidate == square), 0.0)


@dataclass(frozen=True, slots=True)
class PaperState:
    turn: int
    ply: int
    pieces: tuple[PaperPiece, ...]
    roster: tuple[tuple[str, int], ...]
    amplitudes: tuple[tuple[Configuration, Complex], ...]
    captured: tuple[str, ...] = ()
    last_event: CollapseEvent | None = None
    history: tuple[PaperAction, ...] = ()
    continuation_piece: str | None = None
    quiet_moves: int = 0
    chain_captured: bool = False
    coherence: tuple[tuple[str, int], ...] = ()

    @property
    def branches(self) -> tuple[tuple[Configuration, Complex], ...]:
        return self.amplitudes

    def piece(self, piece_id: str) -> PaperPiece:
        for piece in self.pieces:
            if piece.piece_id == piece_id:
                return piece
        raise KeyError(piece_id)

    def pieces_of(self, owner: int) -> tuple[PaperPiece, ...]:
        return tuple(piece for piece in self.pieces if piece.owner == owner)

    def spread_pieces(self) -> tuple[PaperPiece, ...]:
        return tuple(piece for piece in self.pieces if piece.is_spread)

    def certainty(self) -> float:
        if not self.pieces:
            return 0.0
        return sum(max((chance for _, chance in piece.sites), default=0.0)
                   for piece in self.pieces) / len(self.pieces)

    def occupancy(self) -> dict[Square, tuple[int, float]]:
        by_square: dict[Square, list[float]] = {}
        for piece in self.pieces:
            for square, chance in piece.sites:
                pair = by_square.setdefault(square, [0.0, 0.0])
                pair[piece.owner] += chance
        out: dict[Square, tuple[int, float]] = {}
        for square, chances in by_square.items():
            owner = 0 if chances[0] >= chances[1] else 1
            out[square] = (owner, chances[owner])
        return out

    def clone(self, **changes: Any) -> "PaperState":
        return replace(self, **changes)


class PaperQuantumEngine:
    """Sparse exact-amplitude engine for paper levels 0–3 plus custom level 4.

    Level 4 adds the project's optional Observe/decoherence extension. Levels 0–3
    permit no voluntary measurement. `state_from_amplitudes` is public to support
    curated positions, analysis and small conformance tests.
    """

    name = "paper-quantum"

    def __init__(self, seed: int = 0, *, board_size: int = 8, level: int = 0,
                 max_plies: int = 1000, sampler: Sampler | None = None,
                 max_branches: int = 4096, decoherence_ticks: int = 6) -> None:
        if not 4 <= board_size <= 16:
            raise ValueError("board_size must be between 4 and 16")
        if level not in range(5):
            raise ValueError("level must be 0 through 4")
        if max_branches < 1:
            raise ValueError("max_branches must be positive")
        if decoherence_ticks < 1:
            raise ValueError("decoherence_ticks must be positive")
        self.seed = int(seed)
        self.level = int(level)
        self.board_size = int(board_size)
        self.max_plies = int(max_plies)
        self.max_branches = int(max_branches)
        self.decoherence_ticks = int(decoherence_ticks)
        self.allow_observe = self.level == 4
        self.sampler = sampler
        self._rng = random.Random(self.seed)

    def clone(self, seed: int | None = None) -> "PaperQuantumEngine":
        return PaperQuantumEngine(
            self.seed if seed is None else int(seed), board_size=self.board_size,
            level=self.level, max_plies=self.max_plies, sampler=None,
            max_branches=self.max_branches, decoherence_ticks=self.decoherence_ticks,
        )

    def initial_state(self) -> PaperState:
        size = self.board_size
        rows = min(3, max(1, (size - 2) // 2))
        entries: list[tuple[str, Square | None, bool]] = []
        roster: dict[str, int] = {}
        index = 0
        for row in range(rows):
            for col in range(size):
                if (row + col) % 2 == 1:
                    piece_id = f"P1-{index}"
                    index += 1
                    entries.append((piece_id, (row, col), False))
                    roster[piece_id] = 1
        index = 0
        for row in range(size - rows, size):
            for col in range(size):
                if (row + col) % 2 == 1:
                    piece_id = f"P0-{index}"
                    index += 1
                    entries.append((piece_id, (row, col), False))
                    roster[piece_id] = 0
        return self._make_state({tuple(sorted(entries)): 1 + 0j}, roster, turn=0)

    def state_from_amplitudes(
        self, amplitudes: Mapping[Configuration, Complex], *, owners: Mapping[str, int],
        turn: int = 0, ply: int = 0, quiet_moves: int = 0,
        continuation_piece: str | None = None,
    ) -> PaperState:
        """Build a normalized state from complete basis configurations."""
        if turn not in (0, 1):
            raise ValueError("turn must be 0 or 1")
        roster = {str(piece_id): int(owner) for piece_id, owner in owners.items()}
        if any(owner not in (0, 1) for owner in roster.values()):
            raise ValueError("piece owners must be 0 or 1")
        for configuration in amplitudes:
            for piece_id, _, _ in configuration:
                if piece_id not in roster and not _is_ancilla(piece_id):
                    raise ValueError(f"missing owner for piece {piece_id!r}")
        return self._make_state(amplitudes, roster, turn=turn, ply=ply,
                                quiet_moves=quiet_moves, continuation_piece=continuation_piece)

    def _make_state(self, amplitudes: Mapping[Configuration, Complex], roster: Mapping[str, int],
                    *, turn: int, ply: int = 0, quiet_moves: int = 0,
                    continuation_piece: str | None = None, chain_captured: bool = False,
                    history: tuple[PaperAction, ...] = (), coherence: Mapping[str, int] | None = None,
                    last_event: CollapseEvent | None = None) -> PaperState:
        expanded = {
            tuple(configuration) + tuple((pid, None, False) for pid in roster
                                         if pid not in {entry[0] for entry in configuration}): amplitude
            for configuration, amplitude in amplitudes.items()
        }
        branches = self._coalesce(expanded)
        norm = sum(abs(amplitude) ** 2 for amplitude in branches.values())
        if not math.isclose(norm, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise PaperRuleError(f"quantum state must have norm 1; got {norm:.12g}")
        self._check_cap(len(branches))
        site_weights: dict[str, dict[Square, float]] = {pid: {} for pid in roster}
        king_weights: dict[str, dict[Square, float]] = {pid: {} for pid in roster}
        present: dict[str, float] = {pid: 0.0 for pid in roster}
        for configuration, amplitude in branches.items():
            probability = abs(amplitude) ** 2
            for piece_id, square, crowned in configuration:
                if piece_id not in roster or square is None:
                    continue
                present[piece_id] += probability
                sites = site_weights[piece_id]
                sites[square] = sites.get(square, 0.0) + probability
                if crowned:
                    kings = king_weights[piece_id]
                    kings[square] = kings.get(square, 0.0) + probability
        pieces = tuple(
            PaperPiece(
                pid, owner,
                tuple(sorted(site_weights[pid].items())),
                tuple(sorted(king_weights[pid].items())),
                present[pid],
            )
            for pid, owner in sorted(roster.items())
        )
        captured = tuple(sorted(
            pid for pid in roster
            if all(_entry(branch, pid)[1] is None for branch in branches)
        ))
        return PaperState(
            turn=turn, ply=ply, pieces=pieces, roster=tuple(sorted(roster.items())),
            amplitudes=tuple(sorted(branches.items(), key=lambda item: repr(item[0]))),
            captured=captured, last_event=last_event, history=history,
            continuation_piece=continuation_piece, quiet_moves=quiet_moves,
            chain_captured=chain_captured,
            coherence=tuple(sorted((coherence or {}).items())),
        )

    def _coalesce(self, branches: Mapping[Configuration, Complex]) -> dict[Configuration, Complex]:
        out: dict[Configuration, Complex] = {}
        for raw, amplitude in branches.items():
            config = tuple(sorted((str(pid), square, bool(king)) for pid, square, king in raw))
            if len({pid for pid, _, _ in config}) != len(config):
                raise PaperRuleError("a configuration may list each piece once")
            occupied = [square for _, square, _ in config if square is not None]
            if len(occupied) != len(set(occupied)):
                raise PaperRuleError("a basis configuration cannot overlap pieces")
            if any(square is not None and not self._in_board(square) for _, square, _ in config):
                raise PaperRuleError("a configuration square lies outside the board")
            out[config] = out.get(config, 0j) + complex(amplitude)
        return {config: amp for config, amp in out.items() if abs(amp) > 1e-14}

    def _check_cap(self, count: int) -> None:
        if count > self.max_branches:
            raise BranchLimitError(
                f"exact state needs {count} branches; configured cap is {self.max_branches}"
            )

    def _in_board(self, square: Square) -> bool:
        return 0 <= square[0] < self.board_size and 0 <= square[1] < self.board_size

    def _is_promotion(self, square: Square, owner: int) -> bool:
        return square[0] == (0 if owner == 0 else self.board_size - 1)

    def _directions(self, owner: int, crowned: bool) -> tuple[tuple[int, int], ...]:
        forward = -1 if owner == 0 else 1
        rows = (forward, -forward) if crowned else (forward,)
        return tuple((dr, dc) for dr in rows for dc in (-1, 1))

    def _step_allowed(self, owner: int, crowned: bool, origin: Square, target: Square) -> bool:
        return (target[0] - origin[0], target[1] - origin[1]) in self._directions(owner, crowned)

    def _capture_allowed(self, owner: int, crowned: bool, origin: Square,
                         jumped: Square, target: Square) -> bool:
        dr = jumped[0] - origin[0]
        dc = jumped[1] - origin[1]
        return ((dr, dc) in self._directions(owner, crowned)
                and target == (origin[0] + 2 * dr, origin[1] + 2 * dc))

    @staticmethod
    def _occupied(configuration: Configuration, square: Square, except_id: str | None = None) -> bool:
        return any(pid != except_id and location == square for pid, location, _ in configuration)

    def _destination_clear(self, state: PaperState, square: Square,
                           except_piece_id: str | None = None) -> bool:
        """A possible occupant blocks a landing without measurement.

        Ordinary moves, capture landings, and split destinations are blocked by every
        piece, including the acting piece's own other branches: letting a part land
        where the piece could already be would silently coalesce configurations that
        only the merge operator may join. The merge operator passes its own piece id
        as an exception, because rejoining its own branches is exactly what it does.
        """
        return all(
            not self._occupied(configuration, square, except_piece_id)
            for configuration, amplitude in state.amplitudes
            if abs(amplitude) > 1e-14
        )

    def _config_actions(self, configuration: Configuration, roster: Mapping[str, int], owner: int
                        ) -> tuple[set[PaperMoveAction], set[PaperCaptureAction]]:
        moves: set[PaperMoveAction] = set()
        captures: set[PaperCaptureAction] = set()
        for piece_id, square, crowned in configuration:
            if piece_id not in roster:
                continue
            if roster[piece_id] != owner or square is None:
                continue
            for dr, dc in self._directions(owner, crowned):
                target = (square[0] + dr, square[1] + dc)
                if self._in_board(target) and not self._occupied(configuration, target, piece_id):
                    moves.add(PaperMoveAction(piece_id, square, target))
                jumped = target
                landing = (square[0] + 2 * dr, square[1] + 2 * dc)
                if not self._in_board(landing) or not self._in_board(jumped):
                    continue
                victim = next((pid for pid, loc, _ in configuration
                               if loc == jumped and roster[pid] != owner), None)
                if victim is not None and not self._occupied(configuration, landing, piece_id):
                    captures.add(PaperCaptureAction(piece_id, square, jumped, landing))
        return moves, captures

    def legal_actions(self, state: PaperState) -> tuple[PaperAction, ...]:
        if state.ply >= self.max_plies or state.quiet_moves > 40:
            return ()
        owners = dict(state.roster)
        moves: set[PaperMoveAction] = set()
        captures: set[PaperCaptureAction] = set()
        for configuration, amplitude in state.amplitudes:
            if abs(amplitude) <= 1e-14:
                continue
            branch_moves, branch_captures = self._config_actions(configuration, owners, state.turn)
            moves.update(branch_moves)
            captures.update(branch_captures)
        # Branch-local availability does not make an uncertain landing empty.
        # Filter captures before applying compulsory-capture priority so blocked
        # landings cannot suppress otherwise legal ordinary moves.
        moves = {action for action in moves
                 if self._destination_clear(state, action.target)}
        captures = {action for action in captures
                    if self._destination_clear(state, action.target)}
        if state.continuation_piece is not None:
            captures = {action for action in captures if action.piece_id == state.continuation_piece}
            candidates: set[PaperAction] = set(captures)
        elif captures:
            candidates = set(captures)
        else:
            candidates = set(moves)
            if self.level >= 1:
                candidates.update(self._split_actions(state))
            if self.level >= 3:
                candidates.update(self._merge_actions(state))
        # Observe is an optional level-4 extension, but it may not bypass either
        # forced continuation or the paper's mandatory-capture rule.
        if self.allow_observe and state.continuation_piece is None and not captures:
            for piece in state.pieces_of(state.turn):
                if piece.survival_probability > 0 and piece.is_spread:
                    candidates.add(PaperObserveAction(piece.piece_id, piece.squares[0]))
        return tuple(sorted(candidates, key=lambda a: (a.kind, a.piece_id, str(a.to_json()))))

    def _split_actions(self, state: PaperState) -> Iterable[PaperSplitAction]:
        for piece in state.pieces_of(state.turn):
            if piece.survival_probability <= 0:
                continue
            for origin in piece.squares:
                crown_modes = {
                    _entry(config, piece.piece_id)[2]
                    for config, _ in state.amplitudes
                    if _entry(config, piece.piece_id)[1] == origin
                }
                targets = sorted({
                    target
                    for crowned in crown_modes
                    for dr, dc in self._directions(piece.owner, crowned)
                    for target in ((origin[0] + dr, origin[1] + dc),)
                    if self._in_board(target)
                })
                # Both targets must be clear across the entire quantum state;
                # direction/type validity is checked on the selected source part.
                for i, first in enumerate(targets):
                    for second in targets[i + 1:]:
                        if not (self._destination_clear(state, first)
                                and self._destination_clear(state, second)):
                            continue
                        if any(
                            _entry(config, piece.piece_id)[1] == origin
                            and self._step_allowed(piece.owner, _entry(config, piece.piece_id)[2],
                                                   origin, first)
                            and self._step_allowed(piece.owner, _entry(config, piece.piece_id)[2],
                                                   origin, second)
                            and not self._occupied(config, first, piece.piece_id)
                            and not self._occupied(config, second, piece.piece_id)
                            for config, _ in state.amplitudes
                        ):
                            yield PaperSplitAction(piece.piece_id, origin, (first, second))

    def _merge_actions(self, state: PaperState) -> Iterable[PaperMergeAction]:
        for piece in state.pieces_of(state.turn):
            sites = piece.squares
            for i, origin in enumerate(sites):
                for other in sites[i + 1:]:
                    origin_modes = {
                        _entry(config, piece.piece_id)[2]
                        for config, amplitude in state.amplitudes
                        if abs(amplitude) > 1e-14
                        and _entry(config, piece.piece_id)[1] == origin
                    }
                    other_modes = {
                        _entry(config, piece.piece_id)[2]
                        for config, amplitude in state.amplitudes
                        if abs(amplitude) > 1e-14
                        and _entry(config, piece.piece_id)[1] == other
                    }
                    # Merge joins two parts of the same original piece only when
                    # both source modes have one shared piece type. A man and king
                    # component cannot be merged into one target mode.
                    if len(origin_modes) != 1 or origin_modes != other_modes:
                        continue
                    crown_modes = origin_modes
                    targets = {
                        target
                        for crowned in crown_modes
                        for target in self._diagonal_common_targets(
                            piece.owner, origin, other, crowned, crowned
                        )
                    }
                    for target in sorted(targets):
                        if not self._destination_clear(state, target, piece.piece_id):
                            continue
                        if any(
                            _entry(config, piece.piece_id)[1] in (origin, other)
                            and self._step_allowed(piece.owner, _entry(config, piece.piece_id)[2],
                                                   origin, target)
                            and self._step_allowed(piece.owner, _entry(config, piece.piece_id)[2],
                                                   other, target)
                            and not self._occupied(config, target, piece.piece_id)
                            for config, _ in state.amplitudes
                        ):
                            yield PaperMergeAction(piece.piece_id, origin, other, target)

    def _diagonal_common_targets(self, owner: int, first: Square, second: Square,
                                 first_king: bool, second_king: bool) -> tuple[Square, ...]:
        a = {(first[0] + dr, first[1] + dc)
             for dr, dc in self._directions(owner, first_king)}
        b = {(second[0] + dr, second[1] + dc)
             for dr, dc in self._directions(owner, second_king)}
        return tuple(sorted(target for target in a & b if self._in_board(target)))

    def apply(self, state: PaperState, action: PaperAction) -> Step:
        """Apply an action atomically, including the engine's seeded sampler state."""
        rng_state = self._rng.getstate()
        try:
            return self._apply_impl(state, action)
        except BaseException:
            self._rng.setstate(rng_state)
            raise

    def _apply_impl(self, state: PaperState, action: PaperAction) -> Step:
        legal = self.legal_actions(state)
        if action not in legal:
            raise PaperRuleError(f"illegal {action.kind} action for {action.piece_id} at ply {state.ply}")
        branches = dict(state.amplitudes)
        events: list[CollapseEvent] = []
        captured = False
        coherence = dict(state.coherence)
        continuation: str | None = None

        if isinstance(action, PaperMoveAction):
            branches = self._move_gate(branches, state, action)
        elif isinstance(action, PaperSplitAction):
            branches = self._split_gate(branches, action, dict(state.roster)[action.piece_id])
            if self.level == 4:
                coherence[action.piece_id] = self.decoherence_ticks
        elif isinstance(action, PaperMergeAction):
            branches = self._merge_gate(branches, action, dict(state.roster)[action.piece_id])
            if self.level == 4:
                coherence[action.piece_id] = self.decoherence_ticks
        elif isinstance(action, PaperObserveAction):
            branches, event = self._project_piece(branches, state, action.piece_id, "observe")
            events.append(event)
            if self.level == 4:
                coherence[action.piece_id] = self.decoherence_ticks
        elif isinstance(action, PaperCaptureAction):
            promotion_on_capture = any(
                _entry(config, action.piece_id)[1] == action.origin
                and not _entry(config, action.piece_id)[2]
                and self._is_promotion(action.target, dict(state.roster)[action.piece_id])
                for config in branches
            )
            result = self._capture(branches, state, action)
            branches, events, captured = result
            if captured and not promotion_on_capture:
                after_tmp = self._make_state(
                    branches, dict(state.roster), turn=state.turn, ply=state.ply + 1,
                    history=state.history + (action,), coherence=coherence,
                )
                followup = [a for a in self.legal_actions(after_tmp)
                            if isinstance(a, PaperCaptureAction) and a.piece_id == action.piece_id]
                if followup:
                    continuation = action.piece_id

        # `ply` is a revision counter and advances on every action, including every
        # forced jump. Turn and quiet-move count advance only when the chain ends.
        chain_captured = state.chain_captured or captured
        turn_ends = continuation is None
        if turn_ends:
            quiet = 0 if chain_captured else state.quiet_moves + 1
            next_turn = 1 - state.turn
            chain_captured = False
            if self.level == 4:
                post_action = self._make_state(
                    branches, dict(state.roster), turn=next_turn, ply=state.ply + 1,
                    quiet_moves=quiet, coherence=coherence,
                )
                branches, decay_events, coherence = self._decohere(
                    branches, post_action, action, coherence
                )
                events.extend(decay_events)
        else:
            quiet = state.quiet_moves
            next_turn = state.turn

        last_event = events[-1] if events else None
        next_state = self._make_state(
            branches, dict(state.roster), turn=next_turn, ply=state.ply + 1,
            quiet_moves=quiet, continuation_piece=continuation,
            chain_captured=chain_captured, history=state.history + (action,),
            coherence=coherence, last_event=last_event,
        )
        return Step(state=next_state, events=tuple(events))

    def _capture(self, branches: dict[Configuration, Complex], state: PaperState,
                 action: PaperCaptureAction
                 ) -> tuple[dict[Configuration, Complex], list[CollapseEvent], bool]:
        events: list[CollapseEvent] = []
        piece = state.piece(action.piece_id)
        attacker_was_split = piece.is_spread
        # Level 1 measurement order: measure a split jumper first; a failed location
        # is a pass and the defender is not measured.
        if piece.is_spread:
            branches, event = self._project_piece(branches, state, action.piece_id, "capture")
            events.append(event)
            if event.sampled != action.origin:
                return branches, events, False
            state = self._make_state(branches, dict(state.roster), turn=state.turn,
                                     ply=state.ply, coherence=dict(state.coherence))
        owners = dict(state.roster)
        defender = next((p for p in state.pieces_of(1 - state.turn)
                         if p.chance_at(action.jumped) > 0), None)
        if self.level >= 2 and not attacker_was_split and defender and defender.is_spread:
            # Conditional capture is the paper's L2 entangling rule. Each basis
            # component either jumps/captures or leaves the jumper untouched.
            out: dict[Configuration, Complex] = {}
            any_capture = False
            for config, amplitude in branches.items():
                a_square = _entry(config, action.piece_id)[1]
                d_entry = next(((pid, square, king) for pid, square, king in config
                                if pid != action.piece_id and pid in owners
                                and owners[pid] == 1 - state.turn
                                and square == action.jumped), None)
                if a_square == action.origin and d_entry is not None:
                    a_entry = _entry(config, action.piece_id)
                    if (self._occupied(config, action.target, action.piece_id)
                            or not self._capture_allowed(owners[action.piece_id], a_entry[2],
                                                         action.origin, action.jumped, action.target)):
                        _accumulate(out, config, amplitude)
                        continue
                    a_king = _entry(config, action.piece_id)[2] or self._is_promotion(
                        action.target, owners[action.piece_id]
                    )
                    moved = _replace_entry(config, action.piece_id, action.target,
                                           a_king, owners[action.piece_id], self.board_size)
                    if not a_entry[2] and a_king:
                        moved = _mark_promotion(moved, action.piece_id, state.ply, False)
                    moved = _replace_entry(moved, d_entry[0], None, d_entry[2], owners[d_entry[0]], self.board_size)
                    _accumulate(out, moved, 1j * amplitude)
                    any_capture = True
                else:
                    _accumulate(out, config, amplitude)
            self._validate_norm(branches, out)
            return self._coalesce(out), events, any_capture

        # Level 1 measures a split defender only after jumper is known at origin.
        if defender and defender.is_spread:
            branches, event = self._project_piece(branches, state, defender.piece_id, "capture")
            events.append(event)
            if event.sampled != action.jumped:
                return branches, events, False

        out = {}
        any_capture = False
        for config, amplitude in branches.items():
            a = _entry(config, action.piece_id)
            victim = next(((pid, square, king) for pid, square, king in config
                           if pid != action.piece_id and pid in owners and owners[pid] != state.turn
                           and square == action.jumped), None)
            if (a[1] == action.origin and victim is not None
                    and not self._occupied(config, action.target, action.piece_id)
                    and self._capture_allowed(owners[action.piece_id], a[2],
                                              action.origin, action.jumped, action.target)):
                a_king = a[2] or self._is_promotion(action.target, owners[action.piece_id])
                moved = _replace_entry(config, action.piece_id, action.target, a_king, owners[action.piece_id], self.board_size)
                if not a[2] and a_king:
                    moved = _mark_promotion(moved, action.piece_id, state.ply, False)
                moved = _replace_entry(moved, victim[0], None, victim[2], owners[victim[0]], self.board_size)
                _accumulate(out, moved, 1j * amplitude)
                any_capture = True
            else:
                _accumulate(out, config, amplitude)
        self._validate_norm(branches, out)
        return self._coalesce(out), events, any_capture

    def _measure_distribution(self, branches: Mapping[Configuration, Complex], piece_id: str
                               ) -> tuple[tuple[Square, float], ...]:
        weights: dict[Square, float] = {}
        for config, amplitude in branches.items():
            square = _entry(config, piece_id)[1]
            label = square if square is not None else (-1, -1)
            weights[label] = weights.get(label, 0.0) + abs(amplitude) ** 2
        return tuple(sorted(weights.items()))

    def _choose(self, sites: tuple[tuple[Square, float], ...]) -> tuple[Square, float]:
        if self.sampler is not None:
            result = self.sampler(sites)
            distribution = dict(sites)
            if result[0] not in distribution:
                raise PaperRuleError(f"sampler returned unsupported outcome {result[0]!r}")
            return result[0], distribution[result[0]]
        draw = self._rng.random()
        total = 0.0
        for square, chance in sites:
            total += chance
            if draw < total:
                return square, chance
        return sites[-1]

    def _project_piece(self, branches: Mapping[Configuration, Complex], state: PaperState,
                       piece_id: str, cause: str
                       ) -> tuple[dict[Configuration, Complex], CollapseEvent]:
        sites = self._measure_distribution(branches, piece_id)
        sampled, probability = self._choose(sites)
        norm = math.sqrt(probability)
        if norm <= 0:
            raise PaperRuleError("measurement selected a zero-probability outcome")
        selected = {
            config: amplitude / norm
            for config, amplitude in branches.items()
            if ((_entry(config, piece_id)[1] if _entry(config, piece_id)[1] is not None else (-1, -1)) == sampled)
        }
        owner = dict(state.roster)[piece_id]
        event = CollapseEvent(
            ply=state.ply, piece_id=piece_id, owner=owner,
            cause=cause, chances=sites, sampled=sampled, probability=probability,
        )
        return self._coalesce(selected), event

    def measure_piece(self, state: PaperState, piece_id: str) -> Step:
        """Project just one piece's position; spectator superpositions survive."""
        if not self.allow_observe:
            raise PaperRuleError("voluntary measurement is only available at level 4")
        if not state.piece(piece_id).is_spread:
            raise PaperRuleError("measurement requires a split piece")
        branches, event = self._project_piece(dict(state.amplitudes), state, piece_id, "observe")
        next_state = self._make_state(
            branches, dict(state.roster), turn=1 - state.turn, ply=state.ply + 1,
            quiet_moves=state.quiet_moves + 1, history=state.history + (PaperObserveAction(piece_id, state.piece(piece_id).squares[0]),),
            coherence=dict(state.coherence), last_event=event,
        )
        return Step(next_state, (event,))

    def _split_gate(self, branches: Mapping[Configuration, Complex], action: PaperSplitAction,
                    owner: int
                    ) -> dict[Configuration, Complex]:
        return self._three_mode_gate(branches, action.piece_id,
                                     (action.origin, action.targets[0], action.targets[1]),
                                     _SPLIT_U, owner)

    def _merge_gate(self, branches: Mapping[Configuration, Complex], action: PaperMergeAction,
                    owner: int
                    ) -> dict[Configuration, Complex]:
        # First apply the Appendix's phase i to both ordinary movement parts, then
        # apply the conjugate transpose of the documented split completion.
        matrix = _adjoint(_SPLIT_U)
        result = self._three_mode_gate(
            branches, action.piece_id,
            (action.target, action.origin, action.other_origin), matrix,
            owner,
            move_phase_indices=(1, 2),
        )
        return result

    def _three_mode_gate(self, branches: Mapping[Configuration, Complex], piece_id: str,
                         modes: tuple[Square, Square, Square], matrix: tuple[tuple[Complex, ...], ...],
                         owner: int,
                         move_phase_indices: tuple[int, ...] = ()) -> dict[Configuration, Complex]:
        out: dict[Configuration, Complex] = {}
        mode_index = {square: index for index, square in enumerate(modes)}
        # Group by the unchanged rest of the full board and by this piece's king bit.
        groups: dict[tuple[tuple[tuple[str, Square | None, bool], ...], bool], list[Complex]] = {}
        samples: dict[tuple[tuple[tuple[str, Square | None, bool], ...], bool], Configuration] = {}
        for config, amplitude in branches.items():
            entry = _entry(config, piece_id)
            if entry[1] not in mode_index:
                _accumulate(out, config, amplitude)
                continue
            rest = tuple(row for row in config if row[0] != piece_id)
            key = (rest, entry[2])
            vector = groups.setdefault(key, [0j, 0j, 0j])
            vector[mode_index[entry[1]]] = amplitude
            samples[key] = config
        for (rest, crowned), vector in groups.items():
            if matrix == _SPLIT_U:
                legal_modes = all(
                    self._step_allowed(owner, crowned, modes[0], modes[index])
                    for index in (1, 2)
                )
            else:
                # A merge reverses two ordinary moves from its target into the
                # source modes. Both parts must be legal for this crown status.
                legal_modes = all(
                    self._step_allowed(owner, crowned, modes[index], modes[0])
                    for index in (1, 2)
                )
            if not legal_modes:
                template = samples[(rest, crowned)]
                for index, amplitude in enumerate(vector):
                    if abs(amplitude) > 1e-14:
                        _accumulate(out, _replace_entry(template, piece_id,
                                     modes[index], crowned, owner, self.board_size), amplitude)
                continue
            if any(location in modes for _, location, _ in rest if location is not None):
                for index, amplitude in enumerate(vector):
                    if abs(amplitude) > 1e-14:
                        _accumulate(out, _replace_entry(samples[(rest, crowned)], piece_id,
                                     modes[index], crowned, owner, self.board_size), amplitude)
                continue
            prepared = [amplitude * (1j if index in move_phase_indices else 1)
                        for index, amplitude in enumerate(vector)]
            transformed = _matvec(matrix, prepared)
            template = samples[(rest, crowned)]
            for index, amplitude in enumerate(transformed):
                if abs(amplitude) <= 1e-14:
                    continue
                square = modes[index]
                crowned_after = crowned or square[0] == (0 if owner == 0 else self.board_size - 1)
                replacement = _replace_entry(template, piece_id, square, crowned_after,
                                             owner, self.board_size)
                _accumulate(out, replacement, amplitude)
        result = self._coalesce(out)
        self._check_cap(len(result))
        self._validate_norm(branches, result)
        return result

    def _move_gate(self, branches: Mapping[Configuration, Complex], state: PaperState,
                   action: PaperMoveAction) -> dict[Configuration, Complex]:
        # Two-mode iSWAP: |10> -> i|01>, |01> -> i|10>. The action is applied
        # independently to each spectator configuration, retaining phase for later merge.
        out: dict[Configuration, Complex] = {}
        owner = dict(state.roster)[action.piece_id]
        groups: dict[tuple[tuple[tuple[str, Square | None, bool], ...], bool], list[tuple[int, Configuration, Complex]]] = {}
        for config, amplitude in branches.items():
            pid, square, king = _entry(config, action.piece_id)
            if square not in (action.origin, action.target):
                _accumulate(out, config, amplitude)
                continue
            rest = tuple(row for row in config if row[0] != pid)
            groups.setdefault((rest, king), []).append((0 if square == action.origin else 1, config, amplitude))
        for (rest, king), group in groups.items():
            if not self._step_allowed(owner, king, action.origin, action.target):
                for _, config, amplitude in group:
                    _accumulate(out, config, amplitude)
                continue
            for index, config, amplitude in group:
                destination = action.target if index == 0 else action.origin
                if any(loc == destination for _, loc, _ in rest):
                    _accumulate(out, config, amplitude)
                    continue
                crowned = king or destination[0] == (0 if owner == 0 else self.board_size - 1)
                moved = _replace_entry(config, action.piece_id, destination, crowned, owner, self.board_size)
                if not king and crowned:
                    moved = _mark_promotion(moved, action.piece_id, state.ply, False)
                _accumulate(out, moved, 1j * amplitude)
        result = self._coalesce(out)
        self._check_cap(len(result))
        self._validate_norm(branches, result)
        return result

    def _decohere(self, branches: Mapping[Configuration, Complex], state: PaperState,
                  action: PaperAction, coherence: dict[str, int]
                  ) -> tuple[dict[Configuration, Complex], list[CollapseEvent], dict[str, int]]:
        events: list[CollapseEvent] = []
        for piece in state.pieces:
            if piece.survival_probability <= 1e-9 or not piece.is_spread:
                coherence.pop(piece.piece_id, None)
                continue
            if isinstance(action, (PaperSplitAction, PaperMergeAction, PaperObserveAction)) and action.piece_id == piece.piece_id:
                coherence[piece.piece_id] = self.decoherence_ticks
                continue
            remaining = coherence.get(piece.piece_id, self.decoherence_ticks) - 1
            coherence[piece.piece_id] = remaining
            if remaining <= 0:
                branches, event = self._project_piece(branches, state, piece.piece_id, "decoherence")
                events.append(event)
                coherence[piece.piece_id] = self.decoherence_ticks
        return dict(branches), events, coherence

    def _validate_norm(self, before: Mapping[Configuration, Complex],
                       after: Mapping[Configuration, Complex]) -> None:
        old = sum(abs(value) ** 2 for value in before.values())
        new = sum(abs(value) ** 2 for value in after.values())
        if not math.isclose(old, new, rel_tol=1e-8, abs_tol=1e-8):
            raise PaperRuleError(f"operation failed to conserve norm ({old:.12g} -> {new:.12g})")

    def is_terminal(self, state: PaperState) -> bool:
        return self.outcome(state) is not None

    def outcome(self, state: PaperState) -> GameOutcome | None:
        if state.ply >= self.max_plies:
            return GameOutcome(None, "ply_limit")
        if state.quiet_moves > 40:
            return GameOutcome(None, "forty_move_draw")  # type: ignore[arg-type]
        for owner in (0, 1):
            if not any(piece.owner == owner and piece.survival_probability > 1e-9 for piece in state.pieces):
                return GameOutcome(1 - owner, "no_pieces")
        if not self._side_has_move(state, state.turn):
            return GameOutcome(1 - state.turn, "no_legal_moves")
        return None

    def _side_has_move(self, state: PaperState, owner: int) -> bool:
        if owner != state.turn:
            shadow = state.clone(turn=owner)
            return bool(self.legal_actions(shadow))
        return bool(self.legal_actions(state))

    def render(self, state: PaperState) -> dict[str, Any]:
        occupancy = [[0.0, 0.0] for _ in range(self.board_size * self.board_size)]
        coherence = dict(state.coherence)
        for piece in state.pieces:
            for (row, col), chance in piece.sites:
                occupancy[row * self.board_size + col][piece.owner] += chance
        certainty = (
            sum(max((chance for _, chance in piece.sites), default=0.0) for piece in state.pieces)
            / len(state.pieces)
            if state.pieces else 0.0
        )
        return {
            "engine": self.name, "level": self.level, "board_size": self.board_size,
            "allow_observe": self.allow_observe, "paper_rules": True,
            "ply": state.ply, "turn": state.turn, "captured": list(state.captured),
            "occupancy": occupancy, "branches": len(state.amplitudes),
            "branch_count": len(state.amplitudes), "certainty": certainty,
            "quiet_moves": state.quiet_moves,
            "coherence_ticks": dict(state.coherence),
            "continuation_piece": state.continuation_piece,
            "decoherence": self.level == 4,
            "decoherence_ticks": self.decoherence_ticks if self.level == 4 else None,
            "pieces": [
                {"piece_id": piece.piece_id, "owner": piece.owner,
                 "sites": [[list(square), chance] for square, chance in piece.sites],
                 "survival_probability": piece.survival_probability,
                 "king_sites": [[list(square), chance] for square, chance in piece.king_sites],
                 "coherence": coherence.get(piece.piece_id),
                 "uncertain": piece.is_spread}
                for piece in state.pieces
                if piece.survival_probability > 1e-9 and piece.sites
            ],
            "last_event": state.last_event.to_json() if state.last_event else None,
        }


def _entry(configuration: Configuration, piece_id: str) -> tuple[str, Square | None, bool]:
    return next(entry for entry in configuration if entry[0] == piece_id)


def _is_ancilla(piece_id: str) -> bool:
    return piece_id.startswith(_ANCILLA_PREFIX)


def _mark_promotion(configuration: Configuration, piece_id: str, ply: int,
                    old_crowned: bool) -> Configuration:
    tag = f"{_ANCILLA_PREFIX}{piece_id}:{ply}"
    if any(existing == tag for existing, _, _ in configuration):
        return configuration
    return tuple(sorted(configuration + ((tag, None, old_crowned),)))


def _replace_entry(configuration: Configuration, piece_id: str, square: Square | None,
                   crowned: bool, owner: int, board_size: int) -> Configuration:
    # `owner` and `board_size` are accepted to keep all transformations explicit at
    # call sites; ownership is stored in the state's immutable roster.
    del owner, board_size
    return tuple(sorted((pid, square if pid == piece_id else old_square,
                         crowned if pid == piece_id else king)
                        for pid, old_square, king in configuration))


def _accumulate(output: dict[Configuration, Complex], configuration: Configuration,
                amplitude: Complex) -> None:
    output[configuration] = output.get(configuration, 0j) + amplitude


def _matvec(matrix: Sequence[Sequence[Complex]], vector: Sequence[Complex]) -> list[Complex]:
    return [sum(matrix[row][col] * vector[col] for col in range(len(vector)))
            for row in range(len(vector))]


def _adjoint(matrix: Sequence[Sequence[Complex]]) -> tuple[tuple[Complex, ...], ...]:
    return tuple(tuple(matrix[col][row].conjugate() for col in range(len(matrix)))
                 for row in range(len(matrix)))

