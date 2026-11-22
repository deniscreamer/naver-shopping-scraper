# Collecting from the API

What the scripts collect through the API and how: product details, options, photos, reviews, the listing screen and
the shop check, the examples, the answer types and listing harvests. All calls go over HTTP through
`naver_api_client.NaverApiClient` (`scripts/` never imports server modules, AGENTS.md rule 3). Contract:
[server/docs/ENDPOINTS.md](../server/docs/ENDPOINTS.md); blocks and 502s:
[server/docs/KNOWN_ISSUES.md](../server/docs/KNOWN_ISSUES.md); a whole category as a job: skill `run-a-job`.

## How to use

Start the server first (`.venv/bin/python server/run.py`). Examples 7-10, 14, 15 and 99, and every
`/products/specs` or listing read, also need Chrome open with the adapter (`example_01` shows
`extension: connected`). From the repo root:

```sh
.venv/bin/python scripts/example_01_health.py                 # the server is up, the extension status, the endpoints
.venv/bin/python scripts/example_07_listing_then_details.py   # then the example closest to the task
.venv/bin/python scripts/harvest_listing.py "<query>" --category <id> --out <name>   # every store link for a keyword
.venv/bin/python -m pytest scripts -q                          # offline, includes the type conformance test
.venv/bin/python -m mypy                                       # offline, 0 errors expected
```

