"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ActionMsg,
  BoardMsg,
  ClientMessage,
  GameState,
  Square,
} from "@/types/game";
import { BoardSquare, EMPTY_ROLE, type SquareRole } from "./BoardSquare";
import {
  collapseFlickerSquares,
  deriveMotion,
  primarySite,
  type BoardMotion,
  type PieceTransition,
} from "./motion";
import { colLabel, sameSquare, sqKey, squareName } from "./board-model";

import {
  actionMessage,
  availableModes,
  boardClick,
  boardTargets,
  splitShortcut,
  MODE_HINT,
  MODE_LABEL,
  selectedActions,
  pieceCanActAt,
  type Selection,
  selectionsAt,
} from "./board-interaction";
export type { Selection } from "./board-interaction";

export interface QuantumBoardProps {
  state: GameState;
  selection: Selection | null;
  onSelect: (selection: Selection | null) => void;
  send: (msg: ClientMessage) => void;
  /** Previous frame's board, so the board can derive what moved. */
  previousBoard: BoardMsg | null;
  /** Squares the last collapse could have been on, and where it landed. */
  reveal: { before: Square[]; after: Square | null } | null;
  /** Bumped when a collapse is being animated, to retrigger the flicker. */
  revealNonce: number;
  coherence: Record<string, number>;
  coherenceMax: number;
  interactive: boolean;
  /** Called with a cue when the board's own state changes. */
  onCue?: (cue: "move" | "capture" | "split" | "collapse") => void;
}

type RoleMap = Map<string, SquareRole>;

