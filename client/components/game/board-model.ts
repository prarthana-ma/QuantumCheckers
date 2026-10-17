import type {
  ActionMsg,
  BoardMsg,
  CaptureMsg,
  CollapseEventMsg,
  GameState,
  MergeMsg,
  MoveMsg,
  ObserveMsg,
  PieceMsg,
  RejoinMsg,
  Seat,
  Site,
  SpreadMsg,
  Square,
} from "@/types/game";
import { isDarkSquare } from "./board-interaction";

/** `[row, col]` -> stable key. Every map in this file keys squares by this. */
export function sqKey(square: Square | undefined | null): string {
  return square ? `${square[0]},${square[1]}` : "";
}

export function parseKey(key: string): Square {
  const [row, col] = key.split(",").map(Number);
  return [row, col];
}

/**
 * Algebraic name for a square: the letter is the COLUMN (`a` = 0) and the digit
 * is the row plus one, so `"c3"` is `[2, 2]` (PROTOCOL §3.1). Board sizes run to
 * 16, so columns go past `p` — we keep counting rather than wrapping.
 */
export function squareName(square: Square): string {
  const [row, col] = square;
  if (row < 0 || col < 0) return "absent";
  return `${colLabel(col)}${row + 1}`;
}

export function colLabel(col: number): string {
  if (col < 26) return String.fromCharCode(97 + col);
  return `${String.fromCharCode(97 + Math.floor(col / 26) - 1)}${String.fromCharCode(97 + (col % 26))}`;
}

/** Human label for a seat. Seats are the identity; this is only for display. */
export function seatName(seat: Seat | null | undefined): string {
  if (seat === 0) return "SEAT 0";
  if (seat === 1) return "SEAT 1";
  return "SPECTATOR";
}

/**
 * The seat's colour, named in words. The board draws seat 0 in near-white
 * and seat 1 in violet, so the player can be told what they are playing
 * without learning the numbering first.
 */
export function seatColorName(seat: Seat | null | undefined): string {
  if (seat === 0) return "white";
  if (seat === 1) return "purple";
  return "spectator";
}

/** CSS variable holding a seat's colour. */
export function seatColor(seat: number | null | undefined): string {
  return seat === 1 ? "var(--color-seat-1)" : "var(--color-seat-0)";
}

/**
 * Checkerboard geometry: paper rules play on odd squares, and the toy engine
 * uses `size % 2`. Squares the engine references — piece sites and legal
 * actions — stay playable as well, since odd-sized setups can place pieces on
 * both parities. Rendering never decides legality.
 */
export function isPlayable(state: GameState, row: number, col: number): boolean {
  const size = state.board.board_size;
  if (row < 0 || col < 0 || row >= size || col >= size) return false;
  const parity = state.board.paper_rules ? 1 : size % 2;
  if (isDarkSquare(row, col, size, parity)) return true;
  const square: Square = [row, col];
  return (
    state.board.pieces.some((piece) => piece.sites.some(([site]) => sameSquare(site, square))) ||
    state.legal.some((action) => touches(action, square))
  );
}

/** True when the engine references this square in an action. */
function touches(action: ActionMsg, square: Square): boolean {
  if (sameSquare(action.origin, square)) return true;
  if ("target" in action && sameSquare(action.target, square)) return true;
  if (action.kind === "capture" && sameSquare(action.jumped, square)) return true;
  if (action.kind === "spread") {
    return (
      action.sites.some(([site]) => sameSquare(site, square)) ||
      (action.targets?.some((target) => sameSquare(target, square)) ?? false)
    );
  }
  return false;
}

export function sameSquare(a: Square | undefined | null, b: Square | undefined | null): boolean {
  return !!a && !!b && a[0] === b[0] && a[1] === b[1];
}

/** The chance of the highest-weighted owner on a square, straight from occupancy. */
export function occupancyAt(state: GameState, square: Square): [number, number] {
  const size = state.board.board_size;
  const index = square[0] * size + square[1];
  const pair = state.occupancy[index];
  return pair ?? [0, 0];
}

/** Every piece claiming a square, with its chance there. */
export function piecesAt(board: BoardMsg, square: Square): { piece: PieceMsg; chance: number }[] {
  const out: { piece: PieceMsg; chance: number }[] = [];
  for (const piece of board.pieces) {
    for (const [sq, weight] of piece.sites) {
      if (sq[0] === square[0] && sq[1] === square[1]) out.push({ piece, chance: weight });
    }
  }
  return out;
}

export function pieceById(board: BoardMsg, pieceId: string): PieceMsg | undefined {
  return board.pieces.find((p) => p.piece_id === pieceId);
}

/** A spread piece occupies more than one square. */
export function isSpreadPiece(piece: PieceMsg | undefined): boolean {
  return !!piece && piece.sites.length > 1;
}

