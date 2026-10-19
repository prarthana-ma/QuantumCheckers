"""Seeded game runner.

Owner: **Person B -- baseline agents and harness**. This is the headless harness that
brief section 16 Gate 3 requires, and the JSONL writer whose format Person D and
Person E depend on.

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