export function QuantumBoard({
  state,
  selection,
  onSelect,
  send,
  previousBoard,
  reveal,
  revealNonce,
  coherence,
  coherenceMax,
  interactive,
  onCue,
}: QuantumBoardProps) {
  const size = state.board.board_size;
  const frameRef = useRef<HTMLDivElement>(null);
  const [frameSize, setFrameSize] = useState(520);
  const [motion, setMotion] = useState<BoardMotion | null>(null);

  // Measure the FRAME, never the square. The square is `aspect-square`, so its
  // own height is derived from its width — measuring it would make
  // `min(width, height)` collapse to `width` every time, and the board could
  // never shrink to fit a short viewport. The frame is the box the board is
  // allowed to fill, so that is what has to be measured.
  useEffect(() => {
    const node = frameRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const side = Math.min(
          entry.contentRect.width,
          entry.contentRect.height,
        );
        if (side > 0) setFrameSize(side);
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const gap = size <= 6 ? 4 : size <= 10 ? 3 : 2;
  const gutter = size <= 8 ? 18 : 14;
  const pad = gutter + 6;
  // The square is sized in px from the frame, not by `aspect-square` + width.
  // That is what lets it letterbox inside a frame that is wider than it is tall
  // — at 720p, height is the binding constraint and width is not.
  const board = Math.max(160, Math.floor(frameSize));
  const inner = Math.max(120, board - pad * 2);
  const cell = Math.floor((inner - gap * (size - 1)) / size);
  const pitch = cell + gap;

  const roles = useMemo(() => buildRoles(state, selection), [state, selection]);

  // Derive motion on every state change, then clear it once the animation has
  // run. Clearing matters: without it, a re-render would replay the slide.
  const lastPly = useRef<number | null>(null);
  useEffect(() => {
    const next = deriveMotion(previousBoard, state.board);
    setMotion(next);

    if (state.ply !== lastPly.current) {
      lastPly.current = state.ply;
      const action = state.last_action;
      if (action) {
        if (action.kind === "capture") onCue?.("capture");
        else if (action.kind === "move") onCue?.("move");
        else if (action.kind === "spread") onCue?.("split");
        else onCue?.("collapse");
      }
    }

    const timer = setTimeout(() => setMotion(null), 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.board, state.ply, state.last_action]);

  // The collapse flicker squares, ordered by chance so the likeliest square
  // flickers first. This is what makes the reveal feel like a settling rather
  // than a strobe.
  const flicker = useMemo(() => {
    const event = state.last_event;
    if (!reveal || !event)
      return {
        flicker: new Map<string, number>(),
        kept: null as string | null,
      };
    const ordered = collapseFlickerSquares(
      event.chances.map(([sq, w]) => [sq, w] as [Square, number]),
      reveal.after ?? [0, 0],
    );
    const map = new Map<string, number>();
    for (const entry of ordered) {
      if (reveal.after && sameSquare(entry.square, reveal.after)) continue;
      map.set(sqKey(entry.square), entry.delay);
    }
    return { flicker: map, kept: reveal.after ? sqKey(reveal.after) : null };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealNonce, state.last_event, reveal]);

  const lastTap = useRef<{ square: Square; time: number } | null>(null);
  const handleSelect = useCallback(
    (square: Square, pointerTap: boolean) => {
      if (!interactive) {
        lastTap.current = null;
        return;
      }
      const now = performance.now();
      const previous = lastTap.current;
      const twice =
        pointerTap &&
        previous &&
        sameSquare(previous.square, square) &&
        now - previous.time < 350;
      lastTap.current = pointerTap && !twice ? { square, time: now } : null;
      const result =
        (twice ? splitShortcut(state, selection, square) : null) ??
        boardClick(state, selection, square);
      if (result.kind === "commit") {
        lastTap.current = null;
        send(result.message);
        onSelect(null);
      } else {
        onSelect(result.kind === "select" ? result.selection : null);
      }
    },
    [interactive, selection, send, onSelect, state],
  );

  // Row 0 renders at the TOP of the board and row 0 is rank 1 (`squareName` reads
  // the digit as `row + 1`, PROTOCOL.md §3.1), so the gutter counts 1..size going
  // down. Counting up from `size` here would point every rank at the wrong row.
  const coords = useMemo(
    () => ({
      files: Array.from({ length: size }, (_, i) => colLabel(i)),
      ranks: Array.from({ length: size }, (_, i) => String(i + 1)),
    }),
    [size],
  );

  return (
    <div className="flex h-[min(calc(100vw+6rem),42rem)] min-h-0 w-full shrink-0 flex-col gap-2 lg:h-auto lg:flex-1">
      <div
        ref={frameRef}
        className="relative flex min-h-0 w-full flex-1 items-center justify-center overflow-hidden"
      >
        <div
          className="relative shrink-0"
          style={{ width: board, height: board }}
        >
          <div
            className="pointer-events-none absolute top-0 left-0 flex flex-col text-[9px] font-medium text-ink-faint"
            style={{ width: gutter, paddingTop: pad, paddingLeft: 2 }}
            aria-hidden
          >
            {coords.ranks.map((rank, i) => (
              <div
                key={rank}
                className="tnum grid place-items-center"
                style={{ height: cell, marginBottom: i < size - 1 ? gap : 0 }}
              >
                {rank}
              </div>
            ))}
          </div>

          <div
            className="pointer-events-none absolute bottom-0 left-0 flex text-[9px] font-medium text-ink-faint"
            style={{ paddingLeft: pad, paddingBottom: 2 }}
            aria-hidden
          >
            {coords.files.map((file, i) => (
              <div
                key={file}
                className="grid place-items-center"
                style={{ width: cell, marginRight: i < size - 1 ? gap : 0 }}
              >
                {file}
              </div>
            ))}
          </div>

          <div
            role="grid"
            aria-label={`Quantum checkers board, ${size} by ${size}`}
            className="absolute"
            style={{
              top: pad,
              left: pad,
              display: "grid",
              gridTemplateColumns: `repeat(${size}, ${cell}px)`,
              gridTemplateRows: `repeat(${size}, ${cell}px)`,
              gap: `${gap}px`,
            }}
          >
            {Array.from({ length: size * size }, (_, index) => {
              const row = Math.floor(index / size);
              const col = index % size;
              const square: Square = [row, col];
              const key = sqKey(square);
              const role = roles.get(key) ?? EMPTY_ROLE;

              // The transition that lands on this square, if any piece moved here.
              const transition = transitionForSquare(
                state.board,
                motion,
                square,
              );

              const isKept = flicker.kept === key;
              const flickerDelay = flicker.flicker.get(key);
              const revealState: "flicker" | "kept" | null = isKept
                ? "kept"
                : flickerDelay !== undefined
                  ? "flicker"
                  : null;

              const pieceHere = pieceAtSquare(state, square);
              const entangled =
                !!pieceHere && !!motion?.entangled.has(pieceHere.piece_id);

              return (
                <BoardSquare
                  key={`${key}-${revealNonce}`}
                  state={state}
                  row={row}
                  col={col}
                  role={role}
                  selected={
                    !!selection &&
                    (pieceHere?.piece_id === selection.piece_id ||
                      sameSquare(selection.splitTarget, square))
                  }
                  transition={transition}
                  entangled={entangled}
                  reveal={revealState}
                  revealDelay={flickerDelay ?? 0}
                  coherence={coherence[key] ?? null}
                  coherentMax={coherenceMax}
                  onSelect={handleSelect}
                  cell={cell}
                  interactive={interactive}
                  onHover={() => undefined}
                />
              );
            })}
          </div>
        </div>
      </div>
      <div
        data-board-controls
        className="h-24 shrink-0 overflow-hidden lg:h-14 rounded-lg border border-edge bg-card px-3 py-2"
        aria-live="polite"
      >
        {!selection ? (
          <p className="flex h-full items-center justify-center text-center text-sm text-ink-dim">
            {interactive
              ? state.board.level > 0
                ? "Tap to move · Double-tap a piece to split."
                : "Tap a piece, then tap a highlighted square."
              : state.quantum_pending
                ? "Measuring on hardware…"
                : "Waiting for the next move."}
          </p>
        ) : (
          <div className="flex h-full flex-col justify-center gap-1">
            <div className="flex min-h-10 shrink-0 items-center gap-2 overflow-x-auto whitespace-nowrap">
              <span className="text-sm font-semibold text-primary">
                {squareName(selection.origin)}
              </span>
              {selectionsAt(state, selection.origin).length > 1 &&
                selectionsAt(state, selection.origin).map((option) => (
                  <button
                    key={option.piece_id}
                    type="button"
                    disabled={!interactive}
                    aria-pressed={option.piece_id === selection.piece_id}
                    onClick={() => onSelect(option)}
                    className="min-h-10 shrink-0 rounded-md border border-edge px-2 text-xs text-ink-dim"
                  >
                    {option.piece_id}
                  </button>
                ))}
              {availableModes(state, selection).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  disabled={!interactive}
                  aria-pressed={selection.mode === mode}
                  onClick={() =>
                    onSelect({
                      origin: selection.origin,
                      piece_id: selection.piece_id,
                      mode,
                    })
                  }
                  className={`min-h-10 rounded-md border px-3 py-2 text-sm disabled:opacity-40 ${selection.mode === mode ? "border-primary bg-primary/20 text-primary" : "border-edge text-ink-dim hover:border-primary"}`}
                >
                  {MODE_LABEL[mode]}
                </button>
              ))}
              {(selection.mode === "observe" ||
                (selection.mode === "spread" &&
                  selectedActions(state, selection).length === 1)) && (
                <button
                  type="button"
                  disabled={
                    !interactive ||
                    selectedActions(state, selection).length === 0
                  }
                  className="min-h-10 shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-40"
                  onClick={() => {
                    const action = selectedActions(state, selection)[0];
                    if (interactive && action) {
                      send(actionMessage(action));
                      onSelect(null);
                    }
                  }}
                >
                  {selection.mode === "spread"
                    ? "Confirm split"
                    : "Measure piece"}
                </button>
              )}
              <button
                type="button"
                onClick={() => onSelect(null)}
                className="ml-auto min-h-10 shrink-0 px-2 text-sm text-ink-dim hover:text-foreground"
              >
                Cancel
              </button>
            </div>
            <div className="min-h-8 lg:hidden">
              <p className="line-clamp-2 text-xs leading-4 text-ink-dim">
                {selection.mode === "merge" && !selection.mergeSource
                  ? "Tap another highlighted branch of this same piece, then its destination."
                  : MODE_HINT[selection.mode]}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The transition to play on a square: the one whose `to` is this square. When
 * two pieces land on the same square only the first is animated, which is rare
 * and harmless.
 */
function transitionForSquare(
  board: BoardMsg,
  motion: BoardMotion | null,
  square: Square,
): PieceTransition | null {
  if (!motion) return null;
  for (const piece of board.pieces) {
    const transition = motion.transitions.get(piece.piece_id);
    if (!transition) continue;
    if (sameSquare(transition.to, square) && transition.kind !== "hold")
      return transition;
  }
  return null;
}

/** Highlight every legal destination for the selected piece and action mode. */
function buildRoles(state: GameState, selection: Selection | null): RoleMap {
  const map: RoleMap = new Map();
  const entry = (square: Square) => {
    const key = sqKey(square);
    if (!map.has(key)) map.set(key, { ...EMPTY_ROLE });
    return map.get(key)!;
  };
  for (const piece of state.board.pieces) {
    if (piece.owner !== state.turn) continue;
    for (const [site] of piece.sites) {
      if (pieceCanActAt(state, piece.piece_id, site))
        entry(site).selectable = true;
    }
  }
  for (const { square, action } of boardTargets(state, selection)) {
    const role = entry(square);
    role.target = true;
    role.isMergePartner =
      action.kind === "merge" &&
      (!action.other_origin || !selection?.mergeSource);
    role.isLanding = !role.isMergePartner;
    if (action.kind === "capture") entry(action.jumped).isJumped = true;
  }
  for (const action of selectedActions(state, selection)) {
    if (action.kind === "spread")
      for (const [square] of action.sites) entry(square).inSpreadPreview = true;
  }
  return map;
}

function pieceAtSquare(state: GameState, square: Square) {
  for (const piece of state.board.pieces) {
    if (
      piece.sites.some(([sq]) => sq[0] === square[0] && sq[1] === square[1])
    ) {
      return piece;
    }
  }
  return undefined;
}
