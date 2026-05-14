# 🕵️ Leak-and-Seek

> A Playwright + Python test harness for **Data Loss Prevention (DLP)** detectors. We hide sensitive data inside realistic files, push it through a dozen real-world transfer channels (Slack, Teams, OneDrive, Dropbox, Box, SFTP, WeTransfer, Telegram, WhatsApp, Zoom, …), and see if the DLP product on the other side actually catches it.

If your DLP can't find it, **you lose**. If it does, **everybody wins**.

---

## 🎯 What this project solves

DLP vendors all claim to catch leaks. Proving it requires:

1. **Realistic decoy data** that matches the patterns the detectors are trained on (AWS keys, PII, PHI, PCI, GDPR fields, financial records, etc.).
2. **Multiple egress channels** to make sure the policy works on Slack just as well as it does on SFTP.
3. **Repeatable, automatable triggers** so you can re-run the test plan after every policy change.

This repo gives you all three.

---

## 🗂️ Project structure

```text
.
├── detectors_profile_test_files/   ← Realistic decoy files by detector category
│   ├── developer_secrets/          ← Fake API keys, RSA keys, tokens
│   ├── financial/                  ← Wire instructions, portfolio summaries
│   ├── pci/                        ← Card numbers, POS dumps
│   ├── phi/                        ← Patient records, clinical trials
│   ├── pii_gdpr/                   ← EU customer data, HR exports
│   └── sensitive/                  ← Audit reports, executive briefings
│
├── file_transfer/                  ← Python "leaker" – pushes files to every channel
│   ├── handlers/                   ← One module per destination (slack, teams, ...)
│   ├── inbox/                      ← Drop files here, watcher picks them up
│   ├── config.yaml                 ← Routing rules (pattern → handlers)
│   ├── .env.example                ← Credential template (copy to .env)
│   ├── main.py                     ← Watcher entrypoint
│   ├── seed_inbox.py               ← Copies random decoy files into inbox/
│   └── requirements.txt            ← Python deps
│
├── tests/                          ← Playwright UI test specs
│   └── example.spec.ts
├── playwright.config.ts            ← Playwright projects (Chromium / Firefox / WebKit)
├── package.json                    ← Node deps for Playwright
└── .github/workflows/playwright.yml  ← CI: runs Playwright on push / PR
```

---

## ⚠️ Important: about the test files

`detectors_profile_test_files/` intentionally contains **fake-but-realistic-looking** secrets, card numbers, patient data, and PII. They are decoys designed to trip DLP detectors.

- They are **NOT real credentials.** They never were.
- Some look real enough that GitHub's push protection and other secret scanners will scream. That's the point — those scanners use the same regex families as DLP detectors.
- **Do not** reuse these strings as actual credentials anywhere. **Do not** strip them from this repo — that defeats the purpose.

---

## 🚀 Quick start

### Prerequisites

- **Node.js** 18+ (for Playwright)
- **Python** 3.11+ (for the file-transfer leaker)
- A DLP product positioned between this machine and the outbound channels you care about

### 1. Clone & install

```powershell
git clone https://github.com/SilentProcess87/leak-and-seek.git
cd leak-and-seek

# Node deps (Playwright)
npm install
npx playwright install --with-deps

# Python deps (file-transfer leaker)
pip install -r file_transfer/requirements.txt
```

### 2. Configure credentials

```powershell
copy file_transfer\.env.example file_transfer\.env
# Open file_transfer\.env in your editor and fill in only the channels you want to test.
# You do NOT need every credential — handlers with missing creds are skipped.
```

A handler with invalid/missing credentials is logged as a warning and skipped. You can start with just Slack and add more later.

### 3. Customise routing (optional)

`file_transfer/config.yaml` maps filename patterns to destination handlers. Defaults route `*.txt` to **all** services — perfect for DLP testing because every decoy file is a `.txt`. Trim or extend as you like:

```yaml
rules:
  - name: txt_all_services
    pattern: "*.txt"
    handlers:
      - type: box
      - type: dropbox
      - type: onedrive
      - type: wetransfer
      - type: slack
        message: "DLP test file detected"
```

Rules are evaluated top-down, first-match-wins.

---

## 🧪 Running the leak tests

### Option A — full automation

```powershell
# Terminal 1: start the watcher
python file_transfer/main.py

# Terminal 2: drop random decoys into the inbox
python file_transfer/seed_inbox.py -n 5 -d 3
#   -n 5   → copy 5 random decoy files
#   -d 3   → 3 seconds between each copy
```

