"""Task definitions for each target service.

Each task has:
- A **prompt template** used when running in AI mode (Claude Computer Use).
- An optional **scripted function** for well-known flows that don't need
  vision-based reasoning (faster, more reliable, DLP-visible).

The ``get_task()`` factory returns the right task object for a given
``app`` name from the handler config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .actions import scripted_slack_upload

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """A single desktop-agent task."""

    app: str
    prompt: str
    # If set, the agent will skip Claude Computer Use and run this
    # function directly — much faster for well-known app flows.
    scripted_fn: Callable[..., None] | None = None
    scripted_kwargs: dict[str, Any] = field(default_factory=dict)


# ── Prompt templates ───────────────────────────────────────────────
# Each prompt tells Claude exactly what to do on the desktop.
# Placeholders are filled by ``get_task()``.

_SYSTEM_PREAMBLE = (
    "You are controlling a Windows desktop. Execute the task below by interacting "
    "with the real GUI. Use the file picker dialog or drag-and-drop to upload files "
    "so that the endpoint DLP agent can inspect the transfer. "
    "IMPORTANT: Do NOT navigate away from the target application. "
    "After uploading, if a DLP popup appears, click the confirm/allow button. "
    "Say 'task complete' when done.\n\n"
)

_SLACK_PROMPT = (
    "Open the Slack desktop app from the Windows Start menu. "
    "Wait for Slack to fully load. "
    "Press Ctrl+K to open the channel switcher. "
    "Type '{channel}' and press Enter to navigate to the channel. "
    "Press Ctrl+U to open the file upload dialog. "
    "In the file picker, navigate to and select '{file_path}'. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Then press Enter to send the file."
)

_TEAMS_PROMPT = (
    "Open Chrome and navigate to {url}. "
    "Log in if needed. Navigate to team '{team}', channel '{channel}'. "
    "Click the attach/paperclip button below the message input. "
    "Click 'Upload from my computer'. "
    "In the file picker, navigate to and select '{file_path}'. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Add the message '{message}' and click Send."
)

_TELEGRAM_PROMPT = (
    "Open Chrome and navigate to https://web.telegram.org. "
    "Find and click on chat '{chat}'. "
    "Click the paperclip/attachment icon. "
    "Click 'File' in the popup menu. "
    "In the file picker, select '{file_path}'. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Click Send."
)

_WHATSAPP_PROMPT = (
    "Open Chrome and navigate to https://web.whatsapp.com. "
    "Wait for QR code scan or session to load. "
    "Find and click on contact or group '{contact}'. "
    "Click the paperclip/attachment icon. "
    "Click 'Document'. "
    "In the file picker, select '{file_path}'. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Click Send."
)

_GMAIL_PROMPT = (
    "Open Chrome and navigate to https://mail.google.com. "
    "Click 'Compose' to start a new email. "
    "In the 'To' field, type '{recipient}'. "
    "In the subject, type 'File: {file_name}'. "
    "Click the attach files button (paperclip icon at the bottom). "
    "In the file picker, select '{file_path}'. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Click Send."
)

_GENERIC_PROMPT = (
    "Open Chrome and navigate to {url}. "
    "Upload the file '{file_path}' through the web UI. "
    "Use the file picker dialog to select the file. "
    "If a DLP/security popup appears, click the confirm or allow button. "
    "Confirm the upload is complete."
)


# ── Task factory ───────────────────────────────────────────────────

def get_task(
    app: str,
    file_path: str | Path,
    handler_config: dict[str, Any],
) -> Task:
    """Build a :class:`Task` for the given *app* and config values.

    Parameters
    ----------
    app:
        One of ``slack``, ``teams``, ``telegram``, ``whatsapp``,
        ``gmail``, or any URL (treated as generic).
    file_path:
        Absolute path to the file to upload.
    handler_config:
        The per-handler dict from ``config.yaml``.
    """
    file_path = str(Path(file_path).resolve())
    file_name = Path(file_path).name
    message = handler_config.get("message", "")

    if app == "slack":
        channel = handler_config.get("channel", os.getenv("SLACK_CHANNEL", "general"))
        prompt = _SYSTEM_PREAMBLE + _SLACK_PROMPT.format(
            channel=channel, file_path=file_path,
        )
        return Task(
            app=app,
            prompt=prompt,
            # Use the scripted flow by default — faster & battle-tested
            scripted_fn=scripted_slack_upload,
            scripted_kwargs={"channel": channel, "file_path": file_path},
        )

    if app == "teams":
        url = handler_config.get("url", os.getenv("TEAMS_WEB_URL", "https://teams.microsoft.com"))
        team = handler_config.get("team", "")
        channel = handler_config.get("channel", "General")
        prompt = _SYSTEM_PREAMBLE + _TEAMS_PROMPT.format(
            url=url, team=team, channel=channel,
            file_path=file_path, message=message,
        )
        return Task(app=app, prompt=prompt)

    if app == "telegram":
        chat = handler_config.get("chat", os.getenv("TELEGRAM_CHAT_ID", ""))
        prompt = _SYSTEM_PREAMBLE + _TELEGRAM_PROMPT.format(
            chat=chat, file_path=file_path,
        )
        return Task(app=app, prompt=prompt)

    if app == "whatsapp":
        contact = handler_config.get("contact", "")
        prompt = _SYSTEM_PREAMBLE + _WHATSAPP_PROMPT.format(
            contact=contact, file_path=file_path,
        )
        return Task(app=app, prompt=prompt)

    if app == "gmail":
        recipient = handler_config.get("recipient", "")
        prompt = _SYSTEM_PREAMBLE + _GMAIL_PROMPT.format(
            recipient=recipient, file_path=file_path, file_name=file_name,
        )
        return Task(app=app, prompt=prompt)

    # Generic — treat ``app`` as a URL or use the ``url`` config key
    url = handler_config.get("url", app)
    prompt = _SYSTEM_PREAMBLE + _GENERIC_PROMPT.format(
        url=url, file_path=file_path,
    )
    return Task(app=app, prompt=prompt)
