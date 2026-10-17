"""Game server protocol tests -- P5's server acceptance suite.

Phase 1 acceptance (brief): a scripted two-client test opens two WebSocket
connections, plays a full Level-0 game to ``GameOver`` using only legal engine moves,
and shows that an illegal move returns ``Error`` with the state unchanged. Everything
else here pins the frozen contract in ``docs/PROTOCOL.md``:

* the server is authoritative -- every accepted move is one the engine listed;
* refused moves are inert;
* reconnect resends the seat's view without resolving anything;
* the difficulty tiers are wired as seats, not as client-side opponents.

Ticks are disabled in every app built here, so no background frame can interleave with
a scripted read.

Every socket read in this module is bounded by :data:`RECV_TIMEOUT_SECONDS`. Starlette's
``WebSocketTestSession.receive`` waits forever, so an unbounded read turns any stall into a
hung suite instead of a failure with a stack; see :func:`_receive_within`.
"""

from __future__ import annotations

import json
import queue
from collections.abc import Iterator
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.notify import build_embed
from server.rooms import ProtocolError, Room, RoomRegistry, parse_square, resolve_action
from qcheckers.engine.protocol import MergeAction, RejoinAction, SpreadAction
from qcheckers.engine.toy import DeterministicToyEngine


#: Seconds a single socket read may block before the test fails. Every frame below is
#: produced synchronously by the request that precedes it, so a healthy server answers in
#: single-digit milliseconds; this ceiling only has to outlast a loaded machine, and its
#: job is to convert a stall into a failure that carries a stack.
RECV_TIMEOUT_SECONDS = 10.0

