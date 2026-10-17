"use client";

/**
 * One game, end to end: masthead with the connection pill, then a phase router.
 *
 * The server's `phase` is the only authority on which screen shows:
 *
 *   `waiting` -> the lobby view: code, copy button, what is missing.
 *   `playing` / `over` -> `<GameScreen state send />`, the frozen shared contract,
 *     which owns the board, the status strip, the move log, the rules modal and
 *     the result card (it renders the result once `state.status` is `over`).
 *
 * Seat handling lives here, not in the board: on the first `StateUpdate` this socket
 * learns its own `player_id` (PROTOCOL.md §3.2 — a socket only ever receives its own
 * token), which is stored so a reload presents the same token and reclaims the seat.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { GameScreen, type ConnectionState } from "@/components/game/GameScreen";
import { RulesDialog } from "@/components/game/RulesModal";
import { ConnectionPill, PageShell } from "@/components/shell/PageShell";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useGameSocket } from "@/hooks/useGameSocket";
import { stageMeta } from "@/lib/stages";
import { loadPlayerId, recordStageResult, saveSession } from "@/lib/session";
import type { GameState } from "@/types/game";

export interface GameRouteProps {
    gameId: string;
}

/** Copy-to-clipboard, with a stated fallback when the async clipboard API is blocked. */
function useCopyCode() {
    const [copied, setCopied] = useState(false);
    const copy = async (code: string) => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            toast.info("Copy blocked — select the code and copy it manually.");
        }
    };
    return { copied, copy };
}

/** `phase === "waiting"`: the room exists, the second seat does not yet. */
function WaitingView({ gameId, state }: { gameId: string; state: GameState }) {
    const { copied, copy } = useCopyCode();
    const stage = stageMeta(state.board.level);

    return (
        <Card className="mx-auto max-w-xl">
            <CardHeader className="pb-3">
                <CardTitle>Waiting for the other seat</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                    Share this code to fill the second seat. A game against an agent, or in local mode, starts as
                    soon as the room is created.
                </p>
                <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-center font-mono text-lg tracking-widest">
                        {gameId}
                    </code>
                    <Button variant="outline" onClick={() => void copy(gameId)}>
                        {copied ? "Copied" : "Copy code"}
                    </Button>
                </div>
                {stage && (
                    <p className="font-mono text-xs text-muted-foreground">
                        {stage.title} &middot; {stage.mechanic}
                    </p>
                )}
                <div className="flex flex-wrap gap-2">
                    <Link href="/lobby/join" className={buttonVariants({ variant: "outline", size: "sm" })}>
                        Join a seat
                    </Link>
                    <RulesDialog
                        level={state.board.level}
                        triggerClassName={buttonVariants({
                            variant: "ghost",
                            size: "sm",
                        })}
                    />
                </div>
            </CardContent>
        </Card>
    );
}

/** Shown while the socket has not produced a state yet: liveness and the failure mode. */
function ConnectingView({ gameId, connected }: { gameId: string; connected: boolean }) {
    return (
        <div className="mx-auto max-w-xl space-y-3">
            <p className="font-mono text-sm text-muted-foreground">
                {connected ? "Reading the room state…" : `Connecting to game ${gameId}…`}
            </p>
            {!connected && (
                <p className="text-sm text-muted-foreground">
                    No response from the game server. Start it with <code className="font-mono">python -m
                    server</code> in the repository root, then reload this page.
                </p>
            )}
        </div>
    );
}

export function GameRoute({ gameId }: GameRouteProps) {
    const router = useRouter();

    // The seat token is only knowable on the client: it came from `POST /api/game`
    // or from this browser's own storage. Reading it during render would desync
    // hydration, so the socket opens once storage has been consulted.
    const [playerId, setPlayerId] = useState<string | null>(null);
    const [hydrated, setHydrated] = useState(false);

    useEffect(() => {
        setPlayerId(loadPlayerId(gameId));
        setHydrated(true);
    }, [gameId]);

    const { state, connected, send, gameOver, lastError, gameMissing, submitting } = useGameSocket(gameId, {
        playerId,
    });

    // Learn the token the server just issued to this socket, so a reload presents the
    // same token and reclaims the same seat rather than taking the open one.
    useEffect(() => {
        if (!state) return;
        const token = state.player_id;
        if (!token || token === playerId) return;
        setPlayerId(token);
        saveSession({
            game_id: gameId,
            player_id: token,
            level: state.board.level,
            // The mode is echoed on `GameOver`; before then the board does not carry it,
            // so the stored value is only a display hint for the rejoin banner.
            mode: gameOver?.mode ?? "online",
            saved_at: Date.now(),
        });
    }, [state, playerId, gameId, gameOver?.mode]);

    // A refused move changes nothing server-side; showing it is the whole job here.
    // The game screen also surfaces it in place, so this is the route-level notice.
    useEffect(() => {
        if (lastError) toast.error(`${lastError.message} (${lastError.code})`);
    }, [lastError]);

    // Record the result once the terminal frame arrives, for the landing-page record.
    useEffect(() => {
        if (!gameOver || !state) return;
        recordStageResult(gameOver.level, gameOver.result !== null && gameOver.result === state.you);
    }, [gameOver, state]);

    // The status strip takes a four-value socket state; derive it from the two facts
    // the transport reports rather than tracking a third source of truth.
    const connection: ConnectionState = gameMissing
        ? "closed"
        : connected
          ? "open"
          : state
            ? "reconnecting"
            : "connecting";

    if (gameMissing) {
        return (
            <PageShell aside={<ConnectionPill connected={false} />}>
                <Card className="mx-auto max-w-xl">
                    <CardHeader className="pb-3">
                        <CardTitle>No such game</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <p className="text-sm text-muted-foreground">
                            The server does not know <code className="font-mono">{gameId}</code>. Rooms live in
                            server memory and die with the process, so restarting the server empties every lobby.
                        </p>
                        <Link href="/lobby/create" className={buttonVariants()}>
                            Start a new game
                        </Link>
                    </CardContent>
                </Card>
            </PageShell>
        );
    }

    if (!hydrated) {
        return (
            <PageShell aside={<ConnectionPill connected={false} pending />}>
                <p className="font-mono text-sm text-muted-foreground">Reading saved session…</p>
            </PageShell>
        );
    }

    if (!state) {
        return (
            <PageShell aside={<ConnectionPill connected={connected} pending={!connected} />}>
                <ConnectingView gameId={gameId} connected={connected} />
            </PageShell>
        );
    }

    if (state.phase === "waiting") {
        return (
            <PageShell aside={<ConnectionPill connected={connected} />}>
                <WaitingView gameId={gameId} state={state} />
            </PageShell>
        );
    }

    return (
        // `bleed`: the board needs the full height below the masthead. In the
        // normal content column it can never fit, and its bottom rank scrolls
        // out of reach.
        <PageShell plain bleed aside={<ConnectionPill connected={connected} />}>
            <GameScreen
                state={state}
                send={send}
                submitting={submitting}
                gameOver={gameOver}
                connection={connection}
                error={lastError}
                onRematch={() =>
                    router.push(
                        `/lobby/create?stage=${state.board.level}&mode=${gameOver?.mode ?? "ai-easy"}`,
                    )
                }
                onExit={() => router.push("/")}
            />
        </PageShell>
    );
}

