"""Experiment runner for QuantumCheckers.

Orchestrates complete experiments using the real engine and agent implementations.
The runner owns game orchestration only — no game rules (the engine owns those), no
statistics or plotting (P2 owns those), no frontend (P4 owns that).

P1's ``scripts/run_ablation.py`` imports ``log_path`` and ``run_condition`` from this
module; the signatures are part of the integration contract.

Design:
- Engines are created per-game via a factory (seed -> engine).
- Agents are created per-game from a kind registry.
- Seats alternate when configured, to reduce first-player bias.
- Every game produces one JSONL record via the schema module.
- Failures are captured as distinct outcomes (error/timeout/invalid_action), never
  silently fabricated as valid results.
- Resources are cleaned up after each game regardless of outcome.
"""Seeded game runner.

Owner: **Person B -- baseline agents and harness**. This is the headless harness that
brief section 16 Gate 3 requires, and the JSONL writer whose format Person D and
P4 depend on.

Determinism contract
--------------------
``play(engine, agents, seed)`` is a pure function of its three arguments. The same
``(engine config, agent config, seed)`` produces a :class:`GameRecord` whose
``to_line()`` is byte-identical across runs and across processes. That is asserted in
``tests/test_runner.py`` and is what makes "logs regenerable from seeds" (brief
section 12) true rather than aspirational.

Every random stream is explicit:

* the engine owns its own ``random.Random(seed)`` for collapse sampling;
* each agent owns a ``random.Random``, constructed from the same seed by
  :func:`make_agent`, so agents are reproducible too;
* the runner itself never touches ``random``.

Nothing here imports numpy or matplotlib.
"""

from __future__ import annotations

import logging
import signal
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from qcheckers.agents.base import Agent
from qcheckers.engine.protocol import Action, GameEngine, GameState, Outcome, Transition
from qcheckers.experiment.config import ExperimentConfig
from qcheckers.experiment.schema import (
    env_metadata,
    make_record,
    write_record,
)
from qcheckers.experiment.seeds import SeedManager

logger = logging.getLogger(__name__)

#: Maps agent kind names to factory callables. P1's agents are imported lazily.
_AGENT_REGISTRY: dict[str, Callable[..., Agent]] = {}


def register_agent_kind(kind: str, factory: Callable[..., Agent]) -> None:
    """Register an agent factory under a kind name. Allows P1's agents to plug in."""
    _AGENT_REGISTRY[kind] = factory


def _lazy_import_agent(kind: str) -> Callable[..., Agent] | None:
    """Attempt to import an agent factory from P1's modules. Returns None if unavailable."""
    if kind == "observe":
        try:
            from qcheckers.agents.observe_agent import ObserveAgent
            return lambda engine, **kw: ObserveAgent(engine=engine, **kw)
        except Exception:
            return None
    if kind == "prob":
        try:
            from qcheckers.agents.prob_aware import ProbAwareAgent
            return lambda engine, **kw: ProbAwareAgent(engine=engine, **kw)
        except Exception:
            return None
    return None


def get_agent_factory(kind: str) -> Callable[..., Agent]:
    """Get the factory for an agent kind. Raises KeyError if not registered."""
    if kind in _AGENT_REGISTRY:
        return _AGENT_REGISTRY[kind]
    # Try lazy import for P1's agents
    factory = _lazy_import_agent(kind)
    if factory is not None:
        _AGENT_REGISTRY[kind] = factory
        return factory
    raise KeyError(
        f"unknown agent kind {kind!r}; registered: {list(_AGENT_REGISTRY)}. "
        "P1's agents (observe, prob) require their branch to be merged."
    )


# Register P3's baseline agents at import time
from qcheckers.agents.mcts_baseline import MctsBaselineAgent  # noqa: E402
from qcheckers.agents.random_agent import RandomAgent  # noqa: E402

register_agent_kind("random", lambda engine, **kw: RandomAgent(seed=kw.pop("seed", 0), **kw))
register_agent_kind("mcts", lambda engine, **kw: MctsBaselineAgent(engine=engine, **kw))


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class GameTimeoutError(TimeoutError):
    """Raised when a game exceeds its wall-clock budget."""