#: Loop round-trips allowed for the parked-reader handshake below.
#: ``MemoryObjectReceiveStream.receive`` yields once at its leading checkpoint before it
#: queues the reader, so two or three rounds is the real cost; the bound only stops a
#: regression from spinning forever.
_PARK_POLL_ROUNDS = 50


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient over a fresh app with ticks off and no on-disk logging.

    Entering the client is load-bearing, not decoration. ``TestClient.__enter__`` opens one
    blocking portal -- one event loop in one thread -- and ``websocket_connect`` then reuses
    it. Built *without* ``with``, ``client.portal`` stays ``None`` and
    ``WebSocketTestSession.__enter__`` calls ``portal_factory()`` per connection, so every
    socket got its own event loop in its own thread. ``server.app.broadcast_state`` writes
    to every socket in the room, so it then pushed frames into a peer's anyio memory stream
    from the wrong thread: ``Event.set`` resolves the parked reader's future through
    ``loop.call_soon`` and never writes the loop's self-pipe, so the wakeup was dropped and
    the peer's ``receive()`` never returned. That was the intermittent hang in
    ``test_two_websockets_play_a_full_level_0_game_to_gameover``; a real (uvicorn) server
    always has one loop, so this restores what production does.
    """
    with TestClient(create_app(paper_rules=False, tick_seconds=0.0, log_path=None)) as client:
        yield client


def _new_game(client: TestClient, **payload: Any) -> tuple[str, str]:
    response = client.post("/api/game", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["game_id"], body["player_id"]


async def _receive_within(ws: Any, timeout: float) -> Any:
    """One raw ASGI frame off ``ws``, or ``TimeoutError`` instead of an indefinite block.

    Starlette offers no timed read: ``WebSocketTestSession.receive`` is
    ``portal.call(self._send_rx.receive)``, and ``portal.call`` blocks the calling thread
    forever if the peer never sends. This wraps that same ``receive()`` in an anyio deadline
    on the session's own loop, which is what makes a future stall *fail* rather than hang.
    """
    with anyio.move_on_after(timeout):
        message = await ws._send_rx.receive()  # noqa: SLF001 - see module docstring
    ws._raise_on_close(message)  # noqa: SLF001 - Starlette's own close handling
    return message


def _recv(ws: Any) -> dict[str, Any]:
    message = ws.portal.call(_receive_within, ws, RECV_TIMEOUT_SECONDS)
    assert isinstance(message, dict)
    return json.loads(message["text"])


def _recv_type(ws: Any, expected: str, limit: int = 40) -> dict[str, Any]:
    for _ in range(limit):
        message = _recv(ws)
        if message.get("type") == expected:
            return message
    raise AssertionError(f"no {expected!r} frame within {limit} reads")


def _to_move_message(action: dict[str, Any]) -> dict[str, Any]:
    """Translate one engine action descriptor from ``legal`` into a protocol message.

    Uses only what the server sent -- the test never re-derives legality.
    """
    kind = action["kind"]
    if kind in ("move", "capture"):
        return {"type": "Move", "from": action["origin"], "to": action["target"]}
    if kind == "spread":
        return {"type": "SplitMove", "from": action["origin"]}
    if kind == "observe":
        return {"type": "ObserveMove", "square": action["origin"]}
    if kind == "merge":
        return {
            "type": "MergeMove",
            "pieces": [action["piece_id"], action["other_piece_id"]],
        }
    if kind == "rejoin":
        return {
            "type": "MergeMove",
            "piece": action["piece_id"],
            "target": action["target"],
        }
    raise AssertionError(f"unhandled action kind {kind!r}")


async def _park_one_frame(ws: Any, sink: "queue.Queue[dict[str, Any]]") -> None:
    """Take one frame off ``ws`` on the event loop and publish it to ``sink``."""
    message = await ws._send_rx.receive()  # noqa: SLF001 - same read as _receive_within
    sink.put(json.loads(message["text"]))


def _reader_is_queued(ws: Any) -> bool:
    """Whether a receive on ``ws`` is parked, i.e. waiting for a frame.

    ``anyio``'s ``MemoryObjectReceiveStream.receive`` registers the reader in
    ``_state.waiting_receivers`` immediately before awaiting; this reads that private
    registry because the parked-reader handshake has to be *observable* to avoid sleeping.
    """
    return bool(ws._send_rx._state.waiting_receivers)  # noqa: SLF001 - see docstring


# ---------------------------------------------------------------------------
# Phase 1 acceptance
# ---------------------------------------------------------------------------


def test_two_websockets_play_a_full_level_0_game_to_gameover(client: TestClient) -> None:
    """ACCEPTANCE: two clients, a full Level-0 game, only engine-legal moves."""
    game_id, player0 = _new_game(client, level=0, mode="online", seed=7)

    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        first = _recv_type(ws0, "StateUpdate")
        assert first["you"] == 0
        assert first["status"] == "waiting"

        ws1.send_json({"type": "JoinGame", "label": "guest"})
        state0 = _recv_type(ws0, "StateUpdate")
        state1 = _recv_type(ws1, "StateUpdate")
        assert state1["you"] == 1
        assert state0["status"] == "playing"
        assert state0["board"] == state1["board"], "both clients see one authoritative board"

        moves = 0
        while state0["status"] == "playing":
            moves += 1
            assert moves < 400, "game did not terminate; the cap is the failure"

            legal = state0["legal"] or state1["legal"]
            assert legal, "a running game must offer the seat to move a legal action"
            turn = state0["turn"]
            mover = ws0 if turn == 0 else ws1
            mover.send_json(_to_move_message(legal[0]))

            state0 = _recv_type(ws0, "StateUpdate")
            state1 = _recv_type(ws1, "StateUpdate")
            assert state0["ply"] == state1["ply"] == moves

        over0 = _recv_type(ws0, "GameOver")
        over1 = _recv_type(ws1, "GameOver")
        assert over0 == over1
        assert over0["reason"] in {"no_pieces", "no_legal_moves", "ply_limit"}
        assert over0["result"] in (0, 1, None)

    # Every move really was an engine-legal one: re-derive the record and check the
    # counts add up, which is what "using only legal engine moves" means in practice.
    final = client.get(f"/api/game/{game_id}").json()
    assert final["phase"] == "over"
    assert final["ply"] == moves


def test_illegal_move_returns_error_and_leaves_the_state_unchanged(
    client: TestClient,
) -> None:
    """ACCEPTANCE: a refused move is inert -- Error only, no state change."""
    game_id, player0 = _new_game(client, level=0, mode="online", seed=3)
    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        _recv_type(ws0, "StateUpdate")
        ws1.send_json({"type": "JoinGame"})
        _recv_type(ws0, "StateUpdate")
        _recv_type(ws1, "StateUpdate")

        before = client.get(f"/api/game/{game_id}").json()

        # Nobody is at (0,0) for player 0, and (0,0)->(1,1) is not a legal origin.
        ws0.send_json({"type": "Move", "from": [0, 0], "to": [1, 1]})
        error = _recv_type(ws0, "Error")
        assert error["code"] == "illegal_move"

        after = client.get(f"/api/game/{game_id}").json()
        assert after["board"] == before["board"]
        assert after["ply"] == before["ply"]
        assert after["turn"] == before["turn"]


def test_unknown_game_closes_the_socket(client: TestClient) -> None:
    """An unknown lobby code is refused, not silently created."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/qk-nope") as ws:
            _recv(ws)


