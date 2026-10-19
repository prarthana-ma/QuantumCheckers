# Quantum Checkers — team split, timeline and progress

> **Planning record, not live status.** The roles, schedule and original open-item list below describe the project plan. For current delivery status, verified test counts, and gate results, see [`HANDOFF.md`](HANDOFF.md) and [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md). The final report is in [`REPORT.md`](REPORT.md), with slides in [`SLIDES.md`](SLIDES.md).

Five roles, **P1–P5**. The initial scope proposal is [`docs/quantum-checkers-project.md`](quantum-checkers-project.md); this file is the historical map of roles, schedule, ownership, and report responsibilities.

**Source paper:** M. Raat, L. van den Nouweland, M. Müller-Brockhausen, M. Preuss, E. van Nieuwenburg, *"Quantum Checkers: The Development and Analysis of a Quantum Combinatorial Game,"* 2025 IEEE Conference on Games. DOI: https://doi.org/10.1109/CoG64752.2025.11114278 · Preprint: https://arxiv.org/abs/2506.05962 · Code: https://github.com/raatmarien/cheqqers · Playable: https://cheqqers.com

**Non-negotiable rules from the brief**

- Every role owns code or measurement. No role is writing-and-presenting only.
- Each person writes their own methods and limitations section; one person assembles, and assembly is extra, not the whole role.
- **No one changes core rule logic except P5.**
- **No one edits `Observe` logic except P1.**
- **P2 rejects any plot that cannot be regenerated from logged seeds.**
- Integration ownership rotates weekly so no single person becomes the bottleneck.

Source files name their owner in the module docstring. Where a docstring and this file disagree, this file wins and the docstring is the bug.

---

## Roles at a glance

| Person | Lane | Main responsibility |
| --- | --- | --- |
| **P1** | Agents, experiment design and research direction | The agent framework and every agent except the random baseline — MCTS, `Observe`, probability-aware — plus the ablation specification, novelty verification and the contribution statement |
| **P2** | Statistics and figures | Metric definitions, Wilson intervals, sample-size justification, experiment configuration, every figure and table |
| **P3** | Verification, interpretation and reproducibility | Seed registry, `verify_results.py`, result interpretation and the results section, the random baseline agent, replay payload export, demo seeds, pinned environment, licence conclusion, the limitations log, Gate 6 check |
| **P4** | Frontend and delivery | The replay viewer in the browser (`viewer/` HTML/CSS/JS), interactive figures, report, slides, demo script, related-work and originality table |
| **P5** | Rules, engine, harness and batches | Rules and engine, adapter, seeded runner, JSONL format, batch configs, pilot and full batch execution, games-per-hour, test suite |

**Code role tags.** Module docstrings name roles "Person A–E" and point here. The correspondence is: **A** (rules and engine) → P5, **B** (harness and baselines) → P5 for the harness, P1 for the search agents and P3 for the random baseline, **C** (`Observe` and probability-aware search) → P1, **D** (statistics and plots) → P2, **E** split in two: the replay payload and reproducibility side (`viz/replay.py`) → P3, the browser viewer (`viewer/`) → P4. **P3 emits the replay payload, P4 renders it.**

---

## What to read in the paper, and by whom

