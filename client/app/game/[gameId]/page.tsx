import type { Metadata } from "next";
import { Suspense } from "react";

import { GameRoute } from "@/components/game/GameRoute";

export const metadata: Metadata = {
    title: "Game — QCheckers",
    robots: { index: false, follow: false },
};

/**
 * Route shell for one game. The phase router and the socket live in the client
 * component, because the seat token and the socket both require the browser; this
 * file only resolves the lobby code from the path.
 */
export default async function GamePage({ params }: { params: Promise<{ gameId: string }> }) {
    const { gameId } = await params;
    return (
        // `Suspense` keeps the client subtree out of the static prerender path; the
        // lobby code is only known at request time.
        <Suspense fallback={<p className="font-mono text-sm text-muted-foreground">Opening {gameId}…</p>}>
            <GameRoute gameId={decodeURIComponent(gameId)} />
        </Suspense>
    );
}
