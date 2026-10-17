"""Browser acceptance check for the game client (Phase 2).

Owner: **P4 -- frontend and delivery**, with **P5** owning the server it drives.

This is *not* part of the pytest suite: it needs a real Chromium and a running server,
so it is a script a human (or CI with browsers installed) runs deliberately:

    python scripts/browser_check.py

It checks the Phase 2 acceptance claims through the real UI, not the API:

1. A full Level-1 game vs the Easy (random) agent can be played to the result screen
   with **zero console errors**, preferring quantum actions when they are offered.
2. All **five** stages render their board and rule text, and the engine level matches.
3. A server-rejected illegal move sent from the client is **shown and not applied** --
   the board and ply are unchanged afterwards.
4. The **Observe affordance**: selecting one of your own ghost pieces offers an Observe
   button that says it costs the turn, and clicking it plays a collapse.
5. **Stage 4**: a split piece shows a coherence counter that ticks down, and a piece
   left alone collapses by itself, opening the same reveal inspector as any other
   measurement.
6. The **unlock notes** for the two stages that carry a mechanic the team owns appear
   once, when the stage is first opened.
7. The three **demo replay payloads** load in the static replay viewer, with the timeline
   showing every turn the payload contains and the amplitude caveat still on screen.

Requires: ``pip install playwright`` and ``playwright install chromium``. If no browser
is available the script says so and exits 2 rather than pretending to pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Actions that exercise an uncertainty mechanic, preferred when offered.
QUANTUM_KINDS = ("SPREAD", "OBSERVE", "REJOIN", "MERGE")

#: The word each stage's rule text must contain (one mechanic per stage).
STAGE_KEYWORDS = {0: "Classical", 1: "Split", 2: "Rejoin", 3: "Merge", 4: "Decoherence"}

#: Stages whose unlock note exists, mapped to the phrase that must appear in its title.
#: These two are the mechanics the *team* owns: voluntary measurement (the ablation's
#: subject) and decoherence (our own outreach rule), so the note that introduces each
#: one is checked rather than assumed.
UNLOCK_NOTES = {2: "voluntary measurement", 4: "Decoherence"}

#: Demo replay payloads written by ``scripts/make_demo_seeds.py``.
DEMO_NAMES = ("demo-classical.json", "demo-observe.json", "demo-decoherence.json")


def demo_payloads(results_dir: Path) -> dict[str, int]:
    """The demo payloads on disk, mapped to the turn count each one must display.

    The expected count is read out of the payload rather than typed here, so the check
    compares the viewer against the artifact and cannot go vacuous when the demo is
    regenerated.
    """
    found: dict[str, int] = {}
    for name in DEMO_NAMES:
        path = results_dir / name
        if path.exists():
            header = json.loads(path.read_text(encoding="utf-8"))["header"]
            found[name] = int(header["length"])
    return found

#: Console noise that is not an application error and must not fail the check.
IGNORED_CONSOLE = ("favicon",)


def wait_for_server(base: str, timeout_s: float = 20.0) -> None:
    """Poll ``/api/health`` until the server answers or the timeout expires."""
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
                if json.loads(response.read()).get("status") == "ok":
                    return
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.4)
    raise TimeoutError(f"server did not become ready: {last_error}")


def start_server(port: int, log_path: Path) -> subprocess.Popen[bytes]:
    """Start ``python -m server`` and wait for it to answer."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server",
            "--port",
            str(port),
            "--tick",
            "0.5",
            "--log",
            str(log_path),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    wait_for_server(f"http://127.0.0.1:{port}")
    return process


class Checker:
    """Collects pass/fail lines so every check runs even after one fails."""

    def __init__(self) -> None:
        self.results: list[tuple[bool, str]] = []

    def check(self, ok: bool, label: str) -> None:
        self.results.append((bool(ok), label))
        print(("  PASS  " if ok else "  FAIL  ") + label)

    def summary(self) -> int:
        failed = [label for ok, label in self.results if not ok]
        print("")
        print(f"{len(self.results) - len(failed)}/{len(self.results)} checks passed")
        for label in failed:
            print(f"  FAILED: {label}")
        return 0 if not failed else 1


