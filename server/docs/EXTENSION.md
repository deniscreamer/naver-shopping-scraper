# Extension transport (beta): the search.shopping listing through the owner's Chrome

Status: **beta** (2026-11-01). One job today: the full search.shopping.naver.com listing for a query
(`server/ext_listing.py`). Rules: [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) R-EXT-*, decision log 2026-11-01.

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
server/ext_listing.py ──► server/ext_bridge.py ──ws://127.0.0.1:8765──► extension/ (owner's Chrome)
   (all decisions)          (call(op, args))                            (dumb executor, no site logic)
```

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
| `server/ext_listing.py` | the listing job (path, walls, scroll loop, output) |
| `server/naver_shopping/composite.py` | pure parsers (first batch, answers, rows) |
| `server/notify.py` | captcha / stop notifications (webhook or macOS) |
| tests | `test_ext_bridge.py`, `naver_shopping/test_composite.py` (offline) |
