# scripts/

Client-side consumers of the Naver Shopping API. Everything here talks to a
running server over HTTP only.

## Boundary

- Scripts call the server's HTTP endpoints, as documented in
  `server/docs/ENDPOINTS.md`. They never import server modules: no
  `__init__.py`, no `sys.path` edits. The reasons:
  - The server needs a headed Chrome window (macOS).
  - The server owns the cache, the curl retries and the exit rotation.
  - Importing `routes` registers bottle routes as a side effect.
- The only exception is in a test. `test_naver_api_client.py` borrows
  `naver_shopping.schemas` to check the client's page caps against the server's
  limits, and `naver_shopping.parsers` to check the harvest classifier against
  the server's committed search fixture (both via `pytest.importorskip`).
- `naver_api_client.py` is the single gateway. Every script goes through
  `NaverApiClient`.
- `requirements.txt` holds only `requests`, so scripts run on a machine
  without Chrome or patchright. The offline tests also need `pytest`, which
  the server venv has.

| File | Purpose |
|---|---|
| `naver_api_client.py` | `NaverApiClient` (`get`, `pages`, `health`) and `ApiError` |
| `smoke_endpoints.py` | Live smoke: `/health` plus 11 endpoints (all but `/products/specs`), one at a time. Networked. |
| `example_search_harvest.py` | Template: search, classify the cards, fetch details, write resumable JSONL |
| `test_naver_api_client.py` | Offline tests for the client and the classifier |
| `example_0N_*.py` | Runnable examples, one API topic each (see Examples) |
| `harvest_listing.py` | Full listing of store product links for a keyword + category, price-sliced, resumable |
| `output/` | Run output (`output/<run>/products.jsonl`, `listing.jsonl`), gitignored |

## Product details: two ways

Two ways to get a product's details:

| | 1. `/products/details` (the original way) | 2. `/products/specs` (the new way, beta: the adapter) |
|---|---|---|
| Source | the store backend (`brand.naver.com/n/*`) in the server's own Chrome | the product page itself, in the owner's Chrome through the adapter |
| Gives | prices, options, stock, category path, legal notice, description, reviews, `facts` from the backend's search info and the notice | the page's 상품정보 rows: 제조사, 브랜드, 모델명, 원산지 and every seller attribute (종류, 성별, 총클럽개수, ...), `facts` with those rows first |
| Cost | ~1-10 s, any product, no setup | ~30-60 s a product, one at a time, Chrome open with the adapter, not during a listing job |
| Flexible | fixed set of backend answers; no attribute rows exist there | anything rendered on the page can be read later the same way (Python parses the page HTML) |

The catch of way 2 is the path. The adapter cannot open a product page directly (Naver redirects that to the
login page), so every read walks the whole flow like a person: naver.com -> the shopping home (쇼핑) -> a search
-> click the product's card -> the product opens in a new tab -> unfold the list. Two ways in:

- **A known product**: search its full Korean name (the default `query`) and click the card whose link carries
  its id (`example_10_known_products_specs.py`, `example_08_product_full.py`).
- **Products not known yet**: take them from a search (a listing job), then read each with that search as `query`;
  a card not on the search's first page falls back to its name (`example_09_listing_then_specs.py`).
  Entering through a category page is not built yet (the listing has no category filter either).

