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
