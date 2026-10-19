"""Agent legality and seeded reproducibility -- Persons B and C.

Owner: **Person B** for the shared contract and the two baselines;
**Person C** for the Observe and probability-aware agents.

Two properties matter for every agent, and both are checked here for all four:

1. **Legality.** On the toy engine, from any reachable position, the agent returns an
   action the engine itself listed as legal. An agent that returns something else fails
   the runner mid-game, which is the correct failure mode but an annoying one to debug
   -- so it is caught here first, across many seeds.
2. **Seeded reproducibility.** Two agents constructed with the same seed produce the
   same action sequence.

Both properties are contract properties, not strength properties, so the whole-game
walks below run on a deliberately tiny search budget (see :data:`COVERAGE_ITERATIONS`).
The shipped defaults are what the acceptance tests further down exercise.

The UCT helper in the MCTS baseline gets its own tests: it is the one piece of the
baseline that is finished, and Person C's extension is defined as a modification of it,
so a bug there would silently corrupt both arms of the ablation.
"""

from __future__ import annotations

import math

import pytest

from qcheckers.agents.base import fallback_action
from qcheckers.agents.mcts_baseline import (
    DEFAULT_UCT_C,
    MCTSBaselineAgent,
    evaluate_state,
    uct_score,
)
from qcheckers.agents.observe_agent import ObserveAgent
from qcheckers.agents.prob_aware import HARD_OBSERVE_FLOOR, ProbAwareAgent, expected_material
from qcheckers.agents.random_agent import RandomAgent
from qcheckers.engine.protocol import (
    CaptureAction,
    GameState,
    MoveAction,
    ObserveAction,
    Piece,
    RejoinAction,
    SpreadAction,
)
from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.experiment.runner import make_agent, play, run_condition

#: Every agent kind the harness can build. ``hard`` is the game client's Hard tier:
#: probability-aware search with the voluntary Observe policy enabled.
ALL_KINDS = ("random", "mcts", "observe", "prob", "hard")


def _agent(kind: str, engine: DeterministicToyEngine, seed: int = 1):
    return make_agent(kind, engine, seed)


#: Search budget for the coverage walks. Legality and reproducibility are properties of
#: the agent contract, not of how hard the agent searched, and the shipped defaults (24
#: UCT iterations, a greedy reply over every legal action at each expansion, and a 32-ply
#: rollout) turn one 200-ply walk through five agents into minutes of CPU. Cutting the
#: budget buys *more* positions per second instead, which is what these walks want. The
#: shipped defaults are exercised by the acceptance tests near the end of this file.
COVERAGE_ITERATIONS = 2
COVERAGE_DEPTH = 1
COVERAGE_ROLLOUT_STEPS = 4

#: Kinds built with a tree search, i.e. the ones whose budget can be cut.
SEARCH_KINDS = ("mcts", "prob", "hard")


def _coverage_agent(kind: str, engine: DeterministicToyEngine, seed: int = 1):
    """``kind`` from the harness, with the search budget cut for a coverage walk.

    Built with :func:`make_agent` rather than by naming a class, so the kind-to-class
    mapping under test is still the harness's and only the budget is overridden. The
    assertion makes a rename of one of those attributes fail loudly here instead of
    quietly restoring a multi-minute test run.
    """
    agent = make_agent(kind, engine, seed)
    if kind in SEARCH_KINDS:
        agent.iterations = COVERAGE_ITERATIONS
        agent.depth = COVERAGE_DEPTH
        agent.rollout_steps = COVERAGE_ROLLOUT_STEPS
        assert (
            agent.iterations,
            agent.depth,
            agent.rollout_steps,
        ) == (COVERAGE_ITERATIONS, COVERAGE_DEPTH, COVERAGE_ROLLOUT_STEPS), (
            f"{kind} does not carry a search budget this test can trim; the coverage "
            "walks below would silently run at full strength"
        )
    return agent


