# scripts/

Client-side consumers of the Naver Shopping API. Everything here talks to a
running server over HTTP only, plus a few other fetches (the full list: AGENTS.md rule 3): the photo files the API
linked, from Naver's image CDN (`naver_images.py`, see Product photos), and a
read-only look at our own Shopify store's catalog (`shopify_catalog.py`, see
The listing screen and the shop check), and the publication to that store (`publish.py`, see Publication).
ShopNShip's public shipping calculator is asked by hand only, to capture the delivery tariff
(`shopnship_rates.py`, `shopnship_explore.py`, see The price), never in the price path. The full list of
outside fetches: AGENTS.md rule 3.

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
- `naver_api_client.py` is the single gateway to the API. Every script goes
  through `NaverApiClient`; `naver_images.py` only downloads files whose links
  the API returned.
- `requirements.txt` holds `requests` and `Pillow` (WebP for the photos), so
  scripts run on a machine without Chrome or patchright. The offline tests
  also need `pytest`, which the server venv has.

| File | Purpose |
|---|---|
| `naver_api_client.py` | `NaverApiClient` (`get`, `pages`, `health`) and `ApiError` |
| `naver_images.py` | Downloads the photos the API linked (gallery, review photos, avatars) from Naver's image CDN with plain HTTP and saves them as the store's WebP (see Product photos) |
| `image_prep.py` | The WebP preparation, one algorithm for every store: size, bytes, metadata, checks (no network) |
| `naver_variants.py` | Which variants to collect: free ones by default, paid ones when the operator turns `paid` on; sold-out rows kept and marked (see Product options) |
| `shop_stores.py` | Our Shopify stores (`StoreId` enum + publisher / site + Shopify values), picked by `SHOP_STORE` |
| `listing_filter.py`, `listing_exclusions.json` | The listing screen: which rows to open, a reason code for each left out (rental stop words from the naver-harvester) |
| `shopify_catalog.py` | The "already in the shop" check: every product's source key from the store's Admin API (read only) |
| `publish.py`, `shopify_payload.py`, `shopify_admin.py` | Publication: prepared + translated + placed -> the store (productSet, photos, reviews' files, ACTIVE, the website); the payload built offline; the two writing apps. See Publication |
| `shop_pricing.py` | The price rule per shop: a variant's cost per item, price and how they were made (`Policy.quote`). fairwardgolf: `landed/2`, delivery, duty and margin inside the price; a shop without the rule: `krw-cost/1`, 1 000 KRW = 1 USD up to a dollar, price = cost. See The price |
| `delivery_tariff.py`, `delivery_tariffs.json` | The delivery cost of one packed box by a recorded tariff, offline (billable weight, step, fees once per box); the tariffs as data, each traced to a dated capture, with `version` and `history`. See The price |
| `shopnship_rates.py` | ShopNShip's public calculator (networked, by hand only): `quote` one box, `capture` the grid into a dated file, `compare` a capture with the recorded table. Never in the price path |
| `shopnship_explore.py` | Research tool (networked, by hand only): wide sets of boxes asked of the calculator and compared with the tariff model (`run`, `report`). Never in the price path |
| `store_diff.py` | Read only: what a publication would change in the store, field by field, per published product; the published products that cannot be built now; `--adopt` records `output` for those the store already has. Run it after any change of rules, dictionaries or a new category (ONBOARDING.md part D) |
| `reprice.py` | Products already in the store: old -> new prices under the shop's rule (a dry-run table, also a TSV under `publish/`); `--apply` sends them, on the owner's word. See The price |
| `test_publish.py` | Offline tests for the payload (the variants' prices and metafields included) and publish.py (fake Shopify clients) |
| `test_shop_pricing.py`, `fixtures/pricing/` | Regression for the price rule: real products cut down to what the rule reads (the variants' prices, the delivery in Korea, the package fields), with the cost, price and breakdown each variant must get; `UPDATE_GOLDEN=1` rewrites the expected part after a deliberate change of the rule or the tariff: read the diff |
| `test_delivery_tariff.py`, `test_shopnship_rates.py`, `test_shopnship_explore.py` | Offline tests for the tariff calculator (the captures and explorations replayed through it) and the calculator's client (a fake calculator, a saved capture) |
| `fixtures/shopnship/` | The calculator's answers of 2026-11-11: two grid captures (the second is the tariff's source), two explorations and the second round's rows; the backups a new capture is compared with |
| `test_reprice.py` | Offline tests for the repricing flow |
| `conftest.py` | The folder's tests never reach the network: a connection attempt fails the test |
| `deferred_log.py` | The shop's journal of deferred products (append-only); CLI `list` / `allow <key> --by` |
| `collect_guard.py` | The run rules around one product: one retry, then deferred; stop on a wall; stop on a repeated defect |
| `package_measures.py`, `category_measures.json` | Five shipping fields per variant: the seller's values, else the operator's category averages; the table also holds the operator's `baselines` for the composition; confidence 1-5 |
| `description_images.py`, `description_ocr.py`, `description_measures.py` | Optional stage: OCR of the description images (RapidOCR; Naver's CDN and the seller's HTTPS hosts; a worker process per product) into a sidecar per product; the transform reads size / weight from it and from the typed description text (a core for every category + parts profiles by Naver category id): a stated box / weight takes the place of a category default, and a set's other fields are composed from its parts with the operator's baselines, the flat default last (see Package weight and size) |
| `review_clean.py` | The reviews sanitized in the transform: decoration out, the Korean purchase cut, empty reviews dropped (see Transform) |
| `translate.py`, `translation_dicts.py`, `translation_rules.py`, `translate_keys.py`, `translate_eval.py`, `prompts/` | Translation of the prepared texts (see Translation): the model stage, the per-kind dictionaries (live / backup), the unit rules, the prompts |
| `description_image_text.py` | The images' OCR rows -> clean Korean blocks (text / table) for the translation step; run_transform writes `translation/<product id>/description_images.ko.*` and the flag `product.description_images_text.state` |
| `test_description_images.py`, `test_description_ocr.py`, `test_description_measures.py`, `test_description_image_text.py` | Offline tests for the stage (fake fetcher and engine), the slicer / rows, the guess and the merge (real OCR rows) |
| `product_page.py` | Saves a product page as the owner's Chrome renders it (`/products/page`): page.html, the page's own answer, meta; for developing parsers and checking collected data |
| `captcha_watch.py` | Reports a Naver captcha the adapter waits on (reads `/captcha`): one line per new captcha / solved / timed out; independent of any collection |
| `keep_run.py` | Keeps a collection run (example_99 output) per shop, byte for byte, read-only (see Transform) |
| `transform.py`, `transform_shops.py`, `run_transform.py` | The transform: kept runs -> prepared products per shop (shared rules, per-shop rules as data, the CLI) |
| `attributes.py` | Neutral attributes the transform writes to `product.attributes` (gender with its evidence: the variants, the 성별 row, the title; the listing query only flags `listing_disagrees`). A new kind of split is a new `Attribute` (data) |
| `brand_fallback.py` | Run-level: a brand for every prepared product that states none (a brand of the shop in the title, 원산지's importer, the images' text, else 노브랜드; note `brand_fallback`) |
| `placement.py`, `placement_rules.py` | The last stage before Shopify: prepared products -> the shop's sections (leaf tags, product type, `start_variants`) from the shop's profile (data); unknown / conflict held as `unresolved`. How to add a split: [PLACEMENT.md](PLACEMENT.md) |
| `test_placement.py`, `test_brand_fallback.py` | Offline tests: the gender attribute and placement (the 50 fixtures, the rules case by case), the brand fallback |
| `test_transform.py` | Offline tests for the transform on real collected lines (`fixtures/collected_fairwardgolf.jsonl`) |
| `test_prepared_golden.py`, `collected_fixtures.py` | Regression: collected lines of real products (`fixtures/collected/`, from the server's saved-page fixtures) through the transform must equal `fixtures/prepared/`; `UPDATE_GOLDEN=1` rewrites them after a deliberate change, read the diff. Added only when the owner asks (server DEVELOPMENT_RULES R-TEST-5) |
| `test_measures_fixtures.py` | Regression for the five package fields: 17 real golf sets cut down to what the measures code reads (`fixtures/measures/<product id>.json`: title, 상품정보 rows, variants' option words, add-ons, typed lines, the OCR rows with their confidence, the server path's candidates; sellers' phones, addresses and shop names are "x") through `package_measures.variant_measures` and the transform's hook with the real `category_measures.json`, against the fields each variant must get (value, source, confidence 1-5, how, parts), checked by hand against the product's lines (`checked`; where a fixture's `note` says "approximate" the value pinned is the rule's present approximation, not the page's figure). One test per product, one that the set covers every level and source. `UPDATE_GOLDEN=1` rewrites the expected part: read the diff against the products' lines |
| `smoke_endpoints.py` | Live smoke: `/health` plus 11 endpoints (all but `/products/specs`), one at a time. Networked. |
| `example_search_harvest.py` | Template: search, classify the cards, fetch details, write resumable JSONL |
| `test_naver_api_client.py` | Offline tests for the client and the classifier |
| `test_naver_images.py` | Offline tests for the photo downloader (a fake CDN, Pillow-made photos) |
| `test_image_prep.py` | Offline tests for the WebP preparation (Pillow-made photos) |
| `test_naver_variants.py` | Offline tests for the variant choice (real rows of a product with paid and sold-out variants) |
| `test_shop_stores.py` | Offline tests for the store registry (every `StoreId` has a profile, `SHOP_STORE`) |
| `test_listing_filter.py`, `test_shopify_catalog.py`, `test_deferred_log.py`, `test_package_measures.py` | Offline tests for the screen, the shop check (a fake Admin API), the journal and run rules, the shipping fields |
| `example_0N_*.py` | Runnable examples, one API topic each (see Examples) |
| `harvest_listing.py` | Full listing of store product links for a keyword + category, price-sliced, resumable |
| `output/` | Run output (`output/<run>/products.jsonl`, `listing.jsonl`), gitignored |

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
  Entering through a category page is not built yet (the listing has no category filter either).

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

## The listing screen and the shop check

Before a product page is opened (~30-60 s each), `example_99` screens the listing rows (`listing_filter.Screen`) and
records the reason of every row left out, in this order: `sponsored` (an ad: only with `exclude_sponsored=True`;
ad cards are kept by default, the owner 2026-11-06, though the harvester file says exclude), `title_unavailable`,
`rental` (a stop
word of `listing_exclusions.json`, copied as it is from the naver-harvester: NFKC + lower case, words with
not-preceded-by / not-followed-by exceptions, latin words whole), `category_mismatch` (only the exact leaf
category), `key_unavailable` (no store number: no shop check possible), `already_published`, `deferred`. Catalog and
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

## A job: one listing, one product at a time (`job.py`)

The iterative way (the owner, 2026-11-07): one listing, then each product in turn through every built stage
(collect -> keep as a one-line run -> description images -> prepare) before the next opens; resumable at any point,
the stage of each product read from the files. Translation, placement and publication are named stages
(`job.py STAGES`): placement runs on the whole shop before publication (`placement.py`); translation runs per
product, and in a job made with `--publish` placement and publication too. The
browser stays on the job's search tab (the server searches the next product in it and closes the product tab); a
login page is reset from naver.com, a captcha waits for the owner. How an agent runs it: [JOB_AGENT.md](JOB_AGENT.md);
files, waits and stops: the `job.py` docstring. The per-product collect is `collect_product.collect`, shared with
example_99.

```sh
.venv/bin/python scripts/job.py new --query "남성 골프채 풀세트" --category 50002788 --count 40 --paid
.venv/bin/python -u scripts/job.py run          # resumes; --items N for a few
.venv/bin/python scripts/job.py status [--json]
.venv/bin/python scripts/job.py refresh --more 50  # by hand: the listings read deeper, new products appended
```

The owner's decisions (2026-11-07): one product per iteration (fewer reads in a burst: less risk of a block);
publication goes straight to ACTIVE, right after translation; no age limit between collection and publication.
Changed 2026-11-08: translation is a model API stage (`translate.py`, see Translation), not the session's agent; the
description and the images' text are not translated (`describe.py` writes the description from them, 2026-11-10). Not built on purpose (the owner,
2026-11-08): OCR in parallel with the next collect, an incremental prepare (run_transform.run(shop) rebuilds the
shop after each product: 1-2 s at 143 products, the pace did not drift over 100), a guard memory across runs.

Checked live (2026-11-08, 50002788, own shops root): 40 sets in 53 min and 100 sets in 146 min, every one prepared
`ready`, no stop, wait, captcha, login gate or Naver error page; ~80-88 s a product (collect median 52-56 s, page
read 34-48 s, OCR median 21-22 s, prepare 1-2 s); the search tab reused for every read (`tabs left: 1`). A listing
of 12 batches (one query) read in 110 s: 583 unique rows, no stall. Captcha, login reset, Naver's error page and a
lost extension are covered by offline tests only (none came up live).

## Translation (`translate.py`)

Decisions, a new shop or category, the quality check (`translate_eval.py`), limits: [TRANSLATION.md](TRANSLATION.md).

The owner (2026-11-08): the prepared products' `texts` go to English through Claude Sonnet 5.5 (effort low, JSON
output) before placement and publication. Not translated: `description_ko` and the images' text (a later stage
writes the description from them; their `to_translate` flag is not this stage's).

```sh
.venv/bin/python scripts/translate.py fairwardgolf --offline   # no model: what the dictionaries and rules leave
.venv/bin/python scripts/translate.py fairwardgolf --limit 3   # the model for 3 products
.venv/bin/python scripts/translation_dicts.py status [--json]  # sync helper: dates, what the backup lacks, advice
.venv/bin/python scripts/translation_dicts.py backup           # by hand: live -> scripts/dictionaries/, then commit
```

Per text, the first that answers:

1. **The product's own store:** title, review, a placeholder option name (선택 / 옵션, named from its values), in
   `translation/texts.jsonl`.
2. **The dictionary of its kind:** brand, option name / value, spec and fact label / value, add-on group / name,
   text-field label / placeholder. One file per kind. The live copies in `scripts/output/dictionaries/` grow during
   runs and are out of git. Their backups in `scripts/dictionaries/` are in git and seed a missing live copy; they
   are updated by hand with `backup`, after `status`, since runs never commit; a backup stamps each file
   `backed_up`. The sync only adds: a run takes the entries only the backup has (pulled from git, seeded by hand),
   a backup writes the live entries over the backup's and keeps its others. A wrong entry is fixed in the live
   copy; deleting one for good means both copies. `status` shows when the live copies were last written and the
   last backup, the new and changed entries, the ones only in git, and the advice (`action` none / wait / backup /
   review in `--json`). A backup is due at 20 waiting entries, or 7 days after the last one with any waiting
   (`BACKUP_AT_CHANGES`, `BACKUP_AFTER_DAYS`); changed entries are read first, since the backup writes the live
   English over git's. When it is due, a `translate.py` run's report (not `--only`) and `job.py run` (done) /
   `job.py status` print one reminder line. The brand dictionary comes first: the
   model gets the shop's vendor spellings and reuses one for the same brand.
3. **The rules** (`translation_rules.py`):
   - 10.5도 -> 10.5°, 33인치 -> 33 in, 22호 -> Size 22, 3번 -> #3, 7개 -> 7 / 7 pcs, 12종 -> 12 pcs, 2026년형 -> 2026 model;
   - 노브랜드 alone becomes the tenant's name (`Store.publisher`), and inside a text it is removed;
   - a brand of 기타 ("other") alone becomes the tenant's name as well (2026-11-11);
   - a text with no Hangul left is done; the rest goes to the model already converted.
4. **The model:** one request per product, with the system prompt in `prompts/translate_system.md`. Each item is
   checked:
   - every id is returned once;
   - no Hangul is left;
   - the source's numbers and Latin codes are kept;
   - the text is within its length limit;
   - the option values stay distinct.

   What fails goes back in the same conversation (`prompts/translate_fix.md`), at most twice. What still fails
   leaves the product `untranslated`; what passed is kept.

   **Fallback:** OpenAI (the owner, 2026-11-08), through Chat Completions with a strict JSON schema, the same
   prompts and reasoning effort low. Its model is `OPENAI_MODEL` in `translate.py`; `OPENAI_TRANSLATE_MODEL` in
   `.env` overrides it.
   - **When Anthropic is down** (network, 5xx or overload, a rate limit after the SDK's retries, another API error):
     that batch starts again on OpenAI, and Anthropic rests 10 minutes. A declined or cut batch also goes to OpenAI,
     without the rest.
   - **A refused key** stops the run.
   - **Every provider down:** the product stays `pending` for the next run.
   - The report says which model answered each product.

**Batches.** A product is never sent whole when it is long. Its short texts go in batches of at most 40 items /
2 500 characters, its reviews apart in batches of at most 8 / 2 500 (`make_batches`). Each batch is its own
conversation with its own fix rounds and provider fallback. At the end every pending text must have an answer, or
the product is `untranslated` (a batch no provider could take: `pending`).

**Checked 2026-11-08** on 12 varied trial products with a second model (Opus 5.5) as the judge: 25 of 260 texts
flagged, then 17, then 10 (3.8%) after three rounds of fixes.
- **The fixes:**
  - the golf terms and model lines in the category brief;
  - a glued spec run split after each flex letter (`CATEGORY_RULES`);
  - review fidelity in the system prompt: no "for the price", the subject kept, no upgrade of strength;
  - a title's words that only some variants have (the note `title_names_one_variant`) passed as context;
  - text addressed to a model cut from reviews.
- **Live checks also run:** rerun (0 calls), resume of an untranslated item, every provider down (`pending`, then
  resumed), a 24-value option and a 1 700-character review.
- **The report:** `translate_eval.py` writes `report.html` (see TRANSLATION.md).

**Tokens** (the owner, 2026-11-08: no overspend):
- **The request:**
  - compact JSON;
  - the batch's short ids (`1`, `2` ...) instead of the text ids, both ways;
  - the category's terms only in the system prompt, which is cached and read at a tenth of the input price;
  - the shop's vendor list only when a brand is asked.
- **No thinking:** `thinking: between_tools`, with effort low. On simple words it gave the same English at fewer
  output tokens and 20% less time. `ANTHROPIC_TRANSLATE_THINKING=adaptive` turns it back on.
- **Where the cost goes:** the output, that is the English itself.
- **Measured 2026-11-08** on 4 varied trial products (129 texts, empty dictionaries): 11 batches, 12 calls (one fix
  round), all translated, about $0.015 and 8 s a product, $0.0005 a text. With the dictionaries the shop's repeated
  texts cost nothing.

**The system prompt is assembled** (`system_prompt`):
- the translator's role and rules (`prompts/translate_system.md`);
- the shop's brief (`prompts/tenants/<shop>.md`: who sells to whom, spelling, tone);
- the category's brief (`prompts/categories/<Naver category id>.md`: what the products are, their terms, how buyers
  write about them).

**A new shop or category** (the whole checklist, every stage: [ONBOARDING.md](ONBOARDING.md)) needs a short brief file only here, no code. Write the file following the 50002788 one; the
category's review aspects go in `review_clean.ASPECTS` / `CONTEXT`. A missing brief is left out, and the base prompt
works alone, less precisely.

Out: `translation/translated.jsonl` (per product: status, English by text id, where each came from) and
`report.txt` (counts, tokens and cost, new dictionary entries).

The keys: `scripts/translate_keys.py install <file>` moves the operator's key file out of the repo, makes it 600,
and sets `TRANSLATE_KEY_FILE` in `.env` ([SETUP.md](../SETUP.md)). The models, their efforts and the chain's order
are `.env` settings, not code (`TRANSLATE_PROVIDERS`, `ANTHROPIC_TRANSLATE_MODEL` / `_EFFORT`,
`OPENAI_TRANSLATE_MODEL` / `_EFFORT`; `translate.settings()`). The server-side refusal fallback is sent only to the
Claude models that take it.

On the 143 trial sets (2026-11-08):
- without the model, the dictionaries and rules gave 3 606 of 4 877 texts;
- the model is left 1 271: titles 143, reviews 442, option values 292, spec values 505 (with repeats across
  products, each asked once per product);
- the reviews are sanitized but all kept, so 411 review texts are left (the cut text is gone from them).

A job made since 2026-11-08 runs this stage per product, right after prepare (`job.py`, translated; `new --no-translate`
leaves it out). See [JOB_AGENT.md](JOB_AGENT.md).

## Placement: the shop's sections, the last stage before Shopify (`placement.py`)

The owner (2026-11-08): a shop is split into its sections at the last stage before Shopify, from its own profile,
not while a job collects; one Naver category id can be several sections (50002788 풀세트: men's and women's sets),
and another shop may split other categories by other marks. So the transform only states what the seller says, as
neutral **attributes** with their evidence (`attributes.py`, data: a value's words, the 상품정보 rows that state it,
what a value implies), and placement maps them to the shop's sections by **profile** (`placement_rules.py`, data:
Naver category id -> parent, the attribute that splits it, value -> section (collection handle, product type, tags),
what an unresolved product does: `hold` or a fallback section). A new split is a new attribute and a profile entry.

