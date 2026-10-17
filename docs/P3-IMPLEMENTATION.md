# P3 Implementation: Baselines, Experiment Runner, and Verification

**Owner:** P3 — Harsha
**Branch:** `p3/baselines-runner-verification`
**Status:** Implemented and tested (122 tests passing)

---

## 1. Module ownership

| Module | Owner | Purpose |
|--------|-------|---------|
| `qcheckers/agents/random_agent.py` | P3 | Uniform-random baseline |
| `qcheckers/agents/mcts_baseline.py` | P3 | Conventional UCT MCTS baseline |
| `qcheckers/agents/base.py` | Shared | Agent protocol + `fallback_action` |
| `qcheckers/engine/protocol.py` | Shared (P5 implements) | Engine interfaces |
| `qcheckers/experiment/config.py` | P3 | Validated experiment configuration |
| `qcheckers/experiment/seeds.py` | P3 | Seed derivation and management |
| `qcheckers/experiment/schema.py` | P3 | JSONL record schema |
| `qcheckers/experiment/runner.py` | P3 | Game and batch execution |
| `qcheckers/experiment/replay.py` | P3 | Replay export |
| `scripts/verify_results.py` | P3 | Result verification |
| `scripts/run_baseline.py` | P3 | Baseline CLI |
| `tests/support/quantum_toy.py` | P3 | Non-authoritative dev/test engine |

---

## 2. Agent interface

All agents implement the `Agent` protocol from `qcheckers/agents/base.py`:

```python
class Agent(Protocol):
    name: str
    def decide(self, state: GameState, legal: Sequence[Action]) -> Action: ...
    def reset(self) -> None: ...
```

- `decide` receives the current state and the engine's legal-action list, returns one legal action.
- Agents that need randomness receive a private, seedable RNG — never the global `random` module.
- `reset()` returns the agent to a clean state between games.
- P1's agents (`ObserveAgent`, `ProbAwareAgent`) are imported lazily by the runner when their branch is merged.

---

## 3. Random baseline

**File:** `qcheckers/agents/random_agent.py`

- Selects uniformly at random from the engine's legal actions.
- No heuristics, no lookahead.
- Uses `random.Random(seed)` — injected, seedable, no global state.
- Same seed + same state + same legal sequence ⇒ same action.
- Handles empty legal-action lists by raising `ValueError`.

---

## 4. Conventional MCTS baseline

**File:** `qcheckers/agents/mcts_baseline.py`

### Method

1. **Selection:** UCT — `uct = mean_value + C * sqrt(ln(parent_visits) / visits)`
2. **Expansion:** Pop one untried action, create child node.
3. **Simulation:** Uniform random rollout with ply cap (default 32).
4. **Backpropagation:** Propagate rollout score up the tree. Reward is from the root player's perspective throughout (no perspective flipping — the root player is fixed for the whole search).
5. **Final action selection:** Robust child (most visited), tie-break by mean value.

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `exploration` (C) | 1.41 (√2) | UCT exploration constant |
| `iterations` | 24 | MCTS iterations per move |
| `rollout_steps` | 32 | Ply cap per rollout |

### Reward convention

- +1: root player wins
- -1: root player loses
- 0: draw or depth cut (heuristic evaluation clamped to [-1, 1])

### Quantum uncertainty

This is a **conventional** MCTS — it does NOT model quantum uncertainty in the tree policy. Quantum mechanics (collapse outcomes) are handled by the engine during rollouts. The heuristic evaluation uses only the single most-likely square per piece (not the chance-weighted sum), which is what distinguishes it from P1's probability-aware evaluation.

### Diagnostics

Each `decide()` call populates `last_diagnostics` with: simulations, expansions, completed_rollouts, elapsed_seconds, root_visits, n_root_children.

---

## 5. Engine interface

**File:** `qcheckers/engine/protocol.py` (interfaces only — P5 implements)

```python
class GameEngine(ABC):
    board_size: int
    def initial_state(self) -> GameState: ...
    def legal_actions(self, state: GameState) -> Sequence[Action]: ...
    def apply(self, state: GameState, action: Action) -> Transition: ...
    def is_terminal(self, state: GameState) -> bool: ...
    def outcome(self, state: GameState) -> Outcome | None: ...
```

Engines that support cloning implement `clone(seed) -> GameEngine` for isolated search.

---

## 6. Experiment configuration

**File:** `qcheckers/experiment/config.py`

JSON or TOML format. All fields validated on construction.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `experiment_id` | str | "default" | Experiment identifier |
| `version` | str | "1" | Config schema version |
| `agents` | tuple[str,str] | ("random","mcts") | Agent kinds for p0, p1 |
| `agent_params` | dict | {} | Per-agent parameters |
| `n_games` | int | 10 | Number of games |
| `base_seed` | int | 0 | Root seed |
| `board_size` | int | 4 | Board edge (≥4) |
| `max_plies` | int | 120 | Ply cap |
| `level` | int | 2 | Engine level (0,1,2) |
| `allow_observe` | bool | True | Allow Observe actions |
| `alternate_seats` | bool | True | Swap seats on odd games |
| `engine_kind` | str | "toy" | Engine identifier |
| `output_dir` | str | "results" | Output directory |
| `export_replays` | bool | False | Export replay per game |
| `log_level` | str | "INFO" | Logging level |
| `timeout_seconds` | float\|None | None | Per-game wall-clock timeout |
| `description` | str | "" | Human-readable description |

