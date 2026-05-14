#!/usr/bin/env python3
"""File Transfer Automation – watches a folder and routes files to services.

Usage:
    python main.py                  # uses config.yaml + .env in the same dir
    python main.py --config my.yaml # custom config file
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

import watcher

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        logging.error("Config file not found: %s", config_path)
        sys.exit(1)
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="File Transfer Automation")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(__file__).parent / ".env",
        help="Path to .env file (default: ./.env)",
    )
    args = parser.parse_args()

    # 1. Load environment variables from .env
    load_dotenv(args.env)

    import os
    _setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    logger = logging.getLogger("main")

    # 2. Parse config
    config = _load_config(args.config)
    raw_rules = config.get("rules", [])
    if not raw_rules:
        logger.error("No rules defined in %s", args.config)
        sys.exit(1)

    # 3. Build handler rules (validates credentials)
    rules = watcher.build_rules(raw_rules)
    if not rules:
        logger.error("All rules were skipped (credential issues). Nothing to do.")
        sys.exit(1)

    logger.info("Loaded %d active rule(s).", len(rules))

    # 4. Determine watch folder (fall back to ./inbox if env path is broken)
    env_folder = os.getenv("WATCH_FOLDER", "")
    if env_folder:
        watch_folder = Path(env_folder)
        # If it's an absolute path that doesn't exist and can't be created, use ./inbox
        if watch_folder.is_absolute() and not watch_folder.exists():
            try:
                watch_folder.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                logger.warning(
                    "WATCH_FOLDER '%s' is not accessible, falling back to ./inbox",
                    env_folder,
                )
                watch_folder = Path("./inbox")
    else:
        watch_folder = Path("./inbox")
    watch_folder = watch_folder.resolve()
    logger.info("Watch folder: %s", watch_folder)

    # 5. Start watching
    watcher.start(watch_folder, rules)


if __name__ == "__main__":
    main()