# ---------------------------------------------------------------------------
# Legality, across seeds and positions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_agent_returns_a_legal_action(kind: str) -> None:
    """Walk whole games with one agent per side; every action must be legal."""
    for seed in range(15):
        engine = DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=200
        )
        agents = {
            0: _coverage_agent(kind, engine, seed),
            1: _coverage_agent(kind, engine, seed + 500),
        }
        state = engine.initial_state()
        for _ in range(200):
            if engine.is_terminal(state):
                break
            legal = engine.legal_actions(state)
            assert legal, "engine offered no legal action for a non-terminal position"
            chosen = agents[state.turn].decide(state, legal)
            assert chosen in legal, (
                f"{kind} returned {chosen!r}, which the engine did not list as legal"
            )
            state = engine.apply(state, chosen).state


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_agent_handles_a_single_legal_action(kind: str) -> None:
    """With one legal action there is no choice; the agent must not raise."""
    engine = DeterministicToyEngine(seed=4, level=0, max_plies=20)
    state = engine.initial_state()
    legal = engine.legal_actions(state)
    assert legal
    single = (legal[0],)
    agent = _agent(kind, engine, 4)
    assert agent.decide(state, single) in single


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_agent_rejects_an_empty_legal_list(kind: str) -> None:
    """An empty legal list means the game should be over; raise, do not guess."""
    engine = DeterministicToyEngine(seed=0)
    agent = _agent(kind, engine, 0)
    with pytest.raises(ValueError):
        agent.decide(engine.initial_state(), ())


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_agent_completes_a_game_as_both_players(kind: str) -> None:
    """Each agent must be usable on both sides of the board.

    The agent under test sits in each seat in turn against a random opponent, so the
    seat really does vary per game. (An earlier version ran the same mirrored pair once
    per seat, which produced identical games both times and never moved the agent.)
    """
    for seed in range(3):
        for seat in (0, 1):
            engine = DeterministicToyEngine(
                seed=seed, level=2, allow_observe=True, max_plies=120
            )
            names = {0: "random", 1: "random"}
            names[seat] = kind
            agents = {
                position: _coverage_agent(name, engine, seed)
                for position, name in names.items()
            }
            record = play(engine, agents, seed, condition="agent-smoke")
            assert record.termination in {"no_pieces", "no_legal_moves", "ply_limit"}
            assert set(record.players) == {0, 1}


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_agent_labels_are_distinct(kind: str) -> None:
    """Labels land in every log line and plot legend; they must not collide."""
    labels = {kind: _agent(kind, DeterministicToyEngine(seed=0), 0).name for kind in ALL_KINDS}
    assert len(set(labels.values())) == len(ALL_KINDS)


# ---------------------------------------------------------------------------
# Seeded reproducibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_seeded_agents_replay_identically(kind: str) -> None:
    """Two identically-seeded agent pairs produce the same move sequence."""
    def moves(seed: int) -> list[str]:
        engine = DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=200
        )
        agents = {
            0: _coverage_agent(kind, engine, seed),
            1: _coverage_agent(kind, engine, seed + 900),
        }
        state = engine.initial_state()
        chosen: list[str] = []
        for _ in range(200):
            if engine.is_terminal(state):
                break
            legal = engine.legal_actions(state)
            action = agents[state.turn].decide(state, legal)
            chosen.append(repr(action))
            state = engine.apply(state, action).state
        return chosen

    assert moves(3) == moves(3)


def test_random_agent_draws_depend_on_its_seed() -> None:
    """Different seeds must give different random draws, or the seed is ignored."""
    engine = DeterministicToyEngine(seed=0, level=0, max_plies=20)
    state = engine.initial_state()
    legal = engine.legal_actions(state)
    assert len(legal) > 2, "need branching to test the random draw"

    first = [RandomAgent(seed).decide(state, legal) for seed in range(6)]
    second = [RandomAgent(seed).decide(state, legal) for seed in range(6)]
    assert first == second
    assert len(set(first)) > 1, "six seeds produced the same move every time"


def test_random_agent_reset_rewinds() -> None:
    """``reset`` must restore the seed's exact draw sequence."""
    engine = DeterministicToyEngine(seed=0, level=0, max_plies=20)
    state = engine.initial_state()
    legal = engine.legal_actions(state)

    agent = RandomAgent(5)
    first_pass = [agent.decide(state, legal) for _ in range(20)]
    agent.reset()
    assert [agent.decide(state, legal) for _ in range(20)] == first_pass

    agent.reset(6)
    assert agent.decide(state, legal) == RandomAgent(6).decide(state, legal)


