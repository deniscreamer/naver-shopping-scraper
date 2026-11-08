# SETUP: from a fresh machine to "ready to work"

Written for a coding agent (and humans). **Do every step yourself with your own tools** (shell, file edits, your
browser tools). When a step needs something only the operator can do (a GUI permission, a password, a click inside
their Chrome) and the alternatives below did not work, **stop and ask the operator in this chat**: say which step,
what you tried, and give them the exact clicks or command. Never guess secrets; never enter passwords.

Done = `scripts/check_setup.py --live` prints `READY`.

## 0. What the machine needs

- macOS (the supported platform), `git`, Python **3.11+** (`python3 --version`; else `brew install python@3.13`, or
  ask the operator to install Python).
- **Google Chrome in /Applications**, with the operator's everyday, "warm" profile: a profile that has browsed
  naver.com / shopping.naver.com normally (cookies, history). The listing jobs run inside it. A brand-new profile
  gets captchas; if so, ask the operator to browse naver.com -> 쇼핑 and solve any captcha once.
- Ports free: **8000** (API; another one via `PORT`) and **8765** (browser adapter, fixed).

## 1. Get the code

```sh
git clone https://github.com/deniscreamer/naver-shopping-scraper.git naver-scrap
cd naver-scrap
git checkout develop        # work happens on develop; master = releases
```

If the clone asks for credentials: the repo may be private. Try `gh auth status` / `gh repo clone ...`; if that
fails, ask the operator for access (do not ask for a password in chat; they log in themselves).

## 2. Python environment

```sh
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt -r scripts/requirements.txt
```

The server drives the installed Google Chrome through patchright; `patchright install` is **not** needed.
`scripts/requirements.txt` brings Pillow, which the photo scripts use to write WebP (its macOS wheels include WebP),
and rapidocr + onnxruntime for the optional OCR of description images (`scripts/description_images.py`). Its
Korean models (~15 MB) are downloaded into the rapidocr package by its first run; to fetch them now:

```sh
.venv/bin/python -c "import sys; sys.path.insert(0, 'scripts'); import description_ocr; description_ocr.Engine()"
```

## 3. Per-machine settings (.env)

```sh
cp .env.example .env
```

Every value is optional; each line of [.env.example](.env.example) says what it is, where to get it and gives an
example. Usually all stay empty. Fill only what this machine needs (another port; a proxy if Naver refuses this
IP; a webhook to get captcha notices; `SHOP_STORE` when the saved photos are for a store other than
fairwardgolf). Secrets go only into `.env` (gitignored), never into a commit or the chat.
If a value must come from the operator (proxy credentials, a webhook URL, where the Shopify app's credentials file is), ask them to paste it
into `.env` themselves.

A captcha during a run: the adapter waits `NAVER_CAPTCHA_WAIT_S` (600 s) with the captcha tab in front and the
cursor in the answer field; answer it in Chrome, at the Mac or from a phone through a remote-desktop app (DeskIn,
Chrome Remote Desktop). The run goes on by itself once the captcha is gone. To be told at once, keep
`.venv/bin/python scripts/captcha_watch.py` running in another terminal (or let an agent run it and relay each line).

For the full collection (`scripts/example_99_full_details.py`) two things come from the operator:

- where the store app's credentials file is (client id + secret of the products app, mode 0600, ignored by git;
  fairwardgolf: the naver-harvester's `.env.fairwardgolf`): its path in `.env` as the variable
  `scripts/shop_stores.py` names (`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`), and `chmod 600 .env`. No token is stored: one
  is minted per run. `scripts/check_setup.py --live` then mints one and checks the shop, `read_products` and a first
  product. A store without Shopify values in `shop_stores.py` waits for the operator's domain, shop id, API version
  and namespace;
- the category's package averages in `scripts/category_measures.json` (low / central / high, who approved, when).
  Without a row for the category the run stops and asks for it.

## 4. Offline tests (no network)

```sh
.venv/bin/python -m pytest -q             # server
.venv/bin/python -m pytest scripts -q     # scripts, types, client
```

## 5. Install the browser adapter into the operator's Chrome

The adapter is a folder, loaded unpacked (no store, no build step): [extension/README.md](extension/README.md).

1. In that Chrome: `chrome://extensions` -> **Developer mode** on -> **Load unpacked** -> pick the repo's
   `extension/` folder (absolute path: `$(pwd)/extension`).
2. The card "naver-scrap adapter" shows the version from `extension/manifest.json`.

Try it yourself first if your tools can drive the operator's Chrome or desktop (computer-use / desktop control
with the operator's permission). `chrome://` pages are usually closed to browser-automation tools, and Chrome
ignores `--load-extension` for its stable channel, so this step is often the operator's. Then ask, e.g.:

> Please load the adapter into your Chrome: open chrome://extensions, turn on Developer mode, click
> "Load unpacked" and choose `<absolute path>/extension`. Tell me the version shown on the card.

After any later change in `extension/`, the card must be **reloaded** (circular arrow): ask the operator the same way.

## 6. Start the server and connect

```sh
.venv/bin/python server/run.py            # keep it running (background task / its own terminal)
```

Within ~30 s the adapter connects (an alarm wakes it). Check:

```sh
curl -s http://localhost:8000/health      # "extension": "connected"
```

Still `disconnected` after a minute: ask the operator whether Chrome is open and the card shows no error.

## 7. The checklist

```sh
.venv/bin/python scripts/check_setup.py --live            # add --notify if NAVER_NOTIFY_WEBHOOK is set
```

It also checks the OCR of description images (`OCR (description_images.py)`: rapidocr + onnxruntime installed, the
Korean models downloaded). A WARN there blocks nothing else: install `scripts/requirements.txt` and fetch the models
(section 2) before the first run of `scripts/description_images.py`. Verified versions: KNOWN_ISSUES K-17.

`READY` = done. Each FAIL line says what to fix. `--live` makes one plain-HTTP call and one Chrome call to Naver;
a 418/429/502 there means this IP is refused (wait, or set `NAVER_SHOPPING_PROXY`). Optional end-to-end: run
`scripts/example_07_listing_then_details.py` (one listing batch through the adapter + 3 product details).

## 8. Before coding

Read [AGENTS.md](AGENTS.md), then the binding rules [server/docs/DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md).

## Keep the checklist current

`scripts/check_setup.py` is the definition of "ready". Any change that adds a requirement (an env var, a package,
a service, a port, a file the code needs, a new Chrome/extension condition) adds its check there **and** its line
to `.env.example` / this file, in the same commit (DEVELOPMENT_RULES R-SETUP-1).
