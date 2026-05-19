"""Screenshot capture and image utilities for the desktop agent.

Uses ``mss`` for fast cross-platform screenshots and ``Pillow`` for
resizing to the recommended 1280×800 (WXGA) resolution that Claude
Computer Use expects.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path

import mss
from PIL import Image

logger = logging.getLogger(__name__)

# Anthropic-recommended resolution for Computer Use
TARGET_WIDTH = 1280
TARGET_HEIGHT = 800

# Optional directory to persist screenshots for debugging
SCREENSHOT_DIR: str | None = os.getenv("DESKTOP_AGENT_SCREENSHOT_DIR")


def capture_screenshot(monitor: int = 0) -> tuple[str, int, int]:
    """Capture the full screen and return (base64_png, width, height).

    Parameters
    ----------
    monitor:
        ``mss`` monitor index.  ``0`` = entire virtual screen,
        ``1`` = primary monitor, etc.

    Returns
    -------
    tuple[str, int, int]
        base64-encoded PNG string, scaled width, scaled height.
    """
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[monitor])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Scale to the target resolution (maintains aspect ratio by stretching)
    img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # Optionally save to disk for debugging
    if SCREENSHOT_DIR:
        _save_debug(png_bytes)

    encoded = base64.standard_b64encode(png_bytes).decode("ascii")
    return encoded, TARGET_WIDTH, TARGET_HEIGHT


def _save_debug(png_bytes: bytes) -> None:
    """Persist a screenshot to the debug directory."""
    if not SCREENSHOT_DIR:
        return
    debug_dir = Path(SCREENSHOT_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)
    import time
    path = debug_dir / f"screenshot_{int(time.time() * 1000)}.png"
    path.write_bytes(png_bytes)
    logger.debug("[screen] Debug screenshot → %s", path)


def get_scale_factors() -> tuple[float, float]:
    """Return (sx, sy) to map Claude's 1280×800 coordinates to the real screen."""
    with mss.mss() as sct:
        mon = sct.monitors[0]  # entire virtual screen
        real_w = mon["width"]
        real_h = mon["height"]
    sx = real_w / TARGET_WIDTH
    sy = real_h / TARGET_HEIGHT
    return sx, sy
