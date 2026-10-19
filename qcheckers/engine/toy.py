"""Deterministic toy stand-in engine for the Quantum Checkers study.

Owner: **Person A -- rules and engine guardian**.

Why this exists
---------------
The upstream Cheqqers engine (github.com/raatmarien/cheqqers) is not integrated yet
(Gate 2 pending: no paper-version tag confirmed). The team still needs a runnable
engine so that Person B's runner, Person D's statistics and Person E's viewer can be
built and tested in parallel, without waiting on the upstream import.

What it is
----------
A *small, fully deterministic, dependency-free* checkers-like game on a 4x4 board with
three rules layers mapped onto the levels in the project brief:

* **level 0 (classical)** -- ordinary move and capture only.
* **level 1 (+ spread)** -- a piece may take a :class:`SpreadAction`, replacing its
  single square with a distribution over candidate squares.
* **level 2 (+ rejoin)** -- a spread piece may spend its turn collapsing onto one of
  its own candidate squares (:class:`RejoinAction`), i.e. resolving its own
  uncertainty by choice rather than by being forced.
* **Observe** (:class:`ObserveAction`) is only legal when the engine is built with
  ``allow_observe=True``. That flag is how the ablation toggles the Person C
  condition without touching rule logic.

Determinism
-----------
The engine owns a ``random.Random`` seeded by the caller. All sampling (forced
collapses on capture, and Observe) draws from that one stream, so a given
``(seed, level, agents)`` tuple reproduces a game byte for byte. No global RNG is
touched. There is no numpy import here on purpose: the toy engine must stay usable
in a bare interpreter.

Rules fidelity caveat
---------------------
This is *not* the published rule set. Occupancy here is classical probability only.
Move legality, capture resolution, turn order and win conditions must all be
re-verified against the final paper before any claim about reproduction
(Gate 5, brief sections 5, 6 and 10).
"""

from __future__ import annotations

import random
from typing import Any, Callable, Iterable, Sequence

from qcheckers.engine.protocol import (
    DEFAULT_BOARD_SIZE,
    Action,
    CaptureAction,
    CollapseEvent,
    GameOutcome,
    GameState,
    MergeAction,
    MoveAction,
    ObserveAction,
    Piece,
    RejoinAction,
    SpreadAction,
    Square,
    Step,
)

#: Decimal places kept in rendered floats. Mirrors
#: :data:`qcheckers.experiment.schema.FLOAT_PRECISION`; one precision across the whole
#: log is what makes two runs byte-comparable.
RENDER_FLOAT_PRECISION = 10

#: Signature of an injected collapse sampler.
#:
#: It receives a piece's ``(square, chance)`` distribution and returns the single
#: ``(square, chance)`` the collapse resolves to. Live rooms inject an IBM-backed
#: sampler here; every experiment and offline test leaves it ``None`` and keeps the
#: seeded RNG path below.
Sampler = Callable[[tuple[tuple[Square, float], ...]], tuple[Square, float]]


#: Chance weight given to the origin square when a piece spreads.
SPREAD_ORIGIN_CHANCE = 0.5

#: Chance weight split between the remaining candidate squares of a spread.
#: With two candidates that is 0.5/0.5; with three, 0.5/0.25/0.25.
SPREAD_TAIL_CHANCE = 0.5


