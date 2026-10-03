"""Optional real-browser smoke check against a running local Streamlit instance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from playwright.sync_api import expect, sync_playwright


def settle(page) -> None:
    expect(page.get_by_role("button", name="Stop", exact=True)).not_to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Export effects CSV")).to_be_visible()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path, default=Path(".cache/dashboard-qa"))
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if parts.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("This smoke script only targets the local dashboard")
    url = args.url
    if args.run_id:
        url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode({"run": args.run_id}),
                parts.fragment,
            )
        )
    args.output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(args.browser) if args.browser else None,
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1365, "height": 950}, reduced_motion="reduce")
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        expect(page.get_by_role("tab", name="Price scenarios")).to_be_visible(timeout=30000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        page.get_by_role("tab", name="Method checks").click()
        expect(page.get_by_text("Recovering known effects", exact=True)).to_be_visible()
        expect(page.get_by_role("img").first).to_be_visible(timeout=15000)
        settle(page)
        page.screenshot(path=str(args.output / "method-desktop.png"), full_page=True)
        checks.append("Method tab rendered")
        page.get_by_role("tab", name="Price scenarios").click()
        expect(page.get_by_text("Expected bookings", exact=True)).to_be_visible(timeout=30000)
        settle(page)
        page.screenshot(path=str(args.output / "scenario-desktop.png"), full_page=True)
        checks.append("Supported scenario rendered")
        page.get_by_text("Inspect unsupported price", exact=True).click()
        expect(page.get_by_role("checkbox", name="Inspect unsupported price")).to_be_checked()
        expect(
            page.get_by_text("Price is outside the designed multiplier range 0.90–1.10", exact=True)
        ).to_be_visible(timeout=15000)
        expect(page.get_by_text("Expected bookings", exact=True)).to_have_count(0)
        page.get_by_text("Inspect unsupported price", exact=True).click()
        expect(page.get_by_text("Expected bookings", exact=True)).to_be_visible(timeout=15000)
        settle(page)
        checks.append("Unsupported price withheld and recovered")
        for width in (320, 375, 414, 768):
            page.set_viewport_size({"width": width, "height": 960})
            expect(page.get_by_role("tab", name="Price scenarios")).to_be_visible()
            dimensions = page.evaluate("""() => ({
                viewport: window.innerWidth,
                root: document.documentElement.scrollWidth,
                body: document.body.scrollWidth
            })""")
            if max(dimensions["root"], dimensions["body"]) > width:
                raise AssertionError(f"Horizontal overflow at {width}: {dimensions}")
            page.screenshot(path=str(args.output / f"scenario-{width}.png"), full_page=True)
            page.get_by_role("button", name="Export scenario JSON").scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / f"scenario-{width}-results.png"), full_page=True)
            page.get_by_role(
                "heading", name="GSM Causal Marketplace", exact=True
            ).scroll_into_view_if_needed()
            checks.append(f"No page overflow at {width}px")
        page.set_viewport_size({"width": 1365, "height": 950})
        page.get_by_role("tab", name="Operations").click()
        expect(page.get_by_text("Completed trips", exact=True).first).to_be_visible()
        settle(page)
        page.screenshot(path=str(args.output / "operations-desktop.png"), full_page=True)
        checks.append("Operations tab rendered")
        expect(page.get_by_test_id("stException")).to_have_count(0)
        browser.close()
    if errors:
        raise AssertionError(f"Browser page errors: {errors}")
    report = {"url": url, "checks": checks, "page_errors": errors}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
