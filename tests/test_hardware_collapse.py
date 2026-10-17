"""Live hardware-collapse tests.

These pin the bounded feature "an actual IBM Quantum measurement decides the square a
live collapse writes into game state":

* the circuit genuinely encodes the piece's distribution and maps every measured
  bitstring back to the right square (checked against a real local simulator);
* the engine only reaches for injected hardware on a collapse, never on an ordinary
  move or a split;
* a live room's collapse square comes from the sampler and carries provenance;
* a hardware failure leaves the room completely unchanged and raises a clear error --
  there is no Aer or toy-RNG fallback on the live path;
* the default engine and its clones stay deterministic and QPU-free.

No real QPU job is run here: ``IBMHardwareSampler`` takes a ``runner`` so tests replace
the whole IBM boundary. Running one real hardware job still requires a valid
``IBM_CLOUD_API_KEY`` (see docs/DEPLOYMENT.md) and is not covered by these tests.
"""

from __future__ import annotations

import pytest
from qiskit_aer import AerSimulator

from qcheckers.engine.protocol import ObserveAction, SpreadAction
from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.quantum import game_measure
from server.quantum_measure import (
    IBMHardwareSampler,
    QuantumMeasurementError,
    sampler_from_env,
)
from server.rooms import Room

THREE_SITE = (((0, 1), 0.5), ((1, 0), 0.25), ((1, 2), 0.25))
TWO_SITE = (((2, 1), 0.5), ((3, 0), 0.5))


def _recv_type(ws, expected: str, limit: int = 60) -> dict:
    """Read frames from a live socket until one of type ``expected`` arrives."""
    for _ in range(limit):
        frame = ws.receive_json()
        if frame.get("type") == expected:
            return frame
    raise AssertionError(f"no {expected!r} frame within {limit} reads")


# ---------------------------------------------------------------------------
# Circuit <-> square mapping
# ---------------------------------------------------------------------------


def test_three_site_mapping_matches_the_engine_convention() -> None:
    """|00>=site0, |01>=site1, |10>=site2, and |11> is left empty."""
    circuit, mapping = game_measure.build_measurement_circuit(THREE_SITE)
    assert circuit.num_qubits == 2
    assert mapping == {"00": (0, 1), "01": (1, 0), "10": (1, 2)}
    assert game_measure.qubits_for(3) == 2


def test_two_site_mapping_uses_a_single_qubit() -> None:
    circuit, mapping = game_measure.build_measurement_circuit(TWO_SITE)
    assert circuit.num_qubits == 1
    assert mapping == {"0": (2, 1), "1": (3, 0)}


def test_circuit_sampling_reproduces_the_target_distribution() -> None:
    """The circuit is a real encoding: its Born-rule frequencies are the weights."""
    simulator = AerSimulator()
    circuit, mapping = game_measure.build_measurement_circuit(THREE_SITE)
    counts = simulator.run(circuit, shots=8000).result().get_counts()
    total = sum(counts.values())
    for bitstring, square in mapping.items():
        target = dict(THREE_SITE)[square]
        assert abs(counts.get(bitstring, 0) / total - target) < 0.05
    # The unused fourth basis state stays (near) empty.
    assert counts.get("11", 0) == 0


def test_bitstring_to_square_returns_none_for_the_unused_state() -> None:
    assert game_measure.bitstring_to_square("00", THREE_SITE) == (0, 1)
    assert game_measure.bitstring_to_square("11", THREE_SITE) is None


def test_deterministic_fallback_takes_the_heaviest_site_and_breaks_ties_first() -> None:
    """Documented policy: highest weight wins; an exact tie goes to the first site."""
    sites = (((0, 1), 0.25), ((1, 0), 0.5), ((1, 2), 0.25))
    assert game_measure.deterministic_fallback(sites) == (1, 0)
    tie = (((5, 5), 0.5), ((6, 6), 0.5))
    assert game_measure.deterministic_fallback(tie) == (5, 5)


# ---------------------------------------------------------------------------
# Engine injection
# ---------------------------------------------------------------------------


def test_default_engine_is_seeded_and_has_no_sampler() -> None:
    first = DeterministicToyEngine(seed=5, level=2)
    second = DeterministicToyEngine(seed=5, level=2)
    assert first.sampler is None
    draws_a = [first._sample_sites(THREE_SITE) for _ in range(6)]
    draws_b = [second._sample_sites(THREE_SITE) for _ in range(6)]
    assert draws_a == draws_b, "the seeded device must stay reproducible"


