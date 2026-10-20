import math

import pytest

from qcheckers.engine.paper import (
    BranchLimitError,
    PaperCaptureAction,
    PaperMergeAction,
    PaperMoveAction,
    PaperObserveAction,
    PaperQuantumEngine,
    PaperRuleError,
    PaperSplitAction,
)


def config(*entries):
    """Canonical basis configuration: (piece id, square-or-None, crowned)."""
    return tuple(sorted(entries))


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_move_into_another_piece_superposition_is_illegal_without_measurement(level):
    engine = PaperQuantumEngine(board_size=8, level=level)
    state = engine.state_from_amplitudes(
        {
            config(("A", (5, 4), False), ("B", (6, 3), False),
                   ("C", (7, 2), False), ("D", (7, 6), False)): 1 / math.sqrt(2),
            config(("A", (5, 4), False), ("B", (6, 5), False),
                   ("C", (7, 2), False), ("D", (7, 6), False)): 1 / math.sqrt(2),
        }, owners={"A": 1, "B": 0, "C": 1, "D": 1}, turn=1,
    )
    blocked = PaperMoveAction("A", (5, 4), (6, 5))
    assert blocked not in engine.legal_actions(state)
    with pytest.raises(PaperRuleError, match="illegal move"):
        engine.apply(state, blocked)
    assert state.piece("B").chance_at((6, 5)) == pytest.approx(0.5)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_split_targets_must_be_clear_of_other_piece_superpositions(level):
    engine = PaperQuantumEngine(board_size=8, level=level)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 2), False), ("B", (2, 3), False)): 1 / math.sqrt(2),
            config(("A", (3, 2), False), ("B", (0, 7), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 0}, turn=0,
    )
    blocked = PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))
    assert blocked not in engine.legal_actions(state)
    with pytest.raises(PaperRuleError, match="illegal spread"):
        engine.apply(state, blocked)


def test_split_part_move_to_clear_destination_preserves_other_part_without_measurement():
    engine = PaperQuantumEngine(board_size=8, level=1)
    state = engine.state_from_amplitudes(
        {
            config(("A", (6, 3), False)): 1 / math.sqrt(2),
            config(("A", (6, 5), False)): 1 / math.sqrt(2),
        }, owners={"A": 0}, turn=0,
    )
    step = engine.apply(state, PaperMoveAction("A", (6, 3), (5, 2)))
    assert step.events == ()
    assert step.state.piece("A").chance_at((5, 2)) == pytest.approx(0.5)
    assert step.state.piece("A").chance_at((6, 5)) == pytest.approx(0.5)


@pytest.mark.parametrize("level", [3, 4])
def test_merge_destination_cannot_overlap_another_piece_possible_position(level):
    engine = PaperQuantumEngine(board_size=8, level=level)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 2), False), ("B", (2, 3), False)): 1 / math.sqrt(2),
            config(("A", (3, 4), False), ("B", (0, 7), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 0}, turn=0,
    )
    blocked = PaperMergeAction("A", (3, 2), (3, 4), (2, 3))
    assert blocked not in engine.legal_actions(state)
    with pytest.raises(PaperRuleError, match="illegal merge"):
        engine.apply(state, blocked)


def test_standard_opening_has_twelve_pieces_per_side_on_eight_by_eight():
    engine = PaperQuantumEngine(board_size=8, level=0)
    state = engine.initial_state()

    assert len(state.pieces_of(0)) == len(state.pieces_of(1)) == 12
    assert {square[0] for p in state.pieces_of(0) for square, _ in p.sites} == {5, 6, 7}
    assert {square[0] for p in state.pieces_of(1) for square, _ in p.sites} == {0, 1, 2}


