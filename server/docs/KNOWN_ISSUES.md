# Known issues

Inherited defects, contradictions, stale references and dependency risk in
`server/`. Each entry was re-checked against the code on 2026-11-01; the
statuses on 2026-11-16.

## How to use

1. Something in `server/` looks wrong, a block or 502 needs explaining, or a
   dependency is upgraded: find it in the index below (or grep the symbol).
2. Read its **Status**:
   - **open**: the code still does this. Do not copy the pattern, and do not
     "fix" it without the evidence the policy below asks for. Entries marked
     "working setup" (K-01, K-02) are kept on purpose until an A/B says
     otherwise.
   - **mitigated (date)**: still in the code, but callers or scripts work
     around it as the entry says; keep the workaround.
   - **fixed (date)**: the entry is under [Closed](#closed) at the end, kept
     for its history.
3. A **Today:** sentence in [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) with
   a K-number describes one of these entries; it is not a rule.

**Policy for every entry: do not copy the pattern; fix it only with evidence
and a live A/B** (A/B against the current code on the same exit: step 3 of
"Checklist: changing transport or browser code"; then the live smoke with at
least one curl call and one box call: R-TEST-4; both in
[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)). The current
code is the one observed to fetch Naver data stably; several entries below
are part of that working setup, so "looks wrong" is not enough to change it.
A fix moves its entry to [Closed](#closed) in the same commit, with
**Status: fixed YYYY-MM-DD** and what fixed it; its K-number is never reused
(2026-11-16, the docs re-lay; before: "A fix removes its entry in the same
commit"; the statuses open / mitigated / fixed and the index are from the
same date).

Citations name symbols; `~N` is a line hint only. How the parts fit together
is in [ARCHITECTURE.md](ARCHITECTURE.md).

| K | Issue | Status |
|---|---|---|
| K-01 | `no_viewport=True` despite a NEVER comment | open |
| K-02 | Image/font blocking on an anti-bot target | open |
| K-03 | 418 is not a refusal inside the browser | open |
| K-04 | Transport failures counted as refusals | open |
| K-05 | No retry for box answer errors | open |
| K-06 | Rotation is a no-op with zero or one proxy | open |
| K-07 | Idle reaper | open |
| K-08 | Ignored parameters | open |
| K-09 | Pid-diff assumes a lock that does not exist | open |
| K-10 | No backoff on the box path; backoff blocks request threads | open |
| K-11 | `ValueError` maps to 400, unlogged | open |
| K-12 | Absolute `next`/`previous` links, uncapped | mitigated |
| K-13 | Brand store product lists get smartstore links | open |
| K-14 | `ENV=production` does nothing | open |
| K-15 | Unused `config.NAVER_SHOPPING_PROXY` | open |
| K-16 | `PATCHRIGHT_DIRECT_HOSTS` read at import | open |
| K-17 | Unpinned dependencies | open |
| K-18 | References to code that is not in this repo | open |
| K-19 | Driver features Naver never uses | open |
| K-20 | No shutdown hook: temp profiles survive Ctrl+C | open |
| K-21 | Naver's internal-error page is answered 503, not 404 | mitigated 2026-11-07 |
| K-22 | Held listing tab: limits the probes did not cover | open |

## Browser box

### K-01 `no_viewport=True` despite a NEVER comment
- **Status:** open: working setup, kept until an A/B says otherwise.
- **Where:** `PatchrightDriver._main`, comment ~761 vs the launch kwargs ~860.
- **Observed:** the comment says "NEVER no_viewport=True: its window geometry
  is a DataDome tell", but every launch with a channel passes
  `no_viewport=True`. Naver always launches with channel `"chrome"`, so this is
  the path in use.
- **Impact:** the code contradicts its own guidance. Naver works with it
  today; whether removing it helps or hurts on Naver is untested.

### K-02 Image/font blocking on an anti-bot target
- **Status:** open: working setup, kept until an A/B says otherwise.
- **Where:** `browser_client.BLOCK_RESOURCES`; `PatchrightDriver.__init__`
  comment ~703-710.
- **Observed:** the driver comment calls image/font flag blocking
  "Detectable by WAFs" and meant for pools that never face anti-bot sites.
  Naver lists `"image"` and `"font"` (plus `"media"`).
- **Impact:** a possible fingerprint signal. It works today; change only
  with an A/B.

### K-03 418 is not a refusal inside the browser
- **Status:** open.
- **Where:** `browser_client.REFUSE_STATUSES` = (403, 405, 429, 490);
  `fetch._box_answer`.
- **Observed:** `_box_answer` treats 418 as `NaverBlocked`, but
  `_Browser.fetch_one` does not treat it as a refusal. A 418 answer passes
  through, then raises `NaverBlocked` without closing Chrome or rotating.
- **Impact:** a 418-blocked Chrome stays in use for the next request.

### K-04 Transport failures counted as refusals
- **Status:** open.
- **Where:** `_Browser.fetch_one` (`if not r.status_code and r.error`);
  `_Browser.warm` (goto exception -> `BoxRefused`).
- **Observed:** an in-page fetch that never completed (status 0: network
  error, 30 s abort) and a failed anchor navigation both raise `BoxRefused`,
  the same as a captcha or login wall.
- **Impact:** a network blip closes Chrome and spends a rotation attempt as
  if Naver had refused; logs cannot tell the two apart.

### K-05 No retry for box answer errors
- **Status:** open; clients retry a 502 (ENDPOINTS.md client policy).
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
- **Status:** open: matters only with a rotating proxy.
- **Where:** `browser_client.ExitPool.rotate`, `config.naver_shopping_browser_proxy`.
- **Observed:** `rotate` calls the mint function again, which re-reads the
  same env value. The `ExitPool` docstring says so.
- **Impact:** a "rotated" retry uses a fresh Chrome and profile on the same
  IP. Only a rotating proxy gives a fresh exit.

### K-07 Idle reaper
- **Status:** open.
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
- **Status:** open.
- **Where:** `browser_client.fetch`, `browser_client.fetch_any`.
- **Observed:** `site`, `variant`, `session` and `timeout` are accepted and
  never used. `fetch_any` uses only the first candidate.
- **Impact:** callers may believe they set a timeout; they do not.

### K-09 Pid-diff assumes a lock that does not exist
- **Status:** open: latent, matters only with several proxies.
- **Where:** `patchright_driver._children_since` docstring, comment in
  `PatchrightDriver.__init__` ~731, `kill_orphan_browsers` docstring.
- **Observed:** they rely on launches being serialised by
  `chrome_manager._create_lock`, which is not in this repo. Here launches are
  serialised only by the per-proxy `_Browser.lock`.
- **Impact:** with one proxy, correct. With several proxies launching at once,
  one driver can record (and later kill) another driver's processes.

### K-10 No backoff on the box path; backoff blocks request threads
- **Status:** open.
- **Where:** `fetch._box_call`, `fetch._retrying`.
- **Observed:** box retries relaunch Chrome immediately. Curl backoff
  (`time.sleep`, 2 s then 4 s) runs on the cheroot request thread.
- **Impact:** an immediate relaunch against a refusing exit; under load,
  sleeping threads reduce the 16-thread pool.

## HTTP layer and output

### K-11 `ValueError` maps to 400, unlogged
- **Status:** open; since 2026-11-05 the other failures are logged (below).
- **Where:** `routes.call`.
- **Observed:** `except ValueError` -> 400 also catches parser or upstream
  bugs (e.g. `int(store["merchant_id"])` in `api._reviews`), and that path
  prints nothing. The other failures (400 from Naver, 404, 409, 410, 500, 502,
  503) print one `api: <status> ...` line through `routes._failed` since
  2026-11-05 (R-STYLE-4).
- **Impact:** such server bugs look like client errors and leave no trace in
  the server output.

### K-12 Absolute `next`/`previous` links, uncapped
- **Status:** mitigated: clients paginate with `page` (ENDPOINTS.md "Pagination", `NaverApiClient`).
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
- **Status:** open.
- **Where:** `api._store_products` -> `parsers.parse_store_products(..., is_brand=False)` ~503.
- **Observed:** `is_brand` is never passed, so products of a brand store are
  linked as `https://smartstore.naver.com/<slug>/products/<id>`.
- **Impact:** links differ from the store's own host; passing one to
  `/products/details` takes the smartstore path instead of the brand SSR page.
  Whether the smartstore host serves those links was not checked live.

## Config and environment

### K-14 `ENV=production` does nothing
- **Status:** open: harmless; the Dockerfile is archived (`archive/docker/`).
- **Where:** `archive/docker/Dockerfile` (`ENV ENV=production`), `hostenv.IS_PRODUCTION`,
  `hostenv.IS_VM`, `hostenv.IS_VM_OR_DOCKER`.
- **Observed:** `IS_PRODUCTION` is set and never read. Same for `IS_VM`
  (env `VM`) and `IS_VM_OR_DOCKER`. The Dockerfile comment
  ("Never open debug prompts/devtools on crash") describes no behaviour here.

### K-15 Unused `config.NAVER_SHOPPING_PROXY`
- **Status:** open: R-HTTP-6 forbids using the constant.
- **Where:** `config.NAVER_SHOPPING_PROXY` ~72.
- **Observed:** read at import, used nowhere. The getters
  `naver_shopping_proxy` and `naver_shopping_browser_proxy` re-read the env
  on each call.
- **Impact:** a patch of the constant has no effect.

### K-16 `PATCHRIGHT_DIRECT_HOSTS` read at import
- **Status:** open.
- **Where:** `patchright_driver._DEFAULT_DIRECT_HOSTS` ~564.
- **Impact:** a change needs a process restart. It only matters with a proxy.

## Dependencies

### K-17 Unpinned dependencies
- **Status:** open: a standing risk, re-checked after each upgrade (R-DEP-2).
- **Where:** `server/requirements.txt`.
- **Observed:** only `curl_cffi>=0.16,<0.17` is pinned (`websockets>=13`,
  for the extension bridge, has a lower bound only). bottle, cheroot,
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

## Running the server

### K-20 No shutdown hook: temp profiles survive Ctrl+C
- **Status:** open: disk litter only.
- **Where:** `run.main` (catches `KeyboardInterrupt`, stops cheroot only); `PatchrightDriver.close` is the only
  place that removes `_profile_dir`.
- **Observed (macOS, 2026-11-01):** after Ctrl+C the Chrome processes exit with the patchright driver, but each
  `$TMPDIR/patchright-profile-*` directory stays on disk.
- **Impact:** disk litter only. Clear with `rm -rf "$TMPDIR"/patchright-profile-*` while the server is stopped.
  A fix (an `atexit` close of `browser_client`'s browsers) needs only the live smoke, not an A/B.


## Extension transport

### K-21 Naver's internal-error page is answered 503, not 404
- **Status:** mitigated 2026-11-07: the 503 says `naver error page:` and `scripts/job.py` waits and retries it.
- **Where:** `ext_product._land` (the tab-URL check, both product reads), the extension's page read.
- **Observed (2026-11-06/07, 139 products, ~1 page read in 25):** Naver opens
  `shopv.pstatic.net/web/maintenance/internal-error.html` on any product for 2-15 minutes. The extension cannot read
  that host ("Cannot access contents of url ... Extension manifest must request permission to access this host"), so
  `/products/specs` and `/products/page` answer 503 before the 404 check runs; `CollectGuard` takes a 503 as a stop.
  Two reads of one product right after each other made it likelier.
- **Impact:** a collection run stops on a passing Naver error. Callers wait ~2 min and retry (twice), then skip the
  product and come back to it (scripts/COLLECT.md "Checking a run against product pages"). Since 2026-11-07 the 503's
  error starts with its kind: `naver error page:` for this one (`adapter error:` for another failed read, `wall:`
  for a wall), so `scripts/job.py` waits and retries it and stops only on a wall; the status stays 503.


### K-22 Held listing tab: limits the probes did not cover
- **Status:** open: limits not yet seen live.
- **Where:** `ext_listing_tab.py` (`/listing-tabs`), `scripts/job.py scroll`; `scripts/collect_guard.py`
  `CollectGuard.run`.
- **Observed (2026-11-14, probes 1-3: 11 + 6 + 5 batches, 50 clicks, ~22 min idle at most):**
  - A product partial on the first collect (e.g. `photos_incomplete`) is collected once more by `CollectGuard`; the
    old mode's second `/products/specs` call is a 24 h cache hit, here `/listing-tabs/<id>/specs` is not cached, so
    the product page is loaded and clicked a second time (accepted for the MVP, Fable review 7).
  - Tab life: the 100-product pilot (2026-11-14, 191 min, one tab, 15 batches) kept its tab 3 h 13 min; batch 13
    stayed ~70 min without a scroll and the next scroll brought batch 14, no reopen. Longer than that is unproven; a
    stale tab would show as a stall (503 `wall:`, the job stops) or a 410 (the job opens a new tab, at most 2 times
    an hour).
  - Very long listings are unproven: the furthest walked is batch 15 of ~90 (the pilot) and two ends were seen
    (53, 122 rows); a listing of thousands, read over a day, has not been walked to its end in one tab.
  - A reopen starts from the top and scrolls past done batches (~20-40 s a batch, estimated); products whose card
    does not come again (the list is virtualized) are not read by the tab: `job.py` reports them as `left` for the
    other mode.
  - Not seen live yet: a reopen, the drain of a product stopped mid-read, a second page load on a partial (the pilot
    had none of them: 0 reopens, 0 partials, 0 captchas, 0 login gates).
- **Impact:** small so far (the pilot: 100 published of 101 taken, the one closed by translation). A scroll job
  runs with the owner near for captchas; a stop says why and `scroll --job` resumes.


## Stale references and unused code

### K-18 References to code that is not in this repo
- **Status:** open.
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
- **Status:** open: kept on purpose (R-BOX-14).
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

## Closed

None yet. A fixed entry moves here with its text, **Status: fixed
YYYY-MM-DD**, and the commit or evidence that fixed it, when it no longer
guides work.
