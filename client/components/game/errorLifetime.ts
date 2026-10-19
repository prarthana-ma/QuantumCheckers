/**
 * How long a protocol `Error` stays on screen.
 *
 * This exists because of one specific server sequence. When a hardware-backed collapse
 * fails, the server sends `Error` **followed by** the unchanged authoritative
 * `StateUpdate` (the room is deliberately left exactly as it was). A client that cleared
 * its error on every state update would therefore wipe the hardware failure the instant
 * it was reported, leaving the player staring at a board that simply did not move.
 *
 * The rule: an error survives nonterminal state updates that do not change the board.
 * The board is identified by its ply, which strictly increases on any applied action, so
 *
 *   - `incomingPly === errorPly`  -> nothing happened; keep the error visible;
 *   - `incomingPly !== errorPly` or the game is over -> clear the stale error.
 *
 * Refused moves are unaffected: the server sends no `StateUpdate` for them, so the error
 * persists until the board genuinely changes, exactly as before.
 *
 * Kept dependency-free and pure so it can be unit-tested without a DOM or a socket.
 */

/** The subset of a protocol `Error` frame this rule cares about. */
export interface ProtocolErrorInfo {
    message: string;
    code: string;
}

/**
 * Return the error that should remain after a `StateUpdate` arrives.
 *
 * @param previous  the error currently displayed, or `null`
 * @param errorPly  the ply the board was on when that error was reported
 * @param incomingPly the ply carried by the incoming `StateUpdate`
 * @param gameOver whether the incoming state is terminal
 */
export function resolveErrorAfterStateUpdate(
    previous: ProtocolErrorInfo | null,
    errorPly: number,
    incomingPly: number,
    gameOver = false,
): ProtocolErrorInfo | null {
    if (!previous) return null;
    if (gameOver) return null;
    return incomingPly === errorPly ? previous : null;
}
