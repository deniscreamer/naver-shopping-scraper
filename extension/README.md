# extension/: naver-scrap adapter (beta)

A thin Chrome MV3 extension that lets `server/ext_bridge.py` drive the owner's own Chrome. It holds no Naver
logic: it takes `{id, op, args}` over `ws://127.0.0.1:8765` and answers `{id, ok, result | error}`.
Why it exists and how the listing uses it: [server/docs/EXTENSION.md](../server/docs/EXTENSION.md).

## Install (once)

1. Chrome -> `chrome://extensions` -> turn on **Developer mode** (top right).
2. **Load unpacked** -> choose this `extension/` folder.
3. The card "naver-scrap adapter" appears. It connects by itself whenever a bridge runs (an alarm wakes it every
   30 s, so a server started later is found within ~30 s); with no bridge running, Chrome logs
   `ERR_CONNECTION_REFUSED`: harmless.

After any change in this folder: **reload** the card (circular arrow) and check the version.

## Ops

| Op | Does |
|---|---|
| `hello` | version |
| `tab_open {url}` / `tab_close {tabId}` / `tabs` | its own tabs (and the tabs they open) |
| `wait_load {tabId, timeoutMs}` | until the tab's load is complete |
| `page {tabId, headChars}` | url, title, the first `headChars` of the HTML |
| `query {tabId, selector}` | first visible match: rect, text, value, href |
| `click {tabId, selector}` | mouse move + click (debugger input); returns `newTabId` if a tab opened |
| `type {tabId, text}` / `key {tabId, key}` | key-by-key text; Enter / Escape / Tab |
| `scroll {tabId, dy}` | mouse wheel (debugger input) |
| `captures {tabId, pattern}` | the page's own `/ns/v1/` answers copied since the last call |
| `screenshot {tabId}` | PNG data URL (debugger) |

## Safety

- Host permission `*.naver.com` only; only tabs it opened can be driven.
- The bridge listens on 127.0.0.1 and accepts `chrome-extension://` origins only.
- While a tab is driven Chrome shows "naver-scrap adapter started debugging this browser": expected; closing it
  stops the input.
