# QCheckers

QCheckers is a playable quantum-inspired checkers game built by Team QuriousMinds for the
IEG 313 course project. Each piece can sit on several squares at once, and every collapse
of that uncertainty can be resolved with a real quantum measurement.

**Live demo:** [quriousminds.vercel.app](https://quriousminds.vercel.app) |
**Project report:** [docs/REPORT.md](docs/REPORT.md)

Based on the staged quantum-checkers design of Raat *et al.*, "Quantum Checkers: The
Development and Analysis of a Quantum Combinatorial Game," IEEE CoG 2025
([arXiv:2506.05962](https://arxiv.org/abs/2506.05962)).

## What it is

- A server-authoritative checkers game (English draughts rules) on an 8×8 board, with a
  browser client, lobby, stage selection and reconnectable seats.
- Levels 0–3 follow the paper's staged mechanics: superposition and measurement,
  entanglement, then interference. Level 4 is our own extension with a coherence timer
  and voluntary **Observe** on by default; **Observe** can also be enabled as an opt-in
  rule from Level 1.
- The board state is a sparse **complex-amplitude** state over complete board
  configurations, evolved on the CPU. The client shows occupancy probabilities
  (`|amplitude|²`); amplitudes and phases stay on the server.
- **Hardware measurement (optional).** When `QISKIT_IBM_TOKEN` is configured, every
  collapse (an `Observe`, or a Level-4 decoherence expiry) is resolved with one
  measurement shot of a real circuit on IBM Quantum. A failed job is refused
  (`quantum_unavailable`); an unusable outcome is refused (`quantum_invalid_outcome`).
  The game state is never replaced by a simulator or RNG result on this path. Without a
  token the game runs offline with the engine's seeded local sampling.

## Run it

Python 3.10+ and Node.js 20+.

Server (terminal 1):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m server                # http://127.0.0.1:8000
```

Client (terminal 2):

```powershell
cd client
npm ci
npm run dev                     # http://localhost:3000
```

Screens: landing, then new game (stage, opponent, optional seed, board size), then the
board. The board shows each piece's occupancy chances and reveals collapses as they
happen. The client never decides legality; it talks to whatever server
`NEXT_PUBLIC_API_URL` names.

## Tests

```powershell
python -m pytest                # Python suite
cd client
npm run typecheck
npm test
npm run build
```

## Optional: IBM Quantum hardware mode

```powershell
python -m pip install -r requirements-ibm.txt
$env:QISKIT_IBM_TOKEN = "..."   # enables hardware sampling
```

`IBM_QUANTUM_INSTANCE`, `IBM_QUANTUM_BACKEND` and `IBM_QUANTUM_TIMEOUT` are optional.
One measurement shot is submitted per collapse, and the QPU supplies that sample only;
the board state stays on the CPU. Each collapse costs one job and a few seconds of QPU
quota (the recorded test job reported a 2-second charge).

## Project layout

```text
qcheckers/     complex-amplitude engine, live MCTS agent, measurement circuit
server/        FastAPI + WebSocket game server (authoritative rules, rooms)
client/        Next.js + TypeScript game client (see client/README.md)
viewer/        static replay viewer and alternative client
scripts/       checks and utility scripts
tests/         Python test suite
docs/          project report and figures
```

## Music

The game's Music toggle plays "Outer Space Loop" by wipics (CC0).
