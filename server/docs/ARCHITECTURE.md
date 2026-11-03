# Architecture

How the server works. This file explains; it does not set rules. The binding
rules are in [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) and are linked here
by ID. Defects and contradictions are in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
The HTTP contract is in [ENDPOINTS.md](ENDPOINTS.md).

Citations name symbols (`module.function`, `module.CONSTANT`). A `~N` is a
line hint only and may drift. Dated upstream evidence lives in the code's
docstrings and comments; this file points at them and does not copy them.

## 1. Module map

All paths are relative to `server/`, which is the import root (section 10).

| Module | Role |
|---|---|
| `run.py` | Entry point. cheroot WSGI server on `0.0.0.0:config.PORT`, 16 threads, serving bottle's default app. |
| `main.py` | In-process demo: calls `naver_shopping.api` directly and writes `output/*.json` relative to the CWD. |
| `routes.py` | Mounts the 13 endpoints (`routes.ENDPOINTS`) at `/path` and `/naver-shopping/path`, plus the listing job routes (`routes.LISTING_PATHS`, both prefixes) and unprefixed `/` and `/health` (with the extension status). `routes.call` validates, runs, maps errors to HTTP. `routes.paginate` flattens pagination. |
| `schema_fields.py` | marshmallow base schema (`unknown=RAISE`), `load_query`, field types (`RefField`, `Flag`, page fields). |
| `scraper_errors.py` | Base taxonomy: `UpstreamError`, `Blocked(UpstreamError)`, `BadRequest`, `NotFound`. |
| `cache.py` | In-process TTL cache, `cached_call`. |
| `config.py` | `PORT`, retry constants, box constants, proxy getters, `exit_geo`. |
| `egress.py` | Accept-Language table and exit identity (`accept_language`, `exit_profile`, `TIMEZONE`). No network. |
| `hostenv.py` | Container / OS detection (`IS_DOCKER`, `IS_IN_KUBERNETES`, `get_os`). |
| `browser_client.py` | The browser box: one kept Chrome per proxy, warm-up, in-page fetch, refusal detection, `ExitPool`. |
| `patchright_driver.py` | `PatchrightDriver`: Chrome launch, owner thread, `nav`, `get`, `request`, `close`. Inherited multi-site driver; Naver uses a small part of it. |
| `url_blocking.py` | `compile_block_re`: the one abort-only route regex. |
| `naver_shopping/schemas.py` | One schema per endpoint, public-to-upstream enum maps, page limits. |
| `naver_shopping/refs.py` | Input resolvers (`resolve_product`, `resolve_store`, ...) and link builders/splitters. |
| `naver_shopping/api.py` | Endpoint functions: cache wrappers, shared bundles, request orchestration. |
| `naver_shopping/fetch.py` | The only module that talks to Naver: curl surfaces, box calls, error classification. |
| `naver_shopping/parsers.py` | Pure functions: raw JSON / HTML to output dicts. |
| `naver_shopping/review_select.py` | Pure: which reviews `/products/reviews/selected` keeps (tiers, caps). |
| `naver_shopping/cache_config.py` | One TTL per cached namespace, each with its reason. |
| `test_import_smoke.py`, `naver_shopping/test_*.py` | Offline tests (158 at the time of writing). Fixtures in `naver_shopping/fixtures/`. |

## 2. Layers

```
 HTTP client
     |
     v
 run.py  cheroot (16 threads) + bottle default app
     |
     v
 routes.call ----------------- schema_fields.load_query + naver_shopping/schemas.py
     |                          (refs.resolve_* turn links/ids into canonical links)
     v
 naver_shopping/api.py ------- cache.cached_call (TTLs: cache_config.py)
     |
     v
 naver_shopping/fetch.py
     |                                   |
     | curl surfaces                     | box surfaces (brand.naver.com/n/*)
     v                                   v
 curl_cffi Session                   browser_client.ExitPool.fetch_any
 (impersonate="chrome",              -> browser_client.fetch (per-proxy lock)
  one per thread)                    -> PatchrightDriver (owner thread)
     |                               -> real Chrome, in-page fetch()
     v                                   v
 ns-portal search, /<slug>/best,     Naver store backend
 brand PDP HTML, DataLab
     |                                   |
     +-------------> raw text/JSON <-----+
                          |
                          v
               naver_shopping/parsers.py (pure)
```

