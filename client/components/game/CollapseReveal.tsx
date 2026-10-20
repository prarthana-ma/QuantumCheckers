"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CollapseEventMsg, GameState, Square } from "@/types/game";
import { cn } from "@/lib/utils";
import { causeLabel, describeAction, pctFine, sqKey, squareName } from "./board-model";

/**
 * One entry of the session log. Built only from frames the server has already
 * sent: `last_action` and `last_event` verbatim. Nothing here reconstructs an
 * action we were not told about.
 */
export interface HistoryEntry {
  key: string;
  ply: number;
  action: GameState["last_action"];
  event: CollapseEventMsg | null;
}

export interface CollapseRevealProps {
  state: GameState;
  reveal: { before: Square[]; after: Square | null } | null;
  onClearReveal: () => void;
  history: HistoryEntry[];
}

const STEP_MS = 2400;

/**
 * The collapse reveal.
 *
 * The animation is the point of the game, so it runs in three named beats rather
 * than one blur: the candidate squares were all live, the engine sampled one, and
 * that square is now certain. Pause freezes the timeline so a player mid-thought
 * can read the chances.
 */
export function CollapseReveal({
  state,
  reveal,
  onClearReveal,
  history,
}: CollapseRevealProps) {
  const event = state.last_event;
  const [playing, setPlaying] = useState(true);
  const [cursor, setCursor] = useState<number | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const collapses = useMemo(() => history.filter((h) => h.event !== null), [history]);

  useEffect(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    if (!reveal) return;

    setCursor(null);
    if (!playing) return;

    const t1 = setTimeout(() => setCursor(0), 600);
    const t2 = setTimeout(() => setCursor(1), 600 + STEP_MS * 0.42);
    const t3 = setTimeout(() => setCursor(2), 600 + STEP_MS * 0.76);
    timers.current = [t1, t2, t3];
    return () => timers.current.forEach(clearTimeout);
  }, [reveal, playing, event?.ply]);

  // Auto-dismiss so the board returns to the live position.
  useEffect(() => {
    if (!reveal || !playing) return;
    const t = setTimeout(
      () => {
        setCursor(null);
        onClearReveal();
      },
      600 + STEP_MS * 1.1,
    );
    return () => clearTimeout(t);
  }, [reveal, playing, onClearReveal]);

  if (!event || !reveal) return null;

  const keptKey = sqKey(reveal.after);
  const chanceOfKept = event.chances.find(([sq]) => sqKey(sq) === keptKey)?.[1] ?? 1;

  const beats = [
    { label: "Before", hint: "The piece occupied every one of these squares." },
    {
      label: "Sampled",
      hint: `Chance was ${pctFine(chanceOfKept)} on the square it kept.`,
    },
    { label: "After", hint: `Certain. Resolved by ${event.by}.` },
  ];
  const active = cursor ?? 0;

  return (
    <section
      aria-label="Collapse reveal"
      className="animate-modal-in relative overflow-hidden rounded-lg border border-primary/45 bg-card"
    >
      {/* Three beats, filled as the timeline runs. */}
      <div className="absolute inset-x-0 top-0 flex h-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn(
              "h-full flex-1 transition-opacity duration-300",
              i <= active ? "bg-primary" : "bg-transparent",
            )}
          />
        ))}
      </div>

      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge-soft px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-primary">
            Collapse at ply {event.ply}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-faint">
            {causeLabel(event.by)} — piece {event.piece_id}, seat {event.owner}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          <RevealButton onClick={() => setPlaying((p) => !p)} active={playing}>
            {playing ? "Pause" : "Play"}
          </RevealButton>
          <RevealButton onClick={() => setCursor((c) => Math.max(0, (c ?? 0) - 1))}>
            Step back
          </RevealButton>
          <RevealButton onClick={() => setCursor((c) => Math.min(2, (c ?? 0) + 1))}>
            Step forward
          </RevealButton>
          <RevealButton onClick={onClearReveal}>Dismiss</RevealButton>
        </div>
      </header>

      <div className="grid gap-px bg-edge-soft sm:grid-cols-[1fr_auto]">
        {/* The chance table: the numbers the animation is describing. */}
        <ul className="bg-card px-4 py-3">
          {event.chances.map(([square, chance]) => {
            const kept = sqKey(square) === keptKey;
            return (
              <li
                key={sqKey(square)}
                className={cn(
                  "tnum flex items-center gap-3 py-1 text-xs",
                  kept ? "text-primary" : "text-ink-dim",
                  active >= 1 && !kept && "opacity-40",
                )}
              >
                <span className="w-9 shrink-0 font-semibold">{squareName(square)}</span>
                {/* The bar is a transform, not a width animation: a width change
                    on every chance row would relayout the whole panel. */}
                <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/10">
                  <span
                    className="block h-full origin-left rounded-full bg-current transition-transform duration-500"
                    style={{ transform: `scaleX(${chance})` }}
                  />
                </span>
                <span className="w-12 shrink-0 text-right">{pctFine(chance)}</span>
                {kept && (
                  <span className="w-10 shrink-0 text-[9px] tracking-[0.14em] text-primary">
                    KEPT
                  </span>
                )}
              </li>
            );
          })}
        </ul>

        <div className="flex min-w-[15rem] flex-col justify-center bg-card px-4 py-3">
          <p className="label-inst">{beats[active].label}</p>
          <p className="mt-2 text-xs leading-relaxed text-ink-dim">{beats[active].hint}</p>
          {state.last_action && (
            <p className="tnum mt-3 border-t border-edge-soft pt-2 text-[10px] text-ink-faint">
              {describeAction(state.last_action)}
            </p>
          )}
        </div>
      </div>

      {collapses.length > 1 && (
        <footer className="flex items-center gap-2 border-t border-edge-soft px-4 py-2">
          <span className="label-inst text-[8px]">this session</span>
          <div className="flex flex-1 flex-wrap gap-1">
            {collapses.slice(-12).map((entry) => (
              <button
                key={entry.key}
                type="button"
                onClick={() => setPlaying(false)}
                title={`ply ${entry.ply} — ${causeLabel(entry.event?.by ?? "")}`}
                className={cn(
                  "tnum rounded-sm border px-1.5 py-0.5 text-[9px]",
                  entry.event?.piece_id === event.piece_id
                    ? "border-primary/60 bg-primary/15 text-primary"
                    : "border-edge text-ink-faint hover:border-primary/40 hover:text-ink-dim",
                )}
              >
                {entry.ply}
              </button>
            ))}
          </div>
        </footer>
      )}
    </section>
  );
}

function RevealButton({
  children,
  onClick,
  active,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-sm border px-2.5 py-1 text-[11px]",
        active
          ? "border-primary/60 bg-primary/15 text-primary"
          : "border-edge text-ink-dim hover:border-primary/45 hover:text-primary",
      )}
    >
      {children}
    </button>
  );
}