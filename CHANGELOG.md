# Changelog

Versions follow `VERSION` at the repo root; `/health` reports it. The browser adapter in `extension/` has its own
version in `extension/manifest.json`.

## 0.6.0 (2026-11-05)

- **Listing screen** (`scripts/listing_filter.py`): every listing row left out gets a reason: `sponsored`,
  `title_unavailable`, `rental` (the naver-harvester's stop words as they are, `listing_exclusions.json`),
  `category_mismatch` (exact leaf only), `key_unavailable`, `already_published`, `deferred`. Listing rows add
  `store.channel_no`.
- **Already in the shop** (`scripts/shopify_catalog.py`): the store's Admin API catalog, read only, any status, by
  the source key metafields `source_offer_id` / `naver_offer_key` (never by name); the shop is checked before each
  read; a bad or duplicated key stops the check; snapshot at most 5 minutes. Store values in `shop_stores.Shopify`
  (fairwardgolf given; the others wait for the operator). No stored token: a 24 h token is minted per run from the
  store app's client id + secret (a 0600, git-ignored file whose path is in `.env`), checked for the shop and
  `read_products`, renewed before it ends and once after a 401; queries only; never printed.
- **Deferred products** (`scripts/deferred_log.py`, `scripts/collect_guard.py`): partial -> one retry -> deferred
  with the first error; the owner allows one retry of one product (`deferred_log.py allow`); a wall stops the run
  without marking; two products in a row partial for the same reason stop the run.
- **Video posters as photos**: `/products/reviews/selected` counts a video's poster as a photo (tiers and caps);
  `naver_images` saves it as a review photo (`from_video`), `posters_as_photos` stores the video as its poster.
- **Weight and size candidates**: `/products/specs` `measures` (`naver_shopping/measures.py`): the seller's values
  from the rows, the notice, the description, JSON-LD and description tables, with quote, place, kind, scope,
  variant binding; pointers and doubtful lines kept apart. `scripts/package_measures.py`: five shipping fields per
  variant, the operator's category averages (`category_measures.json`) where the seller gives none; no row -> the run
  stops and asks. 50002788 풀세트 is filled (owner, 2026-11-05): the median of the harvester's estimates on the 55
  fairwardgolf sets in Shopify, `reliability: estimated_average` (the weakest level; delivery will add a coefficient).
- `example_99` runs all of it; it needs the shop's credentials file (`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`) and the
  category's averages. A wall (503, 502 "blocked the request") or a busy adapter (409) stops the run without
  marking a product. Verified live 2026-11-05: 2 sets collected; 25 published products found in a listing, all with
  the same source key as in Shopify.
- Stop words: `scripts/listing_exclusions.json` is now the harvester's file byte for byte.

## 0.5.0 (2026-11-02)

- **Options from the product page** (Naver change, 2026-11-02): the store backend's `validation-products` answers
  419 to the box (the page now sends a one-time token with its product call), so `/products/details` has null
  `option_groups` / `variants` / `supplements`, and a slug-less link answers 404. `/products/specs` now returns
  `options` from the product answer the page itself fetched, copied by the adapter (filter `/channels/` +
  `/products/`; the token is never copied, R-EXT-1): every variant with `extra_price`, `stock_quantity` and the new
  `is_available` (false = sold out, (품절); kept), text options (CUSTOM), simple options, add-ons. Decision log
  R-EXT-2 / R-NAVER-2. Adapter 0.4.4: reload it in `chrome://extensions`.
- **Variant choice** (`scripts/naver_variants.py`): free variants only by default; paid ones (more or less than
  the product's price) when the operator passes `paid`; a name stating another amount "(+N원)" counts as paid and
  is reported; a bare "+" joining a set's parts is not money. `example_14_product_options.py` on real golf sets;
  `example_99` writes `variants` (argument `paid`).
- **Text fields** (a name on a tag, an engraving): `options.text_options[]` adds what the product page shows of
  each field: `label` ("네임스티커 성함 (필수)"), `required`, `placeholder`, `hint`, `min_length`, `max_length`,
  `pattern` (`pdp.text_fields`, the attributes the naver-harvester reads). Null when the page has no such field.
- **Types**: `Variant.is_available`, `PageOptions`, `SimpleOption`, `TextOption`, `ProductSpecs.options`.

## 0.4.0 (2026-11-01)

- **`/products/specs` (beta)**: a product page's 상품정보 rows (label -> value: 제조사, 브랜드, 원산지 and the seller's
  attributes such as 종류, 성별, 총클럽개수), read in the owner's Chrome through the adapter (search -> card click ->
  unfold), parsed in Python (`naver_shopping/pdp.py`). The adapter itself is unchanged. 409 while a listing job runs,
  503 for a wall / no extension (scripts do not retry them). Decision log R-NAVER-1.
- **`/products/details`**: `facts` (brand, manufacturer, model, origin, each with its source); notice rows carry
  `is_see_description` ("상품상세참조"-style pointers); `description.text` is a text-node walk (lines per block,
  null for image-only descriptions instead of `"\u200b ..."`).
- **Types / scripts**: `ProductSpecs`, `ProductFacts`, `Fact`, `SpecRow`; `NoticeRow.is_see_description`;
  `NaverApiClient.product_specs()`; fixtures re-captured.
