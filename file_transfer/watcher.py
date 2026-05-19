"""Watch a folder for new files and dispatch them to configured handlers."""

from __future__ import annotations

import fnmatch
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from handlers import create_handler
from handlers.base import BaseHandler

logger = logging.getLogger(__name__)

# Seconds to wait after detecting a file before processing it.
# Gives the OS time to finish writing / moving the file.
_SETTLE_DELAY = 1.0

# Files to ignore (OS-generated metadata)
_IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_IGNORED_PREFIXES = ("~$", ".")  # Office temp files, hidden files

# Thread pool for processing files in parallel
_FILE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file")
_HANDLER_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="handler")


class _Rule:
    """One routing rule: pattern → list of handler instances."""

    def __init__(self, name: str, pattern: str, handlers: list[BaseHandler]) -> None:
        self.name = name
        self.pattern = pattern
        self.handlers = handlers

    def matches(self, filename: str) -> bool:
        return fnmatch.fnmatch(filename.lower(), self.pattern.lower())


def build_rules(raw_rules: list[dict[str, Any]]) -> list[_Rule]:
    """Parse config.yaml rules into _Rule objects, validating credentials."""
    rules: list[_Rule] = []
    for entry in raw_rules:
        handler_instances: list[BaseHandler] = []
        for h_cfg in entry.get("handlers", []):
            h_type = h_cfg.pop("type")
            handler = create_handler(h_type, h_cfg)
            if not handler.validate_credentials():
                logger.warning(
                    "Rule '%s': handler '%s' has invalid credentials – skipping it.",
                    entry["name"],
                    h_type,
                )
                continue
            handler_instances.append(handler)
        if handler_instances:
            rules.append(
                _Rule(
                    name=entry["name"],
                    pattern=entry["pattern"],
                    handlers=handler_instances,
                )
            )
    return rules


class _EventHandler(FileSystemEventHandler):
    """React to new files in the watched folder."""

    def __init__(self, rules: list[_Rule]) -> None:
        super().__init__()
        self.rules = rules

    # ------------------------------------------------------------------
    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._enqueue(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._enqueue(Path(event.dest_path))

    # ------------------------------------------------------------------
    def _enqueue(self, file_path: Path) -> None:
        """Skip noise files, then dispatch in a worker thread."""
        name = file_path.name
        if name in _IGNORED_NAMES or name.startswith(_IGNORED_PREFIXES):
            logger.debug("Ignoring %s", name)
            return
        _FILE_EXECUTOR.submit(self._dispatch, file_path)

    # ------------------------------------------------------------------
    def _dispatch(self, file_path: Path) -> None:
        time.sleep(_SETTLE_DELAY)
        if not file_path.is_file():
            return  # already gone (race with previous deletion)
        logger.info("New file detected: %s", file_path.name)
        matched = False
        for rule in self.rules:
            if rule.matches(file_path.name):
                matched = True
                logger.info("  → Matched rule '%s' (%d handlers in parallel)",
                            rule.name, len(rule.handlers))
                # Run handlers in parallel within the rule
                futures = [
                    _HANDLER_EXECUTOR.submit(handler.process, file_path)
                    for handler in rule.handlers
                ]
                for fut in futures:
                    try:
                        fut.result()  # surface exceptions
                    except Exception:
                        logger.exception("Handler failed for %s", file_path.name)

                # Delete the file from the watch folder after all handlers
                # have finished so it doesn't get re-processed.
                _delete_after_transfer(file_path)
                break  # first-match-wins
        if not matched:
            logger.info("  → No matching rule for %s", file_path.name)


def _delete_after_transfer(file_path: Path) -> None:
    """Remove a file from the watch folder after all handlers ran."""
    try:
        if file_path.is_file():
            file_path.unlink()
            logger.info("  → Deleted from inbox: %s", file_path.name)
    except Exception:
        logger.warning("  → Could not delete %s (may already be gone)", file_path.name)


def start(watch_folder: Path, rules: list[_Rule]) -> None:
    """Block forever, watching *watch_folder* for new files."""
    import os
    watch_folder.mkdir(parents=True, exist_ok=True)

    # Recursive by default — set WATCH_RECURSIVE=false to scan only top-level
    recursive = os.getenv("WATCH_RECURSIVE", "true").lower() == "true"

    observer = Observer()
    observer.schedule(_EventHandler(rules), str(watch_folder), recursive=recursive)
    observer.start()
    logger.info(
        "Watching folder: %s (recursive=%s, Ctrl+C to stop)",
        watch_folder, recursive,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        observer.stop()
        observer.join()
