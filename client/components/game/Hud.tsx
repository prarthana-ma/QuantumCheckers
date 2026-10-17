"use client";

import type { GameState } from "@/types/game";
import { cn } from "@/lib/utils";
import { STAGE_COUNT, stageDef, stageNumber } from "@/lib/stages";
import { seatColorName } from "./board-model";
import type { ConnectionState } from "./Connection";

export interface HudProps {
  state: GameState;
  connection: ConnectionState;
  collapseCount: number;
  observeCount: number;
  splitCount: number;
  /** Bumped when the turn changes, so the sweep plays once per change. */
  turnNonce: number;
  onOpenRules: () => void;
  onOpenStages: () => void;
  muted: boolean;
  onToggleSound: () => void;
  musicEnabled: boolean;
  onToggleMusic: () => void;
}

const CONNECTION_TEXT: Record<ConnectionState, string> = {
  connecting: "Linking",
  open: "Live",
  reconnecting: "Reconnecting",
  closed: "Offline",
};

const CONNECTION_COLOR: Record<ConnectionState, string> = {
  connecting: "var(--color-ink-dim)",
  open: "var(--color-primary)",
  reconnecting: "var(--color-ink-dim)",
  closed: "var(--color-destructive)",
};

/**
 * The status strip.
 *
 * Turn and ply are the two things a player checks constantly, so they get the
 * largest type and sit on the centre line. Everything else is small instrument
 * labelling. The connection lamp is a lamp, not a spinner: a slow pulse means
 * "trying", steady means "fine".
 */
export function Hud({
  state,
  connection,
  collapseCount,
  observeCount,
  splitCount,
  turnNonce,
  onOpenRules,
  onOpenStages,
  muted,
  onToggleSound,
  musicEnabled,
  onToggleMusic,
}: HudProps) {
  const stage = stageDef(state.board.level);
  const yourTurn = state.you !== null && state.status === "playing" && state.legal.length > 0;
  const spreadCount = state.board.pieces.filter((p) => p.uncertain).length;

  return (
    <header className="relative z-20 flex flex-wrap items-stretch gap-px overflow-hidden rounded-lg border border-edge bg-edge">
      <div className="flex min-w-0 flex-1 items-center gap-3 bg-card px-4 py-2.5">
        <button
          type="button"
          onClick={onOpenStages}
          title="Stage progression"
          className="flex shrink-0 items-center gap-2.5 rounded-sm border border-primary/40 bg-primary/10 px-2.5 py-1.5 hover:bg-primary/20"
        >
          {/* Player-facing number everywhere: "Stage 1 of 5" next to a "0" badge
              read as two competing counts. The wire level stays a wire detail. */}
          <span className="tnum font-display text-sm leading-none font-bold text-primary">
            {stageNumber(state.board.level)}
          </span>
          <span className="font-display text-[11px] tracking-[0.18em] text-primary">
            {stage.tag}
          </span>
        </button>
        <div className="min-w-0">
          {/* Levels run 0..4, so the number the player reads is one higher than
              the level and the total is the stage count, not the max index. */}
          <p className="label-inst">
            stage {stageNumber(state.board.level)} of {STAGE_COUNT}
          </p>
          <p className="truncate text-xs text-ink-dim">{stage.title}</p>
        </div>
      </div>

      {/* Turn and ply: the two big reads. */}
      <div className="flex items-stretch gap-px">
        <div
          key={turnNonce}
          className={cn(
            "relative flex min-w-[9.5rem] flex-col justify-center overflow-hidden px-5 py-2",
            yourTurn ? "bg-primary/12" : "bg-card",
          )}
        >
          {/* The turn-change sweep: one bar crossing the block, played once per
              turn change. It is the only motion in the HUD. */}
          <span
            key={`sweep-${turnNonce}`}
            aria-hidden
            className="animate-turn-sweep pointer-events-none absolute inset-y-0 left-0 w-full bg-primary/25"
          />
          <span className="label-inst relative">
            {yourTurn ? "your turn" : "their turn"}
          </span>
          <span className="relative mt-1 flex items-center gap-2">
            <span
              className={cn(
                "h-3.5 w-3.5 shrink-0 rounded-full",
                state.turn === 0
                  ? "bg-seat-0"
                  : "bg-seat-1",
              )}
            />
            {/* Colour first, seat number second: the board is read by colour, so
                the strip should not ask the player to translate a number first. */}
            <span className="tnum text-2xl leading-none font-bold">
              {seatColorName(state.turn).toUpperCase()}
            </span>
            <span className="text-[10px] text-ink-faint">
              {state.you === null ? "watching" : `seat ${state.you}`}
            </span>
          </span>
        </div>

        <div className="flex min-w-[6.5rem] flex-col justify-center bg-card px-5 py-2">
          <span className="label-inst">ply</span>
          <span className="tnum mt-1 text-2xl leading-none font-bold">
            {String(state.ply).padStart(3, "0")}
          </span>
        </div>
      </div>

      <div className="flex flex-1 items-stretch justify-end gap-px">
        <Counter
          label="collapses"
          value={collapseCount}
          title="Measurement (collapse) resolves a spread piece to one square."
        />
        <Counter label="observed" value={observeCount} />
        <Counter label="splits" value={splitCount} />
        <Counter
          label="spread"
          value={spreadCount}
          title="Spread (superposition) means one piece is represented across several possible squares."
        />

        <div className="flex min-w-[7.5rem] flex-col justify-center bg-card px-4 py-2">
          {/* One indicator, not a label plus a value. The lamp is the state; the
              word beside it is the same information written out. */}
          <span className="label-inst">connection</span>
          <span className="mt-1 flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              {connection !== "open" && connection !== "closed" && (
                <span
                  className="animate-pulse-signal absolute inset-0 rounded-full"
                  style={{ background: CONNECTION_COLOR[connection] }}
                />
              )}
              <span
                className="relative h-2.5 w-2.5 rounded-full"
                style={{ background: CONNECTION_COLOR[connection] }}
              />
            </span>
            <span
              className="font-display text-[11px] tracking-[0.12em]"
              style={{ color: CONNECTION_COLOR[connection] }}
            >
              {CONNECTION_TEXT[connection]}
            </span>
          </span>
        </div>

        <button
          type="button"
          onClick={onToggleMusic}
          aria-pressed={musicEnabled}
          title="Outer Space Loop by wipics — CC0"
          className="flex min-w-[5.5rem] items-center justify-center bg-card px-3 font-display text-[11px] tracking-[0.12em] text-ink-dim hover:text-primary"
        >
          {musicEnabled ? "Music on" : "Music off"}
        </button>

        <button
          type="button"
          onClick={onToggleSound}
          aria-pressed={!muted}
          className="flex min-w-[5.5rem] items-center justify-center bg-card px-3 font-display text-[11px] tracking-[0.12em] text-ink-dim hover:text-primary"
        >
          {muted ? "Sound off" : "Sound on"}
        </button>

        <button
          type="button"
          onClick={onOpenRules}
          className="flex items-center bg-card px-5 font-display text-[11px] tracking-[0.16em] text-ink-dim hover:text-primary"
        >
          Rules
        </button>
      </div>
    </header>
  );
}

function Counter({ label, value, title }: { label: string; value: number; title?: string }) {
  return (
    <div className="flex min-w-[4.75rem] flex-col justify-center bg-card px-3.5 py-2">
      <span className="label-inst text-[8px]" title={title}>{label}</span>
      <span className="tnum mt-1 text-lg leading-none font-semibold text-ink">
        {String(value).padStart(2, "0")}
      </span>
    </div>
  );
}
