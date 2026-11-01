# Development rules for server/

This is the single binding rulebook for everything under `server/`. On a conflict with any other doc, this file wins.

- **MUST** / **MUST NOT**: binding. Breaking one requires a dated entry in the [Decision log](#decision-log) at the bottom of this file, in the same commit: date, rule ID, what changes, why, and the evidence (a live A/B, a probe, a test).
- **SHOULD**: the default. A deviation is explained in the commit message.
- **MAY**: allowed, no justification needed.

Citations name symbols (`module.function`, `module.Class.method`, `module.CONSTANT`). A `~123` is only a line hint and may drift.

Related docs: [ARCHITECTURE.md](ARCHITECTURE.md) (how it works, "Naver specifics"), [ENDPOINTS.md](ENDPOINTS.md) (the public HTTP contract), [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (debt and contradictions).

**Known defects are not rules.** Everything listed in KNOWN_ISSUES.md (for example `no_viewport=True` on the Chrome channel path, 418 missing from `browser_client.REFUSE_STATUSES`, a status-0 in-page fetch counted as a refusal, the idle reaper that never fires with one exit) describes what the code does today, not what new code should do. Do not copy those patterns. A fix needs evidence: a live A/B on Naver for anything that changes how Naver sees the client, otherwise a test or the live smoke.

Where a rule touches such a pattern, the binding part is the invariant only; the rest is marked **Today:** with a K-number. A **Today:** sentence describes current behaviour, is not a MUST, and may be changed by a fix that follows the KNOWN_ISSUES entry (evidence, A/B, KNOWN_ISSUES update) without a decision entry. Two kinds of entries exist: working setup that is kept until an A/B says otherwise (for example K-01, K-02), and defects that can be fixed (for example K-03, K-04, K-05, K-10, K-11, K-15).

---

## R-LAYOUT: layout and imports

- **R-LAYOUT-1 (MUST)** `server/` is the import root. Modules import each other by bare name: `import config`, `from cache import cached_call`, `from naver_shopping import api`, `from scraper_errors import ...`. `pyproject.toml` puts `server` on `pythonpath` for pytest; `python server/run.py` puts it on `sys.path[0]`.
- **R-LAYOUT-2 (MUST NOT)** Do not add `server/__init__.py`, do not use relative imports (`from . import x`) or package-qualified ones (`from server.naver_shopping import ...`). With a `server` package, pytest would import the same file under two names (`server.naver_shopping.fetch` and `naver_shopping.fetch`), splitting module state (`fetch._EXITS`, `browser_client._browsers`, `cache._store`) and making monkeypatches miss. `test_import_smoke.py` checks that every library module in `test_import_smoke.MODULES` imports by its bare name (the entry points `run.py` and `main.py` are not imported). It does not detect a dual-import split; only the absence of `server/__init__.py` and of package-qualified imports prevents that.
- **R-LAYOUT-3 (MUST)** New modules go in one of two places: `server/` for shared infrastructure (transport-agnostic helpers, browser stack, cache, config), `server/naver_shopping/` for anything Naver-specific (fetch, parse, refs, schemas, endpoint functions). Add each new top-level module to `test_import_smoke.MODULES`.
- **R-LAYOUT-4 (SHOULD NOT)** Do not add new `sys.path.insert` lines. The existing ones (`naver_shopping/fetch.py`, `naver_shopping/test_parsers.py`, `naver_shopping/test_schemas.py`) are harmless duplicates of `pythonpath`; leave them.
- **R-LAYOUT-5 (MUST)** The supported entry points are:
  - `.venv/bin/python server/run.py` (or `cd server && ../.venv/bin/python run.py`);
  - `.venv/bin/python server/main.py` (in-process demo, writes `output/` relative to the CWD);
  - `.venv/bin/python -m pytest -q` from the repo root (or from `server/`);
  - macOS is the supported platform; the retired Docker setup lives in `archive/docker/` and is not maintained. Do not add Docker/Linux instructions to the docs without a decision entry.
- **R-LAYOUT-6 (MUST)** File moves are pure `git mv` commits with no content edits, so history and blame survive.

## R-ARCH: request architecture

- **R-ARCH-1 (MUST)** Keep the layer order. Each layer only calls the one below it:

  ```
  routes.call -> schema (load_query) -> naver_shopping.api.<endpoint> -> naver_shopping.fetch -> browser_client -> patchright_driver
                                                                     \-> naver_shopping.parsers (pure)
  ```

  - `routes` holds no business logic: validate, call, map errors, paginate.
  - `naver_shopping/fetch.py` is the only module that sends requests to Naver. `api.py` chooses backend paths, query strings and POST bodies, but never touches a transport, headers, sessions or status codes.
  - `browser_client` is the only caller of `patchright_driver` for Naver (`browser_client._launch`).
- **R-ARCH-2 (MUST)** Parsers are pure: no I/O, no network, no globals mutated, never raise on unexpected input (see R-OUT-1).
- **R-ARCH-3 (MUST)** Schemas validate every input before `api` sees it. `schema_fields.BaseSchema` keeps `unknown = RAISE`. Each entity has ONE reference param (`product`, `store`, `catalog`, `category`) resolved by a `refs.resolve_*` function through a `schema_fields.RefField` subclass; resolvers raise `ValueError("Must be ...")`, which becomes a 400. Never accept sibling `url` + `id` params.
- **R-ARCH-4 (MUST)** Public enum values map to upstream tokens through `{public: upstream}` dicts in `naver_shopping/schemas.py` (`REVIEW_SORTS`, `BEST_PERIODS`, `DATALAB_PERIODS`, ...) and are echoed back in public form (`api._public`; `BEST_PERIODS` via `.lower()` in `api._store_products`).
- **R-ARCH-5 (MUST NOT)** Do not rename route paths (`routes.ENDPOINTS`), the `/naver-shopping` prefix (`routes.SITE`, `routes.mount`), or cache namespaces (`naver_shopping.*`). `/` and `/health` stay unprefixed only.
- **R-ARCH-6 (MUST)** Keep the current execution model: bottle + cheroot with a thread pool (`run.main`, `numthreads=16`), sync code, one curl session per thread, one Chrome owner thread per proxy. Do not introduce an async server, ORM, DI container or logging stack without a decision entry. The per-thread curl session and patchright's greenlet-bound sync API both depend on this model.
- **R-ARCH-7 (SHOULD)** Reuse the shared bundles instead of new fetches: the store record (`api._store` -> `api._store_record`) and the product record (`api._record` -> `api._product_record`). Data they already carry must not be fetched again.

## R-BOX: the browser box (browser_client.py, patchright_driver.py)

The box serves only the store backend `brand.naver.com/n/v1|v2/*` (see R-NAVER-2).

- **R-BOX-1 (MUST)** Use a real, headed Google Chrome: `headless=False` in `browser_client._launch`, channel `"chrome"` by default (`PatchrightDriver._main`), i.e. the Google Chrome installed in /Applications on the Mac; a visible window is expected. The container and Linux/Xvfb branches in the driver are inherited and unused on macOS: keep them, do not build on them. Do not switch Naver to headless or bundled Chromium.
- **R-BOX-2 (MUST)** Warm up once per Chrome on `browser_client.ANCHOR` (`https://brand.naver.com/samsung/best`) with referer `https://www.naver.com/` (`_Browser.warm`, `nav(..., mode="blocked")`). The warm-up is accepted only with render proof: no `nid.naver.com` redirect, status not in `REFUSE_STATUSES`, no `WALL_MARKERS`, and `__PRELOADED_STATE__` present in the HTML. Anything else raises `BoxRefused`.
- **R-BOX-3 (MUST)** Every backend call is a same-origin in-page `fetch()` from the anchor page: `_Browser.fetch_one` -> `PatchrightDriver.get` / `PatchrightDriver.request` -> `patchright_driver._FETCH_JS`, with `referrer=ANCHOR`, `credentials: 'include'`, `referrerPolicy: 'strict-origin-when-cross-origin'`. Never export browser cookies into an HTTP client (Naver answers 429 to replays; `browser_client` module docstring).
- **R-BOX-4 (MUST)** In-page fetches run in patchright's isolated world (the `page.evaluate` default; `PatchrightDriver.evaluate` passes `isolated_context=not main_world`). The page's own scripts cannot see or hook them. Do not move `get` / `request` to the main world.
- **R-BOX-5 (MUST)** Header hygiene: every box call passes through `browser_client._clean_headers`, which drops `_DROP_PREFIXES` (`sec-*`, `origin`, `referer`, `accept-language`, `user-agent`, `host`, ...). The browser sets those itself. Box calls send only `fetch.BOX_HEADERS` (accept, content-type).
- **R-BOX-6 (MUST)** Browser identity is set at process level, not through CDP emulation: locale as `--lang` / `--accept-lang` on the command line, timezone as `TZ` in Chrome's environment (`PatchrightDriver._main`). Playwright `locale` is never used; `timezone_id` only on Windows, where Chrome ignores `TZ`. Evidence: the dated Coupang A/B in the `PatchrightDriver.__init__` and `_main` comments.
- **R-BOX-7 (MUST)** Owner thread, plain data across threads. Every Playwright object is created and used on the driver's own thread through `PatchrightDriver.call()`. Only plain data (dicts, strings, `FetchResponse`) crosses threads. Never return a Page, Response or Locator from `call()`. Every op stays under `CALL_TIMEOUT` (90 s); a timeout means the page is wedged and the driver must be closed.
- **R-BOX-8 (MUST)** In-page JS never throws across the evaluate bridge. It returns a structured object on success and failure alike (`ok, status, url, body, headers`, plus `error` on failure; `_FETCH_JS`, `_FETCH_MANY_JS`), which `PatchrightDriver.get` / `request` turn into a `FetchResponse`. JS lives in module-level string constants that take a single argument (a destructured object, or a scalar such as `n` in `_CAPPED_CONTENT_JS`).
- **R-BOX-9 (MUST)** Request blocking uses one abort-only route built from a single regex (`url_blocking.compile_block_re`, installed with `browser.route(regex, abort)` in `_main`). Do not add a `"**/*"` route or decide per request in Python: that saturated the Playwright pipe and wedged pages (comment at the `browser.route` call). **Today:** images and fonts are blocked by Chrome flags (`browser_client.BLOCK_RESOURCES`; `--blink-settings=imagesEnabled=false`, `--disable-remote-fonts` in `_main`), not routes; see K-02.
- **R-BOX-10 (MUST)** On a refusal, start over with a fresh Chrome and a fresh profile. `_Browser.fetch_one` raises `BoxRefused` for a status in `REFUSE_STATUSES`, `WALL_MARKERS` in the body, or a `nid.naver.com` final URL; `browser_client.fetch` then closes the driver (`PatchrightDriver.close` deletes the throwaway profile dir) and `fetch._box_call` rotates the exit. The next call re-warms. A persistent or owner Chrome profile is not allowed without a decision entry.
- **R-BOX-11 (MUST)** One kept-alive Chrome per proxy URL, each under its own lock (`browser_client._Browser.lock`, registry `_browsers` guarded by `_browsers_lock`). Calls to one proxy are serialized. Keep the `ExitPool` / `fetch_any` / `BoxRefused` / `BoxUnavailable` interface that `naver_shopping/fetch.py` depends on.
- **R-BOX-12 (MUST)** With a proxy, WebRTC stays inside it (`--force-webrtc-ip-handling-policy=disable_non_proxied_udp`), and Chrome's own background hosts go direct (`patchright_driver.CHROME_BACKGROUND_HOSTS`, `PATCHRIGHT_DIRECT_HOSTS`). Never add Naver hosts to the direct list.
- **R-BOX-13 (MUST)** Keep the safety nets: the capped DOM snapshot (`_capped_content`, `_MAX_CONTENT_CHARS`), the pid-diff force-kill on close (`PatchrightDriver._force_kill`), `STARTUP_TIMEOUT` cleanup.
- **R-BOX-14 (MUST NOT)** Do not prune the multi-site code in `patchright_driver.py` (Cloudflare/Turnstile handling, browserforge, the Opera/Brave probe, `TabbedPatchrightDriver`, `kill_orphan_browsers`) without evidence. Its comments record dated A/B results. Naver uses `nav(mode="blocked")`, `get`, `request` and `close`.
- **R-BOX-15 (SHOULD)** A new browser identity knob is a `PatchrightDriver` constructor kwarg set by the caller. Environment variables (`PATCHRIGHT_*`) are for host-level overrides only.

## R-HTTP: the curl_cffi transport (naver_shopping/fetch.py)

Every surface that is not the store backend uses this path (R-NAVER-2).

- **R-HTTP-1 (MUST)** Use `curl_cffi` with `impersonate="chrome"` (`fetch.IMPERSONATE`), through `fetch._session()` only. The session is thread-local (`fetch._local`) and never crosses threads.
- **R-HTTP-2 (MUST)** ns-portal search requests carry the widget headers from `fetch._widget_headers` (`x-ns-*`, `x-ns-view-type: TREND`, mobile device type), with per-session random page/session ids minted in `fetch._session`. A `{}` answer means the headers were refused (`fetch._portal_json`).
- **R-HTTP-3 (MUST)** Each session carries one synthetic `NNB` cookie on `.naver.com` (`fetch.nnb_cookie`, set in `fetch._session`). Since 2026-10-29 ns-portal answers 418 to a request with no naver.com cookie. One NNB per session; do not reuse one across sessions.
- **R-HTTP-4 (MUST)** Every curl request runs as a `once()` closure inside `fetch._retrying`: up to `config.MAX_RETRIES` attempts (3) on `NaverUpstreamError` (which includes `NaverBlocked`). Each retryable failure drops the session (`fetch._drop_session`), so the retry gets a fresh connection, fresh widget ids and a fresh NNB. `NaverNotFound` and `NaverBadRequest` are never retried. **Today:** between attempts the request thread sleeps `config.RETRY_BACKOFF * attempt` seconds (`time.sleep` in `_retrying`); see K-10.
- **R-HTTP-5 (MUST)** Keep the other request shapes unless a dated probe says otherwise: `fetch.PAGE_HEADERS` for HTML pages, `fetch.DATALAB_HEADERS` for DataLab XHR posts, the fixed widget params in `fetch.search_params`, the Accept-Language from `egress.accept_language(proxy)`.
- **R-HTTP-6 (MUST)** The curl proxy comes from `config.naver_shopping_proxy()` and the box proxy from `config.naver_shopping_browser_proxy()`. Do not read `NAVER_SHOPPING_PROXY` anywhere else (the unused `config.NAVER_SHOPPING_PROXY` constant is K-15; do not use it).

## R-NAVER: upstream surfaces

- **R-NAVER-1 (MUST NOT)** Never request Naver's walled pages: `search.shopping.naver.com/ns/*`, catalog pages, `smartstore.naver.com/<store>/products/<id>` (smartstore PDP), `shopping.naver.com`. They serve a captcha (405/490), a login redirect or 429 to every client tried (`naver_shopping/fetch.py` module docstring, research 2026-10-23/24). The same holds for store home, category and search pages (they redirect to login). Exceptions (2026-11-01, decision log): the search.shopping listing, and a smartstore product page reached by a click from that search (`/products/specs`), read only in the owner's Chrome through the adapter under R-EXT-*.
- **R-NAVER-2 (MUST)** Source each datum from the surface that serves it, on the transport listed:

  | Data | Surface | Transport | Symbol |
  |---|---|---|---|
  | Search cards, total count | `ns-portal.shopping.naver.com/api/v3/shopping-paged-slot` (+ `/count`) | curl | `fetch.fetch_search`, `fetch.fetch_search_count` |
  | Store record | `smartstore.naver.com/<slug>/best` or `brand.naver.com/<slug>/best` | curl | `fetch.fetch_store_page` |
  | Brand product page | `brand.naver.com/<slug>/products/<id>` | curl | `fetch.fetch_brand_product_page` |
  | DataLab | `POST datalab.naver.com/shoppingInsight/<action>.naver` | curl | `fetch.fetch_datalab` |
  | Store backend (products, options, contents, notice, reviews, best/popular, catalog reviews) | `brand.naver.com/n/v1|v2/*`, for ANY store including smartstore | box only | `fetch.box_get`, `fetch.box_get_many`, `fetch.box_post` |

  Do not move an open curl surface into the browser, and do not try the store backend over curl.
- **R-NAVER-3 (MUST)** Batch the independent backend GETs of one record into one `fetch.box_get_many` call (one lock acquisition, one exit), like the `box_get_many` call in `api._product_record`. The `box_get` calls before it are dependent (the summary supplies `origin` and the leaf category). Known debt: on the slug-less path `_product_record` fetches `/n/v1/validation-products/{id}` twice (alone, then again in the batch); do not copy that.
- **R-NAVER-4 (MUST)** Every new upstream fact (a status code meaning, a required header or param, an ignored param, a page size, a marker) gets a dated comment at the code that handles it ("probed 2026-10-29: ..."), plus one line in the "Naver specifics" section of [ARCHITECTURE.md](ARCHITECTURE.md). The code comment is the primary record; docs point to it and do not copy it.

## R-ERR: errors and HTTP mapping

- **R-ERR-1 (MUST)** `fetch` raises only the taxonomy built on `scraper_errors`:

  | Class | Base | Meaning | Retried | HTTP (`routes.call`) |
  |---|---|---|---|---|
  | `NaverUpstreamError` | `UpstreamError` | transport failure, 5xx, empty answer | yes | 502 |
  | `NaverBlocked` | `NaverUpstreamError`, `Blocked` | captcha, login gate, 403/405/418/429/490 | yes | 502 |
  | `NaverBadRequest` | `BadRequest` | upstream rejected the params | no | 400 |
  | `NaverNotFound` | `NotFound` | entity does not exist | no | 404 |

  `routes.call` also maps a schema error to 400 (`schema_fields.load_query` body `{"error", "errors"}`). `api` and `fetch` never return HTTP status codes. **Today:** `routes.call` also maps any `ValueError` to 400 and anything else to 500; see K-11. Do not rely on `ValueError` -> 400 in new code: raise `NaverBadRequest` (or a `BadRequest` subclass) for a rejected input after validation.
- **R-ERR-2 (MUST)** Classification lives in `fetch` and `browser_client`, never in `api.py`. `fetch._classify` is the base curl classifier and `fetch._box_answer` the box-answer classifier; the wall checks in `browser_client._Browser.warm` / `fetch_one` work at the browser level. Surface-specific checks live in the matching fetch function: portal JSON shape in `fetch._portal_json` (non-JSON -> `NaverBlocked`, missing `data` -> `NaverUpstreamError`), `NOT_OPERATING_TITLE` / `NO_PRODUCT_TITLE` -> `NaverNotFound` in `fetch.fetch_store_page` / `fetch.fetch_brand_product_page`, DataLab's plain 500 -> `NaverBadRequest` in `fetch.fetch_datalab` (checked before `_classify`).
- **R-ERR-3 (MUST)** Box refusal handling: a `BoxRefused` closes that Chrome (R-BOX-10) and `fetch._box_call` rotates the exit; attempts per call are bounded by `config.NAVER_SHOPPING_BOX_ATTEMPTS` (2). With zero or one proxy, rotation re-mints the same URL, so only Chrome and the profile are new (K-06). **Today:** only `BoxRefused` is retried; `BoxUnavailable` (including a `CALL_TIMEOUT` wedge) becomes `NaverUpstreamError` at once, `_box_answer` errors are never retried (K-05), and a retry relaunches Chrome with no backoff (K-10).
- **R-ERR-4 (MUST)** Wrap transport exceptions as `NaverUpstreamError(f"request failed: {type(e).__name__}: {e}")`. Messages carry a human label (`f"product {id} summary"`) and truncate bodies (`[:120]`, `[:200]`).
- **R-ERR-5 (SHOULD)** A broad `except Exception` is used only to convert into the taxonomy or for best-effort cleanup (`close`, `_drop_session`). A new one carries a short comment saying why (as `routes.call` does: `# parser surprises`).
- **R-ERR-6 (MUST)** Exception classes have a one-line docstring. A new site-level error subclasses a `scraper_errors` base so `routes.call` maps it.

## R-CACHE: caching

- **R-CACHE-1 (MUST)** Every endpoint is served through `cache.cached_call`, in one of two ways:
  - its own namespace wrapping a private impl: `products_search` -> `cached_call("naver_shopping.search", data, _search, ttl.SEARCH_CACHE)`;
  - by slicing a shared cached bundle: `product_details` slices `_record()` (`naver_shopping.product`), `store_details` slices `_store()` (`naver_shopping.store`).
- **R-CACHE-2 (MUST)** Each TTL is a named `timedelta` in `naver_shopping/cache_config.py` with a one-line comment saying why that duration.
- **R-CACHE-3 (MUST)** Cache keys are the validated params (`cache._key`: namespace + sorted JSON). Resolvers return canonical forms, so equivalent inputs share a key; keep it that way when adding params.
- **R-CACHE-4 (MUST)** Exceptions are never cached (`cached_call` lets them propagate). Hits and stored values are deep copies, so callers may mutate results (`routes.paginate` pops `pagination`).
- **R-CACHE-5 (MUST NOT)** The cache is in-process only (`cache._store`, `MAX_ENTRIES`). Do not add an external store without a decision entry.

## R-OUT: output shape

- **R-OUT-1 (MUST)** Every field read in parsers goes through the helpers `_dict`, `_list`, `_clean`, `_text`, `_rich_text`, `_int`, `_float`, `_price`, `_bool`, `_date`, `_datetime`, so bad upstream data yields `None`, not an exception. Server-rendered JSON is read with `parsers.parse_state` (`__PRELOADED_STATE__` via `raw_decode`).
- **R-OUT-2 (MUST)** Conventions:
  - snake_case keys; ids as strings;
  - `null` for missing, masked (`parsers.MASK`) or empty values. Existing exceptions with a non-null default: `or 0` on pricing `discount_ratio`, `seller_discount`, `manager_discount`, `points.purchase`, variant `extra_price`, the search-card `discount_ratio`; the search-card `is_official` defaults to `False` when `mallDescription` is missing. Do not add new ones;
  - prices are KRW integers with `currency: "KRW"` (`parsers._price`, `parsers.CURRENCY`);
  - links are named `link`, never `url`. Links we build use the `refs` helpers (`product_link`, `store_link`, `catalog_link`); links taken from upstream (search-card product URL, review attachments) pass through;
  - new booleans are named `is_*` / `has_*` (`uses_external_stock` is an existing exception; do not rename it);
  - dates `YYYY-MM-DD` (`_date`), datetimes UTC `YYYY-MM-DDTHH:MM:SSZ` (`_datetime`);
  - listings are `{count, results}`, or `{results, pagination}` for paged endpoints, flattened by `routes.paginate` (mark the endpoint `paginated=True` in `routes.ENDPOINTS`);
  - errors are `{"error": "..."}`, plus `"errors"` for schema failures.
- **R-OUT-3 (MUST)** Any change to a public response shape updates [ENDPOINTS.md](ENDPOINTS.md) in the same commit.

## R-STYLE: code style (match the existing code)

- **R-STYLE-1 (MUST)** Every module opens with a prose docstring explaining what it does and, above all, why, with dated evidence for upstream behaviour ("verified 2026-10-24", "probed 2026-10-29"). Non-obvious code gets a WHY comment; an upstream quirk gets a dated comment where it is handled.
- **R-STYLE-2 (MUST)** Naming and layout:
  - section banners `# ---- name ----`;
  - UPPER_SNAKE constants; `_MS` suffix for milliseconds, plain names are seconds (`CALL_TIMEOUT`, `GOTO_TIMEOUT_MS`);
  - `_private` helpers and module state; compiled regexes named `_X_RE`;
  - public endpoint functions named after the resource (`products_search`, `product_details`, `store_products`), private impls as short `_name` (`_search`, `_reviews`, `_store_record`).
- **R-STYLE-3 (MUST NOT)** No type hints in untyped server modules. `egress.py` is the only typed server module and keeps its hints. Types of API answers live on the consumer side (R-TYPE).
- **R-STYLE-4 (MUST)** No logging framework. Diagnostic output is `print()`, and only in the browser driver and the entry points. Driver lines carry a subsystem prefix (`patchright: ...`); the entry points (`run.main`, `main.save`) print plain status lines. `api`, `parsers`, `refs`, `fetch`, `cache` and `browser_client` stay silent; exceptions are the signal.
- **R-STYLE-5 (MUST)** Heavy or optional dependencies are imported lazily inside the function that needs them: `patchright_driver` in `browser_client._launch`, `curl_cffi` in `fetch._session`, `requests` in `config.exit_geo`, `egress` / `config` / `url_blocking` in `PatchrightDriver.__init__`, browserforge in `PatchrightDriver._main`, pyvirtualdisplay in `_ensure_display`. Keep them lazy; parser tests must not load the browser stack.
- **R-STYLE-6 (SHOULD)** Double quotes, f-strings, parenthesized multi-line imports. New lines stay at or under 120 characters. 34 existing lines exceed that; do not reformat them in unrelated commits.

## R-TYPE: data types

Requests are typed on the server, answers on the consumer side.

- **R-TYPE-1 (MUST)** Request params are typed and validated only by the marshmallow schemas in
  `naver_shopping/schemas.py` (fields from `schema_fields.py`). No hand-parsed query params in routes.
- **R-TYPE-2 (MUST)** Every API answer has a TypedDict in `scripts/naver_types.py`, and a captured real answer in
  `scripts/fixtures/` that `scripts/test_naver_types.py` checks against it strictly (missing / unknown keys and wrong
  types fail). A new endpoint or any change to an answer's shape updates the parser, the TypedDict, the fixture and
  the typed client method in the same commit.
- **R-TYPE-3 (MUST)** Types say what the server can really send, read from the parser code, not from one sample:
  `X | None` where a parser helper can return None, `NotRequired` only where the key can be omitted, `Literal` only
  for value sets the code closes. Open upstream enums stay `str`.
- **R-TYPE-4 (MUST)** Scripts call known endpoints through the typed client methods (`search`, `product_details`,
  `listing`, ...), not raw `get(path)`, and guard every `X | None` field before using it. `get` / `pages` stay for
  routes without a method yet, and for `smoke_endpoints.py`, which checks routes as routes.
- **R-TYPE-5 (SHOULD)** New or changed scripts pass `mypy --ignore-missing-imports --check-untyped-defs` (command in
  `scripts/README.md`). Type hints are welcome in `scripts/` (unlike the server, R-STYLE-3).
- **R-TYPE-6 (MUST)** Fixtures hold real answers, trimmed (lists to 5 items, strings to 300 chars), with no cookies,
  tokens, session ids or personal data. Re-capture them from a running server, never hand-edit their shape.

## R-SETUP: environment and setup

- **R-SETUP-1 (MUST)** A change that adds a requirement (an env var, a package, a service, a port, a file the code
  needs, a Chrome / extension condition) adds its check to `scripts/check_setup.py`, its line to `.env.example`
  (what it is, where to get it, an example) and its step to `SETUP.md`, in the same commit.
- **R-SETUP-2 (MUST)** Per-machine values come from the environment / the repo-root `.env` (read by
  `config.load_env_file` and `naver_api_client.load_env_file`, never overriding the shell). Secrets live only in
  `.env` (gitignored): never in code, fixtures, docs or commits.

## R-DEP: dependencies

- **R-DEP-1 (MUST)** Keep `curl_cffi>=0.16,<0.17` in `server/requirements.txt`: 0.17.0 (Oct 2026) has its TLS handshake reset by some home ISPs (comment in requirements.txt).
- **R-DEP-2 (MUST)** All other requirements are unpinned, so every `pip install` is an upgrade. Run the live smoke (R-TEST-4) after one, and compare against the last verified versions recorded in KNOWN_ISSUES K-17 (update that table when a new set passes). Pinning is allowed with a decision entry. A Google Chrome auto-update on the Mac changes the browser under the box too; if box calls start failing, run the live smoke first.
- **R-DEP-3 (MUST NOT)** Do not add a dependency without adding it to `server/requirements.txt` in the same commit. `browserforge` is imported only when `PatchrightDriver(browserforge=True)`, which Naver never sets; enabling it requires adding it to requirements and a decision entry.

## R-TEST: tests

- **R-TEST-1 (MUST)** Tests are offline pytest, colocated as `test_*.py` next to the code. No network, no Chrome. Parser tests read captured fixtures from `naver_shopping/fixtures/` by name (`test_parsers.fixture`).
- **R-TEST-2 (MUST)** Every parser change or new upstream quirk gets a captured fixture and a test. A regression test carries a docstring with the dated observation.
- **R-TEST-3 (MUST)** Tests monkeypatch module attributes (`F.config`, `A._record`, `A.box_post`), so keep `import config` as a module import and call fetch helpers through module names that tests can patch.
- **R-TEST-4 (MUST)** Before merge:
  - `.venv/bin/python -m pytest -q` passes. Baseline: 158 tests (84 parser/schema tests + 8 in `test_pdp.py` + 11 in `test_review_select.py` + 7 in `test_search_filters.py` + 7 in `test_composite.py` + 6 in `test_ext_bridge.py` + 5 in `test_listing_jobs.py` + 5 in `test_ext_product.py` + 25 in `test_import_smoke.py`, which also asserts 34 routes). The count only goes up;
  - any change to transport or browser code (`fetch.py`, `browser_client.py`, `patchright_driver.py`, `url_blocking.py`, `egress.py`, `hostenv.py`, `config.py`, requirements) also passes a live smoke with the server running: `.venv/bin/python scripts/smoke_endpoints.py`, which covers at least one curl call and one box call. Record the result in the commit message.

## Checklist: adding a new endpoint

1. Find the upstream surface (R-NAVER-1, R-NAVER-2). Probe it, and write the dated finding as a comment where it will be handled.
2. Schema in `naver_shopping/schemas.py`, built from `schema_fields` fields, with `metadata={"description": ...}` and page limits. One reference param per entity (R-ARCH-3). Add a test in `test_schemas.py`.
3. A new reference kind: add `resolve_*` (and a link helper) in `naver_shopping/refs.py`.
4. A fetch function in `naver_shopping/fetch.py`: curl for open surfaces, box only for `/n/*`, using that transport's classifier (R-ERR-2).
5. Capture a fixture into `naver_shopping/fixtures/`, write a pure parser using the helpers (R-OUT-1), and test it.
6. In `naver_shopping/api.py`: a private impl plus a public function wrapped in `cached_call` with a new namespace and a new TTL in `cache_config.py`, or a slice of an existing bundle (R-CACHE-1, R-ARCH-7).
7. One row in `routes.ENDPOINTS` (serves both prefixes). Update the route count asserted in `test_import_smoke.test_routes_mounted`.
8. A row in [ENDPOINTS.md](ENDPOINTS.md); a line in ARCHITECTURE "Naver specifics" for new upstream facts (R-NAVER-4).
9. Consumer side: the answer's TypedDict in `scripts/naver_types.py`, a typed method in `scripts/naver_api_client.py`,
   a captured answer in `scripts/fixtures/` (+ its line in `scripts/test_naver_types.py` FIXTURES). Changing an
   existing answer's shape updates the same three, in the same commit.
10. Run pytest (server and `pytest scripts`), then the live smoke for the new endpoint (R-TEST-4).

## Checklist: changing transport or browser code

Scope: the files listed in R-TEST-4 (including `hostenv.py`, which picks the Chrome channel through `patchright_driver._in_container` and the timezone mechanism through `get_os`).

1. Read [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and the dated comments around the code you touch. If the change contradicts one of them, you need new evidence.
2. Keep the invariants: R-BOX-1 to R-BOX-13, R-HTTP-1 to R-HTTP-6, R-ERR-2, R-ERR-3.
3. Change one thing at a time. For anything that affects how Naver sees the client (headers, cookies, flags, identity, timing, proxy handling), run a live A/B against the current code on the same exit and write the dated result as a comment at the change.
4. If a MUST rule changes, add a Decision log entry in the same commit.
5. Run `.venv/bin/python -m pytest -q`, then start the server and run `.venv/bin/python scripts/smoke_endpoints.py`. A box change needs at least one `/products/details` on a smartstore product link; a curl change needs `/products/search` and one DataLab endpoint.
6. Update [ARCHITECTURE.md](ARCHITECTURE.md) if the flow changed, and [KNOWN_ISSUES.md](KNOWN_ISSUES.md) if an issue was fixed or found.

## R-EXT: the extension transport (beta)

- **R-EXT-1 (MUST NOT)** Never mint, copy, replay or forge a bot-defence token (`x-wtm-ncaptcha-token`,
  `cipherText`, `tokenId`) or call the defence SDK for our own requests. Listing calls are made by the page itself;
  we only trigger its own loading (real input) and read its answers.
- **R-EXT-2 (MUST)** The extension stays a dumb executor: generic ops, no site logic (no selectors, page paths or
  stop rules). Its only Naver-specific parts are the `*.naver.com` host scope in `manifest.json` and the `/ns/v1/`
  capture filter in `capture_main.js`. Paths, walls, stop rules and parsing live in Python (`ext_listing.py`,
  `naver_shopping/composite.py`).
- **R-EXT-3 (MUST)** A captcha / login gate: notify (`notify.py`) and wait for the human (60 s), never solve it.
  A ban page or a refused batch: stop, no retry. One listing at a time, sequential, at page speed.
- **R-EXT-4 (MUST)** Parsers are pure and tested on trimmed real captures with tracking / session fields removed
  (`fixtures/composite_*`). Captured raw answers and HARs never enter git.
- **R-EXT-6 (MUST)** Consumers reach the extension transport only through the HTTP routes (`/listings`,
  `/products/specs`), like every
  other endpoint: `scripts/` never import `ext_*` / `listing_jobs` and never talk to the bridge. A new kind of data
  read through the adapter becomes a server route (or job) first.
- **R-EXT-5 (SHOULD)** Bump the adapter version in `manifest.json` and `background.js` together on any change, and
  keep its op table in `extension/README.md` current.

## Decision log

One entry per MUST exception or rule change, newest first. Format:

```
### YYYY-MM-DD: <rule ID>: <short title>
What changes. Why. Evidence (A/B numbers, probe, test). Author.
```

### 2026-11-01: R-NAVER-1: smartstore product page through the owner's Chrome (beta)
`smartstore.naver.com/<store>/products/<id>` is read for its 상품정보 rows (`/products/specs`, `ext_product.py`), ONLY in
the owner's Chrome through the adapter, reached as a person does (naver.com -> 쇼핑 -> search -> click the card),
one page at a time and never while a listing job runs; never by curl, the box or a direct navigation. Why: the
seller's attribute rows (종류, 성별, 총클럽개수, 원산지 ...) are in none of the box answers (simple-products,
validation-products, contents, provided-notice); the backend's full product path
`/n/v2/channels/{uid}/products/{id}` answers 204 for a smartstore channel, `/i/v2/...` and `/n/v1/...` 404 (box probe
2026-11-01); a direct open in the owner's Chrome redirects to the login page, a click from the search renders the
page with the list (PING G440K, Honma D1, Callaway XR26 sets: 15 / 3 / 4 rows, as an independent capture had).
The adapter is unchanged (existing `click` / `query` / `page` ops); parsing is Python (`naver_shopping/pdp.py`).
Owner: Denis.

### 2026-11-01: R-NAVER-1: search.shopping listing through the owner's Chrome (beta)
`search.shopping.naver.com/ns/search` and its `/ns/v1/search/paged-composite-cards` are read, but ONLY in the
owner's own Chrome through the adapter (`extension/`, `ext_bridge.py`, `ext_listing.py`), never by curl, the
patchright box or a direct fetch. Why: the listing needs a one-time WtmCaptcha token per call that only the page
mints (HAR 2026-11-01); our fetch without it got 418, a fresh patchright Chrome got captchas and then a network ban,
the owner's Chrome with page-driven loading got 4/4 batches with HTTP 200 and the first batch from the HTML.
Details: [EXTENSION.md](EXTENSION.md). Owner: Denis.
