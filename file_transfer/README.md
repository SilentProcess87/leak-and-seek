# File Transfer Automation

Watches a folder for new files and automatically routes them to one or more destinations:

| Handler        | What it does                              |
|----------------|-------------------------------------------|
| `slack`        | Uploads the file to a Slack channel/DM    |
| `teams`        | Posts a file to a Microsoft Teams channel |
| `whatsapp`     | Sends the file via Twilio WhatsApp API    |
| `telegram`     | Sends the file via Telegram Bot API       |
| `zoom`         | Shares the file in a Zoom Chat channel    |
| `onedrive`     | Copies to the local OneDrive sync folder  |
| `box`          | Copies to the local Box Drive sync folder |
| `dropbox`      | Copies to the local Dropbox sync folder   |
| `local_copy`   | Copies to another local/network folder    |
| `sftp`         | Uploads via SFTP to a remote server       |
| `wetransfer`   | Sends via WeTransfer (Playwright + MailSlurp verification) |

## Quick Start

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create your .env from the template
copy .env.example .env
# → Edit .env and fill in your real credentials

# 3. (Optional) Customise routing rules in config.yaml

# 4. Run
python main.py
```

The script creates the watch folder (default `inbox/`) if it doesn't exist.
Drop a file in there and watch the logs.

## Configuration

### `.env` — credentials & paths

Every service reads its credentials from environment variables defined in `.env`.
See `.env.example` for the full list.

### `config.yaml` — routing rules

```yaml
rules:
  - name: pdf_reports
    pattern: "*.pdf"
    handlers:
      - type: slack
        message: "New PDF report"
      - type: onedrive

  - name: catch_all
    pattern: "*"
    handlers:
      - type: local_copy
```

Rules are evaluated **top-down, first-match-wins**.  
Each rule can trigger multiple handlers in sequence.

### Adding a new handler

1. Create `handlers/my_handler.py` extending `BaseHandler`.
2. Implement `transfer()` and `validate_credentials()`.
3. Register it in `handlers/__init__.py` → `HANDLER_MAP`.
4. Use `type: my_handler` in `config.yaml`.

## Slack Setup

1. Go to https://api.slack.com/apps and create a new app.
2. Under **OAuth & Permissions**, add scopes: `files:write`, `chat:write`.
3. Install to your workspace and copy the **Bot User OAuth Token**.
4. Put the token in `.env` as `SLACK_BOT_TOKEN`.
5. Set `SLACK_CHANNEL` to the channel or user ID.

## Cloud Storage Setup (OneDrive / Box / Dropbox)

No API credentials needed — the desktop clients handle the cloud upload
automatically. Just install each desktop client, sign in, and point the
handler at its local sync folder via `.env`:

- `ONEDRIVE_SYNC_FOLDER` (e.g. `C:\Users\<you>\OneDrive\Uploads`)
- `BOX_SYNC_FOLDER`      (e.g. `C:\Users\<you>\Box\Uploads`)
- `DROPBOX_SYNC_FOLDER`  (e.g. `C:\Users\<you>\Dropbox\Uploads`)

See `README.html` for the full styled documentation including WeTransfer
and all other handlers.
