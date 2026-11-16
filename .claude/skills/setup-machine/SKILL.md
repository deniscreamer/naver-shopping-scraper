---
name: setup-machine
description: Bring a new Mac to "ready to work" or find why nothing starts: the venv and requirements, Google Chrome, .env (names only), the adapter in the operator's Chrome, server/run.py, /health, and scripts/check_setup.py (--live prints READY). Use on a fresh machine, after a clone or a Python / Chrome / pip upgrade, when the server will not start, /health says "extension" disconnected or off, check_setup prints FAIL or NOT READY, or the owner says "настрой машину", "новый мак", "ничего не запускается", "сервер не стартует", "расширение не подключается".
---

# Set up a machine, or fix "nothing starts"

`SETUP.md` is the procedure and `scripts/check_setup.py` is the definition of ready (R-SETUP-1): follow them, do not
restate them. Never read or print `.env*` or a credentials file; name a variable, the operator fills its value.

| Task | Read |
|---|---|
| What the Mac needs (Python 3.11+, Chrome in /Applications, a warm profile, ports 8000 / 8765) | SETUP.md "0. What the machine needs" |
| The venv, the requirements, the OCR models | SETUP.md "2. Python environment"; server/README.md "Install" |
| `.env`: which variable does what | SETUP.md "3. Per-machine settings (.env)"; `.env.example`; server/README.md "Environment variables" |
| The translation keys (`scripts/translate_keys.py install`, `check`) | SETUP.md "3. Per-machine settings (.env)" |
| Load or reload the adapter in the operator's Chrome | SETUP.md "5. Install the browser adapter into the operator's Chrome"; extension/README.md "Install (once)" |
| Start the server, port, bind address, the Chrome window | SETUP.md "6. Start the server and connect"; server/README.md "Run", "macOS" |
| `connected` / `disconnected` / `off` | server/docs/EXTENSION.md "How to use" step 2 |
| Package versions known to work; temp profiles after Ctrl+C | server/docs/KNOWN_ISSUES.md "K-17 Unpinned dependencies", "K-20 No shutdown hook: temp profiles survive Ctrl+C" |
| A new requirement (env var, package, port, file) | DEVELOPMENT_RULES.md "R-SETUP: environment and setup"; SETUP.md "Keep the checklist current"; skill `server-change` |

Procedure, from the repo root (stop at the first FAIL and fix it):
1. `python3 --version` (3.11+), `ls "/Applications/Google Chrome.app"`, `git branch --show-current` (`develop`).
2. `python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt -r scripts/requirements.txt`
   (every install is an upgrade: K-17). `patchright install` is not needed.
3. `cp .env.example .env` only if `.env` is missing (test with `ls`, never `cat`); usually every value stays empty.
4. `scripts/check.sh` (offline: server suite, scripts suite, mypy; all pass).
5. `.venv/bin/python scripts/check_setup.py --no-server` (local rows only, no network).
6. The adapter: the operator loads `extension/` unpacked (SETUP.md section 5 gives the message to send them).
7. `.venv/bin/python server/run.py` in its own terminal or a background task; then `curl -s localhost:8000/health`.
8. `.venv/bin/python scripts/check_setup.py` (adds the server, the adapter, bridge port 8765), then, only when the
   task allows the network, `--live`: one `/products/count` over plain HTTP, one `/products/details` through the
   server's Chrome, and a Shopify token minted per app (read-only checks). `--notify` adds a test POST to
   `NAVER_NOTIFY_WEBHOOK`. Done = the last line `READY: 0 fail, N warn`; exit code 1 on any FAIL.

What a row means (`check_setup.py` prints OK / WARN / FAIL; WARNs never block READY):
- `python >= 3.11` / `packages` FAIL: rebuild the venv with a newer `python3` (step 2). `curl_cffi 0.16.x` WARN: reinstall the pin.
- `Google Chrome installed` FAIL: Chrome is not in /Applications (or `PATCHRIGHT_EXECUTABLE` points elsewhere).
- `.env` WARN: missing, defaults in use: fine. `SHOP_STORE` FAIL: an unknown store id in that variable.
- `Pillow with WebP` / `tenacity` FAIL: reinstall `scripts/requirements.txt`. `OCR` WARN: models not fetched yet
  (SETUP.md section 2 command). `translation` WARN: no key file or one provider only (`translate_keys.py check`).
- `Shopify shop check` / `Shopify publication` WARN: the credentials file is not set up; only example_99 and
  publication need it, and its path comes from the operator.
- `API server reachable` FAIL: start `server/run.py`; WARN with two versions: restart the server on this checkout.
  A port in use: `lsof -nP -iTCP:8000 -sTCP:LISTEN` (or `PORT=...`; scripts then need `NAVER_API_URL`).
- `browser extension connected` FAIL `disconnected`: Chrome closed or adapter not loaded or not reloaded; wait ~30 s.
  `off`, or `bridge port 8765` FAIL: the bridge did not start (port 8765 taken, `lsof -nP -iTCP:8765`, or
  `websockets` missing); the server log says `extension bridge not started`.
- `Naver over plain HTTP` 418/429/502: this IP is refused: wait, or the operator sets `NAVER_SHOPPING_PROXY`.
  `Naver through the server Chrome` FAIL: read the status with skill `api-error-triage`; never retry a wall in a loop.

Needs the operator: any password, key or webhook value (they paste it into `.env` or the key file themselves); the
clicks in `chrome://extensions`; a captcha or a cold Chrome profile (browse naver.com once); repo access. No store
action belongs to setup; anything that publishes or changes products waits for the owner (scripts/OWNER_RULES.md).
