# server/: operations

The Naver Shopping API: a bottle app on cheroot (16 threads, `run.py`). Search, store pages, brand product pages and
DataLab go over plain HTTP (curl_cffi); the product JSON, reviews, store product lists and catalog reviews run as
in-page fetches inside a real, headed Google Chrome driven by patchright. `/products/details` mixes both.

`server/` is the import root: modules import each other by bare name (`import config`,
`from naver_shopping import api`) and there is no `server/__init__.py`.

Docs: [docs/ENDPOINTS.md](docs/ENDPOINTS.md) (HTTP contract), [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md)
(binding rules), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (how it works), [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)
(inherited defects, dependency risk).

## Install

One venv at the repo root:

```
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
```

The supported platform is macOS (see below). `requirements.txt` bounds only `curl_cffi` (`>=0.16,<0.17`); everything else floats. Last versions verified locally:
patchright 1.64.3, bottle 0.13.4, marshmallow 4.3.1, cheroot 11.1.2, curl_cffi 0.16.3 (Python 3.14 venv; Python
3.14 is not a stated requirement).

## Run

From the repo root (no `cd` needed: Python puts the script's directory, `server/`, first on `sys.path`):

```
.venv/bin/python server/run.py                    # http://localhost:8000
PORT=9000 .venv/bin/python server/run.py
NAVER_SHOPPING_PROXY=http://user:pass@host:port .venv/bin/python server/run.py
```

`cd server && ../.venv/bin/python run.py` works too. Check it is up:

```
curl "http://localhost:8000/health"
curl "http://localhost:8000/products/search?query=raspberry%20pi"
```

## macOS

The server runs natively on macOS; this is the supported setup (verified on Python 3.14, all 11 endpoints live).

- **Google Chrome in /Applications.** The box calls launch the installed Chrome through patchright's `chrome`
  channel (`PatchrightDriver._main`), not patchright's bundled Chromium, so `patchright install` is not needed.
  `PATCHRIGHT_CHANNEL` is honoured on a Mac (it is ignored only inside containers).
- **A real Chrome window opens** on the first box call (product details, reviews, store products, catalog
  reviews), one window per proxy. The first call takes ~10-12 s (Chrome launch + warm-up on a brand store page);
  later calls reuse the warmed window and take well under a second. Leave the window alone while the server runs.
- **No virtual display.** `patchright_driver._ensure_display` starts Xvfb only on Linux without `DISPLAY`;
  on macOS it does nothing. `pyvirtualdisplay` stays in `requirements.txt` but is never imported on a Mac.
- **Throwaway profile.** Every launch gets a fresh profile under the system temp dir (`tempfile.mkdtemp`, prefix
  `patchright-profile-`), removed when Chrome closes; your own Chrome profile is never touched.
- **Identity.** Without a proxy Chrome keeps the Mac's own locale and timezone. With a proxy, the timezone goes to
  the Chrome process as `TZ` and the language as `--accept-lang` (macOS Chrome ignores `--lang` for its UI, which
  does not matter for Naver); see `PatchrightDriver._main`.
- Stop the server with Ctrl+C. There is no shutdown hook: Chrome exits with the patchright driver process, but
  the temp profile directory is not removed (only `close()` removes it). Leftovers are harmless;
  `rm -rf "$TMPDIR"/patchright-profile-*` clears them while the server is stopped (verified 2026-11-01).

Docker/Linux deployment is archived in [../archive/docker/](../archive/docker/README.md) and is not maintained.

## Environment variables

Set them in the shell or in the repo-root `.env` (copy [../.env.example](../.env.example); read by
`config.load_env_file`, the shell wins).

| Variable | Read in | Effect |
|---|---|---|
| `PORT` | `config.PORT` (import time) | Listen port, default 8000. |
| `NAVER_SHOPPING_PROXY` | `config.naver_shopping_proxy` (when a per-thread curl session is built, `fetch._session`), `config.naver_shopping_browser_proxy` (when the box mints a Chrome exit, `fetch._EXITS`) | Set before start; restart to change. One proxy URL for both curl and Chrome. Unset = this machine's IP, which Naver normally answers. With it set, Chrome looks up the exit's geo through the proxy (`config.exit_geo`, ip-api.com) and takes its timezone and language from it. Use a sticky proxy. The module constant `config.NAVER_SHOPPING_PROXY` is read but unused. |
| `PATCHRIGHT_CHANNEL` | `PatchrightDriver._main` | Chrome channel on a host (default `chrome`). Ignored inside a container (`patchright_driver._in_container`), where it is always `chrome`. Empty string opts out of channels (experiments only). |
| `PATCHRIGHT_EXECUTABLE` | `PatchrightDriver._main`, `patchright_driver.chrome_version` | Browser binary; used for launch only when the channel resolves to empty. |
| `PATCHRIGHT_LANG` | `PatchrightDriver.__init__` | Chrome language fallback when the exit profile gives none (i.e. no proxy, or a proxy with no known country). |
| `PATCHRIGHT_DIRECT_HOSTS` | `patchright_driver._DEFAULT_DIRECT_HOSTS` (import time) | Comma list of hosts Chrome reaches directly instead of through the proxy; defaults to Chrome's background-service hosts. Matters only with a proxy. Needs a restart. |
| `PATCHRIGHT_BROWSERFORGE_OS` | `PatchrightDriver._main` | Only used with `browserforge=True`, which `browser_client._launch` never sets: no effect here. |

Not relevant on macOS (read by inherited code, no effect on a Mac): `ENV` and `VM` (`hostenv`, nothing reads the
flags they set), `LOCALAPPDATA` (Windows browser probe), `DISPLAY` (Linux Xvfb), and container detection
(`hostenv.IS_DOCKER` is always False on darwin). All other settings (retries, Chrome slots, box attempts) are
constants in `config.py`.

Default identity without a proxy: curl sends `Accept-Language` for the US (`egress.DIRECT_COUNTRY`), and Chrome
keeps the host's own locale and timezone.

## Tests

Offline (no network, no Chrome), from the repo root; config in `/pyproject.toml` (`testpaths` / `pythonpath` =
`server`):

```
.venv/bin/python -m pytest -q                      # 232 tests
.venv/bin/python -m pytest server/test_import_smoke.py -q
cd server && ../.venv/bin/python -m pytest -q      # also works
```

`test_import_smoke.py` imports every library module (not `run.py` / `main.py`) by its bare name and checks the 30 mounted routes (11 endpoints and 3 `/listings`
routes x 2 prefixes, plus `/` and `/health`).

Live smoke (server running, networked, may launch Chrome); required after any transport or browser change:

```
.venv/bin/python scripts/smoke_endpoints.py        # /health + the 11 Chrome-free endpoints (not /products/specs), sequential
.venv/bin/python scripts/smoke_endpoints.py --base-url http://localhost:9000 --delay 10
```

## main.py

`.venv/bin/python server/main.py` calls `naver_shopping.api` in-process (no server): a search, one product's
details and one keyword rank, validated through the same schemas. It hits Naver and may launch Chrome. Results go
to `output/*.json` relative to the current working directory.

## Listing through your own Chrome (beta)

`search.shopping.naver.com` is read only in your everyday Chrome through the adapter in `extension/`
(install once: [../extension/README.md](../extension/README.md); why: [docs/EXTENSION.md](docs/EXTENSION.md)).

```
curl -X POST "http://localhost:8000/listings?query=...&max_batches=3"   # with run.py running: a listing job
.venv/bin/python server/ext_listing.py "남성 골프채 풀세트" --max-batches 3   # by hand, run.py stopped
```

`/health` shows `"extension": "connected"` once the adapter is connected to the running server.

`NAVER_NOTIFY_WEBHOOK=<url>`: where captcha / stop notices are POSTed (JSON); unset = a macOS notification.
