"""Runner determinism, JSONL round-trip and harness robustness -- Person B's tests.

Owner: **Person B -- baseline agents and harness**.

The tests here are the ones the brief makes load-bearing. Section 12 requires
"deterministic unit checks ... plus a fixed-seed smoke test that two agents can
complete a game headlessly", and section 16 Gate 3 requires a headless run that
produces a log. Section 12 also requires logs to be "sufficient to regenerate plots and
tables" and "regenerable from seeds".

The byte-identity test is the load-bearing one: it is what makes "regenerable from
seeds" a checkable claim rather than an intention. Two separate processes are not
needed for that -- within one process, two independently constructed engine/agent pairs
sharing a seed must produce the same bytes, which is exactly what would break if any
component reached for a global RNG or an unordered iteration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qcheckers.agents.random_agent import RandomAgent
from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.experiment.runner import (
    kind_for_label,
    append_jsonl,
    make_agent,
    play,
    read_jsonl,
    run_condition,
    write_jsonl,
)
from qcheckers.experiment.schema import GameRecord


def _agents(engine: DeterministicToyEngine, seed: int) -> dict:
    """A matched pair of seeded random agents."""
    return {0: RandomAgent(seed), 1: RandomAgent(seed + 1000)}


def _play(
    seed: int, *, level: int = 2, allow_observe: bool = True
) -> GameRecord:
    engine = DeterministicToyEngine(
        seed=seed, level=level, allow_observe=allow_observe, max_plies=120
    )
    return play(engine, _agents(engine, seed), seed, condition="unit")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_seed_is_byte_identical() -> None:
    """Two independent runs of the same seed produce byte-identical JSON lines.

    The core reproducibility claim. Everything in this project -- regenerable plots,
    resumable batches, a replayable demo -- depends on it.
    """
    first = _play(11).to_line()
    second = _play(11).to_line()
    assert first == second
    assert len(first) > 0


def test_different_seed_produces_a_different_record() -> None:
    """Different seeds must actually diverge, or determinism would be trivial.

    Seed 11 and seed 12 are checked to differ; if a future engine change made every
    seed play the same game, this test would catch it.
    """
    assert _play(11).to_line() != _play(12).to_line()


def test_agent_seed_alone_changes_the_game() -> None:
    """With the engine seeded identically, changing the agent seed must change play.

    Guards against an agent accidentally reading the engine's RNG or being deterministic
    in a way that ignores its own seed.
    """
    def line_for(agent_seed: int) -> str:
        engine = DeterministicToyEngine(
            seed=7, level=2, allow_observe=True, max_plies=120
        )
        agents = {0: RandomAgent(agent_seed), 1: RandomAgent(99)}
        return play(engine, agents, 7, condition="unit").to_line()

    assert line_for(1) != line_for(2)


def test_run_condition_is_reproducible() -> None:
    """A whole condition, not just one game, must be seed-reproducible."""
    def batch() -> list[str]:
        return [
            record.to_line()
            for record in run_condition(
                lambda seed: DeterministicToyEngine(
                    seed=seed, level=2, allow_observe=True, max_plies=120
                ),
                ("prob", "random"),
                (1, 2, 3),
                condition="repro",
            )
        ]

    assert batch() == batch()


def test_replaying_from_recorded_seed_reproduces_the_record() -> None:
    """The log's own ``seed`` field must be enough to regenerate that log line.

    This is exactly the "regenerable from seeds" requirement, tested end to end.
    """
    original = _play(23, level=2, allow_observe=True)
    payload = original.to_json()

    engine = DeterministicToyEngine(
        seed=payload["seed"], level=2, allow_observe=True, max_plies=120
    )
    agents = {
        player: RandomAgent(payload["seed"] + (1000 if player == 1 else 0))
        for player in (0, 1)
    }
    replayed = play(
        engine, agents, payload["seed"], condition=payload["condition"]
    )
    assert replayed.to_line() == original.to_line()


# ---------------------------------------------------------------------------
# Headless smoke test
# ---------------------------------------------------------------------------


def test_two_agents_complete_a_game_headlessly(tmp_path: Path) -> None:
    """Gate 3 smoke test: a full game, headless, producing a log file."""
    output = tmp_path / "smoke.jsonl"
    records = run_condition(
        lambda seed: DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=120
        ),
        ("random", "random"),
        tuple(range(5)),
        condition="smoke",
        output=output,
    )

    assert len(records) == 5
    assert output.exists()

    lines = output.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5

    for record in records:
        # Every game must terminate for a reason, not run out of road.
        assert record.termination in {"no_pieces", "no_legal_moves", "ply_limit"}
        assert record.length > 0
        assert record.length == len(record.turns)
        assert set(record.players) == {0, 1}


def test_collapse_events_are_logged_when_observe_is_enabled(tmp_path: Path) -> None:
    """Observe must produce real collapse events, not just an incrementing counter."""
    records = run_condition(
        lambda seed: DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=200
        ),
        ("observe", "random"),
        tuple(range(40)),
        condition="observe",
    )
    collapsed = [record for record in records if record.collapses > 0]
    assert collapsed, "no game in 40 produced a collapse via Observe"

    # Piece ids must come from the engine's own opening, not be invented by a log bug.
    engine_piece_ids = {
        piece.piece_id for piece in DeterministicToyEngine(seed=0).initial_state().pieces
    }

    for record in collapsed:
        assert record.observe_moves > 0
        assert set(record.collapse_pieces).issubset(engine_piece_ids)
        events = [event for turn in record.turns for event in turn.events]
        assert len(events) == record.collapses
        for event in events:
            assert event["cause"] in {"observe", "capture", "rejoin", "join"}
            assert 0.0 <= event["probability"] <= 1.0
            assert len(event["chances"]) >= 1
            # The sampled square must be one of the pre-collapse candidates, and its
            # recorded probability must match that candidate's weight.
            weights = {(s[0], s[1]): s[2] for s in event["chances"]}
            sampled = (event["sampled"][0], event["sampled"][1])
            assert sampled in weights
            assert event["probability"] == pytest.approx(weights[sampled])


def test_ply_cap_is_respected() -> None:
    """``max_plies`` must truncate the game, not be ignored."""
    record = play(
        DeterministicToyEngine(
            seed=3, level=0, allow_observe=False, max_plies=200
        ),
        {0: RandomAgent(3), 1: RandomAgent(4)},
        3,
        condition="capped",
        max_plies=4,
    )
    assert record.length <= 4
    assert len(record.turns) == record.length


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------


def test_write_and_read_jsonl_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "log.jsonl"
    records = [_play(seed, level=0, allow_observe=False) for seed in range(3)]
    assert write_jsonl(output, records) == 3

    decoded = read_jsonl(output)
    assert len(decoded) == 3
    assert [entry["seed"] for entry in decoded] == [0, 1, 2]
    assert [entry["condition"] for entry in decoded] == ["unit"] * 3
    assert [entry["length"] for entry in decoded] == [
        record.length for record in records
    ]


def test_append_jsonl_accumulates(tmp_path: Path) -> None:
    output = tmp_path / "log.jsonl"
    for seed in range(4):
        append_jsonl(output, _play(seed, level=0, allow_observe=False))
    assert len(read_jsonl(output)) == 4


def test_read_jsonl_on_missing_file_is_empty(tmp_path: Path) -> None:
    """Scripts must run before any batch exists."""
    assert read_jsonl(tmp_path / "nothing.jsonl") == []


def test_read_jsonl_reports_a_malformed_line(tmp_path: Path) -> None:
    """A corrupted line must raise with its location, not be silently dropped."""
    output = tmp_path / "log.jsonl"
    output.write_text('{"a":1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError) as info:
        read_jsonl(output)
    assert ":2" in str(info.value)


def test_overwrite_replaces_and_append_extends(tmp_path: Path) -> None:
    """``overwrite`` must not leave stale records from an earlier, longer batch."""
    output = tmp_path / "log.jsonl"
    seeds = tuple(range(5))
    factory = lambda seed: DeterministicToyEngine(  # noqa: E731
        seed=seed, level=0, allow_observe=False, max_plies=120
    )

    run_condition(factory, ("random", "random"), seeds, condition="c", output=output)
    assert len(read_jsonl(output)) == 5

    run_condition(
        factory, ("random", "random"), seeds[:2], condition="c", output=output
    )
    assert len(read_jsonl(output)) == 2

    run_condition(
        factory,
        ("random", "random"),
        seeds[:2],
        condition="c",
        output=output,
        overwrite=False,
    )
    assert len(read_jsonl(output)) == 2


# ---------------------------------------------------------------------------
# Harness robustness
# ---------------------------------------------------------------------------


def test_play_requires_both_agents() -> None:
    engine = DeterministicToyEngine(seed=0)
    with pytest.raises(KeyError):
        play(engine, {0: RandomAgent(0)}, 0, condition="broken")


def test_run_condition_requires_two_agents() -> None:
    """A one-sided condition is a configuration error, not a silent default."""
    with pytest.raises(ValueError):
        run_condition(
            lambda seed: DeterministicToyEngine(seed=seed),
            ("random",),
            (0,),
            condition="broken",
        )


def test_run_condition_writes_nothing_when_output_is_none(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    run_condition(
        lambda seed: DeterministicToyEngine(seed=seed, max_plies=40),
        ("random", "random"),
        (0, 1),
        condition="nowhere",
    )
    assert set(tmp_path.iterdir()) == before


def test_play_rejects_an_illegal_agent_action() -> None:
    """An agent returning an illegal action must fail loudly, not corrupt the log."""

    class Cheater:
        name = "cheater"

        def decide(self, state, legal):
            return legal[0].__class__(
                piece_id=legal[0].piece_id, origin=(0, 0), target=(3, 3)
            )

    engine = DeterministicToyEngine(seed=0, level=0, max_plies=20)
    with pytest.raises(ValueError, match="illegal"):
        play(engine, {0: Cheater(), 1: RandomAgent(0)}, 0, condition="cheat")


def test_engine_never_reports_a_stuck_position_as_playable() -> None:
    """``is_terminal`` and ``legal_actions`` must never contradict each other.

    This is a regression guard: an earlier version treated a truthy-but-empty generator
    as "has moves", which made the runner fail on a stuck board.
    """
    for seed in range(12):
        engine = DeterministicToyEngine(
            seed=seed, level=2, allow_observe=True, max_plies=200
        )
        state = engine.initial_state()
        agents = {0: RandomAgent(seed), 1: RandomAgent(seed + 500)}
        for _ in range(200):
            if engine.is_terminal(state):
                assert engine.legal_actions(state) == ()
                break
            legal = engine.legal_actions(state)
            assert legal, f"seed {seed}: non-terminal with no legal action"
            state = engine.apply(state, agents[state.turn].decide(state, legal)).state
        else:  # pragma: no cover - only on a hang
            pytest.fail(f"seed {seed}: game never terminated")


@pytest.mark.parametrize(
    ("kind", "expected_name"),
    [
        ("random", "random"),
        ("mcts", "mcts-baseline"),
        ("observe", "observe-agent"),
        ("prob", "prob-aware"),
        ("hard", "prob-aware-hard"),
    ],
)
def test_make_agent_builds_each_kind(kind: str, expected_name: str) -> None:
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    agent = make_agent(kind, engine, 5)
    assert agent.name == expected_name


def test_make_agent_rejects_unknown_kind() -> None:
    """A typo must raise rather than silently becoming the random baseline."""
    engine = DeterministicToyEngine(seed=0)
    with pytest.raises(ValueError, match="unknown agent kind"):
        make_agent("magik", engine, 0)


def test_every_agent_label_maps_back_to_its_kind() -> None:
    """Label -> kind must be the exact inverse of the default names ``make_agent`` sets.

    A log records agent *labels*, so regenerating a game from its own record depends on
    this table. A rename that only touches one side would silently make verification
    impossible, hence the round-trip here.
    """
    engine = DeterministicToyEngine(seed=0, level=2, allow_observe=True)
    for kind, expected_name in (
        ("random", "random"),
        ("mcts", "mcts-baseline"),
        ("observe", "observe-agent"),
        ("prob", "prob-aware"),
        ("hard", "prob-aware-hard"),
    ):
        label = make_agent(kind, engine, 0).name
        assert label == expected_name, "a default name moved; update the table too"
        assert kind_for_label(label) == kind


def test_kind_for_label_rejects_an_unknown_label() -> None:
    """An unverifiable log must raise, not quietly replay as something else."""
    with pytest.raises(ValueError, match="unknown agent label"):
        kind_for_label("definitely-not-an-agent")


def test_log_lines_are_valid_single_line_json(tmp_path: Path) -> None:
    """Every written line must parse independently -- no pretty-printing, no newlines."""
    output = tmp_path / "log.jsonl"
    records = [_play(seed) for seed in range(3)]
    for record in records:
        line = record.to_line()
        assert "\n" not in line
        json.loads(line)

    write_jsonl(output, records)
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.count("\n") == 3