def test_hardware_sampler_rejects_more_than_one_shot() -> None:
    with pytest.raises(QuantumMeasurementError) as info:
        IBMHardwareSampler(token="fake", shots=2, runner=_fixed_bitstring_runner("00"))

    assert info.value.code == "quantum_configuration_error"
    assert "one shot" in str(info.value).lower()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_hardware_sampler_rejects_non_positive_or_non_finite_timeout(timeout: float) -> None:
    with pytest.raises(QuantumMeasurementError) as info:
        IBMHardwareSampler(token="fake", timeout=timeout, runner=_fixed_bitstring_runner("00"))

    assert info.value.code == "quantum_configuration_error"
    assert "positive finite" in str(info.value).lower()


def test_clone_drops_the_sampler_so_rollouts_never_hit_hardware() -> None:
    calls: list[object] = []

    def sampler(sites):
        calls.append(sites)
        return sites[0][0], sites[0][1]

    engine = DeterministicToyEngine(seed=0, level=2, sampler=sampler)
    assert engine.sampler is sampler
    assert engine.clone().sampler is None


def test_injected_sampler_owns_the_collapse_choice() -> None:
    engine = DeterministicToyEngine(
        seed=0, level=2, allow_observe=True, sampler=lambda sites: ((9, 9), 1.0)
    )
    state = engine.initial_state()
    spread = [
        action
        for action in engine.legal_actions(state)
        if isinstance(action, SpreadAction)
    ][0]
    step = engine.apply(state, spread)
    # Pass the opponent's turn so seat 0 may act on its own spread piece again.
    opponent = [
        action
        for action in engine.legal_actions(step.state)
        if action.kind in ("move", "capture")
    ][0]
    step = engine.apply(step.state, opponent)
    observe = [
        action
        for action in engine.legal_actions(step.state)
        if isinstance(action, ObserveAction)
    ][0]
    resolved = engine.apply(step.state, observe)
    assert resolved.events[-1].sampled == (9, 9)
    assert resolved.state.piece(observe.piece_id).squares == ((9, 9),)


# ---------------------------------------------------------------------------
# Live room: hardware sampler drives the collapse
# ---------------------------------------------------------------------------


def _fixed_bitstring_runner(bitstring: str):
    """A fake IBM boundary that always reports ``bitstring`` on one shot."""

    def runner(circuit, shots, *, token, instance, backend_name, timeout):
        assert shots == 1, "live collapses must submit exactly one shot"
        return "ibm_fake_backend", "job-123", {bitstring: 1}

    return runner


