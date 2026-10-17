"use client";

/**
 * Shared page chrome: masthead with the connection pill, and the animated grid
 * backdrop. Layout only — no game state.
 */

import Link from "next/link";

import Squares from "@/components/ui/Squares";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface ConnectionPillProps {
    connected: boolean;
    /** Show "connecting" rather than "offline" before the first attempt. */
    pending?: boolean;
    className?: string;
}

/**
 * Small status dot for the socket. Deliberately not a toast: the pill must keep
 * reporting while a toast would have faded, because a dropped link during play is
 * the thing a player most needs to notice.
 */
export function ConnectionPill({ connected, pending = false, className }: ConnectionPillProps) {
    const label = connected ? "live" : pending ? "connecting" : "offline";
    return (
        <Badge
            variant={connected ? "default" : pending ? "outline" : "destructive"}
            className={cn("gap-1.5", className)}
            role="status"
            aria-live="polite"
        >
            <span
                aria-hidden="true"
                className={cn("inline-block size-1.5 rounded-full bg-current", !pending && "animate-pulse-signal")}
            />
            {label}
        </Badge>
    );
}

export interface PageShellProps {
    children: React.ReactNode;
    /** Rendered on the right of the masthead (connection pill, stage badge, …). */
    aside?: React.ReactNode;
    /** Hide the grid backdrop, e.g. behind a dense board view. */
    plain?: boolean;
    /**
     * Full-bleed mode: children become a flex child that fills the height left
     * by the masthead, with no max-width, no padding and no site footer.
     *
     * The board view needs this. Inside the normal content column the page is
     * masthead + `py-10` + child + footer, so a child that wants exactly one
     * viewport of height always overflows — and a board that overflows puts its
     * bottom rank off screen. The attribution is not lost: the rules dialog
     * carries it.
     */
    bleed?: boolean;
}

/** Masthead + backdrop + content column. Every route renders inside this. */
export function PageShell({ children, aside, plain = false, bleed = false }: PageShellProps) {
    return (
        <div
            className={cn(
                "relative flex flex-col",
                bleed ? "min-h-dvh lg:h-dvh lg:overflow-hidden" : "min-h-screen",
            )}
        >
            {!plain && (
                <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
                    <Squares />
                </div>
            )}
            {!bleed && <header className="relative z-10 flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-5 py-4 sm:px-8">
                <Link href="/" className="flex flex-col leading-tight">
                    <span className="text-lg">QCheckers</span>
                    <span className="font-mono text-xs text-muted-foreground">Quantum Checkers</span>
                </Link>
                <div className="flex items-center gap-2">{aside}</div>
            </header>}
            {bleed ? (
                <div className="relative z-10 flex min-h-0 flex-1 flex-col">{children}</div>
            ) : (
                <>
                    <main className="relative z-10 mx-auto w-full max-w-5xl flex-1 px-5 py-10 sm:px-8">
                        {children}
                    </main>
                    <footer className="relative z-10 border-t border-border/60 px-5 py-4 font-mono text-xs text-muted-foreground sm:px-8">
                        {/* The attribution has to survive a narrow window and a long
                            unbroken run of punctuation. Without a break opportunity
                            Chrome will push the tail past the viewport and clip the
                            sentence mid-word. */}
                        <p className="max-w-[70ch] break-words leading-relaxed [overflow-wrap:anywhere]">
                            Based on the quantum-checkers paper, with an original implementation.
                            Stage 5 adds experimental decoherence rules.
                        </p>
                    </footer>
                </>
            )}
        </div>
    );
}
