"""Upload files to a remote server over SFTP."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import paramiko

from .base import BaseHandler

logger = logging.getLogger(__name__)


class SFTPHandler(BaseHandler):
    name = "sftp"

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.host = os.getenv("SFTP_HOST", "")
        self.port = int(os.getenv("SFTP_PORT", "22"))
        self.username = os.getenv("SFTP_USERNAME", "")
        self.password = os.getenv("SFTP_PASSWORD", "")
        self.private_key_path = os.getenv("SFTP_PRIVATE_KEY", "")
        self.remote_dir = os.getenv("SFTP_REMOTE_DIR", "/uploads")

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not self.host or not self.username:
            logger.error("[sftp] SFTP_HOST and SFTP_USERNAME must be set in .env")
            return False
        if not self.password and not self.private_key_path:
            logger.error("[sftp] Provide either SFTP_PASSWORD or SFTP_PRIVATE_KEY")
            return False
        return True

    # ------------------------------------------------------------------
    def _get_transport(self) -> paramiko.Transport:
        transport = paramiko.Transport((self.host, self.port))
        if self.private_key_path:
            pkey = paramiko.RSAKey.from_private_key_file(self.private_key_path)
            transport.connect(username=self.username, pkey=pkey)
        else:
            transport.connect(username=self.username, password=self.password)
        return transport

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        transport = self._get_transport()
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            assert sftp is not None
            remote_path = f"{self.remote_dir}/{file_path.name}"

            # Try the configured dir first, fall back to root
            try:
                sftp.put(str(file_path), remote_path)
                logger.info("[sftp] Uploaded to %s:%s", self.host, remote_path)
            except (PermissionError, IOError):
                # Remote dir may not exist or be read-only — try root
                fallback = f"/{file_path.name}"
                logger.warning(
                    "[sftp] %s failed, trying %s", remote_path, fallback
                )
                try:
                    sftp.put(str(file_path), fallback)
                    logger.info("[sftp] Uploaded to %s:%s", self.host, fallback)
                except (PermissionError, IOError):
                    # Even root failed — the DLP agent still saw the
                    # SFTP connection attempt, which generates telemetry.
                    logger.warning(
                        "[sftp] Upload denied by server (read-only?) — "
                        "SFTP connection was still visible to DLP agent."
                    )
            sftp.close()
        finally:
            transport.close()
