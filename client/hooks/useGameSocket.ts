"use client";

/**
 * Transport for one game socket.
 *
 * Scope: **transport only**. This hook opens `ws://.../ws/{game_id}`, sends `JoinGame`
 * first (PROTOCOL.md §3: any other message before a seat is held is refused), keeps the
 * latest `StateUpdate` in state, and hands back a `send` for the client's own builders.
 * It applies no rules and computes no legality; a refused move arrives as an `Error`
 * and the state is left untouched by the server.
 *
 * Reconnection is safe by design: presenting the same `player_id` reclaims the same
 * seat (PROTOCOL.md §5), and the server sends the authoritative current state rather
 * than replaying history.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { resolveErrorAfterStateUpdate } from "@/components/game/errorLifetime";
import { gameSocketUrl } from "@/lib/backendUrls";
import {
    type ClientMessage,
    type GameOverMsg,
    type GameState,
    JoinGame,
    type ServerMessage,
} from "@/types/game";

/** Reconnect attempts before the hook stops trying. */
const MAX_RECONNECT_ATTEMPTS = 5;

/** WebSocket close code the server uses for an unknown lobby (PROTOCOL.md §3). */
const CLOSE_UNKNOWN_GAME = 4404;

export interface UseGameSocketOptions {
    /** Seat token from `POST /api/game` or localStorage; reclaims the seat on reconnect. */
    playerId?: string | null;
    /** Optional self-given seat label. We use opaque tokens, not accounts. */
    label?: string | null;
}

export interface GameSocket {
    submitting: boolean;
    /** Latest `StateUpdate`, or `null` before the first one arrives. */
    state: GameState | null;
    /** True while the socket is open. Drives the connection pill. */
    connected: boolean;
    /** Send one client message. A no-op while the socket is not open. */
    send: (message: ClientMessage) => void;
    /** The `GameOver` frame once the game ends; `null` while it is running. */
    gameOver: GameOverMsg | null;
    /** The last protocol `Error`, for the refused-move path. */
    lastError: { message: string; code: string } | null;
    /** True when the server closed the lobby as unknown and reconnecting is pointless. */
    gameMissing: boolean;
}

export function useGameSocket(gameId: string, options: UseGameSocketOptions = {}): GameSocket {
    const { playerId = null, label = null } = options;

    const [state, setState] = useState<GameState | null>(null);
    const [connected, setConnected] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const submittingRef = useRef(false);
    const [gameOver, setGameOver] = useState<GameOverMsg | null>(null);
    const [lastError, setLastError] = useState<{ message: string; code: string } | null>(null);
    const [gameMissing, setGameMissing] = useState(false);

    const socketRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const attemptsRef = useRef(0);
    /** Ply of the last state we saw; lets an error outlive an unchanged StateUpdate. */
    const plyRef = useRef(0);
    /** Ply the board was on when the current error was reported. */
    const errorPlyRef = useRef(0);
    /** A finished game must not be retried: `GameOver` and `phase: "over"` are terminal. */
    const finishedRef = useRef(false);

    useEffect(() => {
        if (!gameId) return;

        let disposed = false;

        const connect = () => {
            if (disposed || finishedRef.current) return;

            let socket: WebSocket;
            try {
                socket = new WebSocket(gameSocketUrl(gameId));
            } catch {
                // A malformed URL or a blocked socket: count it as a failed attempt.
                attemptsRef.current += 1;
                return;
            }
            socketRef.current = socket;

            socket.onopen = () => {
                if (disposed) return;
                setConnected(true);
                setGameMissing(false);
                attemptsRef.current = 0;
                // Seat claim first: nothing else is accepted before it.
                socket.send(
                    JSON.stringify(
                        JoinGame({ player_id: playerId ?? undefined, label: label ?? undefined }),
                    ),
                );
            };

            socket.onmessage = (event: MessageEvent<string>) => {
                if (disposed) return;
                let message: ServerMessage;
                try {
                    message = JSON.parse(event.data) as ServerMessage;
                } catch {
                    // A frame we cannot parse is not the server's contract; ignore it
                    // rather than throwing inside the event handler.
                    return;
                }

                switch (message.type) {
                    case "StateUpdate": {
                        submittingRef.current = false;
                        setSubmitting(false);
                        setState(message);
                        plyRef.current = message.ply;
                        // Do NOT clear unconditionally: after a failed hardware
                        // measurement the server sends Error *then* the unchanged state,
                        // so an unconditional clear would hide the failure. Keep it until
                        // the board moves or the game reaches a terminal state.
                        setLastError((prev) =>
                            resolveErrorAfterStateUpdate(
                                prev,
                                errorPlyRef.current,
                                message.ply,
                                message.phase === "over",
                            ),
                        );
                        // A `GameOver` frame may not arrive if the socket dropped at the
                        // same moment; the phase in the state is authoritative.
                        if (message.phase === "over") finishedRef.current = true;
                        break;
                    }
                    case "GameOver":
                        submittingRef.current = false;
                        setSubmitting(false);
                        finishedRef.current = true;
                        setGameOver(message);
                        break;
                    case "Error":
                        submittingRef.current = false;
                        setSubmitting(false);
                        // Remember the board position this error belongs to, so a following
                        // StateUpdate that does not move the game keeps it visible.
                        errorPlyRef.current = plyRef.current;
                        setLastError({ message: message.message, code: message.code });
                        break;
                    case "QuantumPending":
                        // A QPU job just started. Mark the current state pending so the
                        // board can say so; the next StateUpdate replaces this with the
                        // authoritative value and the collapse provenance.
                        setState((prev) =>
                            prev ? { ...prev, quantum_pending: true } : prev,
                        );
                        break;
                    case "Tick":
                        // Liveness only; nothing to render.
                        break;
                    default:
                        break;
                }
            };

            socket.onclose = (event: CloseEvent) => {
                submittingRef.current = false;
                setSubmitting(false);
                if (disposed) return;
                socketRef.current = null;
                setConnected(false);

                if (event.code === CLOSE_UNKNOWN_GAME) {
                    setGameMissing(true);
                    finishedRef.current = true;
                    return;
                }
                if (finishedRef.current || attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) return;

                attemptsRef.current += 1;
                const delay = Math.min(1000 * 2 ** (attemptsRef.current - 1), 8000);
                reconnectTimer.current = setTimeout(connect, delay);
            };

            socket.onerror = () => {
                // `onclose` always follows, and it owns the retry decision.
                socket.close();
            };
        };

        connect();

        return () => {
            disposed = true;
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            reconnectTimer.current = null;
            const socket = socketRef.current;
            socketRef.current = null;
            if (
                socket &&
                (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
            ) {
                socket.close(1000, "component unmounting");
            }
        };
    }, [gameId, playerId, label]);

    const send = useCallback((message: ClientMessage) => {
        const socket = socketRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN) return;
        if (message.type !== "JoinGame") {
            if (submittingRef.current) return;
            submittingRef.current = true;
            setSubmitting(true);
        }
        socket.send(JSON.stringify(message));
    }, []);

    return { state, connected, send, gameOver, lastError, gameMissing, submitting };
}
