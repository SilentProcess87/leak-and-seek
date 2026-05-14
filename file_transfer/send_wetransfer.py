"""
WeTransfer file sender — standalone Playwright script.

Recorded steps (via browser MCP against live wetransfer.com):
  1. Navigate to wetransfer.com, wait for full load
  2. Cookie consent → click "I Accept"
  3. Terms gate     → click "I agree"
  4. Upload file via hidden <input type="file">
  5. Fill "Email to" (recipient) + press Enter to confirm chip
  6. Fill "Your email" (sender)
  7. Optionally fill "Title" and "Message"
  8. Click "Transfer"
  9. Handle email-verification overlay → manual code entry
 10. Wait for success confirmation

Usage:
    python send_wetransfer.py                          # uses defaults below
    python send_wetransfer.py --file path/to/file.zip  # send a specific file
"""

import argparse
import os
import random
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── defaults (edit these or pass via CLI / env vars) ─────────────────
# Relative to this script’s parent (file_transfer/)
TEST_FILES_DIR = Path(__file__).parent.parent / "detectors_profile_test_files"
DEFAULT_FILE = ""  # resolved at runtime from TEST_FILES_DIR
RECIPIENT_EMAIL = "monitor@mailslurp.biz"
SENDER_EMAIL = "monitor@mailslurp.biz"
MESSAGE = "Automated file transfer test"
MAILSLURP_API_KEY = os.getenv("MAILSLURP_API_KEY", "")


def click_if_visible(page, selector, timeout=4_000, label=""):
    """Click the first matching element if it's visible."""
    try:
        loc = page.locator(selector).first
        if loc.is_visible(timeout=timeout):
            print(f"  ✓ [{label}] Clicked: {selector}")
            loc.click()
            page.wait_for_timeout(800)
            return True
    except (PwTimeout, Exception):
        pass
    print(f"  – [{label}] Not found: {selector}")
    return False


