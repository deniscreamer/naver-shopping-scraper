# HTTP contract

This file is the public contract of the server. `scripts/` and any other client may rely on what is written here
and on nothing else: not on module names, not on cache internals, not on upstream Naver URLs.

Source of truth in code: `routes.ENDPOINTS` (paths), `naver_shopping/schemas.py` (params),
`schema_fields.py` (field behaviour), `naver_shopping/api.py` (output), `naver_shopping/cache_config.py` (TTLs),
`routes.call` / `routes.paginate` (errors, pagination). A change to any of these that is visible over HTTP updates
this file in the same commit.

## Basics

- All endpoints are `GET` with query-string params and answer JSON encoded as UTF-8 with Korean text unescaped. The
  `Content-Type` header is `application/json` with no `charset` parameter (`routes.json_response`).
- Each of the 11 endpoints is served at `/<path>` and at `/naver-shopping/<path>` (`routes.mount`). Both forms are
  equivalent; the unprefixed form (`/products/details`) matches the hosted RapidAPI paths, and `/naver-shopping/...`
  is an alias.
- `/` and `/health` exist only unprefixed (`routes.health`). `/naver-shopping/health` is a 404.
- Default base URL: `http://localhost:8000` (`config.PORT`).

```
GET /health  ->  {"status": "ok", "endpoints": ["/products/details", ..., "/listings", ...], "extension": "connected"}
```

### Param rules (all endpoints)

- Unknown params are rejected with 400 (`schema_fields.BaseSchema`, marshmallow `unknown=RAISE`). A typo never
  silently does nothing.
- Strings are whitespace-collapsed (`StrippedString`). An empty optional string or ref counts as missing; an empty
  required one (`query`, `keyword`, `product`, `store`, `catalog`, the DataLab `category`) is 400 `Must not be empty.`
  An empty boolean is `false`. An empty number or date is a format error (400).
- Booleans (`Flag`): `true/false`, `1/0`, `yes/no`, `y/n`, `on/off`, case-insensitive.
- Choices (`ChoiceField`) are case-insensitive. The public value is what you send; the server maps it to Naver's token.
- One param per input (`RefField`): `product`, `store`, `catalog` and `category` each take either a bare id or a
  Naver link, never a sibling `url` / `id` pair. Accepted forms are listed under "Reference params" below.
- Dates are `YYYY-MM-DD` and must be today or earlier (`DateField(bound="past")`).
- `page` is a 1-based integer (`PageField`, default 1).

### Reference params (`naver_shopping/refs.py`)

| Param | Accepted | Rejected |
|---|---|---|
| `product` (`refs.resolve_product`) | a channel product number (6-14 digits); `smartstore.naver.com/<store>/products/<id>`; `brand.naver.com/<store>/products/<id>`; `m.` hosts; scheme optional (`https://`, `http://`, `//` or none) | any other host, including `search.shopping.naver.com/catalog/...` and external malls |
| `store` (`refs.resolve_store`) | a slug (`bauato`); `smartstore.naver.com/<slug>`; `brand.naver.com/<slug>` | reserved paths (`main`, `products`, `search`, ...), so a `/main/products/<id>` link is not a store |
| `catalog` (`refs.resolve_catalog`) | a catalog id / nvMid (6-14 digits); a link whose host ends in `shopping.naver.com` with path `.../catalog/<id>` or query `nv_mid=<id>` / `nvMid=<id>`; scheme optional only for `*search.shopping.naver.com/` hosts | other hosts |
| `category` (`refs.resolve_category`) | `0` (root) or 8 digits starting with `5` (`50000003`) | anything else |

A bare product number resolves to the slug-less link `https://smartstore.naver.com/main/products/<id>`. See
"Search card links" for what that costs.

## Errors (`routes.call`)

Every error body is JSON with an `error` string. `<label>` is the path without the leading slash
(`products/details`).

