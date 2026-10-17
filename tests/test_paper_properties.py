"""Independent rule oracle and bounded randomized invariants for paper checkers."""

import math
import random

from qcheckers.engine.paper import (
    PaperCaptureAction,
    PaperMoveAction,
    PaperQuantumEngine,
)


def _configuration(entries):
    return tuple(sorted(entries))


def _level_zero_oracle(configuration, owners, turn, size):
    """Compute classical legal moves without using engine rule helpers."""
    occupied = {square: (piece_id, king)
                for piece_id, square, king in configuration if square is not None}
    moves = set()
    captures = set()
    for piece_id, origin, king in configuration:
        if origin is None or owners[piece_id] != turn:
            continue
        forward = -1 if turn == 0 else 1
        row_steps = (forward, -forward) if king else (forward,)
        for row_delta in row_steps:
            for col_delta in (-1, 1):
                adjacent = (origin[0] + row_delta, origin[1] + col_delta)
                landing = (origin[0] + 2 * row_delta, origin[1] + 2 * col_delta)
                if not (0 <= adjacent[0] < size and 0 <= adjacent[1] < size):
                    continue
                occupant = occupied.get(adjacent)
                if occupant is None:
                    moves.add(PaperMoveAction(piece_id, origin, adjacent))
                elif occupant[0] in owners and owners[occupant[0]] != turn:
                    if (0 <= landing[0] < size and 0 <= landing[1] < size
                            and landing not in occupied):
                        captures.add(PaperCaptureAction(piece_id, origin, adjacent, landing))
    return captures if captures else moves


def test_level_zero_legal_actions_match_independent_oracle_on_seeded_positions():
    rng = random.Random(680_251)
    checked = 0
    for size in (4, 6, 8):
        playable = [(row, col) for row in range(size) for col in range(size)
                    if (row + col) % 2 == 1]
        for _ in range(100):
            squares = rng.sample(playable, rng.randint(2, min(10, len(playable))))
            entries = []
            owners = {}
            for index, square in enumerate(squares):
                piece_id = f"P{index}"
                owners[piece_id] = index % 2
                entries.append((piece_id, square, rng.random() < 0.28))
            turn = rng.randrange(2)
            engine = PaperQuantumEngine(board_size=size, level=0)
            state = engine.state_from_amplitudes(
                {_configuration(entries): 1 + 0j}, owners=owners, turn=turn
            )

            expected = _level_zero_oracle(_configuration(entries), owners, turn, size)
            assert set(engine.legal_actions(state)) == expected, (
                f"seed=680251 size={size} sample={checked} turn={turn} "
                f"position={entries!r}"
            )
            checked += 1
    assert checked == 300


def test_split_piece_moves_and_splits_cannot_enter_its_other_branch():
    """Own branches block ordinary moves and split targets at every quantum level."""
    origin = (4, 1)
    other_branch = (3, 2)
    amplitudes = {
        _configuration([("A", origin, False)]): 1 / math.sqrt(2),
        _configuration([("A", other_branch, False)]): 1 / math.sqrt(2),
    }
    move_into_other_branch = PaperMoveAction("A", origin, other_branch)
    move_collisions = []
    split_collisions = []

    for level in (1, 2, 3, 4):
        engine = PaperQuantumEngine(board_size=6, level=level)
        state = engine.state_from_amplitudes(amplitudes, owners={"A": 0}, turn=0)
        actions = set(engine.legal_actions(state))
        move_collisions.extend(
            (level, action) for action in actions if action == move_into_other_branch
        )
        split_collisions.extend(
            (level, action) for action in actions
            if action.kind == "spread" and action.piece_id == "A"
            and action.origin == origin and other_branch in action.targets
        )

    assert not split_collisions, f"split collisions={split_collisions}"
    assert not move_collisions, f"move collisions={move_collisions}"


