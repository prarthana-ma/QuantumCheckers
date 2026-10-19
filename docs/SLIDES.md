# Demo + defense slide outline (QCheckers, Team QuriousMinds, IEG 313)

Presenter notes under each slide. Numbers from `docs/REPRODUCIBILITY.md`; never
freestyle a number that is not in the report. Total: ~10 minutes.

---

## 1. Title — "Quantum Checkers: can you choose to look?"

*Say:* team, course, one line — we implemented quantum-checkers rules independently
and built a playable application. A separate archived toy-engine study evaluates
voluntary Observe with probability-aware search; its results do not evaluate the
current live game.

## 2. The game in 60 seconds (DEMO HOOK — play, don't tell)

Open the client, Stage 2 (engine Level 1). Split a piece, attempt a capture on a ghost, show the
collapse reveal. *Say:* pieces can stand on two squares at once; captures force the
universe to answer; a failed capture burns the whole turn.

## 3. Why this project

Laptops-only constraint, real published anchor (Raat *et al.*, IEEE CoG 2025, show
DOI), and the paper's own open problem — its MCTS "simply averages over the rollouts"
(verified §VII quote). Our archived experiment explores one related idea; it does not
establish a general improvement to quantum-game search.

## 4. What we built (architecture, one diagram)

Show two explicit paths: archived 4×4 `DeterministicToyEngine` → batch agents → logged
results; live `PaperQuantumEngine` → FastAPI/WebSockets → Next.js board with Live MCTS.
The server uses engine legal actions as its authority. Read current test counts and
browser results from `HANDOFF.md`; the historical 57-check result belongs to the static
client. The 1,020 experiment records regenerate from seeds.

## 5. Our two ideas

**Observe** — voluntary measurement, costs a turn; absent from the paper (capture-only
measurement, §III-B3). **Probability-aware search** — weight rollouts by occupancy
chance. Ablation: same boards, same seeds 0..169, one variable, n=170/arm, Wilson
intervals on everything.

## 6. Results (show the four plots)

Read the table aloud: ablation win-rate difference −0.006 [−0.046, +0.033] — includes
zero, a **null result, reported as one**. Only collapse rate moved (+0.700, mechanical).
Bonus honesty: observe-only agent loses to random (0.176) — spending turns looking
without cause spends tempo. Our MCTS beats random narrowly (0.547) at 24 iterations —
says nothing about the paper's 800-rollout player.

## 7. The game (DEMO — the fun half)

Play Stage 5 (engine Level 4): demonstrate Observe costing a turn, then an automatic
decoherence expiry. Observe is available only in this custom level and cannot bypass a
mandatory capture. Offer one game against Hard Live MCTS (400 simulations); do not
describe this agent as the archived probability-aware agent.

## 7a. The quantum is real (new)

The live engine evolves a sparse complex-amplitude board state on the CPU, including
relative phase and interference. It does not keep the board on a quantum processor.
Show the live 50/50 two-target split and Level 3 merge. The optional IBM path prepares
a selected piece's measurement distribution and samples one shot, then projects the
CPU state using that result. Agent simulations never submit QPU jobs.

The separate legacy Qiskit/Aer circuit demo uses a 0.50/0.25/0.25 three-site
distribution from the archived toy model. Its inverse-preparation experiment shows
phase effects but is not the live merge gate. No real hardware run is claimed without
a job record and observed result.

## 8. Limitations (read them, don't hide them)

Archived results: toy engine, 4×4, probability-only, no crowning or 40-move rule.
Live engine: supports promotion, compulsory captures, draw limits and complex
amplitudes, but has not been evaluated by the archived batches. Its split matrix
completion and promotion ancilla are documented implementation choices. Upstream
code is not integrated. The novelty search was narrow; the project does not establish
a new solved game or a proven winning strategy. Level 4 is a custom abstraction.

## 9. Close

Null on victories, yes on method: seeded everything, intervalled everything, verified
everything regenerates. The game teaches real quantum intuition — superposition,
measurement cost, entanglement, decoherence — to anyone who plays it. *Thank them.*

---

### Anticipated questions

- *"Why not use the authors' code?"* → AGPL-3.0 confirmed; copyleft obligations vs
  course-pilot scope; seam kept, decision recorded in `adapter.py`.
- *"Your MCTS is weak, so what?"* → Agreed — mismatch 9 is documented; our baseline
  calibrates our engine, never the paper's result.
- *"Observe lost — failed project?"* → No: the question was answered with intervals,
  and collapse-rate + tempo-cost findings are findings. Null is reportable.
- *"Is level 4 real physics?"* → Decoherence is real; our counter rule is a game
  abstraction, unevaluated, never batched. It says so on screen and in §7.
- *"Where is the actual quantum computing?"* → Complex amplitudes are simulated on
  the CPU in live play. Optional IBM hardware supplies a measurement sample for a
  selected piece; it does not evolve the persistent board. The Qiskit/Aer demo is a
  separate circuit artifact. Provider wiring is tested with mocks; this review does
  not claim a real QPU execution.
