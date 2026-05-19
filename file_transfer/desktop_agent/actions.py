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

# Safety: tiny pause between pyautogui actions so DLP agents can react
pyautogui.PAUSE = 0.3

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
# Ported from SlackNative.py — scans the screen for a Cortex DLP
# confirmation button and clicks it if present.

def check_and_handle_dlp_popup() -> bool:
    """Scan the screen for a Cortex DLP popup and click the confirm button.

    Returns True if a popup was detected and handled, False otherwise.
    """
    logger.info("[actions] Checking for Cortex DLP popup…")
    time.sleep(DLP_WAIT_SECONDS)

    if not Path(DLP_BUTTON_IMAGE).is_file():
        logger.debug(
            "[actions] DLP button image not found at %s — skipping check",
            DLP_BUTTON_IMAGE,
        )
        return False

    try:
        location = pyautogui.locateCenterOnScreen(
            DLP_BUTTON_IMAGE, confidence=DLP_CONFIDENCE
        )
        if location is not None:
            logger.info("[actions] DLP popup detected! Clicking confirm button…")
            pyautogui.click(location)
            time.sleep(1)
            return True
    except pyautogui.ImageNotFoundException:
        logger.info("[actions] No DLP popup detected. Proceeding normally.")
    except Exception as exc:
        logger.warning("[actions] DLP popup check error: %s", exc)

    return False


# ── Scripted Native-App Flows ──────────────────────────────────────
# These bypass Claude Computer Use entirely and drive the desktop app
# directly via keyboard shortcuts — faster and more reliable for
# well-known flows.

def _open_app(app_name: str, startup_delay: float = 5.0) -> None:
    """Launch a desktop app by name, cross-platform."""
    if IS_MAC:
        # Cmd+Space → Spotlight → type app name → Enter
        pyautogui.hotkey("command", "space")
        time.sleep(0.8)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(1)
        pyautogui.press("enter")
    else:
        # Windows: Win key → type app name → Enter
        pyautogui.press("win")
        time.sleep(1)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(1)
        pyautogui.press("enter")
    time.sleep(startup_delay)


def _open_browser(url: str, startup_delay: float = 4.0) -> None:
    """Open a URL in the default browser via OS launcher, cross-platform."""
    if IS_MAC:
        pyautogui.hotkey("command", "space")
        time.sleep(0.8)
        pyautogui.write(url, interval=0.02)
        time.sleep(0.5)
        pyautogui.press("enter")
    else:
        pyautogui.press("win")
        time.sleep(1)
        pyautogui.write(url, interval=0.02)
        time.sleep(0.5)
        pyautogui.press("enter")
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
    """
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] Scripted Slack upload → channel=%r, file=%s", channel, file_path)

    # 1. Open Slack via OS launcher
    _open_app("Slack", startup_delay=startup_delay)

    # 2. Navigate to channel (Ctrl/Cmd+K = quick switcher)
    _hotkey_ctrl("k")
    time.sleep(1.5)
    pyautogui.write(channel, interval=0.04)
    time.sleep(2)
    pyautogui.press("enter")
    time.sleep(2)

    # 3. Open file upload dialog (Ctrl/Cmd+U)
    _hotkey_ctrl("u")
    time.sleep(2.5)

    # 4. Type the file path in the file picker and confirm
    pyautogui.write(file_path, interval=0.02)
    time.sleep(1)
    pyautogui.press("enter")

    # 5. DLP popup handling
    check_and_handle_dlp_popup()

    # 6. Send the file
    logger.info("[actions] Sending file to channel…")
    time.sleep(2)
    pyautogui.press("enter")

    logger.info("[actions] Scripted Slack upload complete.")


def scripted_browser_upload(
    url: str,
    file_path: str | Path,
    *,
    startup_delay: float = 4.0,
) -> None:
    """Open a URL in the browser and attempt file upload via
    keyboard shortcuts.  This is a generic pyautogui flow for
    web apps — works for WeTransfer, Gmail, etc.
    """
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] Browser upload → url=%s, file=%s", url, file_path)

    # 1. Open the URL
    _open_browser(url, startup_delay=startup_delay)

    # 2. Wait for page to load, then look for an upload area
    #    Many web apps support Ctrl+O or have a visible upload button.
    #    We use Tab navigation + Enter as a generic approach.
    time.sleep(3)

    # 3. DLP popup handling (in case the browser triggers it)
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