def _wait_for(predicate, *, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """Poll ``predicate`` until true or ``timeout`` elapses.

    Room state is written by the server's WebSocket task and read by the test
    thread. The ``StateUpdate`` frame is serialised as it is built, so receiving it
    does not strictly mean the shared ``room.state`` reference is already swapped.
    A single read therefore races and fails intermittently; polling removes the race
    without weakening the assertion, which still must become true.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            # The piece may be mid-replacement; keep polling rather than masking a
            # genuine failure, which will surface once the timeout expires.
            pass
        time.sleep(interval)
    return False


def _room_to_split_and_observe(room: Room) -> ObserveAction:
    """Split seat 0's first piece, pass seat 1's turn, and return the Observe action."""
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(room.creator_id, {"type": "SplitMove", "from": list(spread.origin)})
    opponent = room.engine.legal_actions(room.state)[0]
    room.move(
        room.creator_id,
        {"type": "Move", "from": list(opponent.origin), "to": list(opponent.target)},
    )
    return [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, ObserveAction)
    ][0]


def test_live_observe_takes_its_square_from_the_hardware_result() -> None:
    sampler = IBMHardwareSampler(token="fake", runner=_fixed_bitstring_runner("00"))
    room = Room(game_id="qk-hw", level=2, mode="local", seed=0, quantum_sampler=sampler)
    observe = _room_to_split_and_observe(room)
    origin = room.state.piece(observe.piece_id).sites[0][0]

    room.move(room.creator_id, {"type": "ObserveMove", "square": list(observe.origin)})

    resolved = room.state.piece(observe.piece_id)
    assert resolved.squares == (origin,), "|00> maps to the piece's origin square"
    assert sampler.last is not None
    assert sampler.last.backend == "ibm_fake_backend"
    assert sampler.last.job_id == "job-123"
    assert sampler.last.used == "measured"


def test_state_update_exposes_backend_provenance_for_the_collapse() -> None:
    sampler = IBMHardwareSampler(token="fake", runner=_fixed_bitstring_runner("01"))
    room = Room(game_id="qk-hw", level=2, mode="local", seed=0, quantum_sampler=sampler)
    observe = _room_to_split_and_observe(room)
    sites = room.state.piece(observe.piece_id).sites
    room.move(room.creator_id, {"type": "ObserveMove", "square": list(observe.origin)})

    view = room.view(room.creator_id)
    assert view["quantum"]["enabled"] is True
    assert view["quantum"]["backend"] == "ibm_fake_backend"
    assert view["quantum"]["pending"] is False
    assert view["quantum_pending"] is False
    # The collapse event the browser reads names the backend that resolved the piece.
    assert view["last_event"]["by"] == "observe"
    assert view["last_event"]["quantum"]["backend"] == "ibm_fake_backend"
    assert view["last_event"]["sampled"] == list(sites[1][0]), "|01> -> second site"


def test_unused_basis_state_takes_the_documented_fallback() -> None:
    # "11" is not a candidate square, so the deterministic fallback runs.
    sampler = IBMHardwareSampler(token="fake", runner=_fixed_bitstring_runner("11"))
    room = Room(game_id="qk-hw", level=2, mode="local", seed=0, quantum_sampler=sampler)
    observe = _room_to_split_and_observe(room)
    sites = room.state.piece(observe.piece_id).sites
    expected = game_measure.deterministic_fallback(sites)

    room.move(room.creator_id, {"type": "ObserveMove", "square": list(observe.origin)})

    assert room.state.piece(observe.piece_id).squares == (expected,)
    assert sampler.last is not None and sampler.last.used == "invalid_fallback"
    assert sampler.last.bitstring == "11"


def test_no_hardware_job_for_a_classical_move_or_a_split() -> None:
    calls: list[str] = []

    def counting_runner(circuit, shots, *, token, instance, backend_name, timeout):
        calls.append("job")
        return "ibm_fake_backend", "job-x", {"00": 1}

    sampler = IBMHardwareSampler(token="fake", runner=counting_runner)
    room = Room(game_id="qk-hw", level=2, mode="local", seed=0, quantum_sampler=sampler)
    room.move(room.creator_id, {"type": "Move", "from": [3, 1], "to": [2, 0]})
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(room.creator_id, {"type": "SplitMove", "from": list(spread.origin)})
    assert calls == [], "only a real collapse may submit a QPU job"


# ---------------------------------------------------------------------------
# Failure: no fallback, no partial mutation
# ---------------------------------------------------------------------------


def test_hardware_failure_leaves_the_room_unchanged_and_raises() -> None:
    def failing_runner(circuit, shots, *, token, instance, backend_name, timeout):
        raise RuntimeError("provider error: super-secret-token")

    sampler = IBMHardwareSampler(token="fake", runner=failing_runner)
    room = Room(game_id="qk-hw", level=2, mode="local", seed=0, quantum_sampler=sampler)
    observe = _room_to_split_and_observe(room)
    before = room.view(room.creator_id)

    with pytest.raises(QuantumMeasurementError) as info:
        room.move(room.creator_id, {"type": "ObserveMove", "square": list(observe.origin)})

    assert info.value.code == "quantum_unavailable"
    assert "super-secret-token" not in str(info.value), "credentials must never leak"
    after = room.view(room.creator_id)
    assert after["board"] == before["board"]
    assert after["ply"] == before["ply"]
    assert after["turn"] == before["turn"]
    assert room.quantum_pending is False, "a failed measurement must clear pending"


def test_level_four_decoherence_expiry_is_also_hardware_backed() -> None:
    """The other ``_sample_sites`` path: the auto-collapse at zero coherence.

    With a one-tick counter the fresh split expires on the very next ply, so this proves
    the decoherence expiry -- not just Observe -- resolves through the injected sampler.
    """
    calls: list[tuple] = []

    def sampler(sites):
        calls.append(sites)
        return sites[0][0], sites[0][1]

    engine = DeterministicToyEngine(
        seed=0, level=4, decoherence=True, decoherence_ticks=1, sampler=sampler
    )
    state = engine.initial_state()
    spread = [
        action
        for action in engine.legal_actions(state)
        if isinstance(action, SpreadAction)
    ][0]
    step = engine.apply(state, spread)
    assert not calls, "creating the split is not a collapse and must not measure"
    opponent = [
        action
        for action in engine.legal_actions(step.state)
        if action.kind in ("move", "capture")
    ][0]
    expired = engine.apply(step.state, opponent)
    assert calls, "the decoherence expiry must resolve through the injected sampler"
    assert expired.state.last_event is not None
    assert expired.state.last_event.cause == "decoherence"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


#: Every variable ``sampler_from_env`` accepts. Tests that assert the *absence* of
#: hardware mode must clear all of them, or they pass on a clean machine and fail on a
#: developer box that happens to have a token exported.
_TOKEN_ENV_VARS = ("QISKIT_IBM_TOKEN", "IBM_CLOUD_API_KEY", "IBM_QUANTUM_API_KEY")


def _clear_tokens(monkeypatch) -> None:
    for name in _TOKEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_sampler_from_env_is_none_without_credentials(monkeypatch) -> None:
    _clear_tokens(monkeypatch)
    assert sampler_from_env() is None


def test_sampler_from_env_rejects_invalid_timeout_with_sanitized_error(monkeypatch) -> None:
    _clear_tokens(monkeypatch)
    monkeypatch.setenv("QISKIT_IBM_TOKEN", "fake-token")
    monkeypatch.setenv("IBM_QUANTUM_TIMEOUT", "private-malformed-value")

    with pytest.raises(QuantumMeasurementError) as info:
        sampler_from_env(runner=_fixed_bitstring_runner("00"))

    assert info.value.code == "quantum_configuration_error"
    assert "positive finite" in str(info.value).lower()
    assert "private-malformed-value" not in str(info.value)


def test_sampler_from_env_accepts_the_current_token_variable(monkeypatch) -> None:
    """``QISKIT_IBM_TOKEN`` is the name current qiskit-ibm-runtime reads."""
    _clear_tokens(monkeypatch)
    monkeypatch.setenv("QISKIT_IBM_TOKEN", "fake-token")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_fake_backend")
    monkeypatch.delenv("IBM_QUANTUM_TIMEOUT", raising=False)
    sampler = sampler_from_env(runner=_fixed_bitstring_runner("00"))
    assert isinstance(sampler, IBMHardwareSampler)
    assert sampler.backend_label == "ibm_fake_backend"


def test_current_token_variable_wins_over_legacy_names(monkeypatch) -> None:
    """Precedence is explicit, so a stale legacy variable cannot shadow the real one."""
    monkeypatch.setenv("QISKIT_IBM_TOKEN", "current-token")
    monkeypatch.setenv("IBM_CLOUD_API_KEY", "legacy-token")
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "older-token")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_fake_backend")
    monkeypatch.delenv("IBM_QUANTUM_TIMEOUT", raising=False)
    sampler = sampler_from_env(runner=_fixed_bitstring_runner("00"))
    assert sampler._token == "current-token"  # noqa: SLF001 - asserting the precedence contract


def test_sampler_from_env_builds_a_sampler_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("IBM_CLOUD_API_KEY", "fake-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE", "crn:v1:fake")
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_fake_backend")
    monkeypatch.delenv("IBM_QUANTUM_TIMEOUT", raising=False)
    sampler = sampler_from_env(runner=_fixed_bitstring_runner("00"))
    assert isinstance(sampler, IBMHardwareSampler)
    assert sampler.backend_label == "ibm_fake_backend"


def test_a_room_without_credentials_runs_the_plain_seeded_game(monkeypatch) -> None:
    _clear_tokens(monkeypatch)
    room = Room(game_id="qk-off", level=2, mode="local", seed=0)
    assert room.quantum_sampler is None
    assert room.engine.sampler is None
    assert room.view(room.creator_id)["quantum"]["enabled"] is False


# ---------------------------------------------------------------------------
# End to end over the WebSocket: a clear error, and an unchanged board
# ---------------------------------------------------------------------------


def test_websocket_observe_reports_quantum_unavailable_and_keeps_the_board(
    monkeypatch,
) -> None:
    """A hardware outage refuses the move with a clear Error; nothing mutates."""
    from fastapi.testclient import TestClient

    from server.app import create_app

    # Credentials present -> the room is hardware-backed; the IBM boundary itself fails.
    monkeypatch.setenv("IBM_CLOUD_API_KEY", "fake-key-for-test")

    def unavailable(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("server.quantum_measure._run_ibm_measurement", unavailable)

    with TestClient(create_app(paper_rules=False, tick_seconds=0.0, log_path=None)) as client:
        created = client.post("/api/game", json={"level": 2, "mode": "local", "seed": 0}).json()
        game_id, player_id = created["game_id"], created["player_id"]
        room = client.app.state.registry.require(game_id)
        observe = _room_to_split_and_observe(room)
        before = room.view(player_id)

        with client.websocket_connect(f"/ws/{game_id}") as ws:
            ws.send_json({"type": "JoinGame", "player_id": player_id})
            ws.send_json({"type": "ObserveMove", "square": list(observe.origin)})
            error = None
            for _ in range(10):
                frame = ws.receive_json()
                if frame.get("type") == "Error":
                    error = frame
                    break
            assert error is not None, "the client must receive a clear Error frame"
            assert error["code"] == "quantum_unavailable"
            assert "fake-key-for-test" not in error["message"], "no credential in an error"

        after = room.view(player_id)
        assert after["board"] == before["board"]
        assert after["ply"] == before["ply"]


def test_resignation_serializes_with_a_pending_hardware_measurement(monkeypatch) -> None:
    """REGRESSION: Resign must contend for the same room lock as a hardware-backed move.

    The failure this pins down: Resign used to bypass the room lock, so while a collapse
    was blocked inside a QPU measurement another connection could resign, finalize the
    game, and then the blocked move would still commit -- a move applied *after* game
    over. Two independent discriminators are recorded, so the test fails on the old code
    for the right reason rather than by timing:

    * the observe's ``_apply`` must see ``status == "playing"`` (with the bug it sees
      ``"over"`` because resignation already finalized the game);
    * ``resign()`` must start with no measurement pending (with the bug it runs while the
      QPU job is still in flight).
    """
    import threading
    import time

    from fastapi.testclient import TestClient

    from server.app import create_app
    from server.rooms import ProtocolError

    monkeypatch.setenv("IBM_CLOUD_API_KEY", "fake-key-for-test")
    gate = threading.Event()

    def blocking_runner(circuit, shots, *, token, instance, backend_name, timeout):
        # Stand in for a queued QPU job: block until the test releases it.
        gate.wait(timeout=20)
        return "ibm_fake_backend", "job-blocked", {"00": 1}

    monkeypatch.setattr("server.quantum_measure._run_ibm_measurement", blocking_runner)

    with TestClient(create_app(paper_rules=False, tick_seconds=0.0, log_path=None)) as client:
        created = client.post("/api/game", json={"level": 2, "mode": "online", "seed": 0}).json()
        game_id, player0 = created["game_id"], created["player_id"]
        room = client.app.state.registry.require(game_id)

        with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
            f"/ws/{game_id}"
        ) as ws1:
            ws0.send_json({"type": "JoinGame", "player_id": player0})
            ws1.send_json({"type": "JoinGame"})

            # Sync on the broadcast rather than assuming the join already landed: wait
            # until seat 1 is claimed and the room reports itself as playing.
            state = _recv_type(ws0, "StateUpdate")
            while state["status"] != "playing":
                state = _recv_type(ws0, "StateUpdate")
            player1 = room.seats[1].player_id
            assert player1 is not None

            # Set up: seat 0 splits, seat 1 replies, seat 0 is left with a split piece.
            spread = [
                action
                for action in room.engine.legal_actions(room.state)
                if isinstance(action, SpreadAction)
            ][0]
            room.move(player0, {"type": "SplitMove", "from": list(spread.origin)})
            reply = [
                action
                for action in room.engine.legal_actions(room.state)
                if action.kind in ("move", "capture")
            ][0]
            room.move(player1, {"type": "Move", "from": list(reply.origin), "to": list(reply.target)})
            observe = [
                action
                for action in room.engine.legal_actions(room.state)
                if isinstance(action, ObserveAction)
            ][0]
            ply_before = room.state.ply

            # Instrument the two mutations instead of racing on wall-clock timing.
            applied: list[tuple[str, str, bool]] = []
            original_apply = room._apply

            def recording_apply(action):
                applied.append((str(action.kind), room.status, room.quantum_pending))
                return original_apply(action)

            room._apply = recording_apply

            resign_pending: list[bool] = []
            original_resign = room.resign

            def recording_resign(player_id):
                resign_pending.append(room.quantum_pending)
                return original_resign(player_id)

            room.resign = recording_resign

            # 1. Seat 0 observes: this blocks inside the (gate-held) hardware measurement.
            ws0.send_json({"type": "ObserveMove", "square": list(observe.origin)})
            deadline = time.monotonic() + 10
            while not room.quantum_pending and time.monotonic() < deadline:
                time.sleep(0.01)
            assert room.quantum_pending, "the measurement never started; test setup is wrong"

            # 2. Seat 1 resigns while that measurement is pending -- it must queue.
            #    Poll across a generous window rather than checking once: the assertion is
            #    that the status *can never* flip, because the resignation is parked on the
            #    room lock the in-flight move holds. The event loop is otherwise idle
            #    (it is awaiting the measurement thread), so the resignation is processed
            #    immediately -- with the lock bypassed it finalizes the game within
            #    milliseconds and this loop catches it.
            ws1.send_json({"type": "Resign"})
            queued_deadline = time.monotonic() + 1.0
            while time.monotonic() < queued_deadline:
                assert room.status == "playing", (
                    "resignation applied while a hardware measurement held the lock"
                )
                time.sleep(0.02)

            # 3. Release the QPU job and let both mutations run to completion.
            gate.set()
            _recv_type(ws1, "GameOver")

            assert room.status == "over"
            assert room.outcome is not None and room.outcome.reason == "resign"

            # The move committed, and it committed while the game was still live.
            observe_records = [record for record in applied if record[0] == "observe"]
            assert observe_records, "the observe never applied"
            assert observe_records[0][1] == "playing", (
                "a move must never commit after the game is over"
            )
            assert room.state.ply == ply_before + 1

            # Resignation waited its turn rather than jumping the lock mid-measurement.
            assert resign_pending == [False], f"resign ran with a pending measurement: {resign_pending}"

            # And the finished game refuses anything else.
            legal_origin = list(observe.origin)
            ws1.send_json({"type": "Move", "from": legal_origin, "to": [0, 0]})
            error = _recv_type(ws1, "Error")
            assert error["code"] == "game_over"
            assert room.state.ply == ply_before + 1, "no move may commit after game over"
            with pytest.raises(ProtocolError) as info:
                room.move(player0, {"type": "ObserveMove", "square": legal_origin})
            assert info.value.code == "game_over"


def test_room_mutations_serialize_on_the_room_lock() -> None:
    """Deterministic lock-contract test, independent of socket scheduling.

    Drives the server's own serialization primitive (``app.state.run_room_mutation``)
    rather than racing two sockets, so the assertion is about the lock itself: with the
    lock, a resignation started while a collapse is mid-measurement stays parked on
    ``Lock.acquire``, which asyncio suspends on the first step -- so after a bounded number
    of loop turns the game is provably still running. The WebSocket test above covers the
    same property end to end; this one makes the guarantee strict.
    """
    import asyncio
    import threading

    from server.app import create_app
    from server.rooms import ProtocolError

    application = create_app(paper_rules=False, tick_seconds=0.0, log_path=None)
    gate = threading.Event()

    def gated_runner(circuit, shots, *, token, instance, backend_name, timeout):
        gate.wait(timeout=20)
        return "ibm_fake_backend", "job-locked", {"00": 1}

    sampler = IBMHardwareSampler(token="fake", runner=gated_runner)
    room = Room(game_id="qk-lock", level=2, mode="local", seed=0, quantum_sampler=sampler)
    token = room.creator_id

    spread = [
        action for action in room.engine.legal_actions(room.state) if isinstance(action, SpreadAction)
    ][0]
    room.move(token, {"type": "SplitMove", "from": list(spread.origin)})
    reply = [
        action
        for action in room.engine.legal_actions(room.state)
        if action.kind in ("move", "capture")
    ][0]
    room.move(token, {"type": "Move", "from": list(reply.origin), "to": list(reply.target)})
    observe = [
        action for action in room.engine.legal_actions(room.state) if isinstance(action, ObserveAction)
    ][0]
    ply_before = room.state.ply

    applied: list[tuple[str, str, bool]] = []
    original_apply = room._apply

    def recording_apply(action):
        applied.append((str(action.kind), room.status, room.quantum_pending))
        return original_apply(action)

    room._apply = recording_apply

    resign_pending: list[bool] = []
    original_resign = room.resign

    def recording_resign(player_id):
        resign_pending.append(room.quantum_pending)
        return original_resign(player_id)

    room.resign = recording_resign

    async def scenario() -> None:
        run = application.state.run_room_mutation
        move_task = asyncio.create_task(
            run(room, room.move, token, {"type": "ObserveMove", "square": list(observe.origin)})
        )
        for _ in range(400):
            if room.quantum_pending:
                break
            await asyncio.sleep(0.005)
        assert room.quantum_pending, "the measurement never started"

        resign_task = asyncio.create_task(run(room, room.resign, token))
        # Several loop turns plus a little real time: plenty for the resignation to run if
        # anything let it past the lock.
        for _ in range(20):
            await asyncio.sleep(0.005)
        assert room.status == "playing", "resignation overtook the locked move"

        gate.set()
        await asyncio.gather(move_task, resign_task)

    asyncio.run(scenario())

    assert room.status == "over"
    assert room.outcome is not None and room.outcome.reason == "resign"
    observe_records = [record for record in applied if record[0] == "observe"]
    assert observe_records and observe_records[0][1] == "playing", (
        "a move must never commit after the game is over"
    )
    assert room.state.ply == ply_before + 1
    assert resign_pending == [False], f"resign ran with a pending measurement: {resign_pending}"

    with pytest.raises(ProtocolError) as info:
        room.move(token, {"type": "ObserveMove", "square": list(observe.origin)})
    assert info.value.code == "game_over"


def test_websocket_observe_applies_the_hardware_square_over_the_wire(monkeypatch) -> None:
    """The interface the browser uses: the board moves to the hardware result and the
    client is told which backend resolved it."""
    from fastapi.testclient import TestClient

    from server.app import create_app

    monkeypatch.setenv("IBM_CLOUD_API_KEY", "fake-key-for-test")

    def runner(circuit, shots, *, token, instance, backend_name, timeout):
        return "ibm_fake_backend", "job-live-1", {"00": 1}

    monkeypatch.setattr("server.quantum_measure._run_ibm_measurement", runner)

    with TestClient(create_app(paper_rules=False, tick_seconds=0.0, log_path=None)) as client:
        created = client.post("/api/game", json={"level": 2, "mode": "local", "seed": 0}).json()
        game_id, player_id = created["game_id"], created["player_id"]
        room = client.app.state.registry.require(game_id)
        observe = _room_to_split_and_observe(room)
        origin = room.state.piece(observe.piece_id).sites[0][0]

        with client.websocket_connect(f"/ws/{game_id}") as ws:
            ws.send_json({"type": "JoinGame", "player_id": player_id})
            ws.send_json({"type": "ObserveMove", "square": list(observe.origin)})
            update = None
            # Keep consuming frames until one carries the *resolved* hardware result.
            # Several StateUpdate frames are in flight and `room.state.ply` already reads
            # the post-observe ply, so matching on ply alone can accept an earlier frame
            # whose `quantum.backend` is still the unresolved placeholder. That was the
            # real intermittent failure -- not a race on the board assertion below.
            for _ in range(20):
                frame = ws.receive_json()
                if (
                    frame.get("type") == "StateUpdate"
                    and frame.get("ply") == room.state.ply
                    and frame.get("quantum", {}).get("backend") == "ibm_fake_backend"
                ):
                    update = frame
                    break
            assert update is not None, "a StateUpdate must carry the applied collapse"

        assert update["board"]["pieces"]  # the board arrived with the resolved piece
        # The frame is serialised as it is built, so receiving it does not strictly mean
        # the shared room state is already swapped. Poll rather than assert once.
        assert _wait_for(lambda: room.state.piece(observe.piece_id).squares == (origin,)), (
            f"collapse did not land on {origin}; piece is at "
            f"{room.state.piece(observe.piece_id).squares}"
        )
        assert update["quantum"]["enabled"] is True
        assert update["quantum"]["backend"] == "ibm_fake_backend"
        assert update["last_event"]["quantum"]["job_id"] == "job-live-1"
