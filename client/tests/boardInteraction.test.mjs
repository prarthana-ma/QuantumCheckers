import assert from "node:assert/strict";
import test from "node:test";
import { actionMessage, availableModes, boardClick, boardTargets, canPlay, isDarkSquare, selectPiece, splitShortcut, pieceCanActAt } from "../components/game/board-interaction.ts";

const piece = (id, sites, owner = 0) => ({ piece_id: id, owner, sites, uncertain: sites.length > 1 });
const move = (target) => ({ kind: "move", piece_id: "A", origin: [7, 3], target });
const state = (legal, pieces = [piece("A", [[[7, 3], 1]])]) => ({
  board: { board_size: 8, pieces }, legal, turn: 0, you: 0, status: "playing",
});

test("piece selection exposes both server destinations and sends the one actually clicked", () => {
  const game = state([move([6, 2]), move([6, 4])]);
  const selected = boardClick(game, null, [7, 3]).selection;
  assert.deepEqual(boardTargets(game, selected).map((t) => t.square), [[6, 2], [6, 4]]);
  assert.deepEqual(boardClick(game, selected, [6, 4]), { kind: "commit", message: { type: "Move", from: [7, 3], to: [6, 4], piece: "A" } });
  assert.deepEqual(boardClick(game, selected, [6, 2]).message.to, [6, 2]);
});

test("capture uses the exact origin and landing square supplied by the server", () => {
  const capture = { ...move([5, 1]), kind: "capture", jumped: [6, 2] };
  const game = state([capture]);
  assert.deepEqual(boardClick(game, selectPiece(game, [7, 3]), [5, 1]).message, { type: "Move", from: [7, 3], to: [5, 1], piece: "A" });
});

test("clicking a split piece's ghost selects that piece and resolves the chosen site", () => {
  const legal = [[4, 2], [3, 1], [3, 3]].map((target) => ({ kind: "rejoin", piece_id: "A", origin: [4, 2], target }));
  const game = state(legal, [piece("A", [[[4, 2], .5], [[3, 1], .25], [[3, 3], .25]])]);
  const selected = selectPiece(game, [3, 3]);
  assert.equal(selected.piece_id, "A");
  assert.equal(selected.mode, "rejoin");
  assert.deepEqual(boardClick(game, selected, [3, 1]).message, { type: "MergeMove", piece: "A", target: [3, 1] });
});

test("merge resolves the clicked partner rather than the first offered partner", () => {
  const legal = ["B", "C"].map((other_piece_id) => ({ kind: "merge", piece_id: "A", origin: [7, 3], other_piece_id }));
  const game = state(legal, [piece("A", [[[7, 3], 1]]), piece("B", [[[6, 2], 1]]), piece("C", [[[6, 4], 1]])]);
  assert.deepEqual(boardClick(game, selectPiece(game, [7, 3]), [6, 4]).message, { type: "MergeMove", pieces: ["A", "C"] });
});

test("empty or stale targets never send an action", () => {
  const game = state([move([6, 2])]);
  const selected = selectPiece(game, [7, 3]);
  assert.equal(boardClick(game, selected, [5, 5]).kind, "clear");
  assert.equal(boardClick(state([]), selected, [6, 2]).kind, "clear");
});

test("all quantum modes are derived from the selected piece's legal actions", () => {
  const game = state([move([6, 2]), { kind: "spread", piece_id: "A", origin: [7, 3], sites: [[[7, 3], .5], [[6, 2], .5]] }]);
  assert.deepEqual(availableModes(game, selectPiece(game, [7, 3])), ["move", "spread"]);
  assert.deepEqual(actionMessage({ kind: "observe", piece_id: "A", origin: [4, 2] }), { type: "ObserveMove", square: [4, 2], piece: "A" });
});

test("a paper split sends exactly the two destinations picked on the board", () => {
  const split = { kind: "spread", piece_id: "A", origin: [7, 3], targets: [[6, 2], [6, 4]], sites: [[[6, 2], .5], [[6, 4], .5]] };
  const game = state([split]);
  const selected = selectPiece(game, [7, 3]);
  const first = boardClick(game, selected, [6, 4]);
  assert.equal(first.kind, "select");
  const second = boardClick(game, first.selection, [6, 2]);
  assert.deepEqual(second.message, { type: "SplitMove", from: [7, 3], piece: "A", targets: [[6, 2], [6, 4]] });
});

