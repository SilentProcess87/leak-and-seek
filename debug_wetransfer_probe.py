"""Probe WeTransfer's upload flow to figure out why DataTransfer injection
isn't working from the Chrome extension.

We do everything through Playwright (headed) so we can:
  - Inspect the real <input type="file"> structure
  - Try the same DataTransfer trick the extension uses, in the SAME JS context
  - See React's onChange behavior in DevTools console
  - Compare to Playwright's native set_input_files() which we know works
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


TEST_FILE = Path(__file__).parent / "_probe_test_file.txt"
if not TEST_FILE.exists():
    TEST_FILE.write_text("DLP probe test content — " + "x" * 200)


def dump(label: str, value):
    print(f"\n=== {label} ===")
    print(value)


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        # Capture browser console output
        page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[pageerror] {err}"))

        print("[probe] Navigating to wetransfer.com…")
        page.goto("https://wetransfer.com", wait_until="networkidle", timeout=45_000)

        # Dismiss cookie consent + terms gate
        for sel in ('button:has-text("I Accept")', 'button:has-text("I agree")'):
            try:
                if page.locator(sel).first.is_visible(timeout=3_000):
                    page.locator(sel).first.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass

        page.wait_for_timeout(1_500)

        # ── 1. Inspect file input structure ──────────────────────────
        info = page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
            return inputs.map(el => ({
                id: el.id,
                name: el.name,
                testid: el.getAttribute('data-testid'),
                accept: el.accept,
                multiple: el.multiple,
                visible: el.offsetParent !== null,
                display: getComputedStyle(el).display,
                outerHTML: el.outerHTML.slice(0, 300),
                parent: el.parentElement ? el.parentElement.outerHTML.slice(0, 300) : null,
            }));
        }""")
        dump("file inputs on page", info)

        # ── 2. Try the DataTransfer injection (mirrors the extension) ─
        result = page.evaluate("""() => {
            const fi = document.querySelector(
                'input[data-testid="file-input"], input[type="file"]'
            );
            if (!fi) return { ok: false, error: 'no file input' };

            const before = {
                hasFiles: !!fi.files,
                filesLen: fi.files ? fi.files.length : -1,
            };

            try {
                const blob = new Blob(['hello dlp from injection'], { type: 'text/plain' });
                const file = new File([blob], 'probe_inject.txt', { type: 'text/plain' });
                const dt = new DataTransfer();
                dt.items.add(file);
                fi.files = dt.files;
                fi.dispatchEvent(new Event('input', { bubbles: true }));
                fi.dispatchEvent(new Event('change', { bubbles: true }));
            } catch (e) {
                return { ok: false, error: String(e), before };
            }

            return {
                ok: true,
                before,
                after: {
                    hasFiles: !!fi.files,
                    filesLen: fi.files ? fi.files.length : -1,
                    fileName: fi.files && fi.files[0] ? fi.files[0].name : null,
                },
            };
        }""")
        dump("DataTransfer injection result", result)

        # ── 3. Wait for React to react, then inspect the page ─────────
        page.wait_for_timeout(3_000)
        post_inject = page.evaluate("""() => {
            const findText = (re) => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                const matches = [];
                let n;
                while ((n = walker.nextNode())) {
                    if (re.test(n.textContent)) matches.push(n.textContent.trim().slice(0, 120));
                }
                return matches.slice(0, 10);
            };
            return {
                fileNameTexts: findText(/probe_inject/),
                addFilesVisible: !!document.querySelector('button[data-testid="upload-file-button"]'),
                anyFileBadge: Array.from(document.querySelectorAll('[data-testid]'))
                    .map(el => el.getAttribute('data-testid'))
                    .filter(t => t && /file|upload|item/i.test(t))
                    .slice(0, 20),
            };
        }""")
        dump("post-injection DOM signals", post_inject)

        page.screenshot(path="probe_after_dt_injection.png")
        print("\n[probe] Screenshot saved -> probe_after_dt_injection.png")

        # ── 4. Now try Playwright's set_input_files for comparison ────
        print("\n[probe] Reloading page to test Playwright's set_input_files…")
        page.goto("https://wetransfer.com", wait_until="networkidle", timeout=45_000)
        for sel in ('button:has-text("I Accept")', 'button:has-text("I agree")'):
            try:
                if page.locator(sel).first.is_visible(timeout=3_000):
                    page.locator(sel).first.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass
        page.wait_for_timeout(1_500)

        fi_locator = page.locator('input[data-testid="file-input"], input[type="file"]').first
        fi_locator.set_input_files(str(TEST_FILE))
        page.wait_for_timeout(3_000)

        playwright_result = page.evaluate("""() => {
            const findText = (re) => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                const matches = [];
                let n;
                while ((n = walker.nextNode())) {
                    if (re.test(n.textContent)) matches.push(n.textContent.trim().slice(0, 120));
                }
                return matches.slice(0, 10);
            };
            return {
                probeTextSeen: findText(/_probe_test_file/),
                fileSizeBadgeSeen: findText(/(B|KB|MB)$/i).slice(0, 5),
            };
        }""")
        dump("after Playwright set_input_files", playwright_result)
        page.screenshot(path="probe_after_playwright_setinput.png")

        print("\n[probe] Done. Browser will close in 5s — inspect manually if needed.")
        page.wait_for_timeout(5_000)
        ctx.close()
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[probe] FAILED: {exc}", file=sys.stderr)
        raise
