"""Execute mouse / keyboard / file-dialog actions via ``pyautogui``.

Also includes **Cortex DLP popup detection** — after any file-upload
action the agent checks the screen for a DLP confirmation dialog and
clicks through it automatically (image-based matching from the
original SlackNative.py flow).
"""

from __future__ import annotations

import logging
import os
import platform
import time
from pathlib import Path
from typing import Any

import pyautogui

from .screen import get_scale_factors

logger = logging.getLogger(__name__)

# Cross-platform detection
IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def _clipboard_type(text: str) -> None:
    """Type text by pasting from clipboard.

    ``pyautogui.write()`` duplicates characters on Windows because of
    keyboard input race conditions.  Clipboard paste is instant and
    100% reliable.
    """
    import subprocess as _sp

    if IS_WINDOWS:
        # PowerShell Set-Clipboard
        _sp.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{text}'"],
            capture_output=True, check=False,
        )
    elif IS_MAC:
        _sp.run(["pbcopy"], input=text.encode(), check=False)
    else:
        # Linux xclip fallback
        _sp.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=False)

    time.sleep(0.15)
    _hotkey_ctrl("v")
    time.sleep(0.3)

# Safety: tiny pause between pyautogui actions so DLP agents can react
pyautogui.PAUSE = 0.3

# Global lock — only ONE desktop agent action can run at a time.
# pyautogui controls the physical keyboard/mouse, so parallel
# scripted flows would corrupt each other.
import threading
_DESKTOP_LOCK = threading.Lock()

# Path to the cropped image of the Cortex DLP "confirm" button.
# Users should place their own screenshot crop next to this file or
# set the env var to an absolute path.
_DEFAULT_DLP_BUTTON = Path(__file__).resolve().parent / "confirm_button.png"
DLP_BUTTON_IMAGE: str = os.getenv(
    "DLP_CONFIRM_BUTTON_IMAGE", str(_DEFAULT_DLP_BUTTON)
)
DLP_CONFIDENCE: float = float(os.getenv("DLP_CONFIDENCE", "0.8"))
DLP_WAIT_SECONDS: float = float(os.getenv("DLP_WAIT_SECONDS", "3"))


# ── Claude Computer-Use action dispatcher ──────────────────────────

def execute_computer_action(action: dict[str, Any]) -> None:
    """Translate a Claude ``computer_20250124`` tool-use block into real
    desktop actions via *pyautogui*.

    Parameters
    ----------
    action:
        The ``input`` dict from a Claude tool-use content block, e.g.
        ``{"action": "click", "coordinate": [640, 400]}``.
    """
    sx, sy = get_scale_factors()
    name = action.get("action", "")

    if name == "screenshot":
        # No-op — the agent loop captures screenshots itself.
        return

    if name == "click":
        x, y = action["coordinate"]
        click_type = action.get("click_type", "left")
        btn = {"left": "left", "right": "right", "middle": "middle"}.get(
            click_type, "left"
        )
        real_x, real_y = int(x * sx), int(y * sy)
        logger.info("[actions] click(%s) → (%d, %d)", btn, real_x, real_y)
        pyautogui.click(real_x, real_y, button=btn)

    elif name == "double_click":
        x, y = action["coordinate"]
        real_x, real_y = int(x * sx), int(y * sy)
        logger.info("[actions] double_click → (%d, %d)", real_x, real_y)
        pyautogui.doubleClick(real_x, real_y)

    elif name == "type":
        text = action.get("text", "")
        logger.info("[actions] type(%d chars)", len(text))
        pyautogui.write(text, interval=0.03)

    elif name == "key":
        key = action.get("key", "")
        logger.info("[actions] key(%s)", key)
        # Claude sends keys like "Return", "ctrl+a", "super" etc.
        _press_key(key)

    elif name == "scroll":
        x, y = action.get("coordinate", [640, 400])
        delta = action.get("delta", [0, 0])
        real_x, real_y = int(x * sx), int(y * sy)
        clicks = int(delta[1] / 30) if delta[1] else 0
        logger.info("[actions] scroll(%d) at (%d, %d)", clicks, real_x, real_y)
        pyautogui.scroll(clicks, real_x, real_y)

    elif name == "drag":
        start = action.get("start_coordinate", [0, 0])
        end = action.get("coordinate", [0, 0])
        sx0, sy0 = int(start[0] * sx), int(start[1] * sy)
        ex0, ey0 = int(end[0] * sx), int(end[1] * sy)
        logger.info("[actions] drag (%d,%d) → (%d,%d)", sx0, sy0, ex0, ey0)
        pyautogui.moveTo(sx0, sy0)
        pyautogui.mouseDown()
        time.sleep(0.15)
        pyautogui.moveTo(ex0, ey0, duration=0.4)
        pyautogui.mouseUp()

    elif name == "wait":
        secs = action.get("duration", 2)
        logger.info("[actions] wait(%ds)", secs)
        time.sleep(secs)

    else:
        logger.warning("[actions] Unknown action: %s", name)


