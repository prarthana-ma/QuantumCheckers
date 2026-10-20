"""Game engine layer.

Person A owns ``protocol.py`` and ``toy.py``. Nothing outside this
subpackage may change core rule logic.
"""

from qcheckers.engine.protocol import (
    Action,
    CaptureAction,
    CollapseEvent,
    GameEngine,
    GameOutcome,
    GameState,
    MergeAction,
    MoveAction,
    ObserveAction,
    Piece,
    RejoinAction,
    SpreadAction,
    Square,
    Step,
    board_chances,
    board_size_of,
    describe_state,
    uncertain_pieces,
)

__all__ = [
    "Action",
    "CaptureAction",
    "CollapseEvent",
    "GameEngine",
    "GameOutcome",
    "GameState",
    "MergeAction",
    "MoveAction",
    "ObserveAction",
    "Piece",
    "RejoinAction",
    "SpreadAction",
    "Square",
    "Step",
    "board_chances",
    "board_size_of",
    "describe_state",
    "uncertain_pieces",
]