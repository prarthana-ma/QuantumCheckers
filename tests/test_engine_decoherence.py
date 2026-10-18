"""Level 4 (decoherence) engine rules -- game-only, flagged, never batched.

Owner: **Person A -- rules and engine guardian** for the rule, **Person B** for the
determinism and batch-boundary checks.

The addendum's boundary is non-negotiable and is what most of this file pins:

* the rule ships behind ``decoherence=True``, which is accepted **only** at level 4;
* levels 0-3 keep ``coherence is None``, so no research path can observe the counter;
* the batch runner refuses levels 3 and 4 (tested in ``test_engine_merge.py``);
* the auto-collapse reuses the existing sampling rule, so it is the same machinery as
  every other collapse rather than a second implementation.
"""

from __future__ import annotations

import pytest

from qcheckers.agents.random_agent import RandomAgent
from qcheckers.engine.protocol import (
    GameState,
    MoveAction,
    Piece,
    SpreadAction,
)
from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.experiment.runner import play

TICKS = 6


def _engine(seed: int = 0, *, board_size: int = 4, **kwargs) -> DeterministicToyEngine:
    return DeterministicToyEngine(
        seed=seed,
        level=4,
        decoherence=True,
        board_size=board_size,
        max_plies=80,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Flag and level contract
# ---------------------------------------------------------------------------


def test_level_four_requires_the_decoherence_flag() -> None:
    with pytest.raises(ValueError, match="decoherence"):
        DeterministicToyEngine(seed=0, level=4)


def test_decoherence_flag_is_refused_outside_level_four() -> None:
    """The rule cannot leak into a research level by accident."""
    for level in (0, 1, 2, 3):
        with pytest.raises(ValueError, match="level-4"):
            DeterministicToyEngine(seed=0, level=level, decoherence=True)


def test_decoherence_defaults_to_six_ticks_and_validates() -> None:
    assert _engine().decoherence_ticks == TICKS
    with pytest.raises(ValueError):
        _engine(decoherence_ticks=0)
    assert _engine(decoherence_ticks=9).decoherence_ticks == 9


def test_research_levels_never_carry_a_coherence_counter() -> None:
    """A level-2 split must leave ``coherence`` unset, or the flag would be leaky."""
    engine = DeterministicToyEngine(seed=0, level=2)
    state = engine.initial_state()
    spread = next(
        action for action in engine.legal_actions(state) if isinstance(action, SpreadAction)
    )
    stepped = engine.apply(state, spread).state
    assert stepped.piece(spread.piece_id).is_spread
    assert stepped.piece(spread.piece_id).coherence is None


# ---------------------------------------------------------------------------
# The counter
# ---------------------------------------------------------------------------


def test_a_fresh_split_starts_at_a_full_counter() -> None:
    engine = _engine()
    state = engine.initial_state()
    spread = next(
        action for action in engine.legal_actions(state) if isinstance(action, SpreadAction)
    )
    stepped = engine.apply(state, spread).state
    assert stepped.piece(spread.piece_id).coherence == TICKS


def test_the_counter_ticks_down_one_per_ply_it_goes_unmeasured() -> None:
    engine = _engine()
    state = engine.initial_state()
    spread = next(
        action for action in engine.legal_actions(state) if isinstance(action, SpreadAction)
    )
    state = engine.apply(state, spread).state

    # Two plies by other pieces: the spread piece ages by two.
    for expected in (TICKS - 1, TICKS - 2):
        action = engine.legal_actions(state)[0]
        if action.piece_id == spread.piece_id:
            break
        state = engine.apply(state, action).state
        assert state.piece(spread.piece_id).coherence == expected


def test_a_piece_expires_at_zero_and_uses_the_engine_chance_rule() -> None:
    """At zero the piece collapses through the same weighted sample as Observe."""
    engine = _engine()
    spread_piece = Piece(
        "A", 0, (((2, 1), 0.5), ((2, 3), 0.5)), coherence=1
    )
    state = GameState(
        turn=0,
        ply=4,
        pieces=(
            spread_piece,
            Piece("B", 0, (((3, 1), 1.0),)),
            Piece("E", 1, (((0, 1), 1.0),)),
        ),
    )

    # Move B; A goes one turn unmeasured and expires.
    move = MoveAction(piece_id="B", origin=(3, 1), target=(2, 0))
    assert move in engine.legal_actions(state)
    step = engine.apply(state, move)

    expiries = [event for event in step.events if event.cause == "decoherence"]
    assert len(expiries) == 1
    event = expiries[0]
    assert event.piece_id == "A"
    assert event.chances == spread_piece.sites
    assert event.probability == pytest.approx(0.5)
    assert event.sampled in [square for square, _ in spread_piece.sites]

    collapsed = step.state.piece("A")
    assert not collapsed.is_spread
    assert collapsed.coherence is None
    assert collapsed.squares == (event.sampled,)


def test_an_expiry_is_byte_reproducible() -> None:
    """Same seed, same expiry square, same log line."""

    def line() -> str:
        engine = _engine(seed=3)
        agents = {0: RandomAgent(3), 1: RandomAgent(1003)}
        return play(engine, agents, 3, condition="L4").to_line()

    assert line() == line()


def test_a_spread_piece_expires_after_exactly_ticks_unmeasured_plies() -> None:
    """Untouched for six plies, a fresh split collapses on the seventh.

    Deterministic and agent-free, so it pins the exact count rather than hoping a random
    game happens to keep a piece alive long enough.
    """
    # An 8x8 board is used so both sides always have a quiet move elsewhere; on 4x4 the
    # pieces block each other before the counter can run out.
    engine = _engine(seed=1, board_size=8)
    state = engine.initial_state()
    spread = next(
        action for action in engine.legal_actions(state) if isinstance(action, SpreadAction)
    )
    state = engine.apply(state, spread).state
    assert state.piece(spread.piece_id).coherence == TICKS

    expired = False
    for ply in range(TICKS + 2):
        untouched = [
            action
            for action in engine.legal_actions(state)
            if action.kind in ("move", "spread")
            and action.piece_id != spread.piece_id
        ]
        assert untouched, "the fixture must always leave a quiet move available"
        step = engine.apply(state, untouched[0])
        state = step.state
        if "decoherence" in [event.cause for event in step.events]:
            expired = True
            assert state.piece(spread.piece_id).coherence is None
            assert not state.piece(spread.piece_id).is_spread
            break
        assert state.piece(spread.piece_id).coherence == TICKS - 1 - ply

    assert expired, "an untouched fresh split must expire within the tick budget"


def test_a_measurement_refreshes_rather_than_expires() -> None:
    """A piece the acting player resolves is certain, so it can never expire."""
    engine = _engine(allow_observe=True)
    spread_piece = Piece("A", 0, (((2, 1), 0.5), ((2, 3), 0.5)), coherence=1)
    state = GameState(
        turn=0,
        ply=2,
        pieces=(spread_piece, Piece("E", 1, (((0, 1), 1.0),))),
    )
    observe = next(
        action
        for action in engine.legal_actions(state)
        if action.kind == "observe"
    )
    step = engine.apply(state, observe)
    assert not step.state.piece("A").is_spread
    assert step.state.piece("A").coherence is None
    # The only event is the observation itself, not an expiry.
    assert [event.cause for event in step.events] == ["observe"]


class _SplitOnceThenIgnore:
    """Splits once, then only moves and captures -- never rejoins its own ghost.

    Random agents rejoin (and merge) often enough that a fresh split rarely survives six
    plies, so this controlled policy is what makes "a played game can reach a decoherence
    expiry" a checkable claim. It is a test fixture, not a published agent.
    """

    name = "split-once-then-ignore"

    def __init__(self, seed: int) -> None:
        self._agent = RandomAgent(seed)
        self._split_done = False

    def decide(self, state, legal):
        if not self._split_done:
            spreads = [a for a in legal if a.kind == "spread"]
            if spreads:
                self._split_done = True
                return spreads[0]
        pool = [a for a in legal if a.kind in ("move", "capture")]
        return self._agent.decide(state, pool) if pool else legal[0]


def test_decoherence_expiries_happen_in_real_play() -> None:
    """The rule must be reachable in an actual game, not only in a hand-made state."""
    found = 0
    for seed in range(12):
        record = play(
            _engine(seed),
            {
                0: _SplitOnceThenIgnore(seed),
                1: _SplitOnceThenIgnore(seed + 1000),
            },
            seed,
            condition="L4-reach",
        )
        found += len(
            [t for t in record.turns for e in t.events if e.get("cause") == "decoherence"]
        )
    assert found, "12 controlled level-4 games produced no decoherence expiry"


def test_render_exposes_the_counter_for_the_game_client() -> None:
    engine = _engine()
    state = engine.initial_state()
    spread = next(
        action for action in engine.legal_actions(state) if isinstance(action, SpreadAction)
    )
    rendered = engine.render(engine.apply(state, spread).state)
    assert rendered["decoherence"] is True
    assert rendered["decoherence_ticks"] == TICKS
    by_id = {piece["piece_id"]: piece for piece in rendered["pieces"]}
    assert by_id[spread.piece_id]["coherence"] == TICKS