# ── DLP Popup Handling ─────────────────────────────────────────────
# Detects the Cortex XDR / DLP popup (CyveraConsole.exe) by finding
# its window, bringing it to focus, and pressing Enter to confirm.
# Falls back to image-based detection if window detection fails.

DLP_PROCESS_NAME = os.getenv("DLP_PROCESS_NAME", "CyveraConsole.exe")


def check_and_handle_dlp_popup() -> bool:
    """Detect and dismiss the Cortex DLP popup.

    Strategy:
    1. Look for a CyveraConsole.exe window (the Cortex XDR DLP popup).
    2. If found, bring it to foreground and press Enter to confirm.
    3. If no window found, fall back to image-based detection.

    Returns True if a popup was detected and handled.
    """
    logger.info("[actions] Checking for Cortex DLP popup (%s)…", DLP_PROCESS_NAME)
    time.sleep(DLP_WAIT_SECONDS)

    # ── Strategy 1: Window-based detection ──────────────────────────
    if _dismiss_dlp_window():
        return True

    # ── Strategy 2: Image-based fallback ───────────────────────────
    if Path(DLP_BUTTON_IMAGE).is_file():
        try:
            location = pyautogui.locateCenterOnScreen(
                DLP_BUTTON_IMAGE, confidence=DLP_CONFIDENCE
            )
            if location is not None:
                logger.info("[actions] DLP popup detected via image! Clicking…")
                pyautogui.click(location)
                time.sleep(1)
                return True
        except pyautogui.ImageNotFoundException:
            pass
        except Exception as exc:
            logger.warning("[actions] Image-based DLP check error: %s", exc)

    logger.info("[actions] No DLP popup detected. Proceeding normally.")
    return False


