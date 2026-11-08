# Known issues

Inherited defects, contradictions, stale references and dependency risk in
`server/`. Each entry was re-checked against the code on 2026-11-01.

**Policy for every entry: do not copy the pattern; fix it only with evidence
and a live A/B** (A/B against the current code on the same exit: step 3 of
"Checklist: changing transport or browser code"; then the live smoke with at
least one curl call and one box call: R-TEST-4; both in
[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)). The current
code is the one observed to fetch Naver data stably; several entries below
are part of that working setup, so "looks wrong" is not enough to change it.
A fix removes its entry in the same commit.

Citations name symbols; `~N` is a line hint only. How the parts fit together
is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Browser box

### K-01 `no_viewport=True` despite a NEVER comment
- **Where:** `PatchrightDriver._main`, comment ~761 vs the launch kwargs ~860.
- **Observed:** the comment says "NEVER no_viewport=True: its window geometry
  is a DataDome tell", but every launch with a channel passes
  `no_viewport=True`. Naver always launches with channel `"chrome"`, so this is
  the path in use.
- **Impact:** the code contradicts its own guidance. Naver works with it
  today; whether removing it helps or hurts on Naver is untested.

### K-02 Image/font blocking on an anti-bot target
- **Where:** `browser_client.BLOCK_RESOURCES`; `PatchrightDriver.__init__`
  comment ~703-710.
- **Observed:** the driver comment calls image/font flag blocking
  "Detectable by WAFs" and meant for pools that never face anti-bot sites.
  Naver lists `"image"` and `"font"` (plus `"media"`).
- **Impact:** a possible fingerprint signal. It works today; change only
  with an A/B.

### K-03 418 is not a refusal inside the browser
- **Where:** `browser_client.REFUSE_STATUSES` = (403, 405, 429, 490);
  `fetch._box_answer`.
- **Observed:** `_box_answer` treats 418 as `NaverBlocked`, but
  `_Browser.fetch_one` does not treat it as a refusal. A 418 answer passes
  through, then raises `NaverBlocked` without closing Chrome or rotating.
- **Impact:** a 418-blocked Chrome stays in use for the next request.

### K-04 Transport failures counted as refusals
- **Where:** `_Browser.fetch_one` (`if not r.status_code and r.error`);
  `_Browser.warm` (goto exception -> `BoxRefused`).
- **Observed:** an in-page fetch that never completed (status 0: network
  error, 30 s abort) and a failed anchor navigation both raise `BoxRefused`,
  the same as a captcha or login wall.
- **Impact:** a network blip closes Chrome and spends a rotation attempt as
  if Naver had refused; logs cannot tell the two apart.

### K-05 No retry for box answer errors
- **Where:** `fetch._box_call`, `fetch._box_answer`, `fetch.BOX_RETRY_STATUSES`.
- **Observed:** `_box_call` retries only `BoxRefused`. `BoxUnavailable`
  (including a `CALL_TIMEOUT` wedge) becomes `NaverUpstreamError` at once.
  `_box_answer` runs after the box call returns, so 418, 5xx and non-JSON
  answers are never retried (status 0 never reaches it: `fetch_one` raises
  `BoxRefused` first, see K-04). The constant `BOX_RETRY_STATUSES`
  (500, 502, 503, 504) is only used to classify; nothing retries on it. The
  `_box_call` docstring ("a box outage is retryable upstream") means the HTTP
  client is expected to retry. The curl path retries 3 times.
- **Impact:** transient backend errors reach the client as 502.

### K-06 Rotation is a no-op with zero or one proxy
- **Where:** `browser_client.ExitPool.rotate`, `config.naver_shopping_browser_proxy`.
- **Observed:** `rotate` calls the mint function again, which re-reads the
  same env value. The `ExitPool` docstring says so.
- **Impact:** a "rotated" retry uses a fresh Chrome and profile on the same
  IP. Only a rotating proxy gives a fresh exit.

### K-07 Idle reaper
- **Where:** `browser_client._browser`, `browser_client.fetch`, `BROWSER_IDLE`.
- **Observed:**
  - the reaper runs only inside `_browser()` and skips the proxy being
    requested; with one exit (the default) there is no other key, so an idle
    Chrome is never closed, contrary to the module docstring;
  - it checks `b.lock.locked()` under `_browsers_lock`, while `fetch` takes
    `b.lock` without `_browsers_lock`, so with two or more proxies a Chrome
    can be closed between the check and the lock;
  - `last_use` is set when a call starts, not when it ends.
- **Impact:** with the default config Chrome stays open for the process
  lifetime. The race is latent until multiple proxies are used.