Layer order and who may talk to Naver: R-ARCH-1. Transport per surface:
R-NAVER-1, R-NAVER-2.

## 3. Request flow, end to end

### 3.1 Curl endpoint: `GET /products/search?query=...`

1. bottle dispatches to the handler made by `routes.mount`, which calls
   `routes.call("products/search", schemas.ProductsSearchSchema, api.products_search)`.
2. `routes.query_dict` reads the query with `getunicode` (Korean keywords);
   `schema_fields.load_query` validates it. A validation error returns 400
   here.
3. `api.products_search(**data)` -> `cache.cached_call("naver_shopping.search", data, api._search, SEARCH_CACHE)`.
   A hit returns a deep copy.
4. On a miss, `api._search` builds filters (`api._filters`: price bounds,
   category prefix = two-digit tree depth from DataLab via `api._category_filter`, boolean flags) and calls `fetch.fetch_search`.
5. `fetch._portal_json` runs `once()` under `fetch._retrying`:
   - `fetch._session()` returns this thread's curl_cffi session, creating it
     on first use (proxy, Accept-Language, widget ids, synthetic NNB cookie);
   - GET `ns-portal.shopping.naver.com/api/v3/shopping-paged-slot` with
     `fetch._widget_headers("mobile")` and `fetch.search_params`;
   - `fetch._classify` maps the status; a body without `data` is raised as
     `NaverUpstreamError` (retried on a fresh session).
6. `parsers.parse_search_slots` turns the slot pages into cards.
7. `fetch.fetch_search_count` makes a second ns-portal call (`/count`) with
   its own retry budget.
8. The result is cached and returned; `routes.call` serialises it. This
   endpoint is not paginated.

### 3.2 Box endpoint: `GET /products/details?product=https://smartstore.naver.com/<slug>/products/<id>`

1. `routes.call` validates with `schemas.ProductSchema`; `refs.resolve_product`
   returns the canonical product link.
2. `api.product_details` -> `api._record(product)` ->
   `cached_call("naver_shopping.product", ..., api._product_record, PRODUCT_CACHE)`.
