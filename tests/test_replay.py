"""Tests for replay export."""

from __future__ import annotations

import json

import pytest

from qcheckers.engine.protocol import (
    Action,
    CollapseEvent,
    GameState,
    ObserveAction,
    Outcome,
    Piece,
    Square,
    Transition,
)
from qcheckers.experiment.replay import (
    REPLAY_VERSION,
    build_replay,
    deserialize_replay,
    event_to_replay,
    export_replay,
    import_replay,
    serialize_replay,
    state_to_pieces,
    validate_replay,
)
from tests.support.quantum_toy import QuantumToyEngine


def _make_transition():
    """Build a small synthetic game and return its components."""
    engine = QuantumToyEngine(seed=5, level=2, board_size=4)
    initial = engine.initial_state()
    legal = list(engine.legal_actions(initial))
    action = legal[0]
    transition = engine.apply(initial, action)
    return engine, initial, [(action, transition)], transition.state


class TestStateToPieces:
    def test_basic(self):
        engine = QuantumToyEngine(seed=0)
        state = engine.initial_state()
        pieces = state_to_pieces(state)
        assert isinstance(pieces, list)
        assert len(pieces) > 0
        for p in pieces:
            assert "piece_id" in p
            assert "owner" in p
            assert "sites" in p

    def test_json_serializable(self):
        engine = QuantumToyEngine(seed=0)
        state = engine.initial_state()
        pieces = state_to_pieces(state)
        # Must be directly JSON-serializable
        json.dumps(pieces)


class TestActionToReplay:
    def test_move_action(self):
        from tests.support.quantum_toy import _MoveAction
        a = _MoveAction(origin=(3, 0), target=(2, 1))
        r = __import__("qcheckers.experiment.replay", fromlist=["action_to_replay"]).action_to_replay(a, 1, 0)
        assert r.kind == "move"
        assert r.origin == [3, 0]
        assert r.target == [2, 1]
        assert r.player == 0
        assert r.ply == 1


class TestEventToReplay:
    def test_collapse_event(self):
        e = CollapseEvent(ply=3, piece_id="p0-0", owner=0, cause="observe",
                          chances=(( (0, 1), 1.0),), sampled=(2, 1), probability=1.0)
        r = event_to_replay(e, 3)
        assert r.piece_id == "p0-0"
        assert r.resolved_to == [2, 1]
        assert r.cause == "observe"
        assert r.ply == 3


class TestBuildReplay:
    def test_builds_valid_payload(self):
        engine, initial, transitions, final = _make_transition()
        outcome = engine.outcome(final) or Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        assert payload.replay_version == REPLAY_VERSION
        assert payload.experiment_id == "test"
        assert payload.n_plies == len(transitions)
        assert len(payload.actions) == len(transitions)

    def test_no_actions(self):
        engine = QuantumToyEngine(seed=0)
        initial = engine.initial_state()
        outcome = Outcome(winner=None, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=0,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=[],
            final_state=initial,
            outcome=outcome,
        )
        assert payload.n_plies == 0
        assert payload.actions == []


class TestSerializeDeserialize:
    def test_round_trip(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        serialized = serialize_replay(payload)
        restored = deserialize_replay(serialized)
        assert restored == payload

    def test_deserialize_invalid_json(self):
        with pytest.raises(ValueError):
            deserialize_replay("not json")

    def test_deserialize_missing_fields(self):
        with pytest.raises(ValueError, match="missing"):
            deserialize_replay('{"replay_version": "1.0"}')

    def test_json_safe(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        s = serialize_replay(payload)
        # Must be valid JSON
        json.loads(s)


class TestValidateReplay:
    def test_valid(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        errors = validate_replay(payload)
        assert errors == []

    def test_bad_version(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        object.__setattr__(payload, "replay_version", "9.9")
        errors = validate_replay(payload)
        assert any("version" in e for e in errors)

    def test_n_plies_mismatch(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        object.__setattr__(payload, "n_plies", 99)
        errors = validate_replay(payload)
        assert any("n_plies" in e for e in errors)

    def test_outcome_winner_inconsistency(self):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        object.__setattr__(payload, "outcome", "draw")
        errors = validate_replay(payload)
        assert any("winner" in e for e in errors)


class TestExportImport:
    def test_export_import_round_trip(self, tmp_path):
        engine, initial, transitions, final = _make_transition()
        outcome = Outcome(winner=0, reason="test")
        payload = build_replay(
            experiment_id="test",
            game_id="test-g0",
            seed=5,
            board_size=4,
            agents={"0": "random", "1": "mcts"},
            initial_state=initial,
            transitions=transitions,
            final_state=final,
            outcome=outcome,
        )
        p = tmp_path / "replay.json"
        export_replay(payload, p)
        assert p.exists()
        restored = import_replay(p)
        assert restored == payload

    def test_import_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_replay(tmp_path / "nonexistent.json")