def _dismiss_dlp_window() -> bool:
    """Find and aggressively dismiss ALL CyveraConsole.exe popup windows."""
    import subprocess as _sp

    if not IS_WINDOWS:
        return False

    # Check if the process is running
    try:
        result = _sp.run(
            ["tasklist", "/FI", f"IMAGENAME eq {DLP_PROCESS_NAME}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        if DLP_PROCESS_NAME.lower() not in result.stdout.lower():
            return False
    except Exception:
        return False

    logger.info("[actions] %s is running — looking for popup windows…", DLP_PROCESS_NAME)
    dismissed = False

    try:
        import pygetwindow as gw

        # Broad keyword match for any Cortex/DLP-related window
        _DLP_KEYWORDS = [
            "cortex", "cyvera", "cyveraconsole", "dlp", "data loss",
            "block", "prevent", "policy", "alert", "notification",
            "warning", "palo alto", "traps", "xdr",
        ]

        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if not title:
                continue
            title_lower = title.lower()
            if any(kw in title_lower for kw in _DLP_KEYWORDS):
                logger.info("[actions] Found DLP window: %r — dismissing…", title)
                _force_close_window(w)
                dismissed = True

    except ImportError:
        logger.debug("[actions] pygetwindow not available")

    # Fallback: brute-force the foreground window if process is running
    if not dismissed:
        try:
            pyautogui.hotkey("alt", "tab")
            time.sleep(0.5)
            # Hammer multiple dismiss keys
            for key in ["enter", "space", "escape"]:
                pyautogui.press(key)
                time.sleep(0.3)
            logger.info("[actions] Sent dismiss keys to foreground window.")
            dismissed = True
        except Exception:
            pass

    return dismissed


def _force_close_window(win) -> None:
    """Aggressively close a window using multiple strategies."""
    try:
        win.activate()
    except Exception:
        try:
            win.minimize()
            win.restore()
        except Exception:
            pass
    time.sleep(0.5)

    # Strategy 1: Enter (default button)
    pyautogui.press("enter")
    time.sleep(0.4)

    # Strategy 2: Space (some dialogs use Space for focused button)
    pyautogui.press("space")
    time.sleep(0.4)

    # Strategy 3: Tab + Enter (move to next button and press)
    pyautogui.press("tab")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.4)

    # Strategy 4: Escape (close dialog)
    pyautogui.press("escape")
    time.sleep(0.4)

    # Strategy 5: Alt+F4 (force close window)
    pyautogui.hotkey("alt", "F4")
    time.sleep(0.5)

    logger.info("[actions] DLP window dismiss sequence complete.")


# ── Scripted Native-App Flows ──────────────────────────────────────
# These bypass Claude Computer Use entirely and drive the desktop app
# directly via keyboard shortcuts — faster and more reliable for
# well-known flows.

def _open_app(app_name: str, startup_delay: float = 5.0) -> None:
    """Launch a desktop app by name, cross-platform."""
    if IS_MAC:
        pyautogui.hotkey("command", "space")
        time.sleep(0.8)
    else:
        pyautogui.press("win")
        time.sleep(1)
    _clipboard_type(app_name)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(startup_delay)


def _open_browser(url: str, startup_delay: float = 4.0) -> None:
    """Open a URL in the default browser, cross-platform.

    Uses webbrowser.open() which is more reliable than typing a URL
    into the Start menu / Spotlight.
    """
    import webbrowser
    logger.info("[actions] Opening browser to %s", url)
    webbrowser.open(url)
    time.sleep(startup_delay)


def _hotkey_ctrl(key: str) -> None:
    """Press Ctrl+key (Windows) or Cmd+key (Mac)."""
    mod = "command" if IS_MAC else "ctrl"
    pyautogui.hotkey(mod, key)


def scripted_slack_upload(
    channel: str,
    file_path: str | Path,
    *,
    startup_delay: float = 5.0,
) -> None:
    """Upload a file to the Slack desktop app using native keyboard
    shortcuts, then handle any Cortex DLP popup.

    Derived from ``SlackNative.py``.  Cross-platform (Windows + Mac).
    Serialized via _DESKTOP_LOCK — only one upload at a time.
    """
    with _DESKTOP_LOCK:
        _do_slack_upload(channel, file_path, startup_delay=startup_delay)


def _do_slack_upload(
    channel: str,
    file_path: str | Path,
    *,
    startup_delay: float = 5.0,
) -> None:
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] Scripted Slack upload → channel=%r, file=%s", channel, file_path)

    # 1. Open Slack via OS launcher
    _open_app("Slack", startup_delay=startup_delay)

    # 2. Navigate to channel (Ctrl/Cmd+K = quick switcher)
    _hotkey_ctrl("k")
    time.sleep(1.5)
    _clipboard_type(channel)
    time.sleep(2)
    pyautogui.press("enter")
    time.sleep(2)

    # 3. Open file upload dialog (Ctrl/Cmd+O)
    _hotkey_ctrl("o")
    time.sleep(2.5)

    # 4. Type the file path in the file picker and confirm
    _clipboard_type(file_path)
    time.sleep(1)
    pyautogui.press("enter")

    # 5. DLP popup handling
    dlp_blocked = check_and_handle_dlp_popup()

    if dlp_blocked:
        # DLP blocked the upload — close any stuck dialogs so the
        # next file can proceed cleanly.
        logger.info("[actions] DLP blocked upload — cleaning up stuck dialogs…")
        time.sleep(1)
        pyautogui.press("escape")   # close file picker if still open
        time.sleep(0.5)
        pyautogui.press("escape")   # close any Slack overlay
        time.sleep(0.5)
        logger.info("[actions] Slack cleanup done — ready for next file.")
    else:
        # 6. Send the file (only if DLP didn't block)
        logger.info("[actions] Sending file to channel…")
        time.sleep(2)
        pyautogui.press("enter")

    logger.info("[actions] Scripted Slack upload complete.")


