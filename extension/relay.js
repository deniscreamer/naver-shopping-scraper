// Isolated world: forward captured answers from capture_main.js to the background.
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || !e.data.__naverScrapCapture) return;
  const { url, status, body, at } = e.data;
  chrome.runtime.sendMessage({ capture: { url, status, body, at } }).catch(() => {});
});
