"""Run the game server: ``python -m server``.

Defaults to ``127.0.0.1:8000`` so nothing is exposed beyond the machine unless
``--host 0.0.0.0`` is passed for LAN play (brief: localhost + LAN only).
"""

from __future__ import annotations

import argparse

import uvicorn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m server",
        description="Run the Quantum Checkers game server (FastAPI + WebSockets).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument(
        "--log",
        default="results/server.jsonl",
        help="JSONL file for finished games (one condition label per level+mode).",
    )
    parser.add_argument(
        "--tick",
        type=float,
        default=1.0,
        help="Liveness tick interval in seconds (0 disables ticks).",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Reload on source changes (development)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from server.app import create_app

    application = create_app(tick_seconds=args.tick, log_path=args.log)
    print(f"QuriousMinds server on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    print(f"  game log: {args.log}")
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
