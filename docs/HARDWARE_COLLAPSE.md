# Handoff — Live IBM Quantum hardware collapses

**Status: implemented and test-verified; NOT deployed and NOT run on hardware.**
These are different claims and are kept apart on purpose:

* **Implemented here:** the opt-in live-hardware path in this repository, exercised by
  `tests/test_hardware_collapse.py` against a **mocked** IBM boundary. That is evidence
  the wiring, mapping, failure handling and serialization are correct — it is *not*
  evidence about real hardware behaviour.
* **Deployment evidence:** the earlier deployment review recorded hardware sampling
  disabled. The public revision and its current configuration were not rechecked in
  the 15 October 2026 local review. No real QPU execution is claimed by this review.
  Enabling hardware is an operator action described in [`DEPLOYMENT.md`](DEPLOYMENT.md).

**Goal (bounded slice):** when live gameplay actually collapses a spread piece
(capture measurement, Level-4 Observe, or Level-4 decoherence expiry), the square written into game state must come
from one measurement shot submitted to IBM Quantum hardware, *when IBM credentials are
configured*. There is no simulator or RNG substitution on the live path: an unusable
bitstring or an unavailable service refuses the move. Research/offline use is unchanged.

## Ground rules honoured
- Existing uncommitted user changes are preserved (no reset/clean/overwrite).
- The upstream Cheqqers repo is AGPL-3.0 and is **not** copied or adapted.
- The research engine keeps its seeded RNG as the default sampler.

## Design decisions
1. **Injection point.** The current live `PaperQuantumEngine` accepts an optional
   sampler for its piece projection; the legacy `DeterministicToyEngine` also retains
   its sampler seam for compatibility. Without a sampler the seeded local RNG resolves
   measurements. Engine `clone()` deliberately **drops** the sampler, so agent rollouts
   never submit QPU jobs. The persistent complex board state evolves on the CPU; the
   hardware circuit samples a selected piece's measurement distribution only.
2. **Circuit encoding.** `qcheckers/quantum/game_measure.py` builds a measurement
   circuit from a piece's `(square, chance)` sites: one qubit per bit needed for the
   candidate count, amplitude `sqrt(chance)` per basis state, measured. The
   basis-state index -> square mapping uses `|00>`=site0, `|01>`=site1, `|10>`=site2.
   Supports variable candidate counts. Live collapses enforce exactly one shot and a
   positive finite timeout. Invalid hardware configuration returns a clear HTTP 503
   when a room is created, with no partial room stored; provider failures during play
   preserve the existing board.
3. **Invalid/noisy outcome policy (refusal, no substitution).** One shot on real
   hardware can return a basis state that maps to no candidate square (for example the
   unused `|11>` state, or a noisy outcome). The move is then refused with error code
   `quantum_invalid_outcome`; the game state is unchanged. Nothing is substituted --
   no highest-weight choice, no simulator, no RNG.
4. **Provenance.** The room records the backend name, job id, raw bitstring, sampled
   square, probability and candidate sites for the last hardware collapse and exposes
   them on the state view (`quantum` field) and on the collapse event as the browser
   sees it. No credential ever enters a payload or a log.
5. **Liveness.** The blocking IBM wait runs in a worker thread (`asyncio.to_thread`)
   under a per-room `asyncio.Lock`, so the FastAPI loop stays free and two players can
   never apply concurrent moves to the same room. A `quantum_pending` flag in the view
   drives the client's pending indicator.
6. **Failure.** A missing key/instance/backend or a failed/timed-out job raises
   `QuantumMeasurementError` (error code `quantum_unavailable`); an unusable bitstring
   is refused with `quantum_invalid_outcome`. The engine raises before any state is
   constructed, so the room is untouched and the socket gets a clear `Error` frame.

## Initial integration file list (historical)
- NEW `qcheckers/quantum/game_measure.py` — circuit from sites, bitstring policy.
- NEW `server/quantum_measure.py` — IBM sampler, provenance, error type.
- MOD `qcheckers/engine/toy.py` — optional `sampler` + clone drops it.
- MOD `server/rooms.py` — sampler wiring, pending + provenance in `view`.
- MOD `server/app.py` — per-room lock, off-loop move, error/pending frames.
- MOD `client/types/game.ts`, `client/hooks/useGameSocket.ts`,
  `client/components/game/GameScreen.tsx` — UI + `QuantumPending` frame.
