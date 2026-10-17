/**
 * Motion bookkeeping for the board.
 *
 * The rule this module exists to keep: every animation must report a state
 * change the player can name. So the board never animates "just because" — it
 * compares the previous frame's board against the current one and derives, per
 * piece, exactly one transition to play.
 *
 * All of it is `transform` and `opacity` only. Nothing here animates width,
 * height, colour or box-shadow, because those cost layout or paint on every
 * frame and a 16x16 board has 256 of them.
 */

import type { BoardMsg, PieceMsg, Square } from "@/types/game";

/** How a piece changed between two frames. Each maps to exactly one animation. */
export type PieceTransition =
    /** Ordinary step: slide from the old square. */
    | { kind: "slide"; from: Square; to: Square }
    /** Capture: an arc, because the piece jumped a piece rather than stepped. */
    | { kind: "arc"; from: Square; to: Square }
    /** Newly split: a shimmer in, because it now occupies several squares. */
    | { kind: "shimmer"; to: Square }
    /** Was spread, now certain: the ghosts converge on the square it kept. */
    | { kind: "converge"; from: Square[]; to: Square }
    /** Unchanged in shape; the board may still want to flash it. */
    | { kind: "hold"; to: Square };

export interface BoardMotion {
  /** Per piece id, the transition to play this frame. */
  transitions: Map<string, PieceTransition>;
  /** Piece ids that are spread across more than one square right now. */
  entangled: Set<string>;
  /** Squares of a spread piece that was just measured, for the reveal flicker. */
  collapseFlicker: { square: Square; delay: number }[];
}

/**
 * Diff two boards. `previous` may be `null` (first frame), in which case every
 * piece enters with a shimmer rather than sliding in from nowhere.
 */
export function deriveMotion(previous: BoardMsg | null, current: BoardMsg): BoardMotion {
  const transitions = new Map<string, PieceTransition>();
  const entangled = new Set<string>();
  const collapseFlicker: { square: Square; delay: number }[] = [];

  for (const piece of current.pieces) {
    const squares = piece.sites.map(([sq]) => sq);
    if (squares.length > 1) entangled.add(piece.piece_id);
  }

  if (!previous) {
    for (const piece of current.pieces) {
      transitions.set(piece.piece_id, { kind: "shimmer", to: primarySite(piece) });
    }
    return { transitions, entangled, collapseFlicker };
  }

  const previousById = new Map(previous.pieces.map((p) => [p.piece_id, p]));

  for (const piece of current.pieces) {
    const before = previousById.get(piece.piece_id);
    const to = primarySite(piece);

    if (!before) {
      // A merge produces a new piece id; it arrives, it does not travel.
      transitions.set(piece.piece_id, { kind: "shimmer", to });
      continue;
    }

    const beforeSquares = before.sites.map(([sq]) => sq);
    const from = primarySite(before);

    if (before.uncertain && !piece.uncertain) {
      // The measurement resolved: every ghost converges on the square it kept.
      transitions.set(piece.piece_id, {
        kind: "converge",
        from: beforeSquares,
        to,
      });
      continue;
    }

    if (!before.uncertain && piece.uncertain) {
      transitions.set(piece.piece_id, { kind: "shimmer", to });
      continue;
    }

    if (before.uncertain) {
      // Still spread. It may still have moved, but a spread piece's origin is
      // what the player tracks, so compare origins.
      if (sameSquare(from, to)) transitions.set(piece.piece_id, { kind: "hold", to });
      else transitions.set(piece.piece_id, { kind: "converge", from: beforeSquares, to });
      continue;
    }

    if (sameSquare(from, to)) {
      transitions.set(piece.piece_id, { kind: "hold", to });
      continue;
    }

    // Two squares apart on an axis means the engine classified this as a capture
    // (PROTOCOL.md §3.1: `Move` covers both, and the engine decides which).
    const jumpedTwo = Math.abs(from[0] - to[0]) === 2 && Math.abs(from[1] - to[1]) === 2;
    transitions.set(
      piece.piece_id,
      jumpedTwo ? { kind: "arc", from, to } : { kind: "slide", from, to },
    );
  }

  return { transitions, entangled, collapseFlicker };
}

/**
 * Staggered flicker squares for a collapse, weighted so the likelier square
 * flickers FIRST — the reveal should feel like the engine settling on an
 * outcome, not a random strobe.
 */
export function collapseFlickerSquares(
  chances: [Square, number][],
  kept: Square,
): { square: Square; delay: number }[] {
  const ordered = [...chances].sort((a, b) => b[1] - a[1]);
  return ordered.map(([square], index) => ({
    square,
    delay: index * 90,
  }));
}

/** The square a piece is tracked from: its highest-weighted site, ties by index. */
export function primarySite(piece: PieceMsg): Square {
  return [...piece.sites].sort((a, b) => b[1] - a[1] || a[0][0] - b[0][0] || a[0][1] - b[0][1])[0][0];
}

export function sameSquare(a: Square, b: Square): boolean {
  return a[0] === b[0] && a[1] === b[1];
}

/**
 * Pixel offset from `from` to `to` for a board whose cells are `cell` wide with
 * `gap` between them. Used as a CSS custom property so the slide animation
 * lives entirely in CSS (compositor-only) rather than in a JS rAF loop.
 */
export function offsetBetween(
  from: Square,
  to: Square,
  cell: number,
  gap: number,
): { x: string; y: string } {
  const pitch = cell + gap;
  return {
    x: `${(from[1] - to[1]) * pitch}px`,
    y: `${(from[0] - to[0]) * pitch}px`,
  };
}