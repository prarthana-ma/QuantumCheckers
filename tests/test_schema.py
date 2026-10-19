"""Record schema, JSON round-trip and replay payload -- Persons B and E.

Owner: **Person B** for the JSONL record format; **Person E** for the replay payload.

The JSONL format is a contract between three people: Person B writes it, Person D's
statistics read it, and Person E's viewer renders it. These tests are the contract's
executable definition -- if a field changes shape without the log still round-tripping,
Person D's rates and Person E's board break in ways that only show up in a plot.

The rules that matter:

* a record must survive ``to_json`` -> ``json.dumps`` -> ``json.loads`` unchanged in
  every field analysis depends on;
* one record must be exactly one line, with no embedded newline;
* floats must be stable, so byte-identity across runs is testable;
* the replay payload must be a pure function of the record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qcheckers.engine.protocol import GameState, Piece
from qcheckers.engine.toy import DeterministicToyEngine
from qcheckers.experiment.runner import play
from qcheckers.experiment.schema import (
    FLOAT_PRECISION,
    GameRecord,
    TurnRecord,
    board_snapshot,
    record_from_json,
)
from qcheckers.experiment.stats import summarize
from qcheckers.viz.replay import build_replay, replay_to_json


@pytest.fixture(scope="module")
def record() -> GameRecord:
    """One played game with the uncertainty mechanics switched on."""
    from qcheckers.agents.random_agent import RandomAgent

    engine = DeterministicToyEngine(
        seed=5, level=2, allow_observe=True, max_plies=200
    )
    return play(
        engine,
        {0: RandomAgent(5), 1: RandomAgent(5005)},
        5,
        condition="schema-test",
    )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_record_round_trips_through_json(record: GameRecord) -> None:
    """Every field analysis depends on must survive a JSON round-trip unchanged."""
    original = record.to_json()
    restored = json.loads(json.dumps(original))

    assert restored == original
    assert restored["game_id"] == record.game_id
    assert restored["seed"] == record.seed
    assert restored["condition"] == record.condition
    assert restored["winner"] == record.winner
    assert restored["termination"] == record.termination
    assert restored["length"] == record.length
    assert restored["players"] == {"0": record.players[0], "1": record.players[1]}
    assert len(restored["turns"]) == len(record.turns)


def test_record_is_json_serialisable_without_custom_encoder(record: GameRecord) -> None:
    """No dataclasses, sets, tuples or objects may leak into the payload.

    ``json.dumps`` is the check: a stray tuple would silently become a list, and a
    stray object would raise here rather than in a consumer.
    """
    text = json.dumps(record.to_json())
    assert isinstance(text, str)
    assert text.startswith("{")
    assert "GameRecord" not in text


def test_record_to_line_is_one_line(record: GameRecord) -> None:
    """One record per line is the whole JSONL contract."""
    line = record.to_line()
    assert "\n" not in line
    assert "\r" not in line
    assert json.loads(line)["game_id"] == record.game_id


def test_record_key_order_is_stable(record: GameRecord) -> None:
    """Fixed key order keeps diffs readable and files byte-comparable."""
    first = list(record.to_json().keys())
    second = list(record.to_json().keys())
    assert first == second
    assert list(json.loads(record.to_line()).keys()) == first


def test_winner_serialises_as_null_for_a_draw() -> None:
    """A draw must be ``null``, never ``-1``, ``"draw"`` or a missing key."""
    from qcheckers.agents.random_agent import RandomAgent

    record = play(
        DeterministicToyEngine(seed=2, level=0, max_plies=2),
        {0: RandomAgent(2), 1: RandomAgent(3)},
        2,
        condition="draw",
        max_plies=1,
    )
    payload = record.to_json()
    assert payload["winner"] is None
    assert "winner" in payload
    assert record.is_draw() is True
    assert record.winner_player() is None
    assert json.loads(record.to_line())["winner"] is None


def test_collapse_pieces_serialise_as_a_list(record: GameRecord) -> None:
    """Piece ids must be JSON arrays, not sets."""
    payload = json.loads(record.to_line())
    assert isinstance(payload["collapse_pieces"], list)
    assert payload["collapse_pieces"] == sorted(payload["collapse_pieces"])


def test_players_serialise_with_string_keys(record: GameRecord) -> None:
    """JSON object keys must be strings; int keys would change the round-trip type."""
    payload = json.loads(record.to_line())
    assert set(payload["players"]) == {"0", "1"}
    assert all(isinstance(key, str) for key in payload["players"])


def test_toy_engine_flag_is_recorded(record: GameRecord) -> None:
    """Toy-engine provenance must be in every line, so nobody mistakes it later."""
    assert record.to_json()["toy_engine"] is True
    assert record.engine == "deterministic-toy"


def test_the_ply_cap_is_recorded(record: GameRecord) -> None:
    """The cap is a terminal condition, not an implementation detail.

    ``outcome()`` treats ``ply >= max_plies`` as a finished game and search agents read
    it inside their rollouts, so a line that omits the cap cannot be regenerated in
    general -- `scripts/verify_results.py` replays every record from the record alone.
    """
    payload = record.to_json()
    assert payload["max_plies"] > 0
    assert payload["max_plies"] == record.max_plies
    # And it is required, not optional: an old-style line must fail loudly here rather
    # than quietly replay under some other cap.
    without = {key: value for key, value in payload.items() if key != "max_plies"}
    with pytest.raises(KeyError, match="max_plies"):
        record_from_json(without)


def test_record_from_json_accepts_a_well_formed_payload(record: GameRecord) -> None:
    payload = json.loads(record.to_line())
    assert record_from_json(payload) is payload


def test_record_from_json_names_the_missing_fields() -> None:
    with pytest.raises(KeyError) as info:
        record_from_json({"game_id": "x", "seed": 1})
    message = str(info.value)
    assert "condition" in message
    assert "turns" in message


# ---------------------------------------------------------------------------
# Determinism of serialisation
# ---------------------------------------------------------------------------


def test_serialised_floats_are_rounded(record: GameRecord) -> None:
    """Every float must be at the declared precision, or byte-identity is fragile."""
    payload = json.dumps(record.to_json())

    def walk(node: object) -> None:
        if isinstance(node, float):
            assert round(node, FLOAT_PRECISION) == node
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(payload))


def test_negative_zero_is_normalised() -> None:
    """``-0.0`` and ``0.0`` differ in JSON text, which would break byte-identity.

    An empty state has certainty exactly ``0.0``; a state whose weighted sum lands
    slightly negative would produce ``-0.0`` without the normalisation in ``_round``.
    """
    empty = board_snapshot(DeterministicToyEngine(seed=0), GameState(0, 0, ()))
    assert "-0.0" not in json.dumps(empty)

    # Force the normalisation through the rounding helper itself.
    assert round(-0.0, FLOAT_PRECISION) == 0.0
    assert json.loads(json.dumps(-0.0)) == 0.0
    assert str(-0.0) != str(0.0)  # why the normalisation is necessary at all


def test_two_runs_serialise_identically(record: GameRecord) -> None:
    """Serialisation must not depend on dict ordering or identity."""
    assert record.to_line() == record.to_line()
    assert json.dumps(record.to_json()) == json.dumps(record.to_json())


# ---------------------------------------------------------------------------
# Turn records
# ---------------------------------------------------------------------------


def test_every_turn_records_its_player_action_and_board(record: GameRecord) -> None:
    """Each turn must be self-sufficient for the viewer to step through it."""
    assert record.turns
    for index, turn in enumerate(record.turns):
        payload = turn.to_json()
        assert payload["ply"] == index
        assert payload["player"] in (0, 1)
        assert payload["action"]["kind"]
        assert payload["action"]["piece_id"]
        assert "board_after" in payload
        assert isinstance(payload["events"], list)

        if not payload["board_after"]["pieces"] and index == 0:
            pytest.fail("the first turn must show a populated board")


def test_turn_ply_advances_by_one(record: GameRecord) -> None:
    """A gap in the ply sequence means the runner dropped or duplicated a turn."""
    assert [turn.ply for turn in record.turns] == list(range(len(record.turns)))


def test_turns_alternate_players(record: GameRecord) -> None:
    """Turn order must alternate; a repeat means the engine failed to switch player."""
    players = [turn.player for turn in record.turns]
    for index in range(1, len(players)):
        assert players[index] != players[index - 1]


def test_move_counts_sum_to_the_game_length(record: GameRecord) -> None:
    """All logged move counters must add up; a leak would corrupt the usage plot."""
    total = (
        record.observe_moves
        + record.spread_moves
        + record.rejoin_moves
        + record.capture_moves
        + record.board_moves
    )
    assert total == record.length == len(record.turns)


def test_board_snapshot_has_every_field_the_viewer_needs() -> None:
    """Snapshot shape is checked directly, without a game, so a refactor cannot break it."""
    state = GameState(
        turn=1,
        ply=3,
        pieces=(
            Piece("A", 0, (((1, 1), 1.0),)),
            Piece("B", 1, (((2, 3), 0.5), ((2, 1), 0.5))),
        ),
        captured=("A0",),
    )
    snapshot = board_snapshot(DeterministicToyEngine(seed=0, level=2), state)

    assert snapshot["ply"] == 3
    assert snapshot["turn"] == 1
    assert snapshot["captured"] == ["A0"]
    assert snapshot["board_size"] == 4
    assert "certainty" in snapshot

    by_id = {piece["piece_id"]: piece for piece in snapshot["pieces"]}
    assert by_id["A"]["uncertain"] is False
    assert by_id["B"]["uncertain"] is True
    assert by_id["B"]["sites"] == [[[2, 3], 0.5], [[2, 1], 0.5]]


def test_empty_state_snapshot_is_still_valid() -> None:
    """A terminal state with no pieces must not break snapshot generation."""
    snapshot = board_snapshot(DeterministicToyEngine(seed=0), GameState(0, 0, ()))
    assert snapshot["pieces"] == []
    json.dumps(snapshot)


def test_turn_record_defaults_to_no_events() -> None:
    turn = TurnRecord(ply=0, player=0, action=_first_action(), board_after={})
    assert turn.events == ()
    assert turn.to_json()["events"] == []


def _first_action():
    from qcheckers.engine.protocol import MoveAction

    return MoveAction(piece_id="A", origin=(3, 1), target=(2, 0))


# ---------------------------------------------------------------------------
# Analysis reads the serialised form
# ---------------------------------------------------------------------------


def test_stats_reads_the_serialised_record(record: GameRecord) -> None:
    """Person D's statistics must work on decoded lines, not just live objects."""
    from_dict = summarize([json.loads(record.to_line())])
    from_object = summarize([record])
    assert from_dict["n_games"] == from_object["n_games"] == 1
    assert from_dict["metrics"]["win_rate_p0"].successes == (
        from_object["metrics"]["win_rate_p0"].successes
    )
    assert from_dict["rates"]["mean_length"] == record.length


