"""Debug script: navigate to WeTransfer and dump the page structure.

Run from the file_transfer/ directory:
    python debug_wetransfer.py

This opens a visible browser, navigates to wetransfer.com, and saves:
  - wetransfer_debug/01_loaded.png       (screenshot after page load)
  - wetransfer_debug/01_loaded.html      (full page HTML)
  - wetransfer_debug/02_after_consent.png (after clicking consent buttons)
  - wetransfer_debug/02_after_consent.html

Inspect the screenshots and HTML to identify the correct selectors.
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

DEBUG_DIR = Path("wetransfer_debug")
DEBUG_DIR.mkdir(exist_ok=True)

CONSENT_SELECTORS = [
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("Allow all")',
    'button:has-text("Allow")',
    'button:has-text("I Agree")',
    'button:has-text("OK")',
    'button[id*="accept"]',
    'button[class*="accept"]',
    '[data-testid="cookie-accept"]',
    '#onetrust-accept-btn-handler',
]

GATE_SELECTORS = [
    "button:has-text('I agree')",
    "button:has-text('I just want to send files')",
    "a:has-text('I just want to send files')",
    "button:has-text('Continue with free')",
    "button:has-text('Get started')",
    "button:has-text('No thanks')",
    "button:has-text('Skip')",
    "[data-testid='decline-signup']",
    "[data-testid='free-wall-decline']",
]


def save_snapshot(page, name: str):
    page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    html = page.content()
    (DEBUG_DIR / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"  Saved {name}.png + {name}.html")


def click_first_visible(page, selectors, label, timeout=3000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
                text = loc.inner_text()
                print(f"  [{label}] Clicked: {sel!r}  (text={text!r})")
                loc.click()
                page.wait_for_timeout(800)
                return True
        except (PwTimeout, Exception):
            continue
    print(f"  [{label}] No matching button found.")
    return False


def dump_inputs(page):
    """Print all visible input/textarea/button elements."""
    print("\n  === Visible interactive elements ===")
    for tag in ["input", "textarea", "button", "a"]:
        elements = page.locator(tag)
        count = elements.count()
        for i in range(count):
            el = elements.nth(i)
            try:
                if not el.is_visible(timeout=500):
                    continue
                attrs = {}
                for attr in ["type", "name", "placeholder", "aria-label", "data-testid", "class", "id"]:
                    val = el.get_attribute(attr)
                    if val:
                        attrs[attr] = val
                text = el.inner_text()[:60] if tag in ("button", "a") else ""
                print(f"    <{tag}> text={text!r}  attrs={attrs}")
            except Exception:
                continue
    print("  === End ===\n")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("[1/4] Navigating to wetransfer.com …")
        page.goto("https://wetransfer.com", wait_until="networkidle", timeout=45_000)
        page.wait_for_timeout(3_000)
        save_snapshot(page, "01_loaded")
        dump_inputs(page)

        print("[2/4] Dismissing consent overlays …")
        click_first_visible(page, CONSENT_SELECTORS, "consent")
        page.wait_for_timeout(1_500)
        save_snapshot(page, "02_after_consent")
        dump_inputs(page)

        print("[3/4] Trying to get past paywall/gate …")
        click_first_visible(page, GATE_SELECTORS, "gate", timeout=5000)
        page.wait_for_timeout(2_000)
        save_snapshot(page, "03_past_gate")
        dump_inputs(page)

        print("[4/4] Checking for file input …")
        file_input = page.locator('input[type="file"]')
        count = file_input.count()
        print(f"  Found {count} file input(s)")
        if count > 0:
            for i in range(count):
                attrs = {}
                for attr in ["name", "accept", "multiple", "class", "id"]:
                    val = file_input.nth(i).get_attribute(attr)
                    if val:
                        attrs[attr] = val
                print(f"    file input #{i}: {attrs}")

        save_snapshot(page, "04_final")

        print("\n✅ Done! Check the wetransfer_debug/ folder.")
        print("   Press Enter to close the browser …")
        input()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
