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
    """Find and dismiss CyveraConsole.exe popup windows.

    Uses Win32 API to enumerate windows by process ID — this is
    reliable even when pygetwindow can't find the window by title.
    """
    import subprocess as _sp

    if not IS_WINDOWS:
        return False

    # Get the PID(s) of CyveraConsole.exe
    pids = _get_process_pids(DLP_PROCESS_NAME)
    if not pids:
        return False

    logger.info("[actions] %s running (PIDs: %s) — finding popup windows…",
                DLP_PROCESS_NAME, pids)

    # Find all windows belonging to CyveraConsole.exe via Win32 API
    hwnd_list = _get_windows_by_pids(pids)
    if not hwnd_list:
        # Process is running but no visible windows — try foreground
        logger.info("[actions] No windows found by PID — trying foreground…")
        return _dismiss_foreground()

    dismissed = False
    for hwnd, title in hwnd_list:
        logger.info("[actions] Found DLP window (hwnd=%s): %r — dismissing…",
                    hwnd, title)
        _activate_hwnd(hwnd)
        time.sleep(0.5)
        _dismiss_dialog_keys()
        dismissed = True

    return dismissed


def _get_process_pids(process_name: str) -> list[int]:
    """Get PIDs of a running process by name."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        pids = []
        for line in result.stdout.strip().splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2 and parts[0].lower() == process_name.lower():
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []


def _get_windows_by_pids(pids: list[int]) -> list[tuple[int, str]]:
    """Enumerate all visible windows belonging to given PIDs using Win32 API."""
    results: list[tuple[int, str]] = []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid_set = set(pids)

        # Callback for EnumWindows
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def _callback(hwnd, _lparam):
            # Check if window is visible
            if not user32.IsWindowVisible(hwnd):
                return True
            # Get the PID of this window
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value in pid_set:
                # Get window title
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                results.append((hwnd, buf.value))
            return True

        user32.EnumWindows(WNDENUMPROC(_callback), 0)
    except Exception as exc:
        logger.debug("[actions] Win32 EnumWindows error: %s", exc)

    return results


def _activate_hwnd(hwnd: int) -> None:
    """Bring a window to foreground by its handle."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # Restore if minimized
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
        # Bring to foreground
        user32.SetForegroundWindow(hwnd)
    except Exception as exc:
        logger.debug("[actions] Could not activate hwnd %s: %s", hwnd, exc)


def _dismiss_dialog_keys() -> None:
    """Send a sequence of keys to dismiss a dialog — covers all button layouts.

    The Cortex DLP popup has Override / Confirm buttons and a text field.
    Tab navigates between them; Enter/Space clicks the focused one.
    """
    # Tab past the text field to the first button, then press it
    for _ in range(3):
        pyautogui.press("tab")
        time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    # If that didn't close it, try Space on current focus
    pyautogui.press("space")
    time.sleep(0.3)

    # Try Enter again (might now be on a different button)
    pyautogui.press("enter")
    time.sleep(0.3)

    # Escape as last resort
    pyautogui.press("escape")
    time.sleep(0.3)

    # Alt+F4 nuclear option
    pyautogui.hotkey("alt", "F4")
    time.sleep(0.3)

    logger.info("[actions] DLP dismiss key sequence complete.")


def _dismiss_foreground() -> bool:
    """Fallback: send dismiss keys to whatever is in the foreground."""
    try:
        _dismiss_dialog_keys()
        return True
    except Exception:
        return False


# ── Scripted Native-App Flows ──────────────────────────────────────
# These bypass Claude Computer Use entirely and drive the desktop app
# directly via keyboard shortcuts — faster and more reliable for
# well-known flows.