- **Examples**: `example_08_product_full.py` (one product, every field), `example_09_listing_then_specs.py` (a
  listing, then details the new way), `example_10_known_products_specs.py` (known links, matched by full name + id).
- **Reviews**: `writer.profile_image` is null for Naver's no-avatar placeholder (`profile-phinf.pstatic.net/404/`);
  `example_11_reviews_full.py` reads a product's reviews completely (all fields, order, media links) to JSONL.
- **Reviews, way 2**: `/products/reviews/selected` chooses up to `count` reviews worth showing (photo + 50+ letters +
  avatar first, then photo + text, then text; all with text for 20 or fewer), reading only the pages it needs;
  `/products/reviews` takes `media` (`all`, `photo_video`, `text`: the backend's `reviewContentClassTypes`).
  Researched against the product page's review window: same JSON, ~10x slower, so no adapter for reviews.
- **Product photos**: `scripts/naver_images.py` downloads the gallery `/products/details` links (the original files:
  the largest real size of every rendition, measured on 25 photos; fallback to `m10000_10000_no_rotate`, then
  `o1000`, recorded per file) and the chosen reviews' photos + avatars, with a plain HTTP GET (no page, no adapter:
  the gallery matched the page's 1:1). Only a store's WebP is written, the source stays in memory:
  `scripts/image_prep.py` (Pillow, one algorithm for every store: gallery short side down to 1500, Merchant Center's
  recommendation, long side <= 5000; reviews long side 1024; never enlarged; <= 1 MB by quality 85-80-75, then
  smaller sizes; sRGB, EXIF orientation, animation -> first frame, old EXIF/GPS/IPTC/ICC/XMP dropped, a new XMP with the store as publisher, read back and checked).
  `scripts/shop_stores.py`: our Shopify stores as a `StoreId` enum + profiles (fairwardgolf, skinsli, kyobooks,
  banafish), picked by `SHOP_STORE` in `.env`. Names `<slug|store-id>-001-<sha16>.webp`,
  `<store>-review-image|avatar-<sha16>.webp`; optional reviewed English `ImageSeo` (slug, title, alt <= 125, brand).
  `example_13_product_images.py`; `example_12` and `example_99` save review photos / avatars too.
- **Review videos**: attachments with `reviewAttachmentType` "M" are `video` now (they came as `image`); the link
  is the poster frame. Paging checked on 6782 reviews (340 pages, all unique, newest first).
- **FULL example**: `example_99_full_details.py` (a category's products -> details + specs + selected reviews),
  `example_12_reviews_selected.py`; `/products/specs` treats a card click that opened the store as not found.
- **Docs**: "Product details: two ways" (`/products/details` vs `/products/specs`, the full-flow catch, the two ways
  in) in ENDPOINTS.md and scripts/README.md.

## 0.3.0 (2026-11-01)

- **Setup for a new machine / agent**: `SETUP.md` (step by step, the agent does it itself and asks the operator only
  for what needs them: loading the adapter into their Chrome, secrets); `.env.example` (every per-machine value:
  what, where to get it, an example) and a dependency-free `.env` loader in the server and the scripts client
  (the shell wins).
- **Checklist**: `scripts/check_setup.py` (Python, packages, Chrome, `.env`, server, version, adapter, bridge port;
  `--live` one Naver call per transport, `--notify` a webhook test) -> READY / NOT READY.
- **Rules**: R-SETUP (a new requirement adds its check, `.env.example` line and SETUP step; secrets only in `.env`).

## 0.2.0 (2026-11-01)

- **Rules**: R-TYPE in `server/docs/DEVELOPMENT_RULES.md` (requests typed by marshmallow schemas, answers by
  TypedDicts + strict fixtures, nullable fields guarded, typed client methods, mypy for scripts); scripts conventions.
- **Scripts on typed methods**: `harvest_listing.py` and `example_search_harvest.py` use `api.search()` /
  `product_details()` / `catalog_reviews()`; every script passes `mypy`.
- **Types**: `scripts/naver_types.py` names every API answer (TypedDicts, written from real captured answers and the
  parser code); `test_naver_types.py` checks the captures strictly; typed client methods (`search`,
  `product_details`, `reviews`, `listing`, ...); examples use them and pass `mypy`.

## 0.1.0 (2026-11-01)

First release of this fork (based on [omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper)).

- **Structure**: the API server lives in `server/` (import root), HTTP-only consumers in `scripts/`, docs in
  `server/docs/` with a binding rulebook (`DEVELOPMENT_RULES.md`); root `README.md` / `AGENTS.md` index everything.
  Docker moved to `archive/docker/`; macOS is the supported platform.
- **Fix**: the search category filter works at any category depth (`categoryIds` = depth + id; was a fixed `03`).
- **Listing (beta)**: `POST /listings` reads the whole search.shopping listing for a query through the owner's own
  Chrome with the adapter extension (`extension/` 0.4.2, `server/docs/EXTENSION.md`); `GET /listings/<id>` and
  `/listings/<id>/products` report and page the rows. Captchas are notified and waited for, bans stop the job.
- **Scripts**: `NaverApiClient` (`get`, `pages`, `listing`, `health`), runnable examples `example_01..07`,
  `harvest_listing.py` (widget listing past 96 cards by price slices), `smoke_endpoints.py`.
- **Tests**: 129 server + 42 scripts offline tests.