# ---------------------------------------------------------------------------
# REST and seats
# ---------------------------------------------------------------------------


def test_create_game_validates_level_and_mode(client: TestClient) -> None:
    assert client.post("/api/game", json={"level": 9, "mode": "local"}).status_code == 422
    assert client.post("/api/game", json={"level": 1, "mode": "nope"}).status_code == 422


def test_health_and_unknown_game(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/game/qk-missing").status_code == 404
    assert client.get("/api/game/qk-missing/view").status_code == 404


def test_reconnect_reclaims_the_same_seat_and_resends_the_view(
    client: TestClient,
) -> None:
    """Reconnect semantics (frozen protocol section 5): same seat, current state."""
    # Local mode so one token can set up the split before the reconnect.
    game_id, player0 = _new_game(client, level=1, mode="local", seed=5)
    with client.websocket_connect(f"/ws/{game_id}") as ws0:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        first = _recv_type(ws0, "StateUpdate")
        assert first["you"] == 0

    # Split a piece first so the reconnected view has an unresolved superposition.
    room: Room = client.app.state.registry.require(game_id)
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ]
    assert spread
    room.move(player0, {"type": "SplitMove", "from": list(spread[0].origin)})
    spread_piece = room.state.spread_pieces()[0]

    with client.websocket_connect(f"/ws/{game_id}") as ws0:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        resumed = _recv_type(ws0, "StateUpdate")
        assert resumed["you"] == 0
        assert resumed["player_id"] == player0
        # The uncertainty is still unresolved: nothing was sampled to fill the view.
        assert any(
            piece["piece_id"] == spread_piece.piece_id and piece["uncertain"]
            for piece in resumed["board"]["pieces"]
        )


def test_spectator_join_is_read_only(client: TestClient) -> None:
    game_id, player0 = _new_game(client, level=0, mode="online", seed=1)
    with client.websocket_connect(f"/ws/{game_id}") as ws0:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        _recv_type(ws0, "StateUpdate")
        with client.websocket_connect(f"/ws/{game_id}") as guest:
            guest.send_json({"type": "JoinGame"})
            _recv_type(ws0, "StateUpdate")
            seat = _recv_type(guest, "StateUpdate")
            assert seat["you"] == 1

            with client.websocket_connect(f"/ws/{game_id}") as watcher:
                watcher.send_json({"type": "JoinGame"})
                error = _recv_type(watcher, "Error")
                assert error["code"] == "spectator"
                watcher.send_json({"type": "Move", "from": [3, 1], "to": [2, 0]})
                assert _recv_type(watcher, "Error")["code"] == "not_seated"


def test_moving_out_of_turn_is_refused(client: TestClient) -> None:
    game_id, player0 = _new_game(client, level=0, mode="online", seed=2)
    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        _recv_type(ws0, "StateUpdate")
        ws1.send_json({"type": "JoinGame"})
        state0 = _recv_type(ws0, "StateUpdate")
        _recv_type(ws1, "StateUpdate")

        # Seat 1 sends a move that is legal for seat 0; the turn check must refuse it.
        ws1.send_json(_to_move_message(state0["legal"][0]))
        error = _recv_type(ws1, "Error")
        assert error["code"] == "not_your_turn"


