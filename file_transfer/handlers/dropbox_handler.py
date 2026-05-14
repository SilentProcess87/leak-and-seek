"""Copy files to the local Dropbox sync folder.

Requires the Dropbox desktop client to be installed and syncing.
The client automatically uploads anything placed in the sync folder.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from .base import BaseHandler

logger = logging.getLogger(__name__)


class DropboxHandler(BaseHandler):
    name = "dropbox"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.sync_folder = Path(os.getenv("DROPBOX_SYNC_FOLDER", ""))

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not str(self.sync_folder):
            logger.error("[dropbox] DROPBOX_SYNC_FOLDER must be set in .env")
            return False
        if not self.sync_folder.is_dir():
            logger.warning(
                "[dropbox] Sync folder does not exist yet: %s  "
                "(it will be created on first transfer)",
                self.sync_folder,
            )
        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        self.sync_folder.mkdir(parents=True, exist_ok=True)
        dest = self.sync_folder / file_path.name
        shutil.copy2(file_path, dest)
        logger.info("[dropbox] Copied to sync folder: %s", dest)
