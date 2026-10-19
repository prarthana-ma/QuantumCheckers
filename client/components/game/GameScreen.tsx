"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BoardMsg, ClientMessage, GameOverMsg, GameState, Square } from "@/types/game";
import { Resign } from "@/types/game";
import { ActionPanel } from "./ActionPanel";
import { CollapseReveal, type HistoryEntry } from "./CollapseReveal";
import { Hud } from "./Hud";
import { QuantumBoard, type Selection } from "./QuantumBoard";
import { ResultScreen } from "./ResultScreen";
import { RulesModal } from "./RulesModal";
import { UnlockModal } from "./UnlockModal";
import { describeAction, seatColorName } from "./board-model";
import { canPlay } from "./board-interaction";
import type { ConnectionState } from "./Connection";
import { useSound, type SfxCue } from "./sound";
import { useMusic } from "./music";
import {
  hasSeenUnlock,
  highestUnlockedLevel,
  markUnlockSeen,
  readProgress,
  recordGame,
} from "./progress";
import { MAX_LEVEL, stageDef } from "@/lib/stages";

export interface GameScreenProps {
  /** The authoritative state. This screen renders it; it never derives it. */
  state: GameState;
  /** Send one client message. The screen never applies its own move locally. */
  send: (msg: ClientMessage) => void;
  submitting?: boolean;
  /** Optional: the `GameOver` frame, when the hook has one. */
  gameOver?: GameOverMsg | null;
  /** Optional: socket status. Defaults to live when not supplied. */
  connection?: ConnectionState;
  /** Optional: the last server `Error`, surfaced verbatim. */
  error?: { message: string; code: string } | null;
  /** Optional: restart the game. */
  onRematch?: () => void;
  /** Optional: leave the game screen. */
  onExit?: () => void;
}

const HISTORY_LIMIT = 64;

/**
 * The game screen.
 *
 * Two rules from the frozen protocol shape everything here:
 *
 *  1. **Legality comes from the server.** Every highlight, every target, every
 *     enabled button is a read of `state.legal`. Nothing decides whether a move is
 *     legal, and a refused move is surfaced as the server's `Error` — the board
 *     never moves optimistically.
 *  2. **`last_event` and `last_action` are the record.** The move log and the
 *     collapse reveal read those two fields verbatim. A local history of frames we
 *     have already received exists purely so the reveal can be stepped through; we
 *     never reconstruct an action we were not told about.
 */
