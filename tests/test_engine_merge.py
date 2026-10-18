"""Level 3 (merge) engine rules -- Person A's rule logic, Person B's harness rules.

Owner: **Person A -- rules and engine guardian** (rule logic), with the determinism and
harness checks belonging to Person B.

Level 3 is playable but must **never** be batched (brief Phase 0 rules note). These tests
pin the two things that make that safe:

1. The merge rule itself: legal only for the mover's two *diagonally adjacent* own
   pieces, and its effect is the inverse of a split (two certain pieces become one
   50/50 spread piece).
2. Ablation integrity: levels 0-2 must never grow a merge action, so the classical
   and quantum arms of the study stay exactly as they were before level 3 existed.

Plus a full-game consistency walk at level 3, mirroring the level-2 regression guard in
``tests/test_runner.py``: the engine must never report a stuck position as playable.
"""

from __future__ import annotations

import pytest

from qcheckers.agents.random_agent import RandomAgent
from qcheckers.engine.protocol import (
    GameState,
    MergeAction,
    MoveAction,
    Piece,
)
from qcheckers.engine.toy import DeterministicToyEngine, _merge_sites
from qcheckers.experiment.runner import play, run_condition


def _two_pieces(first: tuple[int, int], second: tuple[int, int]) -> GameState:
    """Player 0 to move with two certain pieces on ``first`` and ``second``.

    A single player-1 piece is included so the engine does not (correctly) treat the
    position as a player-1 win by ``no_pieces`` and return no legal actions.
    """
    return GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, ((first, 1.0),)),
            Piece("B", 0, ((second, 1.0),)),
            Piece("E", 1, (((0, 1), 1.0),)),
        ),
    )


def _merges(engine: DeterministicToyEngine, state: GameState) -> list[MergeAction]:
    return [a for a in engine.legal_actions(state) if isinstance(a, MergeAction)]


# ---------------------------------------------------------------------------
# Legality
# ---------------------------------------------------------------------------


def test_level_three_is_accepted_and_level_four_is_not() -> None:
    """The engine accepts 0-3 and rejects anything else rather than guessing."""
    for level in (0, 1, 2, 3):
        assert DeterministicToyEngine(seed=0, level=level).level == level
    with pytest.raises(ValueError):
        DeterministicToyEngine(seed=0, level=4)


def test_merge_offered_for_diagonally_adjacent_own_pieces() -> None:
    """Two diagonal neighbours can merge; the option names the lower-id piece first."""
    engine = DeterministicToyEngine(seed=0, level=3)
    merges = _merges(engine, _two_pieces((2, 1), (1, 2)))
    assert merges
    assert all(a.piece_id == "A" and a.other_piece_id == "B" for a in merges)


def test_merge_is_not_offered_when_pieces_are_not_diagonal_neighbours() -> None:
    """Same-row pieces are not mergeable -- the rule is adjacency, not proximity."""
    engine = DeterministicToyEngine(seed=0, level=3)
    assert _merges(engine, _two_pieces((2, 1), (2, 3))) == []


@pytest.mark.parametrize("level", [0, 1, 2])
def test_levels_below_three_never_offer_a_merge(level: int) -> None:
    """Ablation integrity: the pre-level-3 arms must not gain a merge action."""
    engine = DeterministicToyEngine(seed=0, level=level)
    state = _two_pieces((2, 1), (1, 2))
    assert not any(isinstance(a, MergeAction) for a in engine.legal_actions(state))


def test_merge_of_two_certain_pieces_is_a_fifty_fifty_spread() -> None:
    """The effect is the inverse of a split: two certain pieces become one 0.5/0.5."""
    engine = DeterministicToyEngine(seed=0, level=3)
    state = _two_pieces((2, 1), (1, 2))
    action = _merges(engine, state)[0]
    step = engine.apply(state, action)

    survivors = sorted(p.piece_id for p in step.state.pieces)
    assert survivors == ["A", "E"], "only the other merged piece is consumed"
    merged = step.state.piece("A")
    assert merged.is_spread
    assert dict((s, round(w, 6)) for s, w in merged.sites) == {(2, 1): 0.5, (1, 2): 0.5}
    assert step.state.turn == 1, "a merge costs the turn"
    assert not step.events, "a merge is not a measurement, so it logs no collapse"


