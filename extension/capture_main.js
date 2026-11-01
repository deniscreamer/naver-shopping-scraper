// Page world, document_start: copy the bodies of the page's OWN fetch/XHR
// answers whose URL contains one of PATTERNS, and hand them to relay.js.
// The page still builds and sends every request itself (headers, tokens,
// cursors); this only reads what comes back. No site logic here.
(() => {
  const PATTERNS = ["/ns/v1/"];
  const TAG = "__naverScrapCapture";
  const wanted = (url) => PATTERNS.some((p) => String(url || "").includes(p));
  const post = (url, status, body) => {
    try { window.postMessage({ [TAG]: true, url: String(url), status, body, at: Date.now() }, location.origin); } catch (e) {}
  };

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = res.url || (args[0] && args[0].url) || args[0];
      if (wanted(url)) res.clone().text().then((t) => post(url, res.status, t)).catch(() => {});
    } catch (e) {}
    return res;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__nsUrl = url;
    return origOpen.call(this, method, url, ...rest);
  };
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    if (wanted(this.__nsUrl)) {
      this.addEventListener("loadend", () => {
        try {
          const body = this.responseType === "" || this.responseType === "text" ? this.responseText
            : JSON.stringify(this.response);
          post(this.responseURL || this.__nsUrl, this.status, body);
        } catch (e) {}
      });
    }
    return origSend.apply(this, args);
  };
})();
