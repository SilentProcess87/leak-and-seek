# DLP Simulator - WeTransfer Chrome Extension

## What it does
Automates WeTransfer file uploads using DOM manipulation instead of fragile screen-coordinate clicking. When the Python simulator opens `wetransfer.com` with a special hash fragment, this extension:

1. Clicks "Add files" to open the **native OS file picker** (DLP-visible)
2. Waits for file selection (pyautogui types the path in the file dialog)
3. Fills the "Email to" field with the recipient
4. Fills the "Title" field
5. Clicks "Transfer"

## Install (one-time setup on lab machine)

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `chrome_extension/` folder
5. The extension appears as "DLP Simulator - WeTransfer Upload"

## How it's triggered

The Python app opens a URL like:
```
https://wetransfer.com#dlp-upload:eyJyZWNpcGllbnQiOiJhQGIuY29tIn0=
```

The hash fragment contains base64-encoded JSON:
```json
{
  "recipient": "monitor@mailslurp.biz",
  "sender": "monitor@mailslurp.biz",
  "title": "DLP Test File",
  "file_path": "C:\\Users\\dlp\\DLPSimulator\\inbox\\test.txt"
}
```

The content script reads this and automates the page.

## Why this approach
- DOM manipulation is 100% reliable regardless of screen resolution or window position
- The file picker is still native OS dialog — DLP agents see it
- No Anthropic API key needed
- Works with any Chrome version
