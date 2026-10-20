"use client";

/**
 * Create-a-game form: stage, mode, and the two optional reproducibility knobs
 * (seed, board size). Posts to `POST /api/game`, stores the returned seat token for
 * reconnect, then routes to the game.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { RulesDialog } from "@/components/game/RulesModal";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { ApiError, createGame } from "@/lib/api";
import { MODES, STAGES, type ModeValue, isMode, stageMeta } from "@/lib/stages";
import { saveSession } from "@/lib/session";
import { cn } from "@/lib/utils";

export interface CreateLobbyFormProps {
    /** Prefill, used by the rematch link so the same stage and mode come back up. */
    initialLevel?: number;
    initialMode?: string;
}

/** The server accepts board sizes 4..16; the slider spans the sizes worth playing. */
const BOARD_SIZE_MIN = 4;
const BOARD_SIZE_MAX = 8;

export function CreateLobbyForm({ initialLevel = 0, initialMode = "ai-easy" }: CreateLobbyFormProps) {
    const router = useRouter();

    const [level, setLevel] = useState(initialLevel);
    const [allowObserve, setAllowObserve] = useState(initialLevel === 4);
    const [mode, setMode] = useState<ModeValue>(isMode(initialMode) ? initialMode : "ai-easy");
    const [seedText, setSeedText] = useState("");
    const [boardSize, setBoardSize] = useState(8);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const stage = stageMeta(level);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setError(null);

        // An empty seed field means "let the server draw one", which is the default;
        // anything else must be an integer or the server answers 422.
        const seedTrimmed = seedText.trim();
        let seed: number | null = null;
        if (seedTrimmed.length > 0) {
            const parsed = Number(seedTrimmed);
            if (!Number.isInteger(parsed)) {
                setBusy(false);
                setError("Seed must be a whole number, or left empty for the server to draw one.");
                return;
            }
            seed = parsed;
        }

        try {
            const game = await createGame({
                level,
                mode,
                seed,
                board_size: boardSize,
                allow_observe: level >= 1 ? allowObserve : false,
            });
            // Store the seat token so a reload or a dropped socket reclaims this seat
            // instead of taking the other one.
            saveSession({
                game_id: game.game_id,
                player_id: game.player_id,
                level: game.level,
                mode: game.mode,
                saved_at: Date.now(),
            });
            router.push(`/game/${game.game_id}`);
        } catch (caught) {
            const message =
                caught instanceof ApiError ? caught.detail : "Could not reach the game server. Is it running?";
            setError(message);
            toast.error(message);
            setBusy(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-2xl">New game</h1>
                <RulesDialog
                    level={level}
                    triggerLabel="Rules for this stage"
                    triggerClassName={cn(
                        buttonVariants({ variant: "outline", size: "sm" }),
                        "shrink-0",
                    )}
                />
            </div>

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle>Stage</CardTitle>
                    <CardDescription>One mechanic per stage. Later stages keep the earlier rules.</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-2 sm:grid-cols-2">
                    {STAGES.map((entry) => (
                        <button
                            key={entry.level}
                            type="button"
                            onClick={() => {
                                setLevel(entry.level);
                                setAllowObserve(entry.level === 4);
                            }}
                            aria-pressed={entry.level === level}
                            className={cn(
                                "rounded-lg border p-3 text-left transition-colors",
                                entry.level === level
                                    ? "border-primary bg-primary/10"
                                    : "border-border hover:border-primary/40 hover:bg-accent/40",
                            )}
                        >
                            <span className="flex items-center gap-2 text-sm">
                                {entry.title}
                                {entry.level === level && <Badge variant="default">selected</Badge>}
                            </span>
                            <span className="mt-1 block text-xs text-muted-foreground">{entry.mechanic}</span>
                        </button>
                    ))}
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle>Opponent</CardTitle>
                    <CardDescription>
                        Who takes the second seat. Online leaves it open for another browser to join by code.
                    </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-2 sm:grid-cols-2">
                    {MODES.map((entry) => (
                        <button
                            key={entry.value}
                            type="button"
                            onClick={() => setMode(entry.value)}
                            aria-pressed={entry.value === mode}
                            className={cn(
                                "rounded-lg border p-3 text-left transition-colors",
                                entry.value === mode
                                    ? "border-primary bg-primary/10"
                                    : "border-border hover:border-primary/40 hover:bg-accent/40",
                            )}
                        >
                            <span className="block text-sm">{entry.label}</span>
                            <span className="mt-1 block text-xs text-muted-foreground">{entry.hint}</span>
                        </button>
                    ))}
                </CardContent>
            </Card>

            {level >= 1 && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle>Rules variant</CardTitle>
                        <CardDescription>
                            Allow either player to spend a whole turn measuring one of their split pieces.
                            Forced captures still apply.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="grid gap-2 sm:grid-cols-2">
                            {[
                                { value: false, label: "Off", hint: "Voluntary Observe is not offered." },
                                { value: true, label: "On", hint: "Either player may measure a split piece." },
                            ].map((entry) => (
                                <button
                                    key={entry.label}
                                    type="button"
                                    onClick={() => setAllowObserve(entry.value)}
                                    aria-pressed={entry.value === allowObserve}
                                    className={cn(
                                        "rounded-lg border p-3 text-left transition-colors",
                                        entry.value === allowObserve
                                            ? "border-primary bg-primary/10"
                                            : "border-border hover:border-primary/40 hover:bg-accent/40",
                                    )}
                                >
                                    <span className="block text-sm">{entry.label}</span>
                                    <span className="mt-1 block text-xs text-muted-foreground">{entry.hint}</span>
                                </button>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {level === 4 ? "On by default at this stage." : "Off by default."}
                        </p>
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle>Reproducibility</CardTitle>
                    <CardDescription>
                        Both fields are optional. A seed makes the game replayable from its log line; the board
                        size defaults to the paper's standard 8×8 opening.
                    </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-5 sm:grid-cols-2">
                    <div className="space-y-2">
                        <label htmlFor="seed" className="block text-sm text-foreground">
                            Seed
                        </label>
                        <Input
                            id="seed"
                            name="seed"
                            inputMode="numeric"
                            placeholder="server draws one"
                            value={seedText}
                            onChange={(event) => setSeedText(event.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <label htmlFor="board-size" className="block text-sm text-foreground">
                            Board size
                        </label>
                        <div className="flex items-center gap-4">
                            <Slider
                                id="board-size"
                                value={[boardSize]}
                                min={BOARD_SIZE_MIN}
                                max={BOARD_SIZE_MAX}
                                step={2}
                                onValueChange={(value) => setBoardSize(value[0] ?? BOARD_SIZE_MIN)}
                            />
                            <Badge variant="outline" className="w-12 justify-center">
                                {boardSize}&times;{boardSize}
                            </Badge>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {stage?.unlock && (
                <div className="rounded-md border border-primary/30 bg-primary/10 p-3">
                    <p className="text-sm">{stage.unlock.title}</p>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {stage.unlock.body.map((line) => (
                            <li key={line}>{line}</li>
                        ))}
                    </ul>
                </div>
            )}

            {error && (
                <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
                    {error}
                </p>
            )}

            <Button type="submit" size="lg" disabled={busy}>
                {busy ? "Creating game…" : "Create game"}
            </Button>
        </form>
    );
}
