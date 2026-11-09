# scripts/

Client-side consumers of the Naver Shopping API. Everything here talks to a
running server over HTTP only, plus two other fetches: the photo files the API
linked, from Naver's image CDN (`naver_images.py`, see Product photos), and a
read-only look at our own Shopify store's catalog (`shopify_catalog.py`, see
The listing screen and the shop check).

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
| `deferred_log.py` | The shop's journal of deferred products (append-only); CLI `list` / `allow <key> --by` |
| `collect_guard.py` | The run rules around one product: one retry, then deferred; stop on a wall; stop on a repeated defect |
| `package_measures.py`, `category_measures.json` | Five shipping fields per variant: the seller's values, else the operator's category averages |
| `description_images.py`, `description_ocr.py`, `description_measures.py` | Optional stage: OCR of the description images (RapidOCR; Naver's CDN and the seller's HTTPS hosts; a worker process per product) into a sidecar per product; the transform guesses size / weight from it (a core for every category + parts profiles by Naver category id), the larger of that and today's value wins (see Package weight and size) |
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
(`job.py STAGES`): placement is built (`placement.py`, run on the whole shop before publication, not by the job),
translation and publication are not yet. The
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
description and the images' text are not translated (a later stage writes the description from them). Not built on purpose (the owner,
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

