# QCheckers client

Next.js + TypeScript client for the QCheckers game server. It renders the state the
server sends and sends move requests; it never decides legality.

**Live demo:** [quriousminds.vercel.app](https://quriousminds.vercel.app)

## Run

Requires Node.js 20+ and the game server running (`python -m server`, FastAPI +
WebSocket on `127.0.0.1:8000`).

```bash
npm ci
npm run dev        # http://localhost:3000
npm run build      # production build
npm run typecheck  # tsc --noEmit
```

## Configure

Copy `.env.example` to `.env.local` to point at a different server:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | REST base (`/api/...`) |
| `NEXT_PUBLIC_WS_URL` | derived from the REST base (`http` → `ws`) | Socket base |

Both are inlined at build time, so re-run `npm run build` after changing them.

## Routes

| Route | What it does |
| --- | --- |
| `/` | Landing: start a game, join by code, read the rules, rejoin a held seat |
| `/lobby/create` | Stage, opponent and seed settings |
| `/lobby/join` | Validates a lobby code, then routes to the game |
| `/game/[gameId]` | Waiting lobby → board → result |

## Music

The Music toggle plays "Outer Space Loop" by wipics (CC0), after a user gesture and
independently of the sound effects.
