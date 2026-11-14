# Extension transport (beta): the search.shopping listing through the owner's Chrome

Status: **beta** (2026-11-01). Two jobs: the full search.shopping.naver.com listing for a query, served by
the HTTP API as listing jobs (`POST /listings`, [ENDPOINTS.md](ENDPOINTS.md#listing-jobs-beta-the-full-search-listing))
and runnable by hand (`server/ext_listing.py`); and a product page's 상품정보 rows (`GET /products/specs`,
`server/ext_product.py`, [below](#product-page-specs-products-specs)); since 2026-11-14 a third, a listing tab held
open between calls whose products are read by a click on their cards (`POST /listing-tabs`, `server/ext_listing_tab.py`,
[below](#held-listing-tab-listing-tabs)). Rules: [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) R-EXT-*, decision log 2026-11-01.

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
   by ~38 per batch. Until `hasMore=false`. Before each next batch the walk rests (`ext_listing.BATCH_REST_S`,
   3-7 s; every `REST_EVERY` = 10 batches `LONG_REST_S`, 20-40 s; the owner, 2026-11-12): a deep read is spread
   out, ~8 min per 50 batches more.
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

1. The search tab (2026-11-07, the owner: one product per iteration of a job): the tab of the previous read is kept and
   searched again by its own box (`ext_listing.search_again`: click `input[class*="_searchInput_search_text"]`,
   click the visible clear button `button[class*="_searchInput_button_clear"]` (typing without it inserts at the
   caret), type, Enter); only when there is no such tab (first read, gone, another page) `open_search(query)` as
   for a listing: naver.com -> 쇼핑 -> the search. Two ways in: a known product searches its
   full Korean name (the default `query`); a product from a listing uses that listing's search as `query` (its card
   is on the first search page only for the first rows; deeper ones fall back to the name). A category entry is not
   built yet.
2. The card: `a[href*="/products/<id>?"]` on the search page (cards link to
   `smartstore.naver.com/main/products/<id>?nl-query=...`); none -> 404. The card's photo is clicked
   (`img[class*="productCardThumbnail_image"]` in the `product_card` element whose child is that link; the link
   itself when there is no photo): the store's name link lies mid-card and opened the store, then the login page
   (2026-11-05, `ext_product._card`). The click opens the product in a new tab;
   walls are checked as on the listing (`ext_listing.check`). A direct open of the product URL goes to the login
   page instead (2026-11-01), so it is never used.
3. Up to 8 reads, 2 s apart, until the 상품정보 list is rendered; then `button[data-shp-area="pdinfo.more"]`
   ("상품정보 펼쳐보기") is clicked when present (9 rows -> 15 on the PING set) and the page is read again.
4. The HTML (saved to `server/output/ext-product/<run>/product.html`, gitignored) goes to `naver_shopping/pdp.py`:
   rows found by the heading text 상품정보 and the `<li><div>label</div><div>value</div>` shape, not by the hashed
   class names. `parsers.product_facts` merges them with the box record (brand, manufacturer, model, origin, each with
   its source). Every tab the adapter drives but the search tab is closed (the product tab), so Chrome is back on the
   search tab; the server log says `tabs left: 1 (search tab kept)`.
   A **login gate** (nid.naver.com) on the way is not waited for (the owner 2026-11-07: there is no account, and the
   naver.com path resets the session): `ext_listing.check` raises `LoginGate`; `open_search` closes its tabs and
   takes the path again (twice), a product read closes every tab and reads once more from naver.com; a second gate
   is a wall (503 `wall:`). Nothing is ever typed on the login page. A captcha still waits for the owner.
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

## Held listing tab (`/listing-tabs`)

The way `scripts/job.py scroll` reads products (the owner, 2026-11-14; [ENDPOINTS.md](ENDPOINTS.md#held-listing-tabs-beta-listing-tabs)):
one listing tab, opened as for a listing job (`open_search`, the first batch from the HTML), kept open between HTTP
calls and walked one batch per `next` (`rest`, then wheel scrolls, as `walk`); a product of the current batch is read
by a click on its card in that tab (`ext_product._read_card`, the same read as step 2-5 above without the search) and
its tab closed, so Chrome is back on the listing. Probed 2026-11-14 (module docstring): every click opened a new tab,
scrolls after clicks and after 22 min idle brought the next batch, the current batch's cards are always in the DOM
while older ones leave it (a virtualized list: a product is read right after its batch came, never later), and the
last batch carries `hasMore=false` (no scroll after it). Before a click (`steady=True`) the card is wheeled to the
middle of the viewport with the generic `scroll` op and its rect read with `query` until two reads 400 ms apart agree;
the opened URL must be `/products/<id>`, else that tab is closed and the card clicked once more; still another
product -> 404 `card_opened_other` (a plain click opened another product 2 times in 16 while the page inserted a
batch; this one 0 in 30). A click that opened nothing is not repeated (the listing tab may be navigating in place):
404 `card_opened_nothing`, the session lives. No extension change.

- **One session**, `ext_listing_tab._session`. It holds the adapter lock (`listing_jobs._adapter`) from open to
  close: a listing job or a `/products/specs` read meanwhile answers 409, the text naming the tab and its DELETE
  (`listing_jobs.holder`, `who()`). A new open closes the previous session first (its caller is gone, or it is the
  same job opening again), every adapter tab with it.
- **The session lock** (`ext_listing_tab._lock`): `next` and `specs` never wait for it (409), open and close do, so a
  call left running on the server after a client's Ctrl+C (a captcha wait is up to 600 s) cannot close the next
  session's tabs or free the adapter twice.
- **410 is the one "session gone" signal**: unknown id, a server restart, the listing tab closed or no longer a
  search page, an adapter error on it, a login gate, a card that opened in the listing tab itself. The caller opens
  a new tab from the top and skips what it has done. Walls as for a listing (R-EXT-3): a ban, a refused batch or a
  stall end the session (503 `wall:`); a captcha not answered on a product page closes only that page's tab
  (`wall: captcha ...`, the session lives).
- **No idle timer**: a session whose caller died without DELETE holds the adapter until the next open, a DELETE
  (`curl -X DELETE localhost:8000/listing-tabs/<id>`) or a server restart. `job.py` closes it in a `finally`, SIGTERM
  included.

## Effects and limits

- **Everything runs as the owner**: their IP, cookies and account. Bursts get the network banned for Shopping,
  for their personal browsing too. Keep one listing at a time, sequential, at page speed.
- **Captcha**: the adapter saves a screenshot, the page and the question (`ext_listing.captcha_question`), puts the
  cursor in the answer field, reports it through `server/notify.py` (`NAVER_NOTIFY_WEBHOOK`, else a macOS
  notification; the `ext-listing: CAPTCHA ... question: ...` log line is what an agent watching the run relays to the
  owner's chat) and waits `NAVER_CAPTCHA_WAIT_S` (600 s) while the owner answers it in that Chrome window, at the Mac
  or from a phone through a remote-desktop app. A new captcha after a wrong answer is reported again; when the page
  shows no captcha the run goes on, else it stops. Nothing is ever typed into a captcha by the code (R-EXT-3).
  **Ban page / refused batch**: stop, never retried.
- Chrome must be open with the adapter loaded; the run drives its own tabs only.
- Coverage: `total` is the site's count for the query (4385 for 남성 골프채 풀세트, vs ~30k in the ns-portal widget:
  different search). No category filter yet.
- The adapter keeps the list of tabs it drives in its service-worker memory: if Chrome restarts the worker mid-run
  (extension reload, Chrome update), the run stops with an adapter error; start it again.
  A held listing tab is then not in the adapter's list any more (`owned` in `background.js`): the session answers
  410 and the next open cannot close that tab, so it stays open in Chrome; the owner closes it.
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
| `server/ext_listing_tab.py` | `/listing-tabs`: the held listing tab session (open, next batch, a product by its card, close) |
| `server/naver_shopping/pdp.py` | pure parsers: the 상품정보 rows, the description text walk |
| `server/naver_shopping/composite.py` | pure parsers (first batch, answers, rows) |
| `server/notify.py` | captcha / stop notifications (webhook or macOS) |
| tests | `test_ext_bridge.py`, `test_listing_jobs.py`, `test_ext_product.py`, `test_ext_listing_tab.py`, `naver_shopping/test_composite.py`, `naver_shopping/test_pdp.py` (offline) |