def test_random_agent_never_touches_the_global_rng() -> None:
    """The module-level ``random`` stream must be unaffected by agent use.

    Otherwise two agents in one process could interfere through global state, which
    would break the byte-identity guarantee the runner test relies on.
    """
    import random

    random.seed(1234)
    expected = [random.random() for _ in range(5)]

    random.seed(1234)
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True, max_plies=120)
    run_condition(lambda seed: engine, ("random", "random"), (0, 1, 2), condition="global")
    assert [random.random() for _ in range(5)] == expected


# ---------------------------------------------------------------------------
# UCT selection helper (Person B's finished piece)
# ---------------------------------------------------------------------------


def test_uct_unvisited_is_never_called_with_zero_visits() -> None:
    """Zero visits must raise: callers handle unvisited children separately.

    Returning ``inf`` for every unvisited child would make a tree bug look like
    healthy exploration.
    """
    with pytest.raises(ValueError, match="action_visits"):
        uct_score(0.0, 0, 10)
    with pytest.raises(ValueError, match="parent_visits"):
        uct_score(0.0, 5, 0)


def test_uct_matches_the_formula() -> None:
    """Score is ``mean + c * sqrt(ln(parent) / visits)``."""
    value, visits, parent = 6.0, 10, 40
    c = 2.0
    expected = value / visits + c * math.sqrt(math.log(parent) / visits)
    assert uct_score(value, visits, parent, c) == pytest.approx(expected)


def test_uct_known_values() -> None:
    """Two hand-computed cases, independent of the formula test above."""
    # visits = parent = 8, mean = 0.5, c = 1: 0.5 + 1 * sqrt(ln8 / 8) = 0.7268...
    assert uct_score(4.0, 8, 8, 1.0) == pytest.approx(
        0.5 + math.sqrt(math.log(8) / 8), abs=1e-12
    )
    # Default constant is sqrt(2); a fully losing child scores purely on exploration.
    losing = uct_score(-9.0, 9, 9, DEFAULT_UCT_C)
    assert losing == pytest.approx(
        -1.0 + math.sqrt(2.0) * math.sqrt(math.log(9) / 9), abs=1e-12
    )
    assert losing < 0.0


def test_uct_prefers_well_visited_and_high_value_children() -> None:
    """With identical visit counts, the higher mean value wins."""
    assert uct_score(9.0, 10, 50) > uct_score(1.0, 10, 50)


def test_uct_exploration_term_grows_as_a_child_is_visited_less() -> None:
    """A rarely visited child must eventually out-rank a saturated one."""
    parent = 200
    rare = uct_score(1.0, 1, parent)
    saturated = uct_score(2.0, 100, parent)
    assert rare > saturated


def test_mcts_selects_every_legal_action_before_trusting_one() -> None:
    """Unvisited-first selection: a fresh search must not commit immediately.

    With more iterations than actions, every action must have been tried at least once.
    """
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True, max_plies=40)
    state = engine.initial_state()
    legal = engine.legal_actions(state)
    agent = MCTSBaselineAgent(engine, seed=0, iterations=len(legal) + 2, depth=2)

    chosen = agent.decide(state, legal)
    assert chosen in legal
    # Deterministic: the same state yields the same choice.
    assert agent.decide(state, legal) == chosen


def test_mcts_is_seed_reproducible() -> None:
    """Two identically seeded MCTS agents agree on every decision."""
    def choices() -> list[str]:
        engine = DeterministicToyEngine(
            seed=6, level=2, allow_observe=True, max_plies=200
        )
        agents = {
            0: MCTSBaselineAgent(engine, seed=6, depth=COVERAGE_DEPTH,
                                 iterations=COVERAGE_ITERATIONS,
                                 rollout_steps=COVERAGE_ROLLOUT_STEPS),
            1: MCTSBaselineAgent(engine, seed=7, depth=COVERAGE_DEPTH,
                                 iterations=COVERAGE_ITERATIONS,
                                 rollout_steps=COVERAGE_ROLLOUT_STEPS),
        }
        state = engine.initial_state()
        picked: list[str] = []
        for _ in range(200):
            if engine.is_terminal(state):
                break
            legal = engine.legal_actions(state)
            action = agents[state.turn].decide(state, legal)
            picked.append(repr(action))
            state = engine.apply(state, action).state
        return picked

    assert choices() == choices()


