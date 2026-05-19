"""GUI-based file upload handler using the AI desktop agent.

Delegates to :class:`desktop_agent.DesktopAgent` which drives real
desktop interactions (mouse, keyboard, file dialogs) so that endpoint
DLP agents can detect and inspect the transfers.

Config keys (in ``config.yaml``):
    type: desktop_agent
    app:  slack | teams | telegram | whatsapp | gmail | <url>
    channel: "#general"       # Slack / Teams channel
    team: "My Team"           # Teams team name
    chat: "Contact Name"      # Telegram chat
    contact: "John"           # WhatsApp contact
    recipient: "a@b.com"      # Gmail recipient
    message: "Upload note"    # Optional message text
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import BaseHandler

logger = logging.getLogger(__name__)


class DesktopAgentHandler(BaseHandler):
    name = "desktop_agent"

    # Scripted apps that don't need an Anthropic API key
    _SCRIPTED_APPS = {"slack"}

    def __init__(self, handler_config: dict[str, Any] | None = None) -> None:
        super().__init__(handler_config)
        self.app = self.handler_config.get("app", "")

    # ------------------------------------------------------------------
    def validate_credentials(self) -> bool:
        if not self.app:
            logger.error(
                "[desktop_agent] 'app' must be set in handler config "
                "(e.g. slack, teams, telegram, gmail, or a URL)"
            )
            return False

        # Scripted flows (like Slack native) don't need an API key
        if self.app in self._SCRIPTED_APPS:
            return True

        # AI mode needs an Anthropic key
        if not os.getenv("ANTHROPIC_API_KEY"):
            logger.error(
                "[desktop_agent] ANTHROPIC_API_KEY must be set in .env "
                "for AI mode (app='%s'). Scripted mode is only available "
                "for: %s",
                self.app,
                ", ".join(sorted(self._SCRIPTED_APPS)),
            )
            return False

        return True

    # ------------------------------------------------------------------
    def transfer(self, file_path: Path) -> None:
        from desktop_agent import DesktopAgent

        agent = DesktopAgent(app=self.app, handler_config=self.handler_config)
        agent.run(file_path)