def test_resign_ends_the_game_against_the_resigner(client: TestClient) -> None:
    game_id, player0 = _new_game(client, level=0, mode="online", seed=4)
    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        _recv_type(ws0, "StateUpdate")
        ws1.send_json({"type": "JoinGame"})
        _recv_type(ws0, "StateUpdate")
        _recv_type(ws1, "StateUpdate")

        ws0.send_json({"type": "Resign"})
        _recv_type(ws0, "StateUpdate")
        over = _recv_type(ws0, "GameOver")
        assert over["result"] == 1
        assert over["reason"] == "resign"


# ---------------------------------------------------------------------------
# AI seats (Phase 3 tiers, wired server-side)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["ai-easy", "ai-medium", "ai-hard"])
def test_every_ai_tier_replies_with_a_legal_move(client: TestClient, mode: str) -> None:
    """Each tier is seated by the server; its reply arrives as a second StateUpdate."""
    game_id, player0 = _new_game(client, level=1, mode=mode, seed=11)
    with client.websocket_connect(f"/ws/{game_id}") as ws0:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        state = _recv_type(ws0, "StateUpdate")
        assert state["status"] == "playing", "an AI room starts once seat 1 is seated"

        ws0.send_json(_to_move_message(state["legal"][0]))
        after_human = _recv_type(ws0, "StateUpdate")
        assert after_human["ply"] == state["ply"] + 1, "human move must broadcast first"

        if after_human["status"] == "playing" and after_human["turn"] == 1:
            after_ai = _recv_type(ws0, "StateUpdate")
            assert after_ai["ply"] == after_human["ply"] + 1
            assert after_ai["turn"] == 0


def test_ai_hard_is_the_only_tier_with_observe_enabled(client: TestClient) -> None:
    """The tiers are a clean strength ladder: only Hard carries the extension."""
    for mode, expected in (("ai-easy", False), ("ai-medium", False), ("ai-hard", True)):
        game_id, _ = _new_game(client, level=1, mode=mode, seed=11)
        room: Room = client.app.state.registry.require(game_id)
        assert room.engine.allow_observe is expected, mode


# ---------------------------------------------------------------------------
# Protocol -> engine mapping (unit level, no sockets)
# ---------------------------------------------------------------------------


def test_split_move_resolves_to_the_engines_spread_action() -> None:
    room = Room(game_id="qk-unit", level=1, mode="local", seed=0)
    token = room.creator_id
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(token, {"type": "SplitMove", "from": list(spread.origin)})
    assert room.state.piece(spread.piece_id).is_spread


def test_split_targets_must_match_the_engine_distribution() -> None:
    """A client cannot invent a different distribution than the engine offers."""
    room = Room(game_id="qk-unit", level=1, mode="local", seed=0)
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    wrong = [square for square, _ in spread.sites if square != spread.origin]
    wrong.append((0, 0))  # a square the engine did not offer
    with pytest.raises(ProtocolError) as info:
        room.move(room.creator_id, {"type": "SplitMove", "from": list(spread.origin), "targets": [list(s) for s in wrong]})
    assert info.value.code == "illegal_split"


def test_observe_move_is_refused_on_a_certain_piece() -> None:
    room = Room(game_id="qk-unit", level=1, mode="local", seed=0)
    with pytest.raises(ProtocolError) as info:
        room.move(room.creator_id, {"type": "ObserveMove", "square": [3, 1]})
    assert info.value.code == "illegal_move"


def test_merge_move_maps_to_a_rejoin_at_level_two() -> None:
    room = Room(game_id="qk-unit", level=2, mode="local", seed=0)
    token = room.creator_id
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(token, {"type": "SplitMove", "from": list(spread.origin)})
    # Local mode: the same token plays both seats, so advance the opponent.
    opponent = room.engine.legal_actions(room.state)[0]
    room.move(token, {"type": "Move", "from": list(opponent.origin), "to": list(opponent.target)})

    rejoins = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, RejoinAction)
    ]
    assert rejoins, "a spread piece on level 2 must offer a rejoin"
    target = rejoins[0].target
    room.move(
        token,
        {"type": "MergeMove", "piece": rejoins[0].piece_id, "target": list(target)},
    )
    assert not room.state.piece(rejoins[0].piece_id).is_spread


