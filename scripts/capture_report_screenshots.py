"""Capture reproducible screenshots for the report from the public QCheckers site.

Requires Playwright and Chromium. Usage:
    python scripts/capture_report_screenshots.py
    python scripts/capture_report_screenshots.py --site https://example.test
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "figures"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="https://quriousminds.vercel.app")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.goto(args.site, wait_until="networkidle")
        page.get_by_role("heading", name="QCheckers").wait_for()
        page.screenshot(path=OUTPUT / "qcheckers-home.png", full_page=True)

        page.goto(f"{args.site}/lobby/create?stage=1&mode=local", wait_until="networkidle")
        page.get_by_role("button", name=re.compile(r"^Stage 2 — Superposition")).click()
        page.get_by_role("button", name="Create game", exact=True).click()
        page.wait_for_url("**/game/**")
        page.get_by_text("Live", exact=True).wait_for()
        page.get_by_role("grid", name="Quantum checkers board").wait_for()
        page.get_by_role("button", name=re.compile(r"^c6,.*selectable")).click()
        page.get_by_role("button", name="Split", exact=True).click()
        page.get_by_role("button", name="Confirm split", exact=True).click()
        page.get_by_role("button", name=re.compile(r"^b5,.*50 percent")).wait_for()
        page.screenshot(path=OUTPUT / "qcheckers-game.png", full_page=True)
        browser.close()

    print(f"Saved QCheckers homepage and game screenshots in {OUTPUT}")


if __name__ == "__main__":
    main()
