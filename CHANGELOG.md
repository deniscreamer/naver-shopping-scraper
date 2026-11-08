# Changelog

Versions follow `VERSION` at the repo root; `/health` reports it. The browser adapter in `extension/` has its own
version in `extension/manifest.json`.

## 0.10.0 (2026-11-08)

- `scripts/job.py` (new, the owner 2026-11-07): a job takes one listing and works one product per iteration
  (collect -> one-line kept run -> description images -> prepare), resumable, each product's stage read from the
  files; 409 waits, Naver's error page waits and retries then skips, a wall stops; `new` / `run` / `status`.
  Translation and publication are named stages, not built. `scripts/JOB_AGENT.md`: how an agent runs it.
  `collect_product.py`: example_99's per-product collect, shared. `SourceStopped` carries the API status.
  Then: waits 15 min for the extension / server instead of stopping, asks the owner again for a captcha not answered
  in time (6 times), reads the listings deeper when too few products pass the screen or the snapshot is used up
  (`refresh`), a start / done line per product with stage times, a `== progress:` line every 10, `status` shows the
  running product and stage.
- /products/specs, /products/page: the search tab is kept between reads and the next product is searched in its
  own box; the product tab is closed after each read. A login page on the way is reset from naver.com (no wait;
  R-EXT-3 changed, decision log). A 503's error starts with its kind: `wall:`, `naver error page:`,
  `adapter error:` (ENDPOINTS, K-21).

## 0.9.0 (2026-11-07)

- No brand stated is no longer a hold (`brand_missing` removed): `brand_ko` stays null with the note
  `brand_unstated`, whose detail lists the page's hints (manufacturer, a name in brackets in 원산지); the vendor step
  decides from the title, the hints and the images' text. No brand list: brands are not known ahead of a run
  (the owner 2026-11-07; 2 of 40 sets held for it before).