| Task | Section |
|---|---|
| Which script or client method to start from | [Examples: start here](#examples-start-here) |
| A product's details: the backend record or the page (`/products/specs`) | [Product details: two ways](#product-details-two-ways) |
| Options: free / paid / sold-out variants, text options, add-ons | [Product options](#product-options) |
| Photos: gallery, review photos, avatars, video posters (`naver_images.py`, WebP) | [Product photos](#product-photos) |
| Reviews: every review or the ones worth showing | [Reviews: two ways](#reviews-two-ways) |
| Screen listing rows, "already in the shop", the deferred journal | [The listing screen and the shop check](#the-listing-screen-and-the-shop-check) |
| Which link of a search card to pass on | [Link semantics for harvesting](#link-semantics-for-harvesting) |
| Every store link for a keyword, past the 96-card ceiling | [Listing harvest](#listing-harvest-harvest_listingpy) |
| The whole search listing in the owner's Chrome | [Full search listing through the API](#full-search-listing-through-the-api-apilisting) |
| Probe a category's listing before rules or a pilot: queries, title words, the page's filters, adjacent leaves | `scripts/listing_probe.py`; [ONBOARDING.md](ONBOARDING.md) "B0. Probe the listing" (a listing job's answer carries `sort`, `default_total` and the page's `filters` since 2026-11-22) |
| An answer's shape changed (`naver_types.py`, fixtures) | [Response types](#response-types-naver_typespy) |
| Check a run against product pages, replay one offline | [Checking a run against product pages](#checking-a-run-against-product-pages) |
| What sellers write on their pages | [SELLER_DATA.md](SELLER_DATA.md) |

What a call can answer, and what to do (`ApiError(status, error, errors)`; full triage: skill `api-error-triage`):

| Result | Means | Do |
|---|---|---|
| 200 (202 for a started listing job) | the answer, typed in `naver_types.py` | guard every `X \| None` field |
| `ApiError` 400 | the input is wrong (e.g. a store link without a real slug) | fix the call ([Link semantics](#link-semantics-for-harvesting)); a harvest logs it, counts it failed and goes on |
| `ApiError` 404 | details: a bare id or slug-less link (since 2026-11-02); specs: the card was not on that search page | skip, or read specs again with another `query` (the name first, the listing's query on a 404) |
| `ApiError` 409 | the adapter is busy: a listing job, a `/products/specs` read, another listing (one at a time) | wait and retry once the other call is done (the check run: every 30 s, up to 12 times) |
| `ApiError` 500 | a server parser bug | report it (skill `api-error-triage`) |
| `ApiError` 502 | blocked / upstream failure; the client already retried twice (10 s, then 30 s) | KNOWN_ISSUES.md; skill `api-error-triage` |
| `ApiError` 410 | a held listing tab is gone (`/listing-tabs/<id>/next` or `/specs`: closed, replaced, the server restarted, ...) | final for that tab: never retry it, open a new one |
| `ApiError` 503, error `wall: ...` or no kind (the extension not connected) | a wall in the owner's Chrome (captcha, login gate, ban page, a refused batch or stall), or no adapter | final: stop, never retry (a retry after a wall risks a ban, R-EXT-3; [ENDPOINTS.md](../server/docs/ENDPOINTS.md#errors-routescall) "Errors" client policy); not connected: `example_01`, tell the owner; a listing tab's `wall: captcha ...` only: the tab is kept and may be read again |
| `ApiError` 503, error `naver error page: ...` or `adapter error: ...` | Naver's internal-error page (K-21, passes in minutes) or a failed read (e.g. the page did not render) | wait ~120 s and retry, at most twice, then skip and read it again at the end |
| `harvest_listing.py` exit 0 / 3 | done / paused with ranges pending | 3: run again with the same `--out` |
| `ShopNotConfigured`, `CatalogError` | the shop check cannot answer (no store values or credentials; another shop, a bad or doubled key) | ask the operator; never treat it as "not there" |
| a product `deferred` | partial twice | not taken again; only the owner allows one retry (`deferred_log.py allow`) |

A shape change updates the type in `naver_types.py`, its fixture and the client method together (R-TYPE in
[server/docs/DEVELOPMENT_RULES.md](../server/docs/DEVELOPMENT_RULES.md)). Tests never hit the network. Never use the
session's browser tools on Naver during a job ([OWNER_RULES.md](OWNER_RULES.md) section 3).

## Examples: start here

Small, runnable scripts, one topic each, in the order to read them. Start `server/run.py` first; examples 7-10, 14, 15
and 99 also need Chrome open with the adapter (`example_01` shows `extension: connected`).

| Script | Shows |
|---|---|
| `example_01_health.py` | `api.health()`: the server is up, the extension status, the endpoint list |
| `example_02_search.py` | `api.get()` with filters: `/products/count` + `/products/search` (up to 96 cards) |
| `example_03_product_details.py` | `/products/details`: prices, stock, review stats of one product (its `variants` are null since 2026-11-02: options come from `/products/specs`, way 2) |
| `example_04_reviews.py` | `api.pages()`: `/products/reviews` page by page |
| `example_05_store.py` | `/stores/details` + `/stores/products` (best-sellers) |
| `example_06_datalab.py` | `/keywords/rank` + `/keywords/trend` (Naver DataLab) |
| `example_07_listing_then_details.py` | `api.listing()`: the full search listing (server: your Chrome via the adapter), then `/products/details` for its rows (server: its own Chrome). Two transports, one API |
| `example_08_product_full.py` | One product as complete as it gets (a golf club set): `product_details()` + `product_specs()` -> the 상품정보 rows, brand / manufacturer / model / origin with their sources, category, the legal notice (pointer rows marked), the description text |
| `example_09_listing_then_specs.py` | Like example 7, details the new way: a listing, then `product_details()` + `product_specs(link, query=<the listing's search>)` per product (name fallback). Collecting products not known yet |
| `example_10_known_products_specs.py` | Known product links -> `product_specs(link, query=<full Korean name>)`: the card is matched by its id on that search page |
| `example_11_reviews_full.py` | `api.reviews()` read completely: every review field in the store's order (id, score, date, full text, option, likes, writer, photo / video links and sizes), the product summary, JSONL to `output/reviews-<id>/` |
| `example_12_reviews_selected.py` | Reviews, way 2: `selected_reviews()` -> up to 20 reviews worth showing (photo + text + avatar first), with the tier of each, JSONL; their photos and avatars as the store's WebP (`download_review_media()`) |
| `example_13_product_images.py` | A product's gallery: `product_details()["images"]` -> `naver_images.download_gallery()` -> the store's WebP files, manifest.json with source and result of each |
| `example_14_product_options.py` | A product's options from the page (`product_specs()["options"]`) and the variants we take (`choose_variants`, `paid` as argument), on real golf sets: no options, free combinations, a text option with a sold-out row, a paid sold-out row |
| `example_15_description_collect.py` | **One golf full set end to end, its description included**: the first new screened card of 남성 골프채 풀세트 (or a product link as argument) -> details, specs and options, variants, five package fields, reviews and photos -> kept in its own folder (`output/description-example/shops/`, the operator's runs untouched) -> description images read (OCR) -> prepared (prepared/2): prints the notes, the five fields with where each came from, the page text and the images' text for translation. Needs the server and the adapter; ~2-4 min |
| `example_99_full_details.py` | **FULL**, the one to grow: a category's products (listing, screened: rental, another category, already in the shop, deferred), each in turn under the run rules -> details + 상품정보 specs and options (adapter) + variants + five shipping fields + selected reviews + gallery and review photos (video posters as photos) as the store's WebP, one JSON line per product. Needs the shop's credentials file (`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`) and the category's averages |

```sh
.venv/bin/python scripts/example_01_health.py
.venv/bin/python scripts/example_07_listing_then_details.py
```

All calls go through `naver_api_client.NaverApiClient`. Typed methods, one per endpoint, return the shapes in
`naver_types.py`: `health()`, `search(query, **filters)`, `count(...)`, `product_details(product)`,
`product_specs(product, query)`, `product_page(product, query)`, `captcha()`, `reviews(product, sort, max_page,
media)` (pages), `selected_reviews(product, count)`, `store_details(store)`, `store_products(store, list, period)`,
`catalog_reviews(catalog)`, `categories(category)`, `keywords_rank(category, **window)` (pages),
`keyword_trend(keyword, category, **window)`, `category_trend(category, **window)`, `listing(query, max_batches)`,
`listing_tab_open` / `listing_tab_next` / `listing_tab_specs` / `listing_tab_close`.
The generic `get(path, **params)` / `pages(path, **params)` reach any route. Any answer but 200 / 202 raises
`ApiError(status, error, errors)`.

## Product details: two ways

Two ways to get a product's details:

| | 1. `/products/details` (the original way) | 2. `/products/specs` (the new way, beta: the adapter) |
|---|---|---|
| Source | the store backend (`brand.naver.com/n/*`) in the server's own Chrome | the product page itself, in the owner's Chrome through the adapter |
| Gives | prices, stock, category path, legal notice, description, reviews, `facts` from the backend's search info and the notice (options: null since 2026-11-02) | the page's 상품정보 rows: 제조사, 브랜드, 모델명, 원산지 and every seller attribute (종류, 성별, 총클럽개수, ...), `facts` with those rows first; `options` (variants, stock, add-ons) |
| Cost | ~1-10 s, any product, no setup | ~30-60 s a product, one at a time, Chrome open with the adapter, not during a listing job |
| Flexible | fixed set of backend answers; no attribute rows exist there | anything rendered on the page can be read later the same way (Python parses the page HTML) |

The catch of way 2 is the path. The adapter cannot open a product page directly (Naver redirects that to the
login page), so a read walks the flow like a person: naver.com -> the shopping home (쇼핑) -> a search -> click the
product's card -> the product opens in a new tab -> unfold the list. The search tab is kept (2026-11-07): the next
read types its search into that tab's box and skips naver.com; the product tab is closed after each read. Two ways in:

- **A known product**: search its full Korean name (the default `query`) and click the card whose link carries
  its id (`example_10_known_products_specs.py`, `example_08_product_full.py`).
- **Products not known yet**: take them from a search (a listing job), then read each with that search as `query`;
  a card not on the search's first page falls back to its name (`example_09_listing_then_specs.py`).
  A category page is not used: it needs a signed-in Naver account (probed 2026-11-14, every level of the 카테고리
  menu lands on nid.naver.com); a listing is a search, the category is the screen's.

Use both together: way 1 for prices / reviews / description, way 2 for the attribute rows and the options.
Contract: [server/docs/ENDPOINTS.md](../server/docs/ENDPOINTS.md#product-details-two-ways).

## Product options

Since 2026-11-02 the options come only from way 2: `api.product_specs(link)["options"]` (null when the page gave no
product answer). Every variant the store declared is there with `extra_price` (added to the product's price;
negative = cheaper) and `stock_quantity` / `is_available` (false = sold out, shown as (품절), cannot be bought).
Besides the variants: `text_options` (a text the buyer types, e.g. a name on the bag tag: its `label`, `required`
and `max_length` from the page's field), `simple_options`, and
`supplements` (add-on products, not variants).

Which variants we collect is one rule for every store and category, `naver_variants.choose_variants(options,
base_price, paid=False)`:

| | default (`paid=False`) | `paid=True` (the operator's choice, e.g. for a category where it is wanted) |
|---|---|---|
| extra price 0 | taken | taken |
| extra price != 0 (more or less) | left out, counted in `skipped_paid` | taken, `price` = product price + extra price |
| name states another amount, "(+N원)" | left out, its id in `name_mismatches` | taken, `price_in_name` shows it |
| sold out | kept, `is_available` false, counted in `sold_out` | the same |

An amount in a name counts only as "(+N원)" / "(-N원)": a bare "+" joins the parts of a set ("드라이버+우드",
"실버블루 + 실버블루"). Example: `example_14_product_options.py` (real golf sets, one per case).

## Product photos

`/products/details` `images` is the product's gallery: the seller's photos in order, main photo first, as links to
the original files (no `?type=` rendition). Checked 2026-11-01: the same files and count as the gallery on the
product page, so no page, adapter or zoom viewer is needed. Review photo links (`attachments`) are originals too;
`writer.profile_image` is the avatar (null for Naver's placeholder). Videos are never downloaded: a review video's
poster (the frame the API links; never a made-up URL) is a photo of the review. The server counts it as a photo when
it chooses reviews, `download_review_media` saves it as a `review-image` with `from_video: true`, and
`posters_as_photos(review)` turns the video attachment into `{type: image, ..., source: video_poster}` before the
review is stored, dropping the video's own data.

Measured on 25 gallery photos of 6 products (smartstore and brand store), every rendition of the same photo:

| Rendition | Resolution | Bytes |
|---|---|---|
| the link as given (no `type`) | the file's own: always the largest real size (600 to 2000 px here) | the seller's file |
| `?type=m10000_10000_no_rotate` | the same | a re-encode (another sha; often fewer bytes) |
| `?type=o1000` | always 1000 px: 17 of 25 upscaled from 600-960, a 2000x1501 photo downscaled | |
| `?type=w860` | at most 860 px | |

**Download** (`naver_images.py`): a plain HTTP GET from Naver's image CDN (`*.pstatic.net`: no browser, no
adapter, no cookies, no redirects), 30 s timeout, 20 MiB cap, image type + file signature, one request every 1 s
(fallbacks, retries, gallery and review photos alike), 3 attempts on 5xx / network errors; a 403 / 429 stops the
run. A gallery link that fails (or whose file cannot be
prepared) is taken as `m10000_10000_no_rotate`, then `o1000`; each file records its `rendition`. A failed review
photo or avatar is skipped, the review stays.

**Prepare** (`image_prep.py`, one algorithm for every store; adapted from the catalog project's
`product-image-webp/v2`): the source stays in memory, only this WebP is written.

| | Gallery | Review photo | Avatar |
|---|---|---|---|
| Size | the short side down to 1500, proportions kept (3000x4000 -> 1500x2000; 900x900 stays), long side at most 5000 | long side at most 1024 | long side at most 1024 |
| File | `<slug>-001-<sha16>.webp` (slug: `ImageSeo.slug`, else `<store>-<product id>`) | `<store>-review-image-<sha16>.webp` | `<store>-review-avatar-<sha16>.webp` |
| XMP | publisher + site; with an `ImageSeo`: title, description (= alt), subject (brand, title) | publisher + site | publisher + site |

Gallery 1500: Google Merchant Center recommends 1500x1500 or more (minimum 500x500 from 31 January 2027, checked
2026-11-01) and asks not to submit scaled-up images, so a smaller photo is kept as it is. Against the
naver-harvester (long side at most 2048, never enlarged) the 1500 short side gives the same file for about 96 % of
real photos (9 of its 250 published differ, sources with a long side over 2048); 22 of those 250 have a short side
under 500 and were not filtered. For all: a static WebP,
never enlarged or cropped, at most 1,000,000 bytes (quality 85, 80, 75 at that size, then each smaller long side;
the first that fits), EXIF orientation applied, sRGB, transparency kept, an animation becomes
its first frame (its last frame must decode; a phone's MPO: its first picture only, an iPhone HDR gain map is not decoded), every old EXIF / GPS / IPTC / ICC / XMP dropped, then read back
(chunks, size, one frame, exactly our XMP). No author or copyright is written; the store is the publisher, not the
brand. `ImageSeo` takes reviewed English text only (slug `a-z0-9-` up to 200, alt up to 125); with only the Korean
name there is none and the file is named after the store and product id.

**Stores** (`shop_stores.py`): `StoreId` enum + `STORES` (publisher, site): fairwardgolf (default), skinsli,
kyobooks, banafish. Pick one per run with `SHOP_STORE` in `.env` or `get_store("...")`. A new store is one enum
member and one `STORES` entry; the algorithm does not change.

Not done here: description images, recommendation images, the product gallery's videos.

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

## The listing screen and the shop check

Before a product page is opened (~30-60 s each), `example_99` screens the listing rows (`listing_filter.Screen`) and
records the reason of every row left out, in this order: `sponsored` (an ad: only with `exclude_sponsored=True`;
ad cards are kept by default, the owner 2026-11-06, though the harvester file says exclude), `title_unavailable`,
`rental` (a stop
word of `listing_exclusions.json`, copied as it is from the naver-harvester: NFKC + lower case, words with
not-preceded-by / not-followed-by exceptions, latin words whole), `title:<code>` (a word of `listing_title_rules.json` the run's category does not sell, the owner
2026-11-11; or no word of a group the category `requires`, 2026-11-19: 50002797 needs a women's word and a cardigan
word; 2026-11-20: 50002798 a women's word and a jacket word; 2026-11-21: fleece, coats too; 50002796 a women's word (the women's section; the men's job, `--leaf mens-fall-long-sleeve-tops`: a men's word ("(MAN)" too) and a long-sleeve word, or a garment long-sleeved by itself: 기모, 히트텍, 맨투맨, 후드, 니트, 집업, 풀오버, 이너 ..., 227 of 274 store products of the query kept, 148 with 긴팔 alone; rules with `leaves`, 2026-11-22), no short sleeve, cardigan, vest, outerwear, bottoms or set, arm sleeves, cooling or kids' word), `category_mismatch` (only the exact leaf
category, or one `listing_title_rules.json` `together` takes with it: 2026-11-21, the owner, 점퍼 50002798 and 재킷
50002799 feed one section, a job of either takes both, each row screened by its own category's rules and collected
as its own category), `key_unavailable` (no store number: no shop check possible), `already_published`, `deferred`. Catalog and
external-mall cards never reach it (the server keeps store products only).

**Already in the shop** (`shopify_catalog.ShopCatalog`): every product of the store, any status (a draft or an
archived one counts), read from its Admin GraphQL API, with the source key metafields `<namespace>.source_offer_id`
and the older `<namespace>.naver_offer_key`; a key is `<namespace>:naver:<channel_no>:<product_id>` (the
harvester's format; `channel_no` is the listing row's `store.channel_no`). Never matched by name. Before each read
the API must answer as the store (`shop { id myshopifyDomain }`); another shop, a key in the wrong format or one key
on two products stops the check (`CatalogError`) instead of answering "not there". The snapshot is read again when
older than 5 minutes (before the run and before each product). The store's values live in `shop_stores.py`
(`Shopify`: domain, shop id, API version, credentials variable, namespace); a store without them raises
`ShopNotConfigured`: ask the operator.
By hand, the same read-only access (2026-11-16): `shopify_catalog.py <shop> show <ref> | counts | vendors |
collection <handle> | dump --out F.jsonl` ([OPERATIONS.md](OPERATIONS.md#reading-the-shop-by-hand-2026-11-16)
"Reading the shop by hand"); in code, `ShopCatalog.paged(query, path)` pages any connection (the query takes
`$cursor`).

**Access**: there is no lasting token (fairwardgolf, 2026-11-05). `.env` holds only the path of the store app's
credentials file (`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`; `PRODUCTS_API_CLIENT_ID` / `PRODUCTS_API_CLIENT_SECRET`, the
harvester's `.env.fairwardgolf`; must be 0600 and ignored by git, else `ShopNotConfigured`). Each run mints a 24 h
token (`client_credentials`), checks it at once (`shop`, `currentAppInstallation.accessScopes` has `read_products`, a
probe `products(first: 1)`; a token that fails is dropped), replaces it 10 minutes before it ends, and after a 401
mid-run mints once more and repeats
the request once. Queries only: the token could write, so a mutation is refused. Token and secret go only to the
store's own host (no cookies, no redirects), never into `os.environ`, an error or a print. Pages of 100 products;
a throttled answer waits what Shopify says (`extensions.cost`, `Retry-After`). The 5-minute age is wall-clock time
from the start of the read (a Mac asleep counts).

**Deferred** (`deferred_log.DeferredLog`, `collect_guard.CollectGuard`; `output/journal/deferred-<store>.jsonl`): a
product whose collection is partial is tried once more; partial again, it is deferred with the reason and the first
error, and is not taken again. Only the owner allows one retry of one product
(`deferred_log.py allow <key> --by <who> [--note]`), written to the journal and spent by the next attempt. Lines are
never removed; there is no switch to ignore the journal. A captcha / 418 / 429 / login wall or a refused image CDN
stops the run without marking the product; a card not found on the listing is just not taken; two products in a row
partial for the same reason stop the run (a defect of the collector).

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
card's store (`api._find_store_for_product`). That path is slow and can 404 (and
always does since 2026-11-02, when validation-products started answering 419).
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

## Response types (`naver_types.py`)

TypedDicts for every answer (91 names: `SearchCard`, `ProductDetails`, `ReviewsPage`, `ListingRow`, `ListingTab`, ...). `X | None`
means the server may send null: guard it (`product["reviews"]` can be None). They were written from real answers
(`fixtures/*.json`, captured live 2026-11-01) and the server's parser code; `test_naver_types.py` checks each
fixture against its type strictly (missing or unknown keys fail).

```sh
.venv/bin/python -m pytest scripts -q                      # includes the type conformance test
.venv/bin/python -m mypy                                   # static check of every script, tests excluded
                                                           # ([tool.mypy] in pyproject.toml; mypy is in requirements)
```

mypy is clean on scripts/ (0 errors since 2026-11-15): a new error is a finding to fix, not to ignore.

When a server answer changes shape: re-capture its fixture (one call with the client, json.dump, lists trimmed to
5 items, long strings to 300 chars), update the type, and commit both with the server change.

## Checking a run against product pages

How the 2026-11-05..07 checks of 139 golf sets were run, to rebuild them (no code is kept for it; the collection
and the transform are the project's own, the check is an offline reading of saved pages).

The run, in batches of 5 products, resumable (products already in `products.jsonl` and batches already done are
skipped):
1. Targets: `api.listing(query, max_batches=2..4)` for "남성 골프채 풀세트" and "여성 골프채 풀세트", screened by
   `listing_filter.Screen(category, namespace, ShopCatalog(store).keys(), deferred)`; duplicates and products of
   earlier runs left out; the list saved, so a rerun takes the same products.
2. Collect each product as example_99 does: `product_details`, `selected_reviews(count=20)`, `product_specs` (the
   name first, the listing query on a 404), `choose_variants(options, discounted_price, paid=...)`,
   `variant_measures(specs, load_table())`, `download_gallery`, `download_review_media`, `posters_as_photos`; all
   under `CollectGuard(DeferredLog(...)).run(key, ...)`; one line `{key, listing, details, specs, variants, package,
   reviews, photos, review_media}` appended, 2 s apart.
3. Read the same 5 pages through `/products/page` one at a time, 30 s apart, saved by `product_page.save`.
4. `keep_run.keep(run, shops)` then `run_transform.run(store, None, shops)` on everything collected so far; a batch
   list `[{id, key, dir}]` starts the check of those 5.

Pacing and retries: one page read at a time; 60 s before the next product after two reads of one product (back to
back they brought Naver's error page on 4 of 8); 409 (adapter busy): every 30 s, up to 12 times; Naver's
internal-error page (503, server/docs/KNOWN_ISSUES.md K-21): wait 120 s, twice, then skip the product and read it
again at the end (it came back after 2-15 min every time). No captcha in 139 products; one at the search page earlier,
answered by the owner.

Cost: [Measurements](#measurements).

The check: one reader per product, offline, from the saved page (page.html, product.json), the collected line and
the prepared product (the browser tools of the session cannot open naver.com, so saved pages are the only way). 12
phases, each `{phase, verdict: ok | issue | changed_since_collection | n/a, page, ours}`: price, delivery, options,
text inputs, add-ons, gallery, specs, notice, description, reviews, measures, transform; then the issues `{phase, kind:
missing_data | wrong_data | transform_decision | improvement | noise, known: <id> | new, severity, what, evidence,
suggested_fix}`. Collection: every page item present and right; transform: status, prices, axes, variants, facts,
attributes (and the placement's sections), spec rows, add-ons, description, images; for the buyer: anything lost, anything shown that should not be.
Measure across runs by high + medium findings per product (0.65 on 40 known sets after two fix rounds; 1.21 then 1.00
on new products).

After a parser change, a run can be replayed offline: the adapter keeps each page it read in
`server/output/ext-product/<time>-<id>/` (product.html, product.json); the newest folder within 10 s of the line's
`specs.read_at` replays through `ext_product.specs_from_page` and `parsers.parse_contents(page_fixtures.contents_from(
description))`, then `choose_variants` / `variant_measures` and the transform (equal to the live API on 4 of 4). New
patterns found this way go to the regression fixtures (server DEVELOPMENT_RULES R-TEST-5) and to
[SELLER_DATA.md](SELLER_DATA.md).

## Measurements

The check run of 2026-11-05..07 ([Checking a run against product pages](#checking-a-run-against-product-pages)),
medians: a product 58-73 s to collect (the page read 48-50 s, details 4-7 s, reviews 0.4 s, gallery 1-3 s,
review photos 4.5-11 s); a `/products/page` read 48 s (38-194); a batch of 5 with its pages ~10-12 min; 40 products
~64 min; keep + transform ~0.2 s. Reading the page by the product's name first (not the listing's query) took the
page read from 74 s to 48 s and 40 products from 61 to 45 min.

Other measurements stay at their rule: photo renditions ([Product photos](#product-photos), 2026-11-01), the
harvest's cost ([Listing harvest](#listing-harvest-harvest_listingpy), 2026-11-01), the reviews' cost
([Reviews: two ways](#reviews-two-ways)).

## History

- 2026-11-16: split from scripts/README.md (history before: `git log --follow scripts/README.md`).