def test_merge_move_maps_to_a_merge_at_level_three() -> None:
    """Drive a real level-3 game until a merge is offered, then take it over the wire."""
    room = Room(game_id="qk-unit", level=3, mode="local", seed=0)
    token = room.creator_id
    for ply in range(120):
        legal = room.engine.legal_actions(room.state)
        if room.status == "over" or not legal:
            break
        merges = [action for action in legal if isinstance(action, MergeAction)]
        if merges:
            action = merges[0]
            room.move(
                token,
                {
                    "type": "MergeMove",
                    "pieces": [action.piece_id, action.other_piece_id],
                },
            )
            survivors = {piece.piece_id for piece in room.state.pieces}
            assert action.other_piece_id not in survivors, "the merge consumed a piece"
            assert room.state.piece(action.piece_id).is_spread
            return
        room.move(token, _to_move_message(legal[0].to_json()))
    pytest.fail("120 plies of level 3 produced no merge opportunity")


def test_resolve_action_refuses_unknown_message_types() -> None:
    engine = DeterministicToyEngine(seed=0, level=1)
    state = engine.initial_state()
    with pytest.raises(ProtocolError) as info:
        resolve_action(engine, state, {"type": "Teleport", "to": [0, 0]})
    assert info.value.code == "unknown_type"


def test_resolve_action_refuses_malformed_squares() -> None:
    engine = DeterministicToyEngine(seed=0, level=0)
    state = engine.initial_state()
    for bad in ({"type": "Move", "from": "a1", "to": [2, 0]}, {"type": "Move", "from": [1], "to": [2, 0]}):
        with pytest.raises(ProtocolError):
            resolve_action(engine, state, bad)


def test_local_mode_creator_controls_both_seats(client: TestClient) -> None:
    """Local 2P is one browser, one token, both seats -- and it is still server-checked."""
    game_id, player0 = _new_game(client, level=0, mode="local", seed=6)
    room: Room = client.app.state.registry.require(game_id)
    assert room.status == "playing"

    first = room.engine.legal_actions(room.state)[0]
    room.move(player0, _to_move_message(first.to_json()))
    assert room.state.turn == 1, "seat 1's turn"
    second = room.engine.legal_actions(room.state)[0]
    room.move(player0, _to_move_message(second.to_json()))
    assert room.state.turn == 0, "local play alternates through the same token"


def test_registry_rejects_unknown_modes_and_levels() -> None:
    registry = RoomRegistry(log_path=None)
    with pytest.raises(ValueError):
        registry.create(level=0, mode="versus-god")
    with pytest.raises(ValueError):
        registry.create(level=7, mode="local")


# ---------------------------------------------------------------------------
# Protocol samples (addendum A) and the Level-4 game path (addendum D)
# ---------------------------------------------------------------------------


def test_parse_square_accepts_algebraic_and_array_forms() -> None:
    """Both frozen sample shapes work: "c3" and [2, 2] are the same square."""
    assert parse_square("c3") == (2, 2)
    assert parse_square("A1") == (0, 0)
    assert parse_square([2, 2]) == (2, 2)
    with pytest.raises(ProtocolError):
        parse_square("z")
    with pytest.raises(ProtocolError):
        parse_square("9")


def test_algebraic_square_messages_are_accepted() -> None:
    """A move sent as "b4" -> "a3" resolves to the engine's MoveAction."""
    room = Room(game_id="qk-alg", level=0, mode="local", seed=0)
    room.move(room.creator_id, {"type": "Move", "from": "b4", "to": "a3"})
    assert room.state.piece("P0-0").squares == ((2, 0),)
    assert room.state.turn == 1


def test_level_four_room_enables_decoherence_only_there() -> None:
    registry = RoomRegistry(log_path=None)
    four = registry.create(level=4, mode="local", seed=0)
    assert four.engine.decoherence is True
    assert four.engine.level == 4
    for level in (0, 1, 2, 3):
        assert registry.create(level=level, mode="local", seed=0).engine.decoherence is False