class Client:
    """Thin wrapper over a Playwright page for this specific app."""

    def __init__(self, page, base: str) -> None:
        self.page = page
        self.base = base
        self.turn_count = 0
        self.console_errors: list[str] = []
        page.on("pageerror", lambda exc: self.console_errors.append(f"pageerror: {exc}"))

        def on_console(message) -> None:
            if message.type != "error":
                return
            text = message.text
            if any(token in text for token in IGNORED_CONSOLE):
                return
            self.console_errors.append(f"console: {text}")

        page.on("console", on_console)

    # -- navigation --------------------------------------------------------

    def open(self, stage: int) -> None:
        uri = (REPO_ROOT / "viewer" / "game.html").as_uri()
        self.page.goto(f"{uri}?stage={stage}&server={self.base}")
        self.page.wait_for_selector("#screen-landing:not(.hidden)", timeout=15000)

    def to_stage_screen(self) -> None:
        self.page.click("#btn-start")
        self.page.wait_for_selector("#screen-stages:not(.hidden)")

    def choose_stage(self, stage: int) -> str | None:
        """Open a stage, returning the title of its unlock note if one appeared.

        The note is shown once per stage (it is remembered in localStorage), so this is
        the only moment a check can see it. It is dismissed here because an open modal
        blocks the clicks the rest of the check needs.
        """
        self.page.locator("#stage-grid .stage-card").nth(stage).click()
        self.page.wait_for_selector("#screen-mode:not(.hidden)")
        return self.dismiss_unlock()

    def dismiss_unlock(self) -> str | None:
        """Close the unlock note if this stage opened one, and return its title."""
        if self.page.locator("#unlock-modal[open]").count() == 0:
            return None
        title = self.page.inner_text("#unlock-title").strip()
        self.page.click("#btn-unlock-continue")
        self.page.wait_for_selector("#unlock-modal", state="hidden")
        return title

    def pick_mode(self, mode: str) -> None:
        self.page.locator(f'.mode-card[data-mode="{mode}"]').click()
        self.page.wait_for_selector("#screen-game:not(.hidden)", timeout=20000)

    def wait_for_ply_change(self, before: int, timeout_ms: int = 30000) -> None:
        self.page.wait_for_function(
            "previous => __qkState().ply !== previous"
            " || !document.querySelector('#screen-result').classList.contains('hidden')",
            arg=before,
            timeout=timeout_ms,
        )

    def rules_text(self) -> str:
        self.page.click("#btn-stages-rules")
        self.page.wait_for_selector("#rules-modal[open]")
        text = self.page.inner_text("#rules-body")
        self.page.click("#rules-close")
        return text

    # -- play --------------------------------------------------------------

    def is_result(self) -> bool:
        return self.page.locator("#screen-result:not(.hidden)").count() > 0

    def wait_for_turn(self, timeout_ms: int = 30000) -> bool:
        self.page.wait_for_function(
            "() => document.querySelectorAll('#action-list .action-button').length > 0"
            " || !document.querySelector('#screen-result').classList.contains('hidden')",
            timeout=timeout_ms,
        )
        return not self.is_result()

    def take_action(self, quantum_every: int = 3, quiet: bool = False) -> str:
        """Click one action, mixing sensible play with periodic quantum moves.

        Strategy, in plain words: take a capture when one is offered, otherwise move,
        and on every ``quantum_every``-th turn prefer a split/observe/rejoin/merge so
        the acceptance also exercises the uncertainty visuals. It is deliberately not
        "always split": in this engine a spread piece is immobile until it is resolved,
        so always splitting is a losing gimmick, and the point of the check is a real
        game rather than a demonstration of the fastest possible loss.

        ``quiet`` prefers plain moves and never takes a capture when a quiet move exists.
        That is how the stage-4 expiry is reached on purpose: with nobody capturing, a
        spread piece cannot be resolved by anyone else, so it must run out of
        coherence. Captures are never forced in this engine, so this always terminates.
        """
        self.turn_count += 1
        prefer_quantum = quantum_every > 0 and self.turn_count % quantum_every == 0
        if prefer_quantum:
            ranking = {"CAPTURE": 1, "MOVE": 2, "SPREAD": 0, "OBSERVE": 0, "REJOIN": 0, "MERGE": 0}
        elif quiet:
            ranking = {"MOVE": 0, "SPREAD": 1, "MERGE": 1, "REJOIN": 1, "OBSERVE": 1, "CAPTURE": 9}
        else:
            ranking = {"CAPTURE": 0, "MOVE": 1, "SPREAD": 2, "REJOIN": 2, "MERGE": 2, "OBSERVE": 3}

        buttons = self.page.locator("#action-list .action-button")
        chosen = 0
        best_rank = None
        kind = buttons.nth(0).locator(".kind").inner_text().strip()
        for index in range(buttons.count()):
            candidate = buttons.nth(index).locator(".kind").inner_text().strip()
            rank = ranking.get(candidate, 9)
            if best_rank is None or rank < best_rank:
                chosen, best_rank, kind = index, rank, candidate
        buttons.nth(chosen).click()
        return kind

    def play_to_result(self, max_plies: int = 400) -> dict[str, object]:
        """Play until the result screen, preferring quantum actions."""
        kinds: dict[str, int] = {}
        plies = 0
        for _ in range(max_plies):
            if self.is_result():
                break
            if not self.wait_for_turn():
                break
            before = self.page.evaluate("() => __qkState().ply")
            kind = self.take_action()
            kinds[kind] = kinds.get(kind, 0) + 1
            self.wait_for_ply_change(before)
            plies += 1
        return {"plies": plies, "kinds": kinds, "reached_result": self.is_result()}

    def select_uncertain_square(self, own: bool = True) -> bool:
        """Click a square holding an uncertain piece, if the board shows one.

        Reads the occupancy the server sent, so it needs no rules knowledge of its own.
        With ``own`` it insists the ghost belongs to the **seat to move** -- only the
        owner can observe their own piece, which is the affordance being checked.
        """
        info = self.page.evaluate("() => __qkState()")
        occupancy = info.get("occupancy") or []
        turn = int(info.get("turn") if info.get("turn") is not None else 0)
        for index, pair in enumerate(occupancy):
            chances = [float(pair[0] or 0), float(pair[1] or 0)]
            if own:
                uncertain = 0.0 < chances[turn] < 1.0 - 1e-9
            else:
                uncertain = 0.0 < max(chances) < 1.0 - 1e-9
            if uncertain:
                self.page.locator("#board .cell").nth(index).click()
                return True
        return False

    def find_observe_affordance(self, attempts: int = 8) -> dict[str, object]:
        """Play until a ghost can be selected, then describe the Observe affordance.

        Returns ``{"found", "cost", "hint", "buttons"}``. Splits are preferred while
        looking, because a ghost has to exist before it can be observed.
        """
        result: dict[str, object] = {"found": False, "cost": "", "hint": "", "buttons": 0}
        for _ in range(attempts):
            if not self.wait_for_turn():
                break
            if self.select_uncertain_square():
                buttons = self.page.locator("#action-list .observe-action")
                if buttons.count() > 0:
                    result["found"] = True
                    result["buttons"] = buttons.count()
                    result["cost"] = buttons.nth(0).locator(".cost").inner_text().strip()
                    result["hint"] = self.page.inner_text("#action-hint")
                    return result
            before = self.page.evaluate("() => __qkState().ply")
            self.take_action(quantum_every=1)
            self.wait_for_ply_change(before)
        return result

    def observe_the_selected_piece(self) -> float:
        """Click the Observe button for the piece that is already selected.

        Returns the ply the client had when the click was sent.
        """
        before = float(self.page.evaluate("() => __qkState().ply"))
        self.page.locator("#action-list .observe-action").nth(0).click()
        return before

    def quit(self) -> None:
        if self.page.locator("#screen-game:not(.hidden)").count():
            self.page.click("#btn-quit")
            self.page.wait_for_selector("#screen-landing:not(.hidden)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Browser acceptance check (Phase 2).")
    parser.add_argument("--port", type=int, default=8765, help="Port for the test server.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window.")
    args = parser.parse_args(argv)

    base = f"http://127.0.0.1:{args.port}"
    log_path = REPO_ROOT / "results" / "browser_check.jsonl"
    # The server appends to this file, so without starting from empty a run's records mix
    # with every earlier run's and the log stops describing one acceptance run. This file
    # is this script's own output, which is why it is the script that clears it.
    log_path.unlink(missing_ok=True)
    checker = Checker()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIPPED: playwright is not installed (`pip install playwright`)")
        return 2

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=not args.headed)
            except Exception as exc:  # browser binary missing
                print(f"SKIPPED: could not launch Chromium ({exc})")
                return 2

            server = start_server(args.port, log_path)
            try:
                page = browser.new_page()
                client = Client(page, base)

                # -- check 1: a full Level-1 game vs the random agent -----------
                client.open(stage=1)
                client.to_stage_screen()
                client.choose_stage(1)
                client.pick_mode("ai-easy")
                outcome = client.play_to_result()
                checker.check(
                    outcome["reached_result"],
                    "Level-1 game vs random reaches the result screen "
                    f"({outcome['plies']} human moves, actions {outcome['kinds']})",
                )
                checker.check(outcome["plies"] > 0, "the game accepted at least one move")
                checker.check(
                    not client.console_errors,
                    "zero console errors during the game"
                    + (f" -- {client.console_errors[:3]}" if client.console_errors else ""),
                )
                client.quit()

                # -- check 3: an illegal move is shown and never applied --------
                client.open(stage=1)
                client.to_stage_screen()
                client.choose_stage(1)
                client.pick_mode("ai-easy")
                client.wait_for_turn()
                before = page.evaluate("() => __qkState()")
                empty = next(
                    (
                        index
                        for index, pair in enumerate(before["occupancy"])
                        if not pair[0] and not pair[1]
                    ),
                    None,
                )
                checker.check(empty is not None, "found an empty square to move from")
                if empty is not None:
                    size = int(round(len(before["occupancy"]) ** 0.5))
                    row, col = divmod(empty, size)
                    page.evaluate(
                        "(square) => __qkSend({type: 'Move', from: square, to: [0, 0]})",
                        [row, col],
                    )
                    page.wait_for_function(
                        "() => /illegal_move|not_your_turn/.test("
                        "document.querySelector('#game-status').textContent)",
                        timeout=10000,
                    )
                    after = page.evaluate("() => __qkState()")
                    checker.check(
                        after["ply"] == before["ply"]
                        and after["occupancy"] == before["occupancy"],
                        "rejected move left ply and board unchanged",
                    )
                    checker.check(
                        "illegal_move" in page.inner_text("#game-status")
                        or "not_your_turn" in page.inner_text("#game-status"),
                        "the refusal is shown in the UI",
                    )
                client.quit()

                # -- check 2: all five stages render and enforce their level ----
                for stage in range(5):
                    client.open(stage=stage)
                    client.to_stage_screen()
                    rules = client.rules_text()
                    unlock_note = client.choose_stage(stage)
                    note = page.inner_text("#mode-stage-note")
                    client.pick_mode("ai-easy")
                    info = page.evaluate("() => __qkState()")
                    cells = page.locator("#board .cell").count()
                    keyword = STAGE_KEYWORDS[stage]
                    checker.check(
                        info["stage"] == stage,
                        f"stage {stage}: engine level is {info['stage']}",
                    )
                    checker.check(
                        cells == 16,
                        f"stage {stage}: board renders 16 squares",
                    )
                    checker.check(
                        keyword in rules or keyword in note,
                        f"stage {stage}: rule text mentions '{keyword}'",
                    )
                    # The readout prints the level the *server* built, so it doubles as a
                    # check that the stage the browser asked for is the stage it got.
                    page.wait_for_function(
                        "() => /^LEVEL\\s/.test(__qkState().levelOutput || '')",
                        timeout=15000,
                    )
                    level_text = page.evaluate("() => __qkState().levelOutput")
                    checker.check(
                        f"LEVEL {stage}" in str(level_text),
                        f"stage {stage}: the level readout prints the server's level "
                        f"({level_text!r})",
                    )
                    checker.check(
                        str(level_text).startswith(
                            f"LEVEL {stage} / {len(STAGE_KEYWORDS) - 1}"
                        ),
                        f"stage {stage}: the readout states the level out of the total "
                        f"({level_text!r})",
                    )
                    if stage not in UNLOCK_NOTES:
                        checker.check(
                            unlock_note is None,
                            f"stage {stage}: no unlock note (it teaches nothing new of ours)",
                        )
                    else:
                        phrase = UNLOCK_NOTES[stage]
                        checker.check(
                            bool(unlock_note) and phrase in str(unlock_note),
                            f"stage {stage}: the unlock note credits the mechanic "
                            f"({unlock_note!r})",
                        )
                    client.quit()

                # -- check 4: the Observe affordance (addendum C) ---------------
                # Local mode on purpose: the Easy and Medium tiers run without the
                # voluntary-measurement flag at all (they are the strength ladder), so
                # the human's own Observe affordance lives in local, online and Hard.
                client.open(stage=2)
                client.to_stage_screen()
                client.choose_stage(2)
                client.pick_mode("local")
                affordance = client.find_observe_affordance()
                checker.check(
                    bool(affordance["found"]),
                    "stage 2: selecting an uncertain piece of your own offers Observe "
                    f"({affordance['buttons']} observe action(s))",
                )
                checker.check(
                    "costs your turn" in str(affordance["cost"]),
                    f"stage 2: the Observe button states the cost ({affordance['cost']!r})",
                )
                checker.check(
                    "costs your whole turn" in str(affordance["hint"]),
                    f"stage 2: the hint explains the cost too ({affordance['hint']!r})",
                )
                if affordance["found"]:
                    before = client.observe_the_selected_piece()
                    client.wait_for_ply_change(before)
                    checker.check(
                        "OBSERVE" in page.inner_text("#event-log"),
                        "stage 2: the observe move is applied by the server, not refused",
                    )
                    checker.check(
                        "cause: observe" in page.inner_text("#collapse-body"),
                        "stage 2: the observe opens the collapse reveal, as a measurement should",
                    )
                client.quit()

                # -- check 5: stage-4 coherence and the automatic expiry -------
                # Local mode on purpose: both seats are driven here, so no agent frame can
                # land between the moves and the expiry is observed on our own terms.
                client.open(stage=4)
                client.to_stage_screen()
                client.choose_stage(4)
                client.pick_mode("local")
                client.wait_for_turn()
                before = page.evaluate("() => __qkState().ply")
                client.take_action(quantum_every=1)  # a split, preferred above all
                client.wait_for_ply_change(before)
                counters = page.evaluate("() => __qkState().coherence") or {}
                checker.check(
                    bool(counters),
                    f"stage 4: a split piece carries a coherence counter ({counters})",
                )
                checker.check(
                    page.locator("#board .cell .coherence").count() > 0,
                    "stage 4: the counter is drawn on the board",
                )

                before = page.evaluate("() => __qkState().ply")
                client.take_action(quantum_every=0, quiet=True)
                client.wait_for_ply_change(before)
                ticked = page.evaluate("() => __qkState().coherence") or {}
                checker.check(
                    bool(ticked) and all(int(value) < 6 for value in ticked.values()),
                    f"stage 4: leaving the piece alone ticks the counter down ({ticked})",
                )

                expired = False
                for _ in range(24):
                    if "coherence expired" in page.inner_text("#event-log"):
                        expired = True
                        break
                    if not client.wait_for_turn():
                        break
                    # Keep one ghost alive (split only when there is none) and otherwise
                    # play quiet moves, so nobody can resolve it by capture either.
                    alive = page.evaluate("() => __qkState().coherence") or {}
                    before = page.evaluate("() => __qkState().ply")
                    client.take_action(quantum_every=0 if alive else 1, quiet=True)
                    client.wait_for_ply_change(before)
                checker.check(
                    expired,
                    "stage 4: a piece nobody measured collapsed on its own "
                    "(the client logged the expiry)",
                )
                checker.check(
                    "cause: decoherence" in page.inner_text("#collapse-body"),
                    "stage 4: the expiry opens the same collapse reveal as any measurement",
                )
                checker.check(
                    not (page.evaluate("() => __qkState().coherence") or {}),
                    "stage 4: the counter is gone once the piece is certain again",
                )
                client.quit()

                # -- check 6: the demo payloads load in the replay viewer ------
                # The demo is a deliverable, so it gets checked the way a person uses it:
                # open the static viewer, pick the file, load it, and count what appeared.
                replay = browser.new_page()
                replay.on(
                    "pageerror",
                    lambda exc: client.console_errors.append(f"replay pageerror: {exc}"),
                )
                demos = demo_payloads(REPO_ROOT / "results")
                for name in DEMO_NAMES:
                    if name not in demos:
                        checker.check(
                            False,
                            f"{name} missing -- run scripts/make_demo_seeds.py",
                        )
                        continue
                    expected_length = demos[name]
                    path = REPO_ROOT / "results" / name
                    replay.goto((REPO_ROOT / "viewer" / "index.html").as_uri())
                    replay.set_input_files("#file-input", str(path))
                    replay.click("#load-button")
                    replay.wait_for_selector("#board-section:not(.hidden)", timeout=20000)
                    cells = replay.locator("#board .cell").count()
                    frames = replay.locator("#timeline li").count()
                    checker.check(
                        cells == 16,
                        f"{name}: replay viewer renders a {cells}-square board",
                    )
                    checker.check(
                        frames == expected_length,
                        f"{name}: timeline shows all {expected_length} turns "
                        f"(got {frames})",
                    )
                    checker.check(
                        bool(replay.inner_text("#amplitude-note").strip()),
                        f"{name}: the viewer still states that amplitudes are not modelled",
                    )
                replay.close()

                checker.check(
                    not client.console_errors,
                    "zero console errors across all checks"
                    + (f" -- {client.console_errors[:3]}" if client.console_errors else ""),
                )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    server.kill()
    except Exception as exc:  # pragma: no cover - surface, do not hide
        print(f"ERROR: browser check aborted: {exc}")
        return 1

    return checker.summary()


if __name__ == "__main__":
    raise SystemExit(main())
