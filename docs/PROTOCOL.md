# Game protocol — FROZEN

**Status: FROZEN.** This document is the contract between the Python server
(`server/`), both browser clients (`client/` and `viewer/`), and the JSONL logs. Client and server are
built *against this document*. Changing anything here after work has started invalidates
that work, so changes require a deliberate revision note at the bottom with a date.

Two hard rules from the governing brief sit on top of everything below:

* **C1 — single source of truth.** `qcheckers/engine` validates *every* move. The server
  never reimplements rules; the client never trusts its own state. A message here is a
  *request*; the engine decides.
* **C2 — browser transport.** Both clients use `fetch` and WebSocket and leave all game
  legality to the server. The primary client is Next.js (`client/`); `viewer/` also
  contains a static zero-build-step client and replay viewer.

**Engine scope (informative; wire contract unchanged).** The default local application
(`server.app.create_app(paper_rules=True)`) selects `PaperQuantumEngine`. Archived
experiment logs and replay verification use the separate `DeterministicToyEngine`.
Some normative sample values below retain `engine: "deterministic-toy"` to illustrate
that historical payload; the common message contract applies to either engine, while
`board` includes engine-specific metadata. See [`RULE_CONFORMANCE.md`](RULE_CONFORMANCE.md)
for the rules and state-model distinction. This protocol does not imply that the hosted
deployment has been updated to the current local source.

---

## 0. Normative wire samples (contract-first)

The shapes below are **normative**. The server emits exactly these and the client is
written against them, never the other way round; `tests/test_server.py` pins each field.
Names may be adapted where the implementation needed it (the adaptations are noted
under each sample), but this document governs both sides: changing a shape here is a
protocol revision (§7), not a client-side decision.

### 0.1 Client → server

Square fields accept either `[row, col]` — what the browser sends — or an algebraic
string: the letter is the **column** (`a` = 0) and the digit is the **row plus one**, so
`"c3"` is `[2, 2]`. Both forms are accepted everywhere a square appears (§3.1).

```json
{"type": "Move", "from": "c3", "to": "d4"}
{"type": "Move", "from": [2, 2], "to": [3, 3]}
{"type": "ObserveMove", "square": "c3"}
```

`Move` covers captures too (§3.1), and `ObserveMove` is legal only where the engine was
opened with `allow_observe=true` and the named square holds a spread piece.

### 0.2 Server → client

The `StateUpdate` JSON below is an **archived toy-engine example**: its
`engine: "deterministic-toy"` and 4×4 board do not describe the production local app.
The live paper-engine payload additions and action forms are specified in §0.3.

After every applied action, and to every seat and spectator:

```json
{"type": "StateUpdate",
 "turn": 1,
 "phase": "playing",
 "board": {"engine": "deterministic-toy", "level": 2, "board_size": 4,
           "allow_observe": true, "ply": 7, "turn": 1, "pieces": [], "captured": []},
 "occupancy": [[0.0, 0.0], [1.0, 0.0]],
 "coherence": {},
 "last_event": {"ply": 6, "piece_id": "C", "owner": 0, "cause": "capture",
                "chances": [[[2, 2], 0.5], [[3, 3], 0.5]],
                "sampled": [3, 3], "probability": 0.5,
                "kind": "collapse", "kept": [3, 3], "by": "capture"},
 "last_action": {"kind": "capture", "piece_id": "A", "origin": [2, 2], "target": [3, 3]},
 "legal": [], "you": 0, "ply": 7, "status": "playing"}
```

```json
{"type": "GameOver", "result": 0, "reason": "no_legal_moves",
 "moves": 87, "seed": 42, "game_id": "qk-3f9c1a2b", "level": 2, "mode": "ai-medium"}
```

### 0.3 Current local paper-engine profile

`server.app.create_app()` defaults to `PaperQuantumEngine`, whose render name is
`"paper-quantum"`. Its board has `paper_rules: true`; the live board payload does not
carry `toy_engine: false` (that provenance flag belongs to JSONL experiment/replay
records). The default board is 8×8, configurable from 4 through 16. Seat 0 is White,
starts at the bottom, and moves first. In the standard opening, seat 1's pieces begin at
the top. The client receives occupancy marginals and each piece's weighted `sites` and
`king_sites`; it receives no amplitude values or complex phases. The engine retains
those complex phases on the server.

