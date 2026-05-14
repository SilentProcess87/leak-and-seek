import os
from pathlib import Path

# Set env vars inline for testing
os.environ["WETRANSFER_RECIPIENT_EMAIL"] = "monitor@mailslurp.biz"
os.environ["WETRANSFER_SENDER_EMAIL"] = "your-email@example.com"
os.environ["WETRANSFER_HEADLESS"] = "false"  # watch the browser

from handlers.wetransfer_handler import WeTransferHandler

handler = WeTransferHandler({"message": "Test transfer"})
assert handler.validate_credentials(), "Missing env vars"

# Point to any small test file
handler.transfer(Path("inbox/test.txt"))