def scripted_wetransfer_upload(
    file_path: str | Path,
    recipient: str,
    sender: str = "",
    *,
    startup_delay: float = 6.0,
) -> None:
    """Upload a file via WeTransfer using pyautogui browser automation.
    Serialized via _DESKTOP_LOCK.
    """
    with _DESKTOP_LOCK:
        _do_wetransfer_upload(file_path, recipient, sender, startup_delay=startup_delay)


def _do_wetransfer_upload(
    file_path: str | Path,
    recipient: str,
    sender: str = "",
    *,
    startup_delay: float = 6.0,
) -> None:
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] WeTransfer upload → %s → %s", file_path, recipient)

    # 1. Open WeTransfer in browser
    _open_browser("https://wetransfer.com", startup_delay=startup_delay)

    # 2. Handle cookie consent / terms (Tab to button, Enter)
    #    WeTransfer shows "I Agree" or "I Accept" on first visit.
    time.sleep(2)
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(2)
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(2)

    # 3. Click the "+" / "Add your files" button area
    #    The upload button is typically in the center-left of the page.
    #    We Tab to it and press Enter to open the file picker.
    for _ in range(5):
        pyautogui.press("tab")
        time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(3)  # wait for file picker dialog

    # 4. Type file path in the file picker and confirm
    _clipboard_type(file_path)
    time.sleep(1)
    pyautogui.press("enter")
    time.sleep(3)  # wait for upload to start

    # 5. Fill "Email to" field (Tab to it, paste recipient)
    pyautogui.press("tab")
    time.sleep(0.3)
    _clipboard_type(recipient)
    pyautogui.press("enter")  # confirm the email chip
    time.sleep(0.5)

    # 6. Fill "Your email" field
    if sender:
        pyautogui.press("tab")
        time.sleep(0.3)
        _clipboard_type(sender)
        time.sleep(0.5)

    # 7. Skip message field, Tab to Transfer button
    pyautogui.press("tab")  # message field
    time.sleep(0.2)
    pyautogui.press("tab")  # Transfer button
    time.sleep(0.2)
    pyautogui.press("enter")  # click Transfer
    time.sleep(3)

    # 8. DLP popup handling
    check_and_handle_dlp_popup()

    logger.info("[actions] WeTransfer upload initiated — verification may be needed.")


def scripted_browser_upload(
    url: str,
    file_path: str | Path,
    *,
    startup_delay: float = 4.0,
) -> None:
    """Open a URL in the browser and attempt file upload via
    keyboard shortcuts.  Generic pyautogui flow.
    """
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] Browser upload → url=%s, file=%s", url, file_path)

    _open_browser(url, startup_delay=startup_delay)
    time.sleep(3)
    check_and_handle_dlp_popup()
    logger.info("[actions] Browser opened to %s — agent will take over.", url)


# ── Helpers ────────────────────────────────────────────────────────

def _press_key(key_str: str) -> None:
    """Handle Claude's key notation → pyautogui key presses.

    Claude sends things like ``Return``, ``ctrl+a``, ``super``,
    ``BackSpace``, etc.
    """
    _KEY_MAP = {
        "Return": "enter",
        "Enter": "enter",
        "BackSpace": "backspace",
        "Delete": "delete",
        "Escape": "escape",
        "Tab": "tab",
        "space": "space",
        "super": "win",
        "Super_L": "win",
        "Up": "up",
        "Down": "down",
        "Left": "left",
        "Right": "right",
        "Home": "home",
        "End": "end",
        "Page_Up": "pageup",
        "Page_Down": "pagedown",
    }

    if "+" in key_str:
        parts = [_KEY_MAP.get(p.strip(), p.strip().lower()) for p in key_str.split("+")]
        pyautogui.hotkey(*parts)
    else:
        mapped = _KEY_MAP.get(key_str, key_str.lower())
        pyautogui.press(mapped)