| Section | What it contains | Primary readers |
| --- | --- | --- |
| Abstract, I | Motivation: quantum intuition for non-experts, Piispanen's three dimensions of a "quantum game", why checkers sits between tic-tac-toe and chess | P1, P4 |
| II | Related work: Dorbec–Mhalla framework, Burke et al. "quantum flavour D" (classical moves always legal), Quantum Chess, quantum minesweeper, quantum tic-tac-toe / TiqTaqToe levels | P1, P4 |
| III-A | Classical English Draughts: setup, forward-diagonal movement, crowning, forced and multi-capture, 40-move draw rule | P5, P3 |
| III-B | **Level 1** — split move (50/50), re-split halving the share, measurement, and the three capture-triggered measurement cases | P1, P5, P3 |
| III-C | **Level 2** — entanglement: a capture attempt on a split piece entangles both pieces instead of measuring | P1, P5, P3 |
| III-D | **Level 3** — merge move, phase rotation, constructive/destructive interference | P1, P5, P3 |
| IV, IV-A | Implementation: Python + `cirq`, only superposed squares simulated quantum mechanically, smallest circuit built at measurement time, one code base for all levels | P5, P3 |
| IV-B | Web UI: per-square occupancy chance display, arrow buttons for split/merge; **phase visualisation not implemented** (stated as future work) | P4, P3 |
| V | The four agents: random, and MCTS low/medium/high (200/400/800 rollouts, `c = 2√2`) | P1, P2 |
| VI-A | Experiment 1 — complexity: 1000 random-vs-random games per board size and level, draw-rate effect of the 40-move rule | P2, P5 |
| VI-B | Experiment 2 — MCTS vs random on 5×5 over 100 games, as white and as black | P2 |
| VI-C | Experiment 3 — TrueSkill tournament, 5×5 (300 matches) and 8×8 (96 matches), μ = 25 / σ = 25/3 | P2 |
| VII | Conclusion and the stated open problems we build on | P1, P4 |
| Appendix | One qubit per square, `\|10⟩ → i\|01⟩` phase rotation, √iSWAP split, merge as its inverse, factorisation into independent square groups | P1, P5 |

**Two facts from the paper that define our contribution** (read these before writing any novelty claim):

- **§III-B2/B3:** measurement happens *only* when a capture is attempted — three cases, all capture-driven. No rule anywhere lets a player choose to measure a piece, so the voluntary `Observe` action is not part of the published game.
- **§VII:** the authors write that their MCTS "simply averages over the rollouts, but future work could include more clever choices of averaging based on the piece probabilities", and suggest heuristics for node selection. Our probability-aware search answers an open problem the paper states directly.

Both still have to be verified against the repository's paper-version tag, tournament submissions and follow-up literature (Gate 5) before they are claimed anywhere.

---

## Files each role owns

| Person | Files |
| --- | --- |
| **P1** | `qcheckers/agents/base.py`, `qcheckers/agents/mcts_baseline.py`, `qcheckers/agents/observe_agent.py`, `qcheckers/agents/prob_aware.py`, the `Observe` action definition, `scripts/run_ablation.py`, the ablation specification, `tests/test_agents.py` except the random-baseline cases |
| **P2** | `qcheckers/experiment/stats.py`, `qcheckers/experiment/config.py`, `scripts/make_plots.py`, `tests/test_stats.py` |
| **P3** | `qcheckers/agents/random_agent.py`, `qcheckers/viz/replay.py`, `qcheckers/viz/__init__.py`, `scripts/verify_results.py`, the seed registry, `notebooks/`, pinned environment, the random-baseline cases in `tests/test_agents.py`, the replay half of `tests/test_schema.py` |
| **P4** | `viewer/index.html`, `viewer/viewer.js`, `viewer/styles.css`, interactive figure exports, report, slides, demo script, related-work and originality table, `docs/` |
| **P5** | `qcheckers/engine/protocol.py`, `qcheckers/engine/toy.py`, `qcheckers/engine/adapter.py`, `qcheckers/engine/__init__.py`, `qcheckers/experiment/schema.py`, `qcheckers/experiment/runner.py`, `scripts/run_baseline.py`, `tests/test_runner.py`, batch configs and batch entry points |

Shared — say so in the group chat before editing: `pytest.ini`, `requirements.txt`, `.gitignore`, `docs/TEAM.md`.

---

## Dependency graph