One product, several collections: a product in two sections stays ONE Shopify product (card, variants, stock
shared, never a second copy) carrying the leaf tags of both (`tags`: fairwardgolf:leaf:mens-complete-sets and
...:womens-complete-sets), shown by both tag collections; `product_type` is the primary section's (the most
variants). A section showing only part of the card (a set with separate men's and women's variants) gets a
start-variant hint (`start_variants` {leaf: sku}, for publication's metafield of start variants per collection: from
the men's collection the men's variant opens), never a removal of the other variants. A stated unisex goes to both;
an unknown gender is not unisex and goes nowhere (held).

Gender (50002788, fairwardgolf): each sold variant's option values first ("여성용-그라파이트": that variant is
women's; a set with both is `mixed` and goes to both sections, each with its own start variant; when the seller marks only
one gender's variants beside a unisex row, the unmarked ones are the other), else the 성별 row, else the title
(여성 / 레이디스 / LADIES, 남성 / MEN'S, 남녀공용 -> both). A row and a title naming opposite genders, or every
variant the opposite of the row: `conflict`; nothing says it: `unknown`; both are held (`unresolved`) for the owner,
never guessed from a flex, a colour or a model. The job's listing query is evidence only (flag `listing_disagrees`).
Checked on the 143 trial sets and the 50 fixtures (2026-11-08): the same sections as the transform's leaves before
on all but one (13425122164: a men's listing with a women's variant: both sections, 2 and 1 variants). GVTOUR
8514409092: 46 men's and 23 women's variants, as the harvester's live check pinned them (2026-09-26).

```sh
.venv/bin/python scripts/placement.py fairwardgolf      # -> shops/<shop>/placement/placements.jsonl, report.txt
```

**The same case in another shop or category**, or a split by another mark: step by step in
[PLACEMENT.md](PLACEMENT.md) (which file for which case, the profile entry, a new attribute, the unresolved policy,
the tests to add). In short: the category's transform rules (`transform_shops.py`), its profile entry
(`placement_rules.py`: parent, `split_by`, value -> section, `unresolved`), and for a new mark an `Attribute` in
`attributes.py`; no code.

## Package weight and size

`/products/specs` `measures` holds the seller's weight and size candidates (server: `naver_shopping/measures.py`,
contract in ENDPOINTS.md). `package_measures.variant_measures(specs, load_table())` turns them into five fields per
variant: `product_weight_g` (net or unspecified, never a part's; in a set only the whole set's), `package_weight_g`
(only a weight with the package), `package_length_mm` / `package_width_mm` / `package_height_mm` (only a triple marked
as the package, longest side first). A value belongs to a variant when its binding is the product or names that
variant; values that disagree are a contradiction and are not taken. Values within 2% agree (6.35 kg and 14 lb are one
weight). A set weight stated per composition is each variant's own (6630856593: 11.5 kg on the 12-club variants, 4.7
kg on the 4-club ones). Parts' weights (club spec tables) are never added up into the set's: their sums leave out the
bag and covers. A default package weight below the seller's product weight is kept but flagged `flags:
["below_stated_product"]` (at collection; in the transform, with the row's `baselines`, that package weight becomes
the seller's product weight + the carton). A table row may carry `plausible: {field: {min, max}}`, the operator's band: a stated value
outside it is not taken (`contradiction`, `reason: implausible_for_category`) and the default fills the field; no row
has a band yet, and none is made up. A row may also carry **`baselines`** (the owner, 2026-11-10), the operator's
amounts for the parts of a set of like items in a container; all of them or no block (`check_row`):

| key | what | 50002788 (the owner, 2026-11-10) | basis |
|---|---|---|---|
| `item_g` | one item (a club) | 340 g | the median of the sellers' club tables (332 g) over the 120 sets |
| `container_g` | the container (the bag) | 3800 g | the median of the 11 bag weights sellers state (2.6-4.8 kg) |
| `carton_g` | the box and its packing | 2000 g | a Callaway Edge 10-club set: clubs 3.7 kg, boxed 6 kg |
| `longest_item_mm` | the longest item (the driver), when its length is not read | 1140 mm | the 118 stated drivers are 1105-1168 mm |
| `length_margin_mm` | the box's length over the longest item | 100 mm | the one stated box, 121 cm, against its 111 cm driver |
| `sides_mm` | the box's [width, height] without the container | 200 x 160 mm | that stated box, 20 x 16 cm |
| `sides_with_container_mm` | the same with the container | 400 x 320 mm | the caddie bags stated on 4 sets, 39-40 x 31 cm |

plus `approved_by`, `approved_at` and `basis` (where each amount comes from; the owner: approximate until the first
real shipment, low certainty). With the block a field the seller does not state is **composed from the set's
parts** and the row's flat averages are the last resort (see "The order of sources" below); a row without the
block composes nothing: a field is the seller's statement or the flat average. No amount is ever made up in
code. The table's `version` is 2 since the block. A missing field comes from
`category_measures.json`, the operator's table (per leaf category: low / central / high of the five fields, who
approved it and when, the table's version), as `source: category_default`; a seller's value is never overwritten.
No row for the category: `CategoryDefaultsMissing`, the run stops and asks the operator (values are never made
up). Every row carries `reliability`; today one level, `estimated_average` (the weakest: an average of estimates,
not measured); the price rule's coefficient goes by the lowest `confidence` of the box's three sides, not by this (see The price).
50002788 풀세트 is filled (owner, 2026-11-05):
the median (central) and about the 10th / 90th percentile (low / high) of the naver-harvester's AI estimates on the
55 fairwardgolf sets in Shopify, sets with and without a bag together (none of their values was seller-stated).
50002787 주니어용클럽 (owner, 2026-11-11) holds single clubs and sets, so its row has **two defaults**: the row's
own fields are a junior set's (105 x 28 x 25 cm, 4.5 kg central) and its `kinds` entry `single_club` a single
club's (90 x 12 x 10 cm, 1 kg). `default_kind()` takes the kind per variant: a club word (퍼터, 드라이버, 아이언, ...)
in the title and the variant's words with no set word (세트, N종, N개, 가방, 구성, ...), or 단품 in the variant's
own words, or a variant that names one club when the title has no strong set word (풀세트, N종, N개, 구성, a bag); a
set word otherwise keeps the set's box, the larger one. The title and the variant are read apart ("...클럽" +
"6~8세" is no count). Such a default carries `kind`. The table's `version` is 3 since that row. A kept run is never
rewritten, so the transform takes each default as today's table gives it (`current_defaults`): a changed row
reaches the product when it is prepared again; a default already today's stays as collected.
Product sizes (not the package: kind product or unknown) are kept apart, optional.
Every field carries `confidence`, **1 to 5** (the owner, 2026-11-10):

| level | meaning |
|---|---|
| 5 | the seller states this field itself in typed text and says what it is: a net weight, a weight with the package, the box's sides (the server path); a typed box or packed weight in the description |
| 4 | the seller states it, a weaker reading: read from an image, or its kind left open (a plain 중량 11.5kg: with the box or not), or bound to the variant by club count, or a per-piece weight times the count |
| 3 | worked out wholly from the seller's own figures for this product, plus the operator's carton / margin: the clubs' exact sum with the bag absent or its weight stated (the count and the bag's state from the listing or the typed text); the length from the driver read; a package weight on such a product weight |
| 2 | composed with a baseline or a weak part: the count x the median, a baseline club / bag / longest club, the baseline box sides, the bag's state known only from an image's sentence or a closed list of clubs, the count read from the images or taken from the clubs' table alone; the bag assumed (`flags: ["container_assumed"]`: the clubs are known and nothing says whether the bag ships, so the baseline bag, the heavy side; the owner 2026-11-11) |
| 1 | the flat category default: the composition is unknown |

**The scale changed on 2026-11-10** (it was 1-3 since 2026-11-06: 3 stated with its kind, 2 stated with the kind
open or the binding worked out, 1 the default). Records written before the change carry the old numbers: collected
lines (`package` is computed at collection), prepared records of `format: prepared/4` and below, and what was
published from them; `prepared/5` is on the new scale. The transform puts a collected line's seller values on
today's scale from their own evidence (`package_measures.on_scale`: the old 3 is 5, the old 2 is 4), so one prepared
record never mixes the two. Of candidates that agree, the most certain is taken.

### From the description images (optional stage, the owner 2026-11-07)

The images are most of a description (golf sets: ~12x the page's text) and state what the page does not: a box,
a product's weight and size, or, for sets, each part's. The stage reads them; the transform takes from that text
what the seller states of the five fields and, for a set, composes the rest from its parts ("The order of
sources" below; until 2026-11-10 the larger of the guess and today's value won). The same reader also gets
the lines of the seller's typed description (`details.description.text`, 2026-11-10) as one more block of rows:
no OCR doubt, table cells joined by " | " ("패키지 무게 : 10.8kg", "클럽 무게(g) | R: 294 / S: 297 | ... | 528"). A
value read there says so in its evidence (`from: description_text`; `source` stays `description_image`). It is
read with the images or not at all (no sidecar, or a stale one: neither is read).

**The operator's (or an agent's) order of commands**, after each collection:

```sh
.venv/bin/python scripts/example_99_full_details.py                  # 1. collect (server running)
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # 2. keep the run
.venv/bin/python scripts/description_images.py fairwardgolf          # 3. read the description images (network)
.venv/bin/python scripts/run_transform.py fairwardgolf               # 4. prepare (offline)
```

Step 3 is not part of the collection on purpose: it is slow (~20 s a product, ~3.5 h per 1000), needs only the
image hosts (no server, no Chrome) and can be run, stopped and resumed on its own. It reads only the categories
whose shop rules set `description_images` (transform_shops; off by default, on for 50002788). Skipped, the
transform still runs: the products get the note `description_images_missing` and today's values.
`--products <id> ...` reads some products only, `--force` reads again.

**What it fetches.** Each kept product's `details.description.images`, in order: seller banners out (by name, link,
spacer, 1x1 pixel: description_clean.clean_images), animated GIFs out (a one-frame GIF is read: 9942710033's whole
description is one), images smaller than 60 px out (`tiny`: counters,
icons), a link repeated in one body once. Hosts: Naver's image CDN and any public HTTPS host the seller links (the
owner, 2026-11-07; never http, an IP, localhost, or a name that resolves to a private / local address; AGENTS.md
rule 3). On 50 golf sets 8 products have 35 such images
(igearmall / esmplus pages with the product copy and the clubs' spec tables, percenty shop-policy pages, rakuten /
mercari photos): checked by eye, they are the description, with the same boilerplate and photos as Naver-hosted
ones. A SmartEditor link is fetched without `?type` (the original). naver_images fetch rules: HTTPS, no
redirects, MAX_BYTES, image types only, one request a second; a 403 / 429 from Naver's CDN stops the stage (the
sidecars so far are kept); from a seller's host it fails that image only (`refused`, not retried: hotlink blocks).

**Memory and failures.** Each product is read in a fresh worker process (one at a time, synchronous,
`read_isolated`); the OCR engine and the image bytes die with it, so a long run never accumulates RapidOCR's memory
(live: the worker up to ~2.1 GB, the run ~50 MB). A worker that crashes, is killed (memory) or outlives
PRODUCT_TIMEOUT (900 s) is that product's error: one more try, then an error sidecar (note
`description_images_failed`; `--force` reads it again); the run goes on. Ctrl+C stops cleanly (exit 130). One run
per shop at a time (a lock; a second run stops with exit 4). A script that calls `description_images.run()` keeps its
work under `if __name__ == "__main__":`: the spawned worker imports the calling script again (example_15 hung once
without it, its worker collecting a second product).

**Files**, per shop, under `scripts/output/shops/<shop>/description_images/`:

```
<product id>.json            the sidecar: the rows as read per image and slice, skipped links with their rule,
                             each image's host (naver / seller), the engine and its settings