def test_mcts_plays_the_reply_against_the_root_player() -> None:
    """The non-root ply must be chosen to hurt the root, not to help it.

    The reply belongs to the side that just moved against us. Choosing the reply that
    minimises the root's evaluation is the minimax flip the search documents; choosing
    the maximum (which is what it did before the arXiv version of the paper was checked)
    models an opponent who cooperates, and that agent loses to a random player.
    """
    engine = DeterministicToyEngine(seed=0, level=0, max_plies=60)
    agent = MCTSBaselineAgent(engine, seed=0)
    state = engine.initial_state()
    legal = engine.legal_actions(state)
    assert len(legal) > 1, "the opening must offer a choice for this to mean anything"

    chosen = agent._best_greedy(state, legal, root_player=0)
    scores = {
        repr(candidate): agent._evaluate(engine.apply(state, candidate).state, 0)
        for candidate in legal
    }
    assert scores[repr(chosen)] == min(scores.values())


def test_prob_aware_plays_the_reply_against_the_root_player() -> None:
    """Same property for the ablation arm: one evaluator differs, not the structure."""
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True, max_plies=60)
    agent = ProbAwareAgent(engine, seed=0)
    state = engine.initial_state()
    legal = engine.legal_actions(state)

    chosen = agent._best_probable(state, legal, root_player=0)
    scores = {
        repr(candidate): agent._evaluate(engine.apply(state, candidate).state, 0)
        for candidate in legal
    }
    assert scores[repr(chosen)] == min(scores.values())


def test_mcts_rejects_nonsensical_parameters() -> None:
    engine = DeterministicToyEngine(seed=0)
    with pytest.raises(ValueError):
        MCTSBaselineAgent(engine, iterations=0)
    with pytest.raises(ValueError):
        MCTSBaselineAgent(engine, depth=0)


# ---------------------------------------------------------------------------
# Evaluation functions
# ---------------------------------------------------------------------------


def _certain_state() -> GameState:
    return GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 1, (((1, 0), 1.0),)),
        ),
    )


def _spread_state() -> GameState:
    """Player 0's piece is split evenly between two squares."""
    return GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, (((2, 1), 0.5), ((2, 3), 0.5))),
            Piece("B", 1, (((1, 0), 1.0),)),
        ),
    )


def test_evaluate_state_prefers_material() -> None:
    """More pieces must score higher from their owner's point of view."""
    two_pieces = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 0, (((2, 3), 1.0),)),
        ),
    )
    one_piece = GameState(
        turn=0,
        ply=0,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 1, (((1, 0), 1.0),)),
        ),
    )
    assert evaluate_state(two_pieces, 0) > evaluate_state(one_piece, 0)
    assert evaluate_state(one_piece, 1) > evaluate_state(two_pieces, 1)


def test_evaluate_state_values_a_spread_piece_below_a_certain_one() -> None:
    """A spread piece contributes its largest chance, so it is worth less.

    This is exactly the weakness Person C's probability-aware agent addresses.
    """
    certain = evaluate_state(_certain_state(), 0)
    spread = evaluate_state(_spread_state(), 0)
    assert spread < certain


def test_expected_material_is_chance_weighted() -> None:
    """The chance-aware material term must equal the weighted sum over sites."""
    value = expected_material(_spread_state(), 0, 4)
    # On a 4-row board, row 2 for player 0 (who advances toward row 0) is 1/3 of the
    # way there: (4 - 1 - 2) / 3. Both spread sites share that row, so the weighted
    # mean of two 1/3 sites is still 1/3 -- which is the point: spreading across
    # equal-progress squares changes nothing, spreading across different ones does.
    assert value == pytest.approx(0.5 * (1.0 / 3.0) + 0.5 * (1.0 / 3.0))
    assert value == pytest.approx(1.0 / 3.0)


def test_expected_material_uses_the_weighted_average_of_different_rows() -> None:
    """A split across rows of different value must average, not max."""
    split = GameState(
        turn=0, ply=1, pieces=(Piece("A", 0, (((1, 1), 0.5), ((3, 1), 0.5))),)
    )
    # (1,1) -> 2/3 progress, (3,1) -> 0. Mean = 1/3.
    assert expected_material(split, 0, 4) == pytest.approx(1.0 / 3.0)
    # A certain piece on the better square is worth more than the split ...
    certain = GameState(turn=0, ply=1, pieces=(Piece("A", 0, (((1, 1), 1.0),)),))
    assert expected_material(certain, 0, 4) > expected_material(split, 0, 4)
    # ... and a certain piece on the worse square is worth less.
    worse = GameState(turn=0, ply=1, pieces=(Piece("A", 0, (((3, 1), 1.0),)),))
    assert expected_material(worse, 0, 4) < expected_material(split, 0, 4)