export function GameScreen({
  state,
  send,
  submitting = false,
  gameOver = null,
  connection = "open",
  error = null,
  onRematch,
  onExit,
}: GameScreenProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [reveal, setReveal] = useState<{ before: Square[]; after: Square | null } | null>(null);
  const [revealNonce, setRevealNonce] = useState(0);
  const [showRules, setShowRules] = useState(false);
  const [showUnlock, setShowUnlock] = useState(false);
  const [overDismissed, setOverDismissed] = useState(false);
  const [turnNonce, setTurnNonce] = useState(0);

  const historyRef = useRef<HistoryEntry[]>([]);
  const lastCollapsePly = useRef<number | null>(null);
  const lastTurn = useRef<number | null>(null);
  const previousBoard = useRef<BoardMsg | null>(null);
  const sound = useSound();
  const music = useMusic();

  const level = state.board.level;
  const stage = stageDef(level);
  const yourTurn = canPlay(state);
  const interactive = yourTurn && connection === "open" && !submitting && !showRules && !showUnlock;

  /** Play a cue, unless sound is muted. `useSound.play` checks the flag itself. */
  const cue = useCallback((c: SfxCue) => sound.play(c), [sound]);

  // --- turn change: the one HUD sweep ---------------------------------------
  useEffect(() => {
    if (lastTurn.current === null) {
      lastTurn.current = state.turn;
      return;
    }
    if (lastTurn.current === state.turn) return;
    lastTurn.current = state.turn;
    setTurnNonce((n) => n + 1);
  }, [state.turn]);

  // --- collapse reveal: once per new collapse event -------------------------
  useEffect(() => {
    const event = state.last_event;
    if (!event) return;
    if (lastCollapsePly.current === event.ply) return;
    lastCollapsePly.current = event.ply;
    const before = event.chances.map(([square]) => square).filter(([row, col]) => row >= 0 && col >= 0);
    setReveal({ before, after: event.kept[0] >= 0 && event.kept[1] >= 0 ? event.kept : null });
    setRevealNonce((n) => n + 1);
    cue("collapse");
  }, [state.last_event, cue]);

  // --- session log, built only from frames already received -------------------
  useEffect(() => {
    if (state.ply === 0 && !state.last_action) return;
    const last = historyRef.current[historyRef.current.length - 1];
    if (last && last.ply === state.ply) {
      if (last.event !== state.last_event || last.action !== state.last_action) {
        historyRef.current[historyRef.current.length - 1] = {
          key: `${state.ply}`,
          ply: state.ply,
          action: state.last_action,
          event: state.last_event,
        };
      }
      return;
    }
    historyRef.current = [
      ...historyRef.current,
      { key: `${state.ply}`, ply: state.ply, action: state.last_action, event: state.last_event },
    ].slice(-HISTORY_LIMIT);
  }, [state.ply, state.last_action, state.last_event]);

  const [historyVersion, setHistoryVersion] = useState(0);
  useEffect(() => setHistoryVersion((v) => v + 1), [state.ply]);

  // The array is mutated in place above, so its identity never changes; the
  // version counter is what tells React to re-read it.
  const history = useMemo(() => historyRef.current, [historyVersion]);
  // eslint-disable-next-line react-hooks/exhaustive-deps

  const counters = useMemo(() => {
    let collapses = 0;
    let observes = 0;
    let splits = 0;
    for (const entry of historyRef.current) {
      if (entry.event) {
        collapses += 1;
        if (entry.event.cause === "observe") observes += 1;
      }
      if (entry.action?.kind === "spread") splits += 1;
    }
    return { collapses, observes, splits };
  }, [historyVersion]);

  // Remember the previous board so the next diff has something to compare against.
  useEffect(() => {
    previousBoard.current = state.board;
  }, [state.board]);

  // --- any state change invalidates the armed action -------------------------
  useEffect(() => {
    const continuation = state.board.continuation_piece;
    const action = continuation ? state.legal.find((action) => action.piece_id === continuation) : undefined;
    setSelection(action ? { origin: action.origin, piece_id: action.piece_id, mode: "move" } : null);
  }, [state.ply, state.legal]);

  // --- unlock modal, once per browser ----------------------------------------
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (stage.unlock && !hasSeenUnlock(level)) setShowUnlock(true);
  }, [level, stage.unlock]);

  const closeUnlock = useCallback(() => {
    markUnlockSeen(level);
    setShowUnlock(false);
  }, [level]);

  // --- game over -------------------------------------------------------------
  useEffect(() => {
    if (state.status !== "over") return;
    const won = gameOver?.result != null && state.you !== null && gameOver.result === state.you;
    recordGame(readProgress(), level, won);
    setOverDismissed(false);
    if (won) cue("win");
    else cue("lose");
  }, [state.status, state.you, gameOver, level, cue]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelection(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const highestUnlocked = useMemo(() => {
    if (typeof window === "undefined") return level;
    return highestUnlockedLevel(readProgress(), MAX_LEVEL);
  }, [state.status, level]);

  const showResult = state.status === "over" && !overDismissed && !showRules && !showUnlock;

  return (
    <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-3 bg-background p-3 sm:p-4">
      <Hud
        state={state}
        connection={connection}
        collapseCount={counters.collapses}
        observeCount={counters.observes}
        splitCount={counters.splits}
        turnNonce={turnNonce}
        onOpenRules={() => setShowRules(true)}
        // The stage badge navigates back to the stage picker when the host
        // supplies one; without a host it stays inert rather than pretending.
        onOpenStages={onExit ?? (() => undefined)}
        muted={sound.muted}
        musicEnabled={music.enabled}
        onToggleMusic={music.toggle}
        onToggleSound={() => {
          sound.toggle();
          cue("click");
        }}
      />

      <TurnBanner
        aiFailed={!!error}
        state={state}
        connection={connection}
        onOpenRules={() => setShowRules(true)}
      />

      {/* Hardware-backed collapses are visible: which backend resolved the piece, and
          a pending state while the QPU job runs. Hidden on the ordinary offline game. */}
      <QuantumStrip state={state} />

      {/* A refused move changes nothing, so we say exactly what the server said
          and leave the board where it was. */}
      {error && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-md border border-destructive/45 bg-destructive/10 px-3 py-2"
        >
          <span className="label-inst text-destructive">move refused</span>
          <span className="text-xs">{error.message}</span>
          <span className="tnum ml-auto text-[10px] text-ink-faint">{error.code}</span>
        </div>
      )}

      {reveal && (
        <CollapseReveal
          state={state}
          reveal={reveal}
          onClearReveal={() => setReveal(null)}
          history={history}
        />
      )}

      <main className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row lg:overflow-hidden">
        {/* The board column takes whatever height is left and no more, so the
            square can letterbox into it instead of pushing the page taller. */}
        <div className="flex min-h-0 min-w-0 shrink-0 flex-col lg:flex-1">
          <QuantumBoard
            state={state}
            selection={selection}
            onSelect={(next) => {
              setSelection(next);
              cue(next ? "select" : "click");
            }}
            send={send}
            previousBoard={previousBoard.current}
            reveal={reveal}
            revealNonce={revealNonce}
            coherence={state.coherence}
            coherenceMax={state.board.decoherence_ticks ?? 6}
            interactive={interactive}
            onCue={cue}
          />
        </div>

{/* The right column carries every non-board readout. On desktop it is a
            column of the viewport height with the panel scrolling inside it, so
            the board, the move log and the way out are all on screen together
            and no gameplay content needs the page to scroll. */}
        <div className="flex w-full flex-col gap-3 lg:h-full lg:w-[19rem] lg:shrink-0">
          <ActionPanel
            state={state}
            selection={selection}
            onOpenRules={() => setShowRules(true)}
            onResign={() => send(Resign())}
            interactive={interactive}
            busy={submitting || !!state.quantum_pending || !!state.quantum?.pending}
            onRetry={state.mode?.startsWith("ai-") && state.turn !== state.you && error && state.status === "playing" ? () => send({ type: "RetryAI" }) : undefined}
          />

          <MoveLog state={state} />

          <footer className="flex flex-wrap items-center justify-between gap-2 pt-1 pb-2 text-[10px] text-ink-faint">
            <span>
              Board {state.board.board_size} by {state.board.board_size} · engine{" "}
              <span className="tnum">{state.board.engine}</span>
            </span>
            <span className="flex items-center gap-3">
              <span>
                {highestUnlocked >= MAX_LEVEL
                  ? "All stages unlocked"
                  : `Stage ${highestUnlocked + 1} unlocked`}
              </span>
              {onExit && (
                <button
                  type="button"
                  onClick={onExit}
                  className="font-display tracking-[0.14em] underline-offset-2 hover:text-ink-dim hover:underline"
                >
                  Leave
                </button>
              )}
            </span>
          </footer>
        </div>
      </main>

      {showRules && <RulesModal level={level} onClose={() => setShowRules(false)} />}

      {showUnlock && (
        <UnlockModal
          level={level}
          onClose={closeUnlock}
          onOpenRules={() => {
            setShowUnlock(false);
            setShowRules(true);
          }}
        />
      )}

      {showResult && (
        <ResultScreen
          state={state}
          gameOver={gameOver}
          onRematch={() => {
            setOverDismissed(true);
            onRematch?.();
          }}
          onBackToStages={() => {
            setOverDismissed(true);
            onExit?.();
          }}
        />
      )}
    </div>
  );
}

