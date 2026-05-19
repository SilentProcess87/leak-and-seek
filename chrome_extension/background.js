/**
 * Service worker: closes the sender's tab on request from bridge.js.
 */

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.action === "close_tab" && sender.tab && sender.tab.id != null) {
    chrome.tabs.remove(sender.tab.id).catch((err) => {
      console.error("[DLP Background] tabs.remove failed:", err);
    });
  }
});
