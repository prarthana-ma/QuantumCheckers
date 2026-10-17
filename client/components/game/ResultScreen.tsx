"use client";

import { useState } from "react";
import type { GameOverMsg, GameState } from "@/types/game";
import { cn } from "@/lib/utils";
import { reasonLabel, seatName } from "./board-model";
import { stageDef, stageNumber } from "@/lib/stages";

export interface ResultScreenProps {
  state: GameState;
  gameOver: GameOverMsg | null;
  onRematch: () => void;
  onBackToStages: () => void;
}

const MODE_LABEL: Record<string, string> = {
  local: "Two players, one browser",
  online: "Two browsers",
  "ai-easy": "Against the Easy agent",
  "ai-medium": "Against the Medium agent",
  "ai-hard": "Against the Hard agent",
};

/**
 * The result card.
 *
 * Shows the seed and the final move count because both are part of the record:
 * a game logged from this screen must be reproducible from the numbers printed on
 * it. Every figure here is read from the `GameOver` frame or the state — nothing
 * is estimated, and nothing is shown as a number we cannot back up.
 */
export function ResultScreen({
  state,
  gameOver,
  onRematch,
  onBackToStages,
}: ResultScreenProps) {
  const winner = gameOver?.result ?? null;
  const youHeldSeat = state.you !== null;
  const youWon = winner !== null && youHeldSeat && winner === state.you;
  const drew = winner === null;
  const stage = stageDef(state.board.level);

  const accent = drew
    ? "var(--color-ink-dim)"
    : winner === 0
      ? "var(--color-seat-0)"
      : "var(--color-seat-1)";

  const headline = gameOver
    ? drew
      ? "Drawn"
      : youWon
        ? "You win"
        : `${seatName(winner).replace("SEAT ", "Seat ")} wins`
    : "Game over";

  const spreadLeft = state.board.pieces.filter((p) => p.uncertain).length;
  const seed = gameOver?.seed;
  const [copied, setCopied] = useState(false);

  const copySeed = async () => {
    if (seed == null) return;
    try {
      await navigator.clipboard.writeText(String(seed));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access is optional; keep the result screen usable if unavailable.
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="result-title"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-background/85 p-4 backdrop-blur-sm"
    >
      <div className="animate-modal-in relative w-full max-w-xl overflow-hidden rounded-xl border border-edge bg-card">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{
            background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          }}
        />

        <header className="px-7 pt-7 pb-5">
          <p className="label-inst">
            stage {stageNumber(state.board.level)} — {stage.tag}
          </p>
          <h2
            id="result-title"
            className="mt-2 text-3xl leading-none font-bold tracking-tight"
            style={{ color: accent }}
          >
            {headline}
          </h2>
          <p className="mt-3 text-sm text-ink-dim">
            {gameOver ? reasonLabel(gameOver.reason) : "The game has ended."}
          </p>
        </header>

        {/* The record block. Every number here is one the log keeps. */}
        <dl className="grid grid-cols-2 gap-px border-y border-edge-soft bg-edge-soft sm:grid-cols-4">
          <ResultStat label="moves" value={String(gameOver?.moves ?? state.ply)} />
          <div className="bg-card px-5 py-4">
            <dt className="label-inst">seed</dt>
            <dd className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="tnum break-all text-sm font-semibold">
                {seed == null ? "not reported" : String(seed)}
              </span>
              {seed != null && (
                <button
                  type="button"
                  aria-label="Copy game seed to clipboard"
                  onClick={copySeed}
                  className="shrink-0 rounded-sm border border-edge px-2 py-1 text-[9px] text-ink-dim hover:border-primary/60 hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {copied ? "Copied" : "Copy seed"}
                </button>
              )}
            </dd>
          </div>
          <ResultStat
            label="certainty"
            value={`${Math.round(state.board.certainty * 100)}%`}
          />
          <ResultStat label="spread left" value={String(spreadLeft)} />
        </dl>

        <div className="px-7 py-5">
          <dl className="flex flex-col gap-2 text-xs">
            <Row
              label="mode"
              value={gameOver ? (MODE_LABEL[gameOver.mode] ?? gameOver.mode) : "not reported"}
            />
            <Row label="game id" value={gameOver?.game_id ?? "not reported"} mono />
            <Row label="your seat" value={youHeldSeat ? seatName(state.you) : "spectator"} />
            <Row label="level" value={String(gameOver?.level ?? state.board.level)} />
          </dl>

          {spreadLeft > 0 && (
            <p className="mt-4 rounded-md border border-edge bg-secondary px-3 py-2 text-[11px] text-ink-faint">
              {spreadLeft} piece{spreadLeft > 1 ? "s were" : " was"} still unresolved when
              the game ended. An unresolved piece is not a piece that moved; it is a
              distribution the engine never measured.
            </p>
          )}
        </div>

        <footer className="flex flex-wrap gap-2 border-t border-edge-soft px-7 py-5">
          <button
            type="button"
            onClick={onBackToStages}
            className="rounded-md border border-edge px-4 py-2.5 font-display text-[11px] tracking-[0.14em] text-ink-dim hover:border-ink-faint hover:text-ink"
          >
            Stages
          </button>
          <button
            type="button"
            onClick={onRematch}
            autoFocus
            className={cn(
              "flex-1 rounded-md px-4 py-2.5 font-display text-[11px] font-semibold tracking-[0.14em]",
              "text-background",
            )}
            style={{ background: accent }}
          >
            Rematch
          </button>
        </footer>
      </div>
    </div>
  );
}

function ResultStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-5 py-4">
      <dt className="label-inst">{label}</dt>
      <dd className="tnum mt-1.5 text-xl font-semibold">{value}</dd>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-edge-soft pb-1.5 last:border-0">
      <dt className="text-ink-faint">{label}</dt>
      <dd className={cn("text-right", mono ? "tnum text-[11px]" : "")}>{value}</dd>
    </div>
  );
}