Paper-engine board keys include:

| key | meaning |
| --- | --- |
| `engine` | `"paper-quantum"` |
| `paper_rules` | `true` |
| `branches` / `branch_count` | Number of exact joint configurations (aliases). |
| `pieces[].sites` | `[[[row,col], probability], ...]` marginal occupancy list. |
| `pieces[].king_sites` | Same weighted-list shape, restricted to branches where that piece is a king. |
| `pieces[].survival_probability` | Probability that the piece remains present. |
| `continuation_piece` | Original piece id required to continue a forced capture chain, or `null`. |
| `quiet_moves` | No-capture counter used for the 40-move draw. |
| `coherence_ticks` | Level-4 decoherence timer keyed by piece id; `{}` when disabled. |

The JSON in §0.2 remains useful for the common envelope, but a paper board's
engine-specific render has the fields above and `occupancy` from that same render.

Paper action messages use these forms (all squares are `[row,col]`; `piece` is an
optional original-piece id on `Move` and `ObserveMove` to disambiguate shared sites):

```json
{"type":"Move", "piece":"P0-1", "from":[5,2], "to":[4,3]}
{"type":"SplitMove", "piece":"P0-1", "from":[5,2], "targets":[[4,1],[4,3]]}
{"type":"MergeMove", "piece":"P0-1", "sources":[[4,1],[4,3]], "target":[3,2]}
{"type":"ObserveMove", "piece":"P0-1", "square":[4,1]}
{"type":"RetryAI"}
```

`SplitMove.targets` must be exactly the two legal destinations offered for that piece;
unlike the archived toy protocol, it is not an advisory distribution. A paper `MergeMove`
identifies two same-piece source branches and their common target. `ObserveMove` is
offered only at custom Level 4. `RetryAI` asks the server to retry a pending AI response
after a prior AI error; it does not advance the human move again. A capture chain counts
each jump as a separate `ply`, but `turn` remains with the capturing seat until the
forced chain ends. A paper no-capture draw reports `GameOver.reason: "forty_move_draw"`.

The production app explicitly uses a 1,000-ply cap. The 200-ply default on direct
`Room`/compatibility-registry construction is a fixture/compatibility default, not the
production app setting.

Field-by-field notes, including where a name differs from the compact sample style:

* `coherence` — **level 4 only**: ticks left before each split piece expires, keyed by
  the piece's origin square as `"row,col"` (`{"2,2": 4}`). Empty `{}` at every other
  level, so a client may render counters unconditionally. See §2.1 for the flag.
* `last_event` — `null`, or the most recent collapse. `sampled`/`cause`/`chances` are the
  event as logged; `kind` (`"collapse"`), `kept` (the square it resolved to) and `by`
  (the cause again, under the compact name) are aliases for the client's animation. The
  collapsed piece's **origin** is not a separate field: `chances` lists every square it
  could have been on, which is exactly what a reveal animation needs. Causes are
  `observe` | `capture` | `rejoin` | `join` | `decoherence`.
* `last_action` — the action just applied, or `null`. The move log renders this and never
  reconstructs an action itself.
* `GameOver.result` — the winning **seat** (`0` | `1`) or `null` for a draw; seats, not
  colour names, because the seat is what the record and the client both key on.
  `moves` is the final ply count, `seed` the engine seed, and `game_id`/`level`/`mode`
  are echoed so a client that reconnects after the end can still label the game.

---

## 1. Transport summary

| Purpose | Transport |
| --- | --- |
| Create a game | `POST /api/game` |
| Fetch current state | `GET /api/game/{game_id}` |
| Static board metadata for a game | `GET /api/game/{game_id}/view` |
| Play / receive updates | `WS /ws/{game_id}` |
| Liveness | `GET /api/health` |