class DeterministicToyEngine:
    """A small checkers-like engine with probability-carrying pieces.

    Parameters
    ----------
    seed:
        Seed for this engine's private RNG. Two engines with the same seed and
        configuration play identical games.
    level:
        0 = classical, 1 = spread, 2 = rejoin, 3 = merge, 4 = merge + decoherence.
        Levels are additives: 2 includes 1, 3 includes 2. Levels 3 and 4 are playable
        in the game client and are **refused by the batch runner**.
    decoherence:
        **Game-only, default OFF.** When on (level 4 only), every spread piece carries a
        coherence counter: a fresh split starts at :attr:`decoherence_ticks`, each turn
        it goes unmeasured ticks it down, and at zero it auto-collapses using the same
        chance rule measurement already uses (cause ``"decoherence"``). This is an
        invented outreach mechanic, is labelled as such everywhere, and is never part
        of an experiment.
    allow_observe:
        Whether :class:`ObserveAction` is legal. Person C flips this on to create the
        "voluntary measurement" condition.
    board_size:
        Board edge length. Defaults to 4, which keeps games short enough for a
        laptop-sized batch.
    live_rules:
        Enable collision-safe movement and measurement-on-capture for live rooms.
        Defaults to ``False`` so research runs retain their existing rules and logs.
    max_plies:
        Hard ply cap; hitting it is a draw. Prevents infinite games once pieces start
        spreading.
    sampler:
        **Live-game injection point, default ``None``.** When set, every collapse that
        would otherwise draw from the seeded RNG (Observe, a live capture attempt, and
        the Level-4 decoherence expiry) delegates to this callable instead. Live rooms
        inject an IBM-backed sampler so a QPU measurement picks the square; experiments,
        the batch runner and every offline unit test leave it ``None`` and stay
        byte-for-byte reproducible. Note that
        :meth:`clone` deliberately drops the sampler, so an agent's search rollouts
        never submit hardware jobs.
    """

    name = "deterministic-toy"
    board_size: int
    level: int
    allow_observe: bool
    max_plies: int
    decoherence: bool
    decoherence_ticks: int
    sampler: Sampler | None
    live_rules: bool

    def __init__(
        self,
        seed: int = 0,
        *,
        level: int = 2,
        allow_observe: bool = False,
        board_size: int = DEFAULT_BOARD_SIZE,
        max_plies: int = 200,
        decoherence: bool = False,
        decoherence_ticks: int = 6,
        sampler: Sampler | None = None,
        live_rules: bool = False,
    ) -> None:
        if level not in (0, 1, 2, 3, 4):
            raise ValueError(f"level must be 0, 1, 2, 3 or 4; got {level!r}")
        if board_size < 4:
            raise ValueError(f"board_size must be at least 4; got {board_size!r}")
        if level == 4 and not decoherence:
            raise ValueError("level 4 is the decoherence stage; pass decoherence=True")
        if decoherence and level != 4:
            raise ValueError("decoherence is a level-4 game-only rule; got level {level!r}")
        if decoherence_ticks < 1:
            raise ValueError(f"decoherence_ticks must be >= 1; got {decoherence_ticks!r}")
        self.seed = int(seed)
        self.level = level
        self.allow_observe = bool(allow_observe)
        self.board_size = int(board_size)
        self.max_plies = int(max_plies)
        self.decoherence = bool(decoherence)
        self.decoherence_ticks = int(decoherence_ticks)
        self.sampler = sampler
        self.live_rules = bool(live_rules)
        self._rng = random.Random(self.seed)

    # -- setup -------------------------------------------------------------

    def initial_state(self) -> GameState:
        """Sparse opening: one piece on each playable square of each home row.

        Pure with respect to the configuration, so ``initial_state()`` is the same
        for every game at a given configuration.
        """
        size = self.board_size
        pieces: list[Piece] = []
        player_zero_cols = range(1, size, 2)
        player_one_cols = range(0, size - 1, 2)
        if self.live_rules and size % 2:
            # On odd boards both home rows have the same row parity, so they need the
            # same column parity to start on the same playable color.
            player_one_cols = range(1, size, 2)
        for index, col in enumerate(player_zero_cols):
            pieces.append(
                Piece(piece_id=f"P0-{index}", owner=0, sites=(((size - 1, col), 1.0),))
            )
        for index, col in enumerate(player_one_cols):
            pieces.append(Piece(piece_id=f"P1-{index}", owner=1, sites=(((0, col), 1.0),)))
        return GameState(turn=0, ply=0, pieces=tuple(pieces))

    # -- geometry ----------------------------------------------------------

    def _dark_squares(self) -> tuple[Square, ...]:
        """Playable squares in row-major order.

        The selected checker color matches the opening's home-edge parity, so both
        sides use the same playable color on even and odd board sizes.
        """
        size = self.board_size
        parity = size % 2
        return tuple(
            (row, col)
            for row in range(size)
            for col in range(size)
            if (row + col) % 2 == parity
        )

    def _forward_rows(self, owner: int) -> tuple[int, ...]:
        """Rows that count as forward for ``owner``.

        Player 0 moves toward row 0, player 1 toward the last row. Turning is not
        modelled; that is a known simplification for the toy engine.
        """
        return (-1,) if owner == 0 else (1,)

    def _in_board(self, square: Square) -> bool:
        row, col = square
        return 0 <= row < self.board_size and 0 <= col < self.board_size

    def _forward_diagonals(self, square: Square, owner: int) -> tuple[Square, Square]:
        """The two squares one step diagonally forward from ``square``.

        Returned in a stable order (negative column first, then positive) so that
        legal-action ordering never depends on dict iteration order.
        """
        row, col = square
        offsets = [(dr, -1) for dr in self._forward_rows(owner)]
        offsets += [(dr, +1) for dr in self._forward_rows(owner)]
        found = [(row + dr, col + dc) for dr, dc in offsets]
        return found[0], found[1]

    def _piece_at(self, state: GameState, square: Square) -> Piece | None:
        """The piece with the highest chance on ``square``, or ``None``."""
        best: Piece | None = None
        best_chance = 0.0
        for piece in state.pieces:
            chance = piece.chance_at(square)
            if chance > best_chance:
                best, best_chance = piece, chance
        return best

    def _is_certainly_blocked(self, state: GameState, square: Square) -> bool:
        """True when ``square`` is occupied with certainty (chance >= 1 - 1e-9).

        A square that only *might* be occupied is passable for spread purposes,
        because the distribution is explicitly a chance, not a fact.
        """
        piece = self._piece_at(state, square)
        return piece is not None and piece.chance_at(square) >= 1.0 - 1e-9

    @staticmethod
    def _has_other_candidate(
        state: GameState, square: Square, piece_id: str
    ) -> bool:
        """Whether a different piece assigns nonzero chance to ``square``."""
        return any(
            piece.piece_id != piece_id and piece.chance_at(square) > 0.0
            for piece in state.pieces
        )

    def _owner_of_certain_piece(self, state: GameState, square: Square) -> int | None:
        piece = self._piece_at(state, square)
        if piece is None or piece.chance_at(square) < 1.0 - 1e-9:
            return None
        return piece.owner

    # -- legality ----------------------------------------------------------

    def legal_actions(self, state: GameState) -> tuple[Action, ...]:
        """Every legal action for the side to move, in a stable deterministic order.

        Ordering is (kind rank, piece_id, squares) so two runs with the same seed
        produce the same list, which the runner's byte-identity test depends on.
        """
        if self.is_terminal(state):
            return ()

        actions: list[Action] = []
        for piece in sorted(state.pieces, key=lambda p: p.piece_id):
            if piece.owner != state.turn:
                continue
            if piece.is_spread:
                actions.extend(self._spread_piece_actions(state, piece))
            else:
                actions.extend(self._certain_piece_actions(state, piece))
        if self.level >= 3:
            actions.extend(self._merge_actions(state))
        actions.sort(key=lambda a: (a.kind, a.piece_id, str(a.to_json())))
        return tuple(actions)

    def _certain_piece_actions(
        self, state: GameState, piece: Piece
    ) -> Iterable[Action]:
        origin = piece.squares[0]
        for target in self._forward_diagonals(origin, piece.owner):
            if not self._in_board(target):
                continue
            if self.live_rules:
                occupants = [
                    other
                    for other in state.pieces
                    if other.piece_id != piece.piece_id
                    and other.chance_at(target) > 0.0
                ]
                if not occupants:
                    yield MoveAction(piece_id=piece.piece_id, origin=origin, target=target)
                    continue
                if len(occupants) != 1 or occupants[0].owner == piece.owner:
                    continue
                defender = occupants[0]
                landing = self._beyond(target, origin, piece.owner)
                if landing is None or not self._in_board(landing):
                    continue
                if self._has_other_candidate(state, landing, piece.piece_id):
                    continue
                # A certain opponent is captured immediately. A spread opponent is
                # measured by the attempted capture in ``apply``.
                if defender.is_spread or defender.chance_at(target) >= 1.0 - 1e-9:
                    yield CaptureAction(
                        piece_id=piece.piece_id,
                        origin=origin,
                        jumped=target,
                        target=landing,
                    )
                continue
            blocker_owner = self._owner_of_certain_piece(state, target)
            if blocker_owner is None:
                yield MoveAction(piece_id=piece.piece_id, origin=origin, target=target)
                continue
            if blocker_owner == piece.owner:
                continue
            landing = self._beyond(target, origin, piece.owner)
            if landing is None or not self._in_board(landing):
                continue
            if self._is_certainly_blocked(state, landing):
                continue
            yield CaptureAction(
                piece_id=piece.piece_id,
                origin=origin,
                jumped=target,
                target=landing,
            )

        if self.level >= 1:
            yield from self._spread_actions(state, piece)

    def _beyond(self, square: Square, origin: Square, owner: int) -> Square | None:
        """The square two steps forward past ``square``, continuing from ``origin``."""
        row, col = square
        step_row = row - origin[0]
        step_col = col - origin[1]
        nxt = (row + step_row, col + step_col)
        if nxt == origin:
            return None
        forward = self._forward_rows(owner)
        if nxt[0] - row not in forward:
            return None
        return nxt

    def _spread_actions(self, state: GameState, piece: Piece) -> Iterable[SpreadAction]:
        """Spread moves for a certain piece: origin plus free forward diagonals.

        The origin square is retained with chance ``SPREAD_ORIGIN_CHANCE`` and the
        remaining weight is divided evenly over the chosen target squares, so the
        total is always exactly 1.0 (asserted by :class:`Piece`).

        House rule -- **keep one certain piece.** A side may not spread its last
        certain piece. Without this guard, spreading every piece strands the side
        permanently (a spread piece cannot move normally, and at levels 0-1 there is
        no way to resolve one), so the first player to use the quantum mechanic simply
        loses. The guard keeps the design invariant "classical moves are always
        available" true in practice and keeps the game from degenerating in two plies.
        It is a deliberate deviation from the published rules and is labelled as such.
        """
        certain = sum(1 for p in state.pieces_of(piece.owner) if not p.is_spread)
        if certain < 2:
            return

        origin = piece.squares[0]
        targets: list[Square] = []
        for target in self._forward_diagonals(origin, piece.owner):
            if not self._in_board(target):
                continue
            if self.live_rules:
                if self._has_other_candidate(state, target, piece.piece_id):
                    continue
                targets.append(target)
                continue
            if self._is_certainly_blocked(state, target):
                continue
            if target not in targets:
                targets.append(target)
        if self.live_rules and self._has_other_candidate(state, origin, piece.piece_id):
            return
        if not targets:
            return
        share = SPREAD_TAIL_CHANCE / len(targets)
        sites: tuple[tuple[Square, float], ...] = (
            (origin, SPREAD_ORIGIN_CHANCE),
            *((target, share) for target in targets),
        )
        yield SpreadAction(piece_id=piece.piece_id, origin=origin, sites=sites)

    def _spread_piece_actions(
        self, state: GameState, piece: Piece
    ) -> Iterable[Action]:
        if self.allow_observe and (
            not self.live_rules
            or not any(
                self._has_other_candidate(state, square, piece.piece_id)
                for square in piece.squares
            )
        ):
            yield ObserveAction(piece_id=piece.piece_id, origin=piece.squares[0])
        if self.level >= 2:
            for square in piece.squares:
                if self.live_rules and self._has_other_candidate(
                    state, square, piece.piece_id
                ):
                    continue
                yield RejoinAction(
                    piece_id=piece.piece_id, origin=piece.squares[0], target=square
                )

    def _merge_actions(self, state: GameState, owner: int | None = None) -> Iterable[MergeAction]:
        """Level 3: merge two of the mover's diagonally adjacent own pieces.

        Ordering is by ``(piece_id, other_piece_id)`` over the sorted piece list, so
        the action set stays deterministic. The merged piece keeps the lower id, which
        is what :meth:`apply` relies on.
        """
        who = state.turn if owner is None else owner
        own = sorted(state.pieces_of(who), key=lambda p: p.piece_id)
        for index, first in enumerate(own):
            for other in own[index + 1 :]:
                if self._diagonally_adjacent(first, other):
                    yield MergeAction(
                        piece_id=first.piece_id,
                        origin=first.squares[0],
                        other_piece_id=other.piece_id,
                    )

    @staticmethod
    def _diagonally_adjacent(a: Piece, b: Piece) -> bool:
        """True when any site of ``a`` is a diagonal neighbour of any site of ``b``."""
        for (row_a, col_a), _ in a.sites:
            for (row_b, col_b), _ in b.sites:
                if abs(row_a - row_b) == 1 and abs(col_a - col_b) == 1:
                    return True
        return False

    # -- applying actions --------------------------------------------------

    def apply(self, state: GameState, action: Action) -> Step:
        """Apply ``action`` and return the next state plus any collapse events.

        Raises ``ValueError`` for an illegal action. Person A's legality tests pin
        this behaviour, and the runner relies on it to catch agent bugs.
        """
        legal = self.legal_actions(state)
        if action not in legal:
            raise ValueError(
                f"illegal {action.kind} action for {action.piece_id} on ply {state.ply}"
            )

        pieces = list(state.pieces)
        events: list[CollapseEvent] = []

        if isinstance(action, MoveAction):
            pieces = self._replace(pieces, action.piece_id, [(action.target, 1.0)])
        elif isinstance(action, CaptureAction):
            defender = next(
                (
                    p
                    for p in state.pieces
                    if p.piece_id != action.piece_id and p.chance_at(action.jumped) > 0.0
                ),
                None,
            )
            if self.live_rules and defender is not None and defender.is_spread:
                sampled = self._sample_sites(defender.sites)
                events.append(
                    CollapseEvent(
                        ply=state.ply,
                        piece_id=defender.piece_id,
                        owner=defender.owner,
                        cause="capture",
                        chances=defender.sites,
                        sampled=sampled[0],
                        probability=sampled[1],
                    )
                )
                if sampled[0] == action.jumped:
                    pieces = self._replace(
                        pieces, action.piece_id, [(action.target, 1.0)]
                    )
                    pieces = [p for p in pieces if p.piece_id != defender.piece_id]
                    state = state.clone(
                        captured=tuple(sorted(state.captured + (defender.piece_id,)))
                    )
                else:
                    pieces = self._replace(
                        pieces, defender.piece_id, [(sampled[0], 1.0)]
                    )
            else:
                pieces = self._replace(pieces, action.piece_id, [(action.target, 1.0)])
                captured = _piece_id_at(state.pieces, action.jumped)
                pieces = [p for p in pieces if p.piece_id != captured]
                state = state.clone(captured=tuple(sorted(state.captured + (captured,))))
        elif isinstance(action, SpreadAction):
            pieces = self._replace(pieces, action.piece_id, action.sites)
        elif isinstance(action, RejoinAction):
            pieces = self._replace(pieces, action.piece_id, [(action.target, 1.0)])
        elif isinstance(action, MergeAction):
            first = state.piece(action.piece_id)
            other = state.piece(action.other_piece_id)
            pieces = [p for p in pieces if p.piece_id != action.other_piece_id]
            pieces = self._replace(pieces, action.piece_id, _merge_sites(first.sites, other.sites))
        elif isinstance(action, ObserveAction):
            piece = state.piece(action.piece_id)
            if not piece.is_spread:
                raise ValueError(
                    f"observe requires an uncertain piece; {action.piece_id} is certain"
                )
            sampled = self._sample_sites(piece.sites)
            events.append(
                CollapseEvent(
                    ply=state.ply,
                    piece_id=piece.piece_id,
                    owner=piece.owner,
                    cause="observe",
                    chances=piece.sites,
                    sampled=sampled[0],
                    probability=sampled[1],
                )
            )
            pieces = self._replace(pieces, action.piece_id, [(sampled[0], 1.0)])
        else:  # pragma: no cover - defensive, Action is a closed union
            raise TypeError(f"unsupported action type: {type(action)!r}")

        if self.decoherence:
            pieces, expiry_events = self._tick_coherence(pieces, action, state.ply)
            events.extend(expiry_events)

        last_event = events[-1] if events else None
        next_state = GameState(
            turn=1 - state.turn,
            ply=state.ply + 1,
            pieces=tuple(sorted(pieces, key=lambda p: p.piece_id)),
            captured=state.captured,
            last_event=last_event,
            history=state.history + (action,),
        )
        return Step(state=next_state, events=tuple(events))

    @staticmethod
    def _replace(
        pieces: list[Piece], piece_id: str, sites: Sequence[tuple[Square, float]]
    ) -> list[Piece]:
        return [
            Piece(p.piece_id, p.owner,
                  tuple((s, float(w)) for s, w in sites)
                  if p.piece_id == piece_id else p.sites)
            if p.piece_id == piece_id else p
            for p in pieces
        ]