```text
Gate 2 (upstream paper-version tag)   Licence check (AGPL-3.0 suspected)
            |                                    |
            v                                    v
[P5] engine + adapter + JSONL schema   (freezes end of Day 2)
            |
      +-----+------------------+
      |                        |
      v                        v
[P1] three agents + base      [P2] statistics + figures
      |                        |
      +-----------+------------+
                  v
      [P5] pilot + full batches   (P3 verifies, P4 builds viewer shell in parallel)
                  |
        +---------+----------+
        v                    v
[P2] figures from       [P4] replay frontend
     frozen logs              |
        \                     /
         +---------+---------+
                   v
        report + demo + reproducibility report
```

Critical path: **P5 → P1 agents + P2 statistics → P5 pilot batch → P3 verification → P2 figures → P4 report and demo.**

If P5 slips, P1, P2, P3 and P4 work against mocked interfaces and re-integrate once the interface freezes. `qcheckers.engine.protocol` is that interface: it is written to be stable, and `CheqqersAdapter` shows the shape the upstream engine must take.

---

## Timeline and start order

Aligned to the kill test and the five-week plan in the brief (§16 and §19). This assumes the kill test passes; if it fails, follow the fallbacks in §18 instead of stretching the schedule.

### Day 1–2 — kill test. Everyone starts; nobody waits.

| Who | Starts with | Why it can start now |
| --- | --- | --- |
| **P1** | Gate 5: full-paper follow-up and tournament overlap search for voluntary measurement and probability-aware play; Gate 1: open the DOI; finish `MCTSBaselineAgent._rollout` | The gates are reading-only, and the rollout runs against the stable `GameEngine` contract |
| **P2** | Start the sample-size and interval-width calculation | Engine-independent statistics work |
| **P3** | Gate 6: confirm the `Observe` stub runs in a test game; create the seed registry and the `scripts/verify_results.py` skeleton; read the upstream licence directly | The stub exists and is tested; seeding and the licence check are independent |
| **P4** | Build the viewer shell — `viewer/index.html`, `viewer.js`, `styles.css` — against a hand-made mock replay payload; start the related-work and originality table | Frontend needs the payload shape, not the engine; the literature pass needs no code |
| **P5** | Gate 2: pin the upstream commit/tag and read the licence; Gate 3: one headless upstream game; Gate 4: measure games per hour; define the batch config format | Owns the engine, the harness and every later batch run |

**Unblock event:** P5 freezes the JSONL log schema at the end of Day 2. P2, P4 and P3 build against logs from that moment.

### Week 1 — verify and freeze

- P1 freezes the ablation specification (conditions, board sizes, seed list, sample size, metrics, stopping rule) and completes the MCTS baseline.
- P5 finishes the engine layer, adapter and legality test suite, and freezes the batch config format.
- P2 freezes the metric definitions and the sample-size calculation.
- P3 owns and completes the random baseline agent, freezes the seed registry and the replay payload export from JSONL.
- P4's viewer shell renders the mock payload end to end: board, occupancy percentages, step and play controls.
- **First team commit lands at the end of Week 1**, carrying the gate record.

### Week 2 — reproduce small

- P5 finishes the runner and the JSONL log format.
- P5 runs the first small batch end to end; P3 checks it through `scripts/verify_results.py`.
- P2 reproduces one paper experiment at small scale and one baseline comparison.
- P1 lands a first working version of the probability-aware search.
- P4 switches the viewer from the mock to real replay payloads, and starts the report skeleton.

### Week 3 — build the new condition

- P1 completes the extension agents and freezes the experiment specification.
- P5 runs the pilot batch; P3 verifies its logs and P2 reports variance, games per hour and Wilson interval widths.
- P4 gets the collapse step-through working: play, pause, step, and the before/after highlight of a measured square.
- P5 holds the harness stable — no interface changes from here on.

### Week 4 — run the controlled batch

