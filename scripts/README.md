# scripts/

Client-side consumers of the Naver Shopping API. Everything here talks to a
running server over HTTP only, plus a few other fetches (the full list: AGENTS.md rule 3): the photo files the API
linked, from Naver's image CDN (`naver_images.py`, see COLLECT.md, Product photos), and a
read-only look at our own Shopify store's catalog (`shopify_catalog.py`, see
COLLECT.md, The listing screen and the shop check), and the publication to that store (`publish.py`, see PUBLISH.md, Publication).
ShopNShip's public shipping calculator is asked by hand only, to capture the delivery tariff
(`shopnship_rates.py`, `shopnship_explore.py`, see PRICE.md, The price), never in the price path. The full list of
outside fetches: AGENTS.md rule 3.

## Docs

Working with the shop's products (the operator's tasks), each a skill (`.claude/skills/<name>/SKILL.md`) to read
first; what waits for the owner: [OWNER_RULES.md](OWNER_RULES.md).

| Task | Skill | Doc |
|---|---|---|
| Start or watch a job, the "Запусти scroll" shorthand | `run-a-job` | [JOB_AGENT.md](JOB_AGENT.md), [DEDUPE.md](DEDUPE.md) |
| Review drafts or a section by eye | `visual-review` | [LENSES.md](LENSES.md) |
| Why is a product missing, held, a draft, withdrawn, odd | `product-trace` | the shop's files (read only); the codes: [TRANSFORM.md](TRANSFORM.md#held-codes) "Held codes" |
| Activate, withdraw, hold, restore, reprice, back up | `store-actions` | [PUBLISH.md](PUBLISH.md), [PRICE.md](PRICE.md), [OPERATIONS.md](OPERATIONS.md) |
| Fix one product's brand, title, price, section, description | `fix-a-product` | the stage's doc below |

The scripts' topics, each in its own doc, each with a skill to read first:

| Doc | Skill | When to read |
|---|---|---|
| [COLLECT.md](COLLECT.md) | `collect-api` | Calling the API: product details, options, photos, the listing screen, reviews, examples, answer types, harvests |
| [JOB_AGENT.md](JOB_AGENT.md) | `run-a-job` | Running or watching `job.py` (one product per iteration, `new` + `run` or `scroll`), step by step: before, start, watch, stop, after |
| [DEDUPE.md](DEDUPE.md) | `run-a-job` | Duplicates (`dedupe.py`, `job.py --dedupe off\|log\|on`): a job's events and what to do, `--pairs`, `--report`, the rule |
| [TRANSFORM.md](TRANSFORM.md) | `transform` | The transform (collected -> prepared), the held codes and what to do on each, record types |
| [PACKAGE.md](PACKAGE.md) | `transform` | Package weight and size (the five fields), category defaults, confidence, the description images' OCR, the images' text for `describe.py` |
| [TRANSLATION.md](TRANSLATION.md) | `translation` | `translate.py`, the dictionaries, the prompts, review cleaning, the quality check |
| [PLACEMENT.md](PLACEMENT.md) | `placement` | The shop's sections, the last stage before Shopify (`placement.py`) |
| [DESCRIBE.md](DESCRIBE.md) | `describe` | The English description (`describe.py`) and its model |
| [PRICE.md](PRICE.md) | `price` | Why a product is priced X, the price rule, the delivery tariff, repricing (`shop_pricing.py`, `reprice.py`) |
| [PUBLISH.md](PUBLISH.md) | `publish` | Publication to Shopify (`publish.py`), the payload, withdraw / hold / restore / activate, the Shopify roadmap |
| [OPERATIONS.md](OPERATIONS.md) | `operations` | Running the scripts, tests and checks, the backup, shared files, conventions |
| (none) | `release` | Cutting a release (developer): VERSION, check.sh, tag, push, the state backup |