def test_state_update_carries_a_coherence_counter_at_level_four(client: TestClient) -> None:
    """The game client renders counters from ``coherence`` (sample A field)."""
    game_id, player0 = _new_game(client, level=4, mode="local", seed=0)
    room: Room = client.app.state.registry.require(game_id)
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(player0, {"type": "SplitMove", "from": list(spread.origin)})
    view = room.view(player0)
    assert view["board"]["decoherence"] is True
    assert view["coherence"], "a fresh split must expose its counter"
    assert sorted(view["coherence"].values()) == [6]


def test_last_event_carries_the_compact_sample_fields() -> None:
    """``kind``/``kept``/``by`` aliases are present alongside the authoritative fields."""
    # Level 2 + local mode is where voluntary resolution (Observe) reaches human seats:
    # stage 1 is the split on its own, and stage 2 is the resolution stage.
    room = Room(game_id="qk-ev", level=2, mode="local", seed=0)
    spread = [
        action
        for action in room.engine.legal_actions(room.state)
        if isinstance(action, SpreadAction)
    ][0]
    room.move(room.creator_id, {"type": "SplitMove", "from": list(spread.origin)})
    opponent = room.engine.legal_actions(room.state)[0]
    room.move(room.creator_id, {"type": "Move", "from": list(opponent.origin), "to": list(opponent.target)})
    observe = [
        action
        for action in room.engine.legal_actions(room.state)
        if action.kind == "observe"
    ][0]
    room.move(room.creator_id, {"type": "ObserveMove", "square": list(observe.origin)})
    view = room.view(room.creator_id)
    event = view["last_event"]
    assert event["kind"] == "collapse"
    assert event["by"] == "observe"
    assert event["kept"] == event["sampled"]


def test_game_over_carries_moves_and_seed(client: TestClient) -> None:
    game_id, player0 = _new_game(client, level=0, mode="local", seed=13)
    room: Room = client.app.state.registry.require(game_id)
    for _ in range(300):
        legal = room.engine.legal_actions(room.state)
        if room.status == "over" or not legal:
            break
        action = legal[0]
        if action.kind in ("move", "capture"):
            room.move(player0, {"type": "Move", "from": list(action.origin), "to": list(action.target)})
        else:
            pytest.fail("level 0 produced a non-classical action")
    with client.websocket_connect(f"/ws/{game_id}") as ws:
        ws.send_json({"type": "JoinGame", "player_id": player0})
        state = _recv_type(ws, "StateUpdate")
        assert state["status"] == "over"
        over = _recv_type(ws, "GameOver")
        assert over["moves"] == state["ply"]
        assert over["seed"] == 13


# ---------------------------------------------------------------------------
# Discord hook (addendum B)
# ---------------------------------------------------------------------------


def test_embed_lists_fields_and_never_the_webhook_url() -> None:
    embed = build_embed(
        "game_over",
        {
            "level": 1,
            "mode": "ai-easy",
            "result": 1,
            "reason": "no_pieces",
            "moves": 12,
            "duration_s": 1.25,
            "seed": 7,
            "game_id": "qk-x",
        },
    )
    text = json.dumps(embed)
    assert "1.2s" in embed["description"]
    assert "qk-x" in embed["description"]
    assert "webhook" not in text.lower()
    assert embed["title"].startswith("Quantum Checkers")


def test_discord_hook_is_disabled_when_the_variable_is_unset() -> None:
    application = create_app(paper_rules=False, tick_seconds=0.0, discord_webhook_url="")
    assert application.state.notifier.enabled is False
    with TestClient(application) as client:
        game_id, player0 = _new_game(client, level=0, mode="local", seed=2)
        with client.websocket_connect(f"/ws/{game_id}") as ws:
            ws.send_json({"type": "JoinGame", "player_id": player0})
            assert _recv_type(ws, "StateUpdate")["status"] == "playing"


