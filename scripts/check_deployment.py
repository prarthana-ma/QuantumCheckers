"""Current-client smoke check: WebSocket moves, reconnect and music.

Requires Playwright and Chromium (same optional setup as browser_check.py).
Usage: python scripts/check_deployment.py --site https://quriousminds.vercel.app
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="https://quriousminds.vercel.app")
    parser.add_argument("--api",
                        default="https://quriousminds-api-207368236521.asia-south1.run.app")
    parser.add_argument("--expected-engine", default="paper-quantum",
                        choices=("paper-quantum", "deterministic-toy"))
    args = parser.parse_args()
    with urllib.request.urlopen(f"{args.api}/api/health", timeout=30) as response:
        assert json.load(response)["status"] == "ok"
    print("PASS public backend health")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        frames: list[dict] = []
        socket_urls: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        def receive(payload):
            try:
                frames.append(json.loads(payload))
            except (ValueError, TypeError):
                pass
        def socket_open(socket):
            socket_urls.append(socket.url)
            socket.on("framereceived", receive)
        page.on("websocket", socket_open)
        # Observe the real HTMLAudioElement without changing playback behavior.
        page.add_init_script("""(() => {
          const NativeAudio = window.Audio;
          window.Audio = function(src) {
            const audio = new NativeAudio(src);
            window.__musicAudio = audio;
            return audio;
          };
          window.Audio.prototype = NativeAudio.prototype;
        })();""")
        page.goto(f"{args.site}/lobby/create", wait_until="networkidle")
        page.get_by_role("button", name="Create game", exact=True).click()
        page.wait_for_url("**/game/**")
        page.get_by_text("Live", exact=True).wait_for()
        initial = next(frame for frame in reversed(frames) if frame.get("type") == "StateUpdate")
        assert initial["legal"] and initial["board"]["engine"] == args.expected_engine
        assert socket_urls[-1].startswith(re.sub(r"^http", "ws", args.api))
        print(f"PASS create game and receive authoritative {args.expected_engine} state")

        action = initial["legal"][0]
        assert action["kind"] in ("move", "capture")
        def square_name(square):
            return f"{chr(97 + square[1])}{square[0] + 1}"
        for square in (action["origin"], action["target"]):
            page.get_by_role("button", name=re.compile(rf"^{square_name(square)},")).click()
        for _ in range(100):
            page.wait_for_timeout(100)
            if any(frame.get("type") == "StateUpdate" and frame.get("ply", 0) > initial["ply"] for frame in frames):
                break
        else:
            raise AssertionError("move did not produce an authoritative state update")
        print("PASS move applied through the deployed WebSocket")

        page.wait_for_function("window.__musicAudio && window.__musicAudio.readyState >= 2 && !window.__musicAudio.paused")
        page.get_by_role("button", name="Music on", exact=True).click()
        assert page.evaluate("window.__musicAudio.paused")
        assert page.evaluate("localStorage.getItem('qk.music.enabled')") == "0"
        page.get_by_role("button", name="Music off", exact=True).click()
        page.wait_for_function("!window.__musicAudio.paused")
        print("PASS actual soundtrack playback, mute, resume and stored preference")

        previous_ply = max(frame.get("ply", 0) for frame in frames)
        frames.clear()
        page.reload(wait_until="networkidle")
        page.get_by_text("Live", exact=True).wait_for()
        latest = next(frame for frame in reversed(frames) if frame.get("type") == "StateUpdate")
        assert latest["ply"] >= previous_ply
        assert latest["you"] == initial["you"]
        print("PASS reload reclaims seat and preserves game state")
        assert not errors, errors
        print("PASS no browser page errors")
        browser.close()


if __name__ == "__main__":
    main()
