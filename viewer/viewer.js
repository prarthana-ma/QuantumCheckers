/* QuriousMinds replay viewer -- plain ES2018, no framework, no build step.
 *
 * Owner: Person E (replay viewer and reproducibility package).
 *
 * Design constraints, all deliberate:
 *
 * 1. Works from a `file://` URL. No fetch, no module imports, no network. The payload
 *    is read from a file input, because a `fetch` of a local path is blocked by every
 *    modern browser's CORS rules.
 * 2. Reads only what `qcheckers.viz.replay.build_replay` emits. That function is a pure
 *    function of the log, so the viewer cannot disagree with the log. If a field is
 *    missing the viewer degrades to "unknown" rather than throwing mid-render.
 * 3. Says plainly that amplitudes are not displayed. Whether the published game uses
 *    amplitudes and phases is UNVERIFIED (Gate 5), so the note comes from the payload
 *    rather than being hard-coded here.
 * 4. Keyboard accessible: arrows step, space plays, Home/End jump. Turn selection in the
 *    timeline is a click target with `aria-current`, so it is reachable without a mouse.
 */

(function () {
  "use strict";

  /* ---------------------------------------------------------------- state */

  var state = {
    payload: null,
    index: 0,
    timer: null,
    speed: 600,
    collapseOnly: false,
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function cacheElements() {
    [
      "load-form",
      "file-input",
      "load-status",
      "provenance",
      "game-panel",
      "game-meta",
      "amplitude-note",
      "board-section",
      "board",
      "timeline-section",
      "timeline",
      "controls",
      "first",
      "prev",
      "play",
      "next",
      "last",
      "speed",
      "collapse-only",
      "turn-readout",
      "progress",
      "event-panel",
      "event-detail",
    ].forEach(function (id) {
      els[id] = $(id);
    });
  }

  /* --------------------------------------------------------------- helpers */

  function frames() {
    if (!state.payload || !Array.isArray(state.payload.frames)) {
      return [];
    }
    if (!state.collapseOnly) {
      return state.payload.frames;
    }
    return state.payload.frames.filter(function (frame) {
      return frame.collapsed;
    });
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function chancePercent(value) {
    var number = Number(value);
    if (!isFinite(number)) {
      return "";
    }
    return Math.round(number * 100) + "%";
  }

  function playerLabel(player) {
    if (player === 0 || player === 1) {
      return "player " + player;
    }
    return "player " + (player === null || player === undefined ? "?" : player);
  }

  function describeAction(action) {
    if (!action || typeof action !== "object") {
      return "(unknown action)";
    }
    var kind = action.kind || "?";
    var square = function (pair) {
      return Array.isArray(pair) ? "(" + pair[0] + "," + pair[1] + ")" : "?";
    };
    switch (kind) {
      case "move":
        return (
          "move " +
          action.piece_id +
          " " +
          square(action.origin) +
          "->" +
          square(action.target)
        );
      case "capture":
        return (
          "capture " +
          action.piece_id +
          " " +
          square(action.origin) +
          " over " +
          square(action.jumped) +
          "->" +
          square(action.target)
        );
      case "spread":
        var sites = Array.isArray(action.sites)
          ? action.sites
              .map(function (site) {
                return square(site) + "@" + chancePercent(site[1]);
              })
              .join(" ")
          : "?";
        return "spread " + action.piece_id + " " + sites;
      case "rejoin":
        return "rejoin " + action.piece_id + " ->" + square(action.target);
      case "observe":
        return "OBSERVE " + action.piece_id;
      default:
        return kind + " " + (action.piece_id || "");
    }
  }

  /* ---------------------------------------------------------------- loader */

  function setStatus(message, isError) {
    els["load-status"].textContent = message;
    els["load-status"].className = isError ? "hint error" : "hint";
  }

  /* A JSONL log is many objects, one per line; a replay payload is a single object.
   * Accept either by trying the whole text as one document first. */
  function parsePayload(text, fileName) {
    var trimmed = text.trim();
    if (!trimmed) {
      throw new Error("file is empty");
    }

    var whole = null;
    try {
      whole = JSON.parse(trimmed);
    } catch (error) {
      whole = null;
    }

    if (whole && whole.frames) {
      return whole;
    }

    if (whole && Array.isArray(whole)) {
      throw new Error("expected one replay payload per file");
    }

    var lines = trimmed.split(/\r?\n/).filter(function (line) {
      return line.trim().length > 0;
    });
    if (lines.length > 1) {
      var first = null;
      try {
        first = JSON.parse(lines[0]);
      } catch (error) {
        throw new Error("first JSONL record is not valid JSON");
      }
      setStatus(
        "Loaded the first of " +
          lines.length +
          " JSONL records from " +
          fileName +
          ". Export a replay payload for the turn-level view.",
        false,
      );
      // A raw game record has `turns`, not `frames`; build frames from it here so the
      // viewer still works on a raw log.
      return rawRecordToPayload(first);
    }

    throw new Error("unrecognised file: not a replay payload or a JSONL log");
  }

  /* Minimal client-side equivalent of build_replay, for when the user drops a raw
   * .jsonl log instead of an exported payload. Same field names, same layout. */
  function rawRecordToPayload(record) {
    var size = 4;
    var finalBoard = record.final_board || {};
    if (
      typeof finalBoard.board_size === "number" &&
      finalBoard.board_size > 0
    ) {
      size = finalBoard.board_size;
    }

    var built = [];
    (record.turns || []).forEach(function (turn, position) {
      var board = turn.board_after || {};
      var claims = {};
      (board.pieces || []).forEach(function (piece) {
        var owner = Number(piece.owner) || 0;
        (piece.sites || []).forEach(function (site) {
          var row = Array.isArray(site) ? Number(site[0][0]) : Number(site[0]);
          var col = Array.isArray(site) ? Number(site[0][1]) : Number(site[1]);
          var weight = Array.isArray(site) ? Number(site[1]) : Number(site[2]);
          var key = row + ":" + col;
          if (!claims[key]) {
            claims[key] = [0, 0];
          }
          claims[key][owner] = Math.max(claims[key][owner], weight);
        });
      });

      var cells = [];
      for (var row = 0; row < size; row += 1) {
        for (var col = 0; col < size; col += 1) {
          var chances = claims[row + ":" + col] || [0, 0];
          cells.push({
            row: row,
            col: col,
            chances: chances,
            occupied: Math.max(chances[0], chances[1]) > 0,
            uncertain:
              Math.max(chances[0], chances[1]) > 0 &&
              Math.max(chances[0], chances[1]) < 1 - 1e-9,
            ambiguous: chances[0] > 0 && chances[1] > 0,
          });
        }
      }

      built.push({
        index: position,
        ply: typeof turn.ply === "number" ? turn.ply : position,
        player: turn.player,
        action: turn.action || {},
        cells: cells,
        collapsed: Boolean(turn.events && turn.events.length),
        events: (turn.events || []).map(function (event) {
          return {
            piece_id: event.piece_id,
            owner: event.owner,
            cause: event.cause,
            chances: (event.chances || []).map(function (entry) {
              return [Number(entry[0]), Number(entry[1]), Number(entry[2])];
            }),
            sampled: Array.isArray(event.sampled) ? event.sampled : null,
            probability: event.probability,
          };
        }),
        captured: board.captured || [],
      });
    });

    return {
      schema: "qcheckers-replay/1 (client-side, from raw JSONL)",
      header: {
        game_id: record.game_id,
        seed: record.seed,
        condition: record.condition,
        engine: record.engine,
        level: record.level,
        allow_observe: Boolean(record.allow_observe),
        toy_engine: Boolean(record.toy_engine),
        players: record.players || {},
        winner: record.winner,
        termination: record.termination,
        length: record.length,
      },
      board_size: size,
      amplitude_display: false,
      amplitude_note:
        "Built in the browser from a raw JSONL log. Chances only; amplitudes are not " +
        "displayed. Whether the published game uses amplitudes and phases is UNVERIFIED " +
        "until Gate 5.",
      summary: {
        collapses: record.collapses,
        collapse_pieces: record.collapse_pieces || [],
        observe_moves: record.observe_moves,
        spread_moves: record.spread_moves,
        rejoin_moves: record.rejoin_moves,
        capture_moves: record.capture_moves,
        board_moves: record.board_moves,
        final_board: record.final_board,
      },
      frames: built,
    };
  }

  function handleLoad(event) {
    event.preventDefault();
    var input = els["file-input"];
    if (!input.files || !input.files.length) {
      setStatus("Choose a file first.", true);
      return;
    }
    var file = input.files[0];
    var reader = new FileReader();
    reader.onerror = function () {
      setStatus("Could not read " + file.name + ".", true);
    };
    reader.onload = function () {
      try {
        var payload = parsePayload(String(reader.result), file.name);
        adopt(payload, file.name);
      } catch (error) {
        setStatus("Failed to load " + file.name + ": " + error.message, true);
      }
    };
    reader.readAsText(file);
  }

  function adopt(payload, fileName) {
    stop();
    state.payload = payload;
    state.index = 0;
    state.collapseOnly = false;
    els["collapse-only"].checked = false;

    var header = payload.header || {};
    els["provenance"].innerHTML =
      "<strong>Toy engine.</strong> Upstream Cheqqers engine: " +
      (header.toy_engine
        ? "<em>not integrated</em> (Gate 2 open)."
        : "<em>unknown engine</em> (" + (header.engine || "unnamed") + ").") +
      " Loaded from " +
      fileName +
      ". Nothing here is a reproduced paper result.";

    [
      "game-panel",
      "board-section",
      "timeline-section",
      "controls",
      "event-panel",
    ].forEach(function (id) {
      els[id].classList.remove("hidden");
    });

    renderMeta();
    renderTimeline();
    show(0);
    setStatus(
      "Loaded " +
        (header.game_id || "payload") +
        " (" +
        (payload.frames || []).length +
        " turns).",
      false,
    );
  }

  /* ----------------------------------------------------------------- meta */

  function renderMeta() {
    var header = (state.payload && state.payload.header) || {};
    var summary = (state.payload && state.payload.summary) || {};
    var players = header.players || {};
    var winnerText = "draw";
    if (header.winner === 0 || header.winner === 1) {
      winnerText = playerLabel(header.winner) + " wins";
    }

    var facts = [
      ["game id", header.game_id],
      ["seed", header.seed],
      ["condition", header.condition],
      ["engine", header.engine],
      ["level", header.level],
      ["Observe allowed", header.allow_observe ? "yes" : "no"],
      ["player 0", players["0"]],
      ["player 1", players["1"]],
      ["result", winnerText + " (" + (header.termination || "?") + ")"],
      ["plies", header.length],
      ["collapses", summary.collapses],
      ["Observe moves", summary.observe_moves],
      ["spread moves", summary.spread_moves],
      ["captures", summary.capture_moves],
    ];

    var list = els["game-meta"];
    clear(list);
    facts.forEach(function (pair) {
      var value = pair[1];
      if (value === undefined || value === null || value === "") {
        value = "unknown";
      }
      var wrapper = make("div");
      wrapper.appendChild(make("dt", null, pair[0]));
      wrapper.appendChild(make("dd", null, value));
      list.appendChild(wrapper);
    });

    var note = els["amplitude-note"];
    note.textContent =
      (state.payload && state.payload.amplitude_note) ||
      "Chances only. Amplitudes are not displayed.";
  }

  /* ---------------------------------------------------------------- board */

  function renderBoard(frame) {
    var board = els["board"];
    clear(board);

    var size = (state.payload && state.payload.board_size) || 4;
    board.style.gridTemplateColumns = "repeat(" + size + ", 1fr)";
    board.style.gridTemplateRows = "repeat(" + size + ", 1fr)";

    var cells = (frame && frame.cells) || [];
    var bySquare = {};
    cells.forEach(function (cell) {
      bySquare[cell.row + ":" + cell.col] = cell;
    });

    for (var row = 0; row < size; row += 1) {
      for (var col = 0; col < size; col += 1) {
        var cell = bySquare[row + ":" + col] || {
          chances: [0, 0],
          occupied: false,
          uncertain: false,
        };
        var chances = cell.chances || [0, 0];
        var top = chances[0] >= chances[1] ? 0 : 1;
        var topChance = Number(chances[top]) || 0;

        var node = make("div", "cell");
        // Playable squares in the toy engine are where row + col is odd; when the
        // payload does not say, colour every square so the board is still readable.
        node.classList.add((row + col) % 2 === 1 ? "dark" : "light");
        if (cell.occupied) {
          node.classList.add("owner-" + top);
          node.appendChild(make("span", "chance", chancePercent(topChance)));
          if (cell.uncertain) {
            node.classList.add("uncertain");
            node.title =
              "player " + top + " here with chance " + chancePercent(topChance);
          }
        }
        if (frame && frame.collapsed && cell.occupied) {
          node.classList.add("collapse");
        }
        node.setAttribute(
          "aria-label",
          "row " +
            row +
            " column " +
            col +
            ", player " +
            top +
            " " +
            chancePercent(topChance) +
            " likely",
        );
        board.appendChild(node);
      }
    }
  }

  /* ------------------------------------------------------------- timeline */

  function renderTimeline() {
    var list = els["timeline"];
    clear(list);

    frames().forEach(function (frame, position) {
      var item = make("li");
      item.setAttribute("data-position", position);
      item.appendChild(make("span", "turn-index", "t" + frame.ply));
      var who = make(
        "span",
        "turn-player p" + frame.player,
        playerLabel(frame.player),
      );
      item.appendChild(who);
      item.appendChild(
        make("span", "turn-action", describeAction(frame.action)),
      );
      if (frame.collapsed) {
        var causes = (frame.events || [])
          .map(function (event) {
            return event.cause;
          })
          .join(", ");
        item.appendChild(
          make("span", "turn-flag", "COLLAPSE (" + causes + ")"),
        );
      }
      item.addEventListener("click", function () {
        stop();
        show(position);
      });
      list.appendChild(item);
    });
  }

  function markCurrent(position) {
    var items = els["timeline"].querySelectorAll("li");
    Array.prototype.forEach.call(items, function (item, offset) {
      if (offset === position) {
        item.setAttribute("aria-current", "true");
      } else {
        item.removeAttribute("aria-current");
      }
    });
    if (items[position] && items[position].scrollIntoView) {
      items[position].scrollIntoView({ block: "nearest" });
    }
  }

  /* ------------------------------------------------------------ turn view */

  function show(position) {
    var list = frames();
    if (!list.length) {
      return;
    }
    state.index = Math.max(0, Math.min(position, list.length - 1));
    var frame = list[state.index];

    renderBoard(frame);
    renderEventDetail(frame);

    els["turn-readout"].textContent =
      "turn " +
      (state.index + 1) +
      " / " +
      list.length +
      "  (ply " +
      frame.ply +
      ", " +
      playerLabel(frame.player) +
      ")";
    els["progress"].max = list.length;
    els["progress"].value = state.index + 1;

    markCurrent(state.index);
    updateButtons(list.length);
  }

  function updateButtons(total) {
    els.first.disabled = state.index <= 0;
    els.prev.disabled = state.index <= 0;
    els.next.disabled = state.index >= total - 1;
    els.last.disabled = state.index >= total - 1;
  }

  function renderEventDetail(frame) {
    var host = els["event-detail"];
    clear(host);

    var facts = make("dl", "fact");
    [
      ["ply", frame.ply],
      ["player", playerLabel(frame.player)],
      ["action", (frame.action && frame.action.kind) || "?"],
      ["piece", (frame.action && frame.action.piece_id) || "unknown"],
      ["captured so far", (frame.captured || []).length],
    ].forEach(function (pair) {
      var wrapper = make("div");
      wrapper.appendChild(make("dt", null, pair[0]));
      wrapper.appendChild(
        make("dd", null, pair[1] === undefined ? "unknown" : pair[1]),
      );
      facts.appendChild(wrapper);
    });
    host.appendChild(facts);

    host.appendChild(make("p", null, describeAction(frame.action)));

    if (!frame.collapsed) {
      host.appendChild(
        make("p", "amplitude-note", "No collapse on this turn."),
      );
      return;
    }

    (frame.events || []).forEach(function (event) {
      var block = make("div", "collapse-block");
      block.appendChild(
        make("h3", null, "Collapse -- cause: " + (event.cause || "?")),
      );
      block.appendChild(
        make(
          "p",
          null,
          event.piece_id +
            " was uncertain over " +
            (event.chances || []).length +
            " square(s). The engine's chance rule sampled " +
            (Array.isArray(event.sampled)
              ? "(" + event.sampled[0] + "," + event.sampled[1] + ")"
              : "?") +
            " with probability " +
            chancePercent(event.probability) +
            ".",
        ),
      );

      var table = document.createElement("table");
      var head = document.createElement("tr");
      ["square", "chance before"].forEach(function (title) {
        head.appendChild(make("th", null, title));
      });
      table.appendChild(head);
      (event.chances || []).forEach(function (chance) {
        var row = document.createElement("tr");
        var sampledHere =
          Array.isArray(event.sampled) &&
          chance[0] === event.sampled[0] &&
          chance[1] === event.sampled[1];
        var squareCell = make(
          "td",
          sampledHere ? "sampled" : null,
          "(" + chance[0] + "," + chance[1] + ")",
        );
        if (sampledHere) {
          squareCell.appendChild(document.createTextNode(" <- sampled"));
        }
        row.appendChild(squareCell);
        row.appendChild(make("td", null, chancePercent(chance[2])));
        table.appendChild(row);
      });
      block.appendChild(table);
      host.appendChild(block);
    });
  }

  /* ------------------------------------------------------------- controls */

  function play() {
    var list = frames();
    if (list.length < 2) {
      return;
    }
    if (state.index >= list.length - 1) {
      state.index = 0;
      show(0);
    }
    els.play.textContent = "Pause";
    state.timer = window.setInterval(function () {
      if (state.index >= frames().length - 1) {
        stop();
        return;
      }
      show(state.index + 1);
    }, state.speed);
  }

  function stop() {
    if (state.timer !== null) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
    els.play.textContent = "Play";
  }

  function toggle() {
    if (state.timer === null) {
      play();
    } else {
      stop();
    }
  }

  function step(delta) {
    stop();
    show(state.index + delta);
  }

  function onKey(event) {
    if (!state.payload) {
      return;
    }
    switch (event.key) {
      case "ArrowLeft":
        step(-1);
        break;
      case "ArrowRight":
        step(1);
        break;
      case "Home":
        stop();
        show(0);
        break;
      case "End":
        stop();
        show(frames().length - 1);
        break;
      case " ":
      case "Spacebar":
        toggle();
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  function wireControls() {
    els["load-form"].addEventListener("submit", handleLoad);
    els.first.addEventListener("click", function () {
      stop();
      show(0);
    });
    els.last.addEventListener("click", function () {
      stop();
      show(frames().length - 1);
    });
    els.prev.addEventListener("click", function () {
      step(-1);
    });
    els.next.addEventListener("click", function () {
      step(1);
    });
    els.play.addEventListener("click", toggle);

    els.speed.addEventListener("change", function () {
      state.speed = Number(els.speed.value) || 600;
      if (state.timer !== null) {
        stop();
        play();
      }
    });

    els["collapse-only"].addEventListener("change", function () {
      stop();
      state.collapseOnly = els["collapse-only"].checked;
      state.index = 0;
      renderTimeline();
      show(0);
    });

    document.addEventListener("keydown", onKey);
  }

  /* ----------------------------------------------------------------- boot */

  function init() {
    cacheElements();
    wireControls();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