def test_split_has_two_half_probability_destinations_and_no_source_occupancy():
    engine = PaperQuantumEngine(board_size=4, level=1)
    state = engine.state_from_amplitudes(
        {config(("A", (3, 2), False)): 1}, owners={"A": 0}, turn=0
    )
    action = PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))

    stepped = engine.apply(state, action).state
    piece = stepped.piece("A")

    assert piece.chance_at((2, 1)) == pytest.approx(0.5)
    assert piece.chance_at((2, 3)) == pytest.approx(0.5)
    assert piece.chance_at((3, 2)) == 0
    amplitudes = dict(stepped.amplitudes)
    assert amplitudes[config(("A", (2, 1), False))] == pytest.approx((1 + 1j) / 2)
    assert amplitudes[config(("A", (2, 3), False))] == pytest.approx((1 - 1j) / 2)


def test_split_part_can_move_and_split_again():
    engine = PaperQuantumEngine(board_size=6, level=1)
    state = engine.state_from_amplitudes(
        {config(("A", (3, 2), False)): 1}, owners={"A": 0}, turn=0
    )
    split = engine.apply(
        state, PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))
    ).state

    split = split.clone(turn=0)
    assert PaperMoveAction("A", (2, 1), (1, 0)) in engine.legal_actions(split)
    resplit = PaperSplitAction("A", (2, 1), ((1, 0), (1, 2)))
    assert resplit in engine.legal_actions(split)
    result = engine.apply(split, resplit).state
    assert math.isclose(sum(abs(a) ** 2 for _, a in result.amplitudes), 1.0)


def test_capture_is_mandatory_and_kings_can_move_and_capture_backward():
    engine = PaperQuantumEngine(board_size=6, level=0)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 2), True), ("B", (4, 3), False), ("C", None, False)): 1 / math.sqrt(2),
            config(("A", (3, 2), True), ("B", None, False), ("C", (2, 1), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0, "B": 1, "C": 1},
        turn=0,
    )

    actions = engine.legal_actions(state)
    assert actions
    assert all(isinstance(action, PaperCaptureAction) for action in actions)
    assert PaperCaptureAction("A", (3, 2), (4, 3), (5, 4)) in actions


def test_multijump_keeps_same_turn_and_advances_revision_per_jump():
    engine = PaperQuantumEngine(board_size=8, level=0)
    state = engine.state_from_amplitudes(
        {config(("A", (5, 0), False), ("B", (4, 1), False), ("C", (2, 3), False)): 1},
        owners={"A": 0, "B": 1, "C": 1},
        turn=0,
    )
    first = PaperCaptureAction("A", (5, 0), (4, 1), (3, 2))

    middle = engine.apply(state, first).state

    assert middle.ply == 1
    assert middle.turn == 0
    assert middle.continuation_piece == "A"
    assert middle.quiet_moves == 0
    second = PaperCaptureAction("A", (3, 2), (2, 3), (1, 4))
    end = engine.apply(middle, second).state
    assert end.ply == 2
    assert end.turn == 1
    assert end.continuation_piece is None
    assert end.quiet_moves == 0


def test_promotion_to_king_ends_capture_chain():
    engine = PaperQuantumEngine(board_size=6, level=0)
    state = engine.state_from_amplitudes(
        {config(("A", (2, 1), False), ("B", (1, 2), False),
                ("C", (1, 4), False)): 1},
        owners={"A": 0, "B": 1, "C": 1},
        turn=0,
    )
    crown = PaperCaptureAction("A", (2, 1), (1, 2), (0, 3))

    after = engine.apply(state, crown).state

    assert after.piece("A").king_chance_at((0, 3)) == pytest.approx(1.0)
    assert after.continuation_piece is None
    assert after.turn == 1


def test_promotion_retains_old_crown_type_in_hidden_orthogonal_ancilla():
    engine = PaperQuantumEngine(board_size=6, level=0)
    state = engine.state_from_amplitudes(
        {
            config(("A", (1, 2), False)): 1 / math.sqrt(2),
            config(("A", (1, 2), True)): 1 / math.sqrt(2),
        }, owners={"A": 0}, turn=0,
    )
    action = PaperMoveAction("A", (1, 2), (0, 1))

    after = engine.apply(state, action).state

    assert len(after.amplitudes) == 2
    assert all(configuration.count(("A", (0, 1), True)) == 1
               for configuration, _ in after.amplitudes)
    ancilla_counts = [sum(piece_id.startswith("@promotion:A:") and square is None
                          for piece_id, square, _ in configuration)
                      for configuration, _ in after.amplitudes]
    assert sorted(ancilla_counts) == [0, 1]
    assert after.piece("A").king_chance_at((0, 1)) == pytest.approx(1.0)
    assert sum(abs(amplitude) ** 2 for _, amplitude in after.amplitudes) == pytest.approx(1.0)
    assert len(engine.render(after)["pieces"]) == 1