Use both together: way 1 for prices / options / reviews, way 2 for the attribute rows.
Contract: [server/docs/ENDPOINTS.md](../server/docs/ENDPOINTS.md#product-details-two-ways).

## Reviews: two ways

Reviews come from the store backend in both ways (no adapter): the same JSON a product page loads in its review
window (`query-pages`), so photo links are originals, product ids are checked and avatars are known.

| | 1. `/products/reviews` (every review) | 2. `/products/reviews/selected` (the ones worth showing) |
|---|---|---|
| Gives | one page of 20, any sort (`ranking`, `recent`, `score_high`, `score_low`), `media` filter (`all`, `photo_video`, `text`) | up to `count` (20) chosen reviews: 50+ letters + photo + real avatar first, then photo + text, then text; all with text when the product has 20 or fewer; at most 8 photos a review, 100 a product |
| Cost | ~0.4 s a page after the record | reads only the pages it needs, newest first: photo/video pages, then text-only pages (Honma D1, 202 reviews: 11 pages, ~5 s) |

Why not through the product page (researched 2026-11-01 on the Honma D1 set): the review window opens from the
"N건 리뷰" link, takes the 최신순 / 포토/동영상 radios, and loads 20 more reviews only on wheel input (~5 wheels and
~4 s a page) after the whole search -> card -> page walk in the owner's Chrome; its answers are this same
`query-pages` JSON, and copying them would need an adapter change. The rendered rows carry only thumbnails and no
product ids. The backend answers the same filter directly (`reviewContentClassTypes`), so the page adds nothing for
reviews.

## Examples: start here

Small, runnable scripts, one topic each, in the order to read them. Start `server/run.py` first; examples 7-10 and 99 also
needs Chrome open with the adapter (`example_01` shows `extension: connected`).

| Script | Shows |
|---|---|
| `example_01_health.py` | `api.health()`: the server is up, the extension status, the endpoint list |
| `example_02_search.py` | `api.get()` with filters: `/products/count` + `/products/search` (up to 96 cards) |
| `example_03_product_details.py` | `/products/details`: prices, options, stock, review stats of one product |
| `example_04_reviews.py` | `api.pages()`: `/products/reviews` page by page |
| `example_05_store.py` | `/stores/details` + `/stores/products` (best-sellers) |
| `example_06_datalab.py` | `/keywords/rank` + `/keywords/trend` (Naver DataLab) |
| `example_07_listing_then_details.py` | `api.listing()`: the full search listing (server: your Chrome via the adapter), then `/products/details` for its rows (server: its own Chrome). Two transports, one API |
| `example_08_product_full.py` | One product as complete as it gets (a golf club set): `product_details()` + `product_specs()` -> the 상품정보 rows, brand / manufacturer / model / origin with their sources, category, the legal notice (pointer rows marked), the description text |
| `example_09_listing_then_specs.py` | Like example 7, details the new way: a listing, then `product_details()` + `product_specs(link, query=<the listing's search>)` per product (name fallback). Collecting products not known yet |
| `example_10_known_products_specs.py` | Known product links -> `product_specs(link, query=<full Korean name>)`: the card is matched by its id on that search page |
| `example_11_reviews_full.py` | `api.reviews()` read completely: every review field in the store's order (id, score, date, full text, option, likes, writer, photo / video links and sizes), the product summary, JSONL to `output/reviews-<id>/` |
| `example_12_reviews_selected.py` | Reviews, way 2: `selected_reviews()` -> up to 20 reviews worth showing (photo + text + avatar first), with the tier of each, JSONL |
| `example_99_full_details.py` | **FULL**, the one to grow: a category's products (listing + category id), each in turn -> details + 상품정보 specs (adapter) + selected reviews, one JSON line per product |

```sh
.venv/bin/python scripts/example_01_health.py
.venv/bin/python scripts/example_07_listing_then_details.py
```

All calls go through `naver_api_client.NaverApiClient`. Typed methods, one per endpoint, return the shapes in
`naver_types.py`: `health()`, `search(query, **filters)`, `count(...)`, `product_details(product)`,
`product_specs(product, query)`, `reviews(product, sort, max_page, media)` (pages), `selected_reviews(product, count)`, `store_details(store)`, `store_products(store, list, period)`,
`catalog_reviews(catalog)`, `categories(category)`, `keywords_rank(category, **window)` (pages),
`keyword_trend(keyword, category, **window)`, `category_trend(category, **window)`, `listing(query, max_batches)`.
The generic `get(path, **params)` / `pages(path, **params)` reach any route. Any non-200 raises
`ApiError(status, error, errors)`.

## Response types (`naver_types.py`)

TypedDicts for every answer (83 names: `SearchCard`, `ProductDetails`, `ReviewsPage`, `ListingRow`, ...). `X | None`
means the server may send null: guard it (`product["reviews"]` can be None). They were written from real answers
(`fixtures/*.json`, captured live 2026-11-01) and the server's parser code; `test_naver_types.py` checks each
fixture against its type strictly (missing or unknown keys fail).

```sh
.venv/bin/python -m pytest scripts -q                      # includes the type conformance test
.venv/bin/pip install mypy && .venv/bin/python -m mypy --ignore-missing-imports --check-untyped-defs \
    $(ls scripts/*.py | grep -v /test_)   # static check of every script (tests excluded)
```

When a server answer changes shape: re-capture its fixture (one call with the client, json.dump, lists trimmed to
5 items, long strings to 300 chars), update the type, and commit both with the server change.

## Running

Start the server first, in another terminal:

```sh
.venv/bin/python server/run.py          # http://localhost:8000
```

Then run the scripts:

```sh
.venv/bin/pip install -r scripts/requirements.txt    # requests; already present in the server venv
.venv/bin/python scripts/smoke_endpoints.py          # --delay 5 --base-url http://localhost:8000
.venv/bin/python scripts/example_search_harvest.py "raspberry pi" --limit 10 --out pi
.venv/bin/python scripts/harvest_listing.py "남성 골프채 풀세트" --category 50002788 --out golf-mens
.venv/bin/python -m pytest scripts -q                # offline; not part of the default `pytest` run
```

## Conventions

- **Typed calls.** Use the typed client methods (`api.search()`, `api.product_details()`, `api.listing()`, ...) and
  the shapes in `naver_types.py`; guard every `X | None` field (`product["reviews"]`, `product["variants"]`, names).
  Run mypy on what you write (see Response types). Rules: server/docs/DEVELOPMENT_RULES.md R-TYPE.
- **Sequential by default.** The server keeps one Chrome per proxy
  (`config.NAVER_SHOPPING_BROWSER_SLOTS = 1`), and box calls serialize on that
  Chrome's lock. Parallel calls just queue up inside the server (cheroot has
  16 threads) and make blocks more likely. Add a pause (`--delay`) for long
  runs.