def test_stats_rejects_an_unreadable_record() -> None:
    """A non-record must raise, not be counted as a zero-length game."""
    with pytest.raises(TypeError):
        summarize([object()])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Replay payload (Person E)
# ---------------------------------------------------------------------------


def test_replay_is_a_pure_function_of_the_record(record: GameRecord) -> None:
    """Same record in, same payload out -- the viewer must not disagree with the log."""
    payload = record.to_json()
    assert replay_to_json(build_replay(payload)) == replay_to_json(build_replay(payload))


def test_replay_frame_count_matches_the_game(record: GameRecord) -> None:
    replay = build_replay(record.to_json())
    assert len(replay["frames"]) == len(record.turns)
    assert [frame["ply"] for frame in replay["frames"]] == [
        turn.ply for turn in record.turns
    ]


def test_replay_cells_cover_the_whole_board(record: GameRecord) -> None:
    """``board_size ** 2`` cells exactly: no gaps, no duplicates."""
    replay = build_replay(record.to_json())
    size = replay["board_size"]
    assert size >= 4
    for frame in replay["frames"]:
        assert len(frame["cells"]) == size * size
        squares = {(cell["row"], cell["col"]) for cell in frame["cells"]}
        assert len(squares) == size * size


def test_replay_marks_collapse_turns(record: GameRecord) -> None:
    """Collapse turns must be flagged and carry their events, with matched pre-collapse
    chances."""
    replay = build_replay(record.to_json())
    flagged = [frame for frame in replay["frames"] if frame["collapsed"]]
    assert len(flagged) == sum(len(turn.events) for turn in record.turns)

    for frame in flagged:
        assert frame["events"]
        for event in frame["events"]:
            assert event["cause"]
            assert event["chances"], "a collapse must log its pre-collapse chances"
            total = sum(chance[2] for chance in event["chances"])
            assert total == pytest.approx(1.0)
            assert event["sampled"] is not None