- Description images (optional stage, the owner 2026-11-07): `scripts/description_images.py` reads a product's
  description images with RapidOCR (PP-OCRv5 Korean) into a sidecar per product. Images from Naver's CDN and any
  public HTTPS host the seller links (AGENTS.md rule 3; never http, an IP, localhost or a name resolving to a private
  address); banners, the first SmartEditor header strip, GIFs and tiny images out; Naver first: a tiled body read
  from its tiles, from the seller's own sources only when a tile fails; an image another product of the store already read is reused; equal
  slices read once (dHash). One fresh worker process per product (no memory build-up; a crash, a kill or a timeout
  is that product's error, one retry, then an error sidecar), one run per shop (a lock), Ctrl+C clean. Image status
  read / failed (5xx, read again) / gone (4xx, for good) / refused (a seller's hotlink block). Cache one folder per
  product, `--prune-cache`. Switch `CategoryRules.description_images`: off by default, on for 50002788.
- Size / weight from the images (`description_measures.py`), in the transform: a core for every category (stated
  packed / set / product weight and size, axis-letter sizes) and a parts profile per Naver category id
  (`CATEGORY_PROFILES`; 50002788 `GOLF_SET`: clubs x median weight + the bag, the longest club / bag, the bag's
  sides); per field the larger of the guess and today's value wins (`compared`: the other one, brief). Never taken:
  a guess above its band (operator > profile > core) or over 3x today's value, a single value read below OCR
  row confidence 0.9; an image's value is confidence 2 at most; an unknown bag drops a set's guesses to 1
  (`container_unknown`). A box never weighs less than its contents. Notes `measures_from_images`,
  `description_images_missing` / `_stale` / `_failed` / `_partial`.
- The images' text for the translation step (`description_image_text.py`): run_transform writes clean Korean blocks
  (text / table; repeats, low confidence, fragments, photo labels, prices, contacts, shop terms, store info, legal,
  promos, cross-sell out; a degree sign read as 0 put back; review screenshots in the images kept as context, the
  instructions say to leave them out) with instructions and the category's
  glossary to `shops/<shop>/translation/<product id>/description_images.ko.txt|.ko.json`; a block's `key` is the
  same in every listing that carries it (`shared`: how many of the store's do), so a store's spec sheet stays and is
  translated once. One flag per prepared product, `product.description_images_text.state`: off | not_read | empty |
  to_translate | translated (an `en.json` with `source_sha256` = the text's sha256). The translation itself is a
  later step.
- `scripts/example_15_description_collect.py`: one golf full set collected end to end with its description images
  (OCR) and prepared, in its own folder; prints where each package field and the images' text came from.
- Prepared format `prepared/2` (the package fields' `how` / `quote` / `flags` / `compared`, the text flag). New
  requirements rapidocr + onnxruntime (check_setup, SETUP.md, K-17). Regression: OCR sidecars of the 50 fixture
  products.
- Docs: the OCR study's durable results moved into the code and docs before its notes were deleted: engines
  and options rejected and why, RapidOCR misreads not repaired, image selection numbers, the cache size, Naver CDN
  facts for description images; a one-photo gallery is the seller's (the page holds one, checked via /products/page).

## 0.8.0 (2026-11-07)

- Run of 40 more (2026-11-07), generic fixes: spec rows vs variants read a part count in an axis name ("아이언 선택
  (8개)") as that part's, not the set's (a true 총클럽개수 row was dropped on 7 sets); notes `specs_contradict`,
  `specs_loft_near_miss`, `specs_lists_unsold`; title words of whole multi-word values; the variant cap covers value
  pairs; few_pieces from 종 / 하프세트, not on "10+1pcs"; 원산지 with the parts' countries kept; SIMPLE one-value
  options as facts; add-on codes and 택N numbering out; colour-named axes of flex values as placeholders.
- Description: table rows as one line ("a | b | c") in `description.text` (shape change, ENDPOINTS); cross-sell
  pairs, the store's genuine-goods pitch, section labels, tracking pixels, dispatch / holiday banners out; run-level
  store banners repeated across one store's listings (`shared_images.py`, note `description_shared_images`).
- Docs: [scripts/SELLER_DATA.md](scripts/SELLER_DATA.md), the seller data patterns behind the collection and
  transform rules. Regression fixtures: 19 more products of the run (50 in all).
- Listing screen: ad cards are kept by default (the owner, 2026-11-06); `Screen(exclude_sponsored=True)` leaves
  them out. Rental, another category, already in the shop and deferred stay screened.
- /products/specs, /products/page: when the card is not on the search page for the product's name (and no query was
  given), a second search with the name's first 5 words (13425122164).
- /products/specs delivery.lead_time: new `today_off` ("오늘출발 휴무"); `today_cutoff` is no longer filled from
  thisDayDispatchBasisTime on such a day (6540695739, 13553116678, 10816781893, 13302492097, 10816904599).
  `arrival_date_text` also read from the 네이버 배송 / 내일배송 "11.11.(수) 도착" line (13369469193).
- Description cleanup from the pilot 20: KRW price promos, cross-sell lines, whole contact sentences (만큼 / -면
  continuation) and contact closings, the store name without a 구매대행 prefix, junk-only text (None, note
  `description_junk`). Banner images: 톡톡 / 하단_상페 / 하단고정배너 names, Hangul typed on a QWERTY keyboard, and, with the
  description HTML, link banners (TalkTalk, Band, blog, Instagram, YouTube, Kakao, store pages) and spacer strips (new
  `clean_images(images, html)` argument, rules `link_banner`, `spacer`).
- transform: spec rows vs variants add the driver loft (드라이버 로프트각 vs 9도 / 9.5 SR values: dropped or bound like the
  shaft material), the description sentence "플렉스 R 모델의 아이언에는 카본 샤프트" as a material binding, and title/row number words
  with units (11.5 = 11.5도, 유틸4 / 4U = 4번 of a 유틸리티 axis, 5W) and the bag (+골프백 vs "캐디백 미포함" values). Pilot
  2026-11-06: 10816781893, 10816904599, 11635855564, 13369469193, 13413924099, 13553116678, 7166885441.
- Transform: per-variant `today_dispatch`; value tags ("[당일출고]") and "(선택)" on option names left out; the cap
  shared out in turn over the first axis; notes `few_pieces` from 총클럽개수, `gift_hidden`.
- Regression fixtures: 12 more saved pages from the pilot (31 in all).

## 0.7.0 (2026-11-06)

- **Transform** (`scripts/transform.py`, `transform_shops.py`, `run_transform.py`, `keep_run.py`): kept collection
  runs per shop -> prepared products (Korean, ready / held with codes, a translation worklist with content-hash text
  ids). Prices, options, SKU, leaves, spec rows, text fields, free add-ons, reviews. Checked on 23 collected sets:
  on 10 the naver-harvester published, SKUs and prices equal on 201 of 201 variants; a review-discount axis it
  published is dropped; 2 sets over 100 combinations held.
- **40-product run** (2026-11-05, research): fixes from checking every product against its saved page:
  `/products/specs` `delivery` (the fee as the page charges it, overseas, customs; a backend said free for a set
  shipped from Japan at 99,000 KRW per unit); `description.images` for SmartEditor ONE bodies (27 of 40 had none);
  "package weight" read as packed; page reads by the product's name first (the listing's search missed the card
  on 27 of 40, reading each page twice); image CDN pace 1 s; a folded 상품정보 list is a partial collection and
  held (`specs_folded`); delivery-message rows, 인증정보 rows and "(구매대행)" in 원산지 left out; log lines
  `api:` per failed answer and `ext-product:` per page read (R-STYLE-4).
- **Delivery, how fast and from where**: `/products/specs` `delivery.scope` (international / domestic) and
  `delivery.lead_time` (the store's average days from the page answer; today cutoff, average arrival days and
  probability, ship date from the purchase box); carried into the prepared product.
- **`/products/page`** (development and analysis): the product page as the owner's Chrome rendered it and its own
  answer, read like `/products/specs`, never cached; `scripts/product_page.py` saves it.
- **Captcha wait and watch**: `NAVER_CAPTCHA_WAIT_S` (default 600 s, was 60); the question text is read and logged,
  the page saved, the cursor put in the answer field (for an answer from a phone through remote desktop); a new
  captcha after a wrong answer is reported again. `GET /captcha` shows the state; `scripts/captcha_watch.py`, a
  separate process, reports each captcha / solved / timed out, so collection only waits. Still answered by the
  human only.
- **40 fresh pages checked** (2026-11-06, `/products/page`): `delivery.extra_fee_text` (the seller's regional fee
  text, "제주 도서산간 10,000"); `description.images` from every image of the body (SmartEditor ONE inline images,
  editor-NONE bodies; map images left out). Transform: paid variants and paid add-ons per category (`paid_variants`,
  `paid_addons`, off by default, both on for 50002788 sets: their photos show the extras), the variant choice made
  from the page's options; notes `paid_variants_left_out`,
  `title_names_one_variant`, `purchase_agency`; placeholder labels on facts and "옵션+..." names; gender words of
  option values add leaves; required add-on groups; 원산지 without a bracketed importer; single spaces in options.
- **Re-run on the same 40** (2026-11-06): the purchase box's new wording ("14:00 까지 결제 시 오늘 바로 발송",
  "11.11.(수) 도착 확률 98%") -> `lead_time.today_cutoff`, new `lead_time.arrival_date_text`; the cutoff also from
  the answer's `thisDayDispatchBasisTime`. Transform: title words that fit part of the values, new notes
  `specs_name_one_variant`, `option_values_duplicate`, `few_pieces`, `description_mentions_gifts`; the seller's
  numbering out of option values and add-ons; 원산지 with brackets inside brackets; the return fee typed as the
  regional fee text dropped (only when the notice states that same return fee); jump-link lines out of the description.
- Weight and size from the seller's text read more of what is written (`naver_shopping/measures.py`): more units (파운드,
  온스, 키로, kgs, 센치, 피트), decimal comma, packed / net words (포장 무게, 택배 무게, 박스 포함, 본품 무게) also after the number,
  tolerances and the same weight in two units, lb + oz, per piece and multipliers, every size triple with its own
  kind, two-side sizes, axes after the unit or in the label, "(단위: cm)", a weight inside a size row, td club tables.
  Sets are recognised from counts (6아이언, 12pcs, 3종); in a set the parts (club codes, bag, reference club "7번 기준", club
  headings) are components and a plain 중량 row is the set's weight. Weight candidates gain `count` and `flags`; new
  review reasons `value_list`, `other_part`, `decimal_comma`, `ambiguous_unit`; loads and capacities and unit-less
  ranges are no longer read. `package_measures`: stated set weights per variant (6630856593), 2% agreement,
  `below_stated_product` flag on a default package weight, optional operator `plausible` band. On the 40 golf sets:
  product weight now stated for 6630856593 (11.5 / 4.7 kg by club count) and 10639350746 (14 lb); 3 more products gain
  correctly tagged club-part candidates; the other 35 are unchanged.
- Description text and images no longer carry SmartEditor cards that are not the product: link cards (other products
  of the store, TalkTalk), the store map and address, and shopping cards' posters. In-page jump links ("▲ 이동(상단)") and
  bare hashtag lines are dropped. **Shape change:** `description.text` now has one empty line between SmartEditor
  components.
- Transform: new `description_clean.py` strips the seller's boilerplate from `description_ko` and `description_images`
  (return / delivery / customs notices, contact and phone lines, greetings and signatures, duties, lead time, promo
  and store claims, the monitor disclaimer, gift blocks when promotions are hidden, banner images by name), with notes
  for a 모음전 page and for banners inside snap tiles.
- Transform: spec rows are checked against the sold variants by fact (shaft material class, club count of stated
  totals and part lists, the composition rows as one set, model year). A row true of no variant, or one every variant
  already states, is dropped with a note. A row true of some variants only is kept with `for_ko`, the option values it
  fits. New notes: `specs_fit_no_variant`, `specs_stated_by_variants`, `specs_bound_to_variants`,
  `specs_composition_undecided`. The `title_names_one_variant` note is less noisy: the title's own span ("XR26"), no
  gender word without a rival, no 백포함 vs 백세트포함, and title counts that name a part list ("(클럽10개)").
- Package fields carry `confidence` 1-3 (3 stated with its kind, 2 stated with the kind open or the binding
  worked out, 1 the category default): 6630856593's 11.5 / 4.7 kg is used at 2.
- Transform: more variants than the shop's cap are no longer held: the first ones are offered (in stock and cheaper
  first, one per option value first so every value stays on sale), note `variants_capped` (an XXIO 14 set: 486 ->
  100).
- Regression fixtures from saved pages (DEVELOPMENT_RULES R-TEST-5): `server/naver_shopping/fixtures/pages/` (cut by
  `page_fixtures.py`, replayed by `test_pages.py` through the new pure `ext_product.specs_from_page`),
  `scripts/fixtures/collected/` and `scripts/fixtures/prepared/` (`collected_fixtures.py`, `test_prepared_golden.py`);
  `UPDATE_GOLDEN=1` rewrites them after a deliberate change.
- **Product page click** (`ext_product._card`): the card's photo is clicked, not the card's middle band, where the
  store name link lies (it opened the store, then Naver's login page; seen twice on thegolf cards, 2026-11-05).

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
  smaller sizes; sRGB, EXIF orientation, animation -> first frame, old EXIF/GPS/IPTC/ICC/XMP dropped, a new XMP with
the store as publisher, read back and checked).
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

First release of this fork (based on
[omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper)).

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