3. `api._product_record`:
   - `refs.split_product_link` gives id, slug, host;
   - smartstore with a slug: `api._store(store_link(slug))` -> cached
     `naver_shopping.store` bundle -> `api._store_record` -> curl
     `fetch.fetch_store_page` (`/<slug>/best`) -> `parsers.parse_store_page`
     (channelUid, merchant id). If the first host gives `NaverNotFound` (a 404,
     or the brand host's "not operating" page) or an unparsable page, the
     other host is tried;
   - box call 1: `fetch.box_get` of `/n/v2/channels/<uid>/simple-products?ids[]=<id>`;
   - box call 2: `fetch.box_get_many` of four paths in one call:
     validation-products, contents, provided-notice, review product-summary.
4. Each box call goes `fetch._box_call` -> `ExitPool.fetch_any` ->
   `browser_client.fetch_any` -> `browser_client.fetch` (section 6), then
   `fetch._box_answer` classifies each answer.
5. Parsers build the record; `api.product_details` slices it into the
   response.

A cold call therefore costs one curl page, a Chrome launch and warm-up if no
Chrome is open, and two box calls (five in-page fetches). A brand product
link replaces the store page and the simple-products call with one curl GET
of the server-rendered brand product page (`fetch.fetch_brand_product_page`,
`parsers.parse_brand_product_page`). A slug-less `/main/products/<id>` link
adds a validation box call and a name search to find the store
(`api._find_store_for_product`).

## 4. Threading model

- **Request threads.** cheroot runs 16 worker threads (`run.main`). Each
  request runs synchronously on one of them, including retries and backoff
  sleeps.
- **Curl sessions.** One curl_cffi session per worker thread, held in
  `fetch._local` (a `threading.local`). It is never shared; it is dropped by
  `fetch._drop_session` on every retryable failure. R-HTTP-1.
- **Box serialisation.** `browser_client._browsers` holds one `_Browser` per
  proxy URL, each with its own `threading.Lock`. `browser_client.fetch` holds
  that lock for the whole call, including launch and warm-up. With the
  default single exit, every box call in the process is serialised behind
  one lock, whatever the thread count.
- **Owner thread.** Each `PatchrightDriver` starts one daemon thread
  (`PatchrightDriver._main`) that launches Chrome and runs every page
  operation from a job queue. Callers marshal work through
  `PatchrightDriver.call`, which waits at most `CALL_TIMEOUT` (90 s). Only
  plain data crosses threads. R-ARCH-6, R-BOX-7, R-BOX-13.
- **Cache.** `cache._lock` guards the dict only; the wrapped function runs
  outside it. Two concurrent identical misses both fetch.
- **Shared Xvfb (Linux only).** On Linux without `DISPLAY`, `patchright_driver._ensure_display`
  starts one process-wide virtual display. On macOS, the supported platform, it is a no-op
  and Chrome opens a real window.

## 5. The two transports

| | Curl | Box |
|---|---|---|
| Surfaces | ns-portal search and count, `/<slug>/best` store pages, brand product page HTML, DataLab | `brand.naver.com/n/v1/*` and `/n/v2/*` (store backend for any store, smartstore included) |
| Client | `curl_cffi.requests.Session(impersonate="chrome")` (`fetch._session`, `fetch.IMPERSONATE`) | Real Chrome via patchright, `fetch()` inside a brand.naver.com page |
| Entry points | `fetch._get`, `fetch._portal_json`, `fetch.fetch_datalab` | `fetch.box_get`, `fetch.box_get_many`, `fetch.box_post` |
| Classifier | `fetch._classify` | `browser_client._Browser.fetch_one` (refusals), then `fetch._box_answer` |
| Timeouts | `PAGE_TIMEOUT` 30 s, `JSON_TIMEOUT` 20 s | in-page `FETCH_TIMEOUT_MS` 30 s, owner-thread `CALL_TIMEOUT` 90 s |
| Retry | `fetch._retrying` | `fetch._box_call` |

Why the split: the store backend answers 429 to plain HTTP even with a
browser's cookies replayed, and Naver's own shopping pages are walled. Primary
record: the `browser_client` and `naver_shopping.fetch` module docstrings.

## 6. Box mechanics, step by step

1. **Pick a browser.** `fetch._box_call` calls `fetch._EXITS.fetch_any`
   (`ExitPool("naver-shopping", config.naver_shopping_browser_proxy, size=NAVER_SHOPPING_BROWSER_SLOTS)`).
   `ExitPool.all` returns the exit list (one slot by default);
   `browser_client.fetch_any` uses the first candidate's proxy.
2. **Lock.** `browser_client.fetch` gets the `_Browser` for that proxy
   (`browser_client._browser`, which also closes other proxies' Chromes idle
   longer than `BROWSER_IDLE`) and takes its lock.
3. **Launch** (only when no Chrome is open). `browser_client._launch` builds
   `PatchrightDriver(proxy, headless=False, geoip_timezone=bool(proxy), block_resources=["image","font","media"])`:
   - throwaway profile dir (`tempfile.mkdtemp`), removed on `close`;
   - channel `"chrome"` (always in a container; `PATCHRIGHT_CHANNEL` on a host);
   - images and fonts blocked by Chrome flags (`--blink-settings=imagesEnabled=false`,
     `--disable-remote-fonts`); media blocked by the one abort-only regex
     route from `url_blocking.compile_block_re`;
   - with a proxy: `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`,
     and Chrome's background hosts (`CHROME_BACKGROUND_HOSTS`) bypass the
     proxy;
   - locale and timezone as process settings (section 9);
   - the launched processes are recorded by pid-diff for force-kill on close.
4. **Warm-up.** `_Browser.warm` calls
   `driver.nav(ANCHOR, referer="https://www.naver.com/", mode="blocked")` with
   `ANCHOR = https://brand.naver.com/samsung/best`. `nav` runs goto,
   settle and DOM snapshot as one owner-thread op. Naver is not Cloudflare,
   so `_settle_challenge` returns None and `_settle_csr` runs. The warm-up
   raises `BoxRefused` (and closes Chrome) on: a goto failure, a
   `nid.naver.com` URL, a status in `REFUSE_STATUSES` (403, 405, 429, 490),
   a `WALL_MARKERS` hit in the first 8000 chars, or no `__PRELOADED_STATE__`
   in the HTML. R-BOX-2.
5. **Call.** `_Browser.fetch_one` strips identity headers
   (`_clean_headers`, `_DROP_PREFIXES`), leaving `fetch.BOX_HEADERS`, then
   calls `driver.get` or `driver.request`. These run `_FETCH_JS` through
   `page.evaluate`, which patchright runs in an isolated world by default
   (`isolated_context=True`, see `PatchrightDriver.evaluate`): the page's own
   scripts cannot see the call. The fetch uses `credentials:'include'`,
   `referrer=ANCHOR`, `referrerPolicy:'strict-origin-when-cross-origin'` and
   `AbortSignal.timeout(30 s)`; Chrome adds its own sec-* headers, cookies and
   TLS fingerprint. The JS never throws; it returns
   `{ok,status,url,body,headers,error}`, wrapped as `FetchResponse`.
   R-BOX-3, R-BOX-4, R-BOX-5, R-BOX-8.
6. **Batch.** A `urls=[...]` call (`box_get_many`) runs the URLs one after
   another inside the same lock, each as its own owner-thread op.
   `PatchrightDriver.get_many` (concurrent) is not used.
7. **Refusal check.** `fetch_one` raises `BoxRefused` for status 0 with an
   error, a `REFUSE_STATUSES` status, a wall marker in the body, or a
   `nid.naver.com` final URL. `browser_client.fetch` closes Chrome on
   `BoxRefused`; any other exception closes Chrome and becomes
   `BoxUnavailable`. R-BOX-10.
8. **Classification.** `fetch._box_answer` maps each answer: 204, 400, 404,
   419 -> None; 403, 405, 418, 429, 490 or captcha markers -> `NaverBlocked`;
   500, 502, 503, 504 or 0 -> `NaverUpstreamError`; otherwise JSON, or
   `NaverUpstreamError` when the body is not JSON.
9. **Keep-alive.** Chrome stays open between requests. It is relaunched
   after a refusal or failure, and closed when idle per step 2.

## 7. Retry topology

| Path | What is retried | How | Not retried |
|---|---|---|---|
| Curl (`fetch._retrying`) | `NaverUpstreamError` and its subclass `NaverBlocked` | up to `config.MAX_RETRIES` = 3 attempts; session dropped each time; sleep `RETRY_BACKOFF * attempt` (2 s, 4 s) on the request thread | `NaverNotFound`, `NaverBadRequest` (incl. DataLab 500) |
| Box (`fetch._box_call`) | `BoxRefused` | up to `config.NAVER_SHOPPING_BOX_ATTEMPTS` = 2 attempts; `ExitPool.rotate` on the refused proxy; no sleep; after the last attempt raises `NaverBlocked` | `BoxUnavailable` (raised at once as `NaverUpstreamError`); every `_box_answer` error |
| Store record (`api._store_record`) | host fallback, not a retry | `NaverNotFound` or an unparsable page on the first host moves to the other host | |
| HTTP layer (`routes.call`) | none | `Blocked` and `UpstreamError` -> 502; the client decides | |

Each curl call has its own budget, so an endpoint that makes several calls
(search + count, the four DataLab calls of `categories_trend`) retries each
one separately. With the default single exit, rotation re-mints the same
proxy URL; the retry gets a fresh Chrome and profile on the same exit.
Rules: R-HTTP-4, R-ERR-3. Gaps: KNOWN_ISSUES K-03 to K-06, K-10.

## 8. Cache

`cache.cached_call(namespace, data, fn, ttl)` keys on
`namespace + json.dumps(data, sort_keys=True)`, stores a deep copy, returns a
deep copy on hit, and never caches an exception. `MAX_ENTRIES` = 2000; when
full it drops expired entries, or else the 100 oldest inserted. Process
memory only; a restart empties it. R-CACHE-1, R-CACHE-3, R-CACHE-4.

| Namespace | TTL (`cache_config`) | Key | Read by |
|---|---|---|---|
| `naver_shopping.search` | `SEARCH_CACHE` 2 h | validated params | `/products/search` |
| `naver_shopping.search_count` | `SEARCH_COUNT_CACHE` 6 h | validated params | `/products/count` |
| `naver_shopping.product` (bundle) | `PRODUCT_CACHE` 6 h | `{"product": <canonical link>}` | `/products/details` (slices it), `/products/reviews` (reads ids and summary) |
| `naver_shopping.reviews` | `REVIEWS_CACHE` 6 h | product, page, sort | `/products/reviews` |
| `naver_shopping.store` (bundle) | `STORE_CACHE` 24 h | `{"store": <store link>}` | `/stores/details`, `/stores/products`, smartstore product records |
| `naver_shopping.store_products` | `STORE_PRODUCTS_CACHE` 12 h | validated params | `/stores/products` |
| `naver_shopping.catalog_reviews` | `CATALOG_REVIEWS_CACHE` 12 h | `{"catalog": id}` | `/catalogs/reviews` |
| `naver_shopping.keywords_rank` | `DATALAB_CACHE` 24 h | validated params | `/keywords/rank` |
| `naver_shopping.keywords_trend` | `DATALAB_CACHE` 24 h | validated params | `/keywords/trend` |
| `naver_shopping.categories_trend` | `DATALAB_CACHE` 24 h | validated params | `/categories/trend` |
| `naver_shopping.categories` | `CATEGORIES_CACHE` 7 d | `{"category": id}` | `/categories/list`, and the category check of every DataLab endpoint (`api._known_category`) |

The two bundles are why details + reviews on one product, or store details
+ store products on one store, cost one upstream fetch for the shared part.
R-ARCH-7.

## 9. Default identity, with and without a proxy

`NAVER_SHOPPING_PROXY` is the only identity input. Both getters
(`config.naver_shopping_proxy`, `config.naver_shopping_browser_proxy`) read it.

| | No proxy (default) | Proxy set |
|---|---|---|
| Curl egress | this machine's IP | the proxy |
| Curl Accept-Language | `en-US,en;q=0.9` (`egress.accept_language` -> `egress.DIRECT_COUNTRY = "us"`) | from the proxy URL's `__cr.<cc>` tag (`egress.exit_country`); a URL without the tag also gets `en-US` |
| Chrome geo lookup | none (`geoip_timezone=False`) | `config.exit_geo` via ip-api.com, through the proxy |
| Chrome language | no `--lang`; `PATCHRIGHT_LANG` if set, else Chrome's default | `--lang` and `--accept-lang` from `egress.exit_profile`: geo result first, else the URL tag; `PATCHRIGHT_LANG` if neither |
| Chrome timezone | host TZ | geo timezone, else `egress.TIMEZONE` for single-zone countries, else host TZ |

Locale and timezone go to the Chrome process (`--lang`, `--accept-lang`,
`TZ` in its environment), not to Playwright/CDP emulation; only Windows keeps
`timezone_id`. Primary record: the comments in `PatchrightDriver.__init__`
and `PatchrightDriver._main`. R-BOX-6.

A Korean identity therefore needs a Korean exit: for Chrome via the geo
lookup, for curl only via a `__cr.kr` tag in the URL. The no-proxy default is
what the code is run with today.

## 10. Config and environment

| Variable | Read in | Effect |
|---|---|---|
| `PORT` | `config.PORT` (import) | listen port, default 8000 |
| `NAVER_SHOPPING_PROXY` | `config.naver_shopping_proxy` (when a thread builds its curl session, `fetch._session`), `config.naver_shopping_browser_proxy` (when the box mints or rotates an exit, `fetch._EXITS`) | proxy for curl and Chrome; set before start; also read into `config.NAVER_SHOPPING_PROXY` at import, which nothing uses (K-15) |
| `PATCHRIGHT_CHANNEL` | `PatchrightDriver._main` | browser channel on a host; ignored in a container (always `"chrome"`, see `patchright_driver._in_container`) |
| `PATCHRIGHT_EXECUTABLE` | `PatchrightDriver._main` | used only when the channel resolves to `""` |
| `PATCHRIGHT_LANG` | `PatchrightDriver.__init__` | language fallback when no exit profile gives one |
| `PATCHRIGHT_DIRECT_HOSTS` | `patchright_driver._DEFAULT_DIRECT_HOSTS` (import) | hosts that bypass the proxy; default `CHROME_BACKGROUND_HOSTS` |
| `PATCHRIGHT_BROWSERFORGE_OS` | `PatchrightDriver._main` | only with `browserforge=True`, which `browser_client._launch` never sets |
| `ENV` | `hostenv.IS_PRODUCTION` | nothing reads it (K-14) |
| `DISPLAY` | `patchright_driver._ensure_display` | Linux without it: shared Xvfb is started |
| `KUBERNETES_SERVICE_HOST` | `hostenv.IS_IN_KUBERNETES` (import) | presence marks a container; `hostenv._is_docker` also checks `/.dockerenv` and `docker` in `/proc/self/cgroup`. `_in_container` = `IS_DOCKER or IS_IN_KUBERNETES` forces channel `"chrome"` |
| `LOCALAPPDATA` | `PatchrightDriver._main` | Windows paths in the Opera/Brave executable probe, used only when the channel resolves to `""`; not on the Naver path |
| `VM` | `hostenv.IS_VM` (import) | read, never used (K-14) |

Plain constants (edit in code): `config.MAX_RETRIES`, `RETRY_BACKOFF`,
`NAVER_SHOPPING_BROWSER_SLOTS`, `NAVER_SHOPPING_BOX_ATTEMPTS`;
`browser_client.ANCHOR`, `BROWSER_IDLE`, `REFUSE_STATUSES`, `WALL_MARKERS`;
`patchright_driver.CALL_TIMEOUT`, `FETCH_TIMEOUT_MS`, `GOTO_TIMEOUT_MS`,
`STARTUP_TIMEOUT`. Run details (macOS) are in `server/README.md`.

## 11. Import model

`server/` is the import root and has no `__init__.py`. Modules import each
other by bare name (`import config`, `from cache import cached_call`,
`from naver_shopping import api`). It is on `sys.path` because:

- `python server/run.py` puts the script's directory first;
- pytest gets it from `pythonpath = ["server"]` in the root `pyproject.toml`
  (`testpaths = ["server"]`);
- the retired Docker setup (`archive/docker/`) built with context `server/`; it is not maintained.

`naver_shopping/fetch.py` and the two `naver_shopping/test_*.py` files also
insert the parent directory (= `server/`) into `sys.path`; that duplicates
the above and is harmless. Heavy dependencies are imported lazily
(patchright in `browser_client._launch`, curl_cffi in `fetch._session`,
requests in `config.exit_geo`, egress / config / url_blocking inside
`PatchrightDriver`). `test_import_smoke.py` imports every library module by
bare name (`MODULES`; not the `run.py` / `main.py` entry points, `main.py`
creates `output/` at import) and checks the 34 routes. R-LAYOUT-1, R-LAYOUT-2, R-STYLE-5.

## 12. Extension transport (beta)

A third transport for what neither curl nor the box can read: the search.shopping listing, which needs a
one-time bot-defence token per call that only the page mints. The owner's own Chrome runs a thin adapter
(`extension/`), `ext_bridge.py` drives it over a local WebSocket, `ext_listing.py` walks naver.com -> 쇼핑 -> search
like a person, takes the first batch from the HTML and lets the page load the rest on wheel scrolls. The API
serves it as listing jobs (`listing_jobs.py`, `POST /listings`); `run.py` starts the bridge. A second use: a
product page's 상품정보 rows (`ext_product.py`, `GET /products/specs`), reached by a click from the search and parsed
in Python (`naver_shopping/pdp.py`); it shares one adapter lock with the listing jobs (`listing_jobs.with_adapter`).
Everything about it: [EXTENSION.md](EXTENSION.md); rules R-EXT-*.

## 13. Naver specifics

Each line is one upstream fact. The code comment or docstring named is the
primary record, with dates; read it before changing the behaviour.

- The ns-portal search widget answers whole pages of 24 only, at most 4: a
  slice matching 45 answers 24 cards, under 24 it answers all. Full listings
  need price slices until cards == `total_count`. -> `api.SEARCH_MAX_CARDS`
  comment; `scripts/harvest_listing.py` docstring.
- Store backend `brand.naver.com/n/*` answers 429 to any plain HTTP client,
  even with replayed cookies; it answers inside a real brand page, for any
  store. -> `browser_client` module docstring; `naver_shopping.fetch` module
  docstring (BOX).
- Naver's own shopping pages (search.shopping/ns, catalog pages, smartstore
  product page, shopping.naver.com) serve WtmCaptcha 405/490, a login
  redirect or a 429 page. -> `naver_shopping.fetch` module docstring.