- **Lean on the server cache.** A repeat call within the TTL is free. TTLs are
  in `server/naver_shopping/cache_config.py`, from 2 h for search to 7 d for
  the category list. `/products/details` and `/products/reviews` share one
  cached product record (`api._record`), so calling reviews after details
  costs no extra fetch.
- **Status handling** (`routes.call`):
  - `404`: the entity does not exist. Skip it and log it.
  - `400`: the input is wrong. Fix the script; do not retry.
  - `502`: blocked or an upstream failure. Back off. The client retries twice
    (10 s, 30 s).
  - `500`: a server parser bug. Report it.
  - Read timeout: the server is still working. Do not retry blindly, because
    the retry would queue duplicate work behind the same Chrome.
  - Connection errors: the client retries only a failure to open the
    connection (`ConnectTimeout`, or refused / DNS). requests also raises
    `ConnectionError` for a dropped connection or a read timeout mid-body,
    after the request was sent; those are raised, not retried.
- **Pagination.** Use `client.pages()`. It increments `page` until `next` is
  null or `results` is empty, stops at the schema cap (500 for
  `/products/reviews`, 25 for `/keywords/rank`, also under the
  `/naver-shopping/` prefix), and treats a 400 whose `errors` name `page` as
  the end once a page was yielded; any other 400 raises. It never follows
  the absolute `next` URL. The server builds that URL from its own request
  host, which is wrong behind a proxy.
- **Config from env, no secrets in files.**
  - `NAVER_API_URL` (default `http://localhost:8000`)
  - `NAVER_API_READ_TIMEOUT` (default 900 s; the connect timeout is 5 s)
- **Naming.** One script per job, with an argparse CLI. Module names must not
  collide with server top-level modules (`config`, `cache`, `routes`, `main`,
  `run`, `browser_client`, ...), because pytest puts `server/` on `sys.path`.
- **Style.** Follow the server's style:
  - a module docstring that says why;
  - `# ---- section ----` banners;
  - `print("<script>: ...")` with a prefix;
  - no type hints.

## Link semantics for harvesting

The `link` on a `/products/search` card (`parsers.parse_search_card`) is one
of three kinds:

| Card | `link` | What to do |
|---|---|---|
| Store product (`type` `product`/`ad`) | slug-less `https://smartstore.naver.com/main/products/<product_id>` | Call `/products/details` with `<store.link>/products/<product_id>` |
| Catalog (`type` `catalog`) | `https://search.shopping.naver.com/catalog/<catalog_id>` | `/catalogs/reviews?catalog=<catalog_id>`, or skip |
| External mall | another host, e.g. `link.coupang.com` | Skip and log |

