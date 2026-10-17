"""Live-game collision and probabilistic-capture rules."""

from __future__ import annotations

import random

import pytest

from qcheckers.engine.protocol import CaptureAction, GameState, Piece
from qcheckers.engine.toy import DeterministicToyEngine
from server.rooms import RoomRegistry


def _capture_position() -> GameState:
    return GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 1, (((1, 2), 0.5), ((1, 0), 0.5))),
            Piece("C", 1, (((0, 1), 1.0),)),
        ),
    )


def _capture_engine(
    sampled_square: tuple[int, int], level: int = 1
) -> DeterministicToyEngine:
    def sampler(sites: tuple[tuple[tuple[int, int], float], ...]):
        return next(site for site in sites if site[0] == sampled_square)

    return DeterministicToyEngine(
        level=level,
        decoherence=level == 4,
        live_rules=True,
        sampler=sampler,
    )


def _attempt(engine: DeterministicToyEngine, state: GameState):
    action = next(
        action
        for action in engine.legal_actions(state)
        if isinstance(action, CaptureAction) and action.piece_id == "A"
    )
    return action, engine.apply(state, action)


@pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("board_size", [4, 8, 16])
def test_live_rooms_use_live_rules_and_keep_all_piece_sites_disjoint(
    level: int, board_size: int
) -> None:
    room = RoomRegistry().create(level=level, mode="local", seed=level, board_size=board_size)
    engine = room.engine
    assert engine.live_rules is True
    assert engine.render(room.state)["live_rules"] is True
    assert len(room.state.pieces_of(0)) == len(room.state.pieces_of(1)) == board_size // 2
    assert {piece.squares[0][0] for piece in room.state.pieces_of(0)} == {board_size - 1}
    assert {piece.squares[0][0] for piece in room.state.pieces_of(1)} == {0}
    assert all(
        square in engine._dark_squares()
        for piece in room.state.pieces
        for square in piece.squares
    )

    rng = random.Random(level * 31 + board_size)
    state = room.state
    for _ in range(120):
        legal = engine.legal_actions(state)
        if not legal:
            break
        state = engine.apply(state, rng.choice(legal)).state
        sites = [square for piece in state.pieces for square in piece.squares]
        assert len(sites) == len(set(sites))


def test_ordinary_step_and_split_cannot_enter_another_piece_candidate() -> None:
    engine = DeterministicToyEngine(level=1, live_rules=True)
    state = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 1, (((1, 0), 0.5), ((1, 2), 0.5))),
            Piece("C", 1, (((0, 1), 1.0),)),
        ),
    )
    actions = engine.legal_actions(state)

    assert not any(
        action.piece_id == "A" and action.kind == "move" and action.target == (1, 2)
        for action in actions
    )
    assert not any(
        action.piece_id == "A"
        and action.kind == "spread"
        and (1, 2) in {square for square, _ in action.sites}
        for action in actions
    )


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_uncertain_capture_success_moves_attacker_and_removes_defender(level: int) -> None:
    engine = _capture_engine((1, 2), level)
    state = _capture_position()

    action, step = _attempt(engine, state)

    assert action.target == (0, 3)
    assert step.state.piece("A").squares == ((0, 3),)
    assert "B" not in {piece.piece_id for piece in step.state.pieces}
    assert step.state.captured == ("B",)
    assert len(step.events) == 1
    assert step.events[0].cause == "capture"
    assert step.events[0].piece_id == "B"
    assert step.events[0].sampled == (1, 2)
    assert step.state.turn == 1


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_uncertain_capture_failure_collapses_defender_and_keeps_attacker(level: int) -> None:
    engine = _capture_engine((1, 0), level)
    state = _capture_position()

    _, step = _attempt(engine, state)

    assert step.state.piece("A").squares == ((2, 1),)
    assert step.state.piece("B").sites == (((1, 0), 1.0),)
    assert step.state.captured == ()
    assert step.events[0].cause == "capture"
    assert step.events[0].sampled == (1, 0)
    assert step.state.turn == 1


def test_uncertain_capture_sampler_failure_leaves_room_state_and_records_untouched() -> None:
    room = RoomRegistry().create(level=1, mode="local", seed=8)
    room.state = _capture_position()
    before_state = room.state
    before_turns = tuple(room._turns)
    before_counts = dict(room._counts)

    def failed_sampler(_sites):
        raise RuntimeError("measurement failed")

    room.engine.sampler = failed_sampler
    with pytest.raises(RuntimeError, match="measurement failed"):
        room.move(
            room.creator_id,
            {"type": "Move", "from": [2, 1], "to": [0, 3]},
        )

    assert room.state is before_state
    assert tuple(room._turns) == before_turns
    assert room._counts == before_counts


def test_odd_sized_live_opening_starts_both_players_on_same_playable_color() -> None:
    state = DeterministicToyEngine(board_size=5, live_rules=True).initial_state()

    assert all((row + col) % 2 == 1 for piece in state.pieces for (row, col), _ in piece.sites)
    assert len(state.pieces_of(0)) == len(state.pieces_of(1)) == 2


def test_live_rejoin_is_not_offered_onto_another_piece_candidate() -> None:
    engine = DeterministicToyEngine(level=2, live_rules=True)
    state = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 0.5), ((1, 2), 0.5)),),
            Piece("B", 0, (((1, 2), 1.0),)),
            Piece("C", 1, (((0, 1), 1.0),)),
        ),
    )

    assert not any(
        action.kind == "rejoin" and action.piece_id == "A" and action.target == (1, 2)
        for action in engine.legal_actions(state)
    )


def test_default_research_engine_keeps_legacy_mode_and_clone_configuration() -> None:
    research = DeterministicToyEngine(seed=42, level=2)
    live = DeterministicToyEngine(seed=42, level=2, live_rules=True)

    assert research.live_rules is False
    assert research.clone().live_rules is False
    assert live.clone().live_rules is True
    explicit_default = DeterministicToyEngine(seed=42, level=2, live_rules=False)
    assert research.initial_state() == explicit_default.initial_state()
    assert "live_rules" not in research.render(research.initial_state())
    assert live.render(live.initial_state())["live_rules"] is True

    sampler = lambda sites: sites[0]
    assert DeterministicToyEngine(seed=1, sampler=sampler, live_rules=True).clone().sampler is None