cache/<product id>/<sha>.bin the downloaded bytes of that product: `--prune-cache [--products ...]` deletes them
                             (the sidecars stay; a --force run fetches again)
```

The cache holds ~6 MB a product (~6 GB per 1000, 2026-11-07): prune it once the sidecars are good (whether to keep
it by default is still open with the owner).

A product is read again when its links or the engine (rapidocr, onnxruntime, params) changed, or when an image
failed last time with a 5xx / network error (`failed`); a 4xx or a non-image (`gone`, e.g. an expired proxy-smartstore
token) and a seller's hotlink block (`refused`) are not retried; the transform notes them (`description_images_partial`).
Naver first (the owner, 2026-11-07): a body Naver cut into snap tiles is read from the tiles; the seller's own `<img>`
sources in its HTML (7583123963: 45 instead of 113) are fetched only when a tile does not read, and used when every
source reads (a seller's host can be 5x slower: 13369469193 266 s vs 54 s; its proxy-smartstore links expire; the
tiles also carry the store's banners, which the text rules cut). To fetch less, an image another product of the store
already read is reused from its
sidecar (`reused`), equal slices in one product are read once (dHash), and a first SmartEditor image lower than
400 px (the store's header strip) is skipped (`first_header`). Measured 2026-11-07 on the 977 slices of the 50 golf
sets: 53 % useful (copy 26 %, spec tables 17 %, set contents 9 %), photos 30 % (cheap to read), store boilerplate
17 %. Not done on purpose: a per-slice "has text" detector (it costs more than the OCR it saves) and a height rule
before the download (set contents sit on small cards: >= 1000 px loses 49 of the 330 useful slices). The download,
not the OCR, sets the time (~13 s against ~7 s a product). A store's first product costs the most (~10 requests,
6.6 MB); later ones reuse its banners. Run step 3 soon after step 2: proxy-smartstore links seemed to expire within
about a day (2026-11-07, not re-checked), and an expired one is `gone`, not retried. Not checked yet: a batch well
over 20 products for the worker's memory and time per product.

**The guess** (`description_measures.py`, offline, in the transform) has two layers:

* the **core**, for every category: what a seller writes of the product itself: a packed weight / box (박스 / 포장 /
  택배 / 패키지), a set / product weight (세트 / 본품 / 제품 / 상품 무게; a row labelled 무게 / 중량 / weight with kg,
  even when OCR split the label: "무 / 0.6kg"), a product size triple (크기 / 사이즈 / 규격 / size, or with a unit:
  "W53 x D38 x H62.5 cm"; read as a fact and, since 2026-11-10, no field's: a product is not its box). Live check
  2026-11-07 on other categories: a camping chair (625 x 530 x 380 mm), a kettle (0.6 kg, 170 x 170 x 100 mm); a
  kettle and desks whose images give sizes only as photo callouts: nothing;
* a **parts profile**, only where the category is sold as a set of like items in a container. Profiles are data
  (description_measures `Profile`: the items' weight / length ranges and labels, part labels that are never an item,
  the container's words and ranges, accessory words, count words, a count row, the 상품정보 row that names the
  container and its "no" values, plausible bands; since 2026-11-10 also what the shared items code held for golf:
  the spread of a set's weights, the rows under a table's header, a part maker's table, the things sold for the
  container), mapped by the **Naver leaf category id** in `CATEGORY_PROFILES`:

  | Naver category | profile | items / container |
  |---|---|---|
  | 50002788 골프클럽 > 풀세트 | `GOLF_SET` | clubs (their weight and length tables, see The clubs; 샤프트 / 헤드 / 그립 are parts) / the bag (weight, height, mouth, sides) |

  A category with no profile gets the core only. Add a profile only when the core cannot read a category's images
  (its own tables of parts); a new category is otherwise just its shop rule's `description_images` switch.

Never read in either layer: a shop rule, customs, a person, a price, a disclaimer, anything after a cross-sell
heading to the end of the image. The heading is "함께 / 같이 구매하면 ...", "추천 상품" or "관련 상품" (2026-11-10): the
returns text "다른 상품으로 교환하는 경우" and "원하시는퍼터를함께구매하시어 ..." are sentences, and on a description
that is one tall image they cut the whole spec away (3 of 120 sets lost their tables, 12606747315 at row 19 of 311).
With a profile, a row is the container's when the nearest row that names one, on it or up to 10 rows above, names
the container; when that row names an **accessory** (the profile's word list: a Boston bag, a shoe bag, a pouch, a
half bag) its size and weight are neither the product's nor the container's (13513786835: the add-on Boston bag's
"L48×W24×H30CM" was the package's width and height). A row naming both is the container's ("총무게:(캐디백+보스턴백)
약4.95kg"). Not a weight: "약1.5kg경량화되어" (1.5 kg lighter); not a club: "47인치 대응" (what the bag takes).

**The clubs** (the profile's items; mined on the 120 collected sets, 2026-11-10). Their tables come two ways: a
labelled row with the values after the label ("클럽길이(inch) / 45.5 / 43", "총중량(g) / 308 / 326 / ... / 545"; the
label in any cell, OCR's spellings too: 클럼무게, 충중량, 길치), or a header naming the columns with one club per row
below ("클럽넘 / 로프트 / 라이각 / 전체길이 / 스윙웨이트 / 플렉스 / 헤드중량 / 총중량", then "1W / 10.5 / 58 / 45.25 inch /
D0 / R / 197g / 320g"; up to 18 rows; the SR and S rows of a club are the same club; a shaft maker's table, TIP /
Butt 외경 in its header, is not the clubs').

* **Length.** Inches (32-48.5) and cm (81-124) never meet, so a value needs no unit mark ("110.49/43.5", "약114cm",
  "45,25", two cells glued: "116.84107.32"); a cm value alone on its row counts too ("(114.935cm)"). Lengths are
  read at any OCR confidence: a row's confidence is its weakest cell and the driver's short row is the one that
  fell under 0.9, so an iron's or a putter's clean row stood as the longest club (25 of 120 sets). **The longest
  club is the largest length stated, taken only in the driver's band** (the profile's `longest_mm`, 42.5-48.5 in:
  the 118 stated drivers are 43.5-46.0 in, a ladies' 3-wood 41-42.5 in); below the band the driver's row was not
  read and the baseline driver stands in, never a shorter club. A row that lists several flexes or optional
  shafts gives the longest of them, 6-25 mm over the one sold on 7 sets (six ladies' sets with an R row, one
  optional shaft; left as it is: the margin covers it).
  On the 120 sets: 116 of the 118 stated drivers (81 before, 25 a shorter club, 12 nothing); the two not read:
  11775161460 ("길이(인처) / 445": the decimal point lost), 11061911792 (the row's label read "3()").
* **Weight.** One club's total is 240-650 g (the lightest stated is 252 g; a wood's head 197-235 g). A row of a
  weight label that holds only weights under a club's makes the label a part's in that image, on its other rows
  too ("중량(g) / 198 / 202 / 207 / 233" over "중량(g) / 257 / 263 / ... / 297": the woods' and the irons' heads,
  which made the median club of 7583123963's 13-club set 296 g; the only set of the 120 with such rows). 스윙웨이트
  beside a total is the balance, not a part. A bare number after a name is the shaft's model, not a club ("약256g /
  C1(ULT 250 J-L)" gave a 250 g club on three rows of 9321714669). Read for 94 of the 120 sets (80 before).

**More of the page, 2026-11-11** (the 300 sets of the fairwardgolf job; the products on the flat default weight
went from 109 to 23 of 426, every one of the rules below a regex or a condition; one fixture per rule in
`fixtures/measures/`, made with `make_measures_fixture.py` from a real product):

* core (every category): shipping rules ("5kg내외", "2kg까지는", "160cm이상"), a buyer's height and weight, the
  returns' shoe box are never read; "풀세트 패키지" is the set, not its box; the notice's "크기,중량 1230mm/10kg" is
  the product's weight.
* golf sets, the bag: machine-translated bag words (볼백, 볼 가방, 공 봉투, 건백); the bag as an item of a
  composition line, or "8개+캐디백"; a gift's 레디백 / 버킷백 / 텀블러백 is an accessory; a bag table with no bag
  word in reach (its mouth "9형"); a list of the clubs from the driver to the putter with no bag, or a title that
  lists the clubs ("[드라이버+우드+유틸리티]", "드라이버 10.5도 R, 아이언 6개"), says no bag (weak); the typed "<캐디백
  별매>" beats a bare bag word in the title (9266324198: "레프트 캐디백" there is a cavity back); nothing says:
  the bag assumed (flagged).
* golf sets, the count: an option value's "11개", "12+볼백", "10클럽"; "11PC" / "11ps"; the 풀세트구성 row and
  composition lines kind by kind ("드라이버 1개/아이언8개/퍼터 1개", "드라이버, 7아이언세트, 유틸리티, 퍼터", the
  typed "1> 드라이버 ... 4> 아이언 / 6,7,8,9,P,S / 5> 퍼터"); a single club filed as a set (치퍼, 드라이빙 아이언,
  접이식 / 실내 골프채, options of one club's lofts x shafts) is one club without a bag; an option's "N개" beside
  other options ("8개구성 NS820", "아이언 9개") is the irons', not the set.
* golf sets, the clubs' weights: OCR's labels (총 종량, 클럽 증량, 무계, Club중량, 클립 무게, T/W(g)); a weight in
  its label's cell, one row above its label, or after an option index ("1378(S:#7)"); head + shaft + grip columns
  (PGM, SMACK) summed per club; the #7 iron's weight ("410(#7)", "#7 약320g", "(7번 R 기준)") for the clubs no row
  weighs in the same image ("(#5 기준)" is a wood's own); a table of half the set or more plus its own median for
  the rest (in place of the count x the page's median); per-row tables that together are the set, summed; a set
  of 3-4 clubs needs a spread of 1.1 only.
* golf sets, the length: a bag's "대응 / 지원" length and a shaft maker's table (CPM, torque, kick point) are not a
  club's; a driver over 46.5 in needs two rows; OCR's labels (같이(inch), 집이(nch), "길 / 이"), inch spellings
  (인츠, 인체, 인처) and a lost dot ("4375": 43.75); an L / A variant takes the driver row of its flex when it is
  within 30 mm of the longest (a wood's L row never stands for the driver).
* **Count**, in the order of trust: the variant's own option values ("스틸12P+캐디백" / "스틸9P+캐디백": the variants
  of a listing are different sets), the title / 모델명 ("12pc", "9종", then the profile's "클럽 10개", "10개 풀세트",
  "[11개]"), the 상품정보 row 총클럽개수 (it disagrees with the title on 5 of the 120 and the title is right on 4:
  10481094198, "10개 풀세트" with a row of "3개"; the row is right on 9321714669, title "클럽9개", row "11개" with
  two gift clubs: left as it is), the images (the weakest, a weak part of a composition: a page shows other sets; a
  head's make, "4피스 티타늄 페이스", "4PCS단조", is no count). **The seller's own club table goes before a count of
  pieces** (Total, below): a listing's "12개" may count the bag and the head covers, and some listings state no
  count at all.
* **Total.** When one table gives exactly one weight per club of the set (as many values as the count, the
  heaviest at least 1.25x the lightest), the total is their **sum** (`how`: "sum of N club weights"); of several
  such tables (an R and an S set) the lightest. A table is one row, the rows of one image (or of the typed text)
  under one label, or the rows under one header.
  Else **a full table before the listing's pieces** (2026-11-10): when the listing's count is larger than a full
  table by up to 3, or nothing states a count, the total is that table's sum and the club count is its length.
  8053135821, 총클럽개수 "12개" (the box's "12-Piece": nine clubs, a stand bag, two head covers): the nine rows
  "Driver / ... / 336" to "Putter / ... / 532" are 3955 g, where 12 x the median said 5340. 13657325637, "11피스"
  with the bag (typed "10개의 클럽으로 구성"): the ten typed weights, 3634 g. No count stated: 5543663553 (two rows
  of ten), 7674852369 (twelve clubs under one header). **Full** is one row or the rows under one header (not rows
  gathered under one label: the two rows of 13446843026 hold 11 of its 12 clubs), at least 9 weights, the
  heaviest 475 g and up: the ladder runs to the putter (the putters stated are 485-549 g, the heaviest wedge
  462 g). Without the putter the table is short of the set and the listing's count stands (X HOT, "총 11개
  클럽": its ten weights end at the SW, 8974646004). On the 120 the shortest set tabled is 9 clubs and the longest
  part of one that holds a putter 7 (13627933340); the two listings seen to count pieces are 1 and 3 over. With no
  count, full tables of two lengths are two sets: no count. The three numbers are the profile's (`full_items`,
  `full_last_g`, `pieces_over`). A count the table gives is a weaker source than the title: confidence 2
  (`count_from: "table"`; `count_listed` keeps what the listing said).
  Else "N clubs x median club weight", only when the weights read **cover at least half of the clubs**: as many
  clubs as half the count, the heaviest at least 1.25x the lightest (the profile's `set_spread`). Clubs, not
  values: weights within 2 % of each other are one club's (the profile's `same_item`), so a club by two flexes
  is not two (10816781893, 9 clubs: the driver "약252 / 약255", the utility "약292 / 약296", the #7 iron "약320g /
  약321g" are 3 clubs, and 9 x 296 = 2664 g stood; an iron's step is about 2 % too, so a ladder of irons counts
  about half its clubs: the baseline club then, never a median of too few). A driver by nine shafts, two woods
  and a utility (8029218821: 18 weights, 292-340 g, 3090 g for a set of about 3.8 kg) or the driver's and the
  wood's four weights of nine clubs (13728931694) are not the set. Else "N clubs x baseline club weight" (the
  operator's `item_g`). On the 120 sets the composed weight holds: a sum on 25 (21 with the listing's count,
  each equal to the research's sum checked by hand; 4 with the table's own count), the median on 22, the
  baseline club on 51; 22 have none (21 the default, 1 the seller's own weight).

**Whether the variant has the container**, in the order of trust (2026-11-10; the first that says it decides):

1. the variant's own option values ("+골프백", "백미포함");
2. the title, 모델명 and the product's one-value facts ("캐디백 포함", "백세트제외", "10개세트 클럽만");
3. the profile's 상품정보 row, 골프백포함여부: "미포함" is no, any other value ("캐디백", "스탠드백", "캐디백, 보스턴백")
   yes (on 81 of the 120 sets; the row and its "no" values are the profile's data);
4. a container sold as a paid add-on (`specs.options.supplements`: "젝시오 골프백 추가 구매" 350,000): the set has
   none. An accessory add-on ("RB LADY 여성용 보스턴백", "4. 골프백 / 럭셔리 신발가방") says nothing, nor does a thing
   for the bag (the profile's `container_trim`: "캐디백 항공커버", "캐디백 네임택");
5. a sentence of the typed text ("골프 가방 불포함 상품 입니다.", "캐디백은 포함되어 있지 않습니다."), then one of the
   images ("본 풀세트는 골프백 미포함 제품입니다", "캐디백까지 포함된"; a weak part: confidence 2 at most); a no wins
   over a yes. "클럽만" says no bag ("[클럽만]", "10개세트 클럽만"), the clubs' own does not ("클럽만의 기술력").

Weak signs (a "조합" title, a composition list without a bag) are not used.

**The order of sources** (the owner, 2026-11-10; `merge_fields`). The flat category default is the last resort. A
field takes the first of:

1. **the seller's own statement of that field.** The server path's value (`source_stated`) is kept whatever the
   description says. Else a statement read in the description (`guess`): a packed weight ("패키지 무게 : 10.8kg"), a
   box (its three sides), a set's or, outside a parts profile, a product's weight. It takes the default's place
   whatever its size (13495098284: the box "-패키지크기:L20×W16×H121cm" read from an image used to lose to the
   default 1250 x 280 x 230 only because it is smaller). Typed: 5; read from an image, or a set / product weight
   (its kind is open): 4; the same line read both ways is the typed one. A row OCR read below 0.9 (its weakest
   cell) gives no statement (research: ~38 % of such digit boxes were wrong). A triple may be in inches ("48.2 x
   12.7 x 8.5 inches"). A stated packed weight goes before the composition also when it is under the composed
   product weight (that weight rests on baselines; the statement is the seller's).
2. **the composition from the set's parts** (`compose`, `_items_total`, `_boxed`), only when the category's row
   has the `baselines` block and the category a parts profile. Each part comes from the product's own data when
   it is there, from the operator's baseline when it is not:

   | field | composed as | `how` |
   |---|---|---|
   | product_weight_g | the clubs (the sum of one table, else the count x the median when the weights cover half the clubs, else the count x `item_g`) + the bag (nothing when the set has none, its stated weight, else `container_g`) | "clubs + bag", "clubs, no bag" |
   | package_weight_g | the product's weight as the field ends up (the seller's, a statement, the composition) + `carton_g` | "product weight + carton" |
   | package_length_mm | the longest club read (the driver), else `longest_item_mm`, + `length_margin_mm` | "longest club + margin" |
   | package_width_mm, package_height_mm | `sides_mm` for a set without a bag, `sides_with_container_mm` with one | "box side, no bag", "box side, with bag" |

   Confidence 3 when it is worked out wholly from the seller's own figures (the levels above), else 2.
3. **the flat category default** (1), only when the composition is unknown: the weight when the number of clubs
   or the bag's state cannot be told, the two sides when the bag's state cannot (the length needs neither). The
   package's weight follows the product's: no weight to put a carton on, no composition. A known composition is
   never dropped for being small: 13302492097 and 12966969668 are a driver, a wood and a utility without a bag
   (총클럽개수 "3개"), 3 x 340 = 1020 g and 3020 g packed, not the flat 5700 / 7000 g of a full set.

A composed field says how it was built: `source: composed`, `how`, `parts` (`[{part, value, from, quote}]`:
`from` is "stated", the clubs' total as it was made ("sum of 10 club weights", "11 clubs x median club weight",
"10 clubs x baseline club weight"), "baseline", "not in the set", or the field it is; a clubs part says where the
count came from, `count_from`: "listing", "description_image" or "table" (the clubs' own full table; then
`count_listed` is the listing's count it set aside), a bag or box-side part who said the bag's state, `said_by`:
"listing", "description_text", "description_image"), `baseline` (who approved the operator's amounts in it, and when) and,
as `compared`, the default it replaced. Under a seller's value `compared` is the description's statement or the
composition, for the reader. 11659201020 ("클럽10개 백포함 R세트"): the R table's ten weights, 3892 g, + the bag's
stated 3.8 kg = 7692 g (3), + the carton = 9692 g (3), the 45.25 in driver + 100 mm = 1249 mm (3), 400 x 320 (2).

**A box is one statement**: its three sides are taken whole or not at all (`box_not_whole`). Of a gift's "증정
골프공 패키지 사이즈 30 x 20 x 10cm" the 300 mm length is refused, and 200 x 100 must not stay as the width and
height of a 1250 mm package (2026-11-10; before, the sides were merged field by field).

Measured in memory on the 120 collected sets (2026-11-10; products per level, by the first variant):

| field | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| product_weight_g | 0 | 1 | 7 | 91 | 21 |
| package_weight_g | 2 | 1 | 5 | 91 | 21 |
| package_length_mm | 2 | 1 | 113 | 4 | 0 |
| package_width_mm | 2 | 1 | 0 | 97 | 20 |
| package_height_mm | 2 | 1 | 0 | 97 | 20 |

The 21 weights left to the default: the bag's state unsaid (20; 8 of them with no club count in the listing
either), no club count anywhere, in the listing or as a full table (1: 9266336330). The figures came from a one-off
research script over the 120, not kept.

**Absurd values are never taken** (`compared.rejected`; `refused` on the composition that stood in): a statement
outside the field's band (the operator's `plausible` in category_measures.json, else the profile's, else the
core's: weight 10 g - 200 kg, a side up to 3 m), any value above the band or more than 3x today's value
(`far_above_today`: a misread "45.5kg", another product). The band's lower side is for statements only: a
composition under it is a small set, not a misread (three clubs). A stated packed weight under the product's
weight is taken all the same; when that product weight is the seller's own (4-5) the field carries `flags:
["below_contents"]` (a box weighs at least what is in it: two statements of the seller, the operator decides).

**Known limits** (2026-11-10, left as they are). A "1+1" listing ships two sets and is weighed as one
(5684497984: about half its weight). A table is not bound to a variant: of several whole tables the lightest
stands for every variant (the S세트 variants of 11659201020 and 5543663553 get the R row, about 300-350 g under;
the two women's variants of 7674852369 get the men's twelve clubs). On a page of several models the bag's
weight may be another model's bag (12696567111: the XR24 stand bag's 4.1 kg on the XR26 set) and the longest
driver stands for every variant. The median is the page's, also of clubs that are not in the set (12965394174:
the add-on woods and utilities; 7583123963: no iron's weight is read).

The owner's rule on parts (never summed) holds for the
seller's candidates (`specs.measures`); for the composition, summing the items is the point. Read as facts and no
field's since 2026-11-10: a product's size, the bag's length, mouth and sides (the box's sides are the baseline's;
7583123963 states a bag of 130 cm in total where the driver + the margin gives 1230 mm). Notes:
`measures_from_images` (fields no longer today's: stated in the images or the typed text, or composed; per variant count), `description_images_missing` (switch on, no
sidecar; never holds), `description_images_stale` (the sidecar was read from other links, an older collection:
not used; run the stage again).

### The images' text, ready for the translation step

Checked by eye against the images (2026-11-07, 20 live sets): prose reads near-exact, spec tables ~95 % (a digit
lost now and then, a degree sign read as 0), small lettering on photos poorly; the rows as read are not a text yet.
`run_transform` turns each product's current sidecar into clean Korean blocks (`description_image_text.py`) and
writes them for the next step, translation (not done here). Fixed after the 100-run check (2026-11-08): a
cross-sell cut starts only at a heading (a sentence cut 292-330 rows of three Sterna listings' spec sheets), a table
heading or row repeated in another table is kept (only a slice overlap is a repeat), short flex rows ("R / D1/296")
are table rows, and a store banner's address, hours, services and map labels are cut:

```
scripts/output/shops/<shop>/translation/<product id>/
    description_images.ko.txt    the blocks to read: a header (format, sha256), then "[b01 text image 1]" / "[b02
                                 table image 3]" and the block; table rows are cells "a | b | c"
    description_images.ko.json   {format: description_image_text/1, product_id, key, sha256, blocks: [{id, kind:
                                 text | table, image, text}]}
    description_images.en.json   written by the translation step: {format: description_image_translation/1,
                                 source_sha256: the .ko sha256 it translated, blocks: [{id, text}]}
