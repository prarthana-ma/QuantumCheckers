"use client";

/**
 * The one rules dialog, used from every entry point: the home page, the lobby
 * forms, the waiting room and the game screen.
 *
 * Two rules from the frozen protocol shape what this screen is allowed to say:
 *
 *  - It describes what the engine actually does, never what a paper might do.
 *    Stages 2 and 4 are mechanics this project invented, and they say so in the
 *    same breath as the explanation (PROTOCOL.md §6).
 *  - The standing caveat travels with the rules, so the honesty note cannot be
 *    reached without the rule text that qualifies it.
 *
 * `RulesModal` is the implementation. `RulesDialog` is the trigger-shaped
 * wrapper so call sites can drop in a button without owning open state.
 */

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  AMPLITUDE_CAVEAT,
  RULES_FOOTNOTE,
  STAGES,
  STAGE_COUNT,
  stageDef,
  stageNumber,
} from "@/lib/stages";

export interface RulesModalProps {
  /** Currently playing stage. */
  level: number;
  onClose: () => void;
}

/**
 * The rules card — one mechanic per stage.
 *
 * Stages 1–4 follow paper levels 0–3; stage 5 is a custom extension.
 */
export function RulesModal({ level, onClose }: RulesModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      // Keep focus inside the dialog while it is open.
      if (e.key === "Tab" && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const current = stageDef(level);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="rules-title"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/78 p-4 backdrop-blur-sm sm:p-8"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="animate-modal-in relative w-full max-w-3xl overflow-hidden rounded-xl border border-edge bg-card "
      >
        <header className="relative flex items-start justify-between gap-4 border-b border-edge-soft px-6 py-5">
          <div>
            <p className="label-inst">rules</p>
            <h2
              id="rules-title"
              className="mt-1.5 font-display text-2xl font-700 tracking-tight text-ink"
            >
              {current.title}
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-dim">
              {current.mechanic}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close rules"
            className="shrink-0 rounded-md border border-edge px-3 py-1.5 font-display text-[11px] tracking-[0.14em] text-ink-dim hover:border-destructive/50 hover:text-destructive"
          >
            CLOSE
          </button>
        </header>

        <div className="grid gap-px bg-edge-soft md:grid-cols-[13rem_1fr]">
          {/* Stage rail. The number is shown 1-based to match the HUD. */}
          <nav aria-label="Stages" className="flex flex-col gap-0.5 bg-card p-3">
            {STAGES.map((stage) => {
              const active = stage.level === level;
              const ours = stage.unlock !== undefined;
              return (
                <div
                  key={stage.level}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2",
                    active && "bg-primary/12",
                  )}
                >
                  <span
                    className={cn(
                      "tnum grid h-6 w-6 shrink-0 place-items-center rounded-sm border font-display text-[11px] font-700",
                      active
                        ? "border-primary text-primary"
                        : "border-edge text-ink-faint",
                    )}
                  >
                    {stageNumber(stage.level)}
                  </span>
                  <div className="min-w-0">
                    <p
                      className={cn(
                        "truncate font-display text-[11px] tracking-[0.12em]",
                        active
                          ? "text-primary"
                          : "text-ink-dim",
                      )}
                    >
                      {stage.tag}
                    </p>
                    {ours && (
                      <p className="text-[9px] tracking-[0.1em] text-primary">
                        OUR MECHANIC
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </nav>

          {/* Detail */}
          <div className="bg-card px-6 py-5">
            <ul className="flex flex-col gap-3">
              {current.detail.map((line, i) => (
                <li key={i} className="flex gap-3">
                  <span className="tnum mt-0.5 shrink-0 font-display text-[11px] text-primary">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-sm leading-relaxed text-ink-dim">
                    {line}
                  </span>
                </li>
              ))}
            </ul>

            {current.unlock && (
              <div className="mt-5 rounded-lg border border-primary/35 bg-primary/[0.06] p-4">
                <p className="label-inst text-primary">{current.level === 4 ? "Project extension" : "Paper rule"}</p>
                <p className="mt-2 text-sm leading-relaxed text-ink-dim">
                  {current.unlock.credit}
                </p>
              </div>
            )}

            {current.gameOnly && (
              <p className="mt-4 border-t border-edge-soft pt-3 text-[11px] leading-relaxed text-ink-faint">
                {current.gameOnly}
              </p>
            )}

            {/* The honesty notes. Protocol §6 says the wire carries chance weights
                only, so we say so wherever we describe the model, and we keep the
                Cheqqers/licence line attached to the rules rather than only in
                the site footer. */}
            <div className="mt-4 space-y-2 border-t border-edge-soft pt-3">
              <p className="text-[11px] leading-relaxed text-ink-faint">
                {AMPLITUDE_CAVEAT}
              </p>
              <p className="text-[11px] leading-relaxed text-ink-faint">
                {RULES_FOOTNOTE}
              </p>
            </div>
          </div>
        </div>

        <footer className="border-t border-edge-soft px-6 py-3 text-[10px] text-ink-faint">
          There are {STAGE_COUNT} stages. Each one keeps the rules of the stages
          before it and adds one mechanic.
        </footer>
      </div>
    </div>
  );
}

export interface RulesDialogProps {
  /** Stage to open on. */
  level?: number;
  /** Text on the trigger. */
  triggerLabel?: string;
  /** Classes for the trigger, so a call site can match its own button styles. */
  triggerClassName?: string;
}

/**
 * Trigger-shaped wrapper. Owns the open state so a call site can drop in a
 * button and nothing else; the dialog itself is `RulesModal`, so there is one
 * rules screen in the app rather than two that drift apart.
 */
export function RulesDialog({
  level = 0,
  triggerLabel = "Rules",
  triggerClassName,
}: RulesDialogProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);

  // Return focus to whatever opened the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      triggerRef.current?.focus();
    };
  }, [open]);

  return (
    <>
      {/* The trigger is always this component's own <button>, never a slotted
          element: a call site that passed a <Button> through `trigger` would
          nest one button inside another, which is invalid and breaks focus. */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "rounded-md border border-edge px-3 py-2 font-display text-[11px] tracking-[0.14em] text-ink-dim",
          "hover:border-primary/50 hover:text-primary",
          triggerClassName,
        )}
      >
        {triggerLabel}
      </button>
      {open && <RulesModal level={level} onClose={() => setOpen(false)} />}
    </>
  );
}