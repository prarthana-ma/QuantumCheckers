"""Live UCT search must model opposing and stochastic replies at state nodes."""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest

from qcheckers.agents.live_mcts import LiveMCTSAgent, evaluate_state
from qcheckers.engine.paper import BranchLimitError


@dataclass(frozen=True)
class TinyPiece:
    piece_id: str
    owner: int
    sites: tuple[tuple[tuple[int, int], float], ...]
    is_king: bool = False


@dataclass(frozen=True)
class TinyState:
    turn: int
    ply: int
    phase: str
    pieces: tuple[TinyPiece, ...]
    captured: tuple[str, ...] = ()
    winner: int | None = None
    amplitudes: tuple[int, ...] = ()


@dataclass(frozen=True)
class TinyAction:
    name: str


@dataclass(frozen=True)
class TinyOutcome:
    winner: int | None


class ReplyEngine:
    board_size = 4

    def __init__(self, seed: int = 0, sampler=None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.sampler = sampler
        self.clone_calls = 0

    def clone(self, seed: int | None = None):
        self.clone_calls += 1
        return type(self)(self.seed if seed is None else seed)

    def legal_actions(self, state: TinyState):
        if state.winner is not None or state.phase in ("draw", "win", "loss"):
            return ()
        if state.phase == "start":
            return (TinyAction("trap"), TinyAction("safe"))
        if state.phase == "trap":
            return (TinyAction("punish"), TinyAction("blunder"))
        return ()

    def apply(self, state: TinyState, action: TinyAction):
        if state.phase == "start" and action.name == "trap":
            return ReplyStep(TinyState(1, state.ply + 1, "trap", state.pieces))
        if state.phase == "start" and action.name == "safe":
            return ReplyStep(TinyState(0, state.ply + 1, "draw", state.pieces))
        if state.phase == "trap" and action.name == "punish":
            return ReplyStep(TinyState(0, state.ply + 1, "loss", state.pieces, winner=1))
        if state.phase == "trap" and action.name == "blunder":
            return ReplyStep(TinyState(0, state.ply + 1, "win", state.pieces, winner=0))
        raise ValueError("unexpected action")

    def outcome(self, state: TinyState):
        if state.phase == "draw":
            return TinyOutcome(None)
        if state.winner is not None:
            return TinyOutcome(state.winner)
        return None


@dataclass(frozen=True)
class ReplyStep:
    state: TinyState


class ContinuationEngine(ReplyEngine):
    def legal_actions(self, state: TinyState):
        if state.phase == "start":
            return (TinyAction("continue"), TinyAction("draw"))
        if state.phase == "continue":
            return (TinyAction("lose"), TinyAction("win"))
        return ()

    def apply(self, state: TinyState, action: TinyAction):
        if state.phase == "start" and action.name == "continue":
            return ReplyStep(TinyState(0, state.ply + 1, "continue", state.pieces))
        if state.phase == "start" and action.name == "draw":
            return ReplyStep(TinyState(0, state.ply + 1, "draw", state.pieces))
        if state.phase == "continue" and action.name == "lose":
            return ReplyStep(TinyState(1, state.ply + 1, "loss", state.pieces, winner=1))
        if state.phase == "continue" and action.name == "win":
            return ReplyStep(TinyState(1, state.ply + 1, "win", state.pieces, winner=0))
        raise ValueError("unexpected action")


class ChanceEngine(ReplyEngine):
    def legal_actions(self, state: TinyState):
        if state.phase == "start":
            return (TinyAction("lottery"), TinyAction("safe"))
        return ()

    def apply(self, state: TinyState, action: TinyAction):
        if action.name == "safe":
            return ReplyStep(TinyState(1, state.ply + 1, "draw", state.pieces))
        if action.name == "lottery":
            winner = 0 if self.rng.random() < 0.2 else 1
            phase = "win" if winner == 0 else "loss"
            return ReplyStep(TinyState(1, state.ply + 1, phase, state.pieces, winner=winner))
        raise ValueError("unexpected action")


class BranchLimitEngine(ReplyEngine):
    def legal_actions(self, state: TinyState):
        if state.phase == "start":
            return (TinyAction("capped"), TinyAction("safe"))
        return ()

    def apply(self, state: TinyState, action: TinyAction):
        if action.name == "capped":
            raise BranchLimitError("simulated branch cap")
        if action.name == "safe":
            return ReplyStep(TinyState(1, state.ply + 1, "draw", state.pieces))
        raise ValueError("unexpected action")


class InvalidActionEngine(ReplyEngine):
    def legal_actions(self, state: TinyState):
        return (TinyAction("invalid"),)

    def apply(self, state: TinyState, action: TinyAction):
        raise ValueError("ordinary rule error")


class BranchWorkEngine(ReplyEngine):
    def __init__(self, seed: int = 0, sampler=None, apply_log=None):
        super().__init__(seed, sampler)
        self.apply_log = [] if apply_log is None else apply_log

    def clone(self, seed: int | None = None):
        self.clone_calls += 1
        return BranchWorkEngine(self.seed if seed is None else seed, apply_log=self.apply_log)

    def legal_actions(self, state: TinyState):
        if state.phase == "start":
            return (TinyAction("left"), TinyAction("right"))
        if state.phase == "reply":
            return (TinyAction("continue"),)
        return ()

    def apply(self, state: TinyState, action: TinyAction):
        self.apply_log.append((state.phase, action.name))
        if state.phase == "start":
            return ReplyStep(TinyState(1, state.ply + 1, "reply", state.pieces))
        return ReplyStep(TinyState(1, state.ply + 1, "reply", state.pieces))


def _start_state(turn: int = 0) -> TinyState:
    pieces = (
        TinyPiece("A", 0, (((3, 0), 1.0),)),
        TinyPiece("B", 1, (((0, 3), 1.0),)),
    )
    return TinyState(turn, 0, "start", pieces)


def test_live_search_chooses_safety_against_an_adverse_opponent_reply() -> None:
    engine = ReplyEngine()
    state = _start_state()
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(engine, seed=3, iterations=100, tree_depth=4, rollout_steps=4)

    chosen = agent.decide(state, legal)

    assert chosen == TinyAction("safe")
    assert chosen in legal


def test_same_player_continuation_is_searched_as_maximizing_for_root() -> None:
    engine = ContinuationEngine()
    state = _start_state()
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(engine, seed=6, iterations=120, tree_depth=4, rollout_steps=4)

    assert agent.decide(state, legal) == TinyAction("continue")


def test_search_replays_chance_actions_into_distinct_state_branches() -> None:
    engine = ChanceEngine()
    state = _start_state()
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(engine, seed=5, iterations=250, tree_depth=4, rollout_steps=2)

    assert agent.decide(state, legal) == TinyAction("safe")


def test_decision_is_seed_repeatable_and_does_not_use_live_sampler_or_rng() -> None:
    sampler_calls = 0

    def sampler(_state):
        nonlocal sampler_calls
        sampler_calls += 1
        raise AssertionError("live hardware sampler must never run in search")

    engine = ChanceEngine(sampler=sampler)
    before_rng = engine.rng.getstate()
    state = _start_state()
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(engine, seed=19, iterations=100, tree_depth=4, rollout_steps=2)

    first = agent.decide(state, legal)
    second = agent.decide(state, legal)

    assert first == second
    assert first in legal
    assert engine.clone_calls == 2
    assert engine.rng.getstate() == before_rng
    assert sampler_calls == 0


def test_live_search_rejects_an_empty_action_list() -> None:
    agent = LiveMCTSAgent(ReplyEngine())

    with pytest.raises(ValueError, match="no legal actions"):
        agent.decide(_start_state(), ())


def test_branch_capped_root_action_is_skipped_for_an_available_alternative() -> None:
    engine = BranchLimitEngine()
    before_rng = engine.rng.getstate()
    state = _start_state()
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(engine, seed=29, iterations=40, tree_depth=4, rollout_steps=2)

    chosen = agent.decide(state, legal)

    assert chosen == TinyAction("safe")
    assert chosen in legal
    assert engine.rng.getstate() == before_rng


def test_live_search_does_not_swallow_non_cap_rule_errors() -> None:
    engine = InvalidActionEngine()
    agent = LiveMCTSAgent(engine, seed=31, iterations=1, tree_depth=2, rollout_steps=1)

    with pytest.raises(ValueError, match="ordinary rule error"):
        agent.decide(_start_state(), engine.legal_actions(_start_state()))


def test_branch_work_budget_cuts_off_rollouts_by_state_branch_count() -> None:
    engine = BranchWorkEngine()
    state = TinyState(0, 0, "start", _start_state().pieces, amplitudes=tuple(range(10)))
    legal = engine.legal_actions(state)
    agent = LiveMCTSAgent(
        engine,
        seed=37,
        iterations=12,
        tree_depth=4,
        rollout_steps=8,
        branch_work_budget=1,
    )

    chosen = agent.decide(state, legal)

    assert chosen in legal
    assert len(engine.apply_log) == agent.iterations
    assert all(phase == "start" for phase, _ in engine.apply_log)


def test_evaluator_is_zero_sum_counts_survival_and_king_value() -> None:
    pieces = (
        TinyPiece("A", 0, (((3, 0), 0.25), ((1, 2), 0.25)), is_king=True),
        TinyPiece("B", 1, (((0, 3), 0.5),)),
    )
    state = TinyState(0, 0, "start", pieces)

    p0 = evaluate_state(state, 0, board_size=4)
    p1 = evaluate_state(state, 1, board_size=4)

    assert p0 == pytest.approx(-p1)
    assert p0 > 0
    assert abs(p0) <= 1


def test_evaluator_does_not_apply_global_captured_piece_penalty() -> None:
    pieces = (
        TinyPiece("A", 0, (((3, 0), 1.0),)),
        TinyPiece("B", 1, (((0, 3), 1.0),)),
    )
    state = TinyState(0, 4, "start", pieces)
    captured = TinyState(0, 4, "start", pieces, captured=("B",))

    assert evaluate_state(state, 0, board_size=4) == evaluate_state(
        captured, 0, board_size=4
    )
