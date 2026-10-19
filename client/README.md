# QCheckers game client

Next.js client for QCheckers, a server-authoritative Quantum Checkers game. It renders the
state the server sends and sends move requests; it never decides legality. The
contract is frozen in [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md).

**Live demo:** [quriousminds.vercel.app](https://quriousminds.vercel.app).
The production client uses the Cloud Run API configured in Vercel's
`NEXT_PUBLIC_API_URL`. Redeploy instructions are in [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

The Music control plays a CC0 ambient loop after a user gesture, independently of
the Sound effects control. Attribution is recorded in `../docs/ATTRIBUTION.md`.

## Prerequisites

- **Node.js 20+** (developed on 22.x). Next 16 requires it.
- **npm 10+** (ships with Node 20).
- The game server running locally: `python -m server` from the repository root
  (FastAPI + WebSocket, `127.0.0.1:8000` by default).

## Install

```bash
npm ci
```

## Configure

Copy the example and edit if your server is not on the default address:

```bash
cp .env.example .env.local     # Windows: copy .env.example .env.local
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | REST base (`/api/...`) |
| `NEXT_PUBLIC_WS_URL` | derived from the REST base (`http` → `ws`) | Socket base (`/ws/{game_id}`) |

Both are inlined at build time by Next, so `npm run build` has to be re-run after
changing them. Nothing is hardcoded to a hosted domain: the client talks to
whatever address the env var names, which is localhost or a LAN address.

## Run

```bash
npm run dev     # development server on http://localhost:3000
npm run build   # production build
npm run start   # serve the production build on http://localhost:3000
```

`npm run typecheck` runs `tsc --noEmit` on its own.

## Routes

| Route | What it does |
| --- | --- |
| `/` | Landing: start a game, join by code, read the rules, rejoin a held seat |
| `/lobby/create` | Stage, opponent and reproducibility settings, then `POST /api/game` |
| `/lobby/join` | Validates a lobby code, then routes to the game |
| `/game/[gameId]` | Phase router: waiting lobby → board → result |

## Where the code lives

| Path | Role |
| --- | --- |
| `types/game.ts` | Wire types and message builders, mirroring `PROTOCOL.md` field for field |
| `hooks/useGameSocket.ts` | Transport only: opens the socket, sends `JoinGame`, keeps the last `StateUpdate` |
| `lib/backendUrls.ts` | REST and socket base URLs from the environment |
| `lib/api.ts` | REST helpers (`POST /api/game`, `GET /api/game/{id}`, health) |
| `lib/stages.ts` | Stage copy and rule text, and the caveat the protocol requires |
| `lib/session.ts` | `qk.*` localStorage keys: seat token, stage record |
| `components/game/` | Board, HUD, action panel, result card |
| `components/ui/` | Button, card, input, badge, dialog, progress, slider, canvas backdrop |

## Seat identity

There are no accounts. `POST /api/game` returns an opaque `player_id`; the client
stores it under `qk.session` and presents it again on `JoinGame`, which is what makes
a reconnect reclaim the same seat (`PROTOCOL.md` §5). A spectator join on a full room
gets read-only frames and is labelled as such in the UI.

## Licence note

The shell's visual language is adapted from [Battle-CP](https://github.com/Prajwal-k-tech/Battle-CP)
with the author's written permission; see [`../docs/ATTRIBUTION.md`](../docs/ATTRIBUTION.md).