The base URL can be localhost/LAN or the HTTPS Cloud Run service used by the hosted
client. Production sockets use WSS. The initial brief's local-only deployment scope
was extended at the user's request; message shapes are unchanged.

---

## 2. REST

### 2.1 `POST /api/game`

Request body (JSON):

```json
{ "level": 1, "mode": "ai-easy" }
```

* `level` — integer `0..4`. With `PaperQuantumEngine`, Levels 0–3 implement the paper's
  staged classical/superposition/entanglement/interference rules; Level 4 is the custom
  project decoherence/Observe extension. The archived `DeterministicToyEngine` uses a
  different historical stage mapping, and its batch runner refuses levels 3 and 4.
  Those archived batch restrictions do not define the live paper-engine rules.
* `mode` — one of:

  | mode | seat 0 | seat 1 | meaning |
  | --- | --- | --- | --- |
  | `local` | human | human | two humans, either may sit at this browser |
  | `ai-easy` | human | agent `random` | Easy tier |
  | `ai-medium` | human | live MCTS (200 iterations) with paper rules; legacy `mcts` with toy rules | Medium tier |
  | `ai-hard` | human | live MCTS (400 iterations) with paper rules; legacy `prob` with toy rules | Hard tier |
  | `online` | human | human | two browsers, join by code |

Optional fields: `"seed"` (int; the server draws one when omitted) and `"board_size"`
(int, default 8 in `create_app`; the archived toy-engine compatibility mode defaults
to 4).

For `PaperQuantumEngine`, `ObserveMove` is offered only at custom Level 4. Paper Levels
1–3 measure through their capture rules; level 3's `MergeMove` is an interference gate,
not a voluntary measurement. The historical toy engine exposes a separate Observe
flag for its archived ablation; it is not the paper-engine Level 4 rule.

Response `201` (created):

```json
{ "game_id": "qk-3f9c1a2b", "player_id": "p-7d21", "level": 1, "mode": "ai-easy", "seed": 42 }
```

`game_id` is the lobby code. `player_id` is the caller's seat token; the client stores
it and presents it in `JoinGame` to reclaim the same seat after a reconnect.

Errors: `422` for an out-of-range level/mode (FastAPI validation) — the server does not
invent a default.

### 2.2 `GET /api/game/{game_id}`

Returns the caller-independent current state view (see §4.1 `StateUpdate`), plus
`status` (`waiting` | `playing` | `over`). `404` if the game is unknown.

### 2.3 `GET /api/game/{game_id}/view?player_id=...`

Same as §2.2 but shaped as a **reconnect snapshot**: it is exactly the `StateUpdate` the
given player would receive on the socket (see §5).

### 2.4 `GET /api/health`

`{"status": "ok", "games": <int>}`.

---

## 3. WebSocket `ws://…/ws/{game_id}`

Text frames, one JSON object each. The connection must send `JoinGame` first; any other
message before a seat is held yields `Error` and is ignored. An unknown `game_id` closes
the socket with code `4404`.

### 3.1 Client → server

The table summarizes the shared command families and the archived compatibility forms.
For the exact production paper-engine payloads, including required two-square split
targets and same-piece merge sources, use §0.3. In particular, toy-engine split targets
and rejoin/merge shortcuts are not the paper-engine request format.

| `type` | fields | engine action it resolves to |
| --- | --- | --- |
| `JoinGame` | `player_id?` | — (seat assignment only) |
| `Move` | `from:[row,col]`, `to:[row,col]` | `MoveAction` **or** `CaptureAction` with `origin==from`, `target==to` |
| `SplitMove` | `from:[row,col]`, `targets?:[[row,col],…]` | `SpreadAction` for the certain piece on `from` |
| `ObserveMove` | `square:[row,col]` | `ObserveAction` for the spread piece occupying `square` |
| `MergeMove` | `pieces:[id,id]`, or `piece`/`from`, or `target:[row,col]` | `MergeAction` (level 3) or `RejoinAction` onto `target` (level 2) |
| `RetryAI` | — | Retries an AI action after a previous AI error, if the AI still has the turn |
| `Resign` | — | — (ends the game) |

