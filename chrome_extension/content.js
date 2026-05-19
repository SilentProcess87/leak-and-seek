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

  // Simulate typing into a React-controlled input field
  function setReactValue(el, value) {
    // React overrides the native setter, so we need to use the native
    // HTMLInputElement setter and then dispatch events React listens to.
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value"
    )?.set || Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype, "value"
    )?.set;

    if (nativeSetter) {
      nativeSetter.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function run(params) {
    log("Starting WeTransfer upload automation...");
    log(`Recipient: ${params.recipient}`);
    log(`Title: ${params.title || "DLP Test File"}`);

    // Wait for page to fully load
    await sleep(3000);

    // Step 1: Fill "Email to" field FIRST (before file picker opens)
    //   We do this first because once the file picker opens,
    //   pyautogui will paste the file path — we don't want it
    //   landing in the email field.
    const emailField = await waitFor([
      'input#autosuggest',
      'input[name="autosuggest"]',
      'input[placeholder*="Email"]',
      'input[placeholder*="email"]',
    ]);

    if (emailField && params.recipient) {
      log(`Filling 'Email to' with: ${params.recipient}`);
      emailField.focus();
      setReactValue(emailField, params.recipient);
      await sleep(500);
      // Press Enter to confirm the email chip
      emailField.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter", code: "Enter", keyCode: 13, bubbles: true,
        })
      );
      emailField.dispatchEvent(
        new KeyboardEvent("keypress", {
          key: "Enter", code: "Enter", keyCode: 13, bubbles: true,
        })
      );
      await sleep(1000);
    } else {
      log("WARNING: Could not find email field");
    }

    // Step 2: Fill "Title" field
    const titleField = await waitFor([
      'input[name="title"]',
      'textarea#message',
      'textarea[name="message"]',
      'input[placeholder*="Title"]',
      'input[placeholder*="title"]',
    ]);

    if (titleField) {
      const title = params.title || "DLP Test File";
      log(`Filling title with: ${title}`);
      titleField.focus();
      setReactValue(titleField, title);
      await sleep(500);
    }

    // Step 3: Click "Add files" to open native file picker
    //   pyautogui will handle typing the file path in the dialog.
    const addFilesBtn = await waitFor([
      'input[data-testid="file-input"]',
      'input[type="file"]',
      'button[data-testid="upload-file-button"]',
    ]);

    if (addFilesBtn) {
      log("Found upload element — clicking to open file picker...");
      addFilesBtn.click();
    } else {
      // Fallback: click buttons containing "Add files" text
      const allBtns = document.querySelectorAll("button");
      for (const btn of allBtns) {
        if (btn.textContent.toLowerCase().includes("add files")) {
          log("Found 'Add files' button by text — clicking...");
          btn.click();
          break;
        }
      }
    }

    // Wait for pyautogui to handle the file picker dialog
    log("File picker opened — waiting for pyautogui to select file...");
    await sleep(12000);

    // Step 4: Click "Transfer" button
    log("Looking for Transfer button...");
    const allButtons = document.querySelectorAll("button");
    for (const btn of allButtons) {
      const text = btn.textContent.trim().toLowerCase();
      if (text === "transfer") {
        log("Clicking 'Transfer' button...");
        btn.click();
        break;
      }
    }

    log("WeTransfer automation complete.");
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