def _owner_material(state):
    """Expected count of live roster pieces per owner, ignoring promotion ancillas."""
    owners = dict(state.roster)
    totals = [0.0, 0.0]
    for configuration, amplitude in state.amplitudes:
        probability = abs(amplitude) ** 2
        for piece_id, square, _ in configuration:
            if piece_id in owners and square is not None:
                totals[owners[piece_id]] += probability
    return tuple(totals)


def _branch_material(state):
    """Set of per-owner physical piece counts across nonzero basis branches."""
    owners = dict(state.roster)
    return {
        tuple(sum(1 for piece_id, square, _ in configuration
                  if piece_id in owners and owners[piece_id] == owner and square is not None)
              for owner in (0, 1))
        for configuration, amplitude in state.amplitudes if abs(amplitude) > 0
    }


def _assert_state_invariants(engine, state):
    roster = dict(state.roster)
    assert state.turn in (0, 1)
    assert math.isclose(sum(abs(amplitude) ** 2
                            for _, amplitude in state.amplitudes), 1.0,
                        rel_tol=1e-9, abs_tol=1e-9)
    for configuration, amplitude in state.amplitudes:
        assert abs(amplitude) > 0
        ids = [piece_id for piece_id, _, _ in configuration]
        assert len(ids) == len(set(ids))
        assert set(roster).issubset(ids)
        assert all(piece_id in roster or piece_id.startswith("@promotion:")
                   for piece_id in ids)
        squares = [square for piece_id, square, _ in configuration
                   if piece_id in roster and square is not None]
        assert len(squares) == len(set(squares))
        assert all(0 <= row < engine.board_size and 0 <= col < engine.board_size
                   for row, col in squares)
    for piece in state.pieces:
        assert piece.survival_probability >= -1e-12
        assert piece.survival_probability <= 1.0 + 1e-9
        assert all(probability >= -1e-12 for _, probability in piece.sites)
        assert all(probability >= -1e-12 for _, probability in piece.king_sites)


def test_seeded_games_preserve_amplitude_material_and_turn_invariants():
    """Bounded opening games cover every supported level and board size."""
    game_seeds = (19, 2026)
    transitions = 0
    for size in (4, 6, 8):
        for level in range(5):
            for game_seed in game_seeds:
                engine = PaperQuantumEngine(
                    seed=game_seed, board_size=size, level=level, max_branches=2048
                )
                chooser = random.Random((game_seed * 31) + size * 7 + level)
                state = engine.initial_state()
                initial_material = _owner_material(state)
                _assert_state_invariants(engine, state)
                for step_index in range(8):
                    actions = engine.legal_actions(state)
                    if not actions:
                        break
                    action = chooser.choice(actions)
                    before_turn = state.turn
                    stepped = engine.apply(state, action)
                    next_state = stepped.state
                    _assert_state_invariants(engine, next_state)

                    # Measurements can change expected material by conditioning
                    # correlated branches, so compare physical branch counts.
                    # A non-capture preserves every represented count pair; a
                    # capture may additionally remove one opposing piece.
                    before_counts = _branch_material(state)
                    allowed_counts = set(before_counts)
                    if isinstance(action, PaperCaptureAction):
                        victim_owner = 1 - before_turn
                        for counts in before_counts:
                            if counts[victim_owner] > 0:
                                reduced = list(counts)
                                reduced[victim_owner] -= 1
                                allowed_counts.add(tuple(reduced))
                    assert _branch_material(next_state).issubset(allowed_counts)

                    if next_state.continuation_piece is not None:
                        assert isinstance(action, PaperCaptureAction)
                        assert next_state.turn == before_turn
                    else:
                        assert next_state.turn == 1 - before_turn
                    assert len(next_state.roster) == len(state.roster)
                    assert all(count <= initial_material[owner] + 1e-8
                               for counts in _branch_material(next_state)
                               for owner, count in enumerate(counts))
                    state = next_state
                    transitions += 1
                assert transitions > 0
    assert transitions <= 3 * 5 * len(game_seeds) * 8