- Search comes from the ns-portal widget backend; it needs the widget's
  `x-ns-*` headers and accepts any page/session id value, but refuses a
  request that carries none; TREND view on mobile gives 4 x 24 = 96 cards.
  -> `naver_shopping.fetch` module docstring (SEARCH); `fetch._session`
  comment; `api.SEARCH_MAX_CARDS` (a documentation constant, never read).
- ns-portal answers `{}` when the widget headers are refused.
  -> `fetch._portal_json` comment.
- Since 2026-10-29 ns-portal answers 418 without a naver.com cookie; one
  synthetic NNB per session passes; one NNB from several exits was refused.
  -> `fetch._session` comment, `fetch.nnb_cookie`.
- ns-portal ignores an open-ended price range. -> `api.OPEN_MAX_PRICE`
  comment (probed 2026-10-29).
- Category filters take a two-digit depth prefix (`04` + id for a level-4 category). -> `api._category_filter`
  docstring (SEARCH); `api._filters`.
- `/<slug>/best` is the server-rendered store page that carries the store
  record without a login redirect. -> `naver_shopping.fetch` module docstring
  (STORE).
- The brand host answers a non-brand slug with a "not operating" page.
  -> `fetch.fetch_store_page` docstring, `fetch.NOT_OPERATING_TITLE`.