def test_a_dead_webhook_cannot_delay_or_fail_a_game() -> None:
    """A deliberately unreachable URL must not disturb a full game."""
    application = create_app(paper_rules=False,
        tick_seconds=0.0,
        discord_webhook_url="http://127.0.0.1:9/definitely-not-listening",
    )
    assert application.state.notifier.enabled is True
    with TestClient(application) as client:
        game_id, player0 = _new_game(client, level=0, mode="local", seed=4)
        room: Room = client.app.state.registry.require(game_id)
        for _ in range(300):
            legal = room.engine.legal_actions(room.state)
            if room.status == "over" or not legal:
                break
            action = legal[0]
            room.move(player0, {"type": "Move", "from": list(action.origin), "to": list(action.target)})
        assert room.status == "over"


# ---------------------------------------------------------------------------
# Transport regression: one event loop per client, so no wakeup is ever dropped
# ---------------------------------------------------------------------------


def test_every_websocket_session_shares_the_clients_single_event_loop(
    client: TestClient,
) -> None:
    """REGRESSION: all of a client's sockets run on one portal, one loop, one thread.

    This is the invariant whose absence caused the intermittent hang. Built without
    ``with``, ``client.portal`` is ``None`` and
    ``WebSocketTestSession.__enter__`` starts a *fresh* blocking portal per connection, so
    each socket ran on its own event loop in its own thread. ``broadcast_state`` writes to
    every socket in the room, so it crossed loop boundaries; anyio then set the peer
    reader's ``Event`` from the wrong thread, which resolves the parked future through
    ``loop.call_soon`` without writing the loop's self-pipe. The wakeup was dropped, the
    peer's ``receive()`` never returned, and the test hung with no output.

    Deterministic by construction: it asserts the invariant, not a timing window.
    """
    game_id, _ = _new_game(client, level=0, mode="online", seed=7)
    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        assert client.portal is not None, "the client fixture must enter the TestClient"
        assert ws0.portal is ws1.portal is client.portal


def test_a_broadcast_wakes_a_socket_that_is_already_waiting(client: TestClient) -> None:
    """REGRESSION: the lost-wakeup shape itself, driven without sleeps or randomness.

    The idle socket parks a read on the event loop *before* the other seat moves, so the
    broadcast is pushed straight into a reader that is already waiting. With one loop the
    reader is woken; with one loop per socket the wakeup is dropped and this stalls until
    :data:`RECV_TIMEOUT_SECONDS` turns the stall into a failure.

    Parking is confirmed rather than assumed: ``portal.call`` round-trips advance the loop
    one scheduling round each, so the poll below terminates as soon as the reader is
    genuinely queued. No sleeping, no fixed seed dependence, no network.
    """
    game_id, player0 = _new_game(client, level=0, mode="online", seed=7)
    with client.websocket_connect(f"/ws/{game_id}") as ws0, client.websocket_connect(
        f"/ws/{game_id}"
    ) as ws1:
        ws0.send_json({"type": "JoinGame", "player_id": player0})
        _recv_type(ws0, "StateUpdate")
        ws1.send_json({"type": "JoinGame", "label": "guest"})
        state0 = _recv_type(ws0, "StateUpdate")
        state1 = _recv_type(ws1, "StateUpdate")
        assert state1["status"] == "playing"
        # ``view`` fills ``legal`` only for the seat to move, so take it from that seat.
        legal = state0["legal"] or state1["legal"]
        assert legal, "the seat to move must be offered a legal action"

        mover, idle = (ws0, ws1) if state0["turn"] == 0 else (ws1, ws0)
        parked: queue.Queue[dict[str, Any]] = queue.Queue()
        idle.portal.start_task_soon(_park_one_frame, idle, parked)
        for _ in range(_PARK_POLL_ROUNDS):
            if idle.portal.call(_reader_is_queued, idle):
                break
        else:  # pragma: no cover - defensive; a few loop rounds always suffice
            pytest.fail("the idle socket's read never parked")

        mover.send_json(_to_move_message(legal[0]))

        frame = parked.get(timeout=RECV_TIMEOUT_SECONDS)
        assert frame["type"] == "StateUpdate"
        assert frame["ply"] == state0["ply"] + 1
        _recv_type(mover, "StateUpdate")