**Resolution rule (C1).** For every move message the server lists
`engine.legal_actions(state)`, finds the action matching the request, and applies it. If
no legal action matches, the server sends `Error` and **the state is unchanged**. The
server contains no rule logic beyond this lookup, so there is exactly one rules
implementation in the codebase.

Notes that keep the wire format honest about the engine:

* `Move` covers captures too — a jump is just a move whose `(from,to)` lands two
  diagonals away; the engine classifies it. The client does not need to tell them apart.
  In the paper profile, `piece` is optional and disambiguates an original piece when
  several pieces can claim the same source square.
* `SplitMove.targets` is **advisory**. The active engine supplies canonical legal
  destinations and the server rejects a target set that does not match them. In
  `PaperQuantumEngine`, a paper split maps a source amplitude to two destination modes;
  it does not retain the toy engine's origin-weight distribution. The legacy toy
  compatibility path keeps its historical probability split.
* `ObserveMove` is legal only when the active engine allows it and the named square
  holds a spread piece. In `PaperQuantumEngine`, `allow_observe` is true only at custom
  Level 4; optional `piece` disambiguates a piece sharing that site. The legacy toy
  engine's Observe flag remains available to replay its old experiment setup.
* `MergeMove` resolves to an action offered by the active engine. In `PaperQuantumEngine`
  at Level 3, it merges two locations of the same original piece through the inverse
  split operation. The archived toy engine's merge/rejoin behavior is different and
  must not be used to infer paper-level rules.
* `Resign` ends the game, but it is applied under the **same per-room lock** as a move
  (see §3.2). It therefore cannot finalize a game while a hardware-backed collapse is
  still being measured, and a move that arrives after it is refused with `Error`
  (`game_over`) rather than committing.
* `RetryAI` reruns a pending AI response without reapplying the preceding human action.
  It can recover a transient AI/provider failure. If all offered paper transitions
  exceed the exact-branch cap, the fallback action is still refused by the engine;
  retrying the same state and deterministic decision seed cannot clear that cap. Resign
  or create a new game in that case.

### 3.2 Server → client

| `type` | payload |
| --- | --- |
| `StateUpdate` | `board`, `occupancy`, `coherence`, `turn`, `phase`, `last_event`, `last_action`, `legal`, `you`, `ply`, `status`, `quantum`, `quantum_pending` |
| `GameOver` | `result` (`0` \| `1` \| `null`), `reason` (`no_pieces` \| `no_legal_moves` \| `ply_limit` \| `forty_move_draw` \| `resign`), `moves`, `seed`, `game_id`, `level`, `mode` |
| `Error` | `message`, `code` |
| `Tick` | `t` (seconds since the room opened, integer) |
| `QuantumPending` | `pending` (`true`), `game_id`, `backend` (`null` when the room is not QPU-backed) |

`StateUpdate` fields:

* `board` — `engine.render(state)` verbatim: common fields include `engine`, `level`, `allow_observe`,
  `board_size`, `ply`, `turn`, `pieces[]` (each `piece_id`, `owner`, `sites` as
  `[[row,col],weight]`, `uncertain`), `captured[]`, `certainty`. Paper-engine views may
  also include `paper_rules`, exact `branch_count`, quiet-move count and coherence data;
  archived toy views have their own engine-specific keys.
* `occupancy` — flat row-major list of `[owner0_chance, owner1_chance]` per square
  (`protocol.board_chances(state, board_size)`). This is what the quantum visuals read.
* `coherence` — level-4 only: `{"row,col": ticks}` for each split piece, the ticks left
  before it expires; `{}` when decoherence is off. The client renders it as a counter on
  the piece's origin square.
* `phase` — string: `waiting` | `playing` | `over`. This is the room phase, not the
  quantum amplitude phase. The paper engine retains complex phases internally, but the
  client receives occupancy marginals rather than raw amplitudes or a phase display.
* `last_event` — the most recent `CollapseEvent` as JSON, or `null`, plus the aliases
  `kind` = `"collapse"`, `kept` (the resolved square) and `by` (the cause) that the
  client's reveal animation reads; `sampled`, `chances` and `cause` stay authoritative.
