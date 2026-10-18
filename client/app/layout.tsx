import type { Metadata } from "next";
import { Chakra_Petch, IBM_Plex_Mono, Press_Start_2P, Space_Grotesk } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";

import "./globals.css";
import { cn } from "@/lib/utils";

/** Arcade display face — headings only; too wide for body copy. */
const arcade = Press_Start_2P({
    weight: "400",
    subsets: ["latin"],
    variable: "--font-arcade",
    display: "swap",
});

/** Display face — angular, engineered, reads like instrument labelling. */
const chakra = Chakra_Petch({
    subsets: ["latin"],
    weight: ["400", "500", "600", "700"],
    variable: "--font-chakra",
    display: "swap",
});

/** Body face — a grotesque with open apertures, holds up at small sizes. */
const grotesk = Space_Grotesk({
    subsets: ["latin"],
    weight: ["400", "500", "600", "700"],
    variable: "--font-grotesk",
    display: "swap",
});

/** Tabular face — every number on the board is monospaced so digits don't jitter. */
const plexMono = IBM_Plex_Mono({
    subsets: ["latin"],
    weight: ["400", "500", "600"],
    variable: "--font-plex-mono",
    display: "swap",
});

export const metadata: Metadata = {
    title: {
        default: "QCheckers — Quantum Checkers",
        template: "%s — QCheckers",
    },
    description:
        "A probability-carrying draughts board. Split a piece, let it sit unresolved, and choose when to measure it.",
    applicationName: "QCheckers",
    openGraph: {
        type: "website",
        title: "QCheckers — Quantum Checkers",
        description:
            "Server-authoritative Quantum Checkers: five stages from classical moves to decoherence, played on a probability-carrying board.",
        siteName: "QCheckers",
        locale: "en_US",
    },
    twitter: {
        card: "summary",
        title: "QCheckers — Quantum Checkers",
        description:
            "Server-authoritative Quantum Checkers: five stages from classical moves to decoherence, played on a probability-carrying board.",
    },
    robots: { index: false, follow: false },
};

/**
 * Provider stack: theme (forced dark — this is a dark ops-console by design) and the
 * toast surface for refused moves and server errors. No analytics, no sound context,
 * no remote scripts.
 */
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    return (
        <html
            lang="en"
            suppressHydrationWarning
            className={cn("dark", arcade.variable, chakra.variable, grotesk.variable, plexMono.variable)}
        >
            <body className="min-h-screen bg-background font-sans text-foreground antialiased">
                <ThemeProvider
                    attribute="class"
                    defaultTheme="dark"
                    enableSystem={false}
                    forcedTheme="dark"
                    disableTransitionOnChange
                >
                    {children}
                    <Toaster position="bottom-right" theme="dark" />
                </ThemeProvider>
            </body>
        </html>
    );
}