test("paper merge selects a second branch of the same piece and its shared destination", () => {
  const merge = { kind: "merge", piece_id: "A", origin: [4, 1], other_origin: [4, 3], target: [3, 2] };
  const game = state([merge], [piece("A", [[[4, 1], .5], [[4, 3], .5]])]);
  const selected = selectPiece(game, [4, 1]);
  assert.deepEqual(boardTargets(game, selected).map((target) => target.square), [[4, 3]]);
  const secondSource = boardClick(game, selected, [4, 3]);
  assert.equal(secondSource.kind, "select");
  assert.deepEqual(boardTargets(game, secondSource.selection).map((target) => target.square), [[3, 2]]);
  assert.deepEqual(boardClick(game, secondSource.selection, [3, 2]).message, { type: "MergeMove", piece: "A", sources: [[4, 1], [4, 3]], target: [3, 2] });
});

test("local second player can act when the server supplies legal actions; spectators and pending jobs cannot", () => {
  assert.equal(canPlay({ ...state([move([6, 2])]), turn: 1 }), true);
  assert.equal(canPlay({ ...state([move([6, 2])]), you: null }), false);
  assert.equal(canPlay(state([])), false);
  assert.equal(canPlay({ ...state([move([6, 2])]), quantum_pending: true }), false);
  assert.equal(canPlay({ ...state([move([6, 2])]), status: "over" }), false);
});

test("checkerboard colours stay consistent for every supported size", () => {
  for (const size of [4, 6, 8, 10, 12, 14, 16]) {
    for (let row = 0; row < size; row++) for (let col = 0; col < size; col++) {
      assert.equal(isDarkSquare(row, col, size), (row + col) % 2 === 0);
      assert.equal(isDarkSquare(row, col, size, 1), (row + col) % 2 === 1);
      if (col + 1 < size) assert.notEqual(isDarkSquare(row, col, size), isDarkSquare(row, col + 1, size));
    }
  }
  assert.equal(isDarkSquare(-1, 0, 8), false);
});


test("double tap performs the sole split pair and never invents a forced-capture split", () => {
  const split = { kind: "spread", piece_id: "A", origin: [7, 3], targets: [[6, 2], [6, 4]], sites: [] };
  const game = state([move([6, 2]), split]);
  assert.deepEqual(splitShortcut(game, selectPiece(game, [7, 3]), [7, 3]), { kind: "commit", message: actionMessage(split) });
  assert.equal(splitShortcut(state([move([5, 1])]), null, [7, 3]), null);
  assert.equal(splitShortcut({ ...game, quantum_pending: true }, null, [7, 3]), null);
});

test("double tap selects Split when several destination pairs are offered", () => {
  const splits = [[[6, 2], [6, 4]], [[6, 2], [8, 4]]].map(targets => ({ kind: "spread", piece_id: "A", origin: [7, 3], targets, sites: [] }));
  const result = splitShortcut(state(splits), null, [7, 3]);
  assert.equal(result.kind, "select");
  assert.equal(result.selection.mode, "spread");
  assert.equal(result.selection.splitTarget, undefined);
});


test("only the occupied branch named by a legal action is marked actionable", () => {
  const legal = [
    { kind: "capture", piece_id: "A", origin: [6, 5], target: [4, 3], jumped: [5, 4] },
    { kind: "capture", piece_id: "B", origin: [7, 6], target: [5, 4], jumped: [6, 5] },
  ];
  const game = state(legal, [
    piece("A", [[[6, 3], .5], [[6, 5], .5]]),
    piece("B", [[[7, 6], 1]]),
  ]);
  assert.equal(pieceCanActAt(game, "A", [6, 3]), false);
  assert.equal(pieceCanActAt(game, "A", [6, 5]), true);
  assert.equal(pieceCanActAt(game, "B", [7, 6]), true);
  assert.equal(boardClick(game, null, [6, 3]).kind, "clear");
  assert.deepEqual(boardTargets(game, selectPiece(game, [6, 5])).map(t => t.square), [[4, 3]]);
  assert.deepEqual(boardTargets(game, selectPiece(game, [7, 6])).map(t => t.square), [[5, 4]]);
});
