"""Core agent loop for AI-driven desktop automation.

Two execution modes:
1. **Scripted** — For apps with a known scripted flow (e.g. Slack native
   keyboard shortcuts from ``SlackNative.py``).  Fast, deterministic, and
   DLP-visible.
2. **AI (Claude Computer Use)** — For everything else.  Claude sees
   screenshots, reasons about UI elements, and issues mouse/keyboard
   actions that we execute via ``pyautogui``.

The handler calls ``DesktopAgent.run()`` which picks the right mode
automatically based on whether the task has a ``scripted_fn``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import anthropic

from .actions import check_and_handle_dlp_popup, execute_computer_action
from .screen import TARGET_HEIGHT, TARGET_WIDTH, capture_screenshot
from .tasks import Task, get_task

logger = logging.getLogger(__name__)

# Defaults (overridable via env)
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_STEPS = 30
COMPUTER_USE_BETA = "computer-use-2025-01-24"
TOOL_VERSION = "computer_20250124"


class DesktopAgent:
    """Orchestrates a single GUI file-upload task."""

    def __init__(
        self,
        app: str,
        handler_config: dict[str, Any],
    ) -> None:
        self.app = app
        self.handler_config = handler_config
        self.model = os.getenv("DESKTOP_AGENT_MODEL", DEFAULT_MODEL)
        self.max_steps = int(os.getenv("DESKTOP_AGENT_MAX_STEPS", str(DEFAULT_MAX_STEPS)))
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        # Client is only needed for AI mode; defer validation.
        self._client: anthropic.Anthropic | None = None
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, file_path: Path) -> None:
        """Execute the full upload task for *file_path*.

        Automatically chooses scripted mode or AI mode.
        """
        task = get_task(self.app, file_path, self.handler_config)

        if task.scripted_fn is not None:
            logger.info(
                "[agent] Using scripted flow for '%s' (file=%s)",
                task.app, file_path.name,
            )
            task.scripted_fn(**task.scripted_kwargs)
            return

        # AI mode — requires Anthropic key
        logger.info(
            "[agent] Using Claude Computer Use for '%s' (file=%s)",
            task.app, file_path.name,
        )
        self._run_ai_loop(task)

    def has_api_key(self) -> bool:
        """Return True if an Anthropic API key is available."""
        return bool(self._api_key)

    # ------------------------------------------------------------------
    # AI loop (Claude Computer Use)
    # ------------------------------------------------------------------

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is required for AI mode (non-scripted apps). "
                    "Set it in your .env file."
                )
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _run_ai_loop(self, task: Task) -> None:
        """Screenshot → Claude → action → repeat."""
        messages: list[dict[str, Any]] = []

        # Initial screenshot + task prompt
        b64, w, h = capture_screenshot()
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {"type": "text", "text": task.prompt},
            ],
        })

        tool_def = {
            "type": TOOL_VERSION,
            "name": "computer",
            "display_width_px": TARGET_WIDTH,
            "display_height_px": TARGET_HEIGHT,
        }

        for step in range(1, self.max_steps + 1):
            logger.info("[agent] Step %d / %d", step, self.max_steps)

            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=[tool_def],
                messages=messages,
                betas=[COMPUTER_USE_BETA],
            )

            # Process response content blocks
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Check for task completion or tool use
            tool_uses = [
                block for block in assistant_content
                if getattr(block, "type", None) == "tool_use"
            ]
            text_blocks = [
                block for block in assistant_content
                if getattr(block, "type", None) == "text"
            ]

            # Check if Claude says it's done
            for tb in text_blocks:
                if "task complete" in getattr(tb, "text", "").lower():
                    logger.info("[agent] Claude reports task complete at step %d", step)
                    # Final DLP check after completion
                    check_and_handle_dlp_popup()
                    return

            if not tool_uses:
                logger.info("[agent] No tool use in response — assuming done.")
                check_and_handle_dlp_popup()
                return

            # Execute each tool call and build tool_result messages
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                action_input = tu.input
                logger.info("[agent] Action: %s", action_input.get("action", "?"))

                if action_input.get("action") == "screenshot":
                    # Return a fresh screenshot
                    b64, w, h = capture_screenshot()
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                        ],
                    })
                else:
                    # Execute the action on the real desktop
                    execute_computer_action(action_input)

                    # Check for DLP popup after file-related actions
                    action_name = action_input.get("action", "")
                    if action_name in ("click", "key", "type"):
                        # Don't block on every action — just a quick check
                        pass

                    # Take a follow-up screenshot as the tool result
                    import time
                    time.sleep(0.5)
                    b64, w, h = capture_screenshot()
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                        ],
                    })

            messages.append({"role": "user", "content": tool_results})

            # Trim conversation to keep token usage manageable
            # Keep system prompt + last 10 exchanges
            if len(messages) > 22:
                messages = messages[:2] + messages[-20:]

        logger.warning(
            "[agent] Reached max steps (%d) without completion — aborting.",
            self.max_steps,
        )
        # Final DLP check even on timeout
        check_and_handle_dlp_popup()