@contextmanager
def _time_limit(seconds: float | None):
    """Context manager that raises GameTimeoutError after ``seconds``.

    Uses signal.alarm on Unix; on platforms without SIGALRM (Windows), falls back
    to a no-op (documented limitation: wall-clock timeout requires SIGALRM).
    """
    if seconds is None:
        yield
        return
    try:
        import sys
        if sys.platform == "win32" or not hasattr(signal, "SIGALRM"):
            # No wall-clock timeout on this platform; documented limitation
            logger.warning(
                "Wall-clock timeout (%s) requested but not supported on this platform; "
                "timeout will not be enforced.",
                seconds,
            )
            yield
            return

        def _handler(signum, frame):
            raise GameTimeoutError(f"game exceeded {seconds}s wall-clock limit")

        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(int(seconds) if seconds >= 1 else 1)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except ImportError:
        yield


# ---------------------------------------------------------------------------
# Game execution
# ---------------------------------------------------------------------------


@dataclass
class GameResult:
    """Result of a single game."""
    outcome: str  # "win_p0", "win_p1", "draw", "error", "timeout", "invalid_action"
    winner: int | None
    n_plies: int
    duration_seconds: float
    seed: int
    engine_seed: int
    error: str | None = None
    draw_reason: str | None = None
    transitions: list[tuple[Action, Transition]] = field(default_factory=list)
    initial_state: GameState | None = None
    final_state: GameState | None = None
    agents: dict[str, str] = field(default_factory=dict)
    player_assignment: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def run_game(
    engine_factory: Callable[[int], GameEngine],
    agent_kinds: tuple[str, str],
    *,
    seed: int,
    game_index: int = 0,
    alternate: bool = True,
    seed_manager: SeedManager | None = None,
    config: ExperimentConfig | None = None,
    timeout_seconds: float | None = None,
    max_plies: int | None = None,
) -> GameResult:
    """Run a single game and return a GameResult.

    Parameters
    ----------
    engine_factory:
        Callable taking an engine seed and returning a fresh GameEngine.
    agent_kinds:
        (kind_for_p0, kind_for_p1). If ``alternate`` is True and game_index is odd,
        the kinds are swapped to balance seats.
    seed:
        Base seed for this game (used for agent RNG seeds).
    game_index:
        Index of this game in the batch (used for seat alternation).
    alternate:
        If True, swap agent kinds on odd-indexed games.
    seed_manager:
        Optional SeedManager for deriving per-agent seeds.
    config:
        Optional ExperimentConfig for engine construction.
    timeout_seconds:
        Optional wall-clock timeout.
    max_plies:
        Optional ply cap override.
    """
    kinds = list(agent_kinds)
    if alternate and game_index % 2 == 1:
        kinds.reverse()

    engine_seed = seed
    agent_seed_p0 = seed_manager.agent_seed(game_index, 0) if seed_manager else seed
    agent_seed_p1 = seed_manager.agent_seed(game_index, 1) if seed_manager else seed + 1

    start = time.perf_counter()
    transitions: list[tuple[Action, Transition]] = []
    diagnostics: dict[str, Any] = {}

    try:
        with _time_limit(timeout_seconds):
            engine = engine_factory(engine_seed)
            factory_p0 = get_agent_factory(kinds[0])
            factory_p1 = get_agent_factory(kinds[1])
            agent_p0 = factory_p0(engine, seed=agent_seed_p0, name=kinds[0])
            agent_p1 = factory_p1(engine, seed=agent_seed_p1, name=kinds[1])

            agents_map = {"0": agent_p0.name, "1": agent_p1.name}
            assignment_map = {"0": kinds[0], "1": kinds[1]}

            state = engine.initial_state()
            initial_state = state
            ply_cap = max_plies or (config.max_plies if config else 120)

            while True:
                outcome = engine.outcome(state)
                if outcome is not None:
                    elapsed = time.perf_counter() - start
                    return GameResult(
                        outcome=_outcome_str(outcome),
                        winner=outcome.winner,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        draw_reason=outcome.reason if outcome.winner is None else None,
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                if state.ply >= ply_cap:
                    elapsed = time.perf_counter() - start
                    return GameResult(
                        outcome="draw",
                        winner=None,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        draw_reason="ply_cap",
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                legal = list(engine.legal_actions(state))
                if not legal:
                    elapsed = time.perf_counter() - start
                    return GameResult(
                        outcome="draw",
                        winner=None,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        draw_reason="no_legal_actions",
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                current_agent = agent_p0 if state.turn == 0 else agent_p1
                try:
                    action = current_agent.decide(state, legal)
                except Exception as exc:
                    elapsed = time.perf_counter() - start
                    diagnostics["agent_error"] = str(exc)
                    return GameResult(
                        outcome="error",
                        winner=None,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        error=f"agent {current_agent.name!r} raised: {exc}",
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                # Validate the action is in the legal set
                if not any(a == action for a in legal):
                    elapsed = time.perf_counter() - start
                    return GameResult(
                        outcome="invalid_action",
                        winner=None,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        error=f"agent {current_agent.name!r} returned illegal action {action!r}",
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                try:
                    transition = engine.apply(state, action)
                except Exception as exc:
                    elapsed = time.perf_counter() - start
                    return GameResult(
                        outcome="error",
                        winner=None,
                        n_plies=state.ply,
                        duration_seconds=elapsed,
                        seed=seed,
                        engine_seed=engine_seed,
                        error=f"engine.apply raised: {exc}",
                        transitions=transitions,
                        initial_state=initial_state,
                        final_state=state,
                        agents=agents_map,
                        player_assignment=assignment_map,
                        diagnostics=diagnostics,
                    )

                transitions.append((action, transition))
                state = transition.state

    except GameTimeoutError:
        elapsed = time.perf_counter() - start
        return GameResult(
            outcome="timeout",
            winner=None,
            n_plies=len(transitions),
            duration_seconds=elapsed,
            seed=seed,
            engine_seed=engine_seed,
            error=f"exceeded {timeout_seconds}s wall-clock limit",
            transitions=transitions,
            initial_state=None,
            final_state=None,
            agents={},
            player_assignment={},
            diagnostics=diagnostics,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return GameResult(
            outcome="error",
            winner=None,
            n_plies=len(transitions),
            duration_seconds=elapsed,
            seed=seed,
            engine_seed=engine_seed,
            error=f"unexpected error: {exc}\n{traceback.format_exc()}",
            transitions=transitions,
            initial_state=None,
            final_state=None,
            agents={},
            player_assignment={},
            diagnostics=diagnostics,
        )
    finally:
        # Cleanup: reset agents if possible
        try:
            if "agent_p0" in dir():
                agent_p0.reset()
            if "agent_p1" in dir():
                agent_p1.reset()
        except Exception:
            pass


def _outcome_str(outcome: Outcome) -> str:
    if outcome.winner is None:
        return "draw"
    return f"win_p{outcome.winner}"


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------


def _result_to_record(
    result: GameResult,
    *,
    experiment_id: str,
    game_id: str,
    timestamp: str,
    seed: int,
    config: ExperimentConfig | None,
    replay_ref: str | None = None,
) -> dict[str, Any]:
    """Convert a GameResult to a JSONL record dict."""
    initial_summary = {}
    if result.initial_state is not None:
        initial_summary = {
            "pieces": len(result.initial_state.pieces),
            "board_size": config.board_size if config else 4,
        }
    record = make_record(
        schema_version="1.0",
        experiment_id=experiment_id,
        game_id=game_id,
        timestamp=timestamp,
        agents=result.agents or {"0": "unknown", "1": "unknown"},
        player_assignment=result.player_assignment or {"0": "unknown", "1": "unknown"},
        seed=seed,
        initial_state=initial_summary,
        config=(config.to_dict() if config else {}),
        outcome=result.outcome,
        winner=result.winner,
        draw_reason=result.draw_reason,
        n_plies=result.n_plies,
        duration_seconds=result.duration_seconds,
        error=result.error,
        replay_ref=replay_ref,
        metrics=result.diagnostics,
        env=env_metadata(),
    )
    return record


# ---------------------------------------------------------------------------
# Batch execution
# ---------------------------------------------------------------------------


def log_path(label: str, results_dir: str | Path) -> Path:
    """Construct the JSONL output path for a condition label."""
    safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    return Path(results_dir) / f"{safe_label}.jsonl"


def run_condition(
    engine_factory: Callable[[int], GameEngine],
    agent_kinds: tuple[str, str],
    seeds: Sequence[int],
    *,
    condition: str = "condition",
    output: Path | str | None = None,
    overwrite: bool = True,
    alternate: bool = True,
    seed_manager: SeedManager | None = None,
    config: ExperimentConfig | None = None,
    export_replays: bool = False,
    replay_dir: str | Path = "results/replays",
) -> list[dict[str, Any]]:
    """Run a batch of games and return the JSONL records.

    This is the function P1's ``scripts/run_ablation.py`` calls.
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from qcheckers.agents.base import Agent
from qcheckers.engine.protocol import Action, GameEngine
from qcheckers.experiment.schema import GameRecord, TurnRecord, board_snapshot

#: Directory the CLI scripts write logs into, relative to the repo root.
DEFAULT_RESULTS_DIR = Path("results")

#: Levels the **batch** runner will play. Level 3 (merge) and level 4 (decoherence) are
#: playable in the game client and are deliberately excluded from experiments:
#: level 3 is game-only per the brief, and level 4 is an invented outreach mechanic.
#: :func:`run_condition` refuses anything outside this set so no batch can quietly
#: include them; :func:`play` stays available for single games and tests.
BATCHABLE_LEVELS: tuple[int, ...] = (0, 1, 2)

#: Signature of the engine factory :func:`run_condition` expects.
EngineFactory = Callable[[int], GameEngine]


def play(
    engine: GameEngine,
    agents: Mapping[int, Agent],
    seed: int,
    *,
    condition: str = "unspecified",
    game_id: str | None = None,
    max_plies: int | None = None,
) -> GameRecord:
    """Play one complete game and return its record.

    Parameters
    ----------
    engine:
        Engine to play on. Its own RNG must already be seeded; the caller constructs
        it with the same ``seed``.
    agents:
        Mapping of player id to agent. Both players must be present -- a missing player
        is a configuration error, not a silent random fallback.
    seed:
        The seed. Recorded on the record so a log line ties back to its generating
        command; it is not consumed here.
    condition:
        Experimental condition label, e.g. ``"classical-random-vs-random"``.
    game_id:
        Override the default ``"<condition>-<seed>"`` identifier.
    max_plies:
        Optional hard cap, tightened against ``engine.max_plies``. Lets a smoke test
        stay short without changing engine behaviour.

    Returns
    -------
    GameRecord
        Complete record, including per-turn detail.

    Raises
    ------
    KeyError
        If a player id has no agent.
    ValueError
        If an agent returns an action outside ``legal``, or if the engine reports a
        non-terminal position with no legal move -- both engine bugs, surfaced
        immediately rather than written into a log.
    """
    missing = [player for player in (0, 1) if player not in agents]
    if missing:
        raise KeyError(f"no agent supplied for player(s) {missing}")

    limit = engine.max_plies if max_plies is None else min(max_plies, engine.max_plies)

    state = engine.initial_state()
    turns: list[TurnRecord] = []
    collapses = 0
    collapse_pieces: set[str] = set()
    counts = {"move": 0, "capture": 0, "spread": 0, "rejoin": 0, "observe": 0}

    while state.ply < limit and not engine.is_terminal(state):
        legal: tuple[Action, ...] = engine.legal_actions(state)
        if not legal:
            raise ValueError(
                f"engine {engine.name} reports a non-terminal position with no legal "
                f"move on ply {state.ply}"
            )

        agent = agents[state.turn]
        action = agent.decide(state, legal)
        if action not in legal:
            raise ValueError(
                f"agent {getattr(agent, 'name', type(agent).__name__)!r} returned an "
                f"illegal {action.kind} action on ply {state.ply}"
            )
        counts[action.kind] = counts.get(action.kind, 0) + 1

        mover = state.turn
        step = engine.apply(state, action)
        for event in step.events:
            collapses += 1
            collapse_pieces.add(event.piece_id)
        state = step.state

        turns.append(
            TurnRecord(
                ply=len(turns),
                player=mover,
                action=action,
                board_after=board_snapshot(engine, state),
                events=tuple(_event_to_json(event) for event in step.events),
            )
        )

    outcome = engine.outcome(state)
    if outcome is None:
        # Exited on the ply cap without the engine declaring a result. Record a draw
        # rather than inventing a winner.
        winner: int | None = None
        termination = "ply_limit"
    else:
        winner = outcome.winner
        termination = outcome.reason

    return GameRecord(
        game_id=game_id or f"{condition}-{seed}",
        seed=int(seed),
        condition=condition,
        engine=engine.name,
        level=int(getattr(engine, "level", 0)),
        allow_observe=bool(getattr(engine, "allow_observe", False)),
        # The cap is a terminal condition of this engine and search agents read it, so it
        # is part of what makes the line regenerable rather than an implementation detail.
        max_plies=int(getattr(engine, "max_plies", limit)),
        players={
            player: str(getattr(agent, "name", type(agent).__name__))
            for player, agent in sorted(agents.items())
        },
        winner=winner,
        termination=termination,
        length=state.ply,
        collapses=collapses,
        collapse_pieces=tuple(sorted(collapse_pieces)),
        observe_moves=counts["observe"],
        spread_moves=counts["spread"],
        capture_moves=counts["capture"],
        board_moves=counts["move"],
        rejoin_moves=counts["rejoin"],
        final_board=board_snapshot(engine, state),
        turns=tuple(turns),
    )


def _event_to_json(event: Any) -> dict[str, Any]:
    """Collapse event -> plain dict with flattened ``[row, col, weight]`` squares."""
    payload = event.to_json()
    payload["chances"] = [[square[0][0], square[0][1], square[1]] for square in payload["chances"]]
    payload["sampled"] = list(payload["sampled"])
    return payload


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------


def write_jsonl(path: str | Path, records: Iterable[GameRecord]) -> int:
    """Write ``records`` to ``path``, replacing any existing file.

    Returns the number of records written. Creates parent directories as needed.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [record.to_line() for record in records]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def append_jsonl(path: str | Path, record: GameRecord) -> None:
    """Append one record to ``path``, creating it and its parents if needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(record.to_line() + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL log into a list of dicts.

    Blank lines are skipped. A malformed line raises ``ValueError`` naming the file and
    line number, because silently dropping a corrupted record would quietly shift every
    rate Person D computes.

    A missing file yields an empty list, so scripts can run before any batch exists.
    """
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    text = source.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{number}: invalid JSON ({exc})") from exc
    return records


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------


#: Agent *label* (what a log records under ``players``) back to the *kind*
#: :func:`make_agent` builds. A record stores the label so the log is readable without
#: the script that wrote it; this table is what turns it back into a player, which is how
#: `scripts/verify_results.py` regenerates a logged game from the log alone. Keep it in
#: step with the default names in :func:`make_agent` -- `tests/test_runner.py` fails if
#: the two drift apart.
AGENT_KINDS_BY_LABEL: Mapping[str, str] = {
    "random": "random",
    "mcts-baseline": "mcts",
    "observe-agent": "observe",
    "prob-aware": "prob",
    "prob-aware-hard": "hard",
}


def kind_for_label(label: str) -> str:
    """The agent kind behind a logged label.

    Raises rather than guessing: an unrecognised label means the log was written by code
    this version cannot replay, and silently substituting a baseline would "verify" a
    game that was never played.
    """
    try:
        return AGENT_KINDS_BY_LABEL[label]
    except KeyError:
        raise ValueError(
            f"unknown agent label {label!r}; known labels are "
            f"{sorted(AGENT_KINDS_BY_LABEL)}"
        ) from None


def make_agent(kind: str, engine: GameEngine, seed: int, *, name: str | None = None) -> Agent:
    """Build one agent by short name, seeded from ``seed``.

    This indirection lets a condition be described as *data* (see
    :mod:`qcheckers.experiment.config`) rather than a hand-written script, so the
    ablation labels live in one place.

    Supported kinds: ``"random"``, ``"mcts"``, ``"observe"``, ``"prob"`` and ``"hard"``.
    The first four are the research agents; ``"hard"`` is the game client's Hard tier
    (probability-aware search with the voluntary Observe policy switched on). Unknown
    kinds raise ``ValueError`` rather than defaulting, because a typo'd label silently
    becoming a random baseline would wreck a comparison.
    """
    normalized = kind.lower()
    if normalized == "random":
        from qcheckers.agents.random_agent import RandomAgent

        return RandomAgent(seed, name=name or "random")
    if normalized == "mcts":
        from qcheckers.agents.mcts_baseline import MCTSBaselineAgent

        return MCTSBaselineAgent(engine, seed=seed, name=name or "mcts-baseline")
    if normalized == "observe":
        from qcheckers.agents.observe_agent import ObserveAgent

        return ObserveAgent(engine, name=name or "observe-agent")
    if normalized == "prob":
        from qcheckers.agents.prob_aware import ProbAwareAgent

        return ProbAwareAgent(engine, seed=seed, name=name or "prob-aware")
    if normalized == "hard":
        from qcheckers.agents.prob_aware import HARD_OBSERVE_FLOOR, ProbAwareAgent

        return ProbAwareAgent(
            engine,
            seed=seed,
            name=name or "prob-aware-hard",
            observe_threshold=HARD_OBSERVE_FLOOR,
            split_eager=True,
        )
    raise ValueError(
        f"unknown agent kind {kind!r}; expected one of 'random', 'mcts', 'observe', "
        "'prob', 'hard'"
    )


def run_condition(
    engine_factory: EngineFactory,
    agent_kinds: Sequence[str],
    seeds: Sequence[int],
    *,
    condition: str,
    output: str | Path | None = None,
    overwrite: bool = True,
    max_plies: int | None = None,
) -> list[GameRecord]:
    """Run one experimental condition across ``seeds``, optionally writing a JSONL log.

    Parameters
    ----------
    engine_factory:
        Callable taking an engine seed and returning a fresh GameEngine.
    agent_kinds:
        (kind_for_p0, kind_for_p1).
    seeds:
        One engine seed per game.
    condition:
        Condition label written into records.
    output:
        JSONL output path. If None, no file is written.
    overwrite:
        If True, overwrite existing output. If False, append.
    alternate:
        Alternate seats on odd-indexed games.
    seed_manager:
        Optional SeedManager for per-agent seeds.
    config:
        Optional ExperimentConfig.
    export_replays:
        If True, export a replay JSON per game.
    replay_dir:
        Directory for replay files.

    Returns
    -------
    list of record dicts, one per game.
    """
    records: list[dict[str, Any]] = []
    from datetime import datetime, timezone

    output_path = Path(output) if output else None
    if output_path and output_path.exists() and not overwrite:
        # Append mode: read existing records and skip already-completed game_ids
        from qcheckers.experiment.schema import read_records
        existing = read_records(output_path)
        existing_ids = {
            r["game_id"] for r, errs in existing if r and not errs
        }
    else:
        existing_ids = set()

    # Decide file mode once, before the loop
    file_mode = "a" if (output_path and output_path.exists() and not overwrite) else "w"

    # Open output file once, outside the loop, so all records go to the same handle
    output_handle = None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = open(output_path, file_mode, encoding="utf-8")

    try:
        for i, engine_seed in enumerate(seeds):
            # Game ID derived from the seed value (not batch position) so that
            # overlapping batches produce identical IDs for the same game.
            game_id = f"{condition}-s{engine_seed:010d}"
            if game_id in existing_ids:
                logger.info("skipping %s (already complete)", game_id)
                continue

            ts = datetime.now(timezone.utc).isoformat()
            result = run_game(
                engine_factory,
                agent_kinds,
                seed=engine_seed,
                game_index=i,
                alternate=alternate,
                seed_manager=seed_manager,
                config=config,
                timeout_seconds=(config.timeout_seconds if config else None),
                max_plies=(config.max_plies if config else None),
            )

            replay_ref = None
            if export_replays and result.final_state is not None:
                from qcheckers.experiment.replay import build_replay, export_replay
                from qcheckers.engine.protocol import Outcome

                outcome_obj = Outcome(
                    winner=result.winner,
                    reason=result.draw_reason or "",
                )
                # Determine board size
                board_size = config.board_size if config else 4
                agents_map = result.agents or {"0": "unknown", "1": "unknown"}
                payload = build_replay(
                    experiment_id=condition,
                    game_id=game_id,
                    seed=engine_seed,
                    board_size=board_size,
                    agents=agents_map,
                    initial_state=result.initial_state,
                    transitions=result.transitions,
                    final_state=result.final_state,
                    outcome=outcome_obj,
                )
                replay_path = Path(replay_dir) / f"{game_id}.replay.json"
                export_replay(payload, replay_path)
                # Store replay ref relative to the output file's directory
                if output_path:
                    try:
                        replay_ref = str(replay_path.relative_to(output_path.parent))
                    except ValueError:
                        replay_ref = str(replay_path)
                else:
                    replay_ref = str(replay_path)

            record = _result_to_record(
                result,
                experiment_id=condition,
                game_id=game_id,
                timestamp=ts,
                seed=engine_seed,
                config=config,
                replay_ref=replay_ref,
            )
            records.append(record)

            if output_handle is not None:
                write_record(output_handle, record)
    finally:
        if output_handle is not None:
            output_handle.close()

    return records


# ---------------------------------------------------------------------------
# Full experiment
# ---------------------------------------------------------------------------


def run_experiment(
    config: ExperimentConfig,
    engine_factory: Callable[[int], GameEngine],
    *,
    export_replays: bool | None = None,
) -> list[dict[str, Any]]:
    """Run a full experiment from an ExperimentConfig.

    Derives seeds via SeedManager, runs all games with seat alternation, writes JSONL
    and optionally exports replays.
    """
    seed_mgr = SeedManager(config.base_seed)
    seeds = seed_mgr.game_seeds(config.n_games)
    output = log_path(config.experiment_id, config.output_dir)
    do_replays = export_replays if export_replays is not None else config.export_replays

    return run_condition(
        engine_factory,
        config.agents,
        seeds,
        condition=config.experiment_id,
        output=output,
        overwrite=True,
        alternate=config.alternate_seats,
        seed_manager=seed_mgr,
        config=config,
        export_replays=do_replays,
        replay_dir=str(Path(config.output_dir) / "replays"),
    )


__all__ = [
    "GameResult",
    "GameTimeoutError",
    "run_condition",
    "run_experiment",
    "run_game",
    "log_path",
    "get_agent_factory",
    "register_agent_kind",
]
        Callable taking ``seed`` and returning a freshly seeded engine. A factory
        rather than an instance, because each game needs its own RNG.
    agent_kinds:
        One agent kind per player in player order: ``agent_kinds[0]`` is player 0.
    seeds:
        Seeds to play, in order.
    condition:
        Label stamped on every record.
    output:
        JSONL path, or ``None`` to skip writing.
    overwrite:
        ``True`` (default) replaces the log. ``False`` appends, which is what a
        resumed batch wants.
    max_plies:
        Optional per-game ply cap.

    Returns
    -------
    list[GameRecord]
        The records, in seed order.

    Raises
    ------
    ValueError
        If ``agent_kinds`` does not name exactly two players.
    """
    if len(agent_kinds) != 2:
        raise ValueError(
            f"need exactly two agent kinds (player 0 and player 1); got {agent_kinds!r}"
        )

    if seeds:
        probe_level = int(getattr(engine_factory(seeds[0]), "level", 0))
        if probe_level not in BATCHABLE_LEVELS:
            raise ValueError(
                f"refusing to batch level {probe_level}: only {BATCHABLE_LEVELS} may be "
                "batched. Level 3 (merge) and level 4 (decoherence) are playable in the "
                "game client but are excluded from experiments by the project boundary."
            )

    if output is not None and not overwrite:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text("", encoding="utf-8")

    records: list[GameRecord] = []
    for seed in seeds:
        engine = engine_factory(seed)
        agents = {
            0: make_agent(agent_kinds[0], engine, seed),
            1: make_agent(agent_kinds[1], engine, seed),
        }
        record = play(engine, agents, seed, condition=condition, max_plies=max_plies)
        records.append(record)
        if output is not None and not overwrite:
            append_jsonl(output, record)

    if output is not None and overwrite:
        write_jsonl(output, records)

    return records


def log_path(condition: str, results_dir: str | Path = DEFAULT_RESULTS_DIR) -> Path:
    """Conventional JSONL path for a condition: ``results/<condition>.jsonl``."""
    return Path(results_dir) / f"{condition}.jsonl"


__all__ = [
    "BATCHABLE_LEVELS",
    "DEFAULT_RESULTS_DIR",
    "EngineFactory",
    "append_jsonl",
    "log_path",
    "make_agent",
    "play",
    "read_jsonl",
    "run_condition",
    "write_jsonl",
]
