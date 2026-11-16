---
name: extension
description: The owner's Chrome adapter (extension/, the bridge ws://127.0.0.1:8765) behind /products/specs, /products/page, /listings and /listing-tabs: install or reload it, read /health `extension` (connected / disconnected / off), a held listing tab or a dead scroll's tab, the product page read, what a job does when the extension drops (job.py wait_service, RECONNECT_S), its messages and errors. Use for "расширение не подключено", "extension disconnected", "перезагрузи расширение", "Chrome закрыт", "вкладка листинга висит", "adapter busy", "listing tab gone", or when a job prints `waiting up to 15 min for the server and the extension`.
---

# The Chrome adapter (extension)

The adapter is a dumb executor in the owner's everyday Chrome; every decision is in `server/ext_*.py` (R-EXT-2).
It runs as the owner (their IP and cookies): a burst or a retried wall can ban their whole network.

| Task | Doc "Section" |
|---|---|
| Install once, reload after a change in `extension/`, the ops, what Chrome shows | `extension/README.md` "Install (once)", "Ops", "Safety" |
| Connect, call, read an answer | `server/docs/EXTENSION.md` "How to use", "Run" |
| The listing walk, the product page read, the held tab | EXTENSION.md "How it works", "Product page specs (`/products/specs`)", "Held listing tab (`/listing-tabs`)" |
| Captcha, ban page, the worker restarted, fragile points | EXTENSION.md "Effects and limits" (**Captcha**) |
| Routes, params, status codes, client policy | `server/docs/ENDPOINTS.md` "Errors (`routes.call`)", "Held listing tabs (beta): `/listing-tabs`", "`GET /captcha`: the captcha the adapter waits on" |
| A job's lines about the extension or the tab | `scripts/JOB_AGENT.md` "What stops, and who acts", "4. Stop and resume" |
| Any error body | skill `api-error-triage` |
| Changing the adapter or `ext_*.py` | skill `server-change`; DEVELOPMENT_RULES "R-EXT: the extension transport (beta)" |

## Procedure (read only)

1. `curl -s localhost:8000/health` -> `extension` (`listing_jobs.extension_status`):
   - `connected`: go on. Which adapter version: the server log's `ext-bridge: extension connected (v<x>)`
     against `"version"` in `extension/manifest.json` (and `VERSION` in `background.js`).
   - `disconnected`: Chrome closed or the adapter not loaded; a started server is found within ~30 s (an alarm).
     Ask the owner to open Chrome, or (after a change in `extension/`) to reload the card in `chrome://extensions`.
   - `off`: the bridge did not start (log `listing-jobs: extension bridge not started: ...`: port 8765 taken, e.g.
     by `server/ext_listing.py` run by hand); restart `server/run.py`. No answer at all: the server is down.
2. Who holds the adapter (one user at a time): `.venv/bin/python scripts/job.py status`; a 409 names
   `listing tab <id>` or a listing job. A tab left by a dead scroll (no `job.py scroll` running; its `job.json` `tab`):
   `curl -X DELETE localhost:8000/listing-tabs/<id>` (idempotent), or restart the server.
3. A pending captcha: `.venv/bin/python scripts/captcha_watch.py --once` (or `GET /captcha`): relay the question to
   the owner at once; never answer, screenshot or type into it (OWNER_RULES "3. Never").

## What a job does when the extension drops (`scripts/job.py`)

- A 503 `the browser extension is not connected ...` (an open, a read, a tab call) or no server: `wait_service`
  prints `<why>: waiting up to 15 min for the server and the extension`, polls `/health` every 30 s
  (`RECONNECT_WAIT_S`, `RECONNECT_S` = 900); `back after N s` goes on; else `STOP ... for 15 min`. You: ask the owner
  to open Chrome / start the server; once back, resume (`job.py run`, or `job.py scroll --job <id>`).
- Dropped mid-read: the read answers `adapter error: ...`: 120 s, twice, then the product is `failed` and retried at
  the end. Scroll: the tab call answers 410, `the listing tab is gone after batch N ...: a new one in S s` (event
  `reopen`); 3 losses in 60 min stop the run (tell the owner).
- An adapter reload or Chrome update mid-run loses the adapter's tab list: the run stops with an adapter error or
  410; the old listing tab stays open in Chrome and the owner closes it.

## Needs the owner's word

Resume after any `wall:` (ban page, refused batch, stall, login gate twice) or a `STOP` the JOB_AGENT table hands
to them, with a small count after a captcha or ban in 24 h; installing, reloading or closing anything in their
Chrome (they do it). During a job: no browser, extension or computer-use tools on Naver, no code edits.