* `legal` — list of legal actions as `action.to_json()` dicts, for the client's
  highlight layer. The client renders these; it must not compute legality itself.
* `you` — the receiving player's seat (`0` \| `1` \| `null`), so a client that holds a
  seat for both sides (local mode) is not confused.
* `last_action` — the action just applied, as `action.to_json()`, or `null`. This is
  what the client's move log renders; it never reconstructs an action itself.
* `ply`, `status` — convenience mirrors.
* `quantum` — the live-quantum block, always present on a `StateUpdate`:
  `{"enabled": <bool>, "pending": <bool>, "backend": <string|null>,
  "last": <provenance|null>}`.
  * `enabled` — `true` when this room resolves collapses on IBM Quantum hardware
    (`IBM_CLOUD_API_KEY` was set when the room was created). `false` is the ordinary
    offline game, and every other field here is then inert.
  * `backend` — the device name. Before the first job it is the configured
    `IBM_QUANTUM_BACKEND` or `"IBM Quantum (unresolved)"`; after a job it is the device
    that actually ran it.
  * `last` — provenance of the most recent hardware collapse, or `null`:
    `backend`, `job_id`, `bitstring` (the raw measured key, e.g. `"01"`), `used`
    (`"measured"` when the bitstring mapped to a candidate square, `"invalid_fallback"`
    when it did not and the deterministic fallback chose), `sampled` (`[row,col]`),
    `probability`, `sites`. The same object is attached to `last_event.quantum` so the
    reveal animation can name the backend that resolved the piece.
  * No credential ever appears in this block, in `Error.message`, or in a log.
* `quantum_pending` — `true` only while a measurement is in flight; the authoritative
  `StateUpdate` that follows the job carries the result and resets it to `false`.
* `QuantumPending` frame — sent **before** a hardware measurement starts, to every socket
  in the room, so the client can say "measuring on hardware" while the QPU job is queued.
  It is advisory: the following `StateUpdate` is what carries the outcome and the
  provenance. Clients that ignore it still behave correctly, they just show no
  intermediate pending state. It is never sent for an ordinary move or a split, because
  neither submits a job.
* **Serialization.** A move, an agent ply and `Resign` are applied one at a time under a
  per-room lock, so a hardware-backed collapse that is still measuring cannot be
  overtaken by a resignation, and no move can commit after the game is `over`. During a
  pending measurement a client may therefore receive `QuantumPending`, then `Error` plus
  the *unchanged* `StateUpdate` if the job failed, or a `StateUpdate` with the applied
  collapse if it succeeded. Clients must **not** clear a `Error` merely because a
  `StateUpdate` arrived: after a failed measurement the state is deliberately unchanged,
  so the error is the only signal that anything happened.
* `player_id` — present **only** in the per-socket view (never on `GET /api/game` or
  for a spectator), so a joining client learns the token it must present to reclaim
  its seat after a reconnect. Each socket only ever receives its own token.

---

## 4. JSONL log schema (frozen alongside the record schema)

The game server writes **the same** `GameRecord` the headless runner writes
(`qcheckers.experiment.schema`). There is one log format for both, so server games are
analysable by the exact same statistics and viewer code. Fields are documented in that
module and pinned by `tests/test_schema.py`; this document only freezes the additions:

* `mode` — the REST `mode` string (`local`, `ai-easy`, …). Stored in `condition` as
  `<level>-<mode>` when written by the server, e.g. `L1-ai-easy`.
* `max_plies` — the ply cap the game was played under. Required, because the cap is a
  *terminal condition* of the engine: a search agent's rollouts consult it, so a replay
  under a different cap may legitimately play a different game. A line without it is not
  self-describing, and `scripts/verify_results.py` verifies every experiment record by
  replaying it from nothing but the record.
* `players` — `{"0": "<agent-or-human-label>", "1": …}`.
* Archived toy-engine server and headless records use `engine == "deterministic-toy"`
  and `toy_engine == true`. Paper-engine gameplay records use `engine == "paper-quantum"`
  and `toy_engine == false`; neither record flag is part of the live `board` render.

