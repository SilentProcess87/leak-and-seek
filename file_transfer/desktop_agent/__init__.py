"""AI-powered desktop agent for DLP-visible file uploads.

Uses Anthropic Claude Computer Use to drive real GUI interactions
(mouse, keyboard, file dialogs) so that endpoint DLP agents can
detect and inspect the transfers.
"""

from .agent import DesktopAgent  # noqa: F401