```

**One flag** on every prepared product says where it stands; the translation step (and any checker) reads the flag,
never the folder: `product.description_images_text = {state, blocks, chars, sha256, dropped, ko, en}`, `state`:

| state | meaning | the translation step |
|---|---|---|
| `off` | the category does not read its images | nothing to do |
| `not_read` | it does; description_images.py has not read this product's current links | run the stage first |
| `empty` | read; nothing left (photos, the shop's own blocks) | nothing to do |
| `to_translate` | `ko` written; no translation of this exact text | translate `ko`, write `en` with `source_sha256 = sha256` |
| `translated` | `en` exists with `source_sha256 = sha256` | done (a changed Korean text goes back to `to_translate`) |

What is cut (counts per rule in `dropped`): rows repeated in the product (slice overlaps), low OCR confidence (<
0.6), fragments and photo labels ("B4", "POWER TRAJECTORY"), prices (KRW, yen), contacts (phones, addresses, URLs),
the shop's terms (delivery, returns, orders, A/S), store info (branches, hours, channels, events), legal notices,
promotions and dealer claims, everything after a cross-sell heading in an image, an image that is mostly the
shop's own notice, and the page text's sentence rules (description_clean.clean: greetings, store claims, ...).

**Kept on purpose, for the agent who writes the description to leave out** (the owner, 2026-11-07: this step
gathers context; a little extra text is fine): screenshots of buyers' reviews that some sellers put in the
description images (13777887875: a "재팬잇 Customer's Real Review" banner with masked ids "ridb*", dates "25.10.23",
"사이즈:240", "175cm, 77~79kg", reviews of shoes and a cap). They read as text like the rest; they are never the
product's description or facts, and may name other products and buyers' body data. The instructions in every
`.ko.txt` / `.ko.json` say so.
A store's block repeated in several listings (a model's spec sheet) **stays**: its `key` (sha256 of its text, 16 hex)
is the same in each, `shared` says in how many of the store's products, and the translation step translates one key
once; `shared` is not part of the product's sha256, so another product's change never resets a translation. On the
20 live sets: 4369 rows -> ~500 blocks, ~60k characters. A degree sign read as 0 is put back in angle rows ("+1.00"
-> "+1.0°"). The `.ko.txt` header and the `.ko.json` carry the instructions for the translator (OCR faults to
expect, keep numbers / units / model names / table cells, do not invent, translate a key once) and the category's
glossary (`GLOSSARIES` by Naver category id; 50002788: 로프트각 = loft, 라이각 = lie angle, ...); neither is part of
the sha256.

## Transform (collected -> prepared, per shop)

The step after collection and before translation and Shopify: offline, deterministic, no AI, no English, no
network. Korean stays Korean; each prepared product lists the Korean texts the translation stage must translate.

```sh
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # keep the run before the next collection
.venv/bin/python scripts/run_transform.py fairwardgolf               # every kept run -> prepared/
```

```
scripts/output/shops/<shop>/collected/<category>-<UTC time>/   products.jsonl, images/, manifest.json (read-only)
scripts/output/shops/<shop>/prepared/products.jsonl            one prepared product per line, rebuilt each run
scripts/output/shops/<shop>/prepared/report.txt                ready / held counts, held products and why
```

example_99 overwrites its `products.jsonl`: a run not kept before the next collection is lost. The shop is the
namespace of the source keys, one shop and one category per run; a product in several runs comes from the newest.
A run is copied into `<run>.partial` and renamed when complete; only folders with a `manifest.json` are runs.

**Prepared product** (`transform.Prepared`, `format: prepared/5`; 5 since 2026-11-10: package `confidence` is 1-5 (1-3 before) and a field may be `source: composed` with `parts`, `baseline` and `refused`; 4 since 2026-11-08: reviews sanitized; 3 since 2026-11-08: no shop leaves, `product.attributes`
instead (see Placement); 2 since 2026-11-07: a variant's `package` fields
may carry `how`, `quote`, `flags`, `from` (`description_text`: the quote is typed text, not an image's) and `compared` (the value not kept, see Package weight and size), and `product` has
`description_images_text` (the images' text flag, see The images' text)): `key`, `shop`, `status` (`ready` / `held`),
`held` and `notes` (`{code, detail}`), `source` (run, line, link, channel_no, product_id, category_id), `product`
(`title_ko`, `brand_ko`, `brand_source`, `attributes` (`{gender: {value, variants, evidence, flags}}`), `options` `[{name_ko, values_ko}]`, `facts`,
`variants` `[{source_id, naver_variant_id, options_ko, price_krw, price_usd, sku, available, package}]`, `pricing`,
`specs`, `personalization`, `addons`, `rating`, `reviews`, `images`), and `texts` `[{id, kind, ko}]`: the translation
worklist, `id = <kind>:<sha256(ko)[:16]>`, so the same Korean text has one id (one translation) in every product.

Rules (`transform.py`, each from a real case, research 2026-11-05 on 23 collected sets: on 10 the naver-harvester
published, SKUs and prices equal on 201 of 201 variants):

- **Prices**: KRW = the product's price + the variant's `extra_price` (the page's own answer; option names are not
  parsed for money); USD = rounded up to the cent at the shop's rate (kept in the record; Shopify's cost and price
  are made at publication by the shop's price rule, see The price); no compare-at, not taxable.
- **Variants**: the category's choice (`transform_shops` `paid_variants`, off by default; on for fairwardgolf
  50002788, owner 2026-11-06), made again from the page's options (`choose_variants`): the line's own choice may
  differ. Left-out paid variants: note `paid_variants_left_out`.
- **Options**: the option groups but CUSTOM / SIMPLE, the observed rows only, sold-out rows kept (`available: false`);
  an axis
  with one value becomes a fact; one row -> one default variant; an axis about writing a review / a coupon
  (리뷰, 후기, 쿠폰, 적립) is dropped with its discounted rows. Over 3 axes: held; over the shop's variant cap:
  the first ones are offered (`variants_capped`, below).
- **SKU**: the shop's prefix + 24 hex of sha256({schemaVersion, sourceId, tenantOfferKey}) (the harvester's recipe).
- **Specs shown**: all 상품정보 rows but 상품번호, 제조일자, 이벤트, 사은품, 인증정보 (purchase-agency / KC legal text)
  and pointers ("상세페이지 참조"); "(구매대행)" / "해외구매대행" and a bracketed importer ("일본(IRUGI SHOJI)") are
  taken out of 원산지 (brackets inside brackets too: "중국산((주)위스트OEM)" -> "중국산"). Option names and values are
  shown with single spaces, and without the seller's numbering ("선택1 9도SR" -> "9도SR") when every value of the
  axis has it and the values stay different (else kept, note `option_values_duplicate`); add-on groups and names
  without theirs ("1-1.남성 장갑"). The SKU keeps the raw tuple.
- **Rows that are not versions**: a row asking for a delivery message (배송메세지) is dropped; a one-value axis named
  like a hidden row (상품번호) is not a fact.
- **Delivery**: `delivery` from the page (fee as charged, scope international / domestic, customs, lead time);
  notes `shipping_paid` and `overseas_shipping`. In a shop with the price rule the base fee of a PAID or
  UNIT_QUANTITY_PAID listing goes into the purchase; any other fee type counts as free (see The price). An
  `extra_fee_text` that is only the return fee the notice states ("18000" = 반품비용 편도 18000원) is dropped;
  another bare number ("7000" beside a 4,000 area fee) is kept.
- **Notes for later stages**: `option_name_placeholder` (an axis named 선택 / 선택2 / 옵션 / "옵션+...": name it from
  its values in translation; a fact with such a label gets an empty label), `paid_addons_left_out` (how many paid
  add-ons were not offered), `title_names_one_variant` (a word of one option value is in the title, "12종", while
  others are sold too: the translation keeps the title to what every variant is; words that together point at part
  of the values count, "12종" with 12종 / 9종 x 스틸 / 카본, "10.5R"; 여성 / 남성 do not when the title names both),
  `few_pieces` ("[3PCS]" in the title or 모델명: a few clubs, not a full set), `purchase_agency`
  (구매대행 in the specs / notice / delivery policy), `description_mentions_gifts` (이벤트 / 사은품 rows are hidden,
  the description still promises 사은품 / 증정), `variants_capped` ("486 -> 100": more combinations than the
  shop's cap; the first ones are offered, in stock and cheaper first, one row per option value first so every
  value stays on sale; not held). `description_ko` and `description_images` (the seller's boilerplate out, see
  Description; what was cut in `description_dropped`) are carried for the later stages (not in `texts` yet).
- **Reviews sanitized** (`review_clean.py`, the owner 2026-11-08). Every review is kept with its score; only a
  sponsored one is dropped.
  - **Cut out:** spans about the Korean purchase, since they do not describe our shop: shipping, customs, prices in
    won, value for money, the seller and their service, packing, the seller's gifts, other platforms, review
    promises. Filler is cut too: thanks, wishes, "잘 쓰겠습니다", decoration. A span is a whole clause up to its joint
    or the sentence end and never crosses a product word, so "배송도 빠르고 디자인도 맘에 듭니다" -> "디자인도 맘에
    듭니다".
  - **Kept, on purpose:** short praise, "not used yet", criticism.
  - **Grades:** `text_grade` is `full` (names the product), `short` (an opinion) or `rating_only` (no text left: the
    score and the photos stay). `text_quality` 0..100 gives an order.
  - **Where the patterns come from:** agents mined them on 666 real reviews (`fixtures/reviews/golf_50002788.jsonl`)
    and checked each other's work. `test_review_clean.py` runs on all of the corpus: no review lost, no won amount
    or decoration left, no product word cut.
  - **On the 143 trial sets:** 448 of 448 reviews kept: 263 full, 154 short, 31 rating only, 192 trimmed.
- **Spec rows vs variants** (`spec_variants.check_specs`): a row is compared with the sold combinations on one fact
  read the same way from both. Material is STEEL / CARBON ("남성용 SR스틸" is steel), and bare R / S values take a class
  only when the description writes it on the whole value, "스틸(S) / 카본(R)". Club count is a stated total (12종 / 9P /
  13PCS / 10개세트 / "4스틸") or the clubs of a full part list ("드라이버 우드 유틸 7아이언 퍼터" = 11). The composition rows 아이언개수 /
  아이언 구성 / 풀세트구성 are one set: they follow 총클럽개수, else the fewest clubs they imply. A 풀세트구성 naming several N아이언세트 is a
  checklist and stays product-wide. Model year is 출시 2026년형 vs XR26 / "XR 24". A row that fits no variant is dropped
  (note `specs_fit_no_variant`). A row every variant's own value already states (스틸9P / 카본12P) is dropped (note
  `specs_stated_by_variants`). Otherwise the row is kept with `for_ko`, the option values it fits as written (`아이언 구성`
  -> `["12종"]`; note `specs_bound_to_variants`). Composition rows with no decidable set are dropped (note
  `specs_composition_undecided`). Other rows whose words fit part of the values (모델명 ... 9종) get
  `specs_name_one_variant`, printing the row as written and its own span ("모델명 26캘러웨이 풀세트 XR26 FULL SET 12PC: XR26").
- `title_names_one_variant` (`spec_variants.title_one_variant`): the words are reported as the title writes them, in
  title order, and words that touch are one span ("XR26", "9도SR"). A gender word counts only when every value without
  it names the other gender. 백포함 / 백세트포함 / 캐디백포함 are the same thing. A part-list value counts as its club count, so
  "(클럽10개)" names "드라이버 유틸 7아이언 퍼터".
- **Description** (`description_clean.py`, research 2026-11-06 on the 40 golf sets): `clean(text, store_name,
  promo_hidden, brand)` drops the seller's boilerplate from `description_ko` by line and sentence. A SmartEditor line
  ending on a connective (로, 와, 의, "," ...) goes on in the next line, and the whole sentence is dropped. The rules:
  return / exchange / delivery / customs notice blocks up to the end of their component (the empty line; 12 lines at
  most when the text has none, note `description_policy_block_unbounded`), phone numbers with separators, TalkTalk /
  유선 전화 / 고객센터 / 카카오톡 상담, 네이버페이 자동수거, a greeting-only line, "감사합니다", signatures ("-제이디스포츠-", "듀벨로 올림"), duties, lead
  times ("배송은 9~14일"), 최저가 / 득템 / 안심하고 구매, store claims ("저희 ...는", "공식 온라인 대리점", "정식 수입업체") and the store's name in a
  short sentence (off for a brand's own store), the monitor disclaimer, jump lines ("▲ 이동(상단)", "▲TOP"), and a 사은품
  block only when the 이벤트 / 사은품 rows are hidden. Product lines that look like these stay: 그립 1회 무상 교환, 랜덤 발송, 정식통관
  품질AS보증라벨, UPC/GTIN numbers, #5-#9, - 세트 설명 -, [안내사항], ☆ 캐디백 증정 ☆, 무상 A/S 3년 보장, - 추가선택 -. `clean_images` drops
  description images whose decoded file name marks a seller banner (배송, 통관, 공지, 이벤트, 하단배너, foot_info, as.jpg ...;
  proxy-smartstore links decoded); snap tiles are never cut. Notes: `description_all_boilerplate`,
  `description_covers_several_products` (2+ in-page sections, a 모음전 page), `description_tiles_include_banners`
  (banners baked into Naver's tiles).
- **Description cleanup** (`description_clean.py`, pilot 20, 2026-11-06): also drops KRW price promotions
  (`price_krw`: "정상가 865,000원", "190,300원 할인", "22% 할인"; our prices are USD), lines about a product card the parser
  left out (`cross_sell`: "아래 링크에서 구매"), and contact closings ("여쭤봐주세요", "답변드리겠습니다"). A sentence goes on across lines
  ending on 만큼 / -시면 / -으면 / -하면 / 는데 / 지만 / 니까 ("타격면", a noun, does not), so a contact sentence goes whole. A store
  named for its trade ("일본 구매대행 해피마로") is matched without the prefix. When no word of 2+ Hangul or Latin letters is
  left, the text is None with note `description_junk` (13741767690: "o"). Images: new names 톡톡, 하단_상페 / 하단고정배너 / 하단안내,
  베너. A Latin name that is Hangul typed on the 2-set keyboard ("gkeksqpsj" = 하단베너) is matched as Hangul, and so is the
  tile note. With the description HTML, `clean_images(images, html)` reads SmartEditor's data-linkdata. It drops
  images that link to TalkTalk, Band, Naver blog, Instagram, YouTube, a Kakao channel, Facebook or a store page
  (`link_banner`), and strips 40 px high or less or wider than 25:1 (`spacer`). originalHeight 1 means not measured,
  and those images stay.
* driver loft (R-LOFT): 드라이버 로프트각 is compared with the loft each variant's values name (10.5도 / 9도 SR / 9.5 SR /
  10.5R, 7-14 degrees). The row is dropped (specs_stated_by_variants) when every variant states its own loft, bound
  with for_ko when some are silent, and dropped (specs_fit_no_variant) when it fits none. A row that lists every loft
  sold ("11.5도, 10.5도") stays product-wide.
* R-DESC also reads the sentence form "플렉스 R 모델의 아이언에는 카본 샤프트": a whole value, then 모델 / 플렉스 / 사양, then the shaft
  material in the same clause, with no part other than the irons named.
* R-TITLE treats numbers with units as one word: the title's "11.5" / "11.5L" names the value "11.5도"; "유틸4" / "4U" /
  "4번유틸" name the 4번 of a 유틸리티 axis (and 우드5 / 5W the 5번 of a 우드 axis); "10.5R" and "10.5도" are one loft. Bag words
  (골프백 / 캐디백 / 스탠드백 / 카트백 / 백포함) are one thing. When some values say "캐디백 미포함", a title bag names the values with the
  bag. The same words feed the specs_name_one_variant row match, e.g. 모델명 "[드라이버11.5L+...+우드5L+유틸4L]" -> "11.5L, 우드5L,
  유틸4L".
- **Pilot 20 (2026-11-06)**: a variant carries `today_dispatch` (the seller's todayDispatch per variant: one of two
  may ship today); a tag every value starts with ("[당일출고]") and a "(선택)" in front of an option name are left out
  (the SKU keeps the raw tuple); past the cap the rows are taken in turn from each value of the first axis; notes
  `few_pieces` also from 총클럽개수 of 5 or fewer, `gift_hidden` (a hidden 사은품 row naming a thing in the box, not
  points or a coupon: "오리지널커버 증정"). `delivery.lead_time` passes through: check `today_off` before
  `today_cutoff`.
Spec rows vs variants, run 40b additions (2026-11-07):
- A count right after a part word is that part's count, not the set's total: "아이언 선택 (8개)" in an axis name, "아이언 6개"
  and "웨지2개" in a title or value. "아이언포함 11개", "클럽11개" and "드라이버+8개 아이언" are still totals or not counts. The option
  axes give a lower bound (axis_floor): the irons an iron axis counts, plus one per other part an axis names, so 드라이버
  로프트 + 드라이버 강도 + 아이언 (8개) = 9.
- specs_contradict (check_specs needs the title): 총클럽개수 N while 아이언개수 or 아이언 구성 gives N irons or more on a set with
  other clubs. If the title states another total (12pc), the total row is dropped. If the title's total equals N, the
  iron rows are dropped. With no total in the title, the iron rows are dropped only when 풀세트구성 or the option axes
  count N clubs and the title does not back the irons ("8i").
- specs_stated_by_variants now says "each variant states its own value (10.5도, 9도)" and lists the values found.
- specs_loft_near_miss: a sold driver loft half a degree from the row's (row 9.5도, values 9도). The row is kept as
  written, noted for a check by hand.
- specs_lists_unsold: a 드라이버 로프트각 row listing several lofts on a product of one variant. The row is kept and noted.
- Title check: an option value of two words or more that the title writes whole names that value, ignoring spacing,
  brackets and case ("NS PRO950GH NEO R" = "NS PRO950GH NEO(R)"). A value starting with a club number must follow its
  axis' part word ("우드3번55S", not the "3번65S" after 유틸). A value followed by "/" is a list of choices. Word hits
  inside such a value with no word between them become one span.
description_clean also drops: the lead line of a cross-sell pair. When a cross_sell sentence starting with 해당 / 이 / 그
/ 위 + 상품 / 제품 / 모델 follows, in the same block, a sentence about another colour or model (컬러 / 색상 / 다른 / 기존 / 신형 / 구형 /
이전 ... 은/는), both go as cross_sell. The seller's genuine-goods pitch is store_claim: 정품만 판매/취급, 유통 경로, 정품 여부, OEM 표기.
A lone section label line '제품상세 / 상품상세 / 상세정보 / 상세설명 (/ 이미지 / 페이지)' is label. Images: 1x1 tracking pixels (SmartEditor
originalWidth 1 and originalHeight 1) are pixel, and dispatch / holiday banners by file name (오늘출발, 당일발송/출고/출발/배송, 추석,
설날, 명절, 한가위, chuseok, seollal) are boilerplate_name. Sentence joins now continue after -거나, 경우, an adnominal + 지 (인지 /
한지 / 는지 / 은지 / 던지), and 본래.
**Run level (run_transform.py -> shared_images.py)**: after every product is prepared, one step looks across the run's
products. It catches store-wide description banners whose numeric or hashed file names no name rule can catch (seen
2026-11-07, 100568453: 30434463209514390_345786175.jpg opens and 60948062508870618_280838627.jpg +
22313003105171778_1094441035.jpg close 17 of its 18 listings). An image is a store banner when it is in at least 3
listing groups of the same store (source.channel_no) and in at least half of them. Listings that share more than half
of the smaller description's images are one set listed again and form one group. It must also open or close the
product's description. It moves to description_dropped (rule shared_store_image), and the product gets the note
description_shared_images ("dropped: <name> (n of m listing groups); kept in the middle: ..."). A shared image among
the product's own photos stays, and the note names it. A store with fewer than 3 groups is untouched. "The same image"
is the link without its query. A distinctive file name (12+ characters, 8+ digits) also merges re-uploads of one file,
since the seller uploads a banner again for each batch of listings. Generic names (image.png, 1.jpg, 상세.jpg) count per
link. The report says how many were dropped. The step is pure: same products in, same bytes out.
- **Run 40b (2026-11-07)**: past the cap, rows that cover the most pairs of option values first, the rest shared over
  the first axis; few_pieces from "(3종)" / "(2종)" / "하프세트(5P)" too, the title's count winning over a wrong
  총클럽개수 row, never on "10+1pcs" or when a variant is a full set; 원산지 brackets naming 2+ countries kept; a SIMPLE
  option of one value becomes a fact (several: note `simple_options_left_out`); an axis named 색상 whose values are
  not colours is a placeholder name; add-on codes ("[G192]01_") left out; "택1" numbering left out. Seller data
  patterns behind these rules: [SELLER_DATA.md](SELLER_DATA.md).
- **Text fields** -> `personalization` (label without ★ and "(필수)": `required` says it); **add-ons**: free ones
  on sale and in stock: free ones, paid ones too with the category's `paid_addons` (`price_krw`, `price_usd`);
  a group named (필수) / (필수선택) is `required`. Why per category: a set's photos often show the extras (bag,
  covers, utility clubs); sold without them, a buyer takes them as part of the set (owner 2026-11-06).
- **Reviews**: the selected reviews (video posters already photos), rating and count from Naver's summary.
- **Held**: `collect_incomplete`, `price_unknown`, `no_variants`,
  `options_unaligned` (rows that do not fit the groups), `specs_folded` (the 상품정보 list stayed folded), `axes_over_3`,
  `no_images`, `images_over_50`.
- **A brand for every product** (the owner, 2026-11-08: the Shopify vendor is never empty; no brand, at least the
  manufacturer). A seller who links no Naver brand leaves no 브랜드 row and no brandName, and Naver then knows none
  anywhere (6 of 143 sets: not in the product answer, the page's answer, the search cards, the notice, the page's
  ld+json). `brand_source` says where it came from: the row / brandName; else the manufacturer
  (`manufacturer:<source>`, never Naver's M0000000); else, run-level (`brand_fallback.py`), a brand the shop's other
  products state found in the title (`title`: 4 of the 6; the first one of a combination set), the importer in
  원산지's brackets (`origin`), the shop's brand most read in the images (`images_text`), a Latin brand phrase the
  images repeat 5+ times (`images_text_latin`: BEN SAYERS on 13425122164), or 노브랜드 (`none`: 13464713764, an
  unbranded putter). These add the note `brand_fallback` (source, other candidates). No brand list is kept by hand.

**Per-shop rules** (`transform_shops.py`, data): SKU prefix, KRW per USD, variant cap, and per Naver leaf category
`paid_variants` / `paid_addons` / `description_images`, off by default, all on for fairwardgolf 50002788 and
50002787 (junior clubs, 2026-11-11; no parts profile: the core reading only). The shop's
sections are not decided here (Placement). A shop or a category without rules: `ShopRulesMissing`, the
run stops and asks the operator.

Not here (later stages): the shop's sections, tags and product type (Placement, `placement.py`), English (titles,
options, specs, reviews), vendor spelling (every product: the same brand
is written 캘러웨이 / 캘러웨이골프, PGM / 피지엠, 젝시오 / XXIO; a `brand_fallback` can be checked against its other
candidates), handle, alt texts, the seller's description prose (images only on the sets checked), publication.

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

Cost (medians): a product 58-73 s to collect (the page read 48-50 s, details 4-7 s, reviews 0.4 s, gallery 1-3 s,
review photos 4.5-11 s); a `/products/page` read 48 s (38-194); a batch of 5 with its pages ~10-12 min; 40 products
~64 min; keep + transform ~0.2 s. Reading the page by the product's name first (not the listing's query) took the
page read from 74 s to 48 s and 40 products from 61 to 45 min.

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

Small, runnable scripts, one topic each, in the order to read them. Start `server/run.py` first; examples 7-10 and 99
also
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
`product_specs(product, query)`, `reviews(product, sort, max_page, media)` (pages), `selected_reviews(product,
count)`, `store_details(store)`, `store_products(store, list, period)`,
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
.venv/bin/pip install -r scripts/requirements.txt    # requests, Pillow
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

## Publication (`publish.py`, MVP, the owner 2026-11-08)

```sh
.venv/bin/python scripts/publish.py fairwardgolf [--only <key>] [--force] [--dry-run] [--shops-root DIR]
```

A product goes to the store when it is `ready` (transform), `translated` and `placed`; a job made with
`job.py new --publish` does it for each product right after translation (placement of the whole shop, offline,
then this one product; with `--describe` its description is written in between, see the next section). Per product: the reviews' photos and avatars to Shopify Files (the files app, once per
file, named by its hash, `publish/files.jsonl`), the review rows as a JSON feed file there, the gallery photos as
staged uploads attached in `productSet` (create, or update the product with its source key), ACTIVE, published
to every sales channel of the store (the owner, 2026-11-09); one line in `shops/<shop>/publish/published.jsonl` (product id, handle,
photos by hash, admin link, `pricing`: the rule's version, `prices_usd`: the lowest and the highest variant price; rows
from before 2026-11-11 have neither). Unchanged inputs: skipped; on an update photos already there are kept by hash, and a
managed metafield the product no longer has is deleted (`shopify_payload.MANAGED`; productSet never removes one).
`--dry-run` writes the payload to `publish/payloads/` and sends nothing. `shopify_payload.VERSION` is in the
digest: a change of what the builder makes sends every product again. So is the shop's price rule
(`shop_pricing.Policy.describe()`: every number and the tariff's version): a new rule or tariff sends every
product again too, so `reprice.py` shows the change first (see The price).

The owner's rules (`shopify_payload.py`):
- **Title, vendor**: the translation's (the title prompt makes the store name: brand first, no shop, distributor or
  after-sales words, no loft / flex / shaft codes, no club list, no usage or gift words). The vendor loses a
  maker's company form and a second brand ("Prokenex / SJG Co., Ltd." -> "Prokenex", "Mizuno, Hillcreek" ->
  "Mizuno") and takes the brand dictionary's spelling, compared without case (the owner, 2026-11-09: PING stays
  PING, Yonex stays Yonex, whatever the case it came in; the dictionary keeps one spelling per brand), else the
  shop's (not the capitals one when the shop has both; a run remembers each new vendor for its next products); the
  title spells the brand as the vendor; a title without its brand gets it in front (not the tenant's name). Handle from the title (ASCII, the brand in front; a taken handle
  gets `-2`, `-3`; an update keeps the shop's handle, `--rehandle` sets the new one with a redirect).
- **Price**: per variant from `shop_pricing.Policy.quote` (see The price, below). In a shop with the delivery
  rule (fairwardgolf, the owner 2026-11-11) the price holds the purchase, the duty, the delivery and the margin,
  and Shopify's cost per item is the purchase with ShopNShip's commission (the duty is not in it); elsewhere cost = price =
  the Naver KRW at 1 000 KRW = 1 USD rounded UP to a whole dollar. A variant that cannot be priced (no box, a box
  over the tariff's 50 kg) holds the product (`PayloadError`). No compare-at price. Add-ons: the KRW at the same
  rate only, no delivery, duty or margin.
- **Buyable**: every variant is untracked and sold without limit (CONTINUE), one sold out on Naver too (the owner,
  2026-11-09: buying opens on the site later); the variant's `fairwardgolf.source.available` keeps Naver's state.
  Weight: the package's central weight in grams.
- **"1+1" options**: an option with the same English name and values as an earlier one, which no price depends on,
  is dropped (one variant per choice of the others, the one whose repeat equals the option); a repeat that changes
  the price stays an option of its own ("Flex", "Flex 2").
- **Options**: the translation's, without a leading "Select" and with " / " made "/" (Shopify refuses it in a name),
  values without a seller's numbering ("01.", "SPEC"); two values with one English get "(2)". A product with one
  variant is named by the seller's one remaining choice (a constant option axis the transform keeps as a fact:
  "Set: 12 Pcs + Caddie Bag"), else `Option: Standard` (`FALLBACK_OPTION`); a gift line is not a choice.
- **Title clean-up** (`clean_title`): "(Parallel Import)", a word written twice in a row, a model code written
  twice. SEO title = the title (the site's page `<title>`), cut at a whole word within 70 characters.
- **Title length** (`fit_title`): at most 150 characters, Google Merchant Center's limit for `title` (a longer one
  is an item issue there; Shopify itself takes 255). The translation already asks the model again for a title over
  100 (TRANSLATION.md); this is the last guard, with the brand put in front counted: the facts after a comma go
  first, from the end, when that keeps 60% of the limit, else whole words from the end; nothing is left dangling (a
  joining word, a comma, a count without its unit: "Set 13" of "13 Pieces", an open bracket), and a brand that
  stood only in the part cut off goes in front. Google truncates a longer title itself and warns ("Text too
  long"); it shows about the first 70 characters, which is why the title's order is brand, model, who, what.
- **Add-ons**: gift words out of the English labels ("Free", "Gift", "Default Selection"); a required free group
  of a one-variant product goes to `custom.required_selections` (product-required-selections/v1, the site's field
  for a choice the buyer must make; "do not add" is no value there). A required choice of a product with several
  variants stays in `custom.optional_addons`: the site's contract allows `required_selections` on one-variant
  products only, so showing it as required is the site's change (the owner, 2026-11-09).
- **Reviews**: a review the cleaning cut mid-sentence and the English ends on "and" is closed ("Lightweight.").
  Text-field labels take one wording ("(e.g., John Doe)").
- **Reviews**: a sentence of the English about the price or the value, or naming another platform or a buying
  agent, goes (`review_clean.cut_english`, the owner 2026-11-09); a review with no text left and no photo is not a
  row (its score is in the rating); one with photos only gets a short neutral line (`PHOTO_ONLY_TEXTS`, picked by
  the review's id); a row Naver gave without an id, score or date is left out (one bad row empties the site's
  whole feed).
- **Photos**: alt "<brand> <title> - photo N" (the brand once when the title starts with it). A product with fewer
  than 2 photos of its own gets buyers' photos after them, 5 photos in all at most (the owner 2026-11-09, a fuller
  gallery for Google Merchant; never from the description images). `review_rank` orders the reviews rated 4-5:
  the review's usefulness (`text_quality`, Naver's "helpful" votes `likes`, a full text over a short one), several
  photos first (the owner), lower for a review that told of the purchase (seller, packing, shipping: its photo is
  often the box); a review with one photo and no product words, or about the purchase only, is passed over.
  `review_gallery` takes one photo per review a round (the review's first photo the gallery may show), two rounds;
  never a photo shown already (same hash), one under 400 px, a strip (over 2.2:1) or one mostly grass-green (over
  15%: a course, a range, a screen-golf room). Measured on the pilot (judging agents on 80 picks): the text tells
  little of what a photo shows, so `publish/gallery_skip.txt` (sha256 per line, "# why") strikes out a photo a
  person saw was wrong (boxes, a shop, people); a photo check by a vision model was offered and declined (the owner,
  2026-11-09).
- **Not sent**: descriptionHtml for a product without a description (`describe.py`, see its section), HS /
  origin codes, Naver's delivery data as such (the seller's fee in Korea and the box are inside the price; the
  box's fields are in `fairwardgolf.package`), facts, gender (placement uses it for the sections), compare-at.

Metafields. Storefront (`custom.*`, the site reads them, the harvester's formats kept): `review` (rating),
`rating_count`, `reviews_seo` (up to 20 rows: id, customer {name, avatarUrl}, rating, title "", description,
images, verified false, source, createdAt), `reviews_feed_url` (the JSON feed, every row, `date` instead of
`createdAt`), `personalization_fields` (product-personalization/v1; a field without an English label is left out,
`maxLength` only when the seller set one), `optional_addons` (product-optional-addons/v1: complimentary choices
only, `{key, label, priceKrw: 0}` and nothing more). The site reads these through strict schemas (naver-harvester
`store-scripts/shared/src/product-*.ts`, `shared/product-configuration/limits.ts`, `shared/reviews/`): an extra key
or a paid choice hides the whole block (seen on the site 2026-11-08). Ours (`fairwardgolf.*`, not on the storefront, one JSON per
concern with a `schemaVersion`; a new value is a new field there, a new concern a new key):

| Owner | Key | What |
|---|---|---|
| product | `source_offer_id` | The source key (the shop check and the update find the product by it) |
| product | `source_url` | The Naver page, without its query |
| product | `source` (json) | platform, key, url, channel / product / category ids, run, Korean title and brand, `priceKrw`, `originalPriceKrw` |
| product | `pricing` (json) | How the prices were made. A shop without the rule: `fairwardgolf-pricing/1`, version `krw-cost/1`, `krwPerUsd`, rounding, margin null. With it: `fairwardgolf-pricing/2`, version `landed/2` and every number of the rule (`krwPerUsd`, `serviceUsd`, `dutyRate`, `koreaPaid`, `coefficients`, `margin` (`fixedUsd`, `rate`, `minUsd`), `paymentRate`, rounding), the tariff (`id`, `checkedAt`, `version`, `sha256`), the dates of the owner's decisions (`decided`) |
| product | `addons` (json) | Every add-on, paid ones too: group (`required`), choices with `priceKrw`, `costUsd`, `priceUsd` (the rate only: no delivery, duty or margin), `free`; ready for the day the site sells paid add-ons |
| variant | `source` (json) | Naver variant id, source id, Korean options, `priceKrw`, `costUsd` (Shopify's cost per item: with the rule the purchase + commission, no duty), `priceUsd`, `available` |
| variant | `price` (json) | With the rule only: `fairwardgolf-variant-price/1`, how the price was made: `naverKrw`, `koreaDeliveryKrw` and `koreaFeeType`, `purchaseUsd`, `serviceUsd`, `dutyRate` / `dutyUsd`, `costUsd`, `box` (cm, gross, billable, step kg), `rule`, `krwPerUsd`, `level`, `coefficient`, `tariff` (id, checkedAt, version, sha256), `gridUsd`, `insideUsd`, `deliveryUsd`, `fees` (id, usd, because), `feeUsd`, `baseUsd`, `marginUsd`, `keepUsd`, `paymentRate`, `neededUsd`, `priceUsd`, `paymentUsd`, `surplusUsd` |
| variant | `package` (json) | The five shipping fields as the transform made them (value range, `confidence`, source, reliability) |

The harvester's other keys (`custom.measurements`, `*_confidence_level`, `fairwardgolf.source_variants`,
`source_pricing`, `catalog_*`, `enrichment_state` ...) are not written; their definitions stay for its 60 products.

Access: `ProductsAdmin` (PRODUCTS_API_*, write_products) and `FilesAdmin` (ADMIN_API_*, write_files), both keys in
the store's credentials file, tokens minted per run as in the shop check. `ShopCatalog` stays read-only.

Uploads in batches (2026-11-09): a product's new review photos and avatars, and its new gallery photos, go at once:
names searched 10 a query, one `stagedUploadsCreate` and one `fileCreate` per 50 files, the files sent to the
staging bucket 6 at a time (each retried on 429 / 5xx), one `nodes()` poll for the whole batch. The GraphQL calls
stay one at a time: Shopify limits by query cost per app and store (this store: a 2 000-point bucket, 100 points a
second back; a search of 10 names costs ~5, a mutation ~10), and a THROTTLED answer, a 429 or a 5xx waits what
Shopify says and repeats (`shopify_catalog._send`). Measured live: 30 photos in 8.3 s (0.28 s a file, 7 GraphQL
calls) against 4.0 s a file one by one (5 calls a file).

## The price: delivery, duty and margin inside it (`shop_pricing.py`, the owner 2026-11-11)

A shop whose buyers pay no delivery carries everything in the variant's price: today fairwardgolf
(`shop_pricing.POLICIES`). A shop not there keeps `krw-cost/1`: cost = price = the Naver KRW at 1 000 KRW = 1 USD,
up to a whole dollar. The rule is `landed/2` (`shop_pricing.VERSION_DELIVERED`, raised on a change of its
arithmetic). Per variant, `Policy.quote(variant, product)` gives the cost per item, the price and the breakdown, in
USD:

```
purchase  = (the variant's Naver price + the seller's delivery in Korea) / 1000, up to a whole dollar
            the delivery in Korea: the listing's base fee when its fee type is PAID or UNIT_QUANTITY_PAID, else 0
