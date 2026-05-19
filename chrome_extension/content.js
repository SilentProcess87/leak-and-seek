/**
 * DLP Simulator - WeTransfer Upload Extension
 *
 * Triggered when the URL hash contains: #dlp-upload:<base64_json>
 * where the JSON has: { file_path, recipient, sender, title }
 *
 * The Python app opens:
 *   https://wetransfer.com#dlp-upload:eyJmaWxlX3BhdGgiOi4uLn0=
 *
 * This content script:
 *   1. Reads the hash params
 *   2. Clicks "Add files" to open the native file picker (DLP-visible)
 *   3. Fills "Email to" with recipient
 *   4. Fills "Title" field
 *   5. Clicks "Transfer"
 *
 * The file picker is native OS dialog — DLP agents WILL see it.
 */

(function () {
  "use strict";

  const PREFIX = "#dlp-upload:";

  function parseParams() {
    const hash = window.location.hash;
    if (!hash.startsWith(PREFIX)) return null;
    try {
      const b64 = hash.slice(PREFIX.length);
      const json = atob(b64);
      return JSON.parse(json);
    } catch (e) {
      console.error("[DLP Extension] Failed to parse hash params:", e);
      return null;
    }
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function log(msg) {
    console.log(`[DLP Extension] ${msg}`);
  }

  // Find an element by various selectors, retrying until found or timeout
  async function waitFor(selectors, timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) return el;
      }
      await sleep(500);
    }
    return null;
  }

  async function run(params) {
    log("Starting WeTransfer upload automation...");
    log(`Recipient: ${params.recipient}`);
    log(`Title: ${params.title || "DLP Test File"}`);

    // Wait for page to fully load
    await sleep(3000);

    // Step 1: Click "Add files" button to open the native file picker
    // WeTransfer uses various selectors for this button
    const addFilesBtn = await waitFor([
      'button[data-testid="upload-file-button"]',
      'input[data-testid="file-input"]',
      'input[type="file"]',
      '.uploader__sources button:first-child',
      'button:has(> svg)',  // the + icon button
    ]);

    if (addFilesBtn) {
      if (addFilesBtn.tagName === "INPUT" && addFilesBtn.type === "file") {
        // It's a file input — we can't set its value (security), but we can
        // click it to open the native file picker. The user/pyautogui will
        // need to type the path in the dialog.
        log("Found file input — clicking to open file picker...");
        addFilesBtn.click();
      } else {
        log("Found 'Add files' button — clicking...");
        addFilesBtn.click();
      }
    } else {
      log("WARNING: Could not find 'Add files' button. Trying click on area...");
      // Click the general area where the button should be
      const panel = document.querySelector('.uploader') ||
                    document.querySelector('[class*="upload"]');
      if (panel) panel.click();
    }

    // Wait for file to be selected (pyautogui handles the file picker dialog)
    log("Waiting for file selection via native dialog (pyautogui will handle this)...");
    await sleep(8000);

    // Step 2: Fill "Email to" field
    const emailField = await waitFor([
      'input#autosuggest',
      'input[name="autosuggest"]',
      'input[placeholder*="Email"]',
      'input[placeholder*="email"]',
    ]);

    if (emailField && params.recipient) {
      log(`Filling 'Email to' with: ${params.recipient}`);
      emailField.focus();
      emailField.value = params.recipient;
      emailField.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(500);
      // Press Enter to confirm the email chip
      emailField.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
      );
      await sleep(1000);
    }

    // Step 3: Fill "Title" / "Message" field
    const titleField = await waitFor([
      'input[name="title"]',
      'textarea#message',
      'textarea[name="message"]',
      'input[placeholder*="Title"]',
      'input[placeholder*="title"]',
    ]);

    if (titleField) {
      const title = params.title || "DLP Test File";
      log(`Filling title/message with: ${title}`);
      titleField.focus();
      titleField.value = title;
      titleField.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(500);
    }

    // Step 4: Click "Transfer" button
    const transferBtn = await waitFor([
      'button[data-testid="uploaderForm-transfer-button"]',
      'button.transfer__button',
      'button:has-text("Transfer")',
    ]);

    if (transferBtn) {
      log("Clicking 'Transfer' button...");
      transferBtn.click();
    } else {
      // Fallback: find any button with "Transfer" text
      const allButtons = document.querySelectorAll("button");
      for (const btn of allButtons) {
        if (btn.textContent.trim().toLowerCase() === "transfer") {
          log("Found Transfer button by text — clicking...");
          btn.click();
          break;
        }
      }
    }

    log("WeTransfer automation complete. File picker was native (DLP-visible).");

    // Clean up the hash so the extension doesn't re-trigger on refresh
    window.location.hash = "";
  }

  // Check on load
  const params = parseParams();
  if (params) {
    run(params);
  }

  // Also watch for hash changes (in case the page was already loaded)
  window.addEventListener("hashchange", () => {
    const p = parseParams();
    if (p) run(p);
  });
})();
