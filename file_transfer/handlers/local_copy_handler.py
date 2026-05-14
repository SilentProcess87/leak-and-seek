"""Copy files to a local or network-mounted destination folder."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from .base import BaseHandler

logger = logging.getLogger(__name__)


class LocalCopyHandler(BaseHandler):
    name = "local_copy"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        raw = os.getenv("LOCAL_COPY_DEST", "")
        self.dest_dir = Path(raw) if raw else Path("./outbox")

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not str(self.dest_dir):
            logger.error("[local_copy] LOCAL_COPY_DEST must be set in .env")
            return False
        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        # Fall back to ./outbox if configured path is inaccessible
        try:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            fallback = Path("./outbox").resolve()
            logger.warning(
                "[local_copy] '%s' not accessible, using %s",
                self.dest_dir, fallback,
            )
            self.dest_dir = fallback
            self.dest_dir.mkdir(parents=True, exist_ok=True)
        dest = self.dest_dir / file_path.name
        shutil.copy2(file_path, dest)
        logger.info("[local_copy] Copied to %s", dest)