cost      = purchase + 3 (ShopNShip's commission)            -> Shopify's cost per item
duty      = 12.5 % of the purchase, up to a cent             US import duty, always prepaid (PDD): in the price,
                                                             not in the cost per item
grid      = the tariff's price for the variant's box         (delivery_tariff.py, see The tariff)
inside    = 32.36 when the box is billed over 25 kg (the tariff holds the dimension fee there), else 0
level     = the lowest confidence of the box's three sides   (the package fields, 5 ... 1)
delivery  = (grid - inside) x coefficient(level) + inside
fee       = FedEx's dimension fee, KRW 35,600 = 35.60, when the box crosses its lines and inside is 0
base      = cost + duty + delivery + fee
margin    = 25 + 11 % of the base, never under 30
keep      = base + margin                                    what stays with the shop
price     = the first pretty number not under keep / 0.97: ending in 9 under 1000, in 99 from 1000
surplus   = price - 3 % of it - keep                         a reserve, kept by the shop
```

The box is the variant's `package` fields (sides in mm, the packed weight in g): a category default's central
value, else the larger end of a range. The duty (the owner, 2026-11-11): every parcel leaves Korea through
ShopNShip with the duty prepaid, 12.5 % of the purchase whatever the country of manufacture; it goes into the base
the price is made from, as a line of its own, and never into Shopify's cost per item (the owner, 2026-11-11: it is
not a purchase price). Shopify's cost per item is the purchase and the commission: its profit report (price - cost)
is therefore not the margin, it holds the duty, the delivery, the fee, the payment share and the surplus too.

The margin (the owner, 2026-11-11): 25 USD for each order plus 11 % of the base, and never under 30. The fixed part
pays the work an order takes whatever it costs; the share grows with every dollar, as the risks do (a dearer set
loses more on a refund, the payment share included). It is 36 at a base of 100, 80 at 500, 135 at 1 000, 190 at
1 500, 355 at 3 000, 575 at 5 000 (36 % to 11.5 % of the base). The owner's first table (points 100 -> 30 ...
1 500 -> 200, joined by lines, 13.3 % over 1 500: `landed/1`) gave 10 % at 800-1 000 and a fifth of each dollar
between 1 000 and 1 500; it was replaced the same day.

The
delivery in Korea: a fee type other than PAID and UNIT_QUANTITY_PAID is free (CONDITIONAL_FREE too; the owner,
2026-11-11). A variant without a box, or with a box over the tariff's last step, has no price
(`PriceError`): the product is held, nothing is sent.

Examples (2026-11-11, tariff version 1; USD):

| Product | Level | Box cm, billable kg | Purchase | Cost | Duty | Grid | Delivery | Fee | Base | Margin | Price | Surplus |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| the seller's box, Korea fee 99 000 KRW (5818229550) | 5 | 121 x 20 x 16, 10.80 | 898 | 901.00 | 112.25 | 183.30 | 183.30 | 0 | 1196.55 | 156.62 | 1399 | 3.86 |
| a set without a bag (13498941795) | 2 | 120.5 x 20 x 16, 7.71 | 689 | 692.00 | 86.13 | 136.12 | 190.57 | 0 | 968.70 | 131.56 | 1199 | 62.77 |
| a set without a bag (12434254421) | 2 | 124 x 20 x 16, 7.94 | 2900 | 2903.00 | 362.50 | 136.12 | 190.57 | 35.60 | 3491.67 | 409.08 | 4099 | 75.28 |
| a set with a bag (13513786835) | 2 | 120.5 x 40 x 32, 30.85 | 899 | 902.00 | 112.38 | 523.48 | 719.93 | inside | 1734.31 | 215.77 | 2099 | 85.95 |
| the bag unknown (9868413561) | 1 | 123 x 28 x 23, 15.84 | 360 | 363.00 | 45.00 | 232.01 | 580.03 | 35.60 | 1023.63 | 137.60 | 1199 | 1.80 |

On the 120 products of the store (2026-11-11): levels 5 / 4 / 2 / 1 on 2 / 1 / 97 / 20 products (none at level 3),
every product priced; with the 5 of the pilot, 939 to 5 099 USD.

**The coefficients** (the owner, 2026-11-11: one a level, on the grid's price; the fee is not multiplied):

| Level | Coefficient | The box | What it covers (golf sets, 50002788) |
|---:|---:|---|---|
| 5 | 1.00 | stated by the seller | the tariff as it is |
| 4 | 1.10 | the seller's, a weaker reading (an image) | a box 1.5 cm wider and higher with a bag, 0.5 cm without |
| 3 | 1.20 | composed from the seller's own figures | 3.5 cm with a bag, 1.5 cm without |
| 2 | 1.40 | composed with the operator's baselines | 7 cm with a bag; 3.5 cm without, or up to 11.5 kg |
| 1 | 2.50 | the category's flat default | whether the set has a bag is unknown |

Level 1 is 2.50 so the margin stays whole when the set does have a bag: the category's average box (about 124 x 28
x 23 cm) is 232-259 USD by the grid, a set with a bag 523-546, and under 2.33 the difference would come out of the
margin; without a bag the price carries 444-511 USD the delivery does not need, kept for the risks. 2.50 was derived
for 50002788: a new category in the shop needs its own check of level 1 (the coefficients are one table per shop,
`shop_pricing.FAIRWARDGOLF`). 50002787 junior clubs (the owner, 2026-11-11) keeps them as they are, to be measured
on its first shipments like the sets. All five are starting estimates: no set had shipped yet. After the first 10-20 sets
shipped, compare each invoice with the variant's `fairwardgolf.price` (the box FedEx measured, the billable kg,
every fee line) and replace them with measured ones; check the first invoice of a set without a bag for FedEx's
18 kg minimum (the switch below). Where they come from: 1-6 cm more on the two short sides raises the grid's price
by up to x1.12-1.60 without a bag and x1.06-1.34 with one; the one real check, the Callaway Edge box the seller
states (121 x 20 x 16 cm, 10.8 kg, 183.30 USD), is passed by 1.40 with a step to spare (1.35 by 0.46 USD).

**The fee, once per box.** FedEx's Additional Handling Surcharge - Dimension (its 2026 rates for Korea; the owner,
2026-11-10): KRW 35,600 on a box whose longest side is over 121 cm, or the second over 76 cm, or length + girth
over 266 cm, or the volume over 169,901 cm3 (strict lines: 121 cm pays nothing), at 1 000 KRW = 1 USD. FedEx bills
it once per box. The partner's table already holds it over 25 kg of billable weight: every step from 26 kg is 32.36
USD over the per-kilogram line (25 -> 26 kg: +48.77 against +16.41 a kilogram; the same for Japan, the UK, Germany
and Canada), KRW 35,600 at the partner's 1 100. So a box billed over 25 kg (every set with a bag) does not pay it
again, and the part inside is not multiplied by the coefficient (the owner, 2026-11-11). The tariff names it
`included_surcharge`. Sources: https://www.fedex.com/content/dam/fedex/international/rates/fedex-rates-sur-en-kr-2026.pdf
and https://www.fedex.com/en-kr/shipping/surcharges/other-surcharges.html (fedex.com refuses plain HTTP requests:
open them in a browser). Read there too (2026-11-11): FedEx measures the box itself and may bill afterwards; an
outside that is not a cardboard box (a bag case, handles, straps) pays the same KRW 35,600 at any length, so the
price assumes cardboard; only the largest handling fee is billed per box; the amount is before tax and before any
contract discount; the Oversize charge (KRW 86,000: over 243 cm, length + girth over 330 cm, or 283,168 cm3) is
not reached by a set.

**Not counted, on purpose** (the owner, 2026-11-11):
- fuel and insurance: inside ShopNShip's tariff;
- FedEx's 18 kg minimum billable weight for a box that pays the dimension fee: not seen on real invoices of long
  boxes. The switch is the fee's `min_billable_kg` in `delivery_tariffs.json`: null is off, 18 bills such a box at
  18 kg at least (a new tariff version). A set without a bag would cost 133-139 USD more to ship: switch it on
  when an invoice shows it;
- FedEx's demand surcharges, the residential and inbound fees, remote areas (the tariff's `not_included`);
- the fuel percent FedEx puts on the dimension fee (52.25 % in the week of 2026-11-09: KRW 35,600 would be about
  54,200);
- the market rate: 1 000 KRW = 1 USD is the owner's constant (the market was about 1 335 on 2026-11-10: the
  constant hides a reserve larger than the whole margin on the catalogue, uneven, 4-18 % of a price, and zero if
  the won reaches 1 000);
- the 10 % Korean VAT inside Naver's price (no export refund counted) and the seller's extra fee for Jeju and the
  islands (ShopNShip's warehouse is on the mainland);
- the duty by country: every parcel pays it since the US de minimis ended (2025-08-29), and the owner's flat 12.5 %
  of the purchase is used instead of the per-country rates a search found (about 24 % for China);
- US sales tax: the variants are sent not taxable; a sales-tax duty would come out of the price;
- a change of Naver's price: the price is taken as Naver shows it, the discount included; a sync is a later stage;
- a dearer payment: 3 % is the payment system's average share, the rest is paid from the margin.

**Accepted as they are** (the owner, 2026-11-11, after a review of the rule on the 120 products):
- Level 1 sits between the two outcomes: 400-600 USD over the same set without a bag at level 2, up to 200 under
  one with a bag. An operator's answer about the bag moves the price either way.
- The coefficient's reserve is part of the base, so it earns margin and the 3 % too.
- The seam at 1000: no price between 999 and 1099; a keep just over the line takes the next hundred.
- The surplus is a reserve only on average: 0.59 to 96.70 USD a product, under 10 on 15 of the 125.
- Prices well above US retail for sets of US brands, and the bag's box adds 500-700 USD: the source is Korea's
  market, with delivery and the shop's margin.
- A bag sold as a paid add-on would ride in a box priced without it (390-400 USD of delivery not in the price):
  paid add-ons stay off for this rule (the site sells free choices only) until a box is priced per add-on. A paid
  variant is priced by its own box; on the 120 products each listing has one price (7583123963's variants have two
  gross weights in the same step).
- Prices move when a product is sent again: each send prices it anew (a new collection, a better box, a new
  tariff or rule version); level 1 to level 2 without a bag is 400-600 USD less.
- The "1+1" listing 5684497984 (two sets, two boxes) is priced as one box; three level-2 sets whose "no bag" is
  read from an image only (5479607864, 13753313321, 13741767690) lose money if they do have one.

### The tariff (`delivery_tariff.py`, `delivery_tariffs.json`)

The partner's prices are data: `delivery_tariffs.json`, one tariff per partner, carrier, service and route,
approved by the owner and traced to a dated capture of the partner's calculator; no amount is made up or
extrapolated in code. Which shops carry delivery in the price is `shop_pricing.POLICIES` (a `Delivered` rule names
its tariff); the file's `shops` map is the calculator's lookup and must agree with it (a test): today
`fairwardgolf` -> `shopnship-fedex-ip-kr-us` (ShopNShip, FedEx International Priority, Korea -> US, captured
2026-11-11, file version 1). A box's price, checked against the captures:

1. volumetric weight = L x W x H / 5000 (cm; the sides as they are, a fraction of a centimetre kept);
2. billable weight = the larger of the gross and the volumetric weight, rounded to hundredths (half up);
3. the price is the row of the first step not under it: 0.5 kg steps to 20.5 kg, whole kilograms from 21 to 50 kg,
   71 steps (0.5 kg 42.49 USD, 8 kg 136.12, 16 kg 232.01, 16.5 kg 258.78, 31 kg 523.48, 50 kg 809.67);
4. over 50 kg the calculator gives no FedEx price: the answer is `needs_quote`, and the variant has no price.

```python
from delivery_tariff import Box, load, box_cost
tariff = load().for_shop("fairwardgolf")          # None: no tariff named for this shop
box_cost(tariff, Box(124, 20, 16, 6), krw_per_usd=1000)
# base_usd "136.12", surcharges [fedex_ahs_dimension "35.60"], included None, total_usd "171.72"
```

Where the table comes from: ShopNShip's public calculator (https://shopnship.co.kr/en/help/shipping_calculator.php;
no login, cookie or key; one line of five USD prices: DHL / FedEx / EMS / EMS Premium / ShopNShip Standard).
`shopnship_rates.py capture` asks the grid one box at a time with a pause, keeps each request with its raw answer,
and stops after three rows in a row without an answer. Two captures on 2026-11-11 (178 and 198 requests, no
error, every repeat equal); the second, `fixtures/shopnship/shopnship-us-20261111T072303Z.json`, is the tariff's
`source`. Its steps to 20 kg equal the owner's table on all 40; the steps from 20.5 to 50 kg are captured too and used
instead of a fresh quote. `shopnship_explore.py` then asked 427 more boxes in two rounds
(length 50-400 cm, the second side, girth and volume around the fee's lines, the order of the sides, weights across
the steps in small increments, flat, thin and tiny boxes, number formats, pounds and inches, other countries):
every answer the model can predict was equal to it (367 of 367; one weight written with 17 digits, which the
server reads as a binary number, left out). What they showed: the calculator knows only the
billable weight (no dimension fee up to 25 kg, and no size limit: a 400 x 10 x 10 cm box gets a price FedEx would
refuse); over 25 kg every step holds the fee; one box over 23 kg costs more than two of the same total (32 kg
539.89 USD, 16 + 16 kg 464.02). All the answers are of one hour of one day: whether the prices move with the day is
not known. On the page itself, for a check by hand: a blank or zero side prices by the gross weight only, and a
comma cuts the weight ("9,5" is 9 kg); use the `quote` command, which sends neither. ShopNShip Standard
("5-15 business days, duties included") priced the two set boxes at 159.57 and 635.98 USD and nothing over 30 kg.

The review is by hand (the owner, 2026-11-11), with versions and the captures kept to compare. Capture and compare
at least when FedEx publishes its 2027 rates for Korea (the fee's amount and lines are of the 2026 document), a week
after a capture (FedEx's fuel moves on Mondays: does the grid?), and after an invoice that differs; a grid 6 %
dearer moves 41 of the 125 prices, 40 by 100 USD.

```sh
.venv/bin/python scripts/shopnship_rates.py quote 124 20 16 6                      # one box: every carrier
.venv/bin/python scripts/shopnship_rates.py capture --out scripts/output/shopnship  # the grid, about 5 min
.venv/bin/python scripts/shopnship_rates.py compare scripts/output/shopnship/shopnship-us-<time>.json
                                                    # against the recorded table: the differences, exit 1 if any
```

Adopting a capture that differs: copy it to `scripts/fixtures/shopnship/` (the earlier captures stay: they are the
backups a later capture is compared with); in `delivery_tariffs.json` put its `table`, `source` and `checked_at`,
raise `version` and add a `history` line (version, date, tariff, source, what changed); fix the expected prices in
`test_delivery_tariff.py` (they are written out on purpose) and rewrite the pricing fixtures with `UPDATE_GOLDEN=1`
after reading the diff; the owner approves. Every price records its tariff: `tariff` {id, checkedAt, version, sha256} in
the variant's `fairwardgolf.price` and in the product's `pricing`; the sha256 is the tariff row's fingerprint, so
any edit (a step, a fee, the 18 kg switch) moves it even without a new version, and with it the publish digest:
after a change, run `reprice.py` (dry) and ask the owner before anything is sent. A new tariff id also changes
`shop_pricing.FAIRWARDGOLF.tariff`.

### In the flow, and products already in the store (`reprice.py`)

New products: `job.py new ... --publish [--describe]` prices each product in its payload. The done line shows the
price (`published <handle> $1099 <admin link>`, `$<min>-<max>` when the variants differ); the job's `published`
event and the ledger row keep `prices_usd` [min, max], the row also `pricing` (the rule's version). A product that
cannot be priced is not sent: `publish held: variant <sku>: <why>` in a job, `held` with the reason in `publish.py`.

Products already in the store (published before the rule, or before a new rule or tariff version):

```sh
.venv/bin/python scripts/reprice.py fairwardgolf [--only KEY] [--apply] [--shops-root DIR]   # --only: repeat for several
```

A dry run by default, nothing sent: one line per product published and still ready (key, handle, the levels and
coefficients, the old prices min-max, the new min-max, the change), then a summary; the old prices are the ledger's
`prices_usd`, else what the plain rule (krw-cost/1) gives from the prepared record, marked "plain rule"; a
published product no longer ready is named on stderr; the same table goes to
`<shops_root>/<shop>/publish/reprice-<UTC time>.tsv`. A product that cannot be priced is shown held and the run
goes on. `--apply` sends the products that are not held through `publish.publish_one` (a product whose digest did
not change is skipped). The rule "ask the owner before touching published products" (JOB_AGENT.md, Never) holds:
`--apply` runs on the owner's word, after the table was read. Done for the 120 products published before the rule
on 2026-11-11 under `landed/1` (120 sent, the 5 of the pilot unchanged; the store then held the rule's price and
cost on all 1 127 variants). The same day the rule became `landed/2` (the margin 25 + 11 %, the duty out of the cost
per item), and on the owner's word all 125 products were sent again: 33 prices changed (329 475 -> 326 915 USD for
the lowest prices), every cost per item lost the duty; the store then held `landed/2` on all 1 127 variants, 939 to
5 099 USD.

**Open, not decided by the owner** (2026-11-11):
- The 17 sellers who bring the set into Korea from abroad (transform note `overseas_shipping`): for 10 of them
  Korean duty and VAT (about 19 %, not checked) are not in Naver's price, and the rule does not add them.
- Returns and refused parcels: who pays the way back of a 1.2 m box (about the outbound price), what happens to a
  set the Naver seller will not take back; the payment share is not refunded. No reserve in the price.
- Naver's price at order time: 66 of the 125 sell at a discount; if every discount ended, 32 orders would lose
  money. Check the price before the payment is captured? How often to re-read published prices?
- Boxes at the fee's 121 cm line: 22 of the 120 computed boxes are 120.5-121.0 cm (5 mm decides) and carry no
  fee; FedEx remeasures. Add the fee to every set, or pack sets without a bag at 121 cm or less?
- Does a set with a bag travel as one box or two (two boxes cost less, the rule prices one)?
- Buyers outside the US: the price carries the US tariff; other destinations were not discussed.
- The level taken from the box's three sides only (not the weights): the agent's choice, not confirmed.
- Cost per item without the delivery: the plan's choice, not confirmed (without the duty: the owner, 2026-11-11).

## The product's description (`describe.py`, the owner 2026-11-10)

```sh
.venv/bin/python scripts/describe.py fairwardgolf [--only <key>] [--limit N] [--offline] [--packet]
.venv/bin/python scripts/job.py new ... --publish --describe      # each product described right before it is sent
```

A minimalist English description in HTML for Shopify's own body (`descriptionHtml`; no metafield, no SEO
description). One model request and one answer per product, through translate.py's client (the same key, models
and fallback order) at this stage's own effort: `high` with thinking on (`DESCRIBE_EFFORT` in .env changes it);
no fix rounds. Why not the translation's `low` without thinking: checked 2026-11-10 on 35 descriptions against
their sources, 15 had a wrong club list or count, a fact of one choice told of all, or a lost "no bag" sentence;
the answer needs the sources compared and the clubs added up ("Which model" below). The script works before and after the request:

- **Before** (`packet`): what is sold goes first (the facts and the options of the variants we publish, the free
  required choices), then the English the shop already shows (title, brand, spec rows, option values: the
  description names the product as its title does), then the seller's typed text and the OCR blocks of the
  description images in Korean, and, in a section of their own, the tables read from those images (digits are
  lost in them, so a figure only a table gives is not stated; but the seller lists the set's clubs there, and the
  Naver spec rows are often wrong about them; one or two rows of mostly Korean words are text in columns, e.g.
  "여성 | 카본10pcs | 클럽만"). Left out:, a block headed by an offer of a paid extra or a gift (a line naming an extra
  inside another block stays with its label: the label is what tells the model to leave the item out), an image of
  buyers' reviews (masked ids), every line on the country of manufacture. A gift among the facts or the free
  choices is listed under "Gifts of the seller: never mention", not as what is sold. Notes the transform already made about the listing (other
  configurations sold, paid extras, gifts, several products in one description) are passed as one line each.
- **Origin** (the owner: keep the country): decided by the script, not the model. The 원산지 row and every
  "제조국 / made in" line of the texts name one country: `Origin: made in <country>`. They disagree or hedge
  ("may differ", "not Japan", "and others"), or the row names a country the table does not know: `Origin: do not
  state`, the reason in the report. Of the first 105: stated for 66, silent for 28, no source for 11. After the
  answer any other country in the text, in any wording ("Japanese-made", "a product of China"), cuts that
  sentence; "Japan-market model" is not an origin.
- **The answer**: JSON fields, not HTML: `conflicts` (points the sources disagree on: asked first, kept out of the
  text, shown in the report), `intro`, and the lists of the product's profile.
- **After** (`settle`): each intro sentence and each list item is checked alone: English only, no link, phone,
  price or markup, no shop talk (warranty, shipping, gifts, reviews, authenticity, parallel import), no talk about
  the listing ("per the specifications", "depending on the option", a seller's disclaimer "specs may differ"), every number is one the model was given or a club inside
  a range it was given (a tripwire, not a proof: a wrong number that stands elsewhere in the packet passes), no country but the decided
  one. A failing highlight or intro sentence is dropped; a failing item of another list drops that list (half a
  list of the box's contents misleads; so does a clean list over its cap of 12). No intro left: the title as one
  sentence (`fallback`). Caps: intro 400 characters, an item 220, the whole text 1 500. The HTML is built by the script (`p`, `h3`, `ul`, `li`, text
  escaped, a line break between blocks).
- **What nothing checks**: a claim without a number that the seller did not make (the model explaining a term).
  The prompt forbids it; read a sample of `translation/descriptions.jsonl` when a category or the prompt changes.

A kind of product has a profile (`describe.PROFILES`: its Naver leaf categories, its lists with headings and
caps) and a brief (`prompts/describe/<profile>.md`: what each list holds, what a buyer of this kind of product
must be told). `golf_set` (50002788): "What's included" and "Highlights"; no bag or no putter is said plainly; a
non-conforming driver gets one fixed sentence; a version for the Asian or Japanese market is one highlight, joined
with the origin. `junior_clubs` (50002787, 2026-11-11): the same two lists, a single club or a set said in the
intro with the age or height range the seller gives. A category without a profile gets `default`: the intro and highlights only. The common prompt
(`prompts/describe_system.md`) holds no golf word.

The answers are kept in `shops/<shop>/translation/descriptions.jsonl` (append-only; fields, HTML, what was cut
and why, conflicts, the origin decision, the model, the time; `generated: model` for a later Merchant feed, where
Google asks for AI-written text to be declared). A product with a row is not asked again; a row whose source
changed is reported `stale` and kept (`--force` asks again). `publish.py` puts the row's HTML into the payload and
into the publish digest only when the product has a row, so a product without one keeps its digest. Products
already in the shop are skipped unless `--published` or `--only` names them: a new description changes the digest,
and the next `publish.py` run sends the product (the owner's go-ahead first, JOB_AGENT.md).

### Which model writes the descriptions (compared 2026-11-10)

The default is **claude-sonnet-5-5 at effort `high`** (the owner, 2026-11-10: fewer errors; `medium` was the
default for a day, see the note after test 2). Two tests stand behind the choice of the model; repeat them when a
new model comes out, and add its row here.

**Test 1, breadth: one product, every model.** The same packet (Bridgestone BG-100, 8958060680: a clean listing
with two traps, a spec row that drops the #6 iron and a driver loft tied to the shaft set; 2 requests a setting)
and a stress packet (Mutsumi Honma + TaylorMade mixed set, 6707956586: the sources disagree on the loft, the
irons and the shaft material; 1 request). Three blind judges a product scored each answer against a fact list,
0-10. Accuracy and coverage are "clean packet / stress packet"; the price is the list price of the tokens used
(input + output, thinking included), no cache discount.

| Model | Effort | Accuracy | Coverage | Errors that block publishing | $ per 1 000 products | Time |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | medium | 9.8 / 5.5 | 7.4 / 5.7 | yes (stress) | 1.5 | 10 s |
| claude-haiku-5-5 | high | 10 / 10 | 5.0 / 6.0 | no | 3 | 21 s |
| claude-sonnet-5-5 | low, thinking off | 8.4 / 6.5 | 6.0 / 6.7 | yes (both) | 16 | 4 s |
| claude-sonnet-5-5 | medium | 10 / 9.7 | 8.9 / 9.0 | no | 24 | 11 s |
| claude-sonnet-5-5 | high | 10 / 10 | 7.7 / 9.0 | no | 29 | 13 s |
| claude-opus-5-5 | low | 10 / 10 | 6.8 / 9.7 | no | 36 | 8 s |
| claude-opus-5-5 | medium | 9.6 / 10 | 5.3 / 7.7 | no | 49 | 14 s |
| claude-opus-5-5 | high | 10 / 10 | 8.5 / 8.5 | no | 62 | 19 s |
| claude-fable-5-2 | low | 10 / 10 | 8.5 / 10 | no | 67 | 9 s |
| claude-fable-5-2 | medium | 9.2 / 10 | 8.2 / 9.2 | no | 109 | 23 s |
| claude-fable-5-2 | high | 9.0 / 10 | 8.3 / 7.7 | no | 208 | 56 s |
| claude-fable-5-1 (legacy) | medium | 8.5 / 10 | 4.3 / 10 | no | 146 | 23 s |

Prices per million tokens then (input / output): Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20,
Fable 5.2 $8 / $40. The answer itself is about 400 tokens; the rest of the output is thinking, which is what a
higher effort or a bigger model costs. From Sonnet `medium` up every setting was accurate; the dearer ones bought
nothing on this task.

**Test 2, depth: 35 products, the three candidates.** The 35 products first described (golf sets, 50002788), each
written by the three settings from the same prompt; one blind checker a product compared the three descriptions
(letters shuffled per product) with the packet: `good` (every claim supported), `minor` (slips of wording),
`wrong` (a false, unsupported or missing fact that misleads), and a usefulness mark 0-10.

| | claude-haiku-5-5 high | claude-sonnet-5-5 medium | claude-sonnet-5-5 high |
|---|---|---|---|
| good / minor / wrong | 11 / 22 / 2 | 18 / 17 / 0 | 20 / 13 / 2 |
| Usefulness, 0-10 | 6.7 | 7.3 | 7.6 |
| Picked as the best of the three | 9 | 14 | 12 |
| Empty "What's included" | 12 | 10 | 7 |
| $ per 1 000 products | 3.6 | 18 | 27 |
| Time a product (mean) | 27 s | 5 s | 12 s |

Sonnet `medium` and `high` cannot be told apart at this size (0 against 2 wrong of 35 is noise); `medium` costs a
third less and answers twice as fast. Haiku `high` is five times cheaper and makes no gross error, but writes
poorer descriptions (more slips, more empty lists, one description that fell back to the title) and is the
slowest, because it thinks the longest: the candidate for very large volumes, after the prompt is tuned for it.

**In use, the other 75 products of the store (harder listings: several configurations in one listing, sets
mixed from several makers).** Written at `medium` and checked the same way: 23 good, 36 minor, 16 wrong (a choice
described where one fixed combination is sold, another edition's features, a wrong count). The 16 asked again at
`high`, with one prompt line added: 14 passed, the other 2 had one highlight cut by hand. `medium` saves about $9
per 1 000 products against `high`; on hard listings that is not worth the errors, hence the default.

How the tests were run (scratch scripts, not in the repo): the packet, `describe.ask` and `describe.settle` called
directly for each model (`translate.AnthropicModel(key, model, effort, thinking="adaptive")`), nothing stored in
the shop and nothing published; the judging by agents that see the answers under neutral labels with the packet.
Limits: one or two requests a setting in test 1, one checker a product in test 2; only large differences are
reliable.

## Shopify roadmap

This is a design note, older than the publication above. The code so far: the read-only check of what a store already has (`shopify_catalog.py`),
the transform to prepared products (see Transform) and the placement into the shop's sections (`placement.py`, see
Placement) and the translation (`translate.py`, see Translation: `translation/translated.jsonl`, English by text
id); publication joins them (`publish.py`, see Publication).

The pipeline: collection (example_99) -> kept runs (`keep_run.py`) -> prepared products (`run_transform.py`:
prices in USD, options, SKUs, attributes, spec rows, text fields, free add-ons, reviews, photo files) ->
translations by text id -> placement (`placement.py`: the shop's sections, tags, product type) -> publication. Settled in the transform: the currency rule, the variant cap (over it: the
first combinations, every pair of values, `variants_capped`), the photos (re-uploaded WebP files, not Naver's CDN).
Settled since: publication through the Admin GraphQL `productSet` (see Publication); delivery, duty and margin
inside the price of a shop with free delivery (see The price, the owner 2026-11-11).

Credentials: a store app's client id + secret file per store, its path in env as `shop_stores.py` names it
(`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`), next to the store's domain, shop id, API version and namespace there; tokens are
minted per run (`shopify_catalog.Credentials`). Publishing needs write scopes: reuse `Credentials`, keep the read
check as it is. They are never committed. When publishing,
write the same source key (`<namespace>.source_offer_id` = `<namespace>:naver:<channel_no>:<product_id>`) and check
for it once more right before (a product published after the 5-minute snapshot).

When publication starts, add it as a flat module (`publish_shopify.py`) reading the prepared products, the
translations and `placement/placements.jsonl` (only `placed` products: their tags, product type, and the start
variant per collection as a metafield), reusing `shopify_catalog.Credentials` and the source-key check.

### What the naver-harvester published (reference for publication)

Read from 60 of its products in the shop (391 variants, all metafields; 2026-11-05). Repeat what works, not its
mistakes. A local snapshot of those 60 (not in git): `scripts/output/harvester-shopify-products-2026-11-05.json`.
- Body: `descriptionHtml` empty on 60 of 60; the text is in `custom.description_html`: optional prose `<p>` blocks,
  then one `<p>` of `<strong>Label:</strong> value<br>` rows (at most 60000 characters; 37 of 60 had spec rows
  only). Hidden labels: product number and date of manufacture (the label NFKC-lowercased, `\s:._-` stripped:
  productnumber, productno, 상품번호, manufacturedate, manufacturingdate, dateofmanufacture, 제조일자, 제조년월, 제조연월).
- Reviews: `custom.review` `{"scale_min":"1.0","scale_max":"5.0","value":"4.9"}` and `custom.rating_count` from
  Naver's summary, only with a count above 0; `custom.reviews_seo` holds the rows, and the same rows go to a Shopify
  File linked from `custom.reviews_feed_url`. A row: `id = int(sha256("naver:" + reviewId)[:12], 16) + 1`,
  `customer.name` the masked id, `title ""`, `verified false`, `source {platform: naver, language: ko, translated:
  true, reviewId}`, `createdAt`, images as Shopify Files links.
- Text fields: `custom.personalization_fields` (product-personalization/v1: key, label, required, placeholder, hint,
  maxLength; the seller's maxLength less the operator's suffix). Add-ons: `custom.optional_addons`
  (product-optional-addons/v1: groups `{key addon_<24hex>, label, choices [{key choice_<24hex>, label, priceKrw}]}`).
  `custom.required_selections` (a fold), `custom.category_start_variants`.
- Private `fairwardgolf.*` metafields (no storefront access): `source_offer_id`, `source_url` (no query or
  fragment), `naver_offer_key` (legacy), `catalog_fingerprint`, `catalog_stage` `showcase-cost-priced/v1`,
  `source_variants` v2 `{offerKey, translationHash, variants [{sourceId, variantId, optionValues, sku}]}`,
  `source_pricing` `{source {url, observedAt, basePriceKrw, originalPriceKrw}, policy, excluded, variants}`.
- Tags: leaf, parent and showcase tags plus `fairwardgolf:naver` (dropped once the public handle is set). Products are
  created DRAFT, then activated; `inventoryQuantity` 0 on all 391 variants.
- Handle: strip ™®© and apostrophes, NFKD without combining marks, refuse any non-ASCII left, lower case, join
  `[^a-z0-9]+` with "-"; refuse an empty one, over 255 characters, the word "naver" or a source id; the brand in front
  unless the name starts with it; a collision holds the product until a person writes a seoName.
- Brand: a Latin brand is its own English name, else a 23-entry dictionary (`mappings/brands.en.json`), then a
  reviewed spelling; distributors dropped (테일러메이드코리아 -> TaylorMade, 던롭코리아 -> XXIO).
- Images: `<handle>-NNN-<hash16>.webp`, alt = the title (at most 125 characters).
- Its mistakes: vendor drift (HONMA / Honma / Mutsumi Honma, PING / PING Golf) and doubled-brand handles, "korea" in
  6 handles, 45 distinct option names (one of 35 characters, "Color: L"), spec-label drift ("Total club count" /
  "Total number of clubs"), Event rows on 11 of 60 and pointer rows on 7 of 60, 62 of 250 alts duplicated or stale,
  2 products with no review rows though the counts said 3 and 21.
- Translation plan: `translations.jsonl` append-only `{id, kind, ko, en, by, at}`, the last line per id wins, the
  English checks (no Hangul, option values of 32 characters at most) there; publication maps every `*_ko` through
  `text_id` and skips a product with a missing id as `untranslated:<ids>`, results in `shops/<shop>/published.jsonl`.

