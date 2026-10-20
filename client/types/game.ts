/**
 * Wire types for the QCheckers game server.
 *
 * Frozen wire contract. Field names here mirror the server's JSON
 * exactly (snake_case on the wire), so a `StateUpdate` frame is assignable to
 * `GameState` with no translation layer.
 *
 * Rule discipline (C1): the server validates every move and ships the
 * legal-action list with each state. Nothing in this file computes legality.
 *
 * Naming: the protocol's own message names (`Move`, `SplitMove`, `Resign`, …) are
 * the canonical builders. The shorter `*Msg` constructors are kept as aliases so
 * the board components and this module read the same way.
 */

// ---------------------------------------------------------------------------
// Squares, seats, pieces
// ---------------------------------------------------------------------------

/** A board square, row-major: `[row, col]`. The letter is the column, the digit is `row + 1`. */
export type Square = [number, number];

/** A square as it may appear on the wire: the pair the browser sends, or `"c3"`. */
export type Squareish = Square | string;

/** A seat. `null` means spectator. Seats, never colour names. */
export type Seat = 0 | 1;

/** Chance weight in `[0, 1]`. The weights of one piece always sum to 1. */
export type Chance = number;

/** `[square, chanceWeight]`. */
export type Site = [Square, Chance];

/** One piece as rendered by the engine: a weighted set of candidate squares. */
export interface PieceMsg {
    piece_id: string;
    owner: Seat;
    sites: Site[];
    /** True when the piece occupies more than one square. */
    uncertain: boolean;
    /** Level-4 coherence counter, `null` when decoherence is off. */
    coherence: number | null;
    king_sites?: Site[];
    survival_probability?: number;
}

/** `engine.render(state)` verbatim. */
export interface BoardMsg {
    engine: string;
    level: number;
    allow_observe: boolean;
    /** 4..16. Never assume a fixed size. */
    board_size: number;
    ply: number;
    turn: Seat;
    /** Level 4 only; absent elsewhere. */
    decoherence?: boolean;
    /** Full counter value, level 4 only. */
    decoherence_ticks?: number | null;
    pieces: PieceMsg[];
    captured: string[];
    /** Mean chance weight over all pieces: a coarse "how fuzzy is the board". */
    certainty: number;
    paper_rules?: boolean;
    continuation_piece?: string | null;
}

/** Alias for callers that read the board as a view rather than a message. */
export type BoardView = BoardMsg;

// ---------------------------------------------------------------------------
// Actions — the `legal` list
// ---------------------------------------------------------------------------

interface ActionBase {
    piece_id: string;
    origin: Square;
}

/** Ordinary checkers step: one square diagonally forward. */
export interface MoveMsg extends ActionBase {
    kind: "move";
    target: Square;
}

/** Jump over an adjacent opponent piece onto the empty square beyond. */
export interface CaptureMsg extends ActionBase {
    kind: "capture";
    jumped: Square;
    target: Square;
}

/** Quantum-like move: hand the piece a distribution over candidate squares. */
export interface SpreadMsg extends ActionBase {
    kind: "spread";
    sites: Site[];
    targets?: Square[];
}

/** Collapse a spread piece onto one of its own candidate squares (level 2+). */
export interface RejoinMsg extends ActionBase {
    kind: "rejoin";
    target: Square;
}

/** Voluntary measurement. Only legal when the engine has `allow_observe`. */
export interface ObserveMsg extends ActionBase {
    kind: "observe";
}

/** Level 3: combine two of your own pieces into one probability-carrying piece. */
export interface MergeMsg extends ActionBase {
    kind: "merge";
    other_piece_id?: string;
    other_origin?: Square;
    target?: Square;
}

/** One entry of `state.legal`. The client renders these and computes nothing. */
export type ActionMsg = MoveMsg | CaptureMsg | SpreadMsg | RejoinMsg | ObserveMsg | MergeMsg;

/**
 * Aliases spelling the action types the way the engine's own class names do
 * (`MoveAction`, `CaptureAction`, …). Same types, two spellings, so a board module
 * can use whichever reads better locally.
 */
export type MoveActionMsg = MoveMsg;
export type CaptureActionMsg = CaptureMsg;
export type SpreadActionMsg = SpreadMsg;
export type RejoinActionMsg = RejoinMsg;
export type ObserveActionMsg = ObserveMsg;
export type MergeActionMsg = MergeMsg;

// ---------------------------------------------------------------------------
// Collapse event
// ---------------------------------------------------------------------------

/** Why a distribution was resolved. */
export type CollapseCause = "observe" | "capture" | "rejoin" | "join" | "decoherence";

/**
 * Where one live collapse's square came from, when the room ran on a QPU.
 *
 * Present on the collapse `last_event` and mirrored in `GameState.quantum.last`. It
 * names the backend and job, the raw bitstring, and the bitstring-to-square mapping
 * (the sampled square and its probability). No credential ever appears here.
 */
