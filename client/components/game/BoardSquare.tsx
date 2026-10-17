"use client";

import type { ActionMsg, GameState, Square } from "@/types/game";
import { cn } from "@/lib/utils";
import {
  isPlayable,
  occupancyAt,
  piecesAt,
  sameSquare,
  sqKey,
  squareName,
} from "./board-model";
import type { PieceTransition } from "./motion";
import type { ActionMsg as LegalAction } from "@/types/game";

/** What a square can do right now, derived only from `state.legal`. */
export interface SquareRole {
  selectable: boolean;
  target: boolean;
  isLanding: boolean;
  isJumped: boolean;
  isMergePartner: boolean;
  inSpreadPreview: boolean;
}

export const EMPTY_ROLE: SquareRole = {
  selectable: false,
  target: false,
  isLanding: false,
  isJumped: false,
  isMergePartner: false,
  inSpreadPreview: false,
};

/** Structural minimum the square needs. A narrow state still type-checks. */
export type SquareState = Pick<GameState, "board" | "occupancy" | "legal">;

export interface BoardSquareProps {
  state: SquareState;
  row: number;
  col: number;
  role: SquareRole;
  selected: boolean;
  /** The piece transition to play on this square this frame, if any. */
  transition: PieceTransition | null;
  /** Part of one spread piece — drawn as a link to its other sites. */
  entangled: boolean;
  /** Collapse reveal state for this square. */
  reveal: "flicker" | "kept" | null;
  /** Flicker stagger in ms, from the collapse's chance ordering. */
  revealDelay: number;
  coherence: number | null;
  coherentMax: number;
  onSelect: (square: Square, pointerTap: boolean) => void;
  onHover: (square: Square | null) => void;
  cell: number;
  interactive: boolean;
}

/**
 * One square.
 *
 * Legibility rule: a square must read its quantum state in one glance on a 4x4
 * and still on a 16x16. Three non-competing channels carry it —
 *
 *   1. SIZE    the disc grows with the chance on this square
 *   2. NUMERAL the chance as a percentage, dropped below ~34px
 *   3. TEXTURE certain = solid fill, spread = dashed ring + hatch
 *
 * A player never has to decode a colour gradient to know how certain a square is.
 */