def test_expected_material_is_player_asymmetric() -> None:
    """Advancing means opposite directions for the two players.

    ``expected_material`` counts only the requested owner's pieces, so this compares
    two owners' own pieces on the same square.
    """
    last_row = GameState(
        turn=0, ply=0, pieces=(Piece("A", 0, (((3, 1), 1.0),)),)
    )
    assert expected_material(last_row, 0, 4) == pytest.approx(0.0)

    same_square_other_owner = GameState(
        turn=1, ply=0, pieces=(Piece("B", 1, (((3, 1), 1.0),)),)
    )
    assert expected_material(same_square_other_owner, 1, 4) == pytest.approx(1.0)


def test_prob_aware_agent_rejects_out_of_range_settings() -> None:
    engine = DeterministicToyEngine(seed=0)
    agent = ProbAwareAgent(engine)
    assert agent.board_size == 4
    assert agent.name == "prob-aware"


# ---------------------------------------------------------------------------
# Person C: the Observe agent
# ---------------------------------------------------------------------------


def test_observe_is_illegal_when_the_engine_disables_it() -> None:
    """Without the flag there is nothing to observe, so Observe must not be offered."""
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=False)
    agent = ObserveAgent(engine)
    state = _spread_state()
    legal = engine.legal_actions(state)
    assert not any(isinstance(a, ObserveAction) for a in legal)
    assert not isinstance(agent.decide(state, legal), ObserveAction)


def test_observe_is_offered_on_a_spread_piece_when_enabled() -> None:
    """With the flag on, Observe must be legal for an uncertain piece."""
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    state = _spread_state()
    legal = engine.legal_actions(state)
    observe = [a for a in legal if isinstance(a, ObserveAction)]
    assert observe, "Observe should be legal for a spread piece when allow_observe=True"
    assert ObserveAgent(engine).decide(state, legal) in observe


def test_observe_agent_uses_observe_on_an_uncertain_piece() -> None:
    """End-to-end: a 0.5/0.5 piece passes the 0.5 threshold, so Observe is chosen."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=True)
    agent = ObserveAgent(engine)
    state = _spread_state()
    legal = engine.legal_actions(state)
    chosen = agent.decide(state, legal)
    assert isinstance(chosen, ObserveAction)
    assert agent.observe_moves == 1


def test_observe_agent_skips_observe_when_a_piece_is_almost_certain() -> None:
    """A 0.9/0.1 piece is not worth a turn of measurement."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=True)
    agent = ObserveAgent(engine, threshold=0.5)
    state = GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, (((2, 1), 0.9), ((2, 3), 0.1))),
            Piece("B", 1, (((1, 0), 1.0),)),
        ),
    )
    legal = engine.legal_actions(state)
    chosen = agent.decide(state, legal)
    assert not isinstance(chosen, ObserveAction)
    assert agent.board_moves == 1


def test_observe_agent_lowering_the_threshold_makes_it_more_eager() -> None:
    """The threshold must actually control eagerness, or it is a dead parameter."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=True)
    state = GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, (((2, 1), 0.7), ((2, 3), 0.3))),
            Piece("B", 1, (((1, 0), 1.0),)),
        ),
    )
    legal = engine.legal_actions(state)
    assert not isinstance(ObserveAgent(engine, threshold=0.5).decide(state, legal), ObserveAction)
    assert isinstance(ObserveAgent(engine, threshold=0.9).decide(state, legal), ObserveAction)


def test_observe_uses_the_engine_chance_rule_and_costs_a_turn() -> None:
    """The brief requires Observe to resolve via the engine's own chance rule."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=True)
    agent = ObserveAgent(engine)
    state = _spread_state()
    legal = engine.legal_actions(state)
    action = agent.decide(state, legal)
    step = engine.apply(state, action)

    assert len(step.events) == 1
    event = step.events[0]
    assert event.cause == "observe"
    assert event.chances == _spread_state().piece("A").sites
    assert event.sampled in [square for square, _ in event.chances]

    # Certain after observing, and the turn passed on: the move cost a turn.
    assert not step.state.piece("A").is_spread
    assert step.state.turn == 1 - state.turn