- MOD `requirements-server.txt`, `.env.example`, `docs/DEPLOYMENT.md`, `docs/REPORT.md`.
- NEW `tests/test_hardware_collapse.py` — initial provider-boundary tests; expanded in the final local review.
- NEW `client/components/game/errorLifetime.ts` + `client/tests/errorLifetime.test.mjs`
  — client error visibility.
- MOD `docs/PROTOCOL.md`, `docs/REPORT.md`, `docs/DEPLOYMENT.md`, `docs/HANDOFF.md`,
  `docs/REPRODUCIBILITY.md`, `README.md`, `docs/TEAM.md`, `docs/SLIDES.md`.

## Review fixes in this pass
1. **Resign serializes with a hardware-backed move.** `Resign` used to bypass the
   per-room lock, so another connection could finalize the game while a collapse was
   blocked in a QPU measurement and the blocked move would still commit afterwards.
   Every room mutation now goes through `app.state.run_room_mutation` (client move, agent
   ply, resign), and the lock covers the mutation only — never the broadcast that follows
   it, so a slow socket cannot extend a hardware wait. Two regression tests: a
   WebSocket-level one and a deterministic `asyncio` one over the lock itself.
2. **Hardware errors stay visible.** The server sends `Error` then the *unchanged*
   `StateUpdate`; the client used to clear its error on every state update, hiding the
   failure. `resolveErrorAfterStateUpdate` keeps an error alive until the board actually
   moves on, with `client/tests/errorLifetime.test.mjs` covering the sequence.
3. **Deployment status is accurate** — see `DEPLOYMENT.md`.
4. **Protocol documented** — `quantum`, `quantum_pending` and the `QuantumPending` frame
   are now in `PROTOCOL.md` §3.2.

## Verification (all green, re-run 12 October 2026)
- `python -m pytest` -> **270 passed**, exit 0 (was 268; this pass adds the two
  serialization regression tests).
- `npm run typecheck` (client) -> clean; `npm test` -> 6/6; `npm run build` -> compiled.
- `python -c` bit-check on Aer (test dependency): 3-site circuit reproduces 0.50/0.25/0.25 and 2-site
  0.50/0.50, confirming the `|00>`/`|01>`/`|10>` -> square mapping.
- WebSocket integration tests exercise the real interface: observe applies the hardware
  square with provenance; a failing IBM boundary returns an Error and leaves the board
  unchanged.
- The resignation regression was verified **both ways**: it passes with the lock and fails
  with the old bypass reintroduced ("resignation applied while a hardware measurement held
  the lock").

## Verification (all green)
- `python -m pytest` -> 268 passed, exit 0 (old HANDOFF.md records 249 before this
  feature; the new `tests/test_hardware_collapse.py` adds 19).
- `python -c` bit-check on Aer (test dependency): 3-site circuit reproduces 0.50/0.25/0.25 and 2-site
  0.50/0.50, confirming the `|00>`/`|01>`/`|10>` -> square mapping.
- `npm run typecheck` (client) -> clean.
- `npm run build` (client) -> compiled successfully.
- Two WebSocket integration tests exercise the real interface: observe applies the
  hardware square with provenance; a failing IBM boundary returns an Error and leaves
  the board unchanged.

## Deferred / known limitations
- **No real QPU job has been run.** `tests/test_hardware_collapse.py` mocks the IBM
  boundary (`server.quantum_measure._run_ibm_measurement`). Running a real hardware job
  still requires a valid `QISKIT_IBM_TOKEN`; no simulated output is labelled hardware output.
- No full-board quantum state; no entanglement or phase gameplay. Each collapse
  re-prepares a fresh circuit from the stored distribution; no qubit is "loaded"
  between turns.
- Concurrency correctness relies on the per-room `asyncio.Lock`. Serialization is now
  covered by the deterministic lock test and a bounded WebSocket check; it is not proven
  against arbitrary scheduling under production load.
- The client test runs under Node's experimental type-stripping (`npm test`); it is not
  part of the `tsc` typecheck pass.
- Stop before deployment (no cloud deploy, DNS or secrets changes were made).
