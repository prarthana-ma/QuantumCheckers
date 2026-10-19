# QCheckers

QCheckers is the playable quantum checkers game developed by Team QuriousMinds.

**Quantum Checkers: The Development and Analysis of a Quantum Combinatorial Game** —
reproduction-plus-extension study.

**Hosted game:** [quriousminds.vercel.app](https://quriousminds.vercel.app).
The client is hosted on Vercel and the game API on Google Cloud Run. Deployment,
redeploy commands, IBM configuration, and limitations are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

**Submission report:** [QCheckers project report](docs/REPORT.md). The title-page
identity fields and named team contributions still need the group's details.

## Research question

A checkers-like game in which a piece can be *uncertain*: spread across more than one
square, with a chance of being found on each. When a player or an agent is given an
explicit, optional choice to **resolve that uncertainty on its own turn** — a voluntary
*Observe* move — does probability-aware decision-making behave differently from
classical-only or uncertainty-ignoring decision-making, and how does the availability of
that choice change game outcomes and game character? Specifically: does a search agent
that evaluates uncertain positions by their occupancy chances choose moves differently
from a matched baseline that treats a spread piece as if it were on its most likely
square; and does allowing voluntary measurement change outcomes? The archived study
tests an Observe on/off comparison with seeded toy-engine games and Wilson intervals.
Both arms use the same legacy `ProbAwareAgent`, whose behavior also includes
chance-weighted material, normalized progress and chance-weighted rollout sampling.
The study does not establish an uncertainty-only effect or evaluate the current local
paper engine. A null result is acceptable and reportable; code changes alone do not
establish novelty.

## Primary source

Raat, *et al.*, "Quantum Checkers: The Development and Analysis of a Quantum Combinatorial
Game," 2025 IEEE Conference on Games. DOI
[<https://doi.org/10.1109/COG64752.2025.11114278>](https://doi.org/10.1109/COG64752.2025.11114278).
Preprint: [arXiv:2506.05962](https://arxiv.org/abs/2506.05962). Upstream code:
[github.com/raatmarien/cheqqers](https://github.com/raatmarien/cheqqers). Demo:
[cheqqers.com](https://cheqqers.com).

## Status

> **Two engine paths are present.** Archived batch experiments use the frozen
> `DeterministicToyEngine`: a 4×4 probability-only model. The local server built with
> `server.app.create_app()` defaults to the separate `PaperQuantumEngine`, which keeps
> sparse joint configurations with complex amplitudes and phases on the CPU. Neither
> path is the upstream Cheqqers implementation, and archived toy-engine results are not
> results for the paper engine or its live MCTS agent.
>
> `PaperQuantumEngine` implements the staged paper-based rules at Levels 0–3 and adds a
> project-defined Level 4 decoherence/Observe extension. Its full split-unitary
> completion is an explicit local choice where the paper does not uniquely specify the
> remaining columns. It enforces a default 4,096-branch operation cap and a library
> default 1,000-ply safety limit. The default local app also sets 1,000 plies; direct
> `Room` construction retains a 200-ply compatibility default.
> [`docs/RULE_CONFORMANCE.md`](docs/RULE_CONFORMANCE.md) explains the mapping, CPU/QPU
> boundary and limits.
>
> **The upstream Cheqqers engine is not integrated.** The paper-version tag
> (`cog-paper-version`) is confirmed to exist on the upstream repository, but the
> upstream code itself has not been run here. The local paper engine is an independent
> implementation, not a wrapper or exact reproduction of upstream code. No archived
> experimental result is a reproduced paper result.
>
> The archived dataset contains 1,020 seeded games from the toy research path and
> regenerates byte-for-byte with its original configuration. Its Observe on/off
> comparison used the same legacy `ProbAwareAgent` in both arms, but that agent's
> heuristic includes chance-weighted material, normalized progress, and chance-weighted
> rollout sampling. The comparison is therefore not an uncertainty-only test of the
> whole agent against a classical baseline. The reported win-rate difference includes
> zero. See [`docs/REPORT.md`](docs/REPORT.md) and
> [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for the archived study boundary.
>
> **Licence: confirmed AGPL-3.0** for upstream Cheqqers (see
> [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) §8). No upstream code is copied
> or integrated.
>
> The source paper was read in full (arXiv:2506.05962v2, accepted to CoG 2025). The
> follow-up literature search was narrow, not systematic; no field-wide novelty claim
> is made. The hosted deployment's engine revision has not been verified against the
> current local source, so these local-engine notes do not assert what the public site
> is currently running.

## Setup

Python 3.10 or newer. Install the full Python environment, including the local quantum-circuit simulator:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No GPU, quantum hardware, or Colab setup is needed. The game client is a Next.js app;
the static viewer and fallback client in `viewer/` have no build step.

## Running

### Tests

```powershell
python -m pytest
```

Python tests cover both engines, archived experiment replay, paper-level transitions,
agent legality and determinism, branch-cap behavior, the server protocol, and the
separate Qiskit circuits. See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the latest recorded
verification count. Passing tests establish implementation behavior, not paper-wide
conformance or a winning strategy.

### Baseline batch

```powershell
python scripts/run_baseline.py --condition classical-mcts-vs-random -n 12
python scripts/run_baseline.py --condition quantum-observe-vs-random -n 12 `
    --replay results/replay_sample.json
```

These commands run the **archived toy-engine study path**; they do not benchmark the
current PaperQuantumEngine or live MCTS. They write `results/<condition>.jsonl` and print
rates with 95% Wilson intervals plus a games-per-second measurement (Gate 4). Available
conditions: `classical-random-vs-random`,
`classical-mcts-vs-random`, `quantum-observe-vs-random`, `quantum-prob-vs-random`.

### Ablation

```powershell
python scripts/run_ablation.py --agent-a prob --agent-b random -n 12
```

Runs two conditions with **matched seeds and a matched opponent**, then prints a
side-by-side rate table and per-metric difference intervals. Prints no p-values, and
warns when the batch is below the brief's 170-games-per-condition target.

### Plots

```powershell
python scripts/make_plots.py
```

Reads the four registered baseline logs and two registered ablation logs (gameplay logs
are excluded) and writes four PNGs to `results/plots/`: win/draw rates with Wilson
intervals, collapse frequency, game-length distribution, and quantum-move usage. Every
figure states its sample size and carries a provenance footer. Submission copies are in
`docs/figures/`.

### Verification of logged results

```powershell
python scripts/verify_results.py --json results/verification.json
```

Rebuilds the engine, both agents, the board size and the ply cap from **each log line
alone**, replays the game, and requires the regenerated line to be byte-identical. It also
restates each batch's rates with sample sizes, refuses a record at a level the batch runner
is forbidden to log, and separates human-played game-client records (not seed-regenerable)
from experiment records. Exit status 0 verified, 1 a check failed,
2 nothing to verify. Current state: **1020/1020 experiment records regenerate
byte-for-byte**.

### Demo seeds

```powershell
python scripts/make_demo_seeds.py
```

Writes three replay payloads the demo and the viewer load: `demo-classical.json` (toy
level 0), `demo-observe.json` (an archived toy level-2 game in which voluntary
measurement fires) and
`demo-decoherence.json` (a level-4 game in which a piece runs out of coherence and collapses
by itself — a *single* game, because a level-4 batch is forbidden by design). The two
logged demos are records from the batches, not re-runs.

### Replay viewer

```powershell
python scripts/run_baseline.py --condition quantum-observe-vs-random -n 12 `
    --replay results/replay_sample.json
```

Then open `viewer/index.html` in a browser and load `results/replay_sample.json`
(or a raw `.jsonl` log — the first record is used). Step through turns with the arrow
keys, space to play, Home/End to jump. Collapse turns are marked on the board and in the
timeline, and the selected turn's pre-collapse chances are shown with the sampled square
marked. The viewer displays **occupancy chances only**: whether the published game uses
amplitudes and phases is unverified, so the viewer says so rather than implying they
exist.

### Playable game (server + client)

Two processes. Terminal 1:

```powershell
python -m server            # http://127.0.0.1:8000
python -m server --host 0.0.0.0 --port 8000   # LAN play
```

Terminal 2 — the web client:

```powershell
cd client
npm ci
npm run dev                 # http://localhost:3000
```

It talks to the server over fetch + WebSocket on `127.0.0.1:8000` (the server allows
cross-origin requests because there are no credentials). Point it elsewhere with
`NEXT_PUBLIC_API_URL`.

Screens: landing → new game (stage, opponent, optional seed and board size) → board.
The board shows ghost pieces with an occupancy chance per square, highlights the legal
targets the *server* sent, and reveals a collapse as it happens. The client never
decides legality: a refused move comes back as an `Error` and is shown, never applied.
At 720p the whole board and every action fit on one screen without scrolling.

The primary game client is the Next.js app in `client/`. `viewer/game.html` is a maintained
static alternative that can be opened straight from disk; `viewer/index.html` is the replay
viewer.

The local paper-rules client exposes Levels 0–3 from the paper-based engine. Level 4 is
the project's custom decoherence and voluntary Observe extension; `Observe` is not an
optional action at Levels 0–3. The `PaperQuantumEngine` runs the complex-amplitude state
on the CPU. When hardware sampling is configured, IBM Quantum supplies a collapse sample
only; it does not hold or evolve a persistent board state. See
[`docs/RULE_CONFORMANCE.md`](docs/RULE_CONFORMANCE.md) for exact boundaries. The hosted
deployment's version has not been checked against this local source revision.

Optional: set `DISCORD_WEBHOOK_URL` before starting the server and game creation and
game-over post a compact embed. Unset means the hook is off and games are byte-identical;
the send is fire-and-forget, so a slow or dead endpoint cannot delay or fail a game.

The frozen wire contract is in [`docs/PROTOCOL.md`](docs/PROTOCOL.md); the server
resolves every message against the selected engine's `legal_actions`, so there is one
authoritative rules implementation per room.

The separate circuit demo uses Qiskit and local Aer simulation; these circuits demonstrate
superposition, measurement and phase dependence but are not integrated into the game engine.
Run `python -m qcheckers.quantum` for the demo. With no IBM key it uses local Aer;
with `QISKIT_IBM_TOKEN` configured and `requirements-ibm.txt` installed it attempts
IBM Quantum, falling back to Aer if unavailable. The CLI labels the backend used. This
standalone circuit demonstration is separate from the CPU-held game state and from the
optional live collapse sampler.

The game's Music toggle controls a CC0 ambient loop independently of sound effects;
see [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md) for the source and license.

The reproducibility report and gate record is
[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) — paper version read, environment pin,
reproduction boundary, the six kill-test gates with their evidence, the ablation
definitions and sample sizes, the mismatch list against the paper's rules, and the licence
constraint (upstream Cheqqers is **AGPL-3.0**; none of its code is copied here).

For the current paper-based engine and its implementation limits, see
[`docs/RULE_CONFORMANCE.md`](docs/RULE_CONFORMANCE.md). Practical level-by-level advice
is in [`docs/STRATEGY.md`](docs/STRATEGY.md); the search implementations are explained in
[`docs/AGENTS_EXPLAINED.md`](docs/AGENTS_EXPLAINED.md).

Browser acceptance check (needs `pip install playwright` and
`playwright install chromium`):

```powershell
python scripts/check_current_client.py --site http://localhost:3000 --api http://127.0.0.1:8000
python scripts/check_deployment.py --site http://localhost:3000 --api http://127.0.0.1:8000
python scripts/capture_report_screenshots.py --site http://localhost:3000
```

These checks target the current Next.js client and paper engine. The older
`scripts/browser_check.py` covers the historical static-client acceptance flow; its
57-check result is archived evidence, not a current Next.js validation result.

## Directory map

```text
qcheckers/
  engine/         GameEngine protocol, value types, and engines
    protocol.py     Person A -- types and the GameEngine contract
    toy.py          Frozen 4×4 probability-only research engine for archived runs
    paper.py        Sparse complex-amplitude local gameplay engine, Levels 0–4
  agents/         Decision-makers
    base.py           Person B -- Agent protocol
    random_agent.py   Person B -- seeded uniform-random baseline
    mcts_baseline.py  Frozen toy-engine MCTS used by archived runs
    live_mcts.py      UCT state tree for the local paper-based game
    observe_agent.py  Frozen toy-research Observe agent
    prob_aware.py     Frozen toy-research probability-aware search
  quantum/        Qiskit/Aer circuit demonstration, separate from game rules
  experiment/     Logging, statistics, configuration
    schema.py         Person B -- GameRecord/TurnRecord, JSONL contract
    runner.py         Person B -- seeded play(), JSONL write/read
    stats.py          Person D -- Wilson interval, rate comparison, summarize()
    config.py         Person D -- conditions, seeds, sample-size target
  viz/
    replay.py         Person E -- GameRecord -> replay payload (pure function)
client/           Primary Next.js game client (see client/README.md)
server/
  app.py          P5 -- FastAPI REST + WebSocket surface (docs/PROTOCOL.md)
  rooms.py        P5 -- in-memory rooms, seats, engine-authoritative move resolution
  notify.py       P5 -- optional Discord hook; unset means off, never blocks a game
scripts/
  run_baseline.py    Person B -- run one condition, write JSONL, print intervals
  run_ablation.py    Person D -- two matched conditions, rates + difference intervals
  make_plots.py      Person D -- PNGs from JSONL, every figure states its n
  browser_check.py   P4 -- Playwright acceptance check for the game client (optional)
viewer/            Static game alternative and replay viewer, no build step
  index.html, viewer.js, styles.css   replay viewer for logged games
  game.html, game.js, game.css        playable game client (server-authoritative)
tests/             Deterministic unit checks (see ownership in docs/TEAM.md)
notebooks/         Colab quickstart notes (no notebook deliverable yet)
docs/
  quantum-checkers-project.md   The authoritative project brief (do not edit casually)
  TEAM.md                        Five-person split, file ownership, dependency graph
  PROTOCOL.md                    FROZEN REST/WebSocket contract and engine scope
  RULE_CONFORMANCE.md            Paper-level mapping and implementation caveats
  STRATEGY.md                     Practical, unproven level-by-level strategy notes
  AGENTS_EXPLAINED.md              Frozen research agents and current live MCTS
results/           Generated logs and plots (git-ignored except .gitkeep)
```

The toy engine, agents, runner and statistics use only the Python standard library. The
full environment also installs `numpy` and `matplotlib` for analysis, `qiskit` and
`qiskit-aer` for the separate circuit demonstration, and FastAPI/Uvicorn for the game
server. The Next.js client has its own locked npm dependencies in `client/package-lock.json`.

## Engine levels

For the local `PaperQuantumEngine`, Levels 0–3 follow the paper's incremental game
mechanics. Level 4 is the custom project extension. The archived `DeterministicToyEngine`
uses a different historical stage mapping for its experiments; see
[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) and
[`docs/RULE_CONFORMANCE.md`](docs/RULE_CONFORMANCE.md).

| Level | Local paper-engine mechanic |
| --- | --- |
| 0 | Classical English draughts: compulsory captures, capture chains, promotion and quiet-move draw rule. |
| 1 | Equal-amplitude split moves; split parts can move and split again; capture can trigger measurement. |
| 2 | Adds correlated capture branches that implement the paper's entanglement rule. |
| 3 | Adds same-original-piece merge and phase-sensitive interference. |
| 4 | Custom project extension: decoherence timer and voluntary `Observe`; not a paper level. |

In `PaperQuantumEngine`, `allow_observe` is derived from the level and is true only at
Level 4. The archived toy experiment engine has its own `allow_observe` option; that is
how the historical on/off comparison was configured. Do not conflate the two engines or
their level mappings.

## Determinism

Random streams are explicitly seeded per engine and agent. The CPU paper engine stores
complex amplitudes deterministically and uses its seeded RNG for local measurement
sampling when no external sampler is configured; a configured IBM sampler is an explicit
live exception. Archived `play(engine, agents, seed)` runs remain reproducible with their
recorded toy-engine parameters, so `(seed, condition)` in a log line is enough to
regenerate that log line byte for byte. This does not make archived toy results
comparable to the paper engine.

## References

- Raat et al., "Quantum Checkers: The Development and Analysis of a Quantum Combinatorial
  Game," 2025 IEEE Conference on Games.
  DOI [10.1109/COG64752.2025.11114278](https://doi.org/10.1109/COG64752.2025.11114278)
- Wilson, E.B. (1927). Probable Inference, the Law of Succession, and Statistical
  Inference. *JASA* 22(158), 209–212. — the interval used throughout
- Newcombe, R.G. (1998). Interval estimation for the difference between independent
  proportions. *Statistics in Medicine* 17(8), 873–890. — the difference intervals
- Battle-CP ([github.com/Prajwal-k-tech/Battle-CP](https://github.com/Prajwal-k-tech/Battle-CP))
  — design language of the game shell (flow, HUD, status strip), recreated in original
  CSS with the author's written permission; see [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md).