- The brand product page is server-rendered (`__PRELOADED_STATE__`); an
  unknown product has its own title. -> `naver_shopping.fetch` module
  docstring (BRAND PDP), `fetch.NO_PRODUCT_TITLE`.
- Search results link products as slug-less `smartstore.naver.com/main/products/<id>`.
  -> `naver_shopping.refs` module docstring; `api._find_store_for_product`.
- The store backend answers an empty or unknown entity with 204, 400, 404 or
  419. -> `fetch._box_answer` docstring.
- The review backend reads only `reviewSearchSortType`; past the last page it
  answers 204. -> comments in `api._reviews`.
- DataLab answers bad parameters with a plain 500; an unknown category is
  turned into 404. -> `fetch.fetch_datalab` comment; `api._known_category`,
  `api._categories_list`.
- DataLab publishes once a day. -> `cache_config.DATALAB_CACHE` comment.
- Page depth limits: 500 review pages, 25 keyword-rank pages; DataLab data
  starts 2017-08-01. -> `schemas.MAX_REVIEW_PAGE`, `schemas.MAX_RANK_PAGE`,
  `schemas.DATALAB_FIRST_DAY` comments.
- Korean query strings need `getunicode`. -> `routes.query_dict` docstring.
- curl_cffi 0.17 has its TLS handshake reset by some ISPs. ->
  `server/requirements.txt` comment. R-DEP-1.
