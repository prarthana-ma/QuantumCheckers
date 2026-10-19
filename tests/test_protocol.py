"""Tests for the shared engine contract and its compatibility helpers."""

from __future__ import annotations

import pytest

from qcheckers.engine.protocol import (
    CaptureAction,
    CollapseEvent,
    GameOutcome,
    GameState,
    MergeAction,
    MoveAction,
    ObserveAction,
    Outcome,
    Piece,
    RejoinAction,
    Step,
    Transition,
    board_chances,
    board_size_of,
    clone_engine,
    describe_state,
    uncertain_pieces,
)
from qcheckers.engine.toy import DeterministicToyEngine


def test_piece_requires_a_normalized_distribution_and_distinct_squares() -> None:
    with pytest.raises(ValueError, match="sum to"):
        Piece("p0", 0, (((1, 0), 0.4),))

    with pytest.raises(ValueError, match="twice"):
        Piece("p0", 0, (((1, 0), 0.5), ((1, 0), 0.5)))


def test_piece_helpers_preserve_distribution_and_coherence() -> None:
    piece = Piece("p0", 0, (((1, 0), 0.5), ((2, 1), 0.5)), coherence=3)

    assert piece.is_spread
    assert piece.squares == ((1, 0), (2, 1))
    assert piece.chance_at((2, 1)) == 0.5
    assert piece.chance_at((3, 2)) == 0.0
    assert piece.with_sites((((3, 2), 1.0),), coherence=2) == Piece(
        "p0", 0, (((3, 2), 1.0),), coherence=2
    )


def test_state_helpers_return_consistent_board_and_uncertainty_views() -> None:
    first = Piece("p0", 0, (((0, 1), 0.6), ((1, 2), 0.4)))
    second = Piece("p1", 1, (((0, 1), 0.8), ((2, 2), 0.2)))
    state = GameState(turn=0, ply=4, pieces=(first, second))

    assert state.piece("p0") is first
    assert state.pieces_of(1) == (second,)
    assert state.spread_pieces() == (first, second)
    assert state.certainty() == pytest.approx(0.7)
    assert state.occupancy()[(0, 1)] == (1, 0.8)
    assert board_size_of(state) == 3
    assert board_chances(state, size=3)[1] == [0.0, 0.8]
    assert board_chances(state, size=3)[5] == [0.4, 0.0]
    assert uncertain_pieces(state) == (first, second)
    assert uncertain_pieces(state, owner=1) == (second,)
    assert describe_state(state)["certainty"] == pytest.approx(0.7)


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (
            MoveAction(piece_id="p0", origin=(3, 0), target=(2, 1)),
            {"kind": "move", "piece_id": "p0", "origin": [3, 0], "target": [2, 1]},
        ),
        (
            CaptureAction(
                piece_id="p0", origin=(3, 0), jumped=(2, 1), target=(1, 2)
            ),
            {
                "kind": "capture",
                "piece_id": "p0",
                "origin": [3, 0],
                "jumped": [2, 1],
                "target": [1, 2],
            },
        ),
        (
            RejoinAction(piece_id="p0", origin=(2, 1), target=(3, 0)),
            {"kind": "rejoin", "piece_id": "p0", "origin": [2, 1], "target": [3, 0]},
        ),
        (
            ObserveAction(piece_id="p0", origin=(2, 1)),
            {"kind": "observe", "piece_id": "p0", "origin": [2, 1]},
        ),
        (
            MergeAction(piece_id="p0", origin=(2, 1), other_piece_id="p1"),
            {
                "kind": "merge",
                "piece_id": "p0",
                "origin": [2, 1],
                "other_piece_id": "p1",
            },
        ),
    ],
)
def test_actions_serialize_to_json_friendly_values(action, expected) -> None:
    assert action.to_json() == expected


def test_aliases_and_collapse_event_serialization() -> None:
    """Legacy names stay importable, and collapse events log the sampled square."""
    assert Outcome is GameOutcome
    assert Transition is Step

    event = CollapseEvent(
        ply=3,
        piece_id="p0",
        owner=0,
        cause="observe",
        chances=(((2, 1), 1.0),),
        sampled=(2, 1),
        probability=1.0,
    )
    assert event.sampled == (2, 1)
    assert event.to_json()["sampled"] == [2, 1]


def test_clone_engine_passes_the_requested_seed_to_an_isolated_clone() -> None:
    engine = DeterministicToyEngine(seed=4, level=1)

    cloned = clone_engine(engine, seed=19)

    assert cloned is not engine
    assert getattr(cloned, "seed") == 19
    assert cloned.level == engine.level