def test_capture_promotion_retains_old_type_ancilla():
    engine = PaperQuantumEngine(board_size=6, level=0)
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False), ("B", (1, 2), False)): 1 / math.sqrt(2),
            config(("A", (2, 1), True), ("B", (1, 2), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 1}, turn=0,
    )
    action = PaperCaptureAction("A", (2, 1), (1, 2), (0, 3))

    after = engine.apply(state, action).state

    assert after.piece("A").king_chance_at((0, 3)) == pytest.approx(1.0)
    assert after.piece("B").survival_probability == pytest.approx(0.0)
    assert len(after.amplitudes) == 2
    assert sum(abs(amplitude) ** 2 for _, amplitude in after.amplitudes) == pytest.approx(1.0)
    assert sorted(any(piece_id.startswith("@promotion:A:")
                      for piece_id, _, _ in configuration)
                  for configuration, _ in after.amplitudes) == [False, True]


def test_level_two_capture_creates_correlated_branches_without_measurement():
    engine = PaperQuantumEngine(board_size=4, level=2)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 0), False), ("B", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (3, 0), False), ("B", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0, "B": 1},
        turn=0,
    )
    action = PaperCaptureAction("A", (3, 0), (2, 1), (1, 2))

    step = engine.apply(state, action)
    amplitudes = dict(step.state.amplitudes)

    assert len(step.events) == 0
    assert amplitudes[config(("A", (1, 2), False), ("B", None, False))] == pytest.approx(
        1j / math.sqrt(2)
    )
    assert amplitudes[config(("A", (3, 0), False), ("B", (2, 3), False))] == pytest.approx(
        1 / math.sqrt(2)
    )


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_capture_landing_on_another_piece_possible_position_is_illegal(level):
    engine = PaperQuantumEngine(board_size=8, level=level)
    state = engine.state_from_amplitudes(
        {
            config(("A", (5, 0), False), ("B", (4, 1), False), ("C", None, False)): 1 / math.sqrt(2),
            config(("A", (5, 0), False), ("B", (4, 1), False), ("C", (3, 2), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0, "B": 1, "C": 0}, turn=0,
    )
    action = PaperCaptureAction("A", (5, 0), (4, 1), (3, 2))

    legal = engine.legal_actions(state)
    assert action not in legal
    # An invalid capture must not force a pass or suppress other pieces' moves.
    assert PaperMoveAction("C", (3, 2), (2, 1)) in legal
    with pytest.raises(PaperRuleError, match="illegal capture"):
        engine.apply(state, action)


def test_backward_split_and_move_do_not_leak_into_uncrowned_component():
    engine = PaperQuantumEngine(board_size=6, level=1)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 2), False)): 1 / math.sqrt(2),
            config(("A", (3, 2), True)): 1 / math.sqrt(2),
        }, owners={"A": 0}, turn=0,
    )
    split = PaperSplitAction("A", (3, 2), ((4, 1), (4, 3)))
    move = PaperMoveAction("A", (3, 2), (4, 3))

    assert split in engine.legal_actions(state)
    split_after = dict(engine.apply(state, split).state.amplitudes)
    assert split_after[config(("A", (3, 2), False))] == pytest.approx(1 / math.sqrt(2))
    assert sum(abs(value) ** 2 for conf, value in split_after.items()
               if conf == config(("A", (4, 1), True)) or conf == config(("A", (4, 3), True))) == pytest.approx(0.5)

    move_after = dict(engine.apply(state, move).state.amplitudes)
    assert move_after[config(("A", (3, 2), False))] == pytest.approx(1 / math.sqrt(2))
    assert sum(abs(value) ** 2 for conf, value in move_after.items()
               if conf == config(("A", (4, 3), True))) == pytest.approx(0.5)