def send(file_path: str):
    fp = Path(file_path)
    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("Hello WeTransfer!", encoding="utf-8")
        print(f"Created test file: {fp}")

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

        # ── Step 1: Navigate ──────────────────────────────────────
        print("[1/9] Navigating to wetransfer.com …")
        page.goto("https://wetransfer.com", wait_until="networkidle", timeout=45_000)
        page.wait_for_timeout(2_000)

        # ── Step 2: Cookie consent → "I Accept" ──────────────────
        print("[2/9] Cookie consent …")
        click_if_visible(page, 'button:has-text("I Accept")', timeout=6_000, label="cookie")

        # ── Step 3: Terms gate → "I agree" ────────────────────────
        print("[3/9] Terms gate …")
        click_if_visible(page, 'button:has-text("I agree")', timeout=6_000, label="terms")
        page.wait_for_timeout(1_500)

        # ── Step 4: Upload file ───────────────────────────────────
        print(f"[4/9] Uploading {fp.name} …")
        file_input = page.locator('input[data-testid="file-input"], input[type="file"]')
        if file_input.count() == 0:
            raise RuntimeError("No file input found on page")
        file_input.first.set_input_files(str(fp.resolve()))
        page.wait_for_timeout(3_000)

        # Confirm file appeared in the UI
        if page.locator(f'text="{fp.name}"').count() > 0:
            print(f"  ✓ File '{fp.name}' attached")
        else:
            print("  ⚠ File may not have attached — continuing anyway")

        # ── Step 5: Fill "Email to" (recipient) ───────────────────
        #   Actual element: <input name="autosuggest" id="autosuggest">
        print(f"[5/9] Filling recipient: {RECIPIENT_EMAIL} …")
        recipient = page.locator('input#autosuggest, input[name="autosuggest"]').first
        recipient.click()
        recipient.fill(RECIPIENT_EMAIL)
        page.keyboard.press("Enter")      # confirm the email chip
        page.wait_for_timeout(500)
        print(f"  ✓ Recipient set")

        # ── Step 6: Fill "Your email" (sender) ────────────────────
        #   Actual element: <input name="email" id="email" type="email">
        print(f"[6/9] Filling sender: {SENDER_EMAIL} …")
        sender = page.locator('input#email, input[name="email"][type="email"]').first
        sender.click()
        sender.fill(SENDER_EMAIL)
        page.wait_for_timeout(500)
        print(f"  ✓ Sender set")

        # ── Step 7: Fill optional Message ─────────────────────────
        #   Actual element: <textarea name="message" id="message">
        print("[7/9] Filling message …")
        try:
            msg = page.locator('textarea#message, textarea[name="message"]').first
            if msg.is_visible(timeout=2_000):
                msg.fill(MESSAGE)
                print(f"  ✓ Message set")
        except PwTimeout:
            pass

        # ── Step 8: Click "Transfer" ──────────────────────────────
        #   Actual element: <button data-testid="uploaderForm-transfer-button">
        print("[8/9] Clicking Transfer …")
        transfer_btn = page.locator(
            'button[data-testid="uploaderForm-transfer-button"], '
            'button:has-text("Transfer"), '
            'button:has-text("Get a link")'
        ).first
        transfer_btn.click()
        page.wait_for_timeout(4_000)

        # ── Step 9: Handle email verification ─────────────────────
        #   Actual element: <input name="verification-code" placeholder="Enter verification code">
        verify_input = page.locator(
            'input[name="verification-code"], '
            'input[placeholder*="verification"], '
            'input[placeholder*="code"]'
        )
        if verify_input.count() > 0 and verify_input.first.is_visible(timeout=5_000):
            print("[9/9] Email verification required!")
            print(f"      WeTransfer sent a code to: {SENDER_EMAIL}")

            code = fetch_verification_code(SENDER_EMAIL)
            if code:
                print(f"      ✓ Got verification code: {code}")
                verify_input.first.click()
                verify_input.first.fill(code)
                page.wait_for_timeout(500)

                # Click "Verify and Send" — wait for button to become enabled
                page.wait_for_timeout(1_000)
                verify_btn = page.locator(
                    'button:has-text("Verify and Send"), '
                    'button:has-text("Verify")'  
                ).first
                try:
                    verify_btn.wait_for(state="visible", timeout=5_000)
                    # Button may be disabled briefly; click when enabled
                    page.wait_for_timeout(1_000)
                    verify_btn.click(force=True)
                    print("      ✓ Clicked 'Verify and Send'")
                    page.wait_for_timeout(8_000)
                except PwTimeout:
                    print("      ⚠ Verify button not found, trying keyboard submit")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(8_000)
            else:
                print("      ⚠ Could not auto-fetch code.")
                print("        Enter the code manually in the browser, then press Enter.")
                input("  ➜ Press Enter after you've verified … ")
        else:
            print("[9/9] No verification prompt — transfer is processing …")

        # ── Wait for completion ───────────────────────────────────
        print("\n⏳ Waiting for transfer to complete …")
        _wait_for_done(page)
        print(f"\n✅ File '{fp.name}' sent to {RECIPIENT_EMAIL} via WeTransfer!")

        print("\nPress Enter to close the browser …")
        input()
        context.close()
        browser.close()