- CDP locale/timezone emulation is detectable; process-level settings are not
  (a dated Coupang A/B, not a Naver test). -> `PatchrightDriver.__init__`
  comment. R-BOX-6.

- A product page's seller attribute rows are in no box answer; `/n/v2/channels/{uid}/products/{id}` is 204 for a
  smartstore channel. -> `ext_product` module docstring. Decision log 2026-11-01.
- A smartstore product page opened directly redirects to the login page even in the owner's Chrome; a click from
  the search renders it. Its `__PRELOADED_STATE__` holds no product data when read; the rendered 상품정보 list does,
  folded after 9 rows behind "상품정보 펼쳐보기", and can render seconds after load. -> `ext_product` docstring and
  `read_page` comment, `pdp` module docstring.
- SmartEditor ONE descriptions have a blank `textContent` (`""` or `\u200b` runs); many are images only. ->
  `parsers.parse_contents` comment.
- Notice rows often hold a pointer instead of a value ("상품상세참조", "[상세설명참조]", "크기 항목 참조"). ->
  `parsers._SEE_DESCRIPTION_RE` comment.
- naverShoppingSearchInfo may carry only `manufacturerName` (no `brandName`) while the name carries the brand. ->
  `parsers.product_facts` docstring.

- The review backend (`query-pages`) serves at most 20 a page (50 / 100 answer 204; no `pageSize` gives 10) and
  filters by media with `reviewContentClassTypes` (PHOTO, VIDEO, TEXT; other keys ignored). -> `api.REVIEW_PAGE_SIZE`
  and `api._reviews` comments.