/**
 * The live-quantum strip.
 *
 * Two honest readouts, and nothing more:
 *
 *  - while a measurement runs, a clearly-labelled pending state naming the backend;
 *  - after a hardware collapse, the backend and job that produced the square.
 *
 * It renders nothing when the room is the ordinary offline engine
 * (`quantum.enabled === false`), so a plain game is unchanged.
 */
function QuantumStrip({ state }: { state: GameState }) {
    const quantum = state.quantum;
    if (!quantum?.enabled) return null;

    const pending = state.quantum_pending ?? quantum.pending;
    const last = quantum.last;

    if (pending) {
        return (
            <div
                role="status"
                aria-live="polite"
                className="flex flex-wrap items-center gap-3 rounded-md border border-primary/40 bg-primary/5 px-4 py-2"
            >
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
                <span
                    className="label-inst text-primary"
                    title="Measurement (collapse) resolves a spread piece to one square."
                >
                    measuring on hardware
                </span>
                <span className="text-xs text-ink-dim">
                    Submitting one shot to IBM Quantum{quantum.backend ? ` · ${quantum.backend}` : ""}.
                    The board updates when the measurement returns.
                </span>
            </div>
        );
    }

    if (!last) return null;

    return (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-edge-soft bg-card px-4 py-2">
            <span
                className="label-inst text-primary"
                title="Measurement (collapse) resolves a spread piece to one square."
            >
                QPU collapse
            </span>
            <span className="tnum text-[11px] text-ink-dim">
                {last.backend} · job {last.job_id}
            </span>
            <span className="tnum text-[10px] text-ink-faint">
                bitstring {last.bitstring}
            </span>
            <span className="ml-auto text-[10px] text-ink-faint">
                one shot per collapse · circuit re-prepared each time
            </span>
        </div>
    );
}