def test_man_only_backward_split_and_merge_are_not_offered():
    split_engine = PaperQuantumEngine(board_size=6, level=1)
    single_man = split_engine.state_from_amplitudes(
        {config(("A", (3, 2), False)): 1}, owners={"A": 0}, turn=0
    )
    backward_split = PaperSplitAction("A", (3, 2), ((4, 1), (4, 3)))
    assert backward_split not in split_engine.legal_actions(single_man)
    with pytest.raises(PaperRuleError, match="illegal spread"):
        split_engine.apply(single_man, backward_split)

    merge_engine = PaperQuantumEngine(board_size=6, level=3)
    split_man = merge_engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), False)): 1 / math.sqrt(2),
        }, owners={"A": 0}, turn=0,
    )
    backward_merge = PaperMergeAction("A", (2, 1), (2, 3), (3, 2))
    assert backward_merge not in merge_engine.legal_actions(split_man)
    with pytest.raises(PaperRuleError, match="illegal merge"):
        merge_engine.apply(split_man, backward_merge)


def test_level_four_observe_cannot_bypass_mandatory_capture():
    engine = PaperQuantumEngine(board_size=6, level=4)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 0), False), ("B", (2, 1), False), ("C", (3, 4), False)): 1 / math.sqrt(2),
            config(("A", (3, 0), False), ("B", (2, 1), False), ("C", (2, 5), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 1, "C": 0}, turn=0,
    )

    actions = engine.legal_actions(state)
    assert actions
    assert all(isinstance(action, PaperCaptureAction) for action in actions)
    assert not any(isinstance(action, PaperObserveAction) for action in actions)


def test_level_two_split_attacker_uses_ordered_measurements_not_entanglement():
    selected = {(3, 0), (2, 1)}

    def sample(sites):
        return next((square, probability) for square, probability in sites
                    if square in selected)

    engine = PaperQuantumEngine(board_size=4, level=2, sampler=sample)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 0), False), ("B", (2, 1), False)): 0.5,
            config(("A", (3, 0), False), ("B", (2, 3), False)): 0.5,
            config(("A", (3, 2), False), ("B", (2, 1), False)): 0.5,
            config(("A", (3, 2), False), ("B", (2, 3), False)): 0.5,
        },
        owners={"A": 0, "B": 1},
        turn=0,
    )
    action = PaperCaptureAction("A", (3, 0), (2, 1), (1, 2))

    step = engine.apply(state, action)

    assert [event.piece_id for event in step.events] == ["A", "B"]
    assert step.state.piece("A").chance_at((1, 2)) == pytest.approx(1.0)
    assert step.state.piece("B").survival_probability == pytest.approx(0.0)


def test_measurement_projects_one_piece_and_preserves_unmeasured_entanglement():
    engine = PaperQuantumEngine(board_size=4, level=4, sampler=lambda sites: ((-1, -1), 0.5))
    state = engine.state_from_amplitudes(
        {
            config(("A", (1, 2), False), ("B", None, False)): 1 / math.sqrt(2),
            config(("A", (3, 0), False), ("B", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0, "B": 1},
        turn=1,
    )
    measured = engine.measure_piece(state, "B")

    assert measured.state.piece("A").chance_at((1, 2)) == pytest.approx(1.0)
    assert measured.state.piece("B").sites == ()
    assert not measured.state.piece("B").is_spread
    assert measured.events[0].sampled == (-1, -1)
    assert {piece["piece_id"] for piece in engine.render(measured.state)["pieces"]} == {"A"}


def test_sampler_reported_probability_is_not_trusted():
    engine = PaperQuantumEngine(board_size=4, level=4, sampler=lambda sites: (sites[0][0], 0.999))
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), False)): 1 / math.sqrt(2),
        }, owners={"A": 0}, turn=0,
    )

    measured = engine.measure_piece(state, "A")

    assert measured.events[0].probability == pytest.approx(0.5)
    assert sum(abs(amplitude) ** 2 for _, amplitude in measured.state.amplitudes) == pytest.approx(1.0)