The watcher detects each new file and fans it out to every channel matched by the rule. Watch your DLP console light up.

### Option B — manual

Just drop any file (or one of the decoys from `detectors_profile_test_files/`) into `file_transfer/inbox/` while `main.py` is running.

---

## 🌐 Playwright tests

The `tests/` folder hosts Playwright specs (UI / browser-based exfiltration paths, WeTransfer, etc.). Run them with:

```powershell
# Headless, all browsers
npx playwright test

# Single browser, headed
npx playwright test --project=chromium --headed

# HTML report
npx playwright show-report
```

Defaults from `playwright.config.ts`:
- Three projects: **Chromium**, **Firefox**, **WebKit**
- Trace recording on first retry
- Tests run in parallel (`fullyParallel: true`)
- On CI: 2 retries, 1 worker

The included `.github/workflows/playwright.yml` runs the suite on every push / PR to `main` and uploads the HTML report as an artifact.

---

## 📡 Supported transfer handlers

| Handler      | What it does                                       | Credentials needed                              |
| ------------ | -------------------------------------------------- | ----------------------------------------------- |
| `slack`      | Uploads the file to a Slack channel/DM             | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`              |
| `teams`      | Posts a file to a Microsoft Teams channel          | `TEAMS_*` (Azure AD app)                        |
| `whatsapp`   | Sends the file via Twilio WhatsApp API             | `TWILIO_*`, `WHATSAPP_*`                        |
| `telegram`   | Sends the file via Telegram Bot API                | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`        |
| `zoom`       | Shares the file in a Zoom Chat channel             | `ZOOM_*` (Server-to-Server OAuth)               |
| `onedrive`   | Copies into the local OneDrive sync folder         | `ONEDRIVE_SYNC_FOLDER` (path only)              |
| `box`        | Copies into the local Box Drive sync folder        | `BOX_SYNC_FOLDER` (path only)                   |
| `dropbox`    | Copies into the local Dropbox sync folder          | `DROPBOX_SYNC_FOLDER` (path only)               |
| `local_copy` | Copies to another local/network folder             | `LOCAL_COPY_DEST` (path only)                   |
| `sftp`       | Uploads via SFTP to a remote server                | `SFTP_HOST`, `SFTP_USERNAME`, `SFTP_PASSWORD`/key |
| `wetransfer` | Sends via WeTransfer (Playwright + MailSlurp)      | `WETRANSFER_*`, `MAILSLURP_API_KEY`             |

Missing credentials? The handler self-skips. No need to comment out config entries.

---

## 🔌 Adding a new handler

1. Create `file_transfer/handlers/my_handler.py` extending `BaseHandler`.
2. Implement `transfer(file_path)` and `validate_credentials()`.
3. Register it in `file_transfer/handlers/__init__.py` → `HANDLER_MAP`.
4. Reference it from `config.yaml` with `type: my_handler`.

See any of the existing handlers (e.g. `slack_handler.py`) for the pattern.

---

## 🛠️ Useful commands cheatsheet

```powershell
# Install
npm install
pip install -r file_transfer/requirements.txt
npx playwright install --with-deps

# Run the watcher
python file_transfer/main.py

# Seed N random decoys
python file_transfer/seed_inbox.py -n 3 -d 2

# Run all Playwright tests
npx playwright test

# Open last Playwright report
npx playwright show-report
```

---

## 🧯 Troubleshooting

- **"All rules were skipped (credential issues)"** — none of the handlers in `config.yaml` had valid credentials in `.env`. Fill in at least one channel.
- **WeTransfer test hangs** — set `WETRANSFER_HEADLESS=false` and `WETRANSFER_DEBUG=true` in `.env` to watch the browser run.
- **`SLACK_BOT_TOKEN` rejected** — make sure the token starts with `xoxb-` (bot token, not user token) and the bot is invited to the target channel.
- **Watcher doesn't pick up new files on Windows network shares** — watchdog has spotty support for SMB. Use a local folder for `WATCH_FOLDER`.

---

## 📜 License

ISC — see `package.json`. Use at your own risk; this project is built for **internal lab / training environments**.

---

## 🤝 Contributing

PRs welcome — especially new handlers (Egnyte, ShareFile, S3, GCS, …) and new detector categories (source code leaks, biometric data, ITAR). Please don't add real credentials, and remember: every new decoy file is another chance for your DLP to prove itself.
