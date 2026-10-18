"""Browser acceptance check for the current Next.js client and paper engine.

Start the API on port 8000 and the client on port 3000, then run::

    python scripts/check_current_client.py

Override either origin with ``--site`` or ``--api``. Requires Playwright and
Chromium. The check creates local games through the UI, reads authoritative
state/legal actions from the REST API, and never sends a move to an enabled
hardware sampler.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import Page, sync_playwright


def request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def wait_for_state(api: str, game_id: str, predicate, *, timeout_s: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = request_json(f"{api}/api/game/{game_id}")
        if predicate(last):
            return last
        time.sleep(0.1)
    raise AssertionError(f"game {game_id} did not reach the expected state; last state: {last}")


def square_name(square: list[int] | tuple[int, int]) -> str:
    row, col = square
    return f"{chr(97 + col)}{row + 1}"


def cell(page: Page, square: list[int] | tuple[int, int]):
    return page.get_by_role("button", name=re.compile(rf"^{re.escape(square_name(square))},"))


def assert_standard_paper_state(state: dict[str, Any], level: int) -> None:
    board = state["board"]
    assert board["level"] == level, (board["level"], level)
    assert board["board_size"] == 8, board["board_size"]
    assert board["engine"] == "paper-quantum", board["engine"]
    assert board["paper_rules"] is True
    assert len(state["legal"]) > 0


def assert_same_rect(before: dict[str, float], after: dict[str, float], label: str) -> None:
    assert before is not None and after is not None, f"board grid missing {label}"
    for dimension in ("width", "height"):
        assert abs(before[dimension] - after[dimension]) <= 1.0, (
            f"board {dimension} changed on selection ({label}): "
            f"{before[dimension]:.2f}px -> {after[dimension]:.2f}px"
        )


def create_local_game(page: Page, site: str, level: int) -> str:
    page.goto(f"{site}/lobby/create?stage={level}&mode=local", wait_until="networkidle")
    page.get_by_role("button", name="Create game", exact=True).click()
    page.wait_for_url(re.compile(r"/game/[^/?]+$"))
    page.get_by_role("grid", name="Quantum checkers board, 8 by 8").wait_for()
    match = re.search(r"/game/([^/?]+)$", page.url)
    assert match, f"unexpected game URL: {page.url}"
    return match.group(1)


def select_ui_move(page: Page, action: dict[str, Any]) -> None:
    assert action["kind"] in ("move", "capture"), action
    cell(page, action["origin"]).click()
    cell(page, action["target"]).click()


def split_c6(page: Page, api: str, game_id: str) -> dict[str, Any]:
    state = request_json(f"{api}/api/game/{game_id}")
    assert any(
        action["kind"] == "spread" and action["origin"] == [5, 2]
        for action in state["legal"]
    ), "server does not offer a Level 1/4 split from c6"

    grid = page.get_by_role("grid", name="Quantum checkers board, 8 by 8")
    before = grid.bounding_box()
    cell(page, (5, 2)).click()
    after_piece_select = grid.bounding_box()
    assert_same_rect(before, after_piece_select, f"selecting c6 in game {game_id}")
    page.get_by_role("button", name="Split", exact=True).click()
    after_mode_select = grid.bounding_box()
    assert_same_rect(before, after_mode_select, f"selecting Split in game {game_id}")
    page.get_by_role("button", name="Confirm split", exact=True).click()

    state = wait_for_state(
        api, game_id,
        lambda current: current["ply"] > 0 and any(
            piece["piece_id"] == "P0-1" and len(piece["sites"]) == 2
            for piece in current["board"]["pieces"]
        ),
    )
    piece = next(piece for piece in state["board"]["pieces"] if piece["piece_id"] == "P0-1")
    probabilities = sorted(chance for _, chance in piece["sites"])
    assert len(probabilities) == 2 and all(math.isclose(p, 0.5, abs_tol=1e-9) for p in probabilities), probabilities
    expected_labels = [square_name(square) for square, _ in piece["sites"]]
    page.wait_for_function(
        "labels => labels.every(label => Array.from(document.querySelectorAll('[data-square]'))"
        ".some(button => button.dataset.square === label && button.getAttribute('aria-label').includes('50 percent'))) ",
        arg=expected_labels,
    )
    for square, chance in piece["sites"]:
        assert "50 percent" in cell(page, square).get_attribute("aria-label"), (square, chance)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="http://localhost:3000")
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    site = args.site.rstrip("/")
    api = args.api.rstrip("/")

    health = request_json(f"{api}/api/health")
    assert health.get("status") == "ok", health
    print("PASS backend health")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.add_init_script(
            "localStorage.setItem('qk.progress.unlock.2', '1');"
            "localStorage.setItem('qk.progress.unlock.4', '1');"
        )

        try:
            for level in range(5):
                game_id = create_local_game(page, site, level)
                state = request_json(f"{api}/api/game/{game_id}")
                assert_standard_paper_state(state, level)
                assert state["mode"] == "local", state.get("mode")
                print(f"PASS Level {level}: UI created local standard 8x8 paper game ({game_id})")

                if level == 0:
                    # Exercise a server-advertised ordinary move through the visible board.
                    move = next(action for action in state["legal"] if action["kind"] == "move")
                    select_ui_move(page, move)
                    after = wait_for_state(api, game_id, lambda current: current["ply"] > state["ply"])
                    assert after["last_action"]["kind"] == "move", after.get("last_action")
                    assert after["last_action"]["origin"] == move["origin"]
                    assert after["last_action"]["target"] == move["target"]
                    print("PASS server-legal ordinary move applied through UI")

                elif level == 1:
                    # Split c6 using the explicit Split and Confirm controls.
                    split_state = split_c6(page, api, game_id)
                    assert split_state["last_action"]["kind"] == "spread"
                    print("PASS Level 1 c6 split renders two 50% branches")

                elif level == 4:
                    # Leave the piece split, make a REST-legal opponent move via UI,
                    # then observe one branch. Refuse to measure if hardware is on.
                    state = split_c6(page, api, game_id)
                    assert state["quantum"]["enabled"] is False, (
                        "hardware sampler is enabled; refusing to submit Level 4 Observe"
                    )
                    # Keep the opponent out of both branches' jump lanes. An arbitrary
                    # legal reply may create a mandatory capture, which correctly removes
                    # Observe from the legal list and would test the wrong path.
                    safe_lanes = {(3, 0), (3, 6)}
                    opponent_move = next(
                        action for action in state["legal"]
                        if action["kind"] == "move"
                        and tuple(action["target"]) in safe_lanes
                    )
                    select_ui_move(page, opponent_move)
                    state = wait_for_state(
                        api, game_id,
                        lambda current: current["ply"] > 1 and current["turn"] == 0,
                    )
                    assert any(action["kind"] == "observe" for action in state["legal"]), (
                        "chosen opponent move did not leave a legal Observe action"
                    )
                    assert state["quantum"]["enabled"] is False, (
                        "hardware sampler became enabled; refusing to submit Level 4 Observe"
                    )
                    piece = next(piece for piece in state["board"]["pieces"] if piece["piece_id"] == "P0-1")
                    branch = piece["sites"][0][0]
                    grid = page.get_by_role("grid", name="Quantum checkers board, 8 by 8")
                    page.wait_for_function(
                        "square => { const button = document.querySelector(`[data-square=\"${square}\"]`); "
                        "return !!button && button.getAttribute('aria-label').includes('50 percent'); }",
                        arg=square_name(branch),
                    )
                    before = grid.bounding_box()
                    cell(page, branch).click()
                    after = grid.bounding_box()
                    assert_same_rect(before, after, "selecting a Level 4 split branch for Observe")
                    page.get_by_role("button", name="Observe", exact=True).click()
                    page.get_by_role("button", name="Measure piece", exact=True).click()

                    measured = wait_for_state(
                        api, game_id,
                        lambda current: current["ply"] > state["ply"]
                        and current.get("last_event") is not None
                        and current["last_event"].get("cause") == "observe",
                    )
                    measured_piece = next(
                        piece for piece in measured["board"]["pieces"]
                        if piece["piece_id"] == "P0-1"
                    )
                    assert len(measured_piece["sites"]) == 1, measured_piece["sites"]
                    assert math.isclose(measured_piece["sites"][0][1], 1.0, abs_tol=1e-9), measured_piece["sites"]
                    assert any(math.isclose(measured["last_event"]["probability"], p, abs_tol=1e-9)
                               for p in (0.5, 1.0)), measured["last_event"]
                    print("PASS Level 4 REST-legal opponent move, branch Observe and measurement")

            assert not page_errors, page_errors
            print("PASS no browser pageerrors")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