- P5 runs the full batch: at least 170 games per condition if the pilot justifies it, otherwise a stated pilot, fixing harness bugs as they appear.
- P2 generates every figure and table from frozen logs.
- P3 interprets results against the research question and drafts the contribution claim; P1 checks the draft against the novelty verification.
- P3 selects and exports the demo seeds; P4 turns them into the demo page.
- P4 embeds the interactive figures in the report and keeps it current as results land.

### Week 5 — harden and report

- P5 completes tests and the separation between reproduced and new code.
- P4 finishes the viewer, the report, the slides and the demo script — the submission package.
- P3 gets `verify_results.py` green against every published number, plus the pinned environment, the licence conclusion and the limitations log.
- P3 writes the results section, P1 writes the contribution statement, every person files their own methods and limitations paragraphs, and P4 assembles the report.
- P2 freezes the logs and the figures.

**Buffer rule:** if a week slips by more than two days, cut viewer polish first, then reduce the full batch to a justified pilot. Never cut logging, confidence intervals or the limitations sections.

---

## What is done so far

**Status as of 9 October 2026.** The live record is
[`docs/REPRODUCIBILITY.md`](REPRODUCIBILITY.md) (gate record, ablation table,
mismatches, limitations, regeneration commands); this section is the summary.
Check the code and the `TODO` markers before writing anything — a lane may already
have a head start.

### Done

- **Paper read in full**, all sections plus the appendix. The two anchors above are recorded from §III-B2/B3 and §VII.
- **Initial project brief** — `docs/quantum-checkers-project.md`, 21 sections including the FAQ, kill test and fallbacks. It is retained as the planning brief, not current status.
- **This team split**, with reading assignments, ownership, timeline and progress.
- **README rewritten** around the research question, with a status banner reconciled to the verified records (toy-engine numbers only, AGPL-3.0 confirmed with no upstream code copied, novelty pending-form).
- **Dependencies cleaned:** PennyLane and SciPy were removed with the earlier project. The current project also includes FastAPI/Uvicorn, Qiskit/Aer and the Next.js client; see the root requirements and client lockfile.
- **Package in place and importable:** `qcheckers.engine` (`protocol.py`, `toy.py`), `qcheckers.agents` (`base`, `random_agent`, `mcts_baseline`, `observe_agent`, `prob_aware`), `qcheckers.experiment` (`schema`, `runner`, `config`, `stats`), `qcheckers.viz` (`replay`).
- The 12 October snapshot had **270 tests**; see `HANDOFF.md` for the current test count.
- **Game protocol frozen** (`docs/PROTOCOL.md`): REST rooms plus WebSocket moves, JSONL log schema, reconnect semantics. The primary game client is Next.js (`client/`); a static alternative remains in `viewer/`.
- **Batches run:** four conditions at n=170 (classical-random, classical-MCTS, quantum-observe, quantum-prob, all vs random) plus a matched observe-on/off ablation at 170 per arm. `scripts/verify_results.py` reports **1020/1020 records regenerating byte-for-byte**; `scripts/browser_check.py` is **57/57** through the real UI.
- **Demo seeds exported** (`scripts/make_demo_seeds.py`): level-0, level-2 with Observe firing, level-4 expiry.
- **Gates 1–6 recorded** in `docs/REPRODUCIBILITY.md` §4 — no gate failed, so no fallback triggered. Gate 2's tag is confirmed present but the upstream engine is deliberately **not** integrated (AGPL-3.0 copyleft vs course-pilot scope; decision recorded in `docs/REPRODUCIBILITY.md` §4). Gate 5's follow-up search was narrow, so novelty stays pending-form.
- **Scripts in place:** `scripts/run_baseline.py`, `scripts/run_ablation.py`, `scripts/make_plots.py` (5 figures, each stating its n), `scripts/make_demo_seeds.py`, `scripts/verify_results.py`, `scripts/browser_check.py`, plus `notebooks/`.
- **Statistics layer already provides** `wilson_interval`, `compare_rates` and `summarize`.
- **Course submission text drafted** — title, abstract and five verified references for the IEG 313 title-and-summary form.

