/**
 * DLP Simulator - WeTransfer Upload Extension
 *
 * Triggered when the URL hash contains: #dlp-upload:<base64_json>
 * where the JSON has:
 *   { file_name, file_content_b64, recipient, sender, title }
 *
 * The Python app opens:
 *   https://wetransfer.com#dlp-upload:eyJmaWxlX25hbWUiOi4uLn0=
 *
 * This content script:
 *   1. Reads the hash params (file content + metadata)
 *   2. Injects the file directly into <input type="file"> via DataTransfer
 *      (bypasses the OS file picker — Chrome blocks programmatic opens)
 *   3. Fills "Email to" with recipient
 *   4. Fills "Title" field
 *   5. Clicks "Transfer"
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
    // setter and then dispatch events React listens to. The setter must
    // come from the prototype that actually matches the element —
    // calling HTMLInputElement's setter on a <textarea> throws
    // "Illegal invocation".
    const proto =
      el instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : el instanceof window.HTMLInputElement
        ? window.HTMLInputElement.prototype
        : Object.getPrototypeOf(el);
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;

    if (nativeSetter) {
      nativeSetter.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Decode base64 → Uint8Array (binary-safe, unlike TextDecoder).
  function b64ToBytes(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  // Inject a File into an <input type="file"> via DataTransfer.
  // This bypasses the native file picker entirely — Chrome blocks
  // programmatic file-picker opens without user activation, and
  // pyautogui workarounds are unreliable (typed path lands in the
  // wrong field). Setting .files + dispatching "change" is what
  // most React test harnesses use, and WeTransfer's onChange handler
  // reads event.target.files normally.
  async function injectFile(fileName, fileBytes) {
    const fileInput = await waitFor([
      'input[data-testid="file-input"]',
      'input[type="file"]',
    ]);
    if (!fileInput) {
      log("ERROR: No <input type=\"file\"> found on page.");
      return false;
    }

    const file = new File([fileBytes], fileName, {
      type: "application/octet-stream",
    });
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;

    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    fileInput.dispatchEvent(new Event("input", { bubbles: true }));
    log(`Injected ${fileBytes.length} bytes as ${fileName}`);
    return true;
  }

  async function run(params) {
    log("Starting WeTransfer upload automation...");
    log(`Recipient: ${params.recipient}`);
    log(`Title: ${params.title || "DLP Test File"}`);
    log(`File: ${params.file_name}`);

    // Wait for page to fully load
    await sleep(3000);

    // Step 1: Fill "Email to" FIRST.
    //   Doing this before the file injection means the React tree is
    //   still in its empty-form state when we set the value — no
    //   re-mount races, no other inputs around for selectors to
    //   accidentally match.
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
      await sleep(4000);
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
      await sleep(4000);
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
      await sleep(4000);
    }

    // Step 3: Inject the file LAST (before Transfer). Doing it here
    //   means any re-render WeTransfer does on file attach won't wipe
    //   the email or title we just typed.
    if (params.file_content_b64 && params.file_name) {
      const bytes = b64ToBytes(params.file_content_b64);
      log(`Injecting file via DataTransfer (${bytes.length} bytes)...`);
      const ok = await injectFile(params.file_name, bytes);
      if (!ok) {
        log("ERROR: File injection failed — aborting.");
        return;
      }
      // Let WeTransfer's React tree re-render with the file attached.
      await sleep(4000);
    } else {
      log("WARNING: No file content in hash params.");
    }

    // Step 4: Click "Transfer" button
    log("Looking for Transfer button...");
    await sleep(4000);
    let transferBtn = document.querySelector(
      'button[data-testid="uploaderForm-transfer-button"]'
    );
    if (!transferBtn) {
      for (const btn of document.querySelectorAll("button")) {
        if (btn.textContent.trim().toLowerCase() === "transfer") {
          transferBtn = btn;
          break;
        }
      }
    }
    if (transferBtn) {
      log("Clicking 'Transfer' button...");
      transferBtn.click();
    } else {
      log("WARNING: Transfer button not found.");
    }

    // Clear the hash so a refresh doesn't re-trigger the upload.
    window.location.hash = "";

    // Give the upload POST time to start before tearing down the tab —
    // closing too early aborts the in-flight request.
    log("Upload triggered — closing tab in 30s.");
    await sleep(30000);

    // Ask the ISOLATED-world bridge to close us. We can't call
    // chrome.tabs from MAIN world, and window.close() doesn't work
    // for tabs the user (or the OS) opened directly.
    log("WeTransfer automation complete — requesting tab close.");
    document.dispatchEvent(new CustomEvent("dlp-close-tab"));
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
