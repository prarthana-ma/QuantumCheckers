"use client";

import { useState } from "react";
import type { GameState } from "@/types/game";
import type { Selection } from "./board-interaction";
import { MODE_HINT } from "./board-interaction";
import { seatColorName, squareName } from "./board-model";

export interface ActionPanelProps {
  state: GameState;
  selection: Selection | null;
  onOpenRules: () => void;
  onResign: () => void;
  interactive: boolean;
  busy?: boolean;
  onRetry?: () => void;
}

/** Context and help only; every gameplay action is performed beside or on the board. */
export function ActionPanel({ state, selection, onOpenRules, onResign, interactive, busy = false, onRetry }: ActionPanelProps) {
  const [confirmResign, setConfirmResign] = useState(false);
  const piece = selection ? state.board.pieces.find((piece) => piece.piece_id === selection.piece_id) : undefined;
  return (
    <aside className="flex w-full flex-col gap-3 lg:min-h-0 lg:flex-1">
      <div className="flex flex-col gap-3 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
        <section className="rounded-lg border border-primary/30 bg-card p-3">
          <h2 className="label-inst mb-3">play on the board</h2>
          <p className="text-sm leading-relaxed text-ink-dim">
            {busy ? "Your move is being resolved. The board will update when it finishes." :
              state.status === "over" ? "The game is over." :
              state.you === null ? "You are watching this game." :
              !interactive ? `Waiting for ${seatColorName(state.turn)} to move.` :
              selection ? MODE_HINT[selection.mode] : "Tap one of your pieces. All its legal destinations will light up. Tap one to play."}
          </p>
          {state.board.level > 0 && (
            <p className="mt-2 text-xs leading-relaxed text-ink-faint">Select a piece to see its quantum actions just below the board. Every action uses one turn.</p>
          )}
          {onRetry && <button type="button" onClick={onRetry} disabled={busy} className="mt-3 min-h-10 rounded-md border border-primary px-3 text-sm text-primary disabled:opacity-40">Retry AI move</button>}
        </section>
        {piece && (
          <section className="rounded-lg border border-edge bg-card p-3">
            <h2 className="label-inst mb-3">selected piece</h2>
            <p className="mb-2 text-sm text-ink-dim">{seatColorName(piece.owner)} · {piece.sites.length > 1 ? "split across possible squares" : "one certain position"}</p>
            <dl className="flex flex-col gap-2 text-sm">
              {piece.sites.map(([site, chance]) => (
                <div key={site.join(",")} className="flex justify-between">
                  <dt className="font-mono text-ink-dim">{squareName(site)}</dt>
                  <dd className="font-mono text-primary">{Math.round(chance * 100)}%</dd>
                </div>
              ))}
            </dl>
          </section>
        )}
        <section className="rounded-lg border border-edge bg-card p-3">
          <h2 className="label-inst mb-3">board</h2>
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <div><dt className="text-ink-faint">Pieces</dt><dd className="mt-1 font-mono text-sm">{state.board.pieces.length}</dd></div>
            <div><dt className="text-ink-faint">Split pieces</dt><dd className="mt-1 font-mono text-sm">{state.board.pieces.filter((piece) => piece.uncertain).length}</dd></div>
            <div><dt className="text-ink-faint">Certainty</dt><dd className="mt-1 font-mono text-sm">{Math.round(state.board.certainty * 100)}%</dd></div>
            <div><dt className="text-ink-faint">Captured</dt><dd className="mt-1 font-mono text-sm">{state.board.captured.length}</dd></div>
          </dl>
          <p className="mt-3 border-t border-edge pt-2 text-xs leading-relaxed text-ink-faint">Solid discs are certain. Dashed discs show possible positions and their probabilities.</p>
        </section>
      </div>
      <div className="flex shrink-0 gap-2">
        <button type="button" onClick={onOpenRules} className="min-h-10 flex-1 rounded-md border border-edge px-3 py-2 text-sm text-ink-dim hover:border-primary hover:text-primary">Rules</button>
        {confirmResign ? (
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-destructive">Confirm resign?</span>
            <button
              type="button"
              aria-label="Confirm resignation"
              onClick={() => {
                onResign();
                setConfirmResign(false);
              }}
              disabled={busy || state.status === "over" || state.you === null}
              className="min-h-10 rounded-md border border-destructive/50 px-3 text-sm text-destructive hover:border-destructive disabled:opacity-30"
            >
              Yes
            </button>
            <button
              type="button"
              aria-label="Cancel resignation"
              onClick={() => setConfirmResign(false)}
              className="min-h-10 rounded-md border border-edge px-3 text-sm text-ink-dim hover:text-ink"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            aria-label="Resign"
            onClick={() => setConfirmResign(true)}
            disabled={busy || state.status === "over" || state.you === null}
            title={state.you === null ? "Spectators cannot resign" : undefined}
            className="min-h-10 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive disabled:opacity-30"
          >
            Resign
          </button>
        )}
      </div>
    </aside>
  );
}