### K-08 Ignored parameters
- **Where:** `browser_client.fetch`, `browser_client.fetch_any`.
- **Observed:** `site`, `variant`, `session` and `timeout` are accepted and
  never used. `fetch_any` uses only the first candidate.
- **Impact:** callers may believe they set a timeout; they do not.

### K-09 Pid-diff assumes a lock that does not exist
- **Where:** `patchright_driver._children_since` docstring, comment in
  `PatchrightDriver.__init__` ~731, `kill_orphan_browsers` docstring.
- **Observed:** they rely on launches being serialised by
  `chrome_manager._create_lock`, which is not in this repo. Here launches are
  serialised only by the per-proxy `_Browser.lock`.
- **Impact:** with one proxy, correct. With several proxies launching at once,
  one driver can record (and later kill) another driver's processes.

### K-10 No backoff on the box path; backoff blocks request threads
- **Where:** `fetch._box_call`, `fetch._retrying`.
- **Observed:** box retries relaunch Chrome immediately. Curl backoff
  (`time.sleep`, 2 s then 4 s) runs on the cheroot request thread.
- **Impact:** an immediate relaunch against a refusing exit; under load,
  sleeping threads reduce the 16-thread pool.

## HTTP layer and output

### K-11 `ValueError` maps to 400; 5xx are not logged
- **Where:** `routes.call`.
- **Observed:** `except ValueError` -> 400 also catches parser or upstream
  bugs (e.g. `int(store["merchant_id"])` in `api._reviews`). The 500 and 502
  paths print nothing.
- **Impact:** server bugs look like client errors; failures leave no trace in
  the server output.

### K-12 Absolute `next`/`previous` links, uncapped
- **Where:** `routes._page_link`, `routes.paginate`.
- **Observed:** links take scheme and host from `request.urlparts`, which in
  bottle 0.13.4 follows `X-Forwarded-Proto`, `X-Forwarded-Host` and `Host`,
  but the path is `request.path`, so a prefix stripped by a reverse proxy is
  lost. On the `total_pages` branch `paginate` sets `next` whenever
  `page < total_pages`, without the schema cap (`schemas.MAX_REVIEW_PAGE` =
  500), so `/products/reviews` can link page 501, which the schema rejects
  with 400. Listings that set `has_next` are not affected
  (`api._keywords_rank` already caps at page < 25).
- **Impact:** clients should paginate with `page`, not follow `next`.

### K-13 Brand store product lists get smartstore links
- **Where:** `api._store_products` -> `parsers.parse_store_products(..., is_brand=False)` ~503.
- **Observed:** `is_brand` is never passed, so products of a brand store are
  linked as `https://smartstore.naver.com/<slug>/products/<id>`.
- **Impact:** links differ from the store's own host; passing one to
  `/products/details` takes the smartstore path instead of the brand SSR page.
  Whether the smartstore host serves those links was not checked live.

## Config and environment

### K-14 `ENV=production` does nothing
- **Where:** `archive/docker/Dockerfile` (`ENV ENV=production`), `hostenv.IS_PRODUCTION`,
  `hostenv.IS_VM`, `hostenv.IS_VM_OR_DOCKER`.
- **Observed:** `IS_PRODUCTION` is set and never read. Same for `IS_VM`
  (env `VM`) and `IS_VM_OR_DOCKER`. The Dockerfile comment
  ("Never open debug prompts/devtools on crash") describes no behaviour here.

### K-15 Unused `config.NAVER_SHOPPING_PROXY`
- **Where:** `config.NAVER_SHOPPING_PROXY` ~26.
- **Observed:** read at import, used nowhere. The getters
  `naver_shopping_proxy` and `naver_shopping_browser_proxy` re-read the env
  on each call.
- **Impact:** a patch of the constant has no effect.

### K-16 `PATCHRIGHT_DIRECT_HOSTS` read at import
- **Where:** `patchright_driver._DEFAULT_DIRECT_HOSTS` ~564.
- **Impact:** a change needs a process restart. It only matters with a proxy.

## Dependencies

### K-17 Unpinned dependencies
- **Where:** `server/requirements.txt`.
- **Observed:** only `curl_cffi>=0.16,<0.17` is pinned. bottle, cheroot,
  marshmallow, requests, patchright, psutil, pyvirtualdisplay and pytest float.
  Chrome itself is the Mac's installed Google Chrome and auto-updates.
  `browserforge` is not listed; it is
  imported only when `browserforge=True`, which Naver never sets.
- **Impact:** every `pip install` is an upgrade. Run the
  live smoke after one (R-DEP-2).

Last verified in the local venv (`.venv/bin/python -m pip list`, 2026-11-01,
Python 3.14.5): offline suite 99 passed.

