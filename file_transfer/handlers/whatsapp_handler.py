"""Send files via WhatsApp using the Twilio API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from twilio.rest import Client as TwilioClient

from .base import BaseHandler

logger = logging.getLogger(__name__)


class WhatsAppHandler(BaseHandler):
    name = "whatsapp"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("WHATSAPP_FROM_NUMBER", "")  # whatsapp:+14155238886
        self.to_number = os.getenv("WHATSAPP_TO_NUMBER", "")      # whatsapp:+1234567890
        self.message = self.handler_config.get("message", "New file uploaded")
        # A publicly reachable base URL where the watcher can serve files temporarily.
        # Twilio fetches the media from this URL.  See README for options.
        self.media_base_url = os.getenv("WHATSAPP_MEDIA_BASE_URL", "")
        self._client: TwilioClient | None = None

    # ------------------------------------------------------------------
    @property
    def client(self) -> TwilioClient:
        if self._client is None:
            self._client = TwilioClient(self.account_sid, self.auth_token)
        return self._client

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        required = {
            "TWILIO_ACCOUNT_SID": self.account_sid,
            "TWILIO_AUTH_TOKEN": self.auth_token,
            "WHATSAPP_FROM_NUMBER": self.from_number,
            "WHATSAPP_TO_NUMBER": self.to_number,
            "WHATSAPP_MEDIA_BASE_URL": self.media_base_url,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            logger.error("[whatsapp] Missing env vars: %s", ", ".join(missing))
            return False
        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        media_url = f"{self.media_base_url.rstrip('/')}/{file_path.name}"
        msg = self.client.messages.create(
            body=f"{self.message}: {file_path.name}",
            from_=self.from_number,
            to=self.to_number,
            media_url=[media_url],
        )
        logger.info("[whatsapp] Sent %s → %s (sid=%s)", file_path.name, self.to_number, msg.sid)
