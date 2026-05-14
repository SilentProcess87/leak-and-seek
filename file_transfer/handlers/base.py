"""Base class every transfer handler must implement."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Interface that every destination handler implements."""

    name: str = "base"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        self.handler_config = handler_config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(self, file_path: Path) -> bool:
        """Validate the file and delegate to the concrete handler.

        Returns True on success, False on failure.
        """
        if not file_path.is_file():
            logger.warning("[%s] File no longer exists: %s", self.name, file_path)
            return False

        try:
            self.transfer(file_path)
            logger.info("[%s] Successfully transferred: %s", self.name, file_path.name)
            return True
        except Exception:
            logger.exception("[%s] Failed to transfer: %s", self.name, file_path.name)
            return False

    # ------------------------------------------------------------------
    # To be implemented by subclasses
    # ------------------------------------------------------------------
    @abstractmethod
    def transfer(self, file_path: Path) -> None:
        """Perform the actual file transfer.  Raise on failure."""

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Return True when the required credentials / config are present."""
