"""Seed the inbox with random files from detectors_profile_test_files.

Copies 1-N random test files into the watcher's inbox folder, triggering
the file transfer automation to route them to all configured services.

Usage:
    python seed_inbox.py            # copy 1 random file
    python seed_inbox.py -n 3       # copy 3 random files
    python seed_inbox.py -n 3 -d 5  # copy 3 files, 5s delay between each
"""

import argparse
import os
import random
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

# Relative paths (from file_transfer/)
TEST_FILES_DIR = Path(__file__).parent.parent / "detectors_profile_test_files"
DEFAULT_INBOX = Path(__file__).parent / "inbox"


def get_test_files() -> list[Path]:
    """Return all non-hidden files in the test directory."""
    return [
        f for f in TEST_FILES_DIR.rglob("*")
        if f.is_file() and not f.name.startswith(".")
    ]


def seed(count: int, delay: float, inbox: Path) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    files = get_test_files()

    if not files:
        print(f"No files found in {TEST_FILES_DIR}")
        return

    print(f"Found {len(files)} test files in {TEST_FILES_DIR.relative_to(TEST_FILES_DIR.parent.parent)}")
    print(f"Inbox: {inbox}")
    print(f"Seeding {count} file(s)…\n")

    picked = random.sample(files, min(count, len(files)))

    for i, src in enumerate(picked, 1):
        dest = inbox / src.name
        # Avoid overwriting — add suffix if name exists
        if dest.exists():
            dest = inbox / f"{src.stem}_{int(time.time())}{src.suffix}"

        shutil.copy2(src, dest)
        rel = src.relative_to(TEST_FILES_DIR)
        print(f"  [{i}/{len(picked)}] Copied: {rel}  →  inbox/{dest.name}")

        if i < len(picked) and delay > 0:
            print(f"         Waiting {delay}s …")
            time.sleep(delay)

    print(f"\n✅ Done — {len(picked)} file(s) placed in inbox/")
    print("   The watcher (main.py) will route them to configured services.")


if __name__ == "__main__":
    # Load .env so WATCH_FOLDER is available
    load_dotenv(Path(__file__).parent / ".env")

    parser = argparse.ArgumentParser(description="Seed inbox with random test files")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="Number of random files to copy (default: 1)")
    parser.add_argument("-d", "--delay", type=float, default=2.0,
                        help="Seconds between each file (default: 2)")
    args = parser.parse_args()

    watch_folder = Path(os.getenv("WATCH_FOLDER", str(DEFAULT_INBOX)))
    seed(args.count, args.delay, watch_folder)