def test_merge_site_combining_normalises_overlaps() -> None:
    """``_merge_sites`` sums shared squares and renormalises to 1.0."""
    sites = _merge_sites((((2, 1), 0.5), ((1, 2), 0.5)), (((2, 1), 1.0),))
    assert dict(sites) == {(2, 1): 0.75, (1, 2): 0.25}
    assert sum(weight for _, weight in sites) == pytest.approx(1.0)


def test_merge_action_serialises_with_a_stable_kind() -> None:
    """The action's JSON is part of the log contract; the kind must be ``merge``."""
    action = MergeAction(piece_id="A", origin=(2, 1), other_piece_id="B")
    assert action.to_json() == {
        "kind": "merge",
        "piece_id": "A",
        "origin": [2, 1],
        "other_piece_id": "B",
    }


# ---------------------------------------------------------------------------
# Determinism and full-game consistency
# ---------------------------------------------------------------------------


def _play_level3(seed: int, *, allow_observe: bool = False, max_plies: int = 80):
    """Play one level-3 game with :func:`play`, not the batch runner.

    :func:`run_condition` deliberately refuses level 3, so the single-game primitive is
    the only way to exercise it from Python.
    """
    engine = DeterministicToyEngine(
        seed=seed, level=3, allow_observe=allow_observe, max_plies=max_plies
    )
    agents = {0: RandomAgent(seed), 1: RandomAgent(seed + 1000)}
    return play(engine, agents, seed, condition="L3")


def test_level_three_games_are_seed_reproducible() -> None:
    """Level 3 stays byte-reproducible: no global RNG, stable action ordering."""
    def batch() -> list[str]:
        return [_play_level3(seed).to_line() for seed in (1, 2, 3)]

    assert batch() == batch()


def test_level_three_merge_actions_actually_occur_in_play() -> None:
    """The rule must be reachable, not dead code on a diagonal-adjacency technicality."""
    records = [_play_level3(seed) for seed in range(30)]
    merges = [t for r in records for t in r.turns if t.action.kind == "merge"]
    assert merges, "30 level-3 games produced no merge"


def test_the_batch_runner_refuses_levels_three_and_four() -> None:
    """Boundary (addendum D): the batch runner must never include a game-only level."""
    for level in (3, 4):
        def factory(seed: int, level: int = level) -> DeterministicToyEngine:
            return DeterministicToyEngine(
                seed=seed, level=level, decoherence=(level == 4), max_plies=40
            )

        with pytest.raises(ValueError, match="refusing to batch"):
            run_condition(
                factory, ("random", "random"), (0, 1), condition="not-batched"
            )


def test_level_three_never_reports_a_stuck_position_as_playable() -> None:
    """``is_terminal`` and ``legal_actions`` must agree at level 3 too."""
    for seed in range(12):
        engine = DeterministicToyEngine(
            seed=seed, level=3, allow_observe=True, max_plies=200
        )
        agents = {0: RandomAgent(seed), 1: RandomAgent(seed + 500)}
        state = engine.initial_state()
        for _ in range(200):
            if engine.is_terminal(state):
                assert engine.legal_actions(state) == ()
                break
            legal = engine.legal_actions(state)
            assert legal, f"seed {seed}: non-terminal with no legal action"
            state = engine.apply(state, agents[state.turn].decide(state, legal)).state
        else:  # pragma: no cover - only on a hang
            pytest.fail(f"seed {seed}: level-3 game never terminated")


def test_merge_is_listed_after_classical_actions_in_the_sorted_set() -> None:
    """Stable ordering: ``merge`` sorts last among the kinds, so logs stay comparable."""
    engine = DeterministicToyEngine(seed=0, level=3)
    state = _two_pieces((2, 1), (1, 2))
    kinds = [a.kind for a in engine.legal_actions(state)]
    assert kinds == sorted(kinds)
    assert "merge" in kinds


def test_move_action_kind_is_unchanged_by_the_level_three_addition() -> None:
    """A guard that the additive change did not accidentally reshape older actions."""
    assert MoveAction("A", (3, 1), (2, 0)).to_json()["kind"] == "move"
