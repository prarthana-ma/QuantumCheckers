"""Quantum Checkers game server (FastAPI + WebSockets).

Owner: **P5 -- rules, engine, harness and batches**.

Public surface:

* :func:`server.app.create_app` -- build the ASGI app (tests use this with ticks off).
* :class:`server.rooms.Room` -- one in-memory match, engine-authoritative.
* :class:`server.rooms.RoomRegistry` -- in-memory lobby table.

The server adds no rule logic. It resolves each client message against
``qcheckers.engine.legal_actions`` and applies the matching action, so the engine stays
the single source of truth (brief constraint C1). The contract is frozen in
``docs/PROTOCOL.md``.
"""

from server.app import CLOSE_UNKNOWN_GAME, CreateGameRequest, create_app
from server.rooms import (
    AI_AGENT_KINDS,
    MODES,
    SUPPORTED_LEVELS,
    ProtocolError,
    Room,
    RoomRegistry,
    Seat,
    resolve_action,
)

__all__ = [
    "AI_AGENT_KINDS",
    "CLOSE_UNKNOWN_GAME",
    "CreateGameRequest",
    "MODES",
    "ProtocolError",
    "Room",
    "RoomRegistry",
    "SUPPORTED_LEVELS",
    "Seat",
    "create_app",
    "resolve_action",
]