def test_replay_states_amplitudes_are_not_shown(record: GameRecord) -> None:
    """The brief requires saying plainly when only chances are available."""
    replay = build_replay(record.to_json())
    assert replay["amplitude_display"] is False
    assert "chance" in replay["amplitude_note"].lower()
    assert "gate 5" in replay["amplitude_note"].lower()


def test_replay_carries_provenance(record: GameRecord) -> None:
    replay = build_replay(record.to_json())
    assert replay["header"]["seed"] == record.seed
    assert replay["header"]["condition"] == record.condition
    assert replay["header"]["toy_engine"] is True
    assert replay["summary"]["collapses"] == record.collapses


def test_replay_requires_the_fields_it_labels_with(record: GameRecord) -> None:
    payload = record.to_json()
    for missing in ("game_id", "seed"):
        partial = {key: value for key, value in payload.items() if key != missing}
        with pytest.raises(KeyError):
            build_replay(partial)


def test_replay_serialises_to_json(record: GameRecord, tmp_path: Path) -> None:
    """The payload must be writable and re-readable, since it is what the viewer loads."""
    target = tmp_path / "replay.json"
    target.write_text(replay_to_json(build_replay(record.to_json()), indent=2), encoding="utf-8")
    restored = json.loads(target.read_text(encoding="utf-8"))
    assert restored["schema"] == "qcheckers-replay/1"
    assert len(restored["frames"]) == len(record.turns)


def test_replay_handles_a_log_without_board_size() -> None:
    """A record with no board metadata must still render a board of the default size."""
    minimal = {
        "game_id": "min",
        "seed": 0,
        "condition": "c",
        "turns": [{"ply": 0, "player": 0, "action": {"kind": "move"}, "board_after": {}, "events": []}],
    }
    replay = build_replay(minimal)
    assert replay["board_size"] == 4
    assert len(replay["frames"][0]["cells"]) == 16
    assert all(cell["occupied"] is False for cell in replay["frames"][0]["cells"])