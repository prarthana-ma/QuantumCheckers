"use client";

/**
 * Landing screen: start a new game, join by lobby code, read the rules, and pick up a
 * game this browser already holds a seat in.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { RulesDialog } from "@/components/game/RulesModal";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchHealth } from "@/lib/api";
import { stageMeta } from "@/lib/stages";
import { clearSession, loadProgress, loadSession, type StoredSession } from "@/lib/session";

/** Human-readable age of a stored session, for the rejoin banner. */
function describeAge(savedAt: number): string {
    if (!savedAt) return "earlier";
    const minutes = Math.round((Date.now() - savedAt) / 60000);
    if (minutes < 1) return "moments ago";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    return `${Math.round(hours / 24)} d ago`;
}

/**
 * The rejoin offer. Storage is read in an effect, never during render: the server
 * markup has no session, so reading it inline would break hydration.
 */
function RejoinBanner() {
    const router = useRouter();
    const [session, setSession] = useState<StoredSession | null>(null);

    useEffect(() => {
        setSession(loadSession());
    }, []);

    if (!session) return null;

    const stage = stageMeta(session.level);

    return (
        <Card className="border-primary/40 bg-primary/5">
            <CardHeader className="pb-3">
                <CardTitle>Seat held in {session.game_id}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">
                    {stage?.title ?? `Stage ${session.level + 1}`} &middot; {session.mode} &middot;{" "}
                    {describeAge(session.saved_at)}
                </p>
                <div className="flex gap-2">
                    <Button size="sm" onClick={() => router.push(`/game/${session.game_id}`)}>
                        Rejoin game
                    </Button>
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                            clearSession();
                            setSession(null);
                        }}
                    >
                        Forget seat
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}

/** Finished games per stage, so the landing page can show a record. */
function StageRecord() {
    const [stages, setStages] = useState<Record<string, { games: number; wins: number }>>({});

    useEffect(() => {
        setStages(loadProgress().stages ?? {});
    }, []);

    const rows = Object.entries(stages).sort((a, b) => Number(a[0]) - Number(b[0]));

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle>Your record</CardTitle>
            </CardHeader>
            <CardContent>
                {rows.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                        No finished games yet. Results appear here after each game ends.
                    </p>
                ) : (
                    <ul className="space-y-1.5 font-mono text-sm text-muted-foreground">
                        {rows.map(([level, stat]) => (
                            <li key={level}>
                                stage {Number(level) + 1}: {stat.wins}W / {stat.games - stat.wins}L over {stat.games}{" "}
                                {stat.games === 1 ? "game" : "games"}
                            </li>
                        ))}
                    </ul>
                )}
            </CardContent>
        </Card>
    );
}

/**
 * Server liveness. An unreachable server is the most likely reason a player cannot
 * start, so it is stated on the page rather than left for a button to fail silently.
 */
function ServerStatus() {
    const [status, setStatus] = useState<"checking" | "ok" | "down">("checking");
    const [games, setGames] = useState<number | null>(null);

    const check = useCallback(async () => {
        setStatus("checking");
        try {
            const health = await fetchHealth();
            setGames(health.games);
            setStatus("ok");
        } catch {
            setStatus("down");
        }
    }, []);

    useEffect(() => {
        void check();
    }, [check]);

    return (
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
            <span
                aria-hidden="true"
                className={
                    status === "ok"
                        ? "inline-block size-1.5 rounded-full bg-collapse"
                        : status === "down"
                          ? "inline-block size-1.5 rounded-full bg-destructive"
                          : "inline-block size-1.5 animate-pulse-signal rounded-full bg-primary"
                }
            />
            {status === "ok" && <span>Server reachable &middot; {games} rooms open</span>}
            {status === "down" && <span>Server unreachable at the configured address.</span>}
            {status === "checking" && <span>Checking the game server…</span>}
            {status === "down" && (
                <Button size="sm" variant="ghost" onClick={() => void check()}>
                    Retry
                </Button>
            )}
        </div>
    );
}

export function HomeClient() {
    return (
        <div className="space-y-8">
            <section className="space-y-4">
                <h1 className="text-3xl sm:text-4xl">QCheckers</h1>
                {/* Subtext is kept to one short line: the CTAs below sit above the
                    fold on a laptop viewport, and the detail lives in the rules. */}
                <p className="max-w-2xl text-muted-foreground">
                    Quantum Checkers on a probability-carrying board. Five stages, from classical moves to
                    decoherence.
                </p>
                <ServerStatus />
            </section>

            {/* Navigation targets are anchors styled with the button variants: this
                client has no `asChild` slot, and a <button> wrapping an <a> is
                invalid markup. One label per intent: start, join, read the rules. */}
            <section className="flex flex-wrap gap-3">
                <Link href="/lobby/create" className={buttonVariants({ size: "lg" })}>
                    Start a game
                </Link>
                <Link href="/lobby/join" className={buttonVariants({ variant: "outline", size: "lg" })}>
                    Join a game
                </Link>
                <RulesDialog triggerClassName={buttonVariants({ variant: "outline", size: "lg" })} />
            </section>

            <RejoinBanner />
            <StageRecord />
        </div>
    );
}
