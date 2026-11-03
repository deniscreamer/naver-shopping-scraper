# Extension transport (beta): the search.shopping listing through the owner's Chrome

Status: **beta** (2026-11-01). Two jobs: the full search.shopping.naver.com listing for a query, served by
the HTTP API as listing jobs (`POST /listings`, [ENDPOINTS.md](ENDPOINTS.md#listing-jobs-beta-the-full-search-listing))
and runnable by hand (`server/ext_listing.py`); and a product page's 상품정보 rows (`GET /products/specs`,
`server/ext_product.py`, [below](#product-page-specs-products-specs)). Rules: [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) R-EXT-*, decision log 2026-11-01.

## Why an adapter at all

search.shopping.naver.com is protected by Naver's bot defence (WtmCaptcha, `ncpt.naver.com` +
`wtm.pstatic.net`). What the owner's HAR of 2026-11-01 shows:

- **Before every listing call the page mints a one-time token.** A WebAssembly module from `wtm.pstatic.net`
  collects browser and behaviour signals into an encrypted `cipherText` (~5.5 KB), the page POSTs it with a
  `siteKey` and timings to `ncpt.naver.com/v2/tokens`, gets `{tokenId}` and sends it as `x-wtm-ncaptcha-token`
  on `GET /ns/v1/search/paged-composite-cards`. A new token per batch.
- **Without that token the call is refused**: HTTP 418 with the page "쇼핑 서비스 접속이 일시적으로 제한되었습니다"
  ("shopping access temporarily restricted"). Measured: our own in-page `fetch` without it -> 418 at once.
- **Low-trust clients get a captcha, then a network ban.** A fresh patchright Chrome got a captcha on the shopping
  home and the search page; after many probes from one IP, the 418 page for the whole network (the owner's own
  browser included) for a while.
- **The owner's everyday Chrome passes**: real history and fingerprint, trusted input. A captcha at the entry can
  still happen and is solved by the owner.

So the listing is read in the owner's own Chrome, and **the page itself makes every listing call with its own
token**. We never mint, copy or replay a token or a `cipherText`: that would be defeating the bot defence, and it is
out of scope (R-EXT-1).

## How it works

```
scripts/ ──HTTP──► run.py: /listings ──► listing_jobs.py ──► ext_listing.walk ──► ext_bridge.py ──ws://127.0.0.1:8765──► extension/
                                          (one job, thread)   (all decisions)     (call(op, args))                       (owner's Chrome)
```

`run.py` starts the bridge at startup; the adapter connects to it and stays connected. `ext_listing.py` run by hand
starts its own bridge on the same port, so stop the API server first (or the port is taken).

1. **Way in, like a person.** `www.naver.com` -> mouse click on 쇼핑 (opens a new tab) -> click the shopping search
   box, type the query key by key, Enter -> the site routes to `search.shopping.naver.com/ns/search`. Clicks and
   keys go through `chrome.debugger` (trusted events; Chrome shows its "is debugging" bar).
2. **First batch from the HTML, no request.** The page is Next.js App Router: its data is in
   `self.__next_f.push([1, "..."])` chunks, and the object after `"initPagedCompositeCards":` is the first batch
   (`{hasMore, cursor, total, data}`, ~50 cards). Parser: `naver_shopping/composite.py` `first_batch`.
3. **Next batches by the page.** Wheel scrolls (debugger input) bring the list end into view; the page mints its
   token and fetches the next batch; `extension/capture_main.js` copies the answer body (page world wrapper around
   `fetch` / XHR for `/ns/v1/`), the adapter hands it over with `captures`. ~2-4 s per batch of 50; `cursor` grows
   by ~38 per batch. Until `hasMore=false`.
4. **Rows.** `composite.listing_row`: the canonical store link `https://{smartstore|brand}.naver.com/<slug>/products/<id>`
   (store from `mallUrl`'s `inflow/outlink?url=`, or a direct store link; cards without one are skipped), name, store, prices, category, reviews, stock, image,
   `is_ad` (`cardType == "AD"`). Deduplicated by `channelProductId` (ads repeat).

Tried and dropped (2026-11-01): our own in-page `fetch` per cursor (418: no token); a JS `scrollTo` to the end
(the page rendered its cards but fetched nothing: it wants real scroll input).

## Product page specs (`/products/specs`)

The second way to get product details ([ENDPOINTS.md](ENDPOINTS.md#product-details-two-ways)): richer than the
store backend and open to more fields later, since the whole rendered page is in hand, but each read walks the
full flow in the owner's Chrome.

The seller's attribute rows of a smartstore product (종류, 성별, 총클럽개수, 원산지 ...) are only on its product page
(decision log 2026-11-01). `ext_product.read_page`, all in Python over the existing ops:

1. `open_search(query)` as for a listing: naver.com -> 쇼핑 -> the search. Two ways in: a known product searches its
   full Korean name (the default `query`); a product from a listing uses that listing's search as `query` (its card
   is on the first search page only for the first rows; deeper ones fall back to the name). A category entry is not
   built yet.
2. The card: `a[href*="/products/<id>?"]` on the search page (cards link to
   `smartstore.naver.com/main/products/<id>?nl-query=...`); none -> 404. A click opens the product in a new tab;
   walls are checked as on the listing (`ext_listing.check`). A direct open of the product URL goes to the login
   page instead (2026-11-01), so it is never used.
3. Up to 8 reads, 2 s apart, until the 상품정보 list is rendered; then `button[data-shp-area="pdinfo.more"]`
   ("상품정보 펼쳐보기") is clicked when present (9 rows -> 15 on the PING set) and the page is read again.
4. The HTML (saved to `server/output/ext-product/<run>/product.html`, gitignored) goes to `naver_shopping/pdp.py`:
   rows found by the heading text 상품정보 and the `<li><div>label</div><div>value</div>` shape, not by the hashed
   class names. `parsers.product_facts` merges them with the box record (brand, manufacturer, model, origin, each with
   its source). All tabs it opened are closed.
5. **Options from the page's own answer** (2026-11-02). While the page loads, it fetches its product
   (`/i/v2/channels/<uid>/products/<id>` on smartstore, `/n/v2/.../products/<id>?withWindow=false` on brand) with a
   one-time page token (`x-client-rtk`); `capture_main.js` copies the answer (filter `/channels/` + `/products/`),
   `ext_product._product_answer` takes the 200 one for this id (up to 5 reads, 2 s apart: a page that got 419 reloads
   itself first) and `parsers.parse_page_options` turns it into `options` (variants with extra price, stock and
   `is_available`, text / simple options, add-ons). The answer is saved as `product.json` next to `product.html`.
   We never send that call or its token ourselves (R-EXT-1): the box's own `validation-products` call answers 419
   since that day. The page's server-rendered state has no options (`optionUsable` false, stock 0), so the answer
   is the only source.

One adapter user at a time: `listing_jobs.with_adapter` holds the same lock a listing job holds, so a read during a
listing answers 409 and a listing during a read 409. ~30-60 s a read; cached 24 h.

## Effects and limits

- **Everything runs as the owner**: their IP, cookies and account. Bursts get the network banned for Shopping,
  for their personal browsing too. Keep one listing at a time, sequential, at page speed.
- **Captcha**: reported through `server/notify.py` (`NAVER_NOTIFY_WEBHOOK`, else a macOS notification) and waited
  for 60 s while the owner solves it in that Chrome window; then the run stops. **Ban page / refused batch**: stop,
  never retried.
- Chrome must be open with the adapter loaded; the run drives its own tabs only.
- Coverage: `total` is the site's count for the query (4385 for 남성 골프채 풀세트, vs ~30k in the ns-portal widget:
  different search). No category filter yet.
- The adapter keeps the list of tabs it drives in its service-worker memory: if Chrome restarts the worker mid-run
  (extension reload, Chrome update), the run stops with an adapter error; start it again.
- Fragile points: the 쇼핑 shortcut selector, the search box selector, the RSC key name, the card fields.
  The offline tests pin the parsers to trimmed real captures.

## Run

Through the API (what scripts use): start `server/run.py`, check `/health` says `"extension": "connected"`, then
`POST /listings` (or `NaverApiClient.listing(query)`); output under `server/output/listings/<job_id>/`.

By hand (API server stopped):

```
.venv/bin/python server/ext_listing.py "남성 골프채 풀세트" --max-batches 3    # a short check
.venv/bin/python server/ext_listing.py "남성 골프채 풀세트" --out golf-mens   # the whole listing
```

Output: `server/output/ext-listing/<run>/listing.jsonl` + `summary.json` (gitignored; the summary is written on
every exit). Exit code 0 done or `--max-batches` reached; 1 stalled, layout changed (no search box / no first batch)
or an adapter error; 2 the extension did not connect; 3 a wall (captcha not solved, login gate, ban page, refused
batch). Install / reload the adapter: [extension/README.md](../../extension/README.md).

## Files

| File | Role |
|---|---|
| `extension/` | MV3 adapter: `background.js` (ops), `capture_main.js` + `relay.js` (answer copy) |
| `server/ext_bridge.py` | WebSocket bridge, 127.0.0.1, extension origins only |
| `server/ext_listing.py` | the listing walk (path, walls, scroll loop, output); also a CLI |
| `server/listing_jobs.py` | HTTP jobs: one at a time, a thread per job, status + rows for `/listings`; the adapter lock |
| `server/ext_product.py` | `/products/specs`: the product page read (search, card click, unfold) and its answer |
| `server/naver_shopping/pdp.py` | pure parsers: the 상품정보 rows, the description text walk |
| `server/naver_shopping/composite.py` | pure parsers (first batch, answers, rows) |
| `server/notify.py` | captcha / stop notifications (webhook or macOS) |
| tests | `test_ext_bridge.py`, `test_listing_jobs.py`, `test_ext_product.py`, `naver_shopping/test_composite.py`, `naver_shopping/test_pdp.py` (offline) |
