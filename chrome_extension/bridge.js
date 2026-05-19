/**
 * Bridge between MAIN-world content.js and the service worker.
 *
 * content.js runs in the page's JS context (MAIN world) so it can
 * inject File objects React accepts — but that context has no
 * chrome.* APIs. This script runs in the ISOLATED world (default),
 * has chrome.runtime, and just forwards a CustomEvent on document
 * to the service worker, which closes the tab via chrome.tabs.
 */

document.addEventListener("dlp-close-tab", () => {
  try {
    chrome.runtime.sendMessage({ action: "close_tab" });
  } catch (e) {
    console.error("[DLP Bridge] sendMessage failed:", e);
  }
});