- A product page's review window loads reviews only on wheel input, 20 at a time, from the same `query-pages`; the
  backend answers the same filters directly. -> ENDPOINTS.md "Reviews: two ways".
- A product with no reviews has no review summary; the base record's count is 0. -> `api.product_reviews_selected`
  comment.
- A search card clicked at its centre can open the store instead of the product. -> `ext_product.read_page` comment.
- `images` from simple-products are the page's gallery (same files, same count) as original-file links; `?type=`
  renditions are re-encodes (`m10000_10000_no_rotate`) or 1000 px resizes (`o1000`, upscaling small photos). ->
  `parsers.parse_simple_product` comment, `scripts/naver_images.py` docstring.
- A review video attachment is `reviewAttachmentType` "M" with a `video/*` `mimeTypeName`; its URL is a poster
  frame. -> `parsers._attachment_type` docstring.
- A review writer without an avatar comes with the placeholder `profile-phinf.pstatic.net/404/default.png`. ->
  `parsers._DEFAULT_AVATAR_RE` comment.

- Since 2026-11-02 `/n/v1/validation-products/<id>` answers 419 (`SDW-E90419`) to the box; the product page's own
  product call carries a one-time page token (`x-client-rtk`) and the options come from that answer, read through
  the adapter. -> `ext_product._product_answer` docstring, `parsers.parse_page_options` docstring.
- A text the buyer types (CUSTOM option) is an `<input data-tag="textOption" id=<textOptions id> maxlength=...>`
  with `<label for=id>... (필수)</label>`; the purchase box renders twice (seen 2026-11-02). -> `pdp.text_fields`.

A new upstream fact gets a dated comment at the code that handles it and one
line here (R-NAVER-4).