### Remaining research limitation

- **Novelty hardening:** the follow-up search must become systematic before anything is published as a new contribution.
- **Unevaluated game-only levels:** levels 3 and 4 are playable but out of study scope.

---

## Original gate checklist (historical)

| # | Original item | Original blocker | Current status |
| --- | --- | --- | --- |
| Gate 1 | DOI resolves to the correct publisher page | The whole project | **Passed**; see `REPRODUCIBILITY.md` §4 |
| Gate 2 | Upstream paper-version tag pinned | `CheqqersAdapter` | **Tag confirmed; engine intentionally not integrated** |
| Gate 3 | Headless game | Pilot batch | **Passed** through the batch runner; no notebook is part of the deliverable |
| Gate 4 | Games-per-hour measured | Batch size | **Passed**; throughput recorded in `REPRODUCIBILITY.md` §4 |
| Gate 5 | Full paper read + follow-up search for overlap | Any novelty claim | **Paper read; search narrow**, so novelty remains pending |
| Gate 6 | `Observe` prototype runs in a test game | P1's result | **Passed** in tests and playable client |
| Licence | Upstream licence read directly | Reuse, modification, redistribution | **AGPL-3.0 confirmed; no upstream code copied** |

**Kill rule (brief §16):** if two or more gates fail, stop the novel study and switch to a fallback in §18. Do not renegotiate the rule after the fact.

---

## Addendum pass — 9 October 2026

The addendum layered four things onto the plan above. All four are in the code, tested, and
recorded here rather than only in a commit message.

**A. Protocol samples.** `docs/PROTOCOL.md` gained a contract-first section (§0) with the
normative client→server and server→client shapes, adapted to the names the implementation
actually ships: `type` as the message tag, `chances` instead of a single collapsed square,
and seats rather than colour names in `GameOver`. Square fields accept `[row, col]` **or**
an algebraic string (`"c3"` = row 2, column 2). `StateUpdate` carries `coherence` (level 4
only) and the compact `last_event` aliases; `GameOver` carries `moves`, `seed`, `game_id`,
`level` and `mode`. The revision log at the bottom records what changed and that nothing
changed meaning for an existing level.

**B. Discord hook.** `server/notify.py`, reading `DISCORD_WEBHOOK_URL`. Unset means
disabled: no task is scheduled at all. On `GameCreated` and `GameOver` only, as a
fire-and-forget background task that swallows every exception, so a slow or dead webhook
cannot delay or fail a game. Tests cover the disabled path and a dead endpoint.

**C. Observe unlock beat.** The voluntary action is now a stage reward rather than an
always-on flag: the server switches `allow_observe` on for human seats from **stage 2**
(level 1 is the split alone; a level-1 spread piece can still be resolved by a capture),
and for the `ai-hard` tier at every stage. The client shows an explicit affordance —
selecting one of your own ghosts offers an **Observe** button that states it costs your
turn, and the collapse reveal plays itself once instead of waiting to be clicked — and
opening stage 2 for the first time shows an unlock note crediting voluntary measurement as
the team's mechanic. The Hard tier demonstrably spends turns on Observe in a played game
(`tests/test_agents.py`).

**D. Level 4 — decoherence (game-only).** Every split piece carries a visible coherence
counter (fresh splits start at 6; re-splitting refreshes it), each turn it is left
unmeasured ticks it down, and at zero the piece auto-collapses through the existing
level-1 measurement code, weighted by its current shares. No new simulation machinery.
Stages are now 0→4, the counter is rendered on the board, and the expiry opens the same
reveal inspector as any other measurement. The boundary is enforced in code, not by
convention: the rule ships behind `decoherence=True`, the engine refuses to build it at
any other level, `run_condition` refuses to batch level 3 **or** level 4, and the report
gets at most one honest paragraph calling it a game-only outreach mechanic that is
unevaluated.