def test_level_one_measures_attacker_first_and_failed_jumper_passes():
    seen = []

    def sample(sites):
        seen.append(sites)
        return ((3, 2), 0.5)

    engine = PaperQuantumEngine(board_size=4, level=1, sampler=sample)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 0), False), ("B", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (3, 2), False), ("B", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0, "B": 1},
        turn=0,
    )
    action = PaperCaptureAction("A", (3, 0), (2, 1), (1, 2))

    step = engine.apply(state, action)

    assert len(seen) == 1  # Defender is not measured after the jumper misses.
    assert step.events[0].piece_id == "A"
    assert step.events[0].sampled == (3, 2)
    assert step.state.turn == 1
    assert step.state.piece("A").chance_at((3, 2)) == pytest.approx(1.0)
    assert step.state.piece("B").chance_at((2, 3)) == pytest.approx(1.0)


def test_failed_apply_restores_internal_rng_after_measurement(monkeypatch):
    engine = PaperQuantumEngine(board_size=4, level=1, seed=29)
    state = engine.state_from_amplitudes(
        {
            config(("A", (3, 0), False), ("B", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (3, 2), False), ("B", (2, 1), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 1}, turn=0,
    )
    action = PaperCaptureAction("A", (3, 0), (2, 1), (1, 2))
    original_projection = engine._project_piece

    def project_then_fail(branches, current_state, piece_id, cause):
        original_projection(branches, current_state, piece_id, cause)
        raise PaperRuleError("simulated later operation failure")

    monkeypatch.setattr(engine, "_project_piece", project_then_fail)
    before_rng = engine._rng.getstate()

    with pytest.raises(PaperRuleError, match="simulated later"):
        engine.apply(state, action)

    assert engine._rng.getstate() == before_rng
    assert state.piece("A").survival_probability == pytest.approx(1.0)


def test_voluntary_measurement_requires_the_room_rule():
    engine = PaperQuantumEngine(board_size=4, level=2)
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0},
        turn=0,
    )

    assert engine.allow_observe is False
    with pytest.raises(PaperRuleError, match="not enabled"):
        engine.measure_piece(state, "A")


def test_default_level_two_has_observe_disabled():
    assert PaperQuantumEngine(level=2).allow_observe is False


@pytest.mark.parametrize("level", [1, 2])
def test_observe_opt_in_offers_action_after_split(level):
    engine = PaperQuantumEngine(board_size=4, level=level, allow_observe=True)
    state = engine.state_from_amplitudes(
        {config(("A", (3, 2), False)): 1}, owners={"A": 0}, turn=0
    )
    split = engine.apply(
        state, PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))
    ).state.clone(turn=0)

    assert PaperObserveAction("A", (2, 1)) in engine.legal_actions(split)


def test_level_four_default_enables_observe():
    engine = PaperQuantumEngine(board_size=4, level=4)
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0},
        turn=0,
    )

    assert engine.allow_observe is True
    assert PaperObserveAction("A", (2, 1)) in engine.legal_actions(state)


def test_level_four_can_disable_observe():
    engine = PaperQuantumEngine(board_size=4, level=4, allow_observe=False)
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), False)): 1 / math.sqrt(2),
        },
        owners={"A": 0},
        turn=0,
    )

    assert not any(isinstance(action, PaperObserveAction) for action in engine.legal_actions(state))


def test_clone_preserves_explicit_allow_observe():
    engine = PaperQuantumEngine(seed=1, board_size=4, level=2, allow_observe=True)

    clone = engine.clone()

    assert clone.allow_observe is True


