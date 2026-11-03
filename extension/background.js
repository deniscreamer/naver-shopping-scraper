// naver-scrap adapter: executes commands from server/ext_bridge.py inside this
// Chrome and answers with plain data. It holds NO site logic: which page to
// open, what to click, when to stop is decided in Python.
//
// Protocol (JSON over ws://127.0.0.1:8765): {id, op, args} -> {id, ok, result | error}.
// Input (click / type / key / scroll) goes through chrome.debugger's Input
// domain, so the page receives trusted events (isTrusted = true); Chrome shows
// its "is debugging this browser" bar while a tab is attached.
// Only tabs this extension opened (or that they opened) can be driven.

const BRIDGE_URL = "ws://127.0.0.1:8765";
const VERSION = "0.4.4";
const KEEPALIVE_MS = 20000;          // an active WebSocket keeps the MV3 worker alive
const MAX_CAPTURES = 300;            // per tab

let ws = null;
const owned = new Set();             // tab ids we may drive
const attached = new Set();          // tab ids with the debugger attached
const captures = new Map();          // tabId -> [{url, status, body, at}]
const mouse = new Map();             // tabId -> {x, y}

// ---- connection -----------------------------------------------------------------

function connect() {
  try { ws = new WebSocket(BRIDGE_URL); } catch (e) { setTimeout(connect, 3000); return; }
  ws.onopen = () => send({ hello: { version: VERSION } });
  ws.onmessage = (e) => handle(e.data);
  ws.onclose = () => { ws = null; setTimeout(() => { if (!ws) connect(); }, 3000); };
  ws.onerror = () => {};
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

setInterval(() => send({ ping: Date.now() }), KEEPALIVE_MS);
connect();
// Chrome stops an idle MV3 worker (~30 s with no bridge to talk to) and its
// reconnect timer dies with it; an alarm wakes the worker every 30 s and
// reconnects, so a bridge started later (run.py) is always found.
chrome.alarms.create("reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => { if (!ws) connect(); });

async function handle(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch (e) { return; }
  if (!msg || !msg.op) return;
  const fn = OPS[msg.op];
  if (!fn) return send({ id: msg.id, ok: false, error: `unknown op ${msg.op}` });
  try {
    const args = msg.args || {};
    if (args.tabId !== undefined && !owned.has(args.tabId)) throw new Error(`tab ${args.tabId} is not ours`);
    send({ id: msg.id, ok: true, result: await fn(args) });
  } catch (e) {
    send({ id: msg.id, ok: false, error: String((e && e.message) || e) });
  }
}

// ---- helpers --------------------------------------------------------------------

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (a, b) => a + Math.random() * (b - a);

function waitComplete(tabId, timeoutMs = 45000) {
  return new Promise((resolve) => {
    const done = (status) => { chrome.tabs.onUpdated.removeListener(on); clearTimeout(t); resolve(status); };
    const on = (id, info) => { if (id === tabId && info.status === "complete") done("complete"); };
    const t = setTimeout(() => done("timeout"), timeoutMs);
    chrome.tabs.onUpdated.addListener(on);
    chrome.tabs.get(tabId).then((tab) => { if (tab.status === "complete") done("complete"); }).catch(() => done("gone"));
  });
}

async function inPage(tabId, func, args = []) {
  const [r] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return r ? r.result : null;
}

async function attach(tabId) {
  if (attached.has(tabId)) return;
  await chrome.debugger.attach({ tabId }, "1.3");
  attached.add(tabId);
}

const cdp = (tabId, method, params) => chrome.debugger.sendCommand({ tabId }, method, params);

async function moveTo(tabId, x, y) {
  const from = mouse.get(tabId) || { x: rand(200, 500), y: rand(150, 350) };
  const steps = Math.round(rand(12, 25));
  for (let i = 1; i <= steps; i++) {
    const k = i / steps;
    await cdp(tabId, "Input.dispatchMouseEvent", {
      type: "mouseMoved", x: from.x + (x - from.x) * k + rand(-1, 1), y: from.y + (y - from.y) * k + rand(-1, 1),
    });
    await sleep(rand(8, 22));
  }
  mouse.set(tabId, { x, y });
}

chrome.tabs.onCreated.addListener((tab) => { if (tab.openerTabId && owned.has(tab.openerTabId)) owned.add(tab.id); });
chrome.tabs.onRemoved.addListener((tabId) => {
  owned.delete(tabId); attached.delete(tabId); captures.delete(tabId); mouse.delete(tabId);
});
chrome.debugger.onDetach.addListener((src) => attached.delete(src.tabId));
// answers copied by capture_main.js -> relay.js, kept per owned tab until `captures` takes them
chrome.runtime.onMessage.addListener((msg, sender) => {
  const id = sender.tab && sender.tab.id;
  if (!msg || !msg.capture || !owned.has(id)) return;
  const list = captures.get(id) || [];
  list.push(msg.capture);
  if (list.length > MAX_CAPTURES) list.splice(0, list.length - MAX_CAPTURES);
  captures.set(id, list);
});


// ---- operations -----------------------------------------------------------------

const OPS = {
  async hello() { return { version: VERSION }; },

  async tab_open({ url }) {
    const tab = await chrome.tabs.create({ url: url || "about:blank", active: true });
    owned.add(tab.id);
    if (url) await waitComplete(tab.id);
    return { tabId: tab.id };
  },

  async tab_close({ tabId }) {
    if (attached.has(tabId)) await chrome.debugger.detach({ tabId }).catch(() => {});
    await chrome.tabs.remove(tabId);
    return true;
  },

  async tabs() {
    const out = [];
    for (const id of owned) {
      const t = await chrome.tabs.get(id).catch(() => null);
      if (t) out.push({ tabId: id, url: t.url, title: t.title, status: t.status, active: t.active });
    }
    return out;
  },

  async wait_load({ tabId, timeoutMs }) { return await waitComplete(tabId, timeoutMs); },

  async page({ tabId, headChars = 20000 }) {
    return await inPage(tabId, (n) => ({
      url: location.href, title: document.title,
      html: document.documentElement ? document.documentElement.outerHTML.slice(0, n) : "",
    }), [headChars]);
  },

  async query({ tabId, selector }) {
    return await inPage(tabId, (sel) => {
      const els = [...document.querySelectorAll(sel)];
      const el = els.find((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }) || els[0];
      if (!el) return { count: 0 };
      const r = el.getBoundingClientRect();
      return { count: els.length, visible: r.width > 0 && r.height > 0, text: (el.innerText || "").slice(0, 200),
               value: el.value, href: el.href, target: el.target, rect: { x: r.x, y: r.y, w: r.width, h: r.height } };
    }, [selector]);
  },

  async click({ tabId, selector }) {
    const box = await inPage(tabId, (sel) => {
      const el = [...document.querySelectorAll(sel)].find((e) => {
        const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
      if (!el) return null;
      el.scrollIntoView({ block: "center", inline: "center" });
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    }, [selector]);
    if (!box) throw new Error(`no visible element for ${selector}`);
    await sleep(rand(250, 600));
    await attach(tabId);
    const x = box.x + box.w * rand(0.35, 0.65), y = box.y + box.h * rand(0.35, 0.65);
    const before = new Set((await chrome.tabs.query({})).map((t) => t.id));
    await moveTo(tabId, x, y);
    await sleep(rand(120, 300));
    await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
    await sleep(rand(60, 140));
    await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
    let newTabId = null;                       // a target=_blank link opens a tab we then own
    for (let i = 0; i < 20 && newTabId === null; i++) {
      await sleep(150);
      const fresh = (await chrome.tabs.query({})).filter((t) => !before.has(t.id) && t.openerTabId === tabId);
      if (fresh.length) { newTabId = fresh[0].id; owned.add(newTabId); }
    }
    return { x: Math.round(x), y: Math.round(y), newTabId };
  },

  async type({ tabId, text, minDelayMs = 90, maxDelayMs = 260 }) {
    await attach(tabId);
    for (const ch of text) {
      await cdp(tabId, "Input.insertText", { text: ch });
      await sleep(rand(minDelayMs, maxDelayMs));
    }
    return true;
  },

  async key({ tabId, key }) {
    const KEYS = { Enter: { code: "Enter", keyCode: 13, text: "\r" }, Escape: { code: "Escape", keyCode: 27 },
                   Tab: { code: "Tab", keyCode: 9 } };
    const k = KEYS[key];
    if (!k) throw new Error(`unsupported key ${key}`);
    await attach(tabId);
    await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyDown", key, code: k.code, windowsVirtualKeyCode: k.keyCode,
                                                 text: k.text, unmodifiedText: k.text });
    await sleep(rand(50, 110));
    await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyUp", key, code: k.code, windowsVirtualKeyCode: k.keyCode });
    return true;
  },

  async scroll({ tabId, dy, x, y }) {
    await attach(tabId);
    const p = { x: x ?? rand(400, 900), y: y ?? rand(300, 600) };
    await moveTo(tabId, p.x, p.y);
    await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseWheel", x: p.x, y: p.y, deltaX: 0, deltaY: dy });
    return true;
  },

  async captures({ tabId, pattern, clear = true }) {
    const list = captures.get(tabId) || [];
    const hit = list.filter((c) => !pattern || c.url.includes(pattern));
    if (clear) captures.set(tabId, list.filter((c) => !hit.includes(c)));
    return hit;
  },

  // Through the debugger (already used for input): needs no <all_urls> / activeTab.
  async screenshot({ tabId }) {
    await attach(tabId);
    const r = await cdp(tabId, "Page.captureScreenshot", { format: "png" });
    return "data:image/png;base64," + r.data;
  },
};