Also: [ONBOARDING.md](ONBOARDING.md) (a new category or shop, skill `new-category-or-shop`),
[LENSES.md](LENSES.md) (visual review, skill `visual-review`), [SELLER_DATA.md](SELLER_DATA.md) (what sellers write); developers: skills
`seller-pattern-rule` (a seller pattern -> rule -> test), `prompt-change` (a model prompt), `api-error-triage` (an
API or job error).

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
| `naver_images.py` | Downloads the photos the API linked (gallery, review photos, avatars) from Naver's image CDN with plain HTTP and saves them as the store's WebP (see COLLECT.md, Product photos) |
| `image_prep.py` | The WebP preparation, one algorithm for every store: size, bytes, metadata, checks (no network) |
| `naver_variants.py` | Which variants to collect: free ones by default, paid ones when the operator turns `paid` on; sold-out rows kept and marked (see COLLECT.md, Product options) |
| `shop_stores.py` | Our Shopify stores (`StoreId` enum + publisher / site + Shopify values), picked by `SHOP_STORE` |
| `listing_filter.py`, `listing_exclusions.json` | The listing screen: which rows to open, a reason code for each left out (rental stop words from the naver-harvester) |
| `shopify_catalog.py` | The "already in the shop" check: every product's source key from the store's Admin API (read only) |
| `publish.py`, `shopify_payload.py`, `shopify_admin.py` | Publication: prepared + translated + placed -> the store (productSet, photos, reviews' files, ACTIVE, or DRAFT first for a category not marked reviewed, the website); the payload built offline; the two writing apps. See PUBLISH.md, Publication |
| `shop_pricing.py` | The price rule per shop: a variant's cost per item, price and how they were made (`Policy.quote`). fairwardgolf: `landed/2`, delivery, duty and margin inside the price; a shop without the rule: `krw-cost/1`, 1 000 KRW = 1 USD up to a dollar, price = cost. See PRICE.md, The price |
| `delivery_tariff.py`, `delivery_tariffs.json` | The delivery cost of one packed box by a recorded tariff, offline (billable weight, step, fees once per box); the tariffs as data, each traced to a dated capture, with `version` and `history`. See PRICE.md, The price |
| `shopnship_rates.py` | ShopNShip's public calculator (networked, by hand only): `quote` one box, `capture` the grid into a dated file, `compare` a capture with the recorded table. Never in the price path |
| `shopnship_explore.py` | Research tool (networked, by hand only): wide sets of boxes asked of the calculator and compared with the tariff model (`run`, `report`). Never in the price path |
| `listing_title_rules.json` | Ours: per Naver category, the title words of what the shop's section does not sell; the screen drops such a row as `title:<code>` (listing_filter) |
| `review_grid.py` | Read only, offline, by hand: numbered sheets of the published products' first photos and an index (number, key, title, handle, admin link), for a look by eye after a run (JOB_AGENT.md, 5. After); draws through `sheet.py` |
| `lens.py` | Read only, offline, by hand: visual lenses, numbered contact sheets for one question each (`section`, `price`, `brand`, `dupes`, `held`, `products`) plus `index.tsv` and `summary.json`, for an agent to look at by eye and prove by number (LENSES.md, skill `visual-review`) |
| `sheet.py` | The contact sheet drawing under the lenses, `review_grid.py`: cards (number, photos, labels, mark, group), grid and rows layouts, the index |
| `shop_view.py` | One read-only view of a shop's files joined by key (prepared, translated, placement, the ledger, collected photos) and a job's events, for the lenses |
| `make_lens_fixture.py` | Offline, by hand: cuts the lenses' real-record fixture (`fixtures/lens/cases.json`) from `scripts/output`, the cases listed with why (LENSES.md, Tests) |
| `review_suspects.py` | Read only, offline: the published products of a category that may not be what its section sells (one club, 2-3 clubs, used, junior or accessory words), with key, store id, handle, price and reason; a table and a CSV for the owner's review after a lenient run (JOB_AGENT.md, 5. After) |
| `dedupe.py` | Duplicates (the owner, 2026-11-15): the rule (title key, photo / variant confirmation, grade then reviews) and the index `job.py --dedupe log` / `on` uses after collect; `--report <shop> [--category]` lists the duplicate groups already in the store, best first (members joined by title words only marked), `--pairs <shop> --job <id>` draws a job's pairs side by side with an index.tsv. Read only, offline (DEDUPE.md) |
| `publish.py --withdraw` | Takes a published product off the store (DRAFT, nothing deleted) and keeps it from being sent again; the ledger keeps why |
| `publish.py --restore` | Undoes a withdrawal (with `--reason`): ACTIVE again (a draft stays a draft, 2026-11-16), its last published row back in the ledger with no digest, so the next `--only` sends today's data to the same product (2026-11-15: no-brand agency imports back under the shop's name). A title translated under the shop's name ("Fairward Golf ...") takes the brand found later in its place (`shopify_payload.title_vendor`) |
| `publish.py --activate` | A draft (a category not marked reviewed, draft first 2026-11-16) live: ACTIVE, the ledger row again with `store_status: ACTIVE` and `activated`, nothing sent again; repeatable; only on the owner's word after the lens review. A key that is not a published draft: `not a draft here` |
| `job.py activate --job <id> [--dry-run]` | Every draft of a job live the same way (withdrawn ones skipped; `--dry-run` lists them, no store call); prints the `--withdraw` lines of the old copies a draft did not replace (`replace_skipped`: the new one is a draft) and, while the category is not marked reviewed, that `reviewed=True` is the owner's word |
| `store_diff.py` | Read only: what a publication would change in the store, field by field, per published product; the published products that cannot be built now; `--adopt` records `output` for those the store already has. A draft's status is not compared (its update sends none); a draft the store has ACTIVE (activated in the admin by hand) is listed with the `--activate` that records it (2026-11-16). Run it after any change of rules, dictionaries or a new category (ONBOARDING.md part D). About a minute for 2,015 products (2026-11-16: 20+ minutes before; publish.py reads the shop's files once while they do not change, the store is read 50 products a query, 3 queries at a time) |
| `reprice.py` | Products already in the store: old -> new prices under the shop's rule (a dry-run table, also a TSV under `publish/`); `--apply` sends them, on the owner's word. See PRICE.md, The price |
| `test_publish.py` | Offline tests for the payload (the variants' prices and metafields included) and publish.py (fake Shopify clients) |
| `test_shop_pricing.py`, `fixtures/pricing/` | Regression for the price rule: real products cut down to what the rule reads (the variants' prices, the delivery in Korea, the package fields), with the cost, price and breakdown each variant must get; `UPDATE_GOLDEN=1` rewrites the expected part after a deliberate change of the rule or the tariff: read the diff |
| `test_delivery_tariff.py`, `test_shopnship_rates.py`, `test_shopnship_explore.py` | Offline tests for the tariff calculator (the captures and explorations replayed through it) and the calculator's client (a fake calculator, a saved capture) |
| `fixtures/shopnship/` | The calculator's answers of 2026-11-11: two grid captures (the second is the tariff's source), two explorations and the second round's rows; the backups a new capture is compared with |
| `test_reprice.py` | Offline tests for the repricing flow |
| `conftest.py` | The folder's tests never reach the network: a connection attempt fails the test; no test sends a notice (`notified` stands in for `notify.notify`) |
| `deferred_log.py` | The shop's journal of deferred products (append-only); CLI `list` / `allow <key> --by` |
| `collect_guard.py` | The run rules around one product: one retry, then deferred; stop on a wall; stop on a repeated defect |
| `package_measures.py`, `category_measures.json` | Five shipping fields per variant: the seller's values, else the operator's category averages; the table also holds the operator's `baselines` for the composition; confidence 1-5 |
| `description_images.py`, `description_ocr.py`, `description_measures.py` | Optional stage: OCR of the description images (RapidOCR; Naver's CDN and the seller's HTTPS hosts; a worker process per product) into a sidecar per product; the transform reads size / weight from it and from the typed description text (a core for every category + parts profiles by Naver category id): a stated box / weight takes the place of a category default, and a set's other fields are composed from its parts with the operator's baselines, the flat default last (see PACKAGE.md) |
| `review_clean.py` | The reviews sanitized in the transform: decoration out, the Korean purchase cut, empty reviews dropped (see TRANSFORM.md, Transform) |
| `translate.py`, `translation_dicts.py`, `translation_rules.py`, `translate_keys.py`, `translate_eval.py`, `prompts/` | Translation of the prepared texts (see TRANSLATION.md, Translation): the model stage, the per-kind dictionaries (live / backup), the unit rules, the prompts |
| `description_image_text.py` | The images' OCR rows -> clean Korean blocks (text / table) for `describe.py` (not translated since 2026-11-10); run_transform writes `translation/<product id>/description_images.ko.*` and the flag `product.description_images_text.state` |
| `test_description_images.py`, `test_description_ocr.py`, `test_description_measures.py`, `test_description_image_text.py` | Offline tests for the stage (fake fetcher and engine), the slicer / rows, the guess and the merge (real OCR rows) |
| `product_page.py` | Saves a product page as the owner's Chrome renders it (`/products/page`): page.html, the page's own answer, meta; for developing parsers and checking collected data |
| `captcha_watch.py` | Reports a Naver captcha the adapter waits on (reads `/captcha`): one line per new captcha / solved / timed out; independent of any collection |
| `keep_run.py` | Keeps a collection run (example_99 output) per shop, byte for byte, read-only (see TRANSFORM.md, Transform) |
| `shop_files.py`, `test_shop_files.py`, `test_shop_lock.py` | The shop's shared files written and read safely: `write_atomic` (a rewritten file through `<path>.<pid>.part` and a rename), `append_line` (one write of whole lines, a line end first when the file lacks one), `read_jsonl` (a bad line is `LedgerError` naming `<path>:<n>`; a cut-off last line of an append-only file ignored with `tail_ok`), `shop_lock` (see OPERATIONS.md, Shared files) |
| `notify.py` | A job's stop / done notice to the owner (`job.py` main, 2026-11-16): a copy of `server/notify.py` (`NAVER_NOTIFY_WEBHOOK`, else a macOS notification, never raises); `conftest.py` replaces it in every test |
| `check.sh` | Offline, before a commit: the server suite, the scripts suite and mypy, each in its own process; prints the three results, non-zero exit when any fails |
| `state_backup.py`, `test_state_backup.py` | Offline, by hand: the backup of `scripts/output`, `server/output` and `research/` (plans outside git, with the state) into tar + zstd archives by phase outside the repository (state, photos, description images in parts, server pages, old runs), `MANIFEST.json` with sha256, `RESTORE.md`; `--dry-run`, `--verify`, `--restore` into an empty folder. Reads the sources only (see OPERATIONS.md, Backup) |
| `transform.py`, `transform_shops.py`, `run_transform.py` | The transform: kept runs -> prepared products per shop (shared rules, per-shop rules as data, the CLI) |
| `attributes.py` | Neutral attributes the transform writes to `product.attributes` (gender with its evidence: the variants, the 성별 row, the title; the listing query only flags `listing_disagrees`). A new kind of split is a new `Attribute` (data) |
| `brand_fallback.py` | Run-level: a brand for every prepared product that states none (a brand of the shop in the title, a dictionary brand in the title, 원산지's importer, the images' text, else 노브랜드; note `brand_fallback`) |
| `placement.py`, `placement_rules.py` | The last stage before Shopify: prepared products -> the shop's sections (leaf tags, product type, `start_variants`) from the shop's profile (data); unknown / conflict held as `unresolved`. How to add a split: [PLACEMENT.md](PLACEMENT.md) |
| `test_placement.py`, `test_brand_fallback.py` | Offline tests: the gender attribute and placement (the 50 fixtures, the rules case by case), the brand fallback |
| `test_transform.py` | Offline tests for the transform on real collected lines (`fixtures/collected_fairwardgolf.jsonl`) |
| `test_prepared_golden.py`, `collected_fixtures.py` | Regression: collected lines of real products (`fixtures/collected/`, from the server's saved-page fixtures) through the transform must equal `fixtures/prepared/`; `UPDATE_GOLDEN=1` rewrites them after a deliberate change, read the diff. Added when the owner asks, or from products checked in test runs without asking (server DEVELOPMENT_RULES R-TEST-5, the owner 2026-11-06) |
| `test_measures_fixtures.py` | Regression for the five package fields: 17 real golf sets cut down to what the measures code reads (`fixtures/measures/<product id>.json`: title, 상품정보 rows, variants' option words, add-ons, typed lines, the OCR rows with their confidence, the server path's candidates; sellers' phones, addresses and shop names are "x") through `package_measures.variant_measures` and the transform's hook with the real `category_measures.json`, against the fields each variant must get (value, source, confidence 1-5, how, parts), checked by hand against the product's lines (`checked`; where a fixture's `note` says "approximate" the value pinned is the rule's present approximation, not the page's figure). One test per product, one that the set covers every level and source. `UPDATE_GOLDEN=1` rewrites the expected part: read the diff against the products' lines |
| `smoke_endpoints.py` | Live smoke: `/health` plus 11 endpoints (all but `/products/specs`, `/products/page` and `/products/reviews/selected`), one at a time. Networked. |
| `example_search_harvest.py` | Template: search, classify the cards, fetch details, write resumable JSONL |
| `test_naver_api_client.py` | Offline tests for the client and the classifier |
| `test_naver_images.py` | Offline tests for the photo downloader (a fake CDN, Pillow-made photos) |
| `test_image_prep.py` | Offline tests for the WebP preparation (Pillow-made photos) |
| `test_naver_variants.py` | Offline tests for the variant choice (real rows of a product with paid and sold-out variants) |
| `test_shop_stores.py` | Offline tests for the store registry (every `StoreId` has a profile, `SHOP_STORE`) |
| `test_listing_filter.py`, `test_shopify_catalog.py`, `test_deferred_log.py`, `test_package_measures.py` | Offline tests for the screen, the shop check (a fake Admin API), the journal and run rules, the shipping fields |
| `example_0N_*.py` | Runnable examples, one API topic each (see COLLECT.md, Examples) |
| `harvest_listing.py` | Full listing of store product links for a keyword + category, price-sliced, resumable |
| `output/` | Run output (`output/<run>/products.jsonl`, `listing.jsonl`), gitignored |

