import type { Metadata } from "next";

import { CreateLobbyForm } from "@/components/lobby/CreateLobbyForm";
import { PageShell } from "@/components/shell/PageShell";

export const metadata: Metadata = { title: "New game — QCheckers" };

/**
 * `stage` and `mode` arrive from the rematch link, so the form comes back up on the
 * same conditions. They are read here rather than in the client with `useSearchParams`,
 * which keeps this route statically prerenderable.
 */
export default async function CreateLobbyPage({
    searchParams,
}: {
    searchParams: Promise<{ stage?: string; mode?: string }>;
}) {
    const { stage, mode } = await searchParams;
    const level = Number(stage);

    return (
        <PageShell>
            <CreateLobbyForm
                initialLevel={Number.isInteger(level) && level >= 0 && level <= 4 ? level : 0}
                initialMode={mode}
            />
        </PageShell>
    );
}