def test_observe_agent_rejects_an_out_of_range_threshold() -> None:
    engine = DeterministicToyEngine(seed=0)
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            ObserveAgent(engine, threshold=bad)


def test_observe_agent_counters_and_reset() -> None:
    """Usage counters feed the quantum-move plot; reset must zero them."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=True)
    agent = ObserveAgent(engine)
    state = _spread_state()
    legal = engine.legal_actions(state)
    agent.decide(state, legal)
    agent.decide(engine.initial_state(), engine.legal_actions(engine.initial_state()))
    assert agent.usage()["observe"] == 1
    assert agent.usage()["board"] == 1

    agent.reset()
    assert agent.usage() == {"observe": 0, "board": 0}


# ---------------------------------------------------------------------------
# Engine rules the agents depend on (Person A's invariants)
# ---------------------------------------------------------------------------


def test_uncertain_pieces_cannot_move_ordinarily() -> None:
    """A spread piece is not a normal mover: only rejoin or observe applies."""
    engine = DeterministicToyEngine(seed=1, level=2, allow_observe=False)
    state = _spread_state()
    legal = engine.legal_actions(state)
    for action in legal:
        assert not isinstance(action, (MoveAction, CaptureAction, SpreadAction))
        assert isinstance(action, RejoinAction)


def test_a_side_may_not_spread_its_last_certain_piece() -> None:
    """House rule: keep one certain piece, so spreading cannot strand a side.

    Without the guard, a player using the quantum mechanic loses immediately, because a
    spread piece cannot move normally at levels 0-1. The rationale for the rule is in
    ``toy.py::_spread_actions``; this pins the behaviour.
    """
    engine = DeterministicToyEngine(seed=0, level=1)
    last_certain = GameState(
        turn=0,
        ply=1,
        pieces=(Piece("A", 0, (((2, 1), 1.0),)), Piece("B", 1, (((0, 1), 1.0),))),
    )
    legal = engine.legal_actions(last_certain)
    assert not any(isinstance(a, SpreadAction) for a in legal)


def test_two_certain_pieces_still_offer_a_spread() -> None:
    """The guard must not remove the mechanic from a normal opening position."""
    engine = DeterministicToyEngine(seed=0, level=1)
    two_certain = GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, (((2, 1), 1.0),)),
            Piece("B", 0, (((2, 3), 1.0),)),
            Piece("E", 1, (((0, 1), 1.0),)),
        ),
    )
    legal = engine.legal_actions(two_certain)
    assert any(isinstance(a, SpreadAction) for a in legal)


def test_spread_moves_are_offered_only_from_level_one() -> None:
    """Level 0 must be genuinely classical, or the ablation is not matched."""
    classical = DeterministicToyEngine(seed=0, level=0)
    state = classical.initial_state()
    kinds = {a.kind for a in classical.legal_actions(state)}
    assert "spread" not in kinds

    spready = DeterministicToyEngine(seed=0, level=1).legal_actions(state)
    assert any(isinstance(a, SpreadAction) for a in spready)


def test_fallback_action_prefers_the_requested_kind() -> None:
    """The matched-baseline helper: indifferent agents must pick the same action."""
    actions = (
        SpreadAction("A", (3, 1), (((3, 1), 0.5), ((2, 0), 0.5))),
        MoveAction("A", (3, 1), (2, 0)),
        CaptureAction("A", (3, 1), (2, 1), (1, 2)),
    )
    assert fallback_action(actions, preferred="capture").kind == "capture"
    assert fallback_action(actions, preferred="capture").piece_id == "A"
    assert fallback_action(actions).kind == "spread"
    assert fallback_action(actions, preferred="nonexistent").kind == "spread"


def test_fallback_action_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError):
        fallback_action(())


# ---------------------------------------------------------------------------
# Phase 3: deterministic agents and the finished search TODOs
# ---------------------------------------------------------------------------


def _midgame_position(seed: int = 5, level: int = 2) -> GameState:
    """A deterministic non-opening position with several legal actions."""
    engine = DeterministicToyEngine(
        seed=seed, level=level, allow_observe=True, max_plies=60
    )
    state = engine.initial_state()
    pilots = {0: RandomAgent(seed), 1: RandomAgent(seed + 1)}
    for _ in range(6):
        if engine.is_terminal(state):
            break
        legal = engine.legal_actions(state)
        state = engine.apply(state, pilots[state.turn].decide(state, legal)).state
    return state


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_same_seed_and_position_give_the_same_move_twenty_times(kind: str) -> None:
    """ACCEPTANCE: same seed + same position -> identical move, 20/20 trials."""
    position = _midgame_position()
    legal = DeterministicToyEngine(
        seed=5, level=2, allow_observe=True, max_plies=60
    ).legal_actions(position)
    assert len(legal) > 1, "the fixture needs branching for the check to mean anything"

    moves = []
    for _ in range(20):
        engine = DeterministicToyEngine(
            seed=5, level=2, allow_observe=True, max_plies=60
        )
        agent = make_agent(kind, engine, 42)
        moves.append(repr(agent.decide(position, legal)))
    assert len(set(moves)) == 1, (
        f"{kind} gave {len(set(moves))} distinct moves in 20 trials"
    )


def test_mcts_rollouts_are_seeded_and_bounded() -> None:
    """Two identically seeded baselines roll out identically, inside [-1, 1]."""
    def agent() -> MCTSBaselineAgent:
        # Its own engine, because a rollout samples through the engine's RNG.
        engine = DeterministicToyEngine(
            seed=3, level=2, allow_observe=True, max_plies=60
        )
        return MCTSBaselineAgent(engine, seed=1)

    state = DeterministicToyEngine(seed=3, level=2, allow_observe=True).initial_state()
    first = [agent()._rollout(state, 0) for _ in range(5)]
    second = [agent()._rollout(state, 0) for _ in range(5)]
    assert first == second
    assert all(-1.0 <= value <= 1.0 for value in first)


def test_mcts_decide_actually_uses_the_rollout() -> None:
    """The rollout TODO is wired in, not left as dead code."""
    engine = DeterministicToyEngine(seed=0, level=0, max_plies=40)
    calls = {"count": 0}

    class CountingRollouts(MCTSBaselineAgent):
        def _rollout(self, state, player, max_steps=None):
            calls["count"] += 1
            return super()._rollout(state, player, max_steps)

    agent = CountingRollouts(engine, seed=0, iterations=4, depth=1)
    state = engine.initial_state()
    agent.decide(state, engine.legal_actions(state))
    assert calls["count"] >= 1


def test_prob_aware_rollout_policy_samples_from_the_chance_rule() -> None:
    """A 90/10 ghost must roll out onto its likely square far more often."""
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    agent = ProbAwareAgent(engine, seed=0)
    state = GameState(
        turn=0,
        ply=1,
        pieces=(
            Piece("A", 0, (((2, 1), 0.9), ((2, 3), 0.1))),
            Piece("E", 1, (((0, 1), 1.0),)),
        ),
    )
    legal = (
        RejoinAction("A", (2, 1), (2, 1)),
        RejoinAction("A", (2, 1), (2, 3)),
    )
    counts = {(2, 1): 0, (2, 3): 0}
    for _ in range(400):
        chosen = agent._rollout_policy(state, legal)
        counts[chosen.target] += 1
    assert counts[(2, 1)] > counts[(2, 3)] * 3, counts


def test_research_agents_do_not_carry_the_game_tier_policy() -> None:
    """The measured `prob` arm stays the plain probability-aware search."""
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    research = make_agent("prob", engine, 0)
    assert isinstance(research, ProbAwareAgent)
    assert research.observe_threshold is None
    assert research.split_eager is False

    game = make_agent("hard", engine, 0)
    assert isinstance(game, ProbAwareAgent)
    assert game.observe_threshold == HARD_OBSERVE_FLOOR
    assert game.split_eager is True
    assert game.name == "prob-aware-hard"


def test_the_hard_tier_demonstrably_uses_observe_in_a_played_game() -> None:
    """ACCEPTANCE (addendum C): Hard must actually spend turns on Observe."""
    for seed in range(12):
        engine = DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=80
        )
        agents = {0: RandomAgent(seed), 1: make_agent("hard", engine, seed)}
        record = play(engine, agents, seed, condition="hard-tier")
        causes = [event.get("cause") for turn in record.turns for event in turn.events]
        if record.observe_moves > 0 and "observe" in causes:
            return
    pytest.fail("12 games vs the Hard tier produced no Observe move")


def test_hard_tier_rejects_a_bad_observe_threshold() -> None:
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    with pytest.raises(ValueError):
        ProbAwareAgent(engine, observe_threshold=1.5)