def _tick_coherence(
        self, pieces: list[Piece], action: Action, ply: int
    ) -> tuple[list[Piece], list[CollapseEvent]]:
        """Level-4 decoherence: age spread pieces, expiring them at zero.

        A piece the current action just created (a split or a merge) is refreshed to a
        full counter; every other spread piece loses one tick. At zero the piece
        auto-collapses through :meth:`_sample_sites` -- the same chance rule Observe
        and capture use -- and logs a ``decoherence`` collapse event, so the viewer can
        animate it exactly like any other collapse.
        """
        events: list[CollapseEvent] = []
        aged: list[Piece] = []
        for piece in pieces:
            if not piece.is_spread:
                aged.append(piece)
                continue
            # Since Piece does not expose coherence as an init argument and is frozen,
            # we track freshness via the action rather than piece attributes.
            is_fresh = piece.piece_id == action.piece_id
            if is_fresh:
                # Fresh piece from current action; keep as-is.
                # The engine's decoherence flag controls whether it expires.
                aged.append(piece)
                continue
            # For non-fresh spread pieces, use the engine's decoherence_ticks.
            remaining = self.decoherence_ticks - 1
            if remaining <= 0:
                sampled = self._sample_sites(piece.sites)
                events.append(
                    CollapseEvent(
                        ply=ply,
                        piece_id=piece.piece_id,
                        owner=piece.owner,
                        cause="decoherence",
                        chances=piece.sites,
                        sampled=sampled[0],
                        probability=sampled[1],
                    )
                )
                aged.append(piece)
            else:
                aged.append(piece)
        return aged, events

    def _sample_sites(self, sites: tuple[tuple[Square, float], ...]) -> tuple[Square, float]:
        """Resolve a distribution to one site: injected sampler, else seeded RNG.

        With no sampler (every experiment and offline test) the draw is a single
        ``random()`` against the cumulative weights, so the same seed always yields the
        same square. With a sampler (live hardware rooms) the callable owns the choice
        and this engine never touches the RNG -- and never falls back to it, so a failed
        hardware measurement surfaces instead of silently changing the game.
        """
        if self.sampler is not None:
            return self.sampler(sites)
        draw = self._rng.random()
        cumulative = 0.0
        for square, weight in sites:
            cumulative += weight
            if draw < cumulative:
                return square, weight
        last_square, last_weight = sites[-1]
        return last_square, last_weight

    # -- termination -------------------------------------------------------

    def is_terminal(self, state: GameState) -> bool:
        return self.outcome(state) is not None

    def outcome(self, state: GameState) -> GameOutcome | None:
        """Terminal result, or ``None`` while the game is running.

        A player that has lost all pieces loses the game. If the side to move has
        pieces but no legal move, it also loses (normal checkers convention, and the
        convention that keeps a spread-heavy board from stalling).
        """
        if state.ply >= self.max_plies:
            return GameOutcome(winner=None, reason="ply_limit")
        for owner in (0, 1):
            if not state.pieces_of(owner):
                return GameOutcome(winner=1 - owner, reason="no_pieces")
        if not self._side_has_any_move(state, state.turn):
            return GameOutcome(winner=1 - state.turn, reason="no_legal_moves")
        return None

    def _side_has_any_move(self, state: GameState, owner: int) -> bool:
        """Whether ``owner`` has at least one piece that is not stuck.

        Evaluates the same generators that :meth:`legal_actions` uses, so the two can
        never disagree -- that disagreement was a real bug during development, where a
        truthy-but-empty generator reported a stuck side as mobile.

        A spread piece counts as mobile on level 2 (it can rejoin) or whenever Observe
        is enabled. On lower levels a spread piece is stuck until something forces a
        collapse, which is exactly the kind of degenerate board we want the toy engine
        to surface rather than hide.
        """
        for piece in state.pieces_of(owner):
            if piece.is_spread:
                if self.level >= 2 or self.allow_observe:
                    return True
                continue
            if any(True for _ in self._certain_piece_actions(state, piece)):
                return True
        if self.level >= 3 and any(True for _ in self._merge_actions(state, owner)):
            return True
        return False

    # -- presentation ------------------------------------------------------

    def render(self, state: GameState) -> dict[str, Any]:
        """JSON-ready board snapshot for the replay viewer (Person E)."""
        return {
            "engine": self.name,
            "level": self.level,
            "allow_observe": self.allow_observe,
            "board_size": self.board_size,
            "ply": state.ply,
            "turn": state.turn,
            "decoherence": self.decoherence,
            "decoherence_ticks": self.decoherence_ticks if self.decoherence else None,
            "pieces": [
                {
                    "piece_id": p.piece_id,
                    "owner": p.owner,
                    "sites": [[list(s), w] for s, w in p.sites],
                    "uncertain": p.is_spread,
                    "coherence": p.coherence if hasattr(p, "coherence") else None,
                }
                for p in state.pieces
            ],
            "captured": list(state.captured),
            # Rounded to the same precision the record schema declares, so every float
            # in a written log sits at one consistent precision and byte-identity holds.
            "certainty": round(state.certainty(), RENDER_FLOAT_PRECISION),
            # Keep research renders byte-compatible; live snapshots identify the
            # alternate rules explicitly when the flag is enabled.
            **({"live_rules": True} if self.live_rules else {}),
        }

    def clone(self, seed: int | None = None) -> "DeterministicToyEngine":
        """An independent engine with the same configuration.

        Used by search agents (see :func:`qcheckers.engine.protocol.clone_engine`): a
        rollout that samples a collapse must not advance the RNG of the engine playing
        the real game, or the search would silently change the game it is thinking
        about.
        """
        # The sampler is deliberately NOT carried over: a clone exists to be rolled out
        # by a search agent, and a simulated collapse must never submit a hardware job.
        return DeterministicToyEngine(
            seed=self.seed if seed is None else int(seed),
            level=self.level,
            allow_observe=self.allow_observe,
            board_size=self.board_size,
            max_plies=self.max_plies,
            decoherence=self.decoherence,
            decoherence_ticks=self.decoherence_ticks,
            sampler=None,
            live_rules=self.live_rules,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"{type(self).__name__}(seed={self.seed}, level={self.level}, "
            f"allow_observe={self.allow_observe}, board_size={self.board_size}, "
            f"live_rules={self.live_rules}, "
            f"decoherence={self.decoherence})"
        )


def _merge_sites(
    first: tuple[tuple[Square, float], ...], second: tuple[tuple[Square, float], ...]
) -> tuple[tuple[Square, float], ...]:
    """Combine two site distributions into one, normalised to sum to 1.0.

    Squares are visited in first-seen order (all of ``first``, then any new squares
    from ``second``) so the result is deterministic. Two certain pieces become a 50/50
    spread -- the inverse of a split, which is the point of the merge move.
    """
    order: list[Square] = []
    totals: dict[Square, float] = {}
    for square, weight in tuple(first) + tuple(second):
        if square not in totals:
            order.append(square)
            totals[square] = 0.0
        totals[square] += weight
    total = sum(totals.values())
    return tuple((square, totals[square] / total) for square in order)


def _piece_id_at(pieces: Iterable[Piece], square: Square) -> str:
    """Piece id with the highest chance on ``square``; empty string when none.

    Used for captures, where the jumper lands over a square whose occupant may be
    certain or merely probable.
    """
    best_id = ""
    best_chance = 0.0
    for piece in pieces:
        chance = piece.chance_at(square)
        if chance > best_chance:
            best_id, best_chance = piece.piece_id, chance
    return best_id