Do not pass the slug-less `/main/products/<id>` link to `/products/details`. It
forces the server through validation, then a name search, then the matching
card's store (`api._find_store_for_product`). That path is slow and can 404.
For Naver store cards, `store.link` is `https://smartstore.naver.com/<slug>`
or `https://brand.naver.com/<slug>`. For external-mall cards it is the
external URL, or null when `mallUrl.pcUrl` is missing (`parsers._store_link_from_mall_url`).
The harvest classifier is `example_search_harvest.classify_card`. It skips
external links, a store link without a real slug (e.g. `.../main`, a
reserved segment in `refs._RESERVED_SLUGS`) and a product id outside 6-14
digits, all of which `/products/details` would reject. A 400 that still comes
back is logged and counted as failed; the run continues.

In the committed fixture `server/naver_shopping/fixtures/search_slots.json`,
the 96 cards break down as:

- 55 smartstore `/main/` products;
- 40 catalogs;
- 1 `link.coupang.com` card.

## Listing harvest (`harvest_listing.py`)

Collects every Naver store product link for a keyword (+ optional category at any depth), past the search's
96-card ceiling, as `output/<run>/listing.jsonl` (one line per unique product: canonical link, name, store,
pricing, category, reviews, purchase count, first image, raw card) plus a `state.json` checkpoint.

- **Slicing.** One `/products/search` call per price slice. The widget answers whole pages of 24 only, so a slice
  is done when its cards reach its `total_count`; otherwise it is split into up to 8 equal parts and searched again.
  Cards from every call are kept. A one-price slice that still falls short is listed as `saturated` (partial).
- **Filter.** Only smartstore.naver.com / brand.naver.com products are kept, with the link
  `<store.link>/products/<product_id>` that `/products/details` takes (`example_search_harvest.classify_card`).
  Catalog cards and external malls (Coupang, Gmarket, 11st, Auction, SSG, ...) are dropped and counted once.
- **Pace.** Sequential, `--delay 3` s by default; `--max-requests N` bounds a run and the same `--out` resumes it.
  Exit code 0 = done, 3 = paused with ranges pending.
- **Cost.** About one call per 12 matches: verified live 2026-11-01 on 남성 골프채 풀세트 / 50002788 / 0-57,220 KRW,
  433 matches in 35 calls, 192 store products + 241 external = 433 (complete). The whole category (~29k men's sets)
  is roughly 2,400 calls, about 2-2.5 hours at 3 s. `--min-price` cuts the cheap tail, where external malls and
  accessories dominate.

## Full search listing through the API (`api.listing`)

The whole search.shopping listing for a query (all batches, not capped at 96, no price slicing), as rows with the
canonical store link. The server reads it in the owner's Chrome; a script only sees HTTP:

```python
from naver_api_client import NaverApiClient
out = NaverApiClient().listing("남성 골프채 풀세트", max_batches=3)   # 0 = all
out["job"]["status"], out["job"]["stop"], len(out["results"])
```

`ApiError` 409: another listing runs (one at a time); 503: the browser extension is not connected. A stopped job
still returns its rows. Contract: server/docs/ENDPOINTS.md "Listing jobs".

## Shopify roadmap

This is a design note only. There is no code yet.

The pipeline: harvest JSONL (`output/<run>/products.jsonl`), then map each
record to a Shopify product, then export.

Draft mapping from a `/products/details` record:

| Shopify | Naver (`/products/details`) |
|---|---|
| title | `name` |
| body_html | `description` |
| vendor | `store.name` (or `brand`) |
| images | `images` |
| options / variants | `option_groups` / `variants` |
| price | `pricing` (KRW; conversion TBD) |
| tags | `category`, `tags` |

Open decisions:

- Export through a CSV import or through the Admin GraphQL `productSet`.
- Image hosting: hotlink Naver's CDN or re-upload.
- Currency and price conversion.
- Whether options beyond Shopify's variant limits are split or dropped.

Credentials will come from env as `SHOPIFY_STORE` and `SHOPIFY_ADMIN_TOKEN`.
They are never committed.

When the work starts, add `scripts/shopify/` as a package (mapper + exporter)
that reads the harvest JSONL. Until then it stays this section, with no stub
code.
