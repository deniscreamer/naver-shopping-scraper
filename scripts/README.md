# scripts/

Client-side consumers of the Naver Shopping API. Everything here talks to a running server over HTTP only, plus a
few other outside calls, each dated at its code (the full list: AGENTS.md rule 3): the photo files the API linked, from
Naver's image CDN (`naver_images.py`, see COLLECT.md, Product photos); the sellers' description image hosts
(`description_images.py`); a read-only look at our own Shopify store's catalog (`shopify_catalog.py`, see COLLECT.md,
The listing screen and the shop check; `store_diff.py`), and the publication to that store (`publish.py` through
`shopify_admin.py`, see PUBLISH.md, Publication); the model APIs (`translate.py`, `describe.py`); the owner's notice
webhook (`notify.py`). ShopNShip's public shipping calculator is asked by hand only, to capture the delivery tariff
(`shopnship_rates.py`, `shopnship_explore.py`, see PRICE.md, The price), never in the price path.

## How to use

Working with the shop's products (the operator's tasks), each a skill (`.claude/skills/<name>/SKILL.md`) to read
first; what waits for the owner: [OWNER_RULES.md](OWNER_RULES.md).

| Task | Skill | Doc |
|---|---|---|
| Start or watch a job, the "Запусти scroll" shorthand | `run-a-job` | [JOB_AGENT.md](JOB_AGENT.md), [DEDUPE.md](DEDUPE.md) |
| Review drafts or a section by eye | `visual-review` | [LENSES.md](LENSES.md) |
| Why is a product missing, held, a draft, withdrawn, odd | `product-trace` | the shop's files (read only); the codes: [TRANSFORM.md](TRANSFORM.md#held-codes) "Held codes" |
| How many / which products (by status, hold, brand, section, store state), the ledger, the store's counts, what a prepare changed | `shop-data` | [OPERATIONS.md](OPERATIONS.md#reading-the-shop-by-hand-2026-11-16) "Reading the shop by hand" |
| Activate, withdraw, hold, restore, reprice, back up | `store-actions` | [PUBLISH.md](PUBLISH.md), [PRICE.md](PRICE.md), [OPERATIONS.md](OPERATIONS.md) |
| Fix one product's brand, title, price, section, description | `fix-a-product` | the stage's doc below |
| A dictionary backup is due, a term or brand wrong for many products | `dictionaries` | [TRANSLATION.md](TRANSLATION.md#2-dictionaries) "2. Dictionaries" |
| Something broke in the files: a crash, `LedgerError`, `shop is busy`, a restore | `recover-state` | [OPERATIONS.md](OPERATIONS.md) "Shared files", "Backup"; [JOB_AGENT.md](JOB_AGENT.md) |
| The extension disconnected, a listing tab hangs | `extension` | [server/docs/EXTENSION.md](../server/docs/EXTENSION.md) |
| A new Mac, or nothing starts | `setup-machine` | [SETUP.md](../SETUP.md) |

The scripts' topics, each in its own doc, each with a skill to read first:

| Doc | Skill | When to read |
|---|---|---|
| [COLLECT.md](COLLECT.md) | `collect-api` | Calling the API: product details, options, photos, the listing screen, reviews, examples, answer types, harvests |
| [JOB_AGENT.md](JOB_AGENT.md) | `run-a-job` | Running or watching `job.py` (one product per iteration, `new` + `run` or `scroll`), step by step: before, start, watch, stop, after |
| [DEDUPE.md](DEDUPE.md) | `run-a-job`, `dedupe-rule` | Duplicates (`dedupe.py`, `job.py --dedupe off\|log\|on`): a job's events and what to do, `--pairs`, `--report`, the rule |
| [TRANSFORM.md](TRANSFORM.md) | `transform` | The transform (collected -> prepared), the held codes and what to do on each, record types |
| [PACKAGE.md](PACKAGE.md) | `transform` | Package weight and size (the five fields), category defaults, confidence, the description images' OCR, the images' text for `describe.py` |
| [TRANSLATION.md](TRANSLATION.md) | `translation` | `translate.py`, the dictionaries, the prompts, review cleaning, the quality check |
| [PLACEMENT.md](PLACEMENT.md) | `placement` | The shop's sections, the last stage before Shopify (`placement.py`) |
| [DESCRIBE.md](DESCRIBE.md) | `describe` | The English description (`describe.py`) and its model |
| [PRICE.md](PRICE.md) | `price` | Why a product is priced X, the price rule, the delivery tariff, repricing (`shop_pricing.py`, `reprice.py`) |
| [PUBLISH.md](PUBLISH.md) | `publish` | Publication to Shopify (`publish.py`), the payload, withdraw / hold / restore / activate, the Shopify roadmap |
| [SWEEP.md](SWEEP.md) | `shop-data` | Old model answers (titles, option names, descriptions) a new rule, dictionary or prompt judges wrong: `sweep.py`, its checks, what to do on each |
| [OPERATIONS.md](OPERATIONS.md) | `operations` | Running the scripts, tests and checks, the backup, shared files, conventions |
| (none) | `release` | Cutting a release (developer): VERSION, check.sh, tag, push, the state backup |

Also: [ONBOARDING.md](ONBOARDING.md) (a new category or shop, skill `new-category-or-shop`),
[LENSES.md](LENSES.md) (visual review, skill `visual-review`), [SELLER_DATA.md](SELLER_DATA.md) (what sellers write); developers: skills
`seller-pattern-rule` (a seller pattern -> rule -> test), `prompt-change` (a model prompt), `api-error-triage` (an
API or job error), `dedupe-rule` (a change to the duplicate rule), `live-smoke` (the live smoke, `smoke_endpoints.py`);
questions over many products, read only: `shop-data` (OPERATIONS.md, Reading the shop by hand).

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
- `requirements.txt` holds `requests` and `Pillow` (WebP for the photos), `rapidocr` + `onnxruntime` (the
  description images' OCR), `anthropic` + `openai` (the model APIs), `tenacity` (`job.py`'s waits), `zstandard`
  (the backup) and `mypy`, so scripts run on a machine without Chrome or patchright. The offline tests also need
  `pytest`, which the server venv has.

## Files

Every `scripts/*.py`, by stage; a test of one module is in the pattern row at the end.

| File | Purpose |
|---|---|
| **Setup and checks** | |
| `check_setup.py` | Setup checklist, read only, one line per check (OK / WARN / FAIL, exit 1 on a FAIL): local + running server + extension; `--live` adds one plain-HTTP and one Chrome call to Naver and a read-only Shopify token check; `--notify` one test POST to `NAVER_NOTIFY_WEBHOOK`; `--no-server` local only. A new requirement gets its check here in the same commit (SETUP.md) |
| `check.sh` | Offline, before a commit: the server suite, the scripts suite and mypy, each in its own process; prints the three results, non-zero exit when any fails |
| `smoke_endpoints.py` | Live smoke: `/health` plus 11 endpoints (all but `/products/specs`, `/products/page` and `/products/reviews/selected`), one at a time. Networked. |
| `captcha_watch.py` | Reports a Naver captcha the adapter waits on (reads `/captcha`): one line per new captcha / solved / timed out; independent of any collection |
| `notify.py` | A job's stop / done notice to the owner (`job.py` main, 2026-11-16): a copy of `server/notify.py` (`NAVER_NOTIFY_WEBHOOK`, else a macOS notification, never raises); `conftest.py` replaces it in every test |
| **The API and collection** | |
| `naver_api_client.py` | `NaverApiClient` (`get`, `pages`, `health`) and `ApiError` |
| `naver_types.py` | The API's answers as TypedDicts (no runtime code), from real answers captured live 2026-11-01 (`fixtures/*.json`) and the server's parsers; a shape change updates type + fixture together (COLLECT.md, Response types) |
| `naver_images.py` | Downloads the photos the API linked (gallery, review photos, avatars) from Naver's image CDN with plain HTTP and saves them as the store's WebP (see COLLECT.md, Product photos) |
| `image_prep.py` | The WebP preparation, one algorithm for every store: size, bytes, metadata, checks (no network) |
| `naver_variants.py` | Which variants to collect: free ones by default, paid ones when the operator turns `paid` on; sold-out rows kept and marked (see COLLECT.md, Product options) |
| `shop_stores.py` | Our Shopify stores (`StoreId` enum + publisher / site + Shopify values), picked by `SHOP_STORE` |
| `listing_filter.py`, `listing_exclusions.json` | The listing screen: which rows to open, a reason code for each left out (rental stop words from the naver-harvester) |
| `listing_title_rules.json` | Ours: per Naver category, the title words of what the shop's section does not sell; the screen drops such a row as `title:<code>` (listing_filter) |
| `shopify_catalog.py` | The "already in the shop" check: every product's source key from the store's Admin API (read only); `ShopCatalog.paged` pages any connection; the CLI reads the store by hand: `show <ref>`, `counts`, `vendors`, `collection <handle>`, `dump --out F` (OPERATIONS.md, Reading the shop by hand) |
| `collect_product.py` | One product of a listing as one collected line (example_99's per-product step, shared with `job.py`): details, chosen reviews (`review_pick`), specs (by the product's name first, then the listing's query; 2026-11-05: 27 of 40 cards not on the listing search's first page), variants, the five package fields, photos; -> `collect_guard.Outcome`, or `SourceStopped` on a 409 / 410 / 503 / 502 "blocked the request" / refused CDN |
| `collect_guard.py` | The run rules around one product: one retry, then deferred; stop on a wall; stop on a repeated defect |
| `deferred_log.py` | The shop's journal of deferred products (append-only); CLI `list` / `allow <key> --by` |
| `review_pick.py` | A product with more than `KEEP` chosen reviews keeps the best by what they say (score: text quality, full text, helpful votes, photos; sponsored ones not taken), photos capped per review and per product, before any photo is fetched (the owner, 2026-11-11); recorded as `reviews.picked` |
| `product_page.py` | Saves a product page as the owner's Chrome renders it (`/products/page`): page.html, the page's own answer, meta; for developing parsers and checking collected data |
| `keep_run.py` | Keeps a collection run (example_99 output) per shop, byte for byte, read-only (see TRANSFORM.md, Transform) |
| `harvest_listing.py` | Full listing of store product links for a keyword + category, price-sliced, resumable |
| `example_search_harvest.py` | Template: search, classify the cards, fetch details, write resumable JSONL |
| `example_NN_*.py` | Runnable examples, one API topic each (see COLLECT.md, Examples): 01 health, 02 search, 03 product details, 04 reviews, 05 store, 06 datalab, 07 listing then details, 08 product full, 09 listing then specs, 10 known products specs, 11 reviews full, 12 reviews selected, 13 product images, 14 product options, 15 description collect (one golf set with its description images, prepared), 99 full details (a category's products, the one to grow) |
| **The job and duplicates** | |
| `job.py` | A job (JOB_AGENT.md): one shop, one listing query, one product per iteration from the listing to prepared, translated (the default since 2026-11-08), placed and published with `--publish` (`--describe` writes the description first), resumable; `new`, `run`, `scroll`, `status`, `activate`, `report`, `where`, `watch`; files under `scripts/output/jobs/<job id>/` |
| `job_report.py` | Read only, no lock: a job's events read back for `job.py report` (counts, reasons by code, held, cost, stops, waits; `--table` a row a key), `where` (one product across the jobs) and `watch` (returns with an exit code when the owner must hear something: every Nth published, stop, waiting, captcha, reopen, done, no runner) (JOB_AGENT.md, 3. Watch) |
| `dedupe.py` | Duplicates (the owner, 2026-11-15): the rule (title key, photo / variant confirmation, grade then reviews) and the index `job.py --dedupe log` / `on` uses after collect; `--report <shop> [--category]` lists the duplicate groups already in the store, best first (members joined by title words only marked), `--pairs <shop> --job <id>` draws a job's pairs side by side with an index.tsv. Read only, offline (DEDUPE.md) |
| **Transform and package** | |
| `transform.py`, `transform_shops.py`, `run_transform.py` | The transform: kept runs -> prepared products per shop (shared rules, per-shop rules as data, the CLI; `--diff`: what the run changed, `--shops-root` a copy) |
| `prepared_diff.py` | Read only, offline: two `prepared/products.jsonl` product by product (status, held, notes, brand, title, price, variants, package, images, other), `key<TAB>change<TAB>field<TAB>old<TAB>new`; `--published-only`, `--keys-out F` (TRANSFORM.md, What a rule change changed) |
| `shop_types.py` | Our own records as TypedDicts (no runtime code, checked 2026-11-16 over the golden fixtures and the shop's files): `PreparedProduct`, `LedgerRow`, `JobMeta`, `CollectedLine`; a shape change updates its type in the same commit |
| `attributes.py` | Neutral attributes the transform writes to `product.attributes` (gender with its evidence: the variants, the 성별 row, the title; the listing query only flags `listing_disagrees`). A new kind of split is a new `Attribute` (data) |
| `brand_fallback.py` | Run-level: a brand for every prepared product that states none (a brand of the shop in the title, a dictionary brand in the title, 원산지's importer, the images' text, else 노브랜드; note `brand_fallback`) |
| `review_clean.py` | The reviews sanitized in the transform: decoration out, the Korean purchase cut, empty reviews dropped (see TRANSFORM.md, Transform) |
| `description_clean.py` | The seller's boilerplate out of a description's text and images (policy blocks, phones, contacts, greetings, promos, store claims, banners by file name or link), each rule from a real case (research 2026-11-06, 40 golf sets of 50002788, false positives checked on 46 more); pure, offline |
| `spec_variants.py` | Spec rows vs the sold variants (material, count, contradiction, composition, model year, driver loft) and the title words that name one variant: a row is dropped, kept, or bound to the variants it fits, each with its note (research 2026-11-06); pure, offline, no AI |
| `shared_images.py` | Run-level: store-wide description banners (the same image opening or closing most listings of one store) moved to `description_dropped`, note `description_shared_images` (thresholds from 99 products of three runs, 2026-11-07) |
| `package_measures.py`, `category_measures.json` | Five shipping fields per variant: the seller's values, else the operator's category averages; the table also holds the operator's `baselines` for the composition; confidence 1-5 |
| `description_images.py`, `description_ocr.py`, `description_measures.py` | Optional stage: OCR of the description images (RapidOCR; Naver's CDN and the seller's HTTPS hosts; a worker process per product) into a sidecar per product; the transform reads size / weight from it and from the typed description text (a core for every category + parts profiles by Naver category id): a stated box / weight takes the place of a category default, and a set's other fields are composed from its parts with the operator's baselines, the flat default last (see PACKAGE.md) |
| `description_image_text.py` | The images' OCR rows -> clean Korean blocks (text / table) for `describe.py` (not translated since 2026-11-10); run_transform writes `translation/<product id>/description_images.ko.*` and the flag `product.description_images_text.state` |
| `collected_fixtures.py` | Development, files only: `add <products.jsonl> <product id> ...` / `refresh` the collected fixtures (`fixtures/collected/`) of `test_prepared_golden.py` |
| `make_measures_fixture.py` | Offline, by hand (2026-11-11): a measures fixture (`fixtures/measures/<product id>.json`, empty `expected`) cut from a product's latest collected line and sidecar, sellers' details as "x"; `--recut` keeps the texts and pins; then `UPDATE_GOLDEN=1` and read the diff (R-TEST-5) |
| **Translation and description** | |
| `translate.py`, `translation_dicts.py`, `translation_rules.py`, `translate_keys.py`, `translate_eval.py`, `prompts/` | Translation of the prepared texts (see TRANSLATION.md, Translation): the model stage, the per-kind dictionaries (live / backup), the unit rules, the prompts |
| `describe.py` | The English description for Shopify's `descriptionHtml` (the owner, 2026-11-10): one model request per product, the packet cleaned before and each sentence checked after, the HTML built here; answers in `<shop>/translation/descriptions.jsonl`; a published product only with `--published` / `--only` (DESCRIBE.md) |
| **Placement and price** | |
| `placement.py`, `placement_rules.py` | The last stage before Shopify: prepared products -> the shop's sections (leaf tags, product type, `start_variants`) from the shop's profile (data); unknown / conflict held as `unresolved`. How to add a split: [PLACEMENT.md](PLACEMENT.md) |
| `shop_pricing.py` | The price rule per shop: a variant's cost per item, price and how they were made (`Policy.quote`). fairwardgolf: `landed/2`, delivery, duty and margin inside the price; a shop without the rule: `krw-cost/1`, 1 000 KRW = 1 USD up to a dollar, price = cost. See PRICE.md, The price |
| `delivery_tariff.py`, `delivery_tariffs.json` | The delivery cost of one packed box by a recorded tariff, offline (billable weight, step, fees once per box); the tariffs as data, each traced to a dated capture, with `version` and `history`. See PRICE.md, The price |
| `shopnship_rates.py` | ShopNShip's public calculator (networked, by hand only): `quote` one box, `capture` the grid into a dated file, `compare` a capture with the recorded table. Never in the price path |
| `shopnship_explore.py` | Research tool (networked, by hand only): wide sets of boxes asked of the calculator and compared with the tariff model (`run`, `report`). Never in the price path |
| `reprice.py` | Products already in the store: old -> new prices under the shop's rule (a dry-run table, also a TSV under `publish/`); `--apply` sends them, on the owner's word. See PRICE.md, The price |
| **Publication and the store** | |
| `publish.py`, `shopify_payload.py`, `shopify_admin.py` | Publication: prepared + translated + placed -> the store (productSet, photos, reviews' files, ACTIVE, or DRAFT first for a category not marked reviewed, the website); the payload built offline; the two writing apps. See PUBLISH.md, Publication |
| `publish.py --withdraw` | Takes a published product off the store (DRAFT, nothing deleted) and keeps it from being sent again; the ledger keeps why |
| `publish.py --restore` | Undoes a withdrawal (with `--reason`): ACTIVE again (a draft stays a draft, 2026-11-16), its last published row back in the ledger with no digest, so the next `--only` sends today's data to the same product (2026-11-15: no-brand agency imports back under the shop's name). A title translated under the shop's name ("Fairward Golf ...") takes the brand found later in its place (`shopify_payload.title_vendor`) |
| `publish.py --activate` | A draft (a category not marked reviewed, draft first 2026-11-16) live: ACTIVE, the ledger row again with `store_status: ACTIVE` and `activated`, nothing sent again; repeatable; only on the owner's word after the lens review. A key that is not a published draft: `not a draft here` |
| `job.py activate --job <id> [--dry-run]` | Every draft of a job live the same way (withdrawn ones skipped; `--dry-run` lists them, no store call); prints the `--withdraw` lines of the old copies a draft did not replace (`replace_skipped`: the new one is a draft) and, while the category is not marked reviewed, that `reviewed=True` is the owner's word |
| `store_diff.py` | Read only: what a publication would change in the store, field by field, per published product; the published products that cannot be built now; `--adopt` records `output` for those the store already has. A draft's status is not compared (its update sends none); a draft the store has ACTIVE (activated in the admin by hand) is listed with the `--activate` that records it (2026-11-16). Run it after any change of rules, dictionaries or a new category (ONBOARDING.md part D). About a minute for 2,015 products (2026-11-16: 20+ minutes before; publish.py reads the shop's files once while they do not change, the store is read 50 products a query, 3 queries at a time) |
| `sweep.py` | Read only, offline, no lock taken (refused while the shop is busy): the published products' cached model answers a rule, dictionary or prompt improvement now judges wrong (a title `translate.plan` would ask again, another brand in a title or a description's first sentence, Hangul left, a description `describe.py` would cut, a stale description), and what a resend would change (today's offline build against `publish/sent/`: same, changed by verdict in groups, worse apart: exit 1), live and drafts apart; a table or `--json`, and `shops/<shop>/sweep/latest/` (answers.json, a keys file a check and store state, store.json, `groups/<id>.keys`; `prev/` the run before; `selection/` a narrowed run; `.force` groups: publish skips them by the inputs digest). About 17 s for the shop (SWEEP.md) |
| **Review by eye** | |
| `lens.py` | Read only, offline, by hand: visual lenses, numbered contact sheets for one question each (`section`, `price`, `brand`, `dupes`, `held`, `products`) plus `index.tsv` and `summary.json`, for an agent to look at by eye and prove by number (LENSES.md, skill `visual-review`) |
| `sheet.py` | The contact sheet drawing under the lenses, `review_grid.py`: cards (number, photos, labels, mark, group), grid and rows layouts, the index |
| `shop_view.py` | One read-only view of a shop's files joined by key (prepared, translated, placement, the ledger, collected photos) and a job's events, for the lenses; `resolve` names a product by key, product id, handle or link (0 or 2+ matches: an error listing them), `selected_keys` / `add_ref_flags` give the CLIs `--keys-file` and `--job [--event]`; `shop_view.py key <shop> <ref> ...` prints `ref<TAB>key` (OPERATIONS.md, Naming a product); `show`, `query`, `ledger`, `history`, `check`: the shop's files by hand, TSV or `--json` (OPERATIONS.md, Reading the shop by hand) |
| `make_shop_fixture.py` | Offline, by hand: copies a real slice of `output/shops/fairwardgolf` (16 products, every file's rows, the ledger's history, two payloads, collected lines cut short) and two jobs into `fixtures/shop/` in the real layout, `cases.json` saying which key is which case; paths made relative, draft preview keys removed (OPERATIONS.md, The shop fixture) |
| `make_lens_fixture.py` | Offline, by hand: cuts the lenses' real-record fixture (`fixtures/lens/cases.json`) from `scripts/output`, the cases listed with why (LENSES.md, Tests) |
| `review_grid.py` | Read only, offline, by hand: numbered sheets of the published products' first photos and an index (number, key, title, handle, admin link), for a look by eye after a run (JOB_AGENT.md, 5. After); draws through `sheet.py` |
| `review_suspects.py` | Read only, offline: the published products of a category that may not be what its section sells (one club, 2-3 clubs, used, junior or accessory words), with key, store id, handle, price and reason; a table and a CSV for the owner's review after a lenient run (JOB_AGENT.md, 5. After) |
| **The shop's files** | |
| `shop_files.py` | The shop's shared files written and read safely: `write_atomic` (a rewritten file through `<path>.<pid>.part` and a rename), `append_line` (one write of whole lines, a line end first when the file lacks one), `read_jsonl` (a bad line is `LedgerError` naming `<path>:<n>`; a cut-off last line of an append-only file ignored with `tail_ok`), `shop_lock`, `ensure_free` (a read tool's busy check: no lock taken, nothing written; `sweep.py`) (see OPERATIONS.md, Shared files) |
| `state_backup.py` | Offline, by hand: the backup of `scripts/output`, `server/output` and `research/` (plans outside git, with the state) into tar + zstd archives by phase outside the repository (state, photos, description images in parts, server pages, old runs), `MANIFEST.json` with sha256, `RESTORE.md`; `--dry-run`, `--verify`, `--restore` into an empty folder. Reads the sources only (see OPERATIONS.md, Backup) |
| `output/` | Run output (`output/<run>/products.jsonl`, `listing.jsonl`), gitignored |
| **Tests** (offline: `conftest.py` fails a network attempt) | |
| `test_<module>.py` | Offline tests of `<module>.py`, every outside service faked (a fake CDN, Admin API, GraphQL and staging bucket, calculator, model, API client); `<module>` is one of brand_fallback, captcha_watch, dedupe, deferred_log, delivery_tariff, describe, description_clean, description_image_text, description_images, description_measures, description_ocr, harvest_listing, image_prep (the WebP preparation), job, listing_filter (the screen), naver_images, naver_variants, package_measures (the shipping fields), placement, product_page, publish, reprice (the repricing flow), review_clean, review_grid, review_pick, review_suspects, run_transform, shared_images, shop_files, shop_pricing, shop_stores (every `StoreId` has a profile, `SHOP_STORE`), shopify_admin, shopify_catalog (the shop check), shopify_payload, shopnship_explore, shopnship_rates (a fake calculator, a saved capture), spec_variants, state_backup, store_diff, transform, translate, translate_eval. The description images' tests: the stage (fake fetcher and engine), the slicer / rows, the guess and the merge (real OCR rows). Also `test_shop_lock.py` (`shop_files.shop_lock`), `test_deferred_log.py` (the journal, with the `collect_guard` run rules), `test_dedupe.py` (with `job.py --dedupe`), `test_publish.py` (the payload's variant prices and metafields too), `test_run_transform.py` (the run-level steps; the per-product prepare is `test_transform.py`) |
| Tests on real data | Real rows, quotes or links, product ids beside them: `test_naver_variants.py` (a product with paid and sold-out variants), `test_transform.py` (`fixtures/collected_fairwardgolf.jsonl`), `test_placement.py` (the gender attribute and placement: the 50 fixtures, the rules case by case), `test_description_clean.py`, `test_spec_variants.py` (40 golf sets, 2026-11-06, run 40b; must-not-match cases too), `test_shared_images.py`, `test_run_transform.py` (store 100568453's banners), `test_description_measures.py` (real OCR rows), `test_dedupe.py` (fairwardgolf patterns, 2026-11-15), `test_describe.py` (six real products, `fixtures/describe/`), `test_delivery_tariff.py` (the captures and explorations replayed); Pillow-made photos in `test_naver_images.py`, `test_image_prep.py` |
| `conftest.py` | The folder's tests never reach the network: a connection attempt fails the test; no test sends a notice (`notified` stands in for `notify.notify`); `shop_fixture` gives a test a tmp copy of `fixtures/shop/` |
| `test_shop_fixture.py`, `test_shop_view_refs.py` | The shop fixture parses (`read_jsonl`) and matches the record types, each case is what `cases.json` says; naming a product (`shop_view.resolve`, keys files, `--job`) and the CLIs that take refs (publish's store actions only with `--dry-run`, every store client failing the test) |
| `test_shop_view_cli.py`, `test_job_report.py`, `test_prepared_diff.py`, `test_shopify_catalog_cli.py` | The read tools on real data: `shop_view.py` show / query / ledger / history / check and the shared pieces (cell, keys file, time, gid) on the shop fixture; `job.py report / where / watch` on its two jobs (a fake clock); `prepared_diff.py` on `fixtures/prepared_diff/` (two real versions of 8 products); `shopify_catalog.py`'s CLI on the store's real answers (`fixtures/shopify/answers.json`) through a fake session |
| `test_naver_api_client.py` | The client and the harvest classifier, against the server's limits and search fixture (the one borrow of server modules, Boundary above) |
| `test_naver_types.py`, `test_shop_types.py` | The saved API answers (`fixtures/*.json`, 2026-11-01, lists trimmed to 5) against `naver_types.py`; the golden prepared products and their collected lines against `shop_types.py`; strict both ways |
| `test_docs_held_codes.py` | Offline: TRANSFORM.md "Held codes" table against the codes the transform, placement and dedupe produce (an AST scan of the source) |
| `test_sweep.py` | Offline: `sweep.py`'s checks, each on a real bad and a real good case (the shop fixture, the two-brand scan's prepared fixtures, live answers quoted with their ids); review rows never flagged, the run writes only under `sweep/`, the busy refusal, an empty selection, SWEEP.md's checks and guards tables against the code; the store part: changed / same equal to what `publish_one` sends / skips on a fake Admin, each guard on a real pair, an improvement, the store's vendor spelling, withdrawn and no-baseline keys in no group, one key one group, drafts and categories apart, each text check's improvement, `.force` keys (a store spelling, a payload change without its version) that `publish_one` skips unforced, a selection written apart, `prev/` new and gone, exit codes |
| `test_lens.py`, `test_lens_fixture.py` | `sheet.py`, `shop_view.py` and `lens.py`; then the lenses on `fixtures/lens/cases.json` (2026-11-15) and on torn files, missing photos, unknown products, a job with no events (photos drawn in a tmp folder) |
| `test_prepared_golden.py`, `collected_fixtures.py` | Regression: collected lines of real products (`fixtures/collected/`, from the server's saved-page fixtures) through the transform must equal `fixtures/prepared/`; `UPDATE_GOLDEN=1` rewrites them after a deliberate change, read the diff. Added when the owner asks, or from products checked in test runs without asking (server DEVELOPMENT_RULES R-TEST-5, the owner 2026-11-06) |
| `test_measures_fixtures.py` | Regression for the five package fields: 17 real golf sets cut down to what the measures code reads (`fixtures/measures/<product id>.json`: title, 상품정보 rows, variants' option words, add-ons, typed lines, the OCR rows with their confidence, the server path's candidates; sellers' phones, addresses and shop names are "x") through `package_measures.variant_measures` and the transform's hook with the real `category_measures.json`, against the fields each variant must get (value, source, confidence 1-5, how, parts), checked by hand against the product's lines (`checked`; where a fixture's `note` says "approximate" the value pinned is the rule's present approximation, not the page's figure). One test per product, one that the set covers every level and source. `UPDATE_GOLDEN=1` rewrites the expected part: read the diff against the products' lines |
| `test_shop_pricing.py`, `fixtures/pricing/` | Regression for the price rule: real products cut down to what the rule reads (the variants' prices, the delivery in Korea, the package fields), with the cost, price and breakdown each variant must get; `UPDATE_GOLDEN=1` rewrites the expected part after a deliberate change of the rule or the tariff: read the diff |
| `fixtures/shopnship/` | The calculator's answers of 2026-11-11: two grid captures (the second is the tariff's source), two explorations and the second round's rows; the backups a new capture is compared with |
