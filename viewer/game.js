/* QuriousMinds game client -- plain ES2018, no framework, no build step.
 *
 * Owner: P4 (frontend and delivery).
 *
 * Hard rules this file follows:
 *
 * 1. **The client never decides legality.** It renders the `legal` action list the
 *    server sent and turns clicks into protocol messages. The only feedback for a
 *    refused move is the server's Error frame; nothing is ever applied locally.
 * 2. **No build step** (brief C2). No modules, no imports, no bundler. Opens from a
 *    file:// URL and talks to the local server over fetch + WebSocket.
 * 3. **Honest visuals.** Ghost pieces show occupancy chances. This engine is a
 *    classical probability model, so the UI says amplitudes/phase/entanglement are not
 *    modelled rather than implying they are.
 */

(function () {
  "use strict";

  /* ------------------------------------------------------------------ meta */

  var STAGES = [
    {
      level: 0,
      name: "Stage 0 \u2014 Classical",
      mechanic: "Forward moves and captures. No uncertainty.",
      rule: [
        "Pieces move one square diagonally forward onto an empty square.",
        "A capture jumps over an adjacent opponent piece to the empty square beyond.",
        "Captures are available but not forced in this engine (the published rule set is unverified).",
        "The side with no pieces, or with no legal move, loses.",
      ],
    },
    {
      level: 1,
      name: "Stage 1 \u2014 Split",
      mechanic: "A piece may split into a 50/50 spread over its forward diagonals.",
      rule: [
        "A split replaces one certain piece with a distribution: it keeps 50% on its origin and shares 50% over its free forward diagonal squares.",
        "A spread piece cannot move or capture normally until it is resolved.",
        "You may not split your last certain piece \u2014 a house rule of this engine, so that using the quantum mechanic cannot strand you.",
        "Resolution happens when a capture is attempted on it, or when you choose to resolve it (Stage 2+).",
        "Before resolution the piece is uncertain: a ghost over several squares with an occupancy chance on each.",
      ],
    },
    {
      level: 2,
      name: "Stage 2 \u2014 Rejoin",
      mechanic: "Resolve a spread piece on purpose: OBSERVE lets the engine sample it, REJOIN picks the square. Either one costs the turn.",
      unlock: {
        title: "Stage 2 unlocked \u2014 voluntary measurement",
        body: [
          "New in this stage: you may resolve one of your own spread pieces on purpose, and it costs your whole turn.",
          "OBSERVE collapses the piece by sampling its chances \u2014 you hand the choice of square to the engine. REJOIN collapses it onto the square you pick. Both are logged as a collapse, with the cause recorded.",
          "This is the mechanic the study is built around. Measuring an uncertain piece early is the team's extension of the paper, and it is the term our ablation switches on and off.",
          "A resolved piece is certain again and can be split later like any other piece.",
        ],
      },
      rule: [
        "Select one of your spread pieces. REJOIN gives you the square; OBSERVE asks the engine to sample the piece's chances.",
        "A rejoin is a choice, an observe is a sample you asked for. Both end your turn and both are logged as a collapse.",
        "It costs the whole turn, exactly like any other action.",
        "This is the voluntary-measurement mechanic the study is built around.",
      ],
    },
    {
      level: 3,
      name: "Stage 3 \u2014 Merge",
      mechanic: "Two diagonally adjacent own pieces may merge into one 50/50 spread piece.",
      rule: [
        "Pick two of your pieces that are diagonal neighbours and merge them.",
        "The merge is the inverse of a split: two certain pieces become one piece spread 50/50 over their two squares.",
        "It costs the turn and logs no collapse, because nothing is measured.",
        "Level 3 is playable here but is never part of a batched experiment.",
      ],
    },
    {
      level: 4,
      name: "Stage 4 \u2014 Decoherence",
      mechanic: "A split piece carries a coherence counter. Every turn you leave it unmeasured, the counter drops; at zero the piece collapses by itself.",
      unlock: {
        title: "Stage 4 unlocked \u2014 Decoherence",
        body: [
          "Invented by us: nothing quantum lasts forever.",
          "Every split piece now shows a coherence counter on the square it split from. Each turn that ends without measuring it costs it one tick, and re-splitting refreshes it to a full counter.",
          "At zero the piece collapses on its own, sampled from the same chances any other measurement uses \u2014 you do not choose the square, and neither does the opponent.",
          "This is our outreach mechanic, not the paper's. It is switched on only for this stage, never for an experiment, so the report gives it one honest paragraph and claims nothing measured about it.",
        ],
      },
      rule: [
        "A split piece starts at 6 coherence, shown as a small counter on the square it split from.",
        "Every turn that ends without resolving that piece takes one tick off the counter.",
        "Re-splitting the piece, or merging into a new spread piece, refreshes the counter to 6.",
        "At zero the piece collapses automatically, weighted by its current chances (cause: decoherence).",
        "Stage 4 is playable here and is never batched. Every measured result in the report comes from stages 0\u20132.",
      ],
    },
  ];

  var MODE_LABELS = {
    "ai-easy": "vs AI \u2014 Easy (random)",
    "ai-medium": "vs AI \u2014 Medium (tree search)",
    "ai-hard": "vs AI \u2014 Hard (probability-aware + Observe)",
    local: "Local 2 player",
    online: "Online",
  };

  var PROGRESS_KEY = "qk.progress";
  var SERVER_KEY = "qk.server";

  /* ----------------------------------------------------------------- state */

  var state = {
    server: "",
    progress: {},
    screen: "landing",
    stage: null,
    mode: null,
    gameId: null,
    playerId: null,
    ws: null,
    view: null,
    mySeat: null,
    selected: null, // "r,c"
    collapse: { event: null, step: 0, timer: null },
    rulesTab: 0,
    connected: false,
  };

  var els = {};
  var COLLAPSE_TICK_MS = 900;

  function $(id) { return document.getElementById(id); }

  function cache() {
    [
      "server-url", "server-check", "server-status", "engine-note",
      "screen-landing", "screen-stages", "screen-mode", "screen-lobby", "screen-game",
      "screen-result",
      "btn-start", "btn-join-show", "btn-rules", "join-form", "join-code", "btn-join",
      "stage-grid", "btn-stages-back", "btn-stages-rules", "mode-stage-note",
      "btn-mode-back", "lobby-code", "lobby-status", "btn-lobby-cancel",
      "turn-indicator", "phase-chip", "level-output", "board", "action-hint", "action-list",
      "uncertainty-list", "collapse-body", "event-log", "game-status",
      "btn-game-rules", "btn-resign", "btn-quit",
      "result-heading", "result-line", "btn-again", "btn-next", "btn-home",
      "rules-modal", "rules-tabs", "rules-body", "rules-caveat", "rules-close",
      "unlock-modal", "unlock-title", "unlock-body", "btn-unlock-continue",
    ].forEach(function (id) { els[id] = $(id); });
  }

  /* --------------------------------------------------------------- helpers */

  function key(row, col) { return row + "," + col; }

  function parseKey(k) {
    var parts = String(k).split(",");
    return [Number(parts[0]), Number(parts[1])];
  }

  function pct(value) {
    var n = Number(value);
    if (!isFinite(n)) { return ""; }
    return Math.round(n * 100) + "%";
  }

  function clear(node) { while (node && node.firstChild) { node.removeChild(node.firstChild); } }

  function make(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function playerLabel(p) { return "player " + p; }

  function squareText(s) {
    return Array.isArray(s) ? "(" + s[0] + "," + s[1] + ")" : "?";
  }

  function describeAction(a) {
    if (!a || typeof a !== "object") { return "unknown action"; }
    switch (a.kind) {
      case "move": return "move " + a.piece_id + " " + squareText(a.origin) + " \u2192 " + squareText(a.target);
      case "capture": return "capture " + a.piece_id + " over " + squareText(a.jumped) + " \u2192 " + squareText(a.target);
      case "spread": return "split " + a.piece_id + " over " + (a.sites || []).map(function (s) { return squareText(s[0]) + "@" + pct(s[1]); }).join(" ");
      case "rejoin": return "rejoin " + a.piece_id + " \u2192 " + squareText(a.target);
      case "observe": return "OBSERVE " + a.piece_id + " " + squareText(a.origin);
      case "merge": return "merge " + a.piece_id + " + " + a.other_piece_id;
      default: return a.kind + " " + (a.piece_id || "");
    }
  }

  /* Turn one server legal-action descriptor into a protocol message. */
  function actionMessage(a) {
    switch (a.kind) {
      case "move":
      case "capture":
        return { type: "Move", from: a.origin, to: a.target };
      case "spread":
        return { type: "SplitMove", from: a.origin };
      case "observe":
        return { type: "ObserveMove", square: a.origin };
      case "merge":
        return { type: "MergeMove", pieces: [a.piece_id, a.other_piece_id] };
      case "rejoin":
        return { type: "MergeMove", piece: a.piece_id, target: a.target };
      default:
        return null;
    }
  }

  function normalizeEvent(ev) {
    if (!ev) { return null; }
    var chances = (ev.chances || []).map(function (entry) {
      if (Array.isArray(entry) && entry.length === 2 && Array.isArray(entry[0])) {
        return { square: [Number(entry[0][0]), Number(entry[0][1])], weight: Number(entry[1]) };
      }
      return { square: [Number(entry[0]), Number(entry[1])], weight: Number(entry[2]) };
    });
    return {
      piece_id: ev.piece_id,
      owner: ev.owner,
      cause: ev.cause,
      chances: chances,
      sampled: Array.isArray(ev.sampled) ? [Number(ev.sampled[0]), Number(ev.sampled[1])] : null,
      probability: ev.probability,
    };
  }

  /* --------------------------------------------------------------- progress */

  function loadProgress() {
    try { return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {}; }
    catch (e) { return {}; }
  }

  function saveProgress(p) {
    try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(p)); } catch (e) { /* private mode */ }
  }

  function stageStats(level) {
    var entry = state.progress[String(level)];
    return entry || { games: 0, wins: 0 };
  }

  function stageCompleted(level) { return stageStats(level).games > 0; }

  function stageOverride() {
    var match = /[?&]stage=(\d+)/.exec(window.location.search);
    return match ? Number(match[1]) : null;
  }

  function isUnlocked(level) {
    if (level === 0) { return true; }
    var override = stageOverride();
    if (override !== null && level <= override) { return true; }
    return stageCompleted(level - 1);
  }

  function markCompleted(level, won) {
    var entry = stageStats(level);
    entry.games += 1;
    if (won) { entry.wins += 1; }
    state.progress[String(level)] = entry;
    saveProgress(state.progress);
  }

  /* --------------------------------------------------------------- screens */

  function showScreen(name) {
    state.screen = name;
    [
      "screen-landing", "screen-stages", "screen-mode", "screen-lobby",
      "screen-game", "screen-result",
    ].forEach(function (id) {
      var section = els[id];
      var target = "screen-" + name;
      if (id === target) { section.classList.remove("hidden"); }
      else { section.classList.add("hidden"); }
    });
  }

  function renderStages() {
    var grid = els["stage-grid"];
    clear(grid);
    STAGES.forEach(function (stage) {
      var unlocked = isUnlocked(stage.level);
      var card = make("button", "stage-card " + (unlocked ? "unlocked" : "locked"));
      card.type = "button";
      card.disabled = !unlocked;
      card.appendChild(make("span", "stage-title", stage.name));
      card.appendChild(make("span", "stage-mechanic", stage.mechanic));
      var stats = stageStats(stage.level);
      var stateText = unlocked
        ? (stats.games ? stats.games + " played, " + stats.wins + " won" : "not played yet")
        : "locked \u2014 complete the previous stage";
      card.appendChild(make("span", "stage-state", stateText));
      card.addEventListener("click", function () { chooseStage(stage.level); });
      grid.appendChild(card);
    });
  }

  function chooseStage(level) {
    state.stage = level;
    var stage = STAGES[level];
    els["mode-stage-note"].textContent = stage.name + ": " + stage.mechanic;
    showScreen("mode");
    maybeShowUnlock(level);
  }

  /* ------------------------------------------------------------ unlock modal */

  /* A stage that carries an `unlock` blurb is a stage whose mechanic the player has
   * just earned by finishing the one before it, so the note is shown once, the first
   * time that stage is opened -- that is the reward beat, not a help screen. Seen
   * stages are remembered in localStorage next to the progress record. */

  function unlockSeen(level) {
    try { return localStorage.getItem(PROGRESS_KEY + ".unlock." + level) === "1"; }
    catch (e) { return false; }
  }

  function markUnlockSeen(level) {
    try { localStorage.setItem(PROGRESS_KEY + ".unlock." + level, "1"); }
    catch (e) { /* private mode: the note simply shows again next time */ }
  }

  function maybeShowUnlock(level) {
    var stage = STAGES[level];
    if (!stage || !stage.unlock || unlockSeen(level)) { return; }
    markUnlockSeen(level);
    els["unlock-title"].textContent = stage.unlock.title;
    var body = els["unlock-body"];
    clear(body);
    stage.unlock.body.forEach(function (line) { body.appendChild(make("p", null, line)); });
    var modal = els["unlock-modal"];
    if (!modal) { return; }
    if (typeof modal.showModal === "function") { modal.showModal(); }
    else { modal.setAttribute("open", "open"); }
  }

  /* ------------------------------------------------------------ rules modal */

  function openRules(tabLevel) {
    state.rulesTab = tabLevel === undefined ? (state.stage === null ? 0 : state.stage) : tabLevel;
    renderRules();
    if (typeof els["rules-modal"].showModal === "function") {
      els["rules-modal"].showModal();
    } else {
      els["rules-modal"].setAttribute("open", "open");
    }
  }

  function renderRules() {
    var tabs = els["rules-tabs"];
    clear(tabs);
    STAGES.forEach(function (stage, index) {
      var tab = make("button", index === state.rulesTab ? "active" : "", "Stage " + stage.level);
      tab.type = "button";
      tab.addEventListener("click", function () { state.rulesTab = index; renderRules(); });
      tabs.appendChild(tab);
    });

    var stage = STAGES[state.rulesTab];
    var body = els["rules-body"];
    clear(body);
    body.appendChild(make("h3", null, stage.name));
    body.appendChild(make("p", null, stage.mechanic));
    var list = make("ul");
    stage.rule.forEach(function (line) { list.appendChild(make("li", null, line)); });
    body.appendChild(list);

    els["rules-caveat"].textContent =
      "This engine (deterministic-toy) implements a classical probability reading: occupancy " +
      "chances only. Quantum amplitudes, phase and interference are not modelled, and the " +
      "published paper's exact rules are unverified against our engine. Values are chance " +
      "weights, not quantum amplitudes.";
  }

  /* ------------------------------------------------------------- server/ws */

  function defaultServer() {
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
      return window.location.origin;
    }
    return "http://127.0.0.1:8000";
  }

  function setServer(value) {
    state.server = String(value).replace(/\/+$/, "");
    try { localStorage.setItem(SERVER_KEY, state.server); } catch (e) { /* ignore */ }
  }

  function wsUrl(gameId) {
    return state.server.replace(/^http/, "ws") + "/ws/" + gameId;
  }

  function checkServer() {
    els["server-status"].textContent = "checking\u2026";
    els["server-status"].className = "";
    fetch(state.server + "/api/health")
      .then(function (r) { return r.json(); })
      .then(function (body) {
        els["server-status"].textContent = "ok (" + body.games + " games)";
        els["server-status"].className = "ok";
      })
      .catch(function () {
        els["server-status"].textContent = "unreachable";
        els["server-status"].className = "bad";
      });
  }

  function createGame(level, mode, onReady) {
    fetch(state.server + "/api/game", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: level, mode: mode }),
    })
      .then(function (r) {
        if (!r.ok) { throw new Error("server rejected the game (" + r.status + ")"); }
        return r.json();
      })
      .then(function (body) {
        state.gameId = body.game_id;
        state.playerId = body.player_id;
        onReady(body);
      })
      .catch(function (err) { gameStatus(err.message, true); });
  }

  function connect(gameId, playerId, label) {
    closeSocket();
    state.connected = false;
    var socket;
    try {
      socket = new WebSocket(wsUrl(gameId));
    } catch (err) {
      gameStatus("could not open a websocket: " + err.message, true);
      return;
    }
    state.ws = socket;
    socket.addEventListener("open", function () {
      state.connected = true;
      var join = { type: "JoinGame" };
      if (playerId) { join.player_id = playerId; }
      if (label) { join.label = label; }
      socket.send(JSON.stringify(join));
    });
    socket.addEventListener("message", function (event) {
      var message;
      try { message = JSON.parse(event.data); } catch (e) { return; }
      handle(message);
    });
    socket.addEventListener("close", function () {
      state.connected = false;
      if (state.screen === "screen-game") {
        gameStatus("connection closed. Press Quit to leave.", true);
      }
    });
    socket.addEventListener("error", function () {
      gameStatus("websocket error \u2014 is the server running at " + state.server + "?", true);
    });
  }

  function closeSocket() {
    if (state.ws) {
      try { state.ws.close(); } catch (e) { /* already closed */ }
      state.ws = null;
    }
    state.connected = false;
  }

  function send(message) {
    if (!state.ws || state.ws.readyState !== 1) {
      gameStatus("not connected.", true);
      return false;
    }
    state.ws.send(JSON.stringify(message));
    return true;
  }

  /* ---------------------------------------------------------- message flow */

  function handle(message) {
    switch (message.type) {
      case "StateUpdate": onState(message); break;
      case "GameOver": onGameOver(message); break;
      case "Error": gameStatus(message.message + " (" + message.code + ")", true); break;
      case "Tick": break; // liveness only
      default: break;
    }
  }

  function onState(view) {
    var previousPly = state.view ? state.view.ply : -1;
    state.view = view;
    state.mySeat = view.you;

    if (view.status === "waiting") {
      els["lobby-code"].textContent = state.gameId;
      els["lobby-status"].textContent = "connected; waiting for an opponent\u2026";
      showScreen("lobby");
      return;
    }
    if (view.status === "playing" && state.screen !== "screen-game") {
      showScreen("game");
    }

    // A collapse arrived on this frame: open the inspector and play the reveal once, so
    // that a measurement is something you watch happen rather than something you have to
    // click into. A decoherence expiry is called out in the log as well, because the
    // player did not choose it and should not have to guess why their piece moved.
    if (view.last_event) {
      var incoming = normalizeEvent(view.last_event);
      setCollapse(incoming);
      if (view.ply !== previousPly && incoming && incoming.chances.length > 1) {
        collapsePlay();
      }
      if (view.ply !== previousPly && incoming && incoming.cause === "decoherence") {
        logEvent("ply " + view.ply + ": coherence expired \u2014 " + incoming.piece_id +
          " collapsed by itself onto " + squareText(incoming.sampled));
      }
    }
    // The inspector deliberately keeps showing the most recent collapse rather than
    // clearing on the next frame: against an agent the reply arrives within
    // milliseconds, which used to wipe the reveal before anyone could watch it. It is
    // replaced by the next collapse, exactly like the server's `last_event`.

    if (view.ply !== previousPly && view.last_action) {
      logEvent("ply " + view.ply + ": " + describeAction(view.last_action));
    }

    if (!state.connected) { gameStatus("read-only (spectating)."); }
    else { gameStatus(""); }
    render();
  }

  function onGameOver(message) {
    var won = state.mySeat !== null && message.result === state.mySeat;
    var text;
    if (message.result === null) { text = "Draw (" + message.reason + ")"; }
    else if (state.mode === "local") { text = playerLabel(message.result) + " wins (" + message.reason + ")"; }
    else if (won) { text = "You win (" + message.reason + ")"; }
    else { text = "You lose (" + message.reason + ")"; }

    if (state.stage !== null) { markCompleted(state.stage, won); }
    // The level is repeated here because this is the screen the player leaves from, and
    // "which level was that?" should not need a trip back into the board view.
    var level = state.view && state.view.board ? state.view.board.level : null;
    var stage = (typeof level === "number" && STAGES[level]) ? STAGES[level] : null;
    els["result-heading"].textContent = stage
      ? "Game over \u2014 level " + level + " (" + stage.name + ")"
      : "Game over";
    els["result-line"].textContent = text;
    els["btn-next"].disabled = state.stage === null || state.stage >= STAGES.length - 1;
    showScreen("result");
  }

  /* -------------------------------------------------------------- rendering */

  function render() {
    if (!state.view) { return; }
    renderBoard();
    renderLevelOutput();
    renderTurn();
    renderActions();
    renderUncertainty();
    renderCollapse();
  }

  function pieceIndex() {
    var byId = {};
    (state.view.board.pieces || []).forEach(function (p) { byId[p.piece_id] = p; });
    return byId;
  }

  /* Every legal action, keyed by the square it starts from. */
  function actionsByOrigin() {
    var map = {};
    (state.view.legal || []).forEach(function (a) {
      var k = key(a.origin[0], a.origin[1]);
      (map[k] = map[k] || []).push(a);
      // A merge can be selected from either of the two pieces.
      if (a.kind === "merge") {
        var other = pieceIndex()[a.other_piece_id];
        if (other) {
          other.sites.forEach(function (site) {
            var ok = key(site[0][0], site[0][1]);
            (map[ok] = map[ok] || []).push(a);
          });
        }
      }
    });
    return map;
  }

  /* Squares a spread piece also sits on, mapped to the square its actions are keyed by.
   * A ghost is *one* piece over several squares, so clicking any of its sites should
   * select it -- not only the site the split started from. Only pieces the mover can
   * act on are aliased, so an opponent's ghost stays inert. */
  function siteAliases(byOrigin) {
    var map = {};
    (state.view.board.pieces || []).forEach(function (p) {
      if (!p.uncertain || !p.sites.length) { return; }
      var origin = key(p.sites[0][0][0], p.sites[0][0][1]);
      if (!byOrigin[origin]) { return; }
      p.sites.forEach(function (s) {
        var k = key(s[0][0], s[0][1]);
        if (k !== origin) { map[k] = origin; }
      });
    });
    return map;
  }

  function actionTargets(a) {
    var byId = pieceIndex();
    if (a.kind === "move" || a.kind === "capture" || a.kind === "rejoin") {
      return [a.target];
    }
    if (a.kind === "spread") {
      return a.sites
        .map(function (s) { return s[0]; })
        .filter(function (sq) { return sq[0] !== a.origin[0] || sq[1] !== a.origin[1]; });
    }
    if (a.kind === "merge") {
      var other = byId[a.other_piece_id];
      return other ? other.sites.map(function (s) { return s[0]; }) : [];
    }
    return []; // observe has no square target
  }

  function renderBoard() {
    var board = els["board"];
    clear(board);
    var view = state.view;
    var size = view.board.board_size || 4;
    board.style.gridTemplateColumns = "repeat(" + size + ", 1fr)";
    board.style.gridTemplateRows = "repeat(" + size + ", 1fr)";

    var occupancy = view.occupancy || [];
    var byOrigin = actionsByOrigin();
    var siteAlias = siteAliases(byOrigin);
    var legal = view.legal || [];
    var targetKeys = {};
    var selectedActions = state.selected ? (byOrigin[state.selected] || []) : [];
    var allowedTargets = {};
    selectedActions.forEach(function (a) {
      actionTargets(a).forEach(function (t) { allowedTargets[key(t[0], t[1])] = a; });
    });

    var collapseStep = state.collapse.event ? state.collapse.step : null;
    var collapseSquare = null;
    var sampledSquare = null;
    if (state.collapse.event) {
      var ev = state.collapse.event;
      if (collapseStep < ev.chances.length) { collapseSquare = ev.chances[collapseStep].square; }
      if (collapseStep >= ev.chances.length && ev.sampled) { sampledSquare = ev.sampled; }
    }

    for (var row = 0; row < size; row += 1) {
      for (var col = 0; col < size; col += 1) {
        var k = key(row, col);
        var cell = make("div", "cell " + ((row + col) % 2 === 1 ? "dark" : "light"));
        cell.setAttribute("role", "gridcell");

        var pair = occupancy[row * size + col] || [0, 0];
        var top = pair[0] >= pair[1] ? 0 : 1;
        var chance = Number(pair[top]) || 0;

        if (chance > 0) {
          var uncertain = chance < 1 - 1e-9;
          var piece = make("span", "piece p" + top + (uncertain ? " ghost" : ""), pct(chance));
          piece.title = playerLabel(top) + " here with chance " + pct(chance);
          cell.appendChild(piece);
        }
        // Stage 4 only: the coherence counter sits on the square a piece split from.
        // `coherence` is `{}` at every other stage, so nothing renders there.
        var ticks = (view.coherence && view.coherence[k] !== undefined) ? view.coherence[k] : null;
        if (ticks !== null) {
          var badge = make("span", "coherence", ticks);
          badge.title = ticks + " turn" + (ticks === 1 ? "" : "s") +
            " of coherence left \u2014 at zero this piece collapses by itself";
          cell.appendChild(badge);
          cell.classList.add("has-coherence");
        }

        if (byOrigin[k] || siteAlias[k]) { cell.classList.add("can-move"); }
        if (state.selected === k) { cell.classList.add("selected"); }
        if (state.selected === k && observeActionAt(byOrigin, k)) {
          cell.classList.add("observe-ready");
        }
        if (allowedTargets[k]) {
          var action = allowedTargets[k];
          if (action.kind === "capture") { cell.appendChild(make("span", "capture-mark")); }
          else { cell.appendChild(make("span", "target-dot")); }
          cell.classList.add("target");
        }
        if (collapseSquare && collapseSquare[0] === row && collapseSquare[1] === col) {
          cell.classList.add("collapse-step");
        }
        if (sampledSquare && sampledSquare[0] === row && sampledSquare[1] === col) {
          cell.classList.add("sampled");
        }

        cell.setAttribute("aria-label", "row " + row + " column " + col);
        (function (r, c) {
          cell.addEventListener("click", function () { onSquareClick(r, c); });
        })(row, col);
        board.appendChild(cell);
      }
    }
    // Keep local references for click handling (avoids recomputing on every click).
    board._byOrigin = byOrigin;
    board._siteAliases = siteAlias;
    board._allowedTargets = allowedTargets;
  }

  /* The level readout.
   *
   * It prints the level the **server** built the engine with, not the stage this browser
   * asked for, so the two disagreeing is visible rather than silent -- which is the whole
   * point of an output instead of a label. It also carries the local progress record, so
   * the panel doubles as "where am I, and how have I done here". */
  function renderLevelOutput() {
    var host = els["level-output"];
    if (!host || !state.view) { return; }
    var board = state.view.board || {};
    var level = (typeof board.level === "number") ? board.level : null;
    var stage = (level !== null && STAGES[level]) ? STAGES[level] : null;
    var parts = [
      "LEVEL " + (level === null ? "?" : level) + " / " + (STAGES.length - 1),
    ];
    if (stage) { parts.push(stage.name.replace(/^Stage \d+ \u2014 /, "")); }
    var stats = (level !== null) ? stageStats(level) : { games: 0, wins: 0 };
    parts.push(stats.games
      ? stats.games + " played \u00b7 " + stats.wins + " won"
      : "first game at this level");
    if (state.stage !== null && level !== null && state.stage !== level) {
      parts.push("server built level " + level);
    }
    host.textContent = parts.join("  \u00b7  ");
  }

  function renderTurn() {
    var view = state.view;
    var yourTurn = view.you !== null && view.turn === view.you;
    var seatText;
    if (view.you === null) { seatText = "spectating"; }
    else if (state.mode === "local") { seatText = "local \u2014 " + playerLabel(view.turn) + " to move"; }
    else if (yourTurn) { seatText = "your move"; }
    else { seatText = "opponent's move"; }
    els["turn-indicator"].textContent = "ply " + view.ply + " \u2014 " + seatText;
    els["phase-chip"].textContent = "[" + view.phase + "]";
  }

  function renderActions() {
    var list = els["action-list"];
    clear(list);
    if (state.view.you === null) {
      els["action-hint"].textContent = "Spectating: moves are read-only.";
      return;
    }
    if (!(state.view.legal || []).length) {
      els["action-hint"].textContent = "No move for you right now.";
      return;
    }

    var byOrigin = actionsByOrigin();
    var actions;
    if (state.selected && byOrigin[state.selected]) {
      actions = byOrigin[state.selected];
      els["action-hint"].textContent = observeActionAt(byOrigin, state.selected)
        ? "This piece is uncertain. OBSERVE resolves it now \u2014 it costs your whole turn."
        : "Actions for " + state.selected.replace(",", ", ") + ":";
    } else {
      actions = state.view.legal;
      els["action-hint"].textContent = "Click one of your pieces, or pick an action below.";
    }

    actions.forEach(function (a) {
      var observing = a.kind === "observe";
      var button = make("button", "action-button" + (observing ? " observe-action" : ""));
      button.type = "button";
      button.appendChild(make("span", "kind", a.kind.toUpperCase()));
      button.appendChild(make("span", "detail", observing
        ? "resolve " + a.piece_id + " now \u2014 the engine samples its chances, you do not pick the square"
        : describeAction(a)));
      if (observing) { button.appendChild(make("span", "cost", "costs your turn")); }
      button.addEventListener("click", function () { perform(a); });
      list.appendChild(button);
    });
  }

  function renderUncertainty() {
    var host = els["uncertainty-list"];
    clear(host);
    var spread = (state.view.board.pieces || []).filter(function (p) { return p.uncertain; });
    if (!spread.length) {
      host.appendChild(make("p", "hint", "No spread pieces on the board."));
      return;
    }
    spread.forEach(function (p) {
      var row = make("div", "uncertainty-row");
      row.appendChild(make("span", "owner", "P" + p.owner + " " + p.piece_id));
      var sites = p.sites.map(function (s) { return squareText(s[0]) + " @" + pct(s[1]); }).join("  ");
      row.appendChild(make("span", "sites", sites));
      var origin = p.sites.length ? p.sites[0][0] : null;
      var ticks = (origin && state.view.coherence)
        ? state.view.coherence[key(origin[0], origin[1])]
        : undefined;
      if (ticks !== undefined) {
        row.appendChild(make("span", "coherence-note", "coherence " + ticks));
      }
      host.appendChild(row);
    });
    host.appendChild(make("p", "note",
      "Each row is one piece spread over several squares (a superposition of position), " +
      "not quantum entanglement."));
  }

  /* ---------------------------------------------------------- interaction */

  function onSquareClick(row, col) {
    var k = key(row, col);
    var board = els["board"];
    var allowed = (board._allowedTargets || {})[k];
    if (state.selected && allowed) {
      perform(allowed);
      return;
    }
    var byOrigin = board._byOrigin || {};
    // Any site of a spread piece selects the piece, via the square its actions use.
    var selected = byOrigin[k] ? k : (board._siteAliases || {})[k];
    state.selected = (selected && byOrigin[selected]) ? selected : null;
    render();
  }

  function perform(action) {
    var message = actionMessage(action);
    if (!message) { gameStatus("cannot send that action type.", true); return; }
    if (send(message)) {
      state.selected = null;
      gameStatus("sent: " + describeAction(action));
    }
  }

  /* ------------------------------------------------------ collapse inspector */

  function setCollapse(event) {
    clearCollapse();
    state.collapse.event = event;
    state.collapse.step = 0;
  }

  function clearCollapse() {
    if (state.collapse.timer !== null) {
      window.clearInterval(state.collapse.timer);
      state.collapse.timer = null;
    }
    state.collapse.event = null;
    state.collapse.step = 0;
  }

  function collapseStepCount() {
    var ev = state.collapse.event;
    return ev ? ev.chances.length + 1 : 0; // candidates, then the resolved frame
  }

  function collapseStep(delta) {
    var count = collapseStepCount();
    if (!count) { return; }
    state.collapse.step = Math.max(0, Math.min(state.collapse.step + delta, count - 1));
    renderCollapse();
    renderBoard();
  }

  function collapsePlay() {
    if (state.collapse.timer !== null) { collapsePause(); return; }
    state.collapse.timer = window.setInterval(function () {
      var count = collapseStepCount();
      if (state.collapse.step >= count - 1) { collapsePause(); return; }
      collapseStep(1);
    }, COLLAPSE_TICK_MS);
    renderCollapse();
  }

  function collapsePause() {
    if (state.collapse.timer !== null) {
      window.clearInterval(state.collapse.timer);
      state.collapse.timer = null;
    }
    renderCollapse();
  }

  function renderCollapse() {
    var host = els["collapse-body"];
    clear(host);
    var ev = state.collapse.event;
    if (!ev) {
      host.appendChild(make("p", "hint", "No measurement yet. A collapse appears here when a piece resolves."));
      return;
    }

    host.appendChild(make("p", null,
      "Collapse of " + ev.piece_id + " (cause: " + ev.cause + "). Step through the chances, then the outcome."));

    if (ev.cause === "decoherence") {
      host.appendChild(make("p", "note",
        "Auto-collapse: the coherence counter for " + ev.piece_id + " reached zero, so the " +
        "piece resolved by itself. Nothing chose this square \u2014 the chances did. This " +
        "rule is ours, and it is never part of a batched experiment."));
    }

    var controls = make("div", "collapse-controls");
    var first = make("button", null, "|\u25c0"); first.type = "button";
    var prev = make("button", null, "\u25c0"); prev.type = "button";
    var play = make("button", null, state.collapse.timer === null ? "Play" : "Pause"); play.type = "button";
    var next = make("button", null, "\u25b6"); next.type = "button";
    var last = make("button", null, "\u25b6|"); last.type = "button";
    first.addEventListener("click", function () { collapsePause(); state.collapse.step = 0; renderCollapse(); renderBoard(); });
    prev.addEventListener("click", function () { collapsePause(); collapseStep(-1); });
    next.addEventListener("click", function () { collapsePause(); collapseStep(1); });
    last.addEventListener("click", function () { collapsePause(); state.collapse.step = collapseStepCount() - 1; renderCollapse(); renderBoard(); });
    play.addEventListener("click", collapsePlay);
    [first, prev, play, next, last].forEach(function (b) { controls.appendChild(b); });
    host.appendChild(controls);

    var table = document.createElement("table");
    table.className = "collapse-table";
    var head = document.createElement("tr");
    ["square", "chance", "state"].forEach(function (t) { head.appendChild(make("th", null, t)); });
    table.appendChild(head);

    ev.chances.forEach(function (chance, index) {
      var tr = document.createElement("tr");
      var isSampled = ev.sampled && chance.square[0] === ev.sampled[0] && chance.square[1] === ev.sampled[1];
      if (index === state.collapse.step) { tr.className = "active"; }
      if (isSampled) { tr.className = (tr.className + " sampled").trim(); }
      tr.appendChild(make("td", null, squareText(chance.square)));
      tr.appendChild(make("td", null, pct(chance.weight)));
      tr.appendChild(make("td", null, isSampled ? "sampled" : "candidate"));
      table.appendChild(tr);
    });
    host.appendChild(table);

    var resolved = state.collapse.step >= ev.chances.length;
    host.appendChild(make("p", resolved ? "note" : "hint",
      resolved
        ? "Resolved: " + ev.piece_id + " is now certain on " + squareText(ev.sampled) + "."
        : "Before the collapse: " + ev.chances.length + " candidate square(s)."));
  }

  /* The observe action offered for the piece on square `k`, if any. Used to mark the
   * board and to phrase the hint, so the "resolve it now" option is discoverable from
   * the piece itself rather than only from the action list. */
  function observeActionAt(byOrigin, k) {
    var list = byOrigin[k] || [];
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].kind === "observe") { return list[i]; }
    }
    return null;
  }

  function logEvent(text) {
    var list = els["event-log"];
    var item = make("li", null, text);
    list.appendChild(item);
    while (list.childNodes.length > 60) { list.removeChild(list.firstChild); }
  }

  function gameStatus(text, isError) {
    if (!els["game-status"]) { return; }
    els["game-status"].textContent = text || "";
    els["game-status"].className = isError ? "game-status error" : "game-status";
  }

  /* --------------------------------------------------------------- actions */

  function startStage(level, mode) {
    state.stage = level;
    state.mode = mode;
    els["event-log"].innerHTML = "";
    clearCollapse();
    state.view = null;
    state.selected = null;

    if (mode === "local") {
      createGame(level, mode, function () { connect(state.gameId, state.playerId, "host"); });
      return;
    }
    if (mode === "online") {
      createGame(level, mode, function () {
        els["lobby-code"].textContent = state.gameId;
        els["lobby-status"].textContent = "connecting\u2026";
        showScreen("lobby");
        connect(state.gameId, state.playerId, "host");
      });
      return;
    }
    createGame(level, mode, function () { connect(state.gameId, state.playerId, "human"); });
  }

  function joinByCode() {
    var code = els["join-code"].value.trim();
    if (!code) { return; }
    state.gameId = code;
    state.playerId = null;
    state.mode = "online";
    state.stage = null;
    els["event-log"].innerHTML = "";
    clearCollapse();
    state.view = null;
    showScreen("lobby");
    els["lobby-code"].textContent = code;
    els["lobby-status"].textContent = "joining\u2026";
    connect(code, null, "guest");
  }

  function wire() {
    els["btn-start"].addEventListener("click", function () { renderStages(); showScreen("stages"); });
    els["btn-join-show"].addEventListener("click", function () {
      els["join-form"].classList.toggle("hidden");
    });
    els["btn-join"].addEventListener("click", joinByCode);
    els["join-code"].addEventListener("keydown", function (e) { if (e.key === "Enter") { joinByCode(); } });
    els["btn-rules"].addEventListener("click", function () { openRules(0); });
    els["btn-stages-rules"].addEventListener("click", function () { openRules(state.stage === null ? 0 : state.stage); });
    els["btn-stages-back"].addEventListener("click", function () { showScreen("landing"); });
    els["btn-mode-back"].addEventListener("click", function () { renderStages(); showScreen("stages"); });
    els["btn-lobby-cancel"].addEventListener("click", function () { closeSocket(); showScreen("landing"); });
    els["btn-game-rules"].addEventListener("click", function () { openRules(state.stage === null ? 0 : state.stage); });
    els["btn-resign"].addEventListener("click", function () {
      if (state.ws && state.connected) { send({ type: "Resign" }); }
    });
    els["btn-quit"].addEventListener("click", function () { closeSocket(); showScreen("landing"); });
    els["btn-again"].addEventListener("click", function () { if (state.stage !== null) { startStage(state.stage, state.mode); } });
    els["btn-next"].addEventListener("click", function () {
      if (state.stage !== null && state.stage < STAGES.length - 1) { startStage(state.stage + 1, state.mode); }
    });
    els["btn-home"].addEventListener("click", function () { closeSocket(); renderStages(); showScreen("landing"); });

    els["server-check"].addEventListener("click", function () {
      setServer(els["server-url"].value);
      checkServer();
    });

    Array.prototype.forEach.call(document.querySelectorAll(".mode-card"), function (card) {
      card.addEventListener("click", function () {
        startStage(state.stage === null ? 0 : state.stage, card.getAttribute("data-mode"));
      });
    });
  }

  /* ------------------------------------------------------------------ boot */

  function init() {
    cache();
    state.progress = loadProgress();
    var stored = null;
    try { stored = localStorage.getItem(SERVER_KEY); } catch (e) { stored = null; }
    // Priority: explicit ?server= (useful when the viewer is opened from disk and the
    // server runs on a non-default port), then the last value the user checked, then
    // the page's own origin or the documented default.
    var fromQuery = null;
    try { fromQuery = new URLSearchParams(window.location.search).get("server"); }
    catch (e) { fromQuery = null; }
    els["server-url"].value = fromQuery || stored || defaultServer();
    setServer(els["server-url"].value);
    els["engine-note"].textContent =
      "Engine: deterministic-toy. The upstream Cheqqers engine is not integrated, so no " +
      "result here reproduces the paper. Quantum amplitudes, phase and entanglement are not modelled.";
    wire();
    renderStages();
    checkServer();
    showScreen("landing");
  }

  /* ----------------------------------------------------------------- hooks */

  /* Two small hooks so the browser acceptance check (scripts/browser_check.py) can
   * drive a raw protocol frame and inspect what the client received. They only expose
   * what a user could already send from the devtools console, and they are the reason
   * the "server-rejected illegal moves are shown, never applied" acceptance can be
   * tested through the real UI rather than only at the API level. */
  window.__qkSend = function (message) { return send(message); };
  window.__qkState = function () {
    return {
      screen: state.screen,
      gameId: state.gameId,
      playerId: state.playerId,
      stage: state.stage,
      mode: state.mode,
      mySeat: state.mySeat,
      ply: state.view ? state.view.ply : null,
      occupancy: state.view ? state.view.occupancy : null,
      turn: state.view ? state.view.turn : null,
      level: state.view && state.view.board ? state.view.board.level : null,
      levelOutput: els["level-output"] ? els["level-output"].textContent : null,
      coherence: state.view ? state.view.coherence : null,
      status: state.view ? state.view.status : null,
      unlockOpen: !!(els["unlock-modal"] && els["unlock-modal"].open),
      unlockTitle: els["unlock-title"] ? els["unlock-title"].textContent : null,
    };
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
