import type { Metadata } from "next";

import { HomeClient } from "@/components/home/HomeClient";
import { PageShell } from "@/components/shell/PageShell";

export const metadata: Metadata = {
    title: "QCheckers — Quantum Checkers",
    description:
        "Server-authoritative Quantum Checkers. Five stages from classical moves to decoherence, on a probability-carrying board.",
};

export default function HomePage() {
    return (
        <PageShell>
            <HomeClient />
        </PageShell>
    );
}