export interface QuantumProvenance {
    backend: string;
    job_id: string;
    /** Raw bitstring returned by the sampler, e.g. `"01"`. */
    bitstring: string;
    sampled: Square;
    probability: Chance;
    sites: Site[];
}

/**
 * The most recent collapse, plus the compact aliases the reveal animation reads.
 * `chances` is the pre-collapse distribution, which is exactly what a reveal
 * animation needs, and `sampled` stays authoritative.
 */
export interface CollapseEventMsg {
    ply: number;
    piece_id: string;
    owner: Seat;
    cause: CollapseCause;
    chances: Site[];
    sampled: Square;
    probability: Chance;
    /** Alias, always `"collapse"`. */
    kind: "collapse";
    /** Alias of `sampled`: the square it resolved to. */
    kept: Square;
    /** Alias of `cause`. */
    by: CollapseCause;
    /** Hardware provenance for this collapse; absent when the room is not QPU-backed. */
    quantum?: QuantumProvenance;
}

/**
 * The live-quantum block on every `StateUpdate`.
 *
 * `enabled` is true when this room resolves collapses on IBM hardware;
 * `backend` names the device (best-known before the first job, resolved after);
 * `last` is the provenance of the most recent hardware collapse; `pending` is true
 * while a QPU job is in flight. `enabled: false` is the ordinary offline game.
 */
export interface QuantumStatus {
    enabled: boolean;
    pending: boolean;
    backend: string | null;
    last: QuantumProvenance | null;
}

/** Alias for callers that read it as an event rather than a message. */
export type CollapseEvent = CollapseEventMsg;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** Game phase as reported by the server. */
export type Phase = "waiting" | "playing" | "over";

/** The authoritative state view every client renders against. */
export interface GameState {
    board: BoardMsg;
    /** Row-major `[chance_for_seat_0, chance_for_seat_1]` per square. */
    occupancy: [Chance, Chance][];
    /**
     * Level 4 only: ticks left before a spread piece expires, keyed `"row,col"`.
     * `{}` at every other level, so a client may render counters unconditionally.
     */
    coherence: Record<string, number>;
    turn: Seat;
    phase: Phase;
    last_event: CollapseEventMsg | null;
    /** The action just applied, or `null`. The move log renders this verbatim. */
    last_action: ActionMsg | null;
    /** Legal actions for this viewer. The client renders these; it never computes legality. */
    legal: ActionMsg[];
    /** The receiving player's seat, or `null` for a spectator. */
    you: Seat | null;
    ply: number;
    status: Phase;
    mode?: string;
    /** Live-quantum status: whether a QPU is in play, the backend, and the last job. */
    quantum?: QuantumStatus;
    /** True while a hardware measurement is running. Drives the pending indicator. */
    quantum_pending?: boolean;
    /** Present only in the per-socket view. */
    player_id?: string;
}

/** Why a game ended. */
export type GameOverReason = "no_pieces" | "no_legal_moves" | "ply_limit" | "resign" | "quiet_moves" | "forty_move_draw";

/** Alias for the narrower spelling used in the frozen samples. */
export type TerminationReason = GameOverReason;

/** The `GameOver` payload. */
export interface GameOverMsg {
    /** Winning seat, or `null` for a draw. Seats, never colour names. */
    result: Seat | null;
    reason: GameOverReason;
    moves: number;
    seed: number;
    game_id: string;
    level: number;
    mode: string;
}

/** A protocol `Error`. A refused move leaves the state unchanged. */
export interface ErrorMsg {
    message: string;
    code: string;
}

/** Liveness tick. Seconds since the room opened. */
export interface TickMsg {
    t: number;
}

// ---------------------------------------------------------------------------
// Frames on the wire
// ---------------------------------------------------------------------------

export type StateUpdate = GameState & { type: "StateUpdate" };
export type GameOver = GameOverMsg & { type: "GameOver" };
export type Error = ErrorMsg & { type: "Error" };
export type Tick = TickMsg & { type: "Tick"; game_id?: string };
/**
 * A hardware measurement just started on the server. The authoritative `StateUpdate`
 * that follows carries the result (and its provenance); this frame only lets the UI
 * say "measuring on hardware" while the QPU job is in the queue.
 */
export type QuantumPending = {
    type: "QuantumPending";
    pending: true;
    game_id?: string;
    backend?: string | null;
};

export type ServerMessage = StateUpdate | GameOver | Error | Tick | QuantumPending;

// ---------------------------------------------------------------------------
// Client -> server messages
// ---------------------------------------------------------------------------