def _is_process_running(name: str) -> bool:
    """Check if a process is running by name."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return name.lower() in result.stdout.lower()
    except Exception:
        return False


def _ensure_app_foreground(app_name: str) -> bool:
    """Bring an app's window to the foreground if it's running."""
    if not IS_WINDOWS:
        return False
    try:
        import pygetwindow as gw
        hint = app_name.lower()
        for w in gw.getAllWindows():
            if hint in (w.title or "").lower():
                try:
                    w.activate()
                except Exception:
                    w.minimize()
                    w.restore()
                time.sleep(1)
                return True
    except ImportError:
        pass
    return False


def _open_app(app_name: str, startup_delay: float = 5.0) -> None:
    """Launch a desktop app by name, cross-platform.

    On Windows, first checks if the app is already running and brings
    it to foreground.  If not, tries the Start menu.  Then verifies
    the correct process started (not the browser).
    """
    process_name = f"{app_name.lower()}.exe"  # e.g. slack.exe

    # If already running, just bring to foreground
    if _is_process_running(process_name):
        logger.info("[actions] %s already running — bringing to foreground", app_name)
        _ensure_app_foreground(app_name)
        time.sleep(2)
        return

    # Launch via Start menu
    logger.info("[actions] Launching %s via Start menu…", app_name)
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

    # Verify the right process started
    if IS_WINDOWS and not _is_process_running(process_name):
        logger.warning(
            "[actions] %s did not start — Start menu may have opened browser instead."
            " Pressing Escape and retrying…", app_name,
        )
        # Close whatever opened (probably browser)
        pyautogui.press("escape")
        time.sleep(1)
        pyautogui.hotkey("alt", "F4")
        time.sleep(1)

        # Try direct path as fallback
        _launch_app_direct(app_name)
        time.sleep(startup_delay)


def _launch_app_direct(app_name: str) -> None:
    """Try to launch an app via common install paths."""
    import subprocess as _sp
    home = Path.home()
    app_lower = app_name.lower()

    # Common install locations on Windows
    candidates = [
        home / "AppData" / "Local" / app_name / f"{app_lower}.exe",
        home / "AppData" / "Local" / "Programs" / app_name / f"{app_lower}.exe",
        Path(f"C:/Program Files/{app_name}/{app_lower}.exe"),
        Path(f"C:/Program Files (x86)/{app_name}/{app_lower}.exe"),
    ]

    for path in candidates:
        if path.is_file():
            logger.info("[actions] Launching %s directly: %s", app_name, path)
            _sp.Popen([str(path)], shell=False)
            return

    logger.warning("[actions] Could not find %s executable in common paths.", app_name)


def _open_browser(url: str, startup_delay: float = 6.0) -> None:
    """Open a URL in the default browser, cross-platform.

    Uses os.startfile() on Windows (works inside PyInstaller bundles)
    and webbrowser.open() elsewhere.
    """
    logger.info("[actions] Opening browser to %s", url)
    if IS_WINDOWS:
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(url)
    time.sleep(startup_delay)


def _wait_for_page_load(url: str, timeout: int = 30, max_retries: int = 3) -> bool:
    """Wait for a browser page to finish loading by checking the title bar.

    Looks for a browser window whose title contains part of the URL's
    domain (e.g. 'wetransfer' for wetransfer.com).  If not found within
    *timeout* seconds, refreshes (F5) and retries up to *max_retries* times.

    Returns True if the page was detected, False if all retries exhausted.
    """
    from urllib.parse import urlparse
    domain_hint = urlparse(url).netloc.replace("www.", "").split(".")[0].lower()
    logger.info("[actions] Waiting for page to load (looking for '%s' in title)…",
                domain_hint)

    for attempt in range(1, max_retries + 1):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if IS_WINDOWS:
                try:
                    import pygetwindow as gw
                    for w in gw.getAllWindows():
                        if domain_hint in (w.title or "").lower():
                            logger.info("[actions] Page loaded (title: %r)", w.title)
                            return True
                except ImportError:
                    pass
            time.sleep(2)

        if attempt < max_retries:
            logger.warning(
                "[actions] Page not loaded after %ds — refreshing (attempt %d/%d)…",
                timeout, attempt, max_retries,
            )
            pyautogui.press("F5")
            time.sleep(5)  # give refresh a head start
        else:
            logger.warning(
                "[actions] Page still not loaded after %d attempts — continuing anyway.",
                max_retries,
            )

    return False


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
        # DLP blocked the upload — two dialogs to close:
        #   1. The "file is blocked" message box (Enter or Space to dismiss)
        #   2. The Windows file picker dialog behind it (Cancel / Escape)
        logger.info("[actions] DLP blocked upload — closing blocked-message dialog…")
        time.sleep(1)

        # Close the "blocked" message box (click OK / acknowledge)
        pyautogui.press("enter")
        time.sleep(1)
        pyautogui.press("space")
        time.sleep(1)

        # Close the file picker dialog (Cancel button = Escape)
        logger.info("[actions] Closing file picker dialog…")
        pyautogui.press("escape")
        time.sleep(1)
    else:
        # 6. Send the file (only if DLP didn't block)
        logger.info("[actions] Sending file to channel…")
        time.sleep(2)
        pyautogui.press("enter")
        time.sleep(2)

    # 7. ALWAYS clean up — close any lingering file dialog or Slack overlay
    #    This is critical: if the file dialog stays open, it blocks all
    #    subsequent uploads.
    logger.info("[actions] Cleaning up any remaining dialogs…")
    for _ in range(4):
        pyautogui.press("escape")
        time.sleep(0.5)

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
    startup_delay: float = 8.0,
) -> None:
    file_path = str(Path(file_path).resolve())
    logger.info("[actions] WeTransfer upload → %s → %s", file_path, recipient)

    # 1. Open WeTransfer in browser
    _open_browser("https://wetransfer.com", startup_delay=startup_delay)

    # 2. Wait for page to actually load (retry with refresh if needed)
    _wait_for_page_load("https://wetransfer.com", timeout=30, max_retries=3)

    # 3. Dismiss any popups (cookie consent, site info, etc.)
    pyautogui.press("escape")
    time.sleep(1)

    # 3. Click "Add files" button — it's in the left panel
    #    Use the "+" icon / "Add files" text area.
    #    Click at roughly (115, 380) relative to the page area.
    logger.info("[actions] Clicking 'Add files' button…")
    pyautogui.click(115, 380)
    time.sleep(3)  # wait for file picker dialog

    # 4. Type file path in the file picker and confirm
    _clipboard_type(file_path)
    time.sleep(1)
    pyautogui.press("enter")
    time.sleep(4)  # wait for upload to start

    # 5. Click "Email to" field and paste recipient
    logger.info("[actions] Filling 'Email to' field…")
    pyautogui.click(165, 461)  # "Email to" field area
    time.sleep(0.5)
    _clipboard_type(recipient)
    pyautogui.press("enter")  # confirm email chip
    time.sleep(1)

    # 6. Click "Title" / message field
    pyautogui.click(165, 545)  # Title field
    time.sleep(0.3)
    _clipboard_type("DLP Test File")
    time.sleep(0.5)

    # 7. Click "Transfer" button
    logger.info("[actions] Clicking 'Transfer' button…")
    pyautogui.click(167, 642)  # Transfer button
    time.sleep(5)

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