/** The square a spread piece split FROM is its highest-weighted site, then lowest index. */
export function pieceOrigin(piece: PieceMsg): Square {
  return [...piece.sites].sort((a, b) => b[1] - a[1] || a[0][0] - b[0][0] || a[0][1] - b[0][1])[0][0];
}

// ---------------------------------------------------------------------------
// Legal-action index — pure lookup over state.legal, never a rule of its own
// ---------------------------------------------------------------------------

/** What a click on a square means, given the current selection. */
export type ClickIntent =
  | { type: "none" }
  | { type: "select-origin"; action: ActionMsg }
  | { type: "commit"; action: ActionMsg };

/**
 * Group `state.legal` by origin square. This is an index of the server's list —
 * it reads the list, it never adds to it.
 */
export function legalByOrigin(state: GameState): Map<string, ActionMsg[]> {
  const map = new Map<string, ActionMsg[]>();
  for (const action of state.legal) {
    const key = sqKey(action.origin);
    const bucket = map.get(key);
    if (bucket) bucket.push(action);
    else map.set(key, [action]);
  }
  return map;
}

/** Actions that name this square as their landing square. */
export function legalTargetsFor(state: GameState, origin: Square | null): ActionMsg[] {
  if (!origin) return [];
  return state.legal.filter((a) => {
    if (!sameSquare(a.origin, origin)) return false;
    if (a.kind === "observe" || a.kind === "merge" || a.kind === "spread") return false;
    return "target" in a;
  });
}

/**
 * A merge names two pieces, not two squares, so its second click is on the
 * partner piece's square rather than a landing square.
 */
export function mergePartnersFor(state: GameState, origin: Square | null): MergeMsg[] {
  if (!origin) return [];
  return state.legal.filter(
    (a): a is MergeMsg => a.kind === "merge" && sameSquare(a.origin, origin),
  );
}

export function targetOf(action: ActionMsg): Square | null {
  if (action.kind === "move" || action.kind === "capture" || action.kind === "rejoin") {
    return action.target;
  }
  return null;
}

export function landsOn(action: ActionMsg, square: Square): boolean {
  const target = targetOf(action);
  return !!target && sameSquare(target, square);
}

/** Rejoin targets are drawn on the piece's own sites; capture shows the jumped square too. */
export function actionFootprint(action: ActionMsg): Square[] {
  const out: Square[] = [];
  if (action.kind === "capture") out.push(action.jumped);
  const target = targetOf(action);
  if (target) out.push(target);
  return out;
}

/** The spread action's candidate sites, for the "what would this become" preview. */
export function spreadSites(action: SpreadMsg): Site[] {
  return action.sites;
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** Chance as a whole percentage. `0.004` reads as "0%", which is honest. */
export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Chance with one decimal when it isn't whole, for the fine-grained reads. */
export function pctFine(value: number): string {
  const rounded = Math.round(value * 1000) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

export function describeAction(action: ActionMsg): string {
  switch (action.kind) {
    case "move":
      return `MOVE ${action.piece_id} ${squareName(action.origin)}→${squareName(action.target)}`;
    case "capture":
      return `CAPTURE ${action.piece_id} ${squareName(action.origin)}→${squareName(action.target)}`;
    case "spread":
      return `SPLIT ${action.piece_id} at ${squareName(action.origin)}`;
    case "rejoin":
      return `REJOIN ${action.piece_id} onto ${squareName(action.target)}`;
    case "observe":
      return `OBSERVE ${action.piece_id} at ${squareName(action.origin)}`;
    case "merge":
      return action.other_origin && action.target
        ? `MERGE ${squareName(action.origin)}+${squareName(action.other_origin)} → ${squareName(action.target)}`
        : `MERGE ${action.piece_id}+${action.other_piece_id}`;
  }
}

export function causeLabel(cause: string): string {
  switch (cause) {
    case "observe":
      return "MEASURED BY OBSERVE";
    case "capture":
      return "FORCED BY CAPTURE";
    case "rejoin":
      return "REJOINED BY CHOICE";
    case "join":
      return "JOINED";
    case "decoherence":
      return "DECOHERED — EXPIRED";
    default:
      return cause.toUpperCase();
  }
}

export function reasonLabel(reason: string): string {
  switch (reason) {
    case "no_pieces":
      return "One side has no pieces left";
    case "no_legal_moves":
      return "The side to move has no legal action";
    case "ply_limit":
      return "The ply cap was reached — nobody could force a win";
    case "resign":
      return "The game was resigned";
    case "quiet_moves":
    case "forty_move_draw":
      return "More than 40 turns without a capture — draw";
    default:
      return reason;
  }
}

export type {
  ActionMsg,
  BoardMsg,
  CaptureMsg,
  CollapseEventMsg,
  GameState,
  MergeMsg,
  MoveMsg,
  ObserveMsg,
  RejoinMsg,
  Seat,
  Site,
  SpreadMsg,
  Square,
};