def test_level_four_decoherence_projects_only_the_expired_piece():
    engine = PaperQuantumEngine(
        board_size=6,
        level=4,
        decoherence_ticks=1,
        sampler=lambda sites: (sites[0][0], sites[0][1]),
    )
    state = engine.state_from_amplitudes(
        {config(("A", (3, 2), False), ("B", (0, 1), False)): 1},
        owners={"A": 0, "B": 1},
        turn=0,
    )
    split = engine.apply(
        state, PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))
    ).state
    assert split.coherence == (("A", 1),)
    opponent_move = PaperMoveAction("B", (0, 1), (1, 0))

    after = engine.apply(split, opponent_move)

    assert after.events[-1].cause == "decoherence"
    assert after.state.piece("A").survival_probability == pytest.approx(1.0)
    assert len(after.state.piece("A").sites) == 1


def test_level_three_merge_has_constructive_and_destructive_interference():
    engine = PaperQuantumEngine(board_size=6, level=3)
    action = PaperMergeAction("A", (2, 1), (2, 3), (1, 2))
    constructive = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): (1 + 1j) / 2,
            config(("A", (2, 3), False)): (1 - 1j) / 2,
        },
        owners={"A": 0},
        turn=0,
    )
    destructive = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False)): (1 + 1j) / 2,
            config(("A", (2, 3), False)): -(1 - 1j) / 2,
        },
        owners={"A": 0},
        turn=0,
    )

    merged = engine.apply(constructive, action).state
    cancelled = engine.apply(destructive, action).state

    assert merged.piece("A").chance_at((1, 2)) == pytest.approx(1.0)
    assert cancelled.piece("A").chance_at((1, 2)) == pytest.approx(0.0)
    assert sum(abs(a) ** 2 for _, a in cancelled.amplitudes) == pytest.approx(1.0)


def test_merge_is_not_offered_between_man_and_king_modes():
    engine = PaperQuantumEngine(board_size=6, level=3)
    state = engine.state_from_amplitudes(
        {
            config(("A", (2, 1), False), ("B", (5, 0), False)): 1 / math.sqrt(2),
            config(("A", (2, 3), True), ("B", (5, 0), False)): 1 / math.sqrt(2),
        }, owners={"A": 0, "B": 1}, turn=0,
    )
    mixed_type_merge = PaperMergeAction("A", (2, 1), (2, 3), (1, 2))

    assert mixed_type_merge not in engine.legal_actions(state)
    with pytest.raises(PaperRuleError, match="illegal merge"):
        engine.apply(state, mixed_type_merge)
    # Mixed crown flags still support valid branch-controlled movement and split.
    assert PaperMoveAction("A", (2, 3), (1, 2)) in engine.legal_actions(state)
    assert PaperSplitAction("A", (2, 3), ((1, 2), (3, 2))) in engine.legal_actions(state)


def test_quiet_move_draws_after_more_than_forty_captureless_turns():
    engine = PaperQuantumEngine(board_size=4, level=0)
    state = engine.state_from_amplitudes(
        {config(("A", (3, 0), False), ("B", (0, 3), False)): 1},
        owners={"A": 0, "B": 1},
        turn=0,
        quiet_moves=40,
    )
    move = PaperMoveAction("A", (3, 0), (2, 1))

    after = engine.apply(state, move).state
    assert engine.outcome(after).reason == "forty_move_draw"
    assert engine.outcome(after).winner is None


def test_clone_preserves_configuration_but_drops_hardware_sampler():
    engine = PaperQuantumEngine(seed=9, board_size=6, level=2, sampler=lambda sites: sites[0])
    clone = engine.clone(17)

    assert clone.seed == 17
    assert clone.level == 2
    assert clone.sampler is None
    assert clone.initial_state() == engine.initial_state()


def test_branch_cap_refuses_exponential_growth_without_mutating_input():
    engine = PaperQuantumEngine(board_size=6, level=1, max_branches=1)
    state = engine.state_from_amplitudes(
        {config(("A", (3, 2), False)): 1}, owners={"A": 0}, turn=0
    )
    action = PaperSplitAction("A", (3, 2), ((2, 1), (2, 3)))

    with pytest.raises(BranchLimitError):
        engine.apply(state, action)
    assert state.piece("A").sites == (((3, 2), 1.0),)

