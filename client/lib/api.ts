"use client";

/**
 * REST helpers for the game server.
 *
 * All calls are browser-side `fetch` against the configured game server.
 * Errors are surfaced as thrown `ApiError`s carrying the
 * server's own status and `detail`, so a 422 from FastAPI reads as a validation
 * message rather than a generic failure.
 */

import { apiUrl } from "@/lib/backendUrls";
import type { GameState } from "@/types/game";

export class ApiError extends Error {
    readonly status: number;
    readonly detail: string;

    constructor(status: number, detail: string) {
        super(detail);
        this.name = "ApiError";
        this.status = status;
        this.detail = detail;
    }
}

/** Extract FastAPI's `detail` when present, else fall back to the status line. */
async function toError(response: Response): Promise<ApiError> {
    let detail = `${response.status} ${response.statusText}`.trim();
    try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") {
            detail = body.detail;
        } else if (Array.isArray(body.detail)) {
            // FastAPI 422 validation errors: flatten loc/msg pairs into one line.
            detail = body.detail
                .map((entry) => {
                    const item = entry as { loc?: unknown[]; msg?: string };
                    const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "input";
                    return `${String(field)}: ${item.msg ?? "invalid"}`;
                })
                .join("; ");
        }
    } catch {
        /* body was not JSON: keep the status line */
    }
    return new ApiError(response.status, detail);
}

export interface CreateGameRequest {
    /** Stage number, 0..4. */
    level: number;
    mode: string;
    /** Optional fixed seed; the server draws one when omitted. */
    seed?: number | null;
    /** Optional board size; the live server defaults to 8. */
    board_size?: number | null;
    /** Optional room-level voluntary Observe rule; omitted keeps the stage default. */
    allow_observe?: boolean | null;
}

export interface CreateGameResponse {
    game_id: string;
    player_id: string;
    level: number;
    mode: string;
    seed: number;
}

/** `POST /api/game`. */
export async function createGame(request: CreateGameRequest): Promise<CreateGameResponse> {
    const response = await fetch(apiUrl("/api/game"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            level: request.level,
            mode: request.mode,
            ...(request.seed === null || request.seed === undefined ? {} : { seed: request.seed }),
            ...(request.board_size === null || request.board_size === undefined
                ? {}
                : { board_size: request.board_size }),
            ...(request.allow_observe === null || request.allow_observe === undefined
                ? {}
                : { allow_observe: request.allow_observe }),
        }),
    });
    if (!response.ok) throw await toError(response);
    return (await response.json()) as CreateGameResponse;
}

/** `GET /api/game/{game_id}` — the caller-independent view. 404 when the game is gone. */
export async function fetchGame(gameId: string): Promise<GameState> {
    const response = await fetch(apiUrl(`/api/game/${encodeURIComponent(gameId)}`), { cache: "no-store" });
    if (!response.ok) throw await toError(response);
    return (await response.json()) as GameState;
}

/**
 * `GET /api/game/{game_id}/view?player_id=...` — the reconnect snapshot: exactly the
 * `StateUpdate` that player would receive on the socket.
 */
export async function fetchGameView(gameId: string, playerId: string): Promise<GameState> {
    const query = `?player_id=${encodeURIComponent(playerId)}`;
    const response = await fetch(apiUrl(`/api/game/${encodeURIComponent(gameId)}/view${query}`), {
        cache: "no-store",
    });
    if (!response.ok) throw await toError(response);
    return (await response.json()) as GameState;
}

/** `GET /api/health`. */
export async function fetchHealth(): Promise<{ status: string; games: number }> {
    const response = await fetch(apiUrl("/api/health"), { cache: "no-store" });
    if (!response.ok) throw await toError(response);
    return (await response.json()) as { status: string; games: number };
}

/** What a lobby code may contain: the server mints `qk-<8 hex>`, and nothing else is valid. */
const LOBBY_CODE_PATTERN = /^qk-[0-9a-f]{8}$/i;

/**
 * Validate a typed lobby code before spending a request on it. Returns the normalised
 * (lower-case, trimmed) code, or `null` when it cannot be a real code.
 */
export function normaliseLobbyCode(raw: string): string | null {
    const trimmed = raw.trim().toLowerCase();
    if (!trimmed) return null;
    if (LOBBY_CODE_PATTERN.test(trimmed)) return trimmed;
    // Tolerate a code pasted without its `qk-` prefix rather than rejecting it outright.
    if (/^[0-9a-f]{8}$/.test(trimmed)) return `qk-${trimmed}`;
    return null;
}