def fetch_verification_code(email: str, timeout_ms: int = 60_000) -> str | None:
    """Fetch the WeTransfer verification code from MailSlurp."""
    if not MAILSLURP_API_KEY:
        print("      [mailslurp] No MAILSLURP_API_KEY set — cannot auto-fetch code")
        return None

    headers = {"x-api-key": MAILSLURP_API_KEY}
    base = "https://api.mailslurp.com"

    try:
        # 1. Find the inbox for this email address
        print(f"      [mailslurp] Looking up inbox for {email} …")
        inbox_id = None

        # Method A: lookup by email address
        try:
            resp = requests.get(
                f"{base}/inboxes/byEmailAddress",
                params={"emailAddress": email},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # Response format: {"inboxId": "...", "exists": true}
            inbox_id = data.get("inboxId") or data.get("id")
        except Exception:
            pass

        # Method B: fallback — list all inboxes and match by email
        if not inbox_id:
            resp = requests.get(
                f"{base}/inboxes",
                params={"size": 100},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            inbox_list = data.get("content", data) if isinstance(data, dict) else data
            for inbox in inbox_list:
                if inbox.get("emailAddress", "").lower() == email.lower():
                    inbox_id = inbox["id"]
                    break

        if not inbox_id:
            print(f"      [mailslurp] No inbox found for {email}")
            return None

        print(f"      [mailslurp] Inbox found: {inbox_id[:12]}…")

        # 2. Wait for the latest unread email (WeTransfer verification)
        print(f"      [mailslurp] Waiting for verification email (up to {timeout_ms//1000}s) …")
        resp = requests.get(
            f"{base}/waitForLatestEmail",
            params={
                "inboxId": inbox_id,
                "timeout": timeout_ms,
                "unreadOnly": "true",
            },
            headers=headers,
            timeout=timeout_ms // 1000 + 10,
        )
        resp.raise_for_status()
        email_data = resp.json()

        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        print(f"      [mailslurp] Email received — subject: {subject!r}")

        # 3. Extract the verification code (alphanumeric, e.g. "DZEU7D")
        #    WeTransfer subject format: "Your code is: DZEU7D"
        #    IMPORTANT: search subject FIRST (clean text), body is messy HTML

        # Subject line (most reliable)
        match = re.search(r'(?:code\s+is:?\s*)([A-Z0-9]{5,8})', subject)
        if match:
            return match.group(1)

        # Body: look for "code is: XXXXX" pattern (uppercase only)
        match = re.search(r'(?:code\s+is:?\s*)([A-Z0-9]{5,8})', body)
        if match:
            return match.group(1)

        # Fallback: any standalone 5-6 char uppercase+digit block
        match = re.search(r'\b([A-Z0-9]{5,6})\b', subject)
        if match:
            return match.group(1)
        match = re.search(r'\b([A-Z0-9]{5,6})\b', body)
        if match:
            return match.group(1)

        print("      [mailslurp] Could not extract code from email body")
        return None

    except Exception as exc:
        print(f"      [mailslurp] Error: {exc}")
        return None


def _wait_for_done(page, timeout_sec=180):
    """Poll until WeTransfer confirms the transfer."""
    deadline = time.time() + timeout_sec
    success_texts = [
        "Transfer complete",
        "Sent!",
        "Your transfer is on its way",
        "We sent your transfer",
        "link is ready",
        "We're on it",
    ]
    while time.time() < deadline:
        for txt in success_texts:
            if page.locator(f'text="{txt}"').count() > 0:
                page.wait_for_timeout(2_000)
                return
        # Check progress bar
        try:
            prog = page.locator('[role="progressbar"]')
            if prog.count() > 0:
                val = prog.first.get_attribute("aria-valuenow")
                if val and float(val) >= 100:
                    page.wait_for_timeout(2_000)
                    return
        except Exception:
            pass
        page.wait_for_timeout(2_000)
    raise RuntimeError("Transfer did not complete within timeout")


def pick_random_file() -> str:
    """Pick a random non-hidden file from the test files directory."""
    files = [
        f for f in TEST_FILES_DIR.rglob("*")
        if f.is_file() and not f.name.startswith(".")
    ]
    if not files:
        raise RuntimeError(f"No files found in {TEST_FILES_DIR}")
    chosen = random.choice(files)
    print(f"Randomly selected: {chosen.relative_to(TEST_FILES_DIR.parent)}")
    return str(chosen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a file via WeTransfer")
    parser.add_argument("--file", default=None, help="File to send (default: random from test files)")
    args = parser.parse_args()
    file_to_send = args.file or pick_random_file()
    send(file_to_send)