**A new shop or category** needs a short brief file only, no code. Write the file following the 50002788 one; the
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
["below_stated_product"]`. A table row may carry `plausible: {field: {min, max}}`, the operator's band: a stated value
outside it is not taken (`contradiction`, `reason: implausible_for_category`) and the default fills the field; no row
has a band yet, and none is made up. A missing field comes from
`category_measures.json`, the operator's table (per leaf category: low / central / high of the five fields, who
approved it and when, the table's version), as `source: category_default`; a seller's value is never overwritten.
No row for the category: `CategoryDefaultsMissing`, the run stops and asks the operator (values are never made
up). Every row carries `reliability`; today one level, `estimated_average` (the weakest: an average of estimates,
not measured), and delivery will apply its own coefficient per level. 50002788 풀세트 is filled (owner, 2026-11-05):
the median (central) and about the 10th / 90th percentile (low / high) of the naver-harvester's AI estimates on the
55 fairwardgolf sets in Shopify, sets with and without a bag together (none of their values was seller-stated).
Product sizes (not the package: kind product or unknown) are kept apart, optional.
Every field carries `confidence` (the owner, 2026-11-06): 3 = stated with its kind (a net weight, a weight with
the package, the box's sides); 2 = stated but its kind left open (a plain 중량 11.5kg: with the box or not), or bound
by club count, or a per-piece weight times the count; 1 = the category default. Of candidates that agree, the most
certain is taken.

### From the description images (optional stage, the owner 2026-11-07)

The images are most of a description (golf sets: ~12x the page's text) and state what the page does not: a box,
a product's weight and size, or, for sets, each part's. The stage reads them; the transform guesses the five
fields from that text and keeps, per field, the larger of the guess and today's value.

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
  "W53 x D38 x H62.5 cm"). Live check 2026-11-07 on other categories: a camping chair (625 x 530 x 380 mm), a
  kettle (0.6 kg, 170 x 170 x 100 mm); a kettle and desks whose images give sizes only as photo callouts: nothing;
* a **parts profile**, only where the category is sold as a set of like items in a container. Profiles are data
  (description_measures `Profile`: the items' weight / length ranges and labels, part labels that are never an item,
  the container's words and ranges, count words, a count row, plausible bands), mapped by the **Naver leaf category
  id** in `CATEGORY_PROFILES`:

  | Naver category | profile | items / container |
  |---|---|---|
  | 50002788 골프클럽 > 풀세트 | `GOLF_SET` | clubs (클럽 중량(g) rows, lengths in inches / cm; 샤프트 / 헤드 / 그립 are parts) / the bag (weight, height, mouth, sides) |

  A category with no profile gets the core only. Add a profile only when the core cannot read a category's images
  (its own tables of parts); a new category is otherwise just its shop rule's `description_images` switch.

Never read in either layer: a shop rule, customs, a person, a price, a disclaimer, anything after a cross-sell
heading to the end of the image. Lower bounds per variant (the item count from the variant's option values, the
title / 모델명, the profile's count row 총클럽개수, or the images; the container from the variant's values, the title /
facts, or the images' 포함 / 미포함 / 별도):

| field | guess | confidence |
|---|---|---|
| product_weight_g | a set / product weight stated; else (profile) items x the median item weight + the container's stated weight when the variant has it; else a plain 무게 / 중량 row | 2 |
| package_weight_g | a packed weight stated; never below the product guess (a box weighs at least its contents) | 2 |
| package_length_mm | a box side stated; else the longest of the product size, (profile) the longest item, the container's long side | 2 |
| package_width_mm, package_height_mm | a box side stated; else the product size's short sides or (profile) the container's mouth / sides | 2 |

An image's reading is never a seller's typed value: confidence 2 at most. A row OCR read below 0.9 (its weakest cell) gives no single
value (a box, a weight, a size, a length; research: ~38 % of such digit boxes were wrong, and the larger value wins,
so an upward misread is the one that would get in), only its share of the items' median weight.

With a profile and no word on the container (the variant, the title and the images say neither with nor without
the bag), every guess but a stated box drops to confidence 1, flag `container_unknown`: the operator's one default
row covers sets with and without the bag (the owner, 2026-11-07: no separate rows).

`merge_fields` compares each guess with today's value (a seller's value: its max; a category default: its central)
and keeps the larger; the other one travels as `compared`. **Absurd guesses are never taken** (`compared.rejected`):
above the field's band (the operator's `plausible` in category_measures.json, else the profile's, else the core's:
weight 10 g - 200 kg, a side up to 3 m), or more than 3x today's value (`far_above_today`: a misread "45.5kg", another
product). The owner's rule on parts (never summed) holds for the seller's text values; for the images' guess,
summing the items is the point. On the 50 fixture sets the guess wins on 4 (heavy or wide bags stated; parts alone
are lighter and shorter than the centrals: 12 clubs x ~330 g = ~4 kg < 5.7 / 7 kg; a 45.5" driver = 1156 mm < 1250
mm). Notes: `measures_from_images` (fields taken, per variant count), `description_images_missing` (switch on, no
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

**Prepared product** (`transform.Prepared`, `format: prepared/3`; 3 since 2026-11-08: no shop leaves, `product.attributes`
instead (see Placement); 2 since 2026-11-07: a variant's `package` fields
may carry `how`, `quote`, `flags` and `compared` (the images' guess, see Package weight and size), and `product` has
`description_images_text` (the images' text flag, see The images' text)): `key`, `shop`, `status` (`ready` / `held`),
`held` and `notes` (`{code, detail}`), `source` (run, line, link, channel_no, product_id, category_id), `product`
(`title_ko`, `brand_ko`, `brand_source`, `attributes` (`{gender: {value, variants, evidence, flags}}`), `options` `[{name_ko, values_ko}]`, `facts`,
`variants` `[{source_id, naver_variant_id, options_ko, price_krw, price_usd, sku, available, package}]`, `pricing`,
`specs`, `personalization`, `addons`, `rating`, `reviews`, `images`), and `texts` `[{id, kind, ko}]`: the translation
worklist, `id = <kind>:<sha256(ko)[:16]>`, so the same Korean text has one id (one translation) in every product.

Rules (`transform.py`, each from a real case, research 2026-11-05 on 23 collected sets: on 10 the naver-harvester
published, SKUs and prices equal on 201 of 201 variants):

- **Prices**: KRW = the product's price + the variant's `extra_price` (the page's own answer; option names are not
  parsed for money); USD = rounded up to the cent at the shop's rate; cost = price, no compare-at, not taxable.
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
  notes `shipping_paid` and `overseas_shipping` (the price stays the cost: the operator decides). An
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
`paid_variants` / `paid_addons` / `description_images`, off by default, all on for fairwardgolf 50002788. The shop's
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

## Shopify roadmap

This is a design note. The code so far: the read-only check of what a store already has (`shopify_catalog.py`),
the transform to prepared products (see Transform) and the placement into the shop's sections (`placement.py`, see
Placement) and the translation (`translate.py`, see Translation: `translation/translated.jsonl`, English by text
id); publication joins them.

The pipeline: collection (example_99) -> kept runs (`keep_run.py`) -> prepared products (`run_transform.py`:
prices in USD, options, SKUs, attributes, spec rows, text fields, free add-ons, reviews, photo files) ->
translations by text id -> placement (`placement.py`: the shop's sections, tags, product type) -> publication. Settled in the transform: the currency rule, the variant cap (over it: the
first combinations, every pair of values, `variants_capped`), the photos (re-uploaded WebP files, not Naver's CDN).
Open: publication through the Admin GraphQL `productSet` (the harvester's way) or a CSV import; whether shipping goes
into the price (today the price stays the cost and the operator decides).

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