| Status | When | Body |
|---|---|---|
| 400 | param validation failed (`schema_fields.load_query`) | `{"error": "Invalid parameters: <field>: <msg>; ...", "errors": {"<field>": ["<msg>", ...]}}` |
| 400 | a `ValueError` raised while serving | `{"error": "<message>"}` |
| 400 | Naver rejected the params (`BadRequest`, e.g. DataLab answering 500 to an impossible window) | `{"error": "naver-shopping rejected the request: <detail>"}` |
| 404 | product / store / catalog / category does not exist (`NotFound`) | `{"error": "<message>"}` (or `"not found"`) |
| 502 | blocked by Naver: captcha, login gate, 403/405/418/429/490 (`Blocked`) | `{"error": "naver-shopping blocked the request, retry later: <detail>"}` |
| 502 | transport failure, upstream 5xx, empty answer, Chrome could not start (`UpstreamError`) | `{"error": "naver-shopping <label> failed: <detail>"}` |
| 500 | anything else (parser surprise) | `{"error": "naver-shopping <label> failed: <ExceptionType>: <detail>"}` |

Validation examples (verified against the schemas):

```
?query=x&foo=1                 -> 400 {"error": "Invalid parameters: foo: Unknown field.", "errors": {"foo": ["Unknown field."]}}
?query=x&min_price=5&max_price=1 -> 400 errors.min_price = ["min_price must not exceed max_price."]
/products/reviews?product=123&page=501 -> 400 errors.product + errors.page ("... less than or equal to 500.")
/keywords/rank?category=0      -> 400 errors.category = ["DataLab needs a category: ..."]
```

Client policy: 400 and 404 are final, do not retry. 502 is retryable after a pause. If a 502 that says
`blocked the request` persists, Naver is refusing this machine's IP (set `NAVER_SHOPPING_PROXY`, see
`server/README.md`). If a 502 that says `failed: ... browser box unavailable` persists, Chrome cannot start on the
host; a proxy does not help. 500 is a server bug.

Outside the JSON contract: an unknown path gets bottle's own 404 HTML page, and a non-`GET` method on a known path
gets bottle's 405 HTML page.

## Pagination (`routes.paginate`)

Only `/products/reviews` and `/keywords/rank` are paginated. Their response is flattened: the pagination keys come
first, then the endpoint's own keys.

```
{
  "count": 1234,
  "per_page": 20,
  "current_page": 2,
  "total_pages": 62,
  "next": "http://localhost:8000/products/reviews?product=...&page=3",
  "previous": "http://localhost:8000/products/reviews?product=...&page=1",
  "...": "endpoint keys (results, summary, ...)"
}
```

- `count`: total items, or null when Naver publishes none. `next`: null on the last page. `previous`: null on page 1.
- `/products/reviews`: totals come from Naver. When Naver gives no `totalElements`, `count` is null but
  `total_pages` is `0` (not null) and `next` is null (`routes.paginate`). Past the end, if the backend answers 204
  (per the code comment in `api._reviews`; not verified live), the page has `results: []`, `count` / `total_pages`
  null and `next` null; `previous` is still set. If it answers 200 with no reviews instead, the real totals come
  back.
- `/keywords/rank`: Naver publishes no total, so `count` and `total_pages` are always null. `next` is set while the
  page held 20 keywords and `page < 25`.
- `next` / `previous` are absolute URLs built from the request's own scheme and host (`routes._page_link`). Behind a
  reverse proxy they can point at the wrong host. For `/products/reviews`, `next` is not capped at
  `MAX_REVIEW_PAGE` (500).
  **Paginate by incrementing `page` yourself** and stop when `next` is null or `results` is empty; do not follow
  `next` as a URL.

## Caching

Results are cached in process memory, keyed on the validated params (`cache.cached_call`). There is no
cache-bypass param; a restart clears everything. TTLs are from `naver_shopping/cache_config.py`. Some endpoints share
an internal bundle (the store record, the product record), so a second endpoint on the same store or product is
cheaper. Errors are never cached.

## Transports