---

## 5. Reconnect semantics

On (re)joining, the server sends that client the **authoritative current state** — it
does not replay the move history. Concretely:

1. If `JoinGame.player_id` matches a seat already held, that seat is reclaimed and the
   server sends one `StateUpdate` to the rejoining socket (and re-broadcasts to the
   other seat).
2. The state is whatever the engine currently holds. **Unresolved superpositions stay
   unresolved.** The server never pre-samples a spread piece to "fill in" a view, so an
   opponent's unmeasured uncertainty is exactly as hidden after a reconnect as before
   one — there is nothing extra to reveal.
3. All occupancy shown is public information by the model's definition; there is no
   private per-player information in this game. The only thing a reconnect could leak is
   a collapse outcome, and collapses exist only as logged events that already happened,
   which `last_event` reports for both players equally.
4. A player whose seat is `null` (spectator join on a full room) receives read-only
   `StateUpdate` frames and its move messages are rejected with `Error` code
   `not_seated`.

---

## 6. What the protocol deliberately does NOT carry

* **No raw amplitudes or phase vectors in gameplay payloads.** The archived toy engine
  stores only chance weights. The current paper engine stores a sparse complex-amplitude
  joint state on the CPU and sends derived occupancy marginals and branch metadata to
  the client. When configured, IBM Quantum can supply a collapse sample; the persistent
  board remains in the CPU engine. The UI has no phase visualization. Payloads that
  could imply a phase display carry `amplitude_display: false` and a note.
* **No rule duplication.** No field ever asserts an action is legal "by client
  computation"; legality always comes from the server's `legal` list or an `Error`.
* **Archived batch restrictions.** The legacy `run_condition` refuses its toy-engine
  levels 3 and 4. This does not disable paper Levels 3–4 for live play: paper Level 3 is
  the interference level; Level 4 is the project's custom extension. The archived
  experiments do not evaluate either paper-engine level.

---

## 7. Revision log

* 2026-10-09 — initial freeze. Author: build.
* 2026-10-09 — same-day clarifications made while writing the client, before any
  client existed to invalidate: `StateUpdate` gained `last_action` (the move log needs
  it) and the per-socket `player_id` (reconnect needs the token, and only the socket
  that holds the seat ever sees it); `MergeMove` was documented to resolve to a
  level-3 `MergeAction` as well as a level-2 `RejoinAction`. No existing field or
  message changed meaning.
* 2026-10-09 — `max_plies` added to the JSONL record (§4) and to `GameOver`'s log
  sibling. The verifier (`scripts/verify_results.py`) found that a record could not be
  regenerated from its own seed without it, because the ply cap is a terminal condition
  the search reads: 680 of 680 records now replay byte-for-byte, which was not true
  before the field existed. Additive only; nothing reinterpreted.
* 2026-10-09 — addendum pass. Added §0 (normative samples, adapted to the names the
  implementation ships: `type` as the message tag, seats rather than colour names in
  `GameOver`, `chances` rather than a single collapsed square). Added `coherence` to
  `StateUpdate` and the `moves`/`seed`/`game_id`/`level`/`mode` metadata to `GameOver`,
  both of which the client now reads. Levels extended to `0..4`, with level 4
  game-only and both level 3 and level 4 refused by the batch runner. Nothing above
  changed meaning for an existing level.
* 2026-10-12 — documentation correction: the primary client is the Next.js app in
  `client/`; `viewer/` remains a static alternative and replay viewer. The browser
  transport and server-authoritative legality contract did not change.
* 2026-10-12 — added opt-in IBM collapse metadata (`quantum`, `quantum_pending`) and
  the advisory `QuantumPending` server frame. Documented room-mutation serialization
  and the unchanged-state error sequence. Existing move and game-over meanings are
  unchanged.
* 2026-10-14 — clarified that the common wire contract serves both the archived toy
  engine and the current local paper engine. Added the live paper-engine board and
  action profile, including its engine-specific fields, two-target split and merge
  source forms, plus `RetryAI`. The earlier toy-engine sample remains as a labeled
  archival example; its fields and meanings did not change.
