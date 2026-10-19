"""The agent interface every baseline and extension implements.

Owner: **Person B -- baseline agents and harness**. Person A owns the engine types an
agent sees; Person B owns this protocol and the baseline implementations.

An agent sees a :class:`~qcheckers.engine.protocol.GameState` and returns exactly one
legal :class:`~qcheckers.engine.protocol.Action`. That is the whole contract. The
runner enforces legality, so an agent that returns something illegal fails loudly
rather than corrupting a game log.

Agents must not mutate the state they are given: :class:`GameState` is frozen, and the
only permitted way to "look ahead" is to call ``engine.apply`` and inspect the
returned :class:`~qcheckers.engine.protocol.Step`.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from qcheckers.engine.protocol import Action, GameEngine, GameState

#: Structural alias for an engine, kept local so agents can be type-annotated without
#: importing the concrete toy engine.
EngineLike = GameEngine


@runtime_checkable
class Agent(Protocol):
    """A decision-maker for one side of one game.

    Attributes
    ----------
    name:
        Short stable label. Logged verbatim into every ``GameRecord``, so it appears
        in plots and the ablation table; keep it filesystem- and JSON-safe.
    """

    name: str

    def decide(self, state: GameState, legal: Sequence[Action]) -> Action:
        """Choose one action from ``legal``.

        Parameters
        ----------
        state:
            The current position. Treated as read-only.
        legal:
            Non-empty list of legal actions, already ordered deterministically by the
            engine. Returning something outside this list is a bug and the runner will
            raise.

        Returns
        -------
        Action
            One element of ``legal``.

        Notes
        -----
        ``legal`` is passed explicitly rather than re-derived from the engine so an
        agent cannot silently disagree with the engine about what is legal -- which
        would hide exactly the class of bug Person A's tests exist to catch.
        """
        ...


def fallback_action(legal: Sequence[Action], preferred: str | None = None) -> Action:
    """Pick an action when an agent has no preference.

    Tries ``preferred`` kind first (matched-baseline fairness: every agent in an
    ablation should be forced onto the same move when both are indifferent), then
    falls back to the first legal action. Never raises for a non-empty ``legal``.
    """
    if not legal:
        raise ValueError("no legal actions: game should have been terminal")
    if preferred is not None:
        for action in legal:
            if action.kind == preferred:
                return action
    return legal[0]


__all__ = ["Agent", "EngineLike", "fallback_action"]