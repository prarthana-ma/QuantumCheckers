"""Regression tests for the toy engine's level-four coherence countdown."""

from __future__ import annotations

from qcheckers.engine.protocol import GameState, MoveAction, Piece, SpreadAction
from qcheckers.engine.toy import DeterministicToyEngine


def test_decoherence_counts_down_then_collapses_the_piece() -> None:
    engine = DeterministicToyEngine(
        level=4,
        decoherence=True,
        decoherence_ticks=2,
        sampler=lambda sites: sites[-1],
    )
    state = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("p0-spread", 0, (((3, 0), 1.0),)),
            Piece("p0-mover", 0, (((3, 2), 1.0),)),
            Piece("p1-mover", 1, (((0, 3), 1.0),)),
        ),
    )

    split = next(
        action
        for action in engine.legal_actions(state)
        if isinstance(action, SpreadAction) and action.piece_id == "p0-spread"
    )
    after_split = engine.apply(state, split)
    spread_piece = after_split.state.piece("p0-spread")
    assert spread_piece.coherence == 2

    opponent_move = next(
        action
        for action in engine.legal_actions(after_split.state)
        if isinstance(action, MoveAction)
    )
    after_opponent = engine.apply(after_split.state, opponent_move)
    assert after_opponent.state.piece("p0-spread").coherence == 1
    assert after_opponent.state.piece("p0-spread").is_spread

    own_move = next(
        action
        for action in engine.legal_actions(after_opponent.state)
        if isinstance(action, MoveAction) and action.piece_id == "p0-mover"
    )
    after_expiry = engine.apply(after_opponent.state, own_move)

    collapsed = after_expiry.state.piece("p0-spread")
    assert collapsed.sites == ((spread_piece.sites[-1][0], 1.0),)
    assert collapsed.coherence is None
    assert len(after_expiry.events) == 1
    assert after_expiry.events[0].piece_id == "p0-spread"
    assert after_expiry.events[0].cause == "decoherence"
    assert after_expiry.events[0].sampled == spread_piece.sites[-1][0]


def test_decoherence_split_starts_at_configured_counter() -> None:
    engine = DeterministicToyEngine(
        level=4,
        decoherence=True,
        decoherence_ticks=5,
    )
    state = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("p0-a", 0, (((3, 0), 1.0),)),
            Piece("p0-b", 0, (((3, 2), 1.0),)),
            Piece("p1-a", 1, (((0, 3), 1.0),)),
        ),
    )
    split = next(
        action
        for action in engine.legal_actions(state)
        if isinstance(action, SpreadAction) and action.piece_id == "p0-a"
    )

    result = engine.apply(state, split)

    assert result.state.piece("p0-a").coherence == 5
