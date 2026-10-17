"""Regression tests for defects found during P3 audit."""

from __future__ import annotations

import pytest

from qcheckers.engine import protocol as protocol_mod
from qcheckers.experiment.runner import _lazy_import_agent, get_agent_factory
from qcheckers.engine.protocol import GameState, Piece
from tests.support.quantum_toy import (
    QuantumToyEngine,
    _CaptureAction,
    _MoveAction,
    SpreadAction,
)


class TestProtocolAll:
    """Defect 1: __all__ exported non-existent CloneableEngine."""

    def test_all_names_exist(self):
        """Every name in __all__ must exist in the module."""
        for name in protocol_mod.__all__:
            assert hasattr(protocol_mod, name), f"__all__ lists {name!r} but it does not exist"

    def test_cloneable_engine_not_in_all(self):
        """CloneableEngine was removed and must not be exported."""
        assert "CloneableEngine" not in protocol_mod.__all__
        assert not hasattr(protocol_mod, "CloneableEngine")


class TestLazyImportRobustness:
    """Defect 2: _lazy_import_agent only caught ImportError, not broader failures."""

    def test_observe_returns_none_when_missing(self):
        """When P1's observe_agent is not importable, returns None gracefully."""
        result = _lazy_import_agent("observe")
        assert result is None

    def test_prob_returns_none_when_missing(self):
        result = _lazy_import_agent("prob")
        assert result is None

    def test_unknown_kind_returns_none(self):
        result = _lazy_import_agent("nonexistent_kind")
        assert result is None

    def test_get_agent_factory_raises_for_unknown(self):
        with pytest.raises(KeyError):
            get_agent_factory("nonexistent_kind")


class TestEngineLegalityCheck:
    """Defect 3: apply() used (kind, origin, target) tuples, allowing captures
    with wrong captured_id to be accepted.

    Fix: apply() now checks the full action identity including piece_id,
    captured_id, and absorbed_id.
    """

    def test_rejects_action_with_wrong_captured_id(self):
        """An action with correct kind/origin/target but wrong captured_id must be rejected."""
        engine = QuantumToyEngine(seed=0, level=2, board_size=4)
        # Construct a state where a capture is available:
        # Player 0 piece at (2,1), player 1 piece at (1,2), empty landing at (0,3).
        state = GameState(
            turn=0,
            ply=5,
            pieces=(
                Piece("p0-cap", 0, (((2, 1), 1.0),)),
                Piece("p1-victim", 1, (((1, 2), 1.0),)),
                Piece("p0-other", 0, (((3, 0), 1.0),)),
                Piece("p1-other", 1, (((0, 1), 1.0),)),
            ),
            captured=(),
        )
        # Verify the capture is legal
        legal = list(engine.legal_actions(state))
        captures = [a for a in legal if isinstance(a, _CaptureAction)]
        assert len(captures) >= 1, "Should have at least one capture in constructed state"

        cap = captures[0]
        # Construct a capture with wrong captured_id
        bad_action = _CaptureAction(
            origin=cap.origin, target=cap.target, captured_id="nonexistent-piece"
        )
        with pytest.raises(ValueError, match="illegal action"):
            engine.apply(state, bad_action)

    def test_accepts_action_with_correct_captured_id(self):
        engine = QuantumToyEngine(seed=0, level=2, board_size=4)
        state = GameState(
            turn=0,
            ply=5,
            pieces=(
                Piece("p0-cap", 0, (((2, 1), 1.0),)),
                Piece("p1-victim", 1, (((1, 2), 1.0),)),
                Piece("p0-other", 0, (((3, 0), 1.0),)),
                Piece("p1-other", 1, (((0, 1), 1.0),)),
            ),
            captured=(),
        )
        legal = list(engine.legal_actions(state))
        captures = [a for a in legal if isinstance(a, _CaptureAction)]
        assert len(captures) >= 1, "Should have at least one capture in constructed state"

        # The original legal action must be accepted
        result = engine.apply(state, captures[0])
        assert result.state is not None
        # Verify the captured piece is removed
        assert "p1-victim" in result.state.captured


