import type { Metadata } from "next";

import { JoinLobbyForm } from "@/components/lobby/JoinLobbyForm";
import { PageShell } from "@/components/shell/PageShell";

export const metadata: Metadata = { title: "Join a game — QCheckers" };

export default function JoinLobbyPage() {
    return (
        <PageShell>
            <JoinLobbyForm />
        </PageShell>
    );
}
