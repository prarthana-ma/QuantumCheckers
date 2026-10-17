import type { ActionMsg, ClientMessage, GameState, Square } from "../../types/game";

export type BoardMode = "move" | "spread" | "observe" | "rejoin" | "merge";
export interface Selection {
  origin: Square;
  piece_id: string;
  mode: BoardMode;
  splitTarget?: Square;
  mergeSource?: Square;
}

const same = (a: Square, b: Square) => a[0] === b[0] && a[1] === b[1];
const modeOf = (action: ActionMsg): BoardMode => action.kind === "capture" ? "move" : action.kind;

/** Availability comes from the server's per-viewer list, including local two-player turns. */
export function canPlay(state: GameState): boolean {
  return state.you !== null && state.status === "playing" && state.legal.length > 0 &&
    !state.quantum_pending && !state.quantum?.pending;
}

/** Board colour is geometry, never affected by occupancy, turn or legal actions. */
export function isDarkSquare(row: number, col: number, size: number, parity = 0): boolean {
  return row >= 0 && col >= 0 && row < size && col < size && (row + col) % 2 === parity;
}

export function pieceCanActAt(state: GameState, pieceId: string, origin: Square): boolean {
  return state.legal.some((action) => action.piece_id === pieceId && (
    action.kind === "observe" || action.kind === "rejoin" || same(action.origin, origin) ||
    (action.kind === "merge" && action.other_origin && same(action.other_origin, origin))
  ));
}

export function pieceActions(state: GameState, selection: Selection): ActionMsg[] {
  return state.legal.filter((action) => action.piece_id === selection.piece_id && (
    action.kind === "observe" || action.kind === "rejoin" ||
    same(action.origin, selection.origin) ||
    (action.kind === "merge" && action.other_origin && same(action.other_origin, selection.origin))
  ));
}

export function availableModes(state: GameState, selection: Selection): BoardMode[] {
  const modes = new Set(pieceActions(state, selection).map(modeOf));
  return (["move", "spread", "observe", "rejoin", "merge"] as const).filter((mode) => modes.has(mode));
}

export function selectedActions(state: GameState, selection: Selection | null): ActionMsg[] {
  return selection ? pieceActions(state, selection).filter((action) => modeOf(action) === selection.mode) : [];
}

export function selectionsAt(state: GameState, square: Square): Selection[] {
  return state.board.pieces.flatMap((piece) => {
    if (piece.owner !== state.turn || !piece.sites.some(([site]) => same(site, square))) return [];
    const selection: Selection = { origin: square, piece_id: piece.piece_id, mode: "move" };
    const modes = availableModes(state, selection);
    return modes.length ? [{ ...selection, mode: modes[0] }] : [];
  });
}

export function selectPiece(state: GameState, square: Square): Selection | null {
  return selectionsAt(state, square)[0] ?? null;
}

export function boardTargets(state: GameState, selection: Selection | null): { square: Square; action: ActionMsg }[] {
  return selectedActions(state, selection).flatMap<{ square: Square; action: ActionMsg }>((action) => {
    if (action.kind === "merge" && action.other_origin && action.target && selection) {
      const other = same(action.origin, selection.origin) ? action.other_origin : action.origin;
      if (!selection.mergeSource) return [{ square: other, action }];
      return same(other, selection.mergeSource) ? [{ square: action.target, action }] : [];
    }
    if ("target" in action && action.target) return [{ square: action.target, action }];
    if (action.kind === "spread" && action.targets) {
      if (selection?.splitTarget && !action.targets.some((target) => same(target, selection.splitTarget!))) return [];
      return action.targets.filter((target) => !selection?.splitTarget || !same(target, selection.splitTarget)).map((square) => ({ square, action }));
    }
    if (action.kind === "merge") {
      const partner = state.board.pieces.find((piece) => piece.piece_id === action.other_piece_id);
      return partner?.sites.map(([square]) => ({ square, action })) ?? [];
    }
    return [];
  });
}

/** Translate one exact server action; never substitute a clicked square into a different action. */
export function actionMessage(action: ActionMsg): ClientMessage {
  switch (action.kind) {
    case "move":
    case "capture": return { type: "Move", from: action.origin, to: action.target, piece: action.piece_id };
    case "spread": return { type: "SplitMove", from: action.origin, piece: action.piece_id, ...(action.targets ? { targets: action.targets } : {}) };
    case "observe": return { type: "ObserveMove", square: action.origin, piece: action.piece_id };
    case "rejoin": return { type: "MergeMove", piece: action.piece_id, target: action.target };
    case "merge": return action.other_origin && action.target
      ? { type: "MergeMove", piece: action.piece_id, sources: [action.origin, action.other_origin], target: action.target }
      : { type: "MergeMove", pieces: [action.piece_id, action.other_piece_id!] };
  }
}

export type BoardClick =
  | { kind: "select"; selection: Selection }
  | { kind: "commit"; message: ClientMessage }
  | { kind: "clear" };

export function boardClick(state: GameState, selection: Selection | null, square: Square): BoardClick {
  if (!canPlay(state)) return { kind: "clear" };
  const target = boardTargets(state, selection).find((target) => same(target.square, square));
  if (target?.action.kind === "spread" && selection && !selection.splitTarget) {
    return { kind: "select", selection: { ...selection, splitTarget: square } };
  }
  if (target?.action.kind === "merge" && target.action.other_origin && selection && !selection.mergeSource) {
    return { kind: "select", selection: { ...selection, mergeSource: square } };
  }
  if (target) return { kind: "commit", message: actionMessage(target.action) };
  if (selection && same(selection.origin, square)) return { kind: "clear" };
  const next = selectPiece(state, square);
  return next ? { kind: "select", selection: next } : { kind: "clear" };
}

/** Double-tap shortcut: use only exact split actions advertised by the server. */
export function splitShortcut(state: GameState, selection: Selection | null, square: Square): BoardClick | null {
  if (!canPlay(state)) return null;
  const picked = selection && same(selection.origin, square) ? selection : selectPiece(state, square);
  if (!picked) return null;
  const split = { origin: square, piece_id: picked.piece_id, mode: "spread" as const };
  const actions = selectedActions(state, split);
  if (actions.length === 1) return { kind: "commit", message: actionMessage(actions[0]) };
  return actions.length ? { kind: "select", selection: split } : null;
}

export const MODE_LABEL: Record<BoardMode, string> = {
  move: "Move", spread: "Split", observe: "Observe", rejoin: "Resolve", merge: "Merge",
};

export const MODE_HINT: Record<BoardMode, string> = {
  move: "Tap a highlighted square to move or capture.",
  spread: "Choose the two highlighted destination squares for the split. Uses your turn.",
  observe: "Measure this piece to resolve its position. Uses your turn.",
  rejoin: "Tap a highlighted site to choose the piece's final square. Uses your turn.",
  merge: "Tap a highlighted destination to recombine this piece's two branches. Uses your turn.",
};
