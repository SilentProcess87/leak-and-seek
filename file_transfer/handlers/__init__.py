"""Handler registry – maps config type names to concrete handler classes."""

from __future__ import annotations

from typing import Any

from .base import BaseHandler
from .box_handler import BoxHandler
from .dropbox_handler import DropboxHandler
from .local_copy_handler import LocalCopyHandler
from .onedrive_handler import OneDriveHandler
from .sftp_handler import SFTPHandler
from .slack_handler import SlackHandler
from .teams_handler import TeamsHandler
from .telegram_handler import TelegramHandler
from .wetransfer_handler import WeTransferHandler
from .whatsapp_handler import WhatsAppHandler
from .zoom_handler import ZoomHandler

HANDLER_MAP: dict[str, type[BaseHandler]] = {
    "slack": SlackHandler,
    "local_copy": LocalCopyHandler,
    "sftp": SFTPHandler,
    "teams": TeamsHandler,
    "whatsapp": WhatsAppHandler,
    "telegram": TelegramHandler,
    "zoom": ZoomHandler,
    "box": BoxHandler,
    "dropbox": DropboxHandler,
    "onedrive": OneDriveHandler,
    "wetransfer": WeTransferHandler,
}


def create_handler(handler_type: str, handler_config: dict[str, Any] | None = None) -> BaseHandler:
    """Instantiate a handler by its config type name."""
    cls = HANDLER_MAP.get(handler_type)
    if cls is None:
        raise ValueError(
            f"Unknown handler type '{handler_type}'. "
            f"Available: {', '.join(HANDLER_MAP)}"
        )
    return cls(handler_config)
