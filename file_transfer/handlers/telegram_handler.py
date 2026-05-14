"""Send files to a Telegram chat via the Bot API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

from .base import BaseHandler

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramHandler(BaseHandler):
    name = "telegram"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.message = self.handler_config.get("message", "")

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.error(
                "[telegram] TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env"
            )
            return False
        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendDocument"
        with open(file_path, "rb") as fh:
            data = {"chat_id": self.chat_id}
            if self.message:
                data["caption"] = f"{self.message}: {file_path.name}"
            resp = requests.post(url, data=data, files={"document": fh}, timeout=120)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
        logger.info("[telegram] Sent %s to chat %s", file_path.name, self.chat_id)
