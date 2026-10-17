"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { stageDef, stageNumber } from "@/lib/stages";

export interface UnlockModalProps {
  level: number;
  onClose: () => void;
  onOpenRules: () => void;
}

/**
 * The unlock card, shown once when a stage is reached for the first time.
 *
 * Shown stages 2 and 4 both carry mechanics we invented, and both say so in the
 * same breath as the explanation — a player should not walk away thinking the
 * decoherence clock came out of a paper.
 */
export function UnlockModal({ level, onClose, onOpenRules }: UnlockModalProps) {
  const stage = stageDef(level);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    buttonRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Enter") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hasUnlock = stage.unlock !== undefined;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="unlock-title"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/80 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="animate-modal-in relative w-full max-w-lg overflow-hidden rounded-xl border border-primary/40 bg-card ">
        {/* A staged reveal: the stage number arrives large, then the copy. */}
        <div className="relative overflow-hidden border-b border-edge-soft px-6 py-6">
          <div
            aria-hidden
            className="pointer-events-none absolute -top-10 -right-6 font-display text-[9rem] leading-none font-700 text-primary/[0.07]"
          >
            {stageNumber(level)}
          </div>
          <p className="label-inst text-primary">stage unlocked</p>
          <h2
            id="unlock-title"
            className="mt-2 font-display text-2xl leading-tight font-700 text-ink"
          >
            {hasUnlock ? stage.unlock!.title : stage.title}
          </h2>
        </div>

        <div className="px-6 py-5">
          <ul className="flex flex-col gap-3">
            {(hasUnlock ? stage.unlock!.body : [stage.mechanic]).map((line, i) => (
              <li key={i} className="flex gap-3">
                <span
                  className={cn(
                    "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                    "bg-primary",
                  )}
                />
                <span className="text-sm leading-relaxed text-ink-dim">
                  {line}
                </span>
              </li>
            ))}
          </ul>

          {hasUnlock && (
            <div className="mt-5 rounded-lg border-l-2 border-primary/60 bg-primary/[0.05] py-3 pr-4 pl-3.5">
              <p className="label-inst text-[9px] text-primary">
                our mechanic — credited
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-dim">
                {stage.unlock!.credit}
              </p>
            </div>
          )}

          {stage.gameOnly && (
            <p className="mt-4 text-[11px] leading-relaxed text-ink-faint">
              {stage.gameOnly}
            </p>
          )}
        </div>

        <footer className="flex gap-2 border-t border-edge-soft px-6 py-4">
          <button
            type="button"
            onClick={onOpenRules}
            className="rounded-md border border-edge px-4 py-2 font-display text-[11px] tracking-[0.14em] text-ink-dim hover:border-ink-faint hover:text-ink"
          >
            FULL RULES
          </button>
          <button
            ref={buttonRef}
            type="button"
            onClick={onClose}
            className="flex-1 rounded-md bg-primary px-4 py-2 font-display text-[11px] font-semibold tracking-[0.14em] text-background"
          >
            START PLAYING
          </button>
        </footer>
      </div>
    </div>
  );
}