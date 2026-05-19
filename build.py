#!/usr/bin/env python3
"""Build DLPSimulator executable using PyInstaller.

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build artifacts first

Output:
    dist/DLPSimulator.exe    (Windows)
    dist/DLPSimulator         (macOS / Linux)
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC_FILE = ROOT / "dlp_simulator.spec"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"


def _ensure_pyinstaller() -> None:
    """Install PyInstaller if it's not available."""
    try:
        import PyInstaller  # noqa: F401
        print("  ✓ PyInstaller found")
    except ImportError:
        print("  Installing PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("  ✓ PyInstaller installed")


def _ensure_deps() -> None:
    """Install project dependencies needed for the build."""
    req = ROOT / "file_transfer" / "requirements.txt"
    if req.is_file():
        print("  Installing project dependencies…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
        )
        print("  ✓ Dependencies installed")


def _clean() -> None:
    """Remove previous build artifacts."""
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"  ✓ Removed {d}")


def _build() -> None:
    """Run PyInstaller with the spec file."""
    print(f"\n  Building DLPSimulator for {platform.system()}…\n")
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(SPEC_FILE),
    ])

    # Find the output
    exe_name = "DLPSimulator.exe" if platform.system() == "Windows" else "DLPSimulator"
    exe_path = DIST_DIR / exe_name

    if exe_path.is_file():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n  ╔══════════════════════════════════════════╗")
        print(f"  ║  ✓ Build successful!                     ║")
        print(f"  ╚══════════════════════════════════════════╝")
        print(f"  Output: {exe_path}")
        print(f"  Size:   {size_mb:.1f} MB")
        print()
        print(f"  Distribute this file to users. They just double-click")
        print(f"  (or run from terminal) — no Python install needed.")
        if platform.system() != "Windows":
            print(f"\n  NOTE: This build is for {platform.system()} only.")
            print(f"  To build a Windows .exe, run this script on a Windows machine.")
    else:
        print(f"\n  ✗ Build failed — {exe_path} not found.")
        sys.exit(1)


def main() -> None:
    print()
    print("  ┌──────────────────────────────────────┐")
    print("  │   DLP Simulator Build System          │")
    print("  └──────────────────────────────────────┘")
    print()

    if "--clean" in sys.argv:
        _clean()

    _ensure_pyinstaller()
    _ensure_deps()
    _build()


if __name__ == "__main__":
    main()