/**
 * The turn banner: the one sentence that says what to do next.
 */
function TurnBanner({
  aiFailed,
  state,
  connection,
  onOpenRules,
}: {
  aiFailed: boolean;
  state: GameState;
  connection: ConnectionState;
  onOpenRules: () => void;
}) {
  const stage = stageDef(state.board.level);
  const spectator = state.you === null;
  const yourTurn = canPlay(state);

  let text: string;
  let tone = "var(--color-ink-dim)";

  if (state.status === "over") {
    text = "The game is over.";
  } else if (state.quantum_pending || state.quantum?.pending) {
    text = "Resolving the quantum measurement. Your board will update when it finishes.";
  } else if (state.board.continuation_piece && yourTurn) {
    text = "Continue the capture with the same piece. Tap its next highlighted landing square.";
    tone = "var(--color-primary)";
  } else if (yourTurn && state.legal.some(action => action.kind === "capture")) {
    text = "Capture required. Select a highlighted piece, then its landing square. Other pieces cannot move this turn.";
    tone = "var(--color-primary)";
  } else if (state.status === "waiting") {
    text = "Waiting for the room to fill.";
  } else if (spectator) {
    text = "Spectating. The board updates as moves are applied.";
  } else if (!yourTurn && state.mode?.startsWith("ai-") && state.turn === 1) {
    text = aiFailed ? "AI move paused. Use Retry AI to try again." : "Opponent is thinking…";
    tone = "var(--color-primary)";
  } else if (!yourTurn) {
    text = `Your opponent (${seatColorName(state.turn)}) to move.`;
  } else {
    const spread = state.board.pieces.filter(
      (p) => p.owner === state.turn && p.uncertain,
    ).length;
    if (spread === 0) {
      text = `Your turn. Move the ${seatColorName(state.turn)} pieces.`;
    } else if (state.board.allow_observe) {
      text =
        `Your turn. ${spread} of your pieces ${spread === 1 ? "is" : "are"} split. ` +
        "Observing one costs your whole turn.";
    } else {
      text =
        `Your turn. ${spread} of your pieces ${spread === 1 ? "is" : "are"} split. ` +
        "Select a branch to move it; captures trigger measurement.";
    }
    tone = "var(--color-primary)";
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-edge-soft bg-card px-4 py-2.5">
      <span className={`h-2 w-2 shrink-0 rounded-full ${text === "Opponent is thinking…" ? "animate-pulse" : ""}`} style={{ background: tone }} />
      <p className="text-sm" style={{ color: tone }}>
        {text}
      </p>

      {connection !== "open" && (
        <p className="text-[11px] text-ink-dim">
          Socket {connection}. Moves are refused while the link is down.
        </p>
      )}

      <button
        type="button"
        onClick={onOpenRules}
        className="ml-auto rounded-sm border border-edge px-2.5 py-1 font-display text-[10px] tracking-[0.14em] text-ink-dim hover:border-primary/50 hover:text-primary"
      >
        {`What is ${stage.tag.toLowerCase()}?`}
      </button>
    </div>
  );
}

/**
 * The move log. Renders `last_action` verbatim (PROTOCOL.md §3.2) and never
 * reconstructs an action to fill a gap.
 */
function MoveLog({ state }: { state: GameState }) {
  const action = state.last_action;
  const spreadCount = state.board.pieces.filter((p) => p.uncertain).length;

  return (
    <div className="flex min-h-[2.1rem] flex-wrap items-center gap-3 rounded-md border border-edge-soft bg-card px-4 py-1.5">
      <span className="label-inst text-[9px]">last action</span>
      {action ? (
        <span className="tnum text-[11px] text-ink-dim">
          ply {state.ply} · {describeAction(action)}
        </span>
      ) : (
        <span className="text-[11px] text-ink-faint">No action applied yet.</span>
      )}
      {spreadCount > 0 && (
        <span className="ml-auto text-[10px] text-primary">
          {spreadCount} piece{spreadCount > 1 ? "s" : ""} unresolved
        </span>
      )}
    </div>
  );
}

export type { Selection, HistoryEntry, ConnectionState };
