/**
 * Backend endpoints for the QCheckers game server.
 *
 * Local development defaults to 127.0.0.1:8000. Vercel builds configure
 * NEXT_PUBLIC_API_URL with the HTTPS Cloud Run origin. Next.js inlines public
 * variables at build time. The WebSocket base is derived from the same origin.
 */

const DEFAULT_API_URL = "http://127.0.0.1:8000";

function trimTrailingSlash(url: string): string {
    return url.replace(/\/+$/, "");
}

/** Base URL for REST calls (`/api/...`). No trailing slash. */
export function getApiBaseUrl(): string {
    const configured = process.env.NEXT_PUBLIC_API_URL;
    return trimTrailingSlash(configured && configured.length > 0 ? configured : DEFAULT_API_URL);
}

/**
 * Base URL for the game socket (`/ws/{game_id}`), derived from the REST base so a
 * single `NEXT_PUBLIC_API_URL` moves both. No trailing slash.
 */
export function getWsBaseUrl(): string {
    const configured = process.env.NEXT_PUBLIC_WS_URL;
    if (configured && configured.length > 0) {
        return trimTrailingSlash(configured);
    }
    return getApiBaseUrl().replace(/^http/, "ws");
}

/** Absolute URL of a game's socket. */
export function gameSocketUrl(gameId: string): string {
    return `${getWsBaseUrl()}/ws/${encodeURIComponent(gameId)}`;
}

/** Absolute URL of a REST path such as `/api/health`. */
export function apiUrl(path: string): string {
    return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
