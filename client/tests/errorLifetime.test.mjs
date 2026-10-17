/**
 * Focused test for the error-lifetime rule (finding 2).
 *
 * The sequence under test is the one the server actually produces after a failed
 * hardware collapse: `Error`, then a `StateUpdate` carrying the *unchanged* board.
 * The player must still see the failure.
 *
 * Run with:  npm test   (which is `node --experimental-strip-types --test tests/*.test.mjs`)
 */

import assert from "node:assert/strict";
import test from "node:test";

import { resolveErrorAfterStateUpdate } from "../components/game/errorLifetime.ts";

const FAILURE = { message: "IBM Quantum measurement unavailable (RuntimeError)", code: "quantum_unavailable" };

test("a hardware failure survives the unchanged StateUpdate that follows it", () => {
    // Server order: Error (board at ply 7) then StateUpdate with the same ply 7.
    const afterError = FAILURE;
    const afterUnchangedState = resolveErrorAfterStateUpdate(afterError, 7, 7);
    assert.deepEqual(afterUnchangedState, FAILURE);
});

test("the error clears once the board actually moves on", () => {
    assert.equal(resolveErrorAfterStateUpdate(FAILURE, 7, 8), null);
});

test("a terminal state update clears an error even when the ply is unchanged", () => {
    assert.equal(resolveErrorAfterStateUpdate(FAILURE, 7, 7, true), null);
});

test("no error stays null", () => {
    assert.equal(resolveErrorAfterStateUpdate(null, 0, 0), null);
    assert.equal(resolveErrorAfterStateUpdate(null, 3, 9), null);
});

test("a refused move at the same ply is still shown (no StateUpdate follows it)", () => {
    // The server sends only Error for a refused move; the next thing that can arrive is
    // a later StateUpdate, which should clear it.
    const refused = { message: "no legal move from (0, 0) to (1, 1)", code: "illegal_move" };
    assert.deepEqual(resolveErrorAfterStateUpdate(refused, 4, 4), refused);
    assert.equal(resolveErrorAfterStateUpdate(refused, 4, 5), null);
});

test("full frame sequence: failure visible, then cleared by the next real move", () => {
    // Play the sequence through as the hook would.
    let ply = 6;
    let errorPly = 0;
    let shown = null;

    // ... player sends ObserveMove, the QPU job fails ...
    errorPly = ply;
    shown = FAILURE;                                   // case "Error"
    assert.notEqual(shown, null);

    shown = resolveErrorAfterStateUpdate(shown, errorPly, ply); // case "StateUpdate" (unchanged)
    assert.deepEqual(shown, FAILURE, "the failure must survive the unchanged state");

    // ... the player retries, the move applies, ply advances ...
    ply += 1;
    shown = resolveErrorAfterStateUpdate(shown, errorPly, ply);
    assert.equal(shown, null, "a stale error must not linger once the game moves on");
});