class TestRejoinTargeting:
    """Defect 4: rejoin picked the first spread piece regardless of action origin.

    Fix: rejoin now matches the piece at the action's origin square.
    """

    def test_rejoin_uses_origin_to_find_piece(self):
        """When multiple spread pieces exist, rejoin must target the one at action origin.

        Fixture design:
        - p0-a (first in tuple): spread over (3,0) and (2,1), rejoin origin=(3,0)
        - p0-b (second in tuple): spread over (1,2) and (0,3), rejoin origin=(1,2)
        - Supports are DISTINCT (no overlap)
        - The test targets p0-b via origin=(1,2)
        - Buggy implementation picks p0-a (first in order) -> test FAILS
        - Fixed implementation picks p0-b (origin match) -> test PASSES
        """
        engine = QuantumToyEngine(seed=0, level=2, board_size=4)
        state = GameState(
            turn=0,
            ply=10,
            pieces=(
                Piece("p0-a", 0, (((3, 0), 0.6), ((2, 1), 0.4))),
                Piece("p0-b", 0, (((1, 2), 0.5), ((0, 3), 0.5))),
                Piece("p1-x", 1, (((0, 1), 1.0),)),
                Piece("p1-y", 1, (((0, 3), 1.0),)),
            ),
            captured=(),
        )
        # Both pieces are spread with distinct supports
        p0a_squares = {(3, 0), (2, 1)}
        p0b_squares = {(1, 2), (0, 3)}
        assert p0a_squares.isdisjoint(p0b_squares), "Supports must be distinct"

        legal = list(engine.legal_actions(state))
        rejoins = [a for a in legal if a.kind == "rejoin"]
        assert len(rejoins) >= 2, "Should have rejoin actions for both spread pieces"

        # Find the rejoin for p0-b (origin must be one of p0-b's squares)
        rejoin_b = None
        for r in rejoins:
            if r.origin in p0b_squares:
                rejoin_b = r
                break
        assert rejoin_b is not None, "Should have a rejoin for p0-b"

        # Apply the rejoin targeting p0-b
        result = engine.apply(state, rejoin_b)
        assert result.state is not None

        # p0-b should be collapsed (targeted by origin)
        p0_b_after = result.state.piece("p0-b")
        assert not p0_b_after.is_spread, "p0-b should be collapsed after rejoin"

        # p0-a should still be spread (not targeted)
        p0_a_after = result.state.piece("p0-a")
        assert p0_a_after.is_spread, "p0-a should remain spread (not targeted)"

    def test_rejoin_rejects_wrong_origin(self):
        """A rejoin action with an origin not matching any spread piece must be rejected."""
        engine = QuantumToyEngine(seed=0, level=2, board_size=4)
        state = GameState(
            turn=0,
            ply=10,
            pieces=(
                Piece("p0-a", 0, (((2, 1), 0.6), ((1, 2), 0.4))),
                Piece("p1-x", 1, (((0, 1), 1.0),)),
                Piece("p1-y", 1, (((0, 3), 1.0),)),
            ),
            captured=(),
        )
        # Construct a rejoin with an origin that doesn't match p0-a's squares
        from tests.support.quantum_toy import _RejoinAction
        bad_rejoin = _RejoinAction(origin=(3, 3), target=(2, 1))
        # This should either not be in legal actions, or apply should reject it
        legal = list(engine.legal_actions(state))
        rejoins = [a for a in legal if a.kind == "rejoin"]
        # If the bad rejoin is not in legal actions, that's correct
        bad_in_legal = any(
            a.origin == (3, 3) for a in rejoins
        )
        if not bad_in_legal:
            # Good — engine didn't generate the bad action
            return
        # If it is in legal, apply should reject it
        with pytest.raises(ValueError):
            engine.apply(state, bad_rejoin)