export function BoardSquare({
  state,
  row,
  col,
  role,
  selected,
  transition,
  entangled,
  reveal,
  revealDelay,
  coherence,
  coherentMax,
  onSelect,
  onHover,
  cell,
  interactive,
}: BoardSquareProps) {
  const square: Square = [row, col];
  const playable = isPlayable(state as GameState, row, col);
  const [chance0, chance1] = occupancyAt(state as GameState, square);
  const claims = piecesAt(state.board, square);

  const topChance = Math.max(chance0, chance1);
  const topSeat = chance0 >= chance1 ? 0 : 1;
  const contested = chance0 > 0.01 && chance1 > 0.01;

  // The numeral carries a "%" now, so it needs a little more room than the bare
// number did. Below this the disc alone is the read.
  const showNumeral = cell >= 40 && topChance > 0.005 && topChance < 0.999;
  const kingHere = claims.some(({ piece }) => piece.king_sites?.some(([site]) => sameSquare(site, square)));
  const discRadius = Math.min(cell * 0.46, 8 + topChance * (cell * 0.3));
  const isCertain = claims.length > 0 && claims.every((c) => c.chance >= 0.999);
  const anySpread = claims.some((c) => c.chance < 0.999);

  const seatColor = topSeat === 0 ? "var(--color-seat-0)" : "var(--color-seat-1)";
  const label = buildLabel(squareName(square), claims, chance0, chance1, role, reveal) + (kingHere ? ", king" : "");

  // Motion class for this square, from the piece that changed here.
  const motion = transition
    ? transitionClass(transition, cell, gapFor(cell))
    : null;

  return (
    <button
      type="button"
      onClick={(event) => onSelect(square, event.detail > 0)}
      onMouseEnter={() => onHover(square)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(square)}
      onBlur={() => onHover(null)}
      aria-label={label}
      aria-pressed={selected}
      title={
        coherence !== null
          ? "Coherence tracks how long a spread piece can remain unresolved."
          : label
      }
      data-square={squareName(square)}
      data-board-color={playable ? "dark" : "light"}
      data-target={role.target || undefined}
      data-selectable={role.selectable || undefined}
      data-king={kingHere || undefined}
      tabIndex={role.selectable || role.target || selected ? 0 : -1}
      disabled={!interactive}
      className={cn(
        "group relative isolate overflow-hidden rounded-[3px]",
        playable ? "bg-[#303036]" : "bg-[#17171c]",
        "touch-manipulation focus:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        role.selectable || role.target ? "cursor-pointer" : "cursor-default",
        !interactive && "cursor-default",
        !playable && "opacity-50",
        selected && "bg-primary/22",
        !selected && role.target && "bg-primary/12",
        !selected && !role.target && role.selectable && "hover:bg-primary/20",
        reveal === "kept" && "bg-primary/30",
      )}
      style={{ ["--cell" as string]: `${cell}px` }}
    >
      {(
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[3px] ring-1 ring-inset ring-white/[0.06]"
        />
      )}

{/* Landing marker: a diamond, so it can never be mistaken for a piece. */}
{role.isLanding && (
  <span aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
    {/* A glow ring under the diamond. The ring is what the eye catches from a
        glance across the board; the diamond is what you read once you are
        close. Both sit on the armed square only, so nothing else on the board
        is moving. */}
    <span className="absolute inset-0 animate-target-glow rounded-[3px] ring-2 ring-inset ring-primary" />
    <span className="block h-[32%] w-[32%] rotate-45 rounded-[2px] border-2 border-primary bg-primary/25" />
  </span>
)}

      {/* The square a capture would jump over. */}
      {role.isJumped && (
        <span aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="absolute inset-[12%] rounded-full border border-dashed border-foreground/60" />
          <span className="block h-1.5 w-1.5 rounded-full bg-foreground" />
        </span>
      )}

{/* Merge partner: a bracket. A different shape from a landing diamond on
          purpose — merging is not landing. */}
{role.isMergePartner && (
  <span aria-hidden className="pointer-events-none absolute inset-1">
    <span className="animate-target-glow absolute inset-0 rounded-[2px] ring-2 ring-inset ring-primary" />
    <span className="absolute inset-0 rounded-[2px] border-2 border-dashed border-primary" />
  </span>
)}

      {/* What this split would become, drawn as a ghost outline. */}
      {role.inSpreadPreview && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-[6%] rounded-full border border-dashed border-primary/70"
        />
      )}

      {/* Selectable squares get a static ring rather than a pulse: a loop that
          runs on every selectable piece would be motion with no new information,
          and on a 4x4 that is 40 simultaneous animations. */}
      {role.selectable && !selected && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[3px] ring-1 ring-inset ring-primary/45"
        />
      )}

      {topChance > 0.005 && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 grid place-items-center"
        >
          <span className={cn("grid place-items-center", motion)}>
            {isCertain && (
              <span
                className="absolute rounded-full"
                style={{
                  width: discRadius * 2,
                  height: discRadius * 2,
                  background:
                    topSeat === 1
                      ? "radial-gradient(circle at 36% 30%, #e9d5ff 0%, var(--color-seat-1) 52%, #6d28d9 100%)"
                      : "radial-gradient(circle at 36% 30%, #ffffff 0%, var(--color-seat-0) 55%, #a1a1aa 100%)",
                }}
              />
            )}

            {anySpread && (
              <>
                <span
                  className="absolute rounded-full"
                  style={{
                    width: discRadius * 2,
                    height: discRadius * 2,
                    background: `radial-gradient(circle at 36% 30%, ${seatColor} 0%, transparent 70%)`,
                    opacity: 0.3 + topChance * 0.5,
                  }}
                />
                {/* Dashed + hatched: "uncertain" is a texture, not just an alpha. */}
                <span
                  className="absolute rounded-full"
                  style={{
                    width: discRadius * 2,
                    height: discRadius * 2,
                    border: `1.5px dashed ${seatColor}`,
                    opacity: 0.4 + topChance * 0.55,
                    backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,0.18) 0 1px, transparent 1px 4px)`,
                  }}
                />
              </>
            )}

            {/* Both seats claim this square: a split ring shows the minority
                claim as an arc, so a 50/50 clash reads as a shape. */}
            {contested && (
              <span
                className="absolute rounded-full"
                style={{
                  width: discRadius * 2.3,
                  height: discRadius * 2.3,
                  background: `conic-gradient(from 180deg, var(--color-seat-0) 0turn ${
                    chance0 / (chance0 + chance1)
                  }turn, var(--color-seat-1) ${chance0 / (chance0 + chance1)}turn 1turn)`,
                  WebkitMask: "radial-gradient(circle, transparent 0 52%, #000 56% 66%, transparent 70%)",
                  mask: "radial-gradient(circle, transparent 0 52%, #000 56% 66%, transparent 70%)",
                }}
              />
            )}

            {showNumeral && (
              <span
                className="tnum relative z-10 font-semibold leading-none"
                style={{
                  fontSize: Math.max(9, Math.min(cell * 0.3, 15)),
                  // Dark ink on a certain piece, light ink on a ghost.
                  color: isCertain ? "#09090b" : "#fafafa",
                }}
              >
                {/* The numeral is a chance, so it carries its unit. A bare "100"
                    reads as a count to anyone meeting the board for the first
                    time. */}
                {Math.round(topChance * 100)}%
              </span>
            )}
          </span>
        </span>
      )}

      {/* One piece spanning several squares: draw the link, and pulse it so the
          entanglement is visible without hovering. */}
      {entangled && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 animate-link-pulse rounded-[3px] ring-1 ring-inset ring-primary/35"
        />
      )}

      {coherence !== null && (
        <CoherenceBadge value={coherence} max={coherentMax} cell={cell} />
      )}
      {kingHere && (
        <span aria-hidden className="pointer-events-none absolute left-1 top-0.5 z-20 text-xs font-bold text-foreground">♔</span>
      )}

      {/* Collapse reveal: a staged flicker across the pre-collapse squares, then
          the kept square holds at full. */}
      {reveal === "flicker" && (
        <span
          aria-hidden
          className="animate-collapse-flick pointer-events-none absolute inset-0 rounded-[3px] bg-primary/35"
          style={{ animationDelay: `${revealDelay}ms` }}
        />
      )}
      {reveal === "kept" && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[3px] ring-2 ring-inset ring-primary"
        />
      )}

      {/* Selection: corner brackets. A machined frame rather than a glow, so the
          armed square stays findable in a crowded position. */}
      {selected && (
        <span aria-hidden className="pointer-events-none absolute inset-0">
          {(
            [
              "left-0 top-0 border-l-2 border-t-2",
              "right-0 top-0 border-r-2 border-t-2",
              "left-0 bottom-0 border-l-2 border-b-2",
              "right-0 bottom-0 border-r-2 border-b-2",
            ] as const
          ).map((pos) => (
            <span key={pos} className={cn("absolute h-2.5 w-2.5 border-primary", pos)} />
          ))}
        </span>
      )}
    </button>
  );
}

/** The class and CSS variables that play one piece transition. */
function transitionClass(
  transition: PieceTransition,
  cell: number,
  gap: number,
): { className: string; vars: Record<string, string> } {
  switch (transition.kind) {
    case "slide": {
      const pitch = cell + gap;
      return {
        className: "animate-piece-slide",
        vars: {
          "--from-x": `${(transition.from[1] - transition.to[1]) * pitch}px`,
          "--from-y": `${(transition.from[0] - transition.to[0]) * pitch}px`,
        },
      };
    }
    case "arc": {
      const pitch = cell + gap;
      return {
        className: "animate-piece-arc",
        vars: {
          "--from-x": `${(transition.from[1] - transition.to[1]) * pitch}px`,
          "--from-y": `${(transition.from[0] - transition.to[0]) * pitch}px`,
          // Two nested transforms: travel along the diagonal, and lift on a
          // separate arc so the piece visibly leaves the board plane.
          "--lift": `${-Math.round(cell * 1.1)}px`,
        },
      };
    }
    case "shimmer":
      return { className: "animate-piece-shimmer", vars: {} };
    case "converge":
    case "hold":
    default:
      return { className: "", vars: {} };
  }
}

/** The gap the board uses at a given cell size; kept in step with QuantumBoard. */
function gapFor(cell: number): number {
  if (cell >= 56) return 4;
  if (cell >= 34) return 3;
  return 2;
}

/**
 * Stage-4 coherence counter. A ring that empties as ticks are lost, and pulses
 * once it reaches a single tick — that is the only moment urgency matters,
 * because at zero the piece collapses without anyone choosing to.
 */
function CoherenceBadge({ value, max, cell }: { value: number; max: number; cell: number }) {
  const safeMax = max > 0 ? max : 6;
  const ratio = Math.max(0, Math.min(1, value / safeMax));
  const r = Math.max(4, Math.min(cell * 0.16, 9));
  const circumference = 2 * Math.PI * r;
  const urgent = value <= 1;

  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute right-[2%] top-[2%] z-20 grid place-items-center",
        urgent && "animate-urgency",
      )}
      style={{ width: r * 2.4, height: r * 2.4 }}
    >
      <svg viewBox="0 0 24 24" className="absolute inset-0 h-full w-full -rotate-90">
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="rgba(9,9,11,0.85)"
          stroke="var(--color-edge)"
          strokeWidth="2"
        />
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
        />
      </svg>
      <span
        className="tnum relative font-semibold leading-none text-primary"
        style={{ fontSize: Math.max(8, Math.min(cell * 0.24, 12)) }}
      >
        {value}
      </span>
    </span>
  );
}

/** The square's spoken label: the accessible channel for everything visual. */
function buildLabel(
  name: string,
  claims: { piece: { piece_id: string; owner: number }; chance: number }[],
  chance0: number,
  chance1: number,
  role: SquareRole,
  reveal: "flicker" | "kept" | null,
): string {
  const parts: string[] = [name];
  if (claims.length === 0) {
    parts.push("empty");
  } else {
    for (const { piece, chance } of claims) {
      parts.push(`seat ${piece.owner} piece ${piece.piece_id} ${Math.round(chance * 100)} percent`);
    }
    if (chance0 > 0.005 && chance1 > 0.005) parts.push("contested by both seats");
  }
  if (role.selectable) parts.push("selectable");
  if (role.isLanding) parts.push("legal target");
  if (role.isJumped) parts.push("would be jumped");
  if (role.isMergePartner) parts.push("legal merge partner");
  if (reveal === "kept") parts.push("collapsed here");
  if (reveal === "flicker") parts.push("was possible here");
  return parts.join(", ");
}

export { sqKey, sameSquare };
export type { ActionMsg };