export type ClientMessage =
    | { type: "JoinGame"; player_id?: string; label?: string }
    | { type: "Move"; from: Squareish; to: Squareish; piece?: string }
    | { type: "SplitMove"; from: Squareish; targets?: Squareish[]; piece?: string }
    | { type: "ObserveMove"; square: Squareish; piece?: string }
    | {
          type: "MergeMove";
          pieces?: string[];
          piece?: string;
          from?: Squareish;
          target?: Squareish;
          sources?: Squareish[];
      }
    | { type: "Resign" }
    | { type: "RetryAI" };

// ---------------------------------------------------------------------------
// Message builders — thin constructors over the wire shapes
// ---------------------------------------------------------------------------

/** Claim a seat. Present the same `player_id` to reclaim it after a reconnect. */
export function JoinGame(options: { player_id?: string; label?: string } = {}) {
    return {
        type: "JoinGame" as const,
        ...(options.player_id ? { player_id: options.player_id } : {}),
        ...(options.label ? { label: options.label } : {}),
    };
}

/**
 * An ordinary step or a capture: the engine classifies which by the distance between
 * `from` and `to`, so the client does not tell them apart.
 */
export function Move(from: Squareish, to: Squareish) {
    return { type: "Move" as const, from, to };
}

/**
 * A split. `targets` is advisory: when present the server requires it to equal the
 * engine's canonical non-origin site set. Omit it and the engine's distribution is used.
 */
export function SplitMove(from: Squareish, targets?: Squareish[]) {
    return {
        type: "SplitMove" as const,
        from,
        ...(targets && targets.length > 0 ? { targets } : {}),
    };
}

/** Voluntary measurement: sample the spread piece occupying `square`. Costs the turn. */
export function ObserveMove(square: Squareish) {
    return { type: "ObserveMove" as const, square };
}

/**
 * Merge or rejoin, whichever the engine offers: a level-3 merge when two ids are
 * named, otherwise a level-2 rejoin onto `target`.
 */
export function MergeMove(options: { pieces?: [string, string]; piece?: string; target?: Squareish }) {
    return {
        type: "MergeMove" as const,
        ...(options.pieces ? { pieces: options.pieces } : {}),
        ...(options.piece ? { piece: options.piece } : {}),
        ...(options.target ? { target: options.target } : {}),
    };
}

/** Give up the game; the other seat wins. */
export function Resign() {
    return { type: "Resign" as const };
}

/**
 * Level-3 merge, by the two pieces it joins. Named apart from `MergeMove` because
 * naming both pieces is the only merge form: the single-piece form is a rejoin.
 */
export function MergePieces(pieces: [string, string]) {
    return { type: "MergeMove" as const, pieces };
}

/**
 * Level-2 rejoin: collapse one spread piece onto the square you pick. Costs the
 * turn, and is logged as a collapse with cause `rejoin` — a choice, not a sample.
 */
export function Rejoin(piece: string, target?: Squareish) {
    return {
        type: "MergeMove" as const,
        piece,
        ...(target === undefined ? {} : { target }),
    };
}

// -- aliases matching the shorter `*Msg` spelling used across the board --------

export function joinMsg(playerId?: string): ClientMessage {
    return playerId ? { type: "JoinGame", player_id: playerId } : { type: "JoinGame" };
}

export function moveMsg(from: Squareish, to: Squareish): ClientMessage {
    return { type: "Move", from, to };
}

export function splitMsg(from: Squareish, targets?: Squareish[]): ClientMessage {
    return targets ? { type: "SplitMove", from, targets } : { type: "SplitMove", from };
}

export function observeMsg(square: Squareish): ClientMessage {
    return { type: "ObserveMove", square };
}

/** Level-3 merge: names both pieces. */
export function mergePiecesMsg(pieces: [string, string]): ClientMessage {
    return { type: "MergeMove", pieces };
}

/** Level-2 rejoin: one piece, optionally narrowed to a target square. */
export function rejoinMsg(piece: string, target?: Squareish): ClientMessage {
    return target === undefined
        ? { type: "MergeMove", piece }
        : { type: "MergeMove", piece, target };
}

export function resignMsg(): ClientMessage {
    return { type: "Resign" };
}

// ---------------------------------------------------------------------------
// Naming helpers
// ---------------------------------------------------------------------------

/**
 * `"c3"` style label for a square: the letter is the COLUMN and the digit is
 * `row + 1`, so `"c3"` is `[2, 2]`. Board sizes run to 16, so columns go past `p`
 * and we keep counting rather than wrapping.
 */
export function squareName([row, col]: Square): string {
    if (row < 0 || col < 0) return "absent";
    return `${colLabel(col)}${row + 1}`;
}

/** Column letter for an index, wrapping into two letters past `z`. */
export function colLabel(col: number): string {
    if (col < 26) return String.fromCharCode(97 + col);
    return `${String.fromCharCode(97 + Math.floor(col / 26) - 1)}${String.fromCharCode(97 + (col % 26))}`;
}