| Package | Version |
|---|---|
| patchright | 1.64.3 |
| bottle | 0.13.4 |
| marshmallow | 4.3.1 |
| cheroot | 11.1.2 |
| curl_cffi | 0.16.3 |
| requests | 2.34.2 |
| psutil | 7.2.2 |
| PyVirtualDisplay | 3.0 |
| pytest | 9.2.0 |

`scripts/requirements.txt` floats too. Last verified 2026-11-07 (Python 3.11.18, scripts suite passing, the
description images stage live on 20 products): the OCR set below. A sidecar records the rapidocr version (it ships
its ONNX models), the onnxruntime version and the engine params (`description_ocr.engine_info()`): after an upgrade of
either, every sidecar is read again on the next run; check one product's rows by eye.

| Package | Version |
|---|---|
| rapidocr | 3.10.0 |
| onnxruntime | 1.31.1 |
| opencv-python-headless | 5.0.0.93 |
| numpy | 2.4.6 |
| Pillow | 13.0.0 |
| requests | 2.34.2 |

### K-20 No shutdown hook: temp profiles survive Ctrl+C
- **Where:** `run.main` (catches `KeyboardInterrupt`, stops cheroot only); `PatchrightDriver.close` is the only
  place that removes `_profile_dir`.
- **Observed (macOS, 2026-11-01):** after Ctrl+C the Chrome processes exit with the patchright driver, but each
  `$TMPDIR/patchright-profile-*` directory stays on disk.
- **Impact:** disk litter only. Clear with `rm -rf "$TMPDIR"/patchright-profile-*` while the server is stopped.
  A fix (an `atexit` close of `browser_client`'s browsers) needs only the live smoke, not an A/B.

### K-21 Naver's internal-error page is answered 503, not 404
- **Where:** `ext_product.read_page` (the tab-URL check), the extension's page read.
- **Observed (2026-11-06/07, 139 products, ~1 page read in 25):** Naver opens
  `shopv.pstatic.net/web/maintenance/internal-error.html` on any product for 2-15 minutes. The extension cannot read
  that host ("Cannot access contents of url ... Extension manifest must request permission to access this host"), so
  `/products/specs` and `/products/page` answer 503 before the 404 check runs; `CollectGuard` takes a 503 as a stop.
  Two reads of one product right after each other made it likelier.
- **Impact:** a collection run stops on a passing Naver error. Callers wait ~2 min and retry (twice), then skip the
  product and come back to it (scripts/README.md "Checking a run against product pages"). Since 2026-11-07 the 503's
  error starts with its kind: `naver error page:` for this one (`adapter error:` for another failed read, `wall:`
  for a wall), so `scripts/job.py` waits and retries it and stops only on a wall; the status stays 503.

## Stale references and unused code

### K-18 References to code that is not in this repo
Do not look for these and do not trust the text around them as a
description of this repo:
- `route_glue` (`scraper_errors` docstring; `naver_shopping.fetch` and
  `naver_shopping.api` docstrings). The route layer is `routes.call`.
- `recipes/naver_shopping.py` and the knobs `NAVER_SHOPPING_EXIT` /
  `NAVER_SHOPPING_BROWSER_EXIT` (`naver_shopping.fetch` docstring). The only
  knob is `NAVER_SHOPPING_PROXY`.
- `coupang/fetch.py` (`egress` docstring).
- `chrome_manager`, `camoufox_driver`, `browser_worker`, `ONLY_SCRAPER`,
  `config.CHROME_POOLS`, `config.resolve_timezone`, the "g2 pool" and the
  `patchright_test.py` / `patchright_fetch_test.py` probes
  (`patchright_driver` docstrings and comments; `camoufox_driver` also in the
  `url_blocking` docstring).
- `test_url_blocking.py` (`url_blocking` docstring) and
  `tests/test_egress_policy.py` (`egress.accept_language` docstring).
- `requirements-worker.txt` (`hostenv` docstring).

### K-19 Driver features Naver never uses
- **Where:** `patchright_driver`.
- **Observed:** not called by the Naver path: the Cloudflare/Turnstile loop
  (runs but returns None on Naver), `get_many`, `TabbedPatchrightDriver`,
  `kill_orphan_browsers`, `chrome_version`, `content_frames`, `clear_cookies`,
  `reset_on_release`, the Opera/Brave executable probe and browserforge.
  Also `api.SEARCH_MAX_CARDS` (= 96) is defined and never read; it only
  documents the widget's depth.
- **Impact:** most of the module is multi-site code. Its comments hold dated
  A/B evidence; do not prune it without evidence (R-BOX-14), and do not
  read its comments as Naver facts.
