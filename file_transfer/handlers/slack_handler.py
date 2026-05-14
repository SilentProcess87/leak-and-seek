"""Upload files to a Slack channel or DM."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .base import BaseHandler

logger = logging.getLogger(__name__)


class SlackHandler(BaseHandler):
    name = "slack"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.token = os.getenv("SLACK_BOT_TOKEN", "")
        self.channel = os.getenv("SLACK_CHANNEL", "")
        self.message = self.handler_config.get("message", "New file uploaded")
        self._client: WebClient | None = None

    # ------------------------------------------------------------------
    @property
    def client(self) -> WebClient:
        if self._client is None:
            self._client = WebClient(token=self.token)
        return self._client

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not self.token or not self.channel:
            logger.error("[slack] SLACK_BOT_TOKEN and SLACK_CHANNEL must be set in .env")
            return False
        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        try:
            self.client.files_upload_v2(
                channel=self.channel,
                file=str(file_path),
                title=file_path.name,
                initial_comment=self.message,
            )
        except SlackApiError as exc:
            raise RuntimeError(f"Slack upload failed: {exc.response['error']}") from exc
