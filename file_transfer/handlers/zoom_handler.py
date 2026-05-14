"""Send files to a Zoom chat channel via the Zoom Server-to-Server OAuth API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

from .base import BaseHandler

logger = logging.getLogger(__name__)

ZOOM_AUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API = "https://api.zoom.us/v2"


class ZoomHandler(BaseHandler):
    name = "zoom"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.account_id = os.getenv("ZOOM_ACCOUNT_ID", "")
        self.client_id = os.getenv("ZOOM_CLIENT_ID", "")
        self.client_secret = os.getenv("ZOOM_CLIENT_SECRET", "")
        self.chat_channel_id = os.getenv("ZOOM_CHAT_CHANNEL_ID", "")
        self.message = self.handler_config.get("message", "New file uploaded")
        self._token: str | None = None

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        required = {
            "ZOOM_ACCOUNT_ID": self.account_id,
            "ZOOM_CLIENT_ID": self.client_id,
            "ZOOM_CLIENT_SECRET": self.client_secret,
            "ZOOM_CHAT_CHANNEL_ID": self.chat_channel_id,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            logger.error("[zoom] Missing env vars: %s", ", ".join(missing))
            return False
        return True

    # ------------------------------------------------------------------
    def _get_token(self) -> str:
        if self._token:
            return self._token
        resp = requests.post(
            ZOOM_AUTH_URL,
            params={"grant_type": "account_credentials", "account_id": self.account_id},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload the file
        upload_url = f"{ZOOM_API}/chat/users/me/messages/files"
        with open(file_path, "rb") as fh:
            resp = requests.post(
                upload_url,
                headers=headers,
                files={"file": (file_path.name, fh)},
                data={"to_channel": self.chat_channel_id},
                timeout=120,
            )
        resp.raise_for_status()

        # 2. Send a companion text message
        msg_url = f"{ZOOM_API}/chat/users/me/messages"
        resp = requests.post(
            msg_url,
            headers=headers,
            json={
                "to_channel": self.chat_channel_id,
                "message": f"{self.message}: {file_path.name}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("[zoom] Sent %s to channel %s", file_path.name, self.chat_channel_id)
