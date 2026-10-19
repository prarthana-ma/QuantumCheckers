/**
 * Client-side session storage.
 *
 * Seats are **opaque tokens**, not accounts: the server hands back a `player_id` and
 * the client presents it again to reclaim the same seat after a reload or a dropped
 * socket (PROTOCOL.md §5). No identity, no handle, no personal data is stored — only
 * the token, the lobby code and the labels the player typed for themselves.
 *
 * Keys are namespaced `qk.*` so they cannot collide with the zero-build viewer in
 * `viewer/`, which uses the same prefix for its replay-progress record.
 */

import type { ModeValue } from "@/lib/stages";

/** The game the browser currently holds a seat in, for the rejoin banner. */
export const SESSION_KEY = "qk.session";

/** Which stages the player has already finished, plus which unlocks they have seen. */
export const PROGRESS_KEY = "qk.progress";

/** A server base URL the player typed in, if it differs from `NEXT_PUBLIC_API_URL`. */
export const SERVER_KEY = "qk.server";

export interface StoredSession {
    game_id: string;
    /** Seat token from `POST /api/game`. Presenting it reclaims the seat. */
    player_id: string;
    level: number;
    mode: ModeValue | string;
    /** Epoch millis, used to label how stale the rejoin offer is. */
    saved_at: number;
    /** Optional self-given seat label. Never a handle or an identity. */
    label?: string;
}

export interface StoredProgress {
    /** Stage numbers with at least one finished game. */
    stages?: Record<string, { games: number; wins: number }>;
    /** Stage numbers whose unlock blurb has already been shown. */
    unlocks?: Record<string, true>;
}

/**
 * All reads are guarded: Safari private mode and blocked-storage browsers throw on
 * `localStorage` access, and a missing rejoin banner is a fine outcome there.
 */
function readJson<T>(key: string): T | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = window.localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as T) : null;
    } catch {
        return null;
    }
}

function writeJson(key: string, value: unknown): void {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
        /* storage unavailable or full: the session simply is not remembered */
    }
}

function remove(key: string): void {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.removeItem(key);
    } catch {
        /* nothing to do */
    }
}

/** A stored session with the expected shape; anything else is discarded as stale. */
export function loadSession(): StoredSession | null {
    const parsed = readJson<Partial<StoredSession>>(SESSION_KEY);
    if (!parsed || typeof parsed.game_id !== "string" || typeof parsed.player_id !== "string") {
        return null;
    }
    return {
        game_id: parsed.game_id,
        player_id: parsed.player_id,
        level: typeof parsed.level === "number" ? parsed.level : 0,
        mode: typeof parsed.mode === "string" ? parsed.mode : "local",
        saved_at: typeof parsed.saved_at === "number" ? parsed.saved_at : 0,
        label: typeof parsed.label === "string" ? parsed.label : undefined,
    };
}

export function saveSession(session: StoredSession): void {
    writeJson(SESSION_KEY, session);
}

export function clearSession(): void {
    remove(SESSION_KEY);
}

/** Seat token for a lobby code, if this browser already holds one there. */
export function loadPlayerId(gameId: string): string | null {
    const session = loadSession();
    return session && session.game_id === gameId ? session.player_id : null;
}

export function loadProgress(): StoredProgress {
    return readJson<StoredProgress>(PROGRESS_KEY) ?? {};
}

/** Record one finished game for a stage. */
export function recordStageResult(level: number, won: boolean): void {
    const progress = loadProgress();
    const stages = progress.stages ?? {};
    const current = stages[String(level)] ?? { games: 0, wins: 0 };
    stages[String(level)] = {
        games: current.games + 1,
        wins: current.wins + (won ? 1 : 0),
    };
    writeJson(PROGRESS_KEY, { ...progress, stages });
}

export function markUnlockSeen(level: number): void {
    const progress = loadProgress();
    writeJson(PROGRESS_KEY, {
        ...progress,
        unlocks: { ...(progress.unlocks ?? {}), [String(level)]: true },
    });
}

export function unlockSeen(level: number): boolean {
    return loadProgress().unlocks?.[String(level)] === true;
}

export function loadServerOverride(): string | null {
    if (typeof window === "undefined") return null;
    try {
        return window.localStorage.getItem(SERVER_KEY);
    } catch {
        return null;
    }
}

export function saveServerOverride(url: string): void {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.setItem(SERVER_KEY, url);
    } catch {
        /* ignore */
    }
}