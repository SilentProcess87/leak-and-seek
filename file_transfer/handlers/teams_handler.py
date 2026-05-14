"""Upload files to a Microsoft Teams channel via the MS Graph API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import msal
import requests

from .base import BaseHandler

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class TeamsHandler(BaseHandler):
    name = "teams"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.tenant_id = os.getenv("TEAMS_TENANT_ID", "")
        self.client_id = os.getenv("TEAMS_CLIENT_ID", "")
        self.client_secret = os.getenv("TEAMS_CLIENT_SECRET", "")
        self.team_id = os.getenv("TEAMS_TEAM_ID", "")
        self.channel_id = os.getenv("TEAMS_CHANNEL_ID", "")
        self.message = self.handler_config.get("message", "New file uploaded")
        self._token: str | None = None

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        required = {
            "TEAMS_TENANT_ID": self.tenant_id,
            "TEAMS_CLIENT_ID": self.client_id,
            "TEAMS_CLIENT_SECRET": self.client_secret,
            "TEAMS_TEAM_ID": self.team_id,
            "TEAMS_CHANNEL_ID": self.channel_id,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            logger.error("[teams] Missing env vars: %s", ", ".join(missing))
            return False
        return True

    # ------------------------------------------------------------------
    def _get_token(self) -> str:
        if self._token:
            return self._token
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id, authority=authority, client_credential=self.client_secret
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"Teams auth failed: {result.get('error_description', result)}")
        self._token = result["access_token"]
        return self._token

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload file to the channel's file folder (SharePoint-backed)
        upload_url = (
            f"{GRAPH_BASE}/teams/{self.team_id}/channels/{self.channel_id}"
            f"/filesFolder/content?@microsoft.graph.conflictBehavior=rename"
        )
        with open(file_path, "rb") as fh:
            resp = requests.put(
                f"{GRAPH_BASE}/teams/{self.team_id}/channels/{self.channel_id}"
                f"/filesFolder:/{file_path.name}:/content",
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=fh,
                timeout=120,
            )
        resp.raise_for_status()
        file_info = resp.json()

        # 2. Post a message linking to the file
        msg_url = (
            f"{GRAPH_BASE}/teams/{self.team_id}/channels/{self.channel_id}/messages"
        )
        body = {
            "body": {
                "contentType": "html",
                "content": (
                    f"{self.message}<br/>"
                    f'<a href="{file_info.get("webUrl", "")}">{file_path.name}</a>'
                ),
            }
        }
        resp = requests.post(msg_url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        logger.info("[teams] Uploaded %s to channel %s", file_path.name, self.channel_id)
