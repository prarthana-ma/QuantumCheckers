"""Production paper-rule wiring, exact board messages and atomic hardware failures."""
import math

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.rooms import ProtocolError, Room, resolve_action
from server.quantum_measure import IBMHardwareSampler, QuantumMeasurementError


def config(*entries):
    return tuple(sorted(entries))


def test_invalid_hardware_configuration_returns_clear_error_without_creating_room(monkeypatch):
    monkeypatch.delenv("QCHECKERS_DISABLE_HARDWARE", raising=False)
    monkeypatch.setenv("QISKIT_IBM_TOKEN", "test-token-never-submitted")
    monkeypatch.setenv("IBM_QUANTUM_TIMEOUT", "not-a-timeout")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post("/api/game", json={"level": 1, "mode": "local"})
        assert response.status_code == 503
        assert response.json()["detail"] == "IBM Quantum timeout must be a positive finite number"
        assert client.get("/api/health").json()["games"] == 0


def recv_state(socket):
    for _ in range(30):
        frame = socket.receive_json()
        if frame["type"] == "StateUpdate":
            return frame
    raise AssertionError("no state frame")


def test_default_app_uses_paper_rules_and_standard_opening(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post("/api/game", json={"level": 2, "mode": "local", "seed": 0})
        assert response.status_code == 201
        game = response.json()
        room = client.app.state.registry.require(game["game_id"])
        assert room.engine.name == "paper-quantum"
        assert room.engine.board_size == 8
        assert room.engine.max_plies == 1000
        assert len(room.state.pieces_of(0)) == len(room.state.pieces_of(1)) == 12
        assert not room.engine.allow_observe
        with client.websocket_connect(f"/ws/{game['game_id']}") as socket:
            socket.send_json({"type": "JoinGame", "player_id": game["player_id"]})
            before = recv_state(socket)
            action = next(action for action in before["legal"] if action["kind"] == "move")
            socket.send_json({"type": "Move", "from": action["origin"], "to": action["target"]})
            after = recv_state(socket)
            assert after["ply"] == before["ply"] + 1
            assert after["turn"] == 1
            assert after["you"] == 0
            assert after["legal"], "the shared local seat must control the second player's turn"
            assert after["board"]["paper_rules"] is True


def test_create_game_accepts_observe_opt_in(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post(
            "/api/game",
            json={"level": 1, "mode": "local", "allow_observe": True},
        )
        assert response.status_code == 201
        game = response.json()
        room = client.app.state.registry.require(game["game_id"])
        assert room.engine.allow_observe is True
        view = client.get(
            f"/api/game/{game['game_id']}/view",
            params={"player_id": game["player_id"]},
        ).json()
        assert view["board"]["allow_observe"] is True


def test_create_game_level_one_defaults_observe_off(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post("/api/game", json={"level": 1, "mode": "local"})
        assert response.status_code == 201
        game = response.json()
        room = client.app.state.registry.require(game["game_id"])
        assert room.engine.allow_observe is False
        view = client.get(
            f"/api/game/{game['game_id']}/view",
            params={"player_id": game["player_id"]},
        ).json()
        assert view["board"]["allow_observe"] is False


def test_create_game_level_four_defaults_observe_on(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post("/api/game", json={"level": 4, "mode": "local"})
        assert response.status_code == 201
        game = response.json()
        room = client.app.state.registry.require(game["game_id"])
        assert room.engine.allow_observe is True
        view = client.get(
            f"/api/game/{game['game_id']}/view",
            params={"player_id": game["player_id"]},
        ).json()
        assert view["board"]["allow_observe"] is True


def test_create_game_level_four_can_disable_observe(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        response = client.post(
            "/api/game",
            json={"level": 4, "mode": "local", "allow_observe": False},
        )
        assert response.status_code == 201
        game = response.json()
        room = client.app.state.registry.require(game["game_id"])
        assert room.engine.allow_observe is False
        view = client.get(
            f"/api/game/{game['game_id']}/view",
            params={"player_id": game["player_id"]},
        ).json()
        assert view["board"]["allow_observe"] is False


def test_paper_split_dispatch_validates_both_destinations(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    room = Room(game_id="paper-split", level=1, mode="local", seed=0, board_size=6, paper_rules=True)
    room.state = room.engine.state_from_amplitudes(
        {config(("A", (3, 2), False), ("B", (0, 1), False)): 1}, owners={"A": 0, "B": 1},
    )
    before = room.state
    with pytest.raises(ProtocolError):
        room.move(room.creator_id, {"type": "SplitMove", "from": [3, 2], "targets": [[2, 1], [0, 1]]})
    assert room.state is before
    room.move(room.creator_id, {"type": "SplitMove", "from": [3, 2], "targets": [[2, 3], [2, 1]]})
    assert room.state.piece("A").chance_at((3, 2)) == 0
    assert room.state.piece("A").chance_at((2, 1)) == pytest.approx(.5)
    assert room.state.piece("A").chance_at((2, 3)) == pytest.approx(.5)


def test_paper_merge_dispatch_uses_same_piece_sources_and_shared_target(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    room = Room(game_id="paper-merge", level=3, mode="local", seed=0, board_size=6, paper_rules=True)
    room.state = room.engine.state_from_amplitudes(
        {config(("A", (4, 1), False), ("B", (0, 1), False)): (1 + 1j)/2,
         config(("A", (4, 3), False), ("B", (0, 1), False)): (1 - 1j)/2},
        owners={"A": 0, "B": 1},
    )
    message = {"type": "MergeMove", "piece": "A", "sources": [[4, 1], [4, 3]], "target": [3, 2]}
    action = resolve_action(room.engine, room.state, message)
    assert action.piece_id == "A"
    assert action.other_origin == (4, 3)
    room.move(room.creator_id, message)
    assert room.state.piece("A").chance_at((3, 2)) == pytest.approx(1)


def test_second_hardware_measurement_failure_does_not_publish_partial_provenance():
    calls = []
    def runner(circuit, shots, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("provider unavailable")
        return "ibm-test", "first-job", {"0": 1}
    sampler = IBMHardwareSampler(token="fake", runner=runner)
    room = Room(game_id="paper-atomic", level=1, mode="local", seed=0, board_size=6, paper_rules=True, quantum_sampler=sampler)
    room.state = room.engine.state_from_amplitudes(
        {config(("A", a, False), ("B", b, False)): .5
         for a in ((5, 0), (5, 2)) for b in ((4, 1), (4, 3))},
        owners={"A": 0, "B": 1},
    )
    before = room.state
    with pytest.raises(QuantumMeasurementError):
        room.move(room.creator_id, {"type": "Move", "from": [5, 0], "to": [3, 2]})
    assert len(calls) == 2
    assert room.state is before
    assert room.last_quantum is None
    assert not room.quantum_pending
    assert room._turns == []


def test_branch_limit_refuses_action_without_mutating_room(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    room = Room(game_id="paper-limit", level=1, mode="local", seed=0, board_size=6, paper_rules=True)
    room.state = room.engine.state_from_amplitudes(
        {config(("A", (3, 2), False), ("B", (0, 1), False)): 1}, owners={"A": 0, "B": 1},
    )
    room.engine.max_branches = 1
    before = room.state
    with pytest.raises(ProtocolError) as exc:
        room.move(room.creator_id, {"type": "SplitMove", "from": [3, 2], "targets": [[2, 1], [2, 3]]})
    assert exc.value.code == "quantum_rule_error"
    assert room.state is before


@pytest.mark.parametrize("mode,budget", [("ai-medium", 200), ("ai-hard", 400)])
def test_production_tiers_use_live_tree_search(monkeypatch, mode, budget):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    room = Room(game_id="paper-ai", level=2, mode=mode, seed=0, paper_rules=True)
    assert room.agents[1].iterations == budget
    assert room.agents[1].name == f"live-mcts-{budget}"
    assert not room.engine.allow_observe


def test_ai_failure_can_be_retried_without_replaying_human_move(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    original = Room.play_ai_ply
    calls = []

    def flaky(room):
        calls.append(room.state.ply)
        if len(calls) == 1:
            raise QuantumMeasurementError("provider unavailable", "quantum_unavailable")
        return original(room)

    monkeypatch.setattr(Room, "play_ai_ply", flaky)
    with TestClient(create_app(tick_seconds=0)) as client:
        game = client.post("/api/game", json={"level": 0, "mode": "ai-easy", "seed": 0}).json()
        with client.websocket_connect(f"/ws/{game['game_id']}") as socket:
            socket.send_json({"type": "JoinGame", "player_id": game["player_id"]})
            before = recv_state(socket)
            action = before["legal"][0]
            socket.send_json({"type": "Move", "from": action["origin"], "to": action["target"]})
            human = recv_state(socket)
            assert human["ply"] == 1 and human["turn"] == 1
            assert socket.receive_json()["type"] == "Error"
            failed = recv_state(socket)
            assert failed["ply"] == 1 and failed["turn"] == 1
            socket.send_json({"type": "RetryAI"})
            recovered = recv_state(socket)
            assert recovered["ply"] == 2 and recovered["turn"] == 0
            assert calls == [1, 1]


def test_explicit_piece_identity_disambiguates_shared_square(monkeypatch):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    room = Room(game_id="paper-identity", level=2, mode="local", seed=0, board_size=6, paper_rules=True)
    room.state = room.engine.state_from_amplitudes(
        {config(("A", (3, 2), False), ("B", None, False), ("C", (0, 1), False)): 1/math.sqrt(2),
         config(("A", None, False), ("B", (3, 2), False), ("C", (0, 1), False)): 1/math.sqrt(2)},
        owners={"A": 0, "B": 0, "C": 1},
    )
    action = resolve_action(room.engine, room.state, {"type": "Move", "piece": "B", "from": [3, 2], "to": [2, 1]})
    assert action.piece_id == "B"
    room.move(room.creator_id, {"type": "Move", "piece": "B", "from": [3, 2], "to": [2, 1]})
    assert room.state.piece("A").chance_at((3, 2)) == pytest.approx(.5)
    assert room.state.piece("B").chance_at((2, 1)) == pytest.approx(.5)


@pytest.mark.parametrize("owner", [0, 1])
def test_level_zero_promotion_exposes_backward_king_moves_over_websocket(monkeypatch, owner):
    monkeypatch.setenv("QCHECKERS_DISABLE_HARDWARE", "1")
    with TestClient(create_app(tick_seconds=0)) as client:
        game = client.post("/api/game", json={"level": 0, "mode": "local", "seed": 0}).json()
        room = client.app.state.registry.require(game["game_id"])
        origin, target, opponent = ((1, 2), (0, 1), (5, 4)) if owner == 0 else ((6, 1), (7, 0), (2, 3))
        room.state = room.engine.state_from_amplitudes(
            {config(("K", origin, False), ("B", opponent, False)): 1},
            owners={"K": owner, "B": 1-owner}, turn=owner,
        )
        with client.websocket_connect(f"/ws/{game['game_id']}") as socket:
            socket.send_json({"type": "JoinGame", "player_id": game["player_id"]})
            recv_state(socket)
            socket.send_json({"type": "Move", "piece": "K", "from": origin, "to": target})
            crowned = recv_state(socket)
            piece = next(p for p in crowned["board"]["pieces"] if p["piece_id"] == "K")
            assert piece["king_sites"] == [[list(target), 1.0]]
            reply = crowned["legal"][0]
            socket.send_json({"type": "Move", "piece": reply["piece_id"], "from": reply["origin"], "to": reply["target"]})
            king_turn = recv_state(socket)
            backwards = next(a for a in king_turn["legal"] if a["piece_id"] == "K" and a["kind"] == "move")
            assert backwards["origin"] == list(target)
            assert backwards["target"][0] == (1 if owner == 0 else 6)
            socket.send_json({"type": "Move", "piece": "K", "from": backwards["origin"], "to": backwards["target"]})
            moved = recv_state(socket)
            piece = next(p for p in moved["board"]["pieces"] if p["piece_id"] == "K")
            assert piece["king_sites"] == [[backwards["target"], 1.0]]