- **curl**: plain HTTPS with a Chrome TLS fingerprint (curl_cffi); a block or transport error gets up to 3 attempts in all.
- **box**: an in-page `fetch()` inside a real, headed Google Chrome parked on a brand.naver.com page. Needs Google Chrome
  installed on the Mac. Slower; calls on one Chrome run one at a time. Up to 2 attempts
  (`config.NAVER_SHOPPING_BOX_ATTEMPTS`), and only when the box refuses the call; a refusal rotates (relaunches)
  the Chrome it used.
  A Chrome that cannot start, a box 5xx, a block status or a non-JSON answer is not retried server-side
  (`server/docs/KNOWN_ISSUES.md`, K-05), so clients should retry a 502.

## Endpoints

### `/products/search`

Up to 96 search cards for a keyword (the widget's 4 pages x 24; there is no deeper paging and no `page` param).
Only whole pages of 24 come back: when `total_count` is 45 you get 24 cards, 67 gives 48; under 24 you get all.
To list everything, narrow `min_price`/`max_price` until the card count equals `total_count`
(`scripts/harvest_listing.py` does this).

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | string, required | | 1-200 chars |
| `min_price`, `max_price` | number >= 0 (KRW) | none | `min_price <= max_price`; an open bound is filled server-side |
| `category` | category ref | none | restrict to a category id at any depth (the depth prefix comes from DataLab, cached 7 d; unknown id -> 404; `0` = no filter) |
| `min_rating` | choice | none | only `4.8` |
| `free_delivery`, `fast_delivery`, `arrival_guarantee`, `brand_store`, `official_mall`, `membership_benefit` | bool | none | `true` filters; `false` = no filter |

Transport: curl (two calls: cards + total count). Cache: 2 h (`SEARCH_CACHE`).
Output: `{query, filters (applied, or null), total_count, count (cards returned), results: [card]}`. Card keys:
`id` (nvMid), `product_id`, `origin_product_id`, `catalog_id`, `name`, `link`, `type` (`product` / `catalog` /
`ad`), `is_ad`, `rank`, `pricing`, `images`, `store` (null for catalog cards), `mall_count` (catalog cards),
`purchase_options`, `reviews`, `purchase_count`, `keep_count`, `category`, `delivery`, `promotion_types`, and
`is_*` / `has_*` flags (`parsers.parse_search_card`).

```
curl "http://localhost:8000/products/search?query=raspberry%20pi&max_price=100000&free_delivery=true"
```

### `/products/count`

Same params as `/products/search` (same schema). Transport: curl (one call). Cache: 6 h (`SEARCH_COUNT_CACHE`).
Output: `{query, filters, total_count}` (`total_count` may be null).

```
curl "http://localhost:8000/products/count?query=raspberry%20pi"
```

### `/products/details`

| Param | Type | Default | Notes |
|---|---|---|---|
| `product` | product ref, required | | see "Reference params" |

Transport: curl for the store page (smartstore) or the product page (brand), then box for the product JSON. A
slug-less link or bare number costs extra calls (see "Search card links"). Cache: 6 h (`PRODUCT_CACHE`, the product
record shared with `/products/reviews`; store record 24 h).
Output: the product record (`id`, `origin_product_id`, `name`, `link`, `catalog_id`, `catalog_link`, `status`,
`pricing`, `stock_quantity`, `images`, `category`, `brand`, `delivery`, flags, ...) plus `option_groups`, `variants`,
`supplements`, `description` (`{html, text, editor_type, images}`), `notice` (`{type, items, terms}`), `reviews`
(the review summary: counts, `average_score`, `score_counts`, `evaluations`, `representative_reviews`) and `store`
(`id, uid, name, slug, link, type, grade, sale_count, merchant_id, business`). Any section Naver did not answer is
null.

```
curl "http://localhost:8000/products/details?product=https://smartstore.naver.com/dailyromantic/products/8087042745"
```

### `/products/reviews` (paginated)

| Param | Type | Default | Notes |
|---|---|---|---|
| `product` | product ref, required | | |
| `page` | int | 1 | 1..500 (`MAX_REVIEW_PAGE`), 20 reviews a page |
| `sort` | choice | `ranking` | `ranking`, `recent`, `score_high`, `score_low` |

Transport: box (plus the product record, as in `/products/details`). Cache: 6 h per page (`REVIEWS_CACHE`).
Output: pagination keys + `{product: {id, name, link}, sort, summary, results: [review]}`. Review keys: `id`,
`score`, `text`, `created_at`, `type`, `content_type`, `option`, `is_repurchase`, `is_free_trial`, `event_title`,
`writer`, `attachments`, `product`, `likes`.

```
curl "http://localhost:8000/products/reviews?product=8087042745&page=2&sort=recent"
```

### `/stores/details`

| Param | Type | Default | Notes |
|---|---|---|---|
| `store` | store ref, required | | |

Transport: curl only (the store's `/<slug>/best` page; brand host first for brand links, else smartstore first).
Cache: 24 h (`STORE_CACHE`).
Output: the store record (`id`, `uid`, `name`, `slug`, `link`, `type`, `description`, `image`, `grade`,
`sale_count`, `merchant_id`, `business`, `social`, flags, ...) plus `categories` (nested store category tree).

```
curl "http://localhost:8000/stores/details?store=dailyromantic"
```

### `/stores/products`

| Param | Type | Default | Notes |
|---|---|---|---|
| `store` | store ref, required | | |
| `list` | choice | `popular` | `popular` (20) or `best` (up to 30 per period) |
| `period` | choice | `daily` | `realtime`, `daily`, `weekly`, `monthly`; used only with `list=best` |

Transport: curl (store record) + box (the list). Cache: 12 h (`STORE_PRODUCTS_CACHE`; store record 24 h).
Output: `{store: {id, uid, name, slug, link}, list, period (null for popular), count, results: [product record]}`.
Product `link`s here always use the smartstore host, also for brand stores (see `server/docs/KNOWN_ISSUES.md`).

```
curl "http://localhost:8000/stores/products?store=bauato&list=best&period=weekly"
```

### `/catalogs/reviews`

| Param | Type | Default | Notes |
|---|---|---|---|
| `catalog` | catalog ref, required | | |

Transport: box. Cache: 12 h (`CATALOG_REVIEWS_CACHE`). Not paginated: a sample of reviews, as Naver serves it.
Output: `{catalog_id, link, count, results: [{id, score, text, created_at, writer, mall_name, product_id,
catalog_product_id, option, attachments}]}`. A catalog with no reviews is a 404.

```
curl "http://localhost:8000/catalogs/reviews?catalog=61626354397"
```

### DataLab window params

Shared by `/keywords/rank`, `/keywords/trend` and `/categories/trend` (`schemas._DatalabWindow`):

| Param | Type | Default | Notes |
|---|---|---|---|
| `start_date` | date | 31 days ago | not before `2017-08-01`; not after `end_date` |
| `end_date` | date | yesterday | today or earlier |
| `period` | choice | `daily` | `daily`, `weekly`, `monthly` |
| `device` | choice | both | `pc`, `mobile` |
| `gender` | choice | both | `male`, `female` |
| `age` | comma list | all | any of `10,20,30,40,50,60` |
| `category` | category ref, required | | must not be `0`; an unknown id is a 404 |

All three echo the window: `category_id, start_date, end_date, period, device, gender, age` (public values;
`device` / `gender` / `age` are null when not set; `age` is a list of strings such as `["20", "30"]`), plus
`category_name`. Transport: curl (DataLab form POSTs). Cache: 24 h (`DATALAB_CACHE`; the
category lookup 7 days).

### `/keywords/rank` (paginated)

Window params + `page` (int, default 1, 1..25 = `MAX_RANK_PAGE`, 20 keywords a page, top 500).
Output: pagination keys + window echo + `{category_name, results: [{rank, keyword}]}`.

```
curl "http://localhost:8000/keywords/rank?category=50000002&page=2"
```

### `/keywords/trend`

Window params + `keyword` (string, required, 1-100 chars).
Output: `{keyword, ...window echo, category_name, series: [{date, value}]}`; `value` is Naver's relative click
index, copied as a float (100 = peak per the `parsers.parse_datalab_series` docstring; not verified here).

```
curl "http://localhost:8000/keywords/trend?keyword=laptop&category=50000003&period=weekly"
```

### `/categories/trend`

Window params only. Four DataLab calls (plus the category lookup, cached 7 days).
Output: `{...window echo, category_name, category_path, series: [{date, value}], device_share, gender_share,
age_share}`; each share is `[{code, label, ratio}]`.

```
curl "http://localhost:8000/categories/trend?category=50000003&device=mobile&age=20,30"
```

### `/categories/list`

| Param | Type | Default | Notes |
|---|---|---|---|
| `category` | category ref | `0` | `0` lists the top-level categories |

Transport: curl (DataLab). Cache: 7 days (`CATEGORIES_CACHE`). Unknown id: 404.
Output: `{id, name, parent_id, level, path, is_leaf, order, count, children: [same keys without children]}`.

```
curl "http://localhost:8000/categories/list?category=50000003"
```

## Listing jobs (beta): the full search listing

The whole search.shopping.naver.com listing for a query (~50 products per batch, all batches), read on the server
through the owner's Chrome (extension transport, [EXTENSION.md](EXTENSION.md)); callers see only these routes.
Both prefixes. One job at a time.

| Route | Params | Answer |
|---|---|---|
| `POST /listings` | `query` (1-100 chars, required), `max_batches` (0-200, 0 = all) as query params | `202` job; `409 {error, job_id}` another job runs; `503` the browser extension is not connected; `400` bad params |
| `GET /listings/<job_id>` | - | job: `{id, query, status, max_batches, batches, kept, ads, total, cursor, has_more, stop, started_at, finished_at}`; `404` unknown |
| `GET /listings/<job_id>/products` | `page` (1-1000) | rows, 50 a page, the usual pagination shape (works while the job runs: rows so far) |

`status`: `running`; `captcha` (the owner is asked to solve one in Chrome; waits 60 s); `done` (`hasMore=false` or
`max_batches` reached); `stopped` (`stop` says why: a wall, a refused batch, a stall, an adapter error).
`/health` adds `extension: connected | disconnected | off`.

A row: `{product_id, nv_mid, link, name, store {name, slug, link, grade, is_brand_store}, pricing {sale_price,
discounted_price, discount_ratio, currency}, category_id, reviews {count, average_score}, stock_quantity, image,
is_ad, query, batch, seen_at}`. `link` is the canonical store product link `/products/details` takes. Unique by
`product_id`; ads are kept and flagged.

```
curl -X POST "http://localhost:8000/listings?query=%EB%82%A8%EC%84%B1%20%EA%B3%A8%ED%94%84%EC%B1%84%20%ED%92%80%EC%84%B8%ED%8A%B8&max_batches=3"
curl "http://localhost:8000/listings/<job_id>"
curl "http://localhost:8000/listings/<job_id>/products?page=1"
```

Client: `scripts/naver_api_client.py` `NaverApiClient.listing(query)` starts, polls and returns every row.

## Search card links

A card's `link` (`parsers.parse_search_card`) is one of three shapes:

| Card | `link` | Use with |
|---|---|---|
| Naver store product (`type: product`) | `https://smartstore.naver.com/main/products/<id>` (slug-less) | `/products/details`, `/products/reviews` |
| Catalog (`type: catalog`) | `https://search.shopping.naver.com/catalog/<id>` | `/catalogs/reviews` (or pass `catalog_id`) |
| External mall product or ad | the mall's own URL or a click-bridge URL (11st, lotteon, coupang, ...) | nothing; `/products/*` rejects it with 400 |

- `/products/details` accepts only smartstore / brand links or a bare number (`refs.resolve_product`). A catalog
  link sent as `product` is a 400.
- A slug-less link carries no store. The server then reads the product name, searches it, and takes the store of the
  card with the same `product_id`. This costs extra calls and fails with 404 when the product is not in the search
  index. When the card's `store.link` is a smartstore / brand store link, building
  `<store.link>/products/<product_id>` and sending that skips the lookup.
- `store.link` may also be an external mall URL; only smartstore / brand store links are valid for `/stores/*`.
