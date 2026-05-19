#!/usr/bin/env python3
"""DLP File Transfer Simulator — fully autonomous launcher.

Single entry point for the bundled executable.  On first run it asks
for ALL service credentials, writes them to a **hidden** config file,
deploys test files, and starts the watcher.  From then on it runs
fully unattended — auto-seeding files on a timer and routing them
to every configured service (Slack, Box, Dropbox, OneDrive, …).

Usage (development):
    python launcher.py

Usage (bundled exe):
    DLPSimulator.exe
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve paths — works both in dev and inside a PyInstaller bundle.
# ---------------------------------------------------------------------------

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
TEST_FILES_DIR = BASE_DIR / "detectors_profile_test_files"

VERSION = "1.1.0"
IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Working directory + hidden config
# ---------------------------------------------------------------------------

WORK_DIR = Path.home() / "DLPSimulator"
HIDDEN_ENV = WORK_DIR / ".dlp_env"             # hidden credentials file
HIDDEN_CONFIG = WORK_DIR / ".dlp_config.yaml"   # hidden routing rules


# ---------------------------------------------------------------------------
# Hide a file (OS-specific)
# ---------------------------------------------------------------------------

def _hide_file(path: Path) -> None:
    """Make a file hidden on the current OS."""
    if IS_WINDOWS:
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2)  # type: ignore[union-attr]
        except Exception:
            subprocess.run(["attrib", "+h", str(path)], capture_output=True, check=False)
    # On Mac/Linux files starting with '.' are already hidden.


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _banner() -> None:
    print()
    print("  ╔══════════════════════════════════════════╗")
    print(f"  ║   DLP File Transfer Simulator v{VERSION}    ║")
    print("  ║   Palo Alto Networks — Lab Use Only      ║")
    print("  ╚══════════════════════════════════════════╝")
    print()


# ---------------------------------------------------------------------------
# Setup wizard — collect ALL credentials upfront
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    else:
        return input(f"  {prompt}: ").strip()


def _setup_wizard() -> Path:
    """Collect ALL env vars and write hidden config files."""
    print("  ┌──────────────────────────────────────────┐")
    print("  │  First-Run Setup — Configure All Services │")
    print("  └──────────────────────────────────────────┘")
    print(f"\n  OS: {platform.system()}\n")

    env: dict[str, str] = {}

    # ── General ────────────────────────────────────────────────────
    print("  ── General ──")
    inbox = _ask("Watch folder", str(WORK_DIR / "inbox"))
    env["WATCH_FOLDER"] = inbox
    env["LOG_LEVEL"] = "INFO"
    env["LOCAL_COPY_DEST"] = str(WORK_DIR / "outbox")
    print()

    # ── Slack ──────────────────────────────────────────────────────
    print("  ── Slack (native desktop app — no API key needed) ──")
    env["SLACK_CHANNEL"] = _ask("Slack channel", "#general")
    print()

    # ── Cloud sync folders ─────────────────────────────────────────
    print("  ── Cloud Sync Folders (leave blank to skip) ──")
    env["BOX_SYNC_FOLDER"] = _ask("Box Drive sync folder", "")
    env["DROPBOX_SYNC_FOLDER"] = _ask("Dropbox sync folder", "")
    env["ONEDRIVE_SYNC_FOLDER"] = _ask("OneDrive sync folder", "")
    print()

    # ── SFTP ───────────────────────────────────────────────────────
    print("  ── SFTP (leave host blank to skip) ──")
    env["SFTP_HOST"] = _ask("SFTP host", "")
    if env["SFTP_HOST"]:
        env["SFTP_PORT"] = _ask("SFTP port", "22")
        env["SFTP_USERNAME"] = _ask("SFTP username", "")
        env["SFTP_PASSWORD"] = _ask("SFTP password", "")
        env["SFTP_REMOTE_DIR"] = _ask("SFTP remote dir", "/uploads")
    print()

    # ── Anthropic API key ──────────────────────────────────────────
    print("  ── AI Desktop Agent (for Teams / Telegram / Gmail) ──")
    print("  Not needed for Slack.  Leave blank to skip.")
    env["ANTHROPIC_API_KEY"] = _ask("Anthropic API key", "")
    env["DESKTOP_AGENT_MODEL"] = "claude-sonnet-4-20250514"
    env["DESKTOP_AGENT_MAX_STEPS"] = "30"
    env["DESKTOP_AGENT_SCREENSHOT_DIR"] = str(WORK_DIR / "screenshots")
    print()

    # ── Teams / Telegram / Gmail ───────────────────────────────────
    env["TEAMS_TEAM"] = ""
    env["TEAMS_CHANNEL"] = ""
    env["TEAMS_WEB_URL"] = ""
    env["TELEGRAM_CHAT"] = ""
    env["GMAIL_RECIPIENT"] = ""

    if env["ANTHROPIC_API_KEY"]:
        print("  ── Teams (browser via AI agent) ──")
        env["TEAMS_TEAM"] = _ask("Teams team name (blank to skip)", "")
        if env["TEAMS_TEAM"]:
            env["TEAMS_CHANNEL"] = _ask("Teams channel", "General")
            env["TEAMS_WEB_URL"] = _ask("Teams URL", "https://teams.microsoft.com")
        print()

        print("  ── Telegram (browser via AI agent) ──")
        env["TELEGRAM_CHAT"] = _ask("Telegram chat name (blank to skip)", "")
        print()

        print("  ── Gmail (browser via AI agent) ──")
        env["GMAIL_RECIPIENT"] = _ask("Gmail recipient (blank to skip)", "")
        print()

    # ── Auto-seed settings ─────────────────────────────────────────
    print("  ── Auto-Seed ──")
    env["DLP_AUTO_SEED_INTERVAL"] = _ask("Seconds between auto-seeds", "120")
    env["DLP_AUTO_SEED_COUNT"] = _ask("Files per auto-seed", "2")
    print()

    # ── DLP popup ──────────────────────────────────────────────────
    env["DLP_CONFIDENCE"] = "0.8"
    env["DLP_WAIT_SECONDS"] = "3"

    # ── Write hidden files ─────────────────────────────────────────
    _write_hidden_env(env)
    _write_hidden_config(env)

    return Path(inbox)


# ---------------------------------------------------------------------------
# Write hidden env file
# ---------------------------------------------------------------------------

def _write_hidden_env(env: dict[str, str]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# DLP Simulator — auto-generated credentials",
        f"# {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for key, val in env.items():
        lines.append(f"{key}={val}")

    HIDDEN_ENV.write_text("\n".join(lines), encoding="utf-8")
    _hide_file(HIDDEN_ENV)
    print(f"  ✓ Credentials saved (hidden): {HIDDEN_ENV.name}")


# ---------------------------------------------------------------------------
# Generate config.yaml with ALL active handlers
# ---------------------------------------------------------------------------

def _write_hidden_config(env: dict[str, str]) -> None:
    handlers: list[dict] = []

    # Slack — always active
    handlers.append({
        "type": "desktop_agent",
        "app": "slack",
        "channel": env.get("SLACK_CHANNEL", "#general"),
    })

    # Cloud sync folders
    if env.get("BOX_SYNC_FOLDER"):
        handlers.append({"type": "box"})
    if env.get("DROPBOX_SYNC_FOLDER"):
        handlers.append({"type": "dropbox"})
    if env.get("ONEDRIVE_SYNC_FOLDER"):
        handlers.append({"type": "onedrive"})

    # SFTP
    if env.get("SFTP_HOST"):
        handlers.append({"type": "sftp"})

    # AI-driven browser apps
    if env.get("ANTHROPIC_API_KEY"):
        if env.get("TEAMS_TEAM"):
            handlers.append({
                "type": "desktop_agent", "app": "teams",
                "team": env["TEAMS_TEAM"],
                "channel": env.get("TEAMS_CHANNEL", "General"),
                "url": env.get("TEAMS_WEB_URL", "https://teams.microsoft.com"),
            })
        if env.get("TELEGRAM_CHAT"):
            handlers.append({
                "type": "desktop_agent", "app": "telegram",
                "chat": env["TELEGRAM_CHAT"],
            })
        if env.get("GMAIL_RECIPIENT"):
            handlers.append({
                "type": "desktop_agent", "app": "gmail",
                "recipient": env["GMAIL_RECIPIENT"],
            })

    # Local copy — always active (audit trail)
    handlers.append({"type": "local_copy"})

    config = {"rules": [{"name": "dlp_all_services", "pattern": "*", "handlers": handlers}]}
    HIDDEN_CONFIG.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
    _hide_file(HIDDEN_CONFIG)

    names = [h["type"] + ("/" + h["app"] if "app" in h else "") for h in handlers]
    print(f"  ✓ Active handlers: {', '.join(names)}")


# ---------------------------------------------------------------------------
# Deploy test files
# ---------------------------------------------------------------------------

def _deploy_test_files(inbox: Path, count: int | None = None) -> int:
    inbox.mkdir(parents=True, exist_ok=True)

    test_dir = TEST_FILES_DIR
    if not test_dir.is_dir():
        test_dir = Path(__file__).resolve().parent.parent / "detectors_profile_test_files"
    if not test_dir.is_dir():
        return 0

    files = [f for f in test_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
    if not files:
        return 0

    if count is not None:
        files = random.sample(files, min(count, len(files)))

    copied = 0
    for src in files:
        dest = inbox / f"{src.stem}_{int(time.time() * 1000) % 100000}{src.suffix}"
        shutil.copy2(src, dest)
        copied += 1
    return copied


# ---------------------------------------------------------------------------
# Auto-seed (background timer)
# ---------------------------------------------------------------------------

def _auto_seed_loop(inbox: Path, interval: int, count: int) -> None:
    logger = logging.getLogger("auto_seed")
    while True:
        time.sleep(interval)
        n = _deploy_test_files(inbox, count=count)
        if n:
            logger.info("Auto-seeded %d file(s) into %s", n, inbox)


def _start_auto_seed(inbox: Path) -> None:
    interval = int(os.getenv("DLP_AUTO_SEED_INTERVAL", "120"))
    count = int(os.getenv("DLP_AUTO_SEED_COUNT", "2"))
    t = threading.Thread(
        target=_auto_seed_loop, args=(inbox, interval, count),
        daemon=True, name="auto_seed",
    )
    t.start()


# ---------------------------------------------------------------------------
# Start watcher
# ---------------------------------------------------------------------------

def _start_watcher(config_path: Path, watch_folder: Path) -> None:
    file_transfer_dir = BASE_DIR
    if str(file_transfer_dir) not in sys.path:
        sys.path.insert(0, str(file_transfer_dir))

    import watcher  # noqa: E402

    with open(config_path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    rules = watcher.build_rules(config.get("rules", []))
    if not rules:
        print("  ✗ No valid rules — check your config.")
        return

    watch_folder.mkdir(parents=True, exist_ok=True)
    watcher.start(watch_folder, rules)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _banner()
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # ── First-run: setup wizard ────────────────────────────────────
    if not HIDDEN_ENV.is_file():
        inbox = _setup_wizard()
        print()
    else:
        print(f"  Config loaded from hidden file.")

    # ── Load credentials ───────────────────────────────────────────
    load_dotenv(HIDDEN_ENV, override=True)
    _setup_logging()

    inbox = Path(os.getenv("WATCH_FOLDER", str(WORK_DIR / "inbox")))
    interval = int(os.getenv("DLP_AUTO_SEED_INTERVAL", "120"))
    seed_count = int(os.getenv("DLP_AUTO_SEED_COUNT", "2"))

    # ── Initial seed — deploy ALL test files ───────────────────────
    n = _deploy_test_files(inbox)
    print(f"  ✓ {n} test file(s) deployed to {inbox}")

    # ── Start auto-seed timer ──────────────────────────────────────
    _start_auto_seed(inbox)
    print(f"  ✓ Auto-seed: {seed_count} file(s) every {interval}s")

    # ── Start watcher (blocking — runs forever) ────────────────────
    print(f"  ✓ Watcher active — monitoring {inbox}")
    print("    Everything is automatic. Press Ctrl+C to stop.\n")
    _start_watcher(HIDDEN_CONFIG, inbox)


def _setup_logging() -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


if __name__ == "__main__":
    main()
