"""FastAPI + WebSocket game server for Quantum Checkers.

Owner: **P5 -- rules, engine, harness and batches**.

The server is deliberately thin: it owns rooms, seats, turn order and broadcast, and it
delegates every rule decision to :mod:`qcheckers.engine` through
:func:`server.rooms.resolve_action`. See ``docs/PROTOCOL.md`` for the frozen contract.

Run it with::

    python -m server                # 127.0.0.1:8000
    python -m server --host 0.0.0.0 --port 8000   # LAN

No authentication, no persistence: rooms live in memory and are open to anyone who
knows the lobby code (brief: localhost + LAN only, no accounts).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from server.notify import Notifier, notifier_from_env
from server.quantum_measure import QuantumMeasurementError
from server.rooms import MODES, SUPPORTED_LEVELS, ProtocolError, Room, RoomRegistry

#: WebSocket close code for an unknown lobby (4400-range: application defined).
CLOSE_UNKNOWN_GAME = 4404


class CreateGameRequest(BaseModel):
    """Body of ``POST /api/game`` (frozen protocol section 2.1)."""

    level: int = Field(default=0, ge=0, le=4)
    mode: str = "local"
    seed: int | None = None
    board_size: int = Field(default=8, ge=4, le=16)


def create_app(
    *,
    tick_seconds: float = 1.0,
    log_path: str | Path | None = None,
    discord_webhook_url: str | None = None,
    paper_rules: bool = True,
    ai_delay_seconds: float = 1.1,
) -> FastAPI:
    """Build the application.

    Parameters
    ----------
    tick_seconds:
        Liveness tick interval. ``0`` disables ticks, which is what the test suite uses
        so background frames cannot interleave with scripted message reads.
    log_path:
        Optional JSONL file for finished games. When ``None`` (the default for tests)
        nothing is written to disk.
    discord_webhook_url:
        Optional Discord webhook. ``None`` reads ``DISCORD_WEBHOOK_URL`` from the
        environment; an empty string (or an unset variable) disables the hook. It is
        always fire-and-forget: see :mod:`server.notify`.
    """
    app = FastAPI(
        title="QuriousMinds game server",
        description=(
            "Server-authoritative Quantum Checkers. Rules live in qcheckers/engine; "
            "the server resolves messages against engine.legal_actions only."
        ),
        version="0.1.0",
    )
    # The client is a static file that may be opened from disk (origin ``null``), so the
    # browser needs CORS to reach this server. There are no credentials and no cookies,
    # and the brief keeps everything on localhost/LAN, so allowing any origin is safe
    # here and is stated rather than hidden.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    registry = RoomRegistry(log_path=log_path, paper_rules=paper_rules)
    #: game_id -> [[player_id, socket], ...]. A mutable two-slot holder, not a tuple,
    #: so a ``JoinGame`` can fill in the token in place and the *next* broadcast sees it.
    sockets: dict[str, list[list[Any]]] = {}

    notifier: Notifier = notifier_from_env(discord_webhook_url)
    app.state.registry = registry
    app.state.sockets = sockets
    app.state.tick_seconds = tick_seconds
    app.state.notifier = notifier
    #: One lock per room. A hardware collapse can block for many seconds, so a room's
    #: move (and the agent replies it triggers) runs to completion under its lock before
    #: any other socket in that room may apply a move -- ordering per room is preserved
    #: while a measurement is pending.
    room_locks: dict[str, asyncio.Lock] = {}
    app.state.room_locks = room_locks
    #: Rooms already announced as finished, so the game-over event fires exactly once.
    announced: set[str] = set()

    # -- broadcast helpers -------------------------------------------------

    async def broadcast_state(room: Room) -> None:
        """Send every connected socket its own view of the current state."""
        for holder in list(sockets.get(room.game_id, [])):
            token, socket = holder[0], holder[1]
            try:
                await socket.send_json(room.view(token))
            except Exception:  # pragma: no cover - a dead socket must not kill a room
                continue
        if room.status == "over" and room.outcome is not None:
            payload = {
                "type": "GameOver",
                "result": room.outcome.winner,
                "reason": room.outcome.reason,
                "moves": room.state.ply,
                "seed": room.seed,
                "game_id": room.game_id,
                "level": room.level,
                "mode": room.mode,
            }
            for holder in list(sockets.get(room.game_id, [])):
                try:
                    await holder[1].send_json(payload)
                except Exception:  # pragma: no cover
                    continue
            if room.game_id not in announced:
                announced.add(room.game_id)
                notifier.game_over(
                    level=room.level,
                    mode=room.mode,
                    result=room.outcome.winner,
                    reason=room.outcome.reason,
                    moves=room.state.ply,
                    duration_s=(room.finished_at - room.started_at),
                    seed=room.seed,
                    game_id=room.game_id,
                )

    async def send_all(room: Room, payload: dict[str, Any]) -> None:
        """Push one raw frame to every connected socket in a room."""
        for holder in list(sockets.get(room.game_id, [])):
            try:
                await holder[1].send_json(payload)
            except Exception:  # pragma: no cover - a dead socket must not kill a room
                continue

    def room_lock(game_id: str) -> asyncio.Lock:
        """The room's synchronization primitive, created on first use."""
        return room_locks.setdefault(game_id, asyncio.Lock())

    async def run_room_mutation(room: Room, operation: Callable[..., None], *args: Any) -> None:
        """Run one blocking room mutation under the room lock, on a worker thread.

        **Every** mutation that can race a move goes through here -- a client move, an
        agent ply, and Resign. That is what makes "a move cannot commit after the game is
        over" true: a resignation and a move contend for the same lock, so the second one
        to arrive observes the finished game and is refused.

        Two deliberate properties:

        * The lock covers only the mutation, never the broadcast that follows it. Holding
          it across a socket write would let one stalled client extend a hardware wait and
          needlessly block every other player in the room.
        * The mutation (which may block for seconds inside a QPU measurement) runs on a
          worker thread, so the event loop keeps serving every other room.
        """
        async with room_lock(room.game_id):
            await asyncio.to_thread(operation, *args)

    async def drive_ai(room: Room) -> None:
        """Play seated-agent replies one ply at a time, broadcasting after each.

        Every ply runs on a worker thread because an agent's Observe can trigger a
        hardware measurement, and it takes the room lock like any other mutation. If that
        measurement fails there is no fallback: the state is left untouched, an Error goes
        to the room, and the game stops rather than resolve the collapse some other way.
        """
        while room.ai_to_move():
            # Give the preceding move and its animation time to register.
            await asyncio.sleep(max(0.0, ai_delay_seconds))
            try:
                await run_room_mutation(room, room.play_ai_ply)
            except (QuantumMeasurementError, ProtocolError) as exc:
                await send_all(
                    room, {"type": "Error", "code": exc.code, "message": str(exc)}
                )
                await broadcast_state(room)
                return
            await broadcast_state(room)

    #: Exposed for tests: the serialization primitive every room mutation goes through.
    #: A regression test drives it directly so the lock contract can be asserted without
    #: depending on when a socket message happens to be scheduled.
    app.state.run_room_mutation = run_room_mutation
    app.state.room_lock = room_lock

    # -- REST --------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "games": len(registry)}

    @app.post("/api/game", status_code=201)
    async def create_game(request: CreateGameRequest) -> dict[str, Any]:
        if request.mode not in MODES:
            raise HTTPException(
                status_code=422,
                detail=f"mode must be one of {list(MODES)}; got {request.mode!r}",
            )
        if request.level not in SUPPORTED_LEVELS:
            raise HTTPException(
                status_code=422,
                detail=f"level must be one of {list(SUPPORTED_LEVELS)}",
            )
        try:
            room = registry.create(
                level=request.level,
                mode=request.mode,
                seed=request.seed,
                board_size=request.board_size if paper_rules or "board_size" in request.model_fields_set else 4,
                max_plies=1000 if paper_rules else 200,
            )
        except QuantumMeasurementError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        notifier.game_created(
            level=room.level, mode=room.mode, seed=room.seed, game_id=room.game_id
        )
        return {
            "game_id": room.game_id,
            "player_id": room.creator_id,
            "level": room.level,
            "mode": room.mode,
            "seed": room.seed,
        }

    @app.get("/api/game/{game_id}")
    async def get_game(game_id: str) -> dict[str, Any]:
        room = registry.get(game_id)
        if room is None:
            raise HTTPException(status_code=404, detail=f"unknown game {game_id!r}")
        return room.view(None)

    @app.get("/api/game/{game_id}/view")
    async def get_view(game_id: str, player_id: str | None = None) -> dict[str, Any]:
        room = registry.get(game_id)
        if room is None:
            raise HTTPException(status_code=404, detail=f"unknown game {game_id!r}")
        return room.view(player_id)

    # -- WebSocket ---------------------------------------------------------

    @app.websocket("/ws/{game_id}")
    async def game_socket(websocket: WebSocket, game_id: str) -> None:
        await websocket.accept()
        room = registry.get(game_id)
        if room is None:
            await websocket.close(code=CLOSE_UNKNOWN_GAME)
            return

        # A socket is registered only once it has sent JoinGame, so a connection that
        # has not claimed anything yet never sees another player's pre-game frames.
        holder: list[Any] = [None, websocket]
        registered = False

        ticker: asyncio.Task[None] | None = None
        if tick_seconds > 0:
            ticker = asyncio.create_task(_tick(websocket, tick_seconds, game_id))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await _error(websocket, "frame was not valid JSON", "bad_json")
                    continue
                if not isinstance(message, dict):
                    await _error(websocket, "frame must be a JSON object", "bad_json")
                    continue

                message_type = message.get("type")

                if message_type == "JoinGame":
                    requested = message.get("player_id")
                    token = str(requested) if requested else None
                    label = message.get("label")
                    seat = room.claim(token, str(label) if label else None)
                    if not registered:
                        sockets.setdefault(game_id, []).append(holder)
                        registered = True
                    if seat is None:
                        holder[0] = None
                        await _error(
                            websocket,
                            "room is full; joining as spectator (read-only)",
                            "spectator",
                        )
                    else:
                        holder[0] = room.seats[seat].player_id
                        await broadcast_state(room)
                    continue

                token = holder[0]
                if token is None:
                    await _error(
                        websocket,
                        "no seat held; send JoinGame first",
                        "not_seated",
                    )
                    continue

                if message_type == "RetryAI":
                    if not room.ai_to_move():
                        await _error(websocket, "there is no pending AI turn", "not_ai_turn")
                    else:
                        await drive_ai(room)
                    continue

                loop = asyncio.get_running_loop()

                def notify_pending(_room: Room = room, _loop: Any = loop) -> None:
                    """Fired from the measurement worker thread when a QPU job starts.

                    Schedules a small pending frame on the event loop rather than reading
                    room state across threads, so it can never tear a partially applied
                    turn. The authoritative StateUpdate that follows clears it.
                    """
                    payload = {
                        "type": "QuantumPending",
                        "pending": True,
                        "game_id": room.game_id,
                        "backend": (
                            room.quantum_sampler.backend_label
                            if room.quantum_sampler is not None
                            else None
                        ),
                    }
                    _loop.call_soon_threadsafe(
                        lambda: asyncio.ensure_future(send_all(room, payload))
                    )

                if message_type == "Resign":
                    room.on_quantum_change = notify_pending
                    try:
                        # Resignation is a room mutation like any other: it takes the same
                        # lock, so it cannot finalize the game while a hardware-backed move
                        # is mid-flight (nor can that move commit after the game is over).
                        await run_room_mutation(room, room.resign, token)
                    except ProtocolError as exc:
                        await _error(websocket, str(exc), exc.code)
                        continue
                    await broadcast_state(room)
                    continue

                room.on_quantum_change = notify_pending
                try:
                    # The blocking QPU wait happens on a worker thread under the room lock,
                    # so the event loop keeps serving every other room while it runs.
                    await run_room_mutation(room, room.move, token, message)
                except QuantumMeasurementError as exc:
                    # No Aer/RNG fallback and no partial mutation: the move is refused and
                    # the room is exactly as it was.
                    await _error(websocket, str(exc), exc.code)
                    await broadcast_state(room)
                    continue
                except ProtocolError as exc:
                    # Refused moves never touch the state: the Error is the only effect.
                    await _error(websocket, str(exc), exc.code)
                    if room.paper_rules:
                        await broadcast_state(room)
                    continue
                await broadcast_state(room)
                await drive_ai(room)

        except WebSocketDisconnect:
            pass
        finally:
            if ticker is not None:
                ticker.cancel()
            remaining = [
                item for item in sockets.get(game_id, []) if item[1] is not websocket
            ]
            sockets[game_id] = remaining

    return app


async def _error(websocket: WebSocket, message: str, code: str) -> None:
    """Send one protocol ``Error`` frame."""
    await websocket.send_json({"type": "Error", "code": code, "message": message})


async def _tick(websocket: WebSocket, interval: float, game_id: str) -> None:
    """Per-second liveness tick; the client uses it to detect a dead link."""
    seconds = 0
    try:
        while True:
            await asyncio.sleep(interval)
            seconds += 1
            await websocket.send_json(
                {"type": "Tick", "t": seconds, "game_id": game_id}
            )
    except Exception:  # pragma: no cover - socket closed
        # CancelledError is a BaseException, so cancellation still propagates and the
        # task ends cleanly; any send failure just retires the ticker.
        return


#: Module-level app for ``uvicorn server.app:app``. Uses the default 1 s tick, no
#: on-disk log and whatever ``DISCORD_WEBHOOK_URL`` is set to; ``python -m server``
#: builds an app with logging switched on.
app = create_app()


__all__ = ["CLOSE_UNKNOWN_GAME", "CreateGameRequest", "app", "create_app"]
