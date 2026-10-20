"use client";

/**
 * Join-by-code form.
 *
 * Two things matter here and both are about the seat:
 * 1. The code is validated locally first (the server mints `qk-<8 hex>`), so an
 *    obviously wrong code costs no request.
 * 2. The seat token is never typed or guessed. If this browser already holds a seat
 *    in that lobby its token is presented again, which makes a reload a *reconnect*
 *    rather than a third player; a first-time joiner gets a fresh token from the
 *    socket's own `StateUpdate` and the game route stores it.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, fetchGame, normaliseLobbyCode } from "@/lib/api";

export function JoinLobbyForm() {
    const router = useRouter();

    const [code, setCode] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);

        const normalised = normaliseLobbyCode(code);
        if (!normalised) {
            setError("A lobby code looks like qk-1a2b3c4d.");
            return;
        }

        setBusy(true);
        try {
            // Read the public view first: it costs nothing to sit at the table, and it
            // turns "no such game" into a clear message before we route. The seat is
            // claimed on the socket, not here.
            await fetchGame(normalised);
            router.push(`/game/${normalised}`);
        } catch (caught) {
            const message =
                caught instanceof ApiError && caught.status === 404
                    ? `No game with code ${normalised}. Rooms live in server memory and die with the process.`
                    : caught instanceof ApiError
                      ? caught.detail
                      : "Could not reach the game server. Is it running?";
            setError(message);
            setBusy(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            <h1 className="text-2xl">Join a game</h1>

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle>The code your host shares</CardTitle>
                    <CardDescription>
                        There are no accounts. A seat is an opaque token, and coming back with the same one
                        reclaims the same seat.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <label htmlFor="code" className="block text-sm text-foreground">
                            Lobby code
                        </label>
                        <Input
                            id="code"
                            name="code"
                            placeholder="qk-1a2b3c4d"
                            autoComplete="off"
                            spellCheck={false}
                            value={code}
                            onChange={(event) => setCode(event.target.value)}
                        />
                    </div>
                </CardContent>
            </Card>

            {error && (
                <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
                    {error}
                </p>
            )}

            <Button type="submit" size="lg" disabled={busy}>
                {busy ? "Checking code…" : "Join game"}
            </Button>
        </form>
    );
}