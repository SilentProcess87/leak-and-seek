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

import os
import threading

# Seconds to wait after detecting a file before processing it.
# Gives the OS time to finish writing / moving the file.
_SETTLE_DELAY = 2.0

# Seconds to wait BETWEEN handlers for the same file.
# Gives DLP agents time to react and prevents UI overlap.
_HANDLER_DELAY = float(os.getenv("DLP_HANDLER_DELAY", "5"))

# Seconds to wait BETWEEN processing different files.
_FILE_DELAY = float(os.getenv("DLP_FILE_DELAY", "10"))

# Files to ignore (OS-generated metadata)
_IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_IGNORED_PREFIXES = ("~$", ".")  # Office temp files, hidden files

# Single-threaded: only ONE file processed at a time.
# Desktop agent controls the physical keyboard/mouse so parallel
# processing would create chaos.
_FILE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="file")

# Global lock for serial file processing
_FILE_LOCK = threading.Lock()


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
        """Process one file through all handlers SEQUENTIALLY."""
        time.sleep(_SETTLE_DELAY)
        if not file_path.is_file():
            return  # already gone (race with previous deletion)

        # Only one file at a time — wait for previous file to finish
        with _FILE_LOCK:
            self._process_file(file_path)

    def _process_file(self, file_path: Path) -> None:
        if not file_path.is_file():
            return
        logger.info("New file detected: %s", file_path.name)
        matched = False
        for rule in self.rules:
            if rule.matches(file_path.name):
                matched = True
                logger.info("  → Matched rule '%s' (%d handlers, running sequentially)",
                            rule.name, len(rule.handlers))

                # Run each handler ONE AT A TIME with a wait between them
                for i, handler in enumerate(rule.handlers):
                    logger.info("  → [%d/%d] Running handler: %s",
                                i + 1, len(rule.handlers), handler.name)
                    try:
                        handler.process(file_path)
                    except Exception:
                        logger.exception("Handler '%s' failed for %s",
                                         handler.name, file_path.name)

                    # Wait between handlers so DLP can react
                    if i < len(rule.handlers) - 1:
                        logger.debug("  → Waiting %.1fs before next handler…",
                                     _HANDLER_DELAY)
                        time.sleep(_HANDLER_DELAY)

                # Delete the file from the watch folder after all handlers
                _delete_after_transfer(file_path)
                break  # first-match-wins

        if not matched:
            logger.info("  → No matching rule for %s", file_path.name)

        # Wait before processing the next file
        logger.debug("Waiting %.1fs before next file…", _FILE_DELAY)
        time.sleep(_FILE_DELAY)


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
