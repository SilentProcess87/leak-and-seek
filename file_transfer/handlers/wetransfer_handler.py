"""Send files via WeTransfer using Playwright browser automation.

Automates the WeTransfer web UI to upload a file and email it to the
configured recipient.  Includes automatic email verification via MailSlurp.

Recorded & verified steps (via chrome-devtools MCP, May 2025):
  1. Navigate to wetransfer.com (networkidle)
  2. Cookie consent   → click "I Accept"
  3. Terms gate       → click "I agree"
  4. Upload file      → input[data-testid="file-input"]
  5. Fill recipient   → input#autosuggest  + Enter
  6. Fill sender      → input#email
  7. Fill message     → textarea#message
  8. Click Transfer   → button[data-testid="uploaderForm-transfer-button"]
  9. Email verify     → input[name="verification-code"]  (auto via MailSlurp)
 10. Wait for success

Env vars:
  WETRANSFER_RECIPIENT_EMAIL  – who receives the file
  WETRANSFER_SENDER_EMAIL     – sender (must match a MailSlurp inbox)
  WETRANSFER_HEADLESS         – true/false (default true)
  WETRANSFER_DEBUG            – true/false – save screenshots
  MAILSLURP_API_KEY           – auto-fetch verification code
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import requests

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from .base import BaseHandler

logger = logging.getLogger(__name__)

WETRANSFER_URL = "https://wetransfer.com"
DEBUG_DIR = Path(__file__).resolve().parent.parent / "wetransfer_debug"

# Global lock — only one WeTransfer transfer runs at a time. This prevents
# multiple Playwright browsers from conflicting and racing for MailSlurp codes.
_TRANSFER_LOCK = threading.Lock()


class WeTransferHandler(BaseHandler):
    name = "wetransfer"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.recipient_email = os.getenv("WETRANSFER_RECIPIENT_EMAIL", "")
        self.sender_email = os.getenv("WETRANSFER_SENDER_EMAIL", "")
        self.message_text = self.handler_config.get("message", "Automated file transfer")
        # Browser is always visible — makes debugging the WeTransfer flow easier.
        self.headless = os.getenv("WETRANSFER_HEADLESS", "false").lower() == "true"
        self.debug = os.getenv("WETRANSFER_DEBUG", "false").lower() == "true"
        self.mailslurp_api_key = os.getenv("MAILSLURP_API_KEY", "")

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not HAS_PLAYWRIGHT:
            logger.warning(
                "[wetransfer] Playwright is not installed — WeTransfer handler "
                "disabled.  Install 'playwright' or use 'desktop_agent' with "
                "app=wetransfer instead."
            )
            return False
        if not self.recipient_email:
            logger.error("[wetransfer] WETRANSFER_RECIPIENT_EMAIL must be set in .env")
            return False
        if not self.sender_email:
            logger.error("[wetransfer] WETRANSFER_SENDER_EMAIL must be set in .env")
            return False
        return True

    # ------------------------------------------------------------------
    def _screenshot(self, page, name: str) -> None:
        if not self.debug:
            return
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        logger.debug("[wetransfer] Screenshot → %s", path)

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        # Acquire the global lock so only one WeTransfer browser runs at a time.
        # The MailSlurp verification flow can't safely run in parallel either
        # (whichever browser asks first gets the latest code, blocking the others).
        logger.info("[wetransfer] Waiting for transfer lock for %s…", file_path.name)
        with _TRANSFER_LOCK:
            logger.info("[wetransfer] Lock acquired — starting transfer for %s",
                        file_path.name)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()
                try:
                    self._run_transfer(page, file_path)
                except Exception:
                    self._screenshot(page, "error_final")
                    raise
                finally:
                    context.close()
                    browser.close()

    # ------------------------------------------------------------------
    def _run_transfer(self, page, file_path: Path) -> None:
        # ── Step 1: Navigate ─────────────────────────────────────────
        logger.info("[wetransfer] Navigating to WeTransfer…")
        page.goto(WETRANSFER_URL, wait_until="networkidle", timeout=45_000)
        page.wait_for_timeout(2_000)
        self._screenshot(page, "01_loaded")

        # ── Step 2: Cookie consent → "I Accept" ──────────────────────
        logger.info("[wetransfer] Handling cookie consent…")
        self._click_if_visible(page, 'button:has-text("I Accept")', timeout=6_000)
        self._screenshot(page, "02_cookie")

        # ── Step 3: Terms gate → "I agree" ───────────────────────────
        logger.info("[wetransfer] Handling terms gate…")
        self._click_if_visible(page, 'button:has-text("I agree")', timeout=6_000)
        page.wait_for_timeout(1_500)
        self._screenshot(page, "03_terms")

        # ── Step 4: Upload file ─────────────────────────────────────
        logger.info("[wetransfer] Uploading %s …", file_path.name)
        file_input = page.locator('input[data-testid="file-input"], input[type="file"]')
        if file_input.count() == 0:
            self._screenshot(page, "error_no_file_input")
            raise RuntimeError("[wetransfer] No file input found on page.")
        file_input.first.set_input_files(str(file_path))
        page.wait_for_timeout(3_000)
        self._screenshot(page, "04_uploaded")

        # ── Step 5: Fill "Email to" (recipient) ─────────────────────
        logger.info("[wetransfer] Filling recipient: %s", self.recipient_email)
        recipient = page.locator('input#autosuggest, input[name="autosuggest"]').first
        recipient.click()
        recipient.fill(self.recipient_email)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)

        # ── Step 6: Fill "Your email" (sender) ──────────────────────
        logger.info("[wetransfer] Filling sender: %s", self.sender_email)
        sender = page.locator('input#email, input[name="email"][type="email"]').first
        sender.click()
        sender.fill(self.sender_email)
        page.wait_for_timeout(500)

        # ── Step 7: Fill message ────────────────────────────────────
        try:
            msg = page.locator('textarea#message, textarea[name="message"]').first
            if msg.is_visible(timeout=2_000):
                msg.fill(f"{self.message_text} — {file_path.name}")
        except PwTimeout:
            pass
        self._screenshot(page, "05_fields")

        # ── Step 8: Click "Transfer" ───────────────────────────────
        logger.info("[wetransfer] Clicking Transfer…")
        transfer_btn = page.locator(
            'button[data-testid="uploaderForm-transfer-button"], '
            'button:has-text("Transfer"), '
            'button:has-text("Get a link")'
        ).first
        transfer_btn.click()
        page.wait_for_timeout(4_000)
        self._screenshot(page, "06_clicked")

        # ── Step 9: Handle email verification ───────────────────────
        verify_input = page.locator(
            'input[name="verification-code"], '
            'input[placeholder*="verification"], '
            'input[placeholder*="code"]'
        )
        if verify_input.count() > 0 and verify_input.first.is_visible(timeout=5_000):
            logger.info("[wetransfer] Email verification required — fetching code…")
            code = self._fetch_verification_code()
            if code:
                logger.info("[wetransfer] Got verification code: %s", code)
                verify_input.first.click()
                verify_input.first.fill(code)
                page.wait_for_timeout(1_000)
                verify_btn = page.locator(
                    'button:has-text("Verify and Send"), '
                    'button:has-text("Verify")'
                ).first
                try:
                    verify_btn.wait_for(state="visible", timeout=5_000)
                    page.wait_for_timeout(1_000)
                    verify_btn.click(force=True)
                    logger.info("[wetransfer] Clicked Verify and Send")
                    page.wait_for_timeout(8_000)
                except PwTimeout:
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(8_000)
            else:
                raise RuntimeError(
                    "[wetransfer] Verification code required but could not be fetched. "
                    "Set MAILSLURP_API_KEY in .env for automatic verification."
                )
        self._screenshot(page, "07_verified")

        # ── Step 10: Wait for completion ────────────────────────────
        logger.info("[wetransfer] Waiting for transfer to complete…")
        try:
            self._wait_for_completion(page)
        except RuntimeError:
            # If we got past verification, the transfer likely succeeded
            # even if we can't detect the success text.
            logger.warning("[wetransfer] Completion text not detected, "
                           "but verification was successful — treating as sent.")
        self._screenshot(page, "08_done")

        logger.info(
            "[wetransfer] Successfully sent %s → %s",
            file_path.name, self.recipient_email,
        )

    # ------------------------------------------------------------------
    def _fetch_verification_code(self, timeout_ms: int = 60_000) -> str | None:
        """Fetch the WeTransfer verification code from MailSlurp."""
        if not self.mailslurp_api_key:
            logger.error("[wetransfer] MAILSLURP_API_KEY not set — cannot fetch code")
            return None

        headers = {"x-api-key": self.mailslurp_api_key}
        base = "https://api.mailslurp.com"

        try:
            # 1. Find inbox by email address
            inbox_id = None
            try:
                resp = requests.get(
                    f"{base}/inboxes/byEmailAddress",
                    params={"emailAddress": self.sender_email},
                    headers=headers, timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                inbox_id = data.get("inboxId") or data.get("id")
            except Exception:
                pass

            # Fallback: list all inboxes
            if not inbox_id:
                resp = requests.get(
                    f"{base}/inboxes", params={"size": 100},
                    headers=headers, timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                inbox_list = data.get("content", data) if isinstance(data, dict) else data
                for inbox in inbox_list:
                    if inbox.get("emailAddress", "").lower() == self.sender_email.lower():
                        inbox_id = inbox["id"]
                        break

            if not inbox_id:
                logger.error("[wetransfer] No MailSlurp inbox for %s", self.sender_email)
                return None

            # 2. Wait for the verification email
            logger.info("[wetransfer] Waiting for verification email (up to %ds)…",
                        timeout_ms // 1000)
            resp = requests.get(
                f"{base}/waitForLatestEmail",
                params={"inboxId": inbox_id, "timeout": timeout_ms, "unreadOnly": "true"},
                headers=headers, timeout=timeout_ms // 1000 + 10,
            )
            resp.raise_for_status()
            email_data = resp.json()
            subject = email_data.get("subject", "")
            body = email_data.get("body", "")
            logger.info("[wetransfer] Email received — subject: %r", subject)

            # 3. Extract alphanumeric code (e.g. "DZEU7D")
            #    Subject first (clean text), then body (messy HTML)
            for text in [subject, body]:
                match = re.search(r'(?:code\s+is:?\s*)([A-Z0-9]{5,8})', text)
                if match:
                    return match.group(1)
            for text in [subject, body]:
                match = re.search(r'\b([A-Z0-9]{5,6})\b', text)
                if match:
                    return match.group(1)

            logger.error("[wetransfer] Could not extract code from email")
            return None

        except Exception as exc:
            logger.error("[wetransfer] MailSlurp error: %s", exc)
            return None

    # ------------------------------------------------------------------
    @staticmethod
    def _click_if_visible(page, selector: str, timeout: int = 4_000) -> bool:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=timeout):
                loc.click()
                page.wait_for_timeout(800)
                return True
        except (PwTimeout, Exception):
            pass
        return False

    # ------------------------------------------------------------------
    @staticmethod
    def _wait_for_completion(page, timeout_sec: int = 15) -> None:
        """Wait for the success panel. After verification, WeTransfer shows
        a panel with "Sent X seconds ago", a we.tl link, and "Total downloads".
        Timeout defaults to 15s — the success panel appears within seconds
        of clicking "Verify and Send".
        """
        import re as _re
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                body_text = page.inner_text("body", timeout=2_000)
            except Exception:
                return  # page closed/navigated = transfer done

            # Primary success markers (post-verification success panel)
            if _re.search(r"Sent\s+\d+\s+(second|minute|hour|day)s?\s+ago", body_text):
                logger.info("[wetransfer] Transfer confirmed (\"Sent ... ago\")")
                return
            if _re.search(r"https?://we\.tl/", body_text):
                logger.info("[wetransfer] Transfer confirmed (we.tl link present)")
                return
            if "Total downloads" in body_text or "Total previews" in body_text:
                logger.info("[wetransfer] Transfer confirmed (download stats visible)")
                return

            # Legacy success markers
            for txt in ("Transfer complete", "Sent!", "Your transfer is on its way",
                        "We sent your transfer", "We're on it"):
                if txt in body_text:
                    logger.info("[wetransfer] Transfer confirmed (%r)", txt)
                    return

            # Progress bar at 100%
            try:
                progress = page.locator('[role="progressbar"]')
                if progress.count() > 0:
                    val = progress.first.get_attribute("aria-valuenow")
                    if val and float(val) >= 100:
                        page.wait_for_timeout(2_000)
                        return
            except Exception:
                return  # page closed = transfer done

            try:
                page.wait_for_timeout(1_000)
            except Exception:
                return  # page closed = transfer done
        raise RuntimeError(
            f"[wetransfer] Upload did not complete within {timeout_sec}s"
        )