**Acceptance.** `python scripts/browser_check.py` runs 57 checks through the real UI
across all five stages: a full Level-1 game to the result screen with zero console
errors, every stage's board and rule text, the refused-move path, the Observe affordance
and its reveal, the stage-4 coherence counter ticking down to an automatic expiry, and both unlock notes. The current test count is 270; see `HANDOFF.md`.

---

## Phase 4-5 record — 9 October 2026

**The paper is now read in full, and its anchor quote is verified.** The full text is on
arXiv as **2506.05962v2**, marked accepted to CoG 2025. §VII says the authors' MCTS
"simply averages over the rollouts, but future work could include more clever choices of
averaging based on the piece probabilities" — the open problem our probability-aware
rollout policy answers. The code repository carries a **`cog-paper-version`** tag (Gate 2
passes) and is **AGPL-3.0**, so it was read and never copied. Gate record:
1-6 all pass, with the follow-up search recorded as narrow rather than systematic.

**A real defect the verification found, and fixed.** `scripts/verify_results.py` replays
every logged game from nothing but the record. It failed on the search conditions because
the ply cap is a *terminal condition* the rollouts read, so a log that omits the cap cannot
be regenerated in general; `max_plies` is now part of the record. The same pass found that
both search agents chose the opponent's reply to **maximise** the root player's score —
modelling an opponent who cooperates. With the reply chosen adversarially, the
probability-aware agent goes from 0.876 [0.819, 0.918] to 0.976 [0.941, 0.991] against
random, which is what a search agent should look like.

**Batches at the brief's target.** Four conditions at **n = 170** each plus a matched
ablation at 170 per arm. Rate table and intervals are in
`docs/REPRODUCIBILITY.md` §5; the short version is that the ablation's *only* difference
excluding zero is the collapse rate (+0.700), which is true by construction, while the
win-rate difference is −0.006 [−0.046, +0.033] — a null result on the effect the project
cares about, reported as one.

**Verified, not asserted.** `python scripts/verify_results.py` reports **1020/1020
experiment records regenerating byte-for-byte**; the browser check is **57/57** through
the real UI including both new stages; Gate 4 measured **1984 / 56 / 1477 / 13.8
games-per-second** across the four conditions, so the 170-per-condition target costs
seconds, not hours.

**Demo assembled.** `scripts/make_demo_seeds.py` writes three replay payloads — a level-0
game, a level-2 game where voluntary measurement fires, and a level-4 game where a piece
expires on its own (a single game, because a level-4 batch is forbidden by design).

The nine mismatches between our engine and the paper's rules — obligatory captures,
crowning, the 40-move draw, the meaning of the levels, mobile split parts, the merge
semantics, amplitudes, board sizes and the MCTS budget — are tabulated with their
consequences in `docs/REPRODUCIBILITY.md` §7. They are the reason no number here is
presented as a reproduction of a paper figure.

---

## Working rules that keep the split workable

1. **Freeze early, freeze once.** The move interface, the JSONL format and the condition labels are frozen after the first pilot. Changing them later invalidates logs.
2. **Seed everything.** No global `random` anywhere. If a result cannot be regenerated from a seed, it is not a result. This is enforced by `tests/test_runner.py`.
3. **No result without an interval.** Point estimates alone are not reportable.
4. **Report null results.** The brief is explicit that a negative outcome is acceptable and more credible. Do not tune an agent until the number looks good.
5. **Mark what is unverified.** The brief labels almost everything UNVERIFIED. Do not upgrade a label without recording the check that did it, with a date and a source.
6. **Keep reproduced code and new code apart.** A reviewer must be able to see the boundary between the §10 reproduction and the §11 extension at a glance. That is why `Observe` and `prob_aware` live in their own modules under P1's ownership.
7. **Every claim carries a link**, and every published number regenerates from a seeded log by a documented command.