`MIN_GAMES_JUSTIFIED = 20` — imported by P1's ablation script.

---

## 7. JSONL schema

**File:** `qcheckers/experiment/schema.py`
**Schema version:** `1.0`

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | str | Must be "1.0" |
| `experiment_id` | str | Non-empty |
| `game_id` | str | Unique, non-empty |
| `timestamp` | str | ISO 8601 |
| `agents` | dict | {"0": name, "1": name} |
| `player_assignment` | dict | {"0": kind, "1": kind} |
| `seed` | int | Non-negative |
| `initial_state` | dict | {"pieces": int, "board_size": int} |
| `config` | dict | Serialized ExperimentConfig |
| `outcome` | str | win_p0, win_p1, draw, error, timeout, invalid_action |
| `winner` | int\|None | 0, 1, or None |
| `draw_reason` | str\|None | Reason if draw |
| `n_plies` | int | Non-negative |
| `duration_seconds` | float | Non-negative, finite |
| `error` | str\|None | Error message if applicable |

### Optional fields

| Field | Type | Description |
|-------|------|-------------|
| `replay_ref` | str\|None | Path to replay JSON |
| `metrics` | dict | Performance diagnostics |
| `env` | dict | Python version, platform |

### Outcome/winner consistency

- `win_p0` ⇒ `winner=0`
- `win_p1` ⇒ `winner=1`
- `draw` ⇒ `winner=None`
- `error`/`timeout`/`invalid_action` ⇒ `winner=None`

---

## 8. Seed policy

**File:** `qcheckers/experiment/seeds.py`

- Root seed → per-game engine seeds: `derive_seed(root, 0, game_index)`
- Per-agent seeds: `derive_seed(root, 1, game_index, agent_slot)`
- Per-replay seeds: `derive_seed(root, 2, game_index)`
- Formula: `sha256("root|p1|p2|...")[:4] % 2^31`
- All seeds are non-negative integers.
- Same root + same parts ⇒ same seed (deterministic).
- `SeedManager.manifest()` records the policy for result files.

---

## 9. Replay format

**File:** `qcheckers/experiment/replay.py`
**Replay version:** `1.0`

Each replay is a self-contained JSON object with:
- `replay_version`, `experiment_id`, `game_id`, `seed`, `board_size`
- `agents` — player/agent mapping
- `initial_pieces` — starting position (piece_id, owner, sites with weights)
- `actions` — ordered list of {ply, player, kind, origin, target, piece_id, captured_id}
- `events` — collapse/measurement events
- `final_state` — resulting pieces, captured list, outcome
- `outcome`, `winner`, `n_plies`
- `config_ref` — optional config reference

No Python runtime objects — all data is JSON-native (lists, dicts, strings, numbers).

---

## 10. Commands

### Smoke test (2 games, random vs random)

```bash
python scripts/run_baseline.py --smoke
```

### Small batch (10 games, random vs MCTS)

```bash
python scripts/run_baseline.py -n 10 --agent-a random --agent-b mcts
```

### With config file

```bash
python scripts/run_baseline.py --config configs/baseline.json
```

### Export replays

```bash
python scripts/run_baseline.py -n 10 --agent-a random --agent-b mcts --replays
```

### Verify results

```bash
python scripts/verify_results.py results/baseline-random-vs-mcts.jsonl
```

### Run tests

```bash
python -m pytest tests/ -v
```

---

## 11. Known limitations

1. **P5's engine not yet available.** All integration tests use the non-authoritative `QuantumToyEngine` fixture (`tests/support/quantum_toy.py`). When P5's real engine lands, the fixture can be swapped without changing any P3 code — all modules depend only on the `GameEngine` interface.

2. **Wall-clock timeout on Windows.** The `timeout_seconds` config uses `signal.SIGALRM`, which is unavailable on Windows. On Windows the timeout is logged as a warning and not enforced. The ply cap (`max_plies`) always applies.

3. **P1's agents not yet merged.** The runner lazily imports `ObserveAgent` and `ProbAwareAgent` when available. Until P1's branch is merged, requesting those kinds raises a clear `KeyError`.

4. **P2's stats module not yet available.** The runner produces records with all fields P2 needs (outcome, winner, n_plies, duration, draw_reason, error), but does not compute statistics or confidence intervals.

5. **Engine determinism.** The `QuantumToyEngine` is deterministic when seeded. P5's real engine may have additional nondeterministic elements; the seed policy records all seeds but cannot guarantee bitwise reproduction of a nondeterministic engine.

6. **Resume/interrupt recovery.** `run_condition` with `overwrite=False` appends and skips completed game IDs. This is safe for crash recovery but does not resume mid-game.

---

## 12. Cross-owner integration

| Owner | Integration point | Status |
|-------|-------------------|--------|
| P1 (Teja) | Agent protocol, `DEFAULT_UCT_C`, `uct_score`, `MIN_GAMES_JUSTIFIED`, `log_path`, `run_condition` | **Tested** — P1's imports resolved against P3 modules |
| P2 (Vrinda) | Config schema, JSONL record fields | **Implemented** — all statistical fields present; stats module not yet built |
| P4 (Sona) | Replay payload format | **Implemented** — versioned, JSON-native, self-contained |
| P5 (Prarthana) | Engine protocol | **Implemented** — interfaces defined; concrete engine pending |
