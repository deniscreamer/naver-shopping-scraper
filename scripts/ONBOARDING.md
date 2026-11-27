# A new Naver category or a new shop (tenant)

Where to add what, so that a new Naver leaf category in a shop, or a new shop, runs through the whole pipeline
(collect, transform, OCR, translate, describe, place, price, publish) without silent gaps. Agents: the
`new-category-or-shop` skill (`.claude/skills/`) walks through this file. The rows' ids (A1-A15, B1-B10, C1-C11,
L1-L10) are cited from code and other docs: keep them. When was what written: [History](#history).

## How to use

| Task | Section |
|---|---|
| A category in an existing shop: what stops without it | [A. Required](#required) (A1-A6) |
| What works without, but worse | [A. Quality](#quality-works-without-these-but-worse) (A7-A15) |
| A new shop (tenant) | [B](#b-a-new-shop-tenant) (B1-B10), then A for each of its categories |
| Golf or `fairwardgolf` in shared code: decide before the first run | [C](#c-golf-or-fairwardgolf-in-shared-code-decide-before-the-first-run) (C1-C11) |
| The first run, in order | [D](#d-the-order-of-a-first-run) |
| The pilots of 5 and 30, their review, fixes and report | [E](#e-the-pilot-cycle-5-then-30-then-the-owner) |
| What earlier categories did to the rest of the shop, and the fix | [Learned](#learned-on-the-first-new-category-50002787-2026-11-11) (L1-L10) |

First, the agent's package defaults (A1, [E1](#e-the-pilot-cycle-5-then-30-then-the-owner)) and its proposed values
for A2, A3, A5 with numbers, the owner's yes on those (for a shop B1, B2, B6 are the owner's). Then the first run
(part D, the pilot cycle E) prints, and you:

| Command | Result | You |
|---|---|---|
| `SHOP_STORE=<shop> .venv/bin/python scripts/job.py new --query "..." --category <leaf id> --count 5` | `stop: no category_measures.json row for <id>: write it (ONBOARDING.md E1)` (exit 2) | A1 |
| the same | `category_mismatch` in the screen counts | a wrong id: use the leaf id (below) |
| `job.py run` | `stop: prepare: ShopRulesMissing` | A2 (a new shop: B4) |
| `job.py run` (a job made with `--publish`) or `publish.py <shop>` | a product `failed` at stage publish / `held` with `Untranslated: ...` (a text the product needs has no English) | the translation (skill `translation`): [TRANSLATION.md](TRANSLATION.md#how-to-use), status `untranslated`: fix the brief, rule or dictionary entry, then `translate.py <shop> --only <key>` |
| `.venv/bin/python scripts/placement.py <shop>` | `no_profile` or `unresolved` in the counts; a new shop without a profile: `PlacementRulesMissing` | A3; B5 |
| `.venv/bin/python scripts/publish.py <shop> --dry-run` | builds only what is ready, translated and placed; payloads in `shops/<shop>/publish/payloads/<id>.json` | read the price breakdown (D step 5); the pilots publish DRAFT on their own (part E); activation and any resend of a live product only on the owner's word |
| `.venv/bin/python scripts/store_diff.py <shop>`, then `translation_dicts.py status` | the published products a publication would change, those that cannot be built now; the new dictionary entries | each product is the owner's to decide; read every new entry before the dictionaries' backup (D step 6) |

After the first run of a category, also read by hand what the [Learned](#learned-on-the-first-new-category-50002787-2026-11-11)
rows ask: its vendors and its cheapest and dearest prices (L7); its no-brand, agency and dearest products (L8);
`review_grid.py`, then its new brands against the makers' own Latin spelling (L9); the held products' titles, not
only their codes (L10). `store_diff.py` goes over the **whole shop**, not only the new category (L8).

## Rules for every row

Each row says what happens **without** the step:
- **stops**: an exception or an exit 2, named;
- **silent**: it runs, but the result is wrong and nothing says so;
- **weaker**: a generic fallback, lower quality.

**One id everywhere.** Use the Naver **leaf** category id, the same string in every file below. Collection keeps
a product only when its page's category equals the run's exactly (`collect_product.py`, `listing_filter.Screen`), or
is one `listing_title_rules.json` `together` takes with it (2026-11-21: 50002798 and 50002799, one section; such a
row is screened by its own category's rules and collected as its own category, `job.category_of`; dedupe compares
them as one, `dedupe.dedupe_category`).
A parent or a near id collects nothing: every product ends `category_mismatch`, and only the counts show it.

**Who gives the values.** The package defaults (A1) are the agent's (the owner, 2026-11-26): measured from the
probe's cards and the products' pages, priced, and refined on the pilots of 5 and 30 from the real products (part E);
never a default left as it was written. Prices, coefficients, sections and the paid-variant choice are the owner's
decisions: the agent proposes them with numbers, the owner says yes; a baseline (a set in a container,
PACKAGE.md) stays his. None is made up; each is written down with its
date and who decided.

## A. A new category in an existing shop

### Required

| # | Where | What | Without it |
|---|---|---|---|
| A1 | `scripts/category_measures.json` | A row with `category_id`, `category_name`, `fields` (low / central / high of the 5 package fields), `reliability`, `approved_by`, `approved_at`, `basis`. Optional: `plausible`; `baselines` (only a set of like items in a container; all of them or none); `kinds` (a category that mixes kinds of very different size, e.g. 50002787: single clubs and sets: each kind its own defaults, chosen by title and variant words, `package_measures.default_kind`; a count kind may carry `lofts`, e.g. 50002783 two_wedges); `compose_by_count` (50002783: a set's weight from its clubs' labelled weights, PACKAGE.md). Before writing it, price the central box (`shop_pricing.POLICIES[shop].quote`) on a cheap and a dear product of the listing: at level 1 (x2.50) one default box for a 25,000 KRW putter and a set came to $699. A row changed later reaches the products already collected when they are prepared again (`current_defaults`; kept runs are read-only, never edit them), then `publish.py --only` them. Append it last, after the existing rows (50002788 stays first: tests read `rows[0]`), raise `version` and give the row `defaults_version` equal to it (a row whose fields or a kind's numbers change later gets the new version there too; 2026-11-18: the other rows' restamped defaults keep theirs; 2026-11-25: a kind's words alone, no number moved, keep it, as a band does: 50002816 at table version 20), then update the pin in `test_package_measures.py::test_baselines_block_is_optional_and_the_operators`. | **stops**: `job.py new` exits 2 ("no category_measures.json row"); `CategoryDefaultsMissing` |
| A2 | `scripts/transform_shops.py` `RULES[shop].categories` | `CategoryRules(paid_variants, paid_addons, description_images, agency_needs_brand, sets_only, wedge_sets, gift_axis_out, no_choice_out, composition, reviewed)`, with the owner's reason in a comment (`reviewed` stays False for a new category, 2026-11-16: its products are created DRAFT until the agent's lens review and the owner's activation; `reviewed=True` with a dated comment only on the owner's word after the pilot; `agency_needs_brand`: a purchase agency's import with no brand is held; off in fairwardgolf since 2026-11-15, the owner: its vendor is the shop's name; `sets_only`: a section of sets, a one-club variant left out and a listing of them held, wedges 2026-11-15; a shop taking 50002783 needs it: `translation_rules.TITLE_RULES` drops the titles' "or single", test_title_rules checks it, 2026-11-16; `wedge_sets`: a section of wedge sets, an iron set or a full set filed under the category held `not_wedge_set`, 50002783 2026-11-16; `gift_axis_out`: a free gift's option axis (사은품 / 증정) left out, one variant per remaining choice, chippers 2026-11-18; `no_choice_out`: an option value saying "no choice" (선택안함, 없음, 필요없음, 선택없음) is no version, its rows go and an axis of nothing else goes, knit cardigans 2026-11-19; `composition`: the fibre rows (spec and notice: 소재, 혼용률, 재질, 섬유의 조성) kept as `product.composition_ko` for a duty by fibre and the description, knit cardigans 2026-11-19) | **stops**: `ShopRulesMissing` in `transform.prepare`; a job stops with `stop: prepare: ShopRulesMissing` |
| A3 | `scripts/placement_rules.py` `PROFILES[shop].categories` | `CategoryPlacement(parent, leaves, split_by, unresolved)` and its `Leaf(handle, product_type)` constants. How: [PLACEMENT.md](PLACEMENT.md) | **silent**: status `no_profile` (in `placements.jsonl` and the counts of `placement.py`), and `publish.py <shop>` skips the product without a word |
| A4 | `scripts/attributes.py` `ATTRIBUTES` | Only when the split is by something other than `gender`: a new `Attribute` | **stops**: `KeyError` in `placement.place` |
| A5 | Price, `scripts/shop_pricing.py` (the shop's `Delivered`) | Check level 1 (2.50) and the duty (12.5%) for this category. The rule is per shop; a category with other values gets a `CategoryPrice` in `Delivered.categories` (its coefficients, its duty by fibre; since 2026-11-19, 50002797), and `quote` / `describe` take the category id. [PRICE.md](PRICE.md) "A category's own rule" | **silent**: priced with golf's coefficients and duty |
| A6 | Shopify admin | A smart collection for every new `Leaf` handle, condition tag = `<shop>:leaf:<handle>`. No code creates collections. Read what exists first (read-only: `ShopCatalog(store)._post("{ collections(first: 100) { nodes { handle ruleSet { rules { column condition } } } } }")`): fairwardgolf already has 36, empty ones included, and the `Leaf` handle is the tag's part, without the `fairwardgolf-` of the collection's handle | **silent**: products are published (DRAFT first, then ACTIVE) but in no section |

### Quality: works without these, but worse

| # | Where | What | Without it |
|---|---|---|---|
| A7 | `scripts/prompts/categories/<id>.md` | The translation brief: what the products are, their terms, how buyers write. Model: `50002788.md` | **weaker**: the base prompt only, and it is golf-worded (C3) |
| A8 | `scripts/review_clean.py` `ASPECTS`, `PRODUCT_WORDS` | The category's review aspects and product words; plus a review fixture corpus `fixtures/reviews/<name>_<id>.jsonl` with its test | **weaker**: reviews rarely rate "full", and shipping-clause cuts keep only the generic product words |
| A9 | `scripts/translation_rules.py` `CATEGORY_RULES` | The category's glued codes, plus exceptions to the general rules (C4) | **weaker**, or **silent** where a general rule misreads the category |
| A10 | `scripts/describe.py` `PROFILES` and `scripts/prompts/describe/<profile>.md` | A profile with its lists (e.g. "What's included") and its brief. Ship the two together | **weaker**: `default` (highlights only). A profile without its `.md` **stops** with `FileNotFoundError` |
| A11 | `scripts/description_image_text.py` `GLOSSARIES` | The fixed Korean -> English terms of the images' text | **weaker**: terms are translated inconsistently |
| A12 | `scripts/description_measures.py` `CATEGORY_PROFILES` | Only a set of like items in a container (its tables of parts); otherwise the core is enough. [PACKAGE.md](PACKAGE.md) "More of the page" | **weaker**: no counts, no container, no composition. Unstated fields fall to the flat default (A1) |
| A13 | Tests | Fixtures from the first checked products: `make_measures_fixture.py` (package), `fixtures/collected` with `test_placement.EXPECTED` (placement), the golden prepared files | regressions go unnoticed |
| A14 | `scripts/listing_title_rules.json` | The category's title words for what its section does not sell (toys, gloves, loose heads, another sport), studied on 300-500 listing titles of the category: every rule checked on all of them, none may drop a product that fits (2026-11-11: 46 of 56 misfits of 50002787 with no false hit). A rule may instead `require` words (groups, one word of each; 2026-11-19, 50002797: a women's word and a cardigan word) | **weaker**: misfits are collected, translated and published; a person has to find them |
| A15 | `transform_shops.py` `CategoryRules.sizes`, `scripts/size_profiles/<profile>.json` (+ `.md`) | Apparel only: the size profile (Korean labels -> US sizes, the size chart). A brand that sizes its own way gets a row with its evidence. [SIZES.md](SIZES.md), skill `apparel-sizes` | **silent**: Korean sizes ("M(90)", "L(55-66)") on the storefront, no size chart |

## B. A new shop (tenant)

| # | Where | What | Without it |
|---|---|---|---|
| B1 | `scripts/shop_stores.py` | `skinsli`, `kyobooks`, `banafish` already exist (publisher and site, `shopify=None`): fill their `Shopify(...)`. Another shop: a `StoreId` member and its `STORES` entry (and the four names pinned in `test_delivery_tariff.py`). The fields: publisher (the tenant's name, also the brand fallback), site, `Shopify(domain, shop_id, api_version, credentials_env, namespace)`. Keep `namespace` equal to the StoreId value (C1, `keep_run.py` folders) | **stops**: `ValueError` unknown store; while `shopify` is None, `job.py new` fails on `assert store.shopify`, and the catalog and publish raise `ShopNotConfigured`. A copied publisher or site is **silent**: every photo's XMP carries it |
| B2 | `.env` (operator), `.env.example`, [SETUP.md](../SETUP.md) | `SHOPIFY_CREDENTIALS_<SHOP>`: the path of a 0600, git-ignored file with `PRODUCTS_API_CLIENT_ID/_SECRET` and `ADMIN_API_CLIENT_ID/_SECRET`. Document the variable (R-SETUP). Never read or print the file | **stops**: `ShopNotConfigured` |
| B3 | `SHOP_STORE` in `.env` for each run | `job.py new` takes the shop **only** from `SHOP_STORE` (default `fairwardgolf`) | **silent**: the job is created for fairwardgolf and screened against its catalog. Only `job.py run` refuses later |
| B4 | `scripts/transform_shops.py` `RULES` | `ShopRules(shop, sku_prefix, krw_per_usd, variant_cap, categories={...})`, then A2 for each category | **stops**: `ShopRulesMissing` |
| B5 | `scripts/placement_rules.py` `PROFILES` | `PlacementProfile(shop, categories={...})`, then A3 | **stops**: `PlacementRulesMissing` (traceback) |
| B6 | `scripts/shop_pricing.py` `POLICIES` and `scripts/delivery_tariffs.json` `shops` | When the price carries the delivery: a `Delivered` rule for the shop and its tariff. The two maps must agree (a test) | **silent**: price = cost = the Naver price at 1 000 KRW = 1 USD, rounded up to a dollar, with no delivery, duty or margin |
| B7 | `scripts/prompts/tenants/<shop>.md` | The shop's brief: who sells to whom, spelling, tone | **weaker**: no shop identity in translation |
| B8 | `scripts/listing_exclusions.json` | Today one file, fairwardgolf's, and only its `universal` stop words are read. A shop of its own needs code to choose the file per shop | **silent**: the rental stop words are fairwardgolf's |
| B9 | The Shopify store | At least one publication (sales channel), one active location, the collections of A6. The theme must read the `custom.*` metafields (reviews, rating, add-ons, text fields) in the formats of [PUBLISH.md](PUBLISH.md) "Metafields" | **stops** at publish (`AdminError`: no publication / no active location); **silent**: the blocks are written but never shown |
| B10 | Tests | `test_shop_stores.py` pins that only fairwardgolf has Shopify values; `test_delivery_tariff.py` and `test_shop_pricing.py` check the shops; `test_placement.py` pins `fairwardgolf:` tags. Update them in the same commit | the suite fails (intended) |

## C. Golf or fairwardgolf in shared code: decide before the first run

These are not keyed by category or shop. Each needs a decision (keep, or make it keyed, which is new code)
before a different kind of product or a second shop is published.

| # | Where | What it does today | Risk |
|---|---|---|---|
| C1 | `scripts/shopify_payload.py` (metafields 484-495, 650-682, `MANAGED`), `scripts/transform.py:161` | Our own metafields are written under the literal namespace `fairwardgolf` (and its `schemaVersion` names), not under `store.shopify.namespace`. The SKU hash is `fairwardgolf-sku/v1` | **New shop: fix first.** The catalog and `handle_owner` look in `<namespace>.source_offer_id`, find nothing, and publish duplicates with a `-2` handle |
| C2 | `scripts/translation_dicts.py`, `scripts/dictionaries/` | Since 2026-11-11 every kind but the brand is per Naver category (`dictionaries/<category id>/`): a new category starts empty and pays the model once for its option, spec and add-on texts. The brand dictionary stays the shop's, and the whole brand list goes with every request that asks a brand | read the new category's entries before its first backup (L4) |
| C3 | `scripts/prompts/translate_system.md`, `translate_fix.md`, `describe_system.md` | The base prompts are golf-worded (caddie bag, flex and loft codes, "an American golfer") | move the golf parts into `prompts/categories/50002788.md` and make the base generic before a non-golf category |
| C4 | `scripts/translation_rules.py` `_RULES` | General rules for every category: `N호` -> "Size N", `N번` -> "#N", `N도` -> "N°". No per-category switch-off | wrong for books (issue numbers) or cosmetics (shade numbers) |
| C5 | `scripts/spec_variants.py` (`_GENERIC_WORDS` and the fact checks), `scripts/transform.py` few-pieces notes and the `_image_measures` regexes (club kinds, flex, ladies) | Golf set words and rows | false notes; with `description_images` on, misread counts |
| C6 | `server/naver_shopping/measures.py` (`SET_NAME`, `SET_PARTS`, `SIZE_SKIP`) | In a "세트" product, a weight under 1 kg is taken as a part | a cosmetics or cookware set loses its stated weight, and the flat default fills it. A server change: [DEVELOPMENT_RULES.md](../server/docs/DEVELOPMENT_RULES.md) |
| C7 | `scripts/shopify_payload.py` `GALLERY_MAX_GREEN`, `_COUNTED_RE` | Buyers' photos that are mostly grass green are dropped; title cuts know golf counts and a few units (pcs, sets, cm, g, kg, in, oz), not ml, L or other categories' counts | green products lose review photos; a title can end in a bare number |
| C8 | `scripts/description_measures.py` (the closed-list regex in `read_rows`, `composition_count`'s 아이언) | Golf literals inside the profile branch, not `Profile` fields | a second profile gets no closed list or composition count |
| C9 | `scripts/description_image_text.py` `INSTRUCTIONS`, `_STORE`; `scripts/brand_fallback.py` (`골프` after a one-syllable brand); `scripts/description_clean.py` banner names | Golf wording and golf shops' banners | minor |
| C10 | `scripts/example_99_full_details.py`, `example_15_description_collect.py` | `QUERY` and `CATEGORY_ID` constants | use `job.py new --query --category` instead |
| C11 | `placement.start_variants` | Computed but not written by `shopify_payload` (no `custom.category_start_variants`) | a split category opens every section on the same variant |

## B0. Probe the listing: the analysis phase (before the rules, before the pilot, after every screen change)

The gate (the owner 2026-11-22): no row of part A is final and no pilot runs before a probe of the owner's query and
its candidates has been looked at and its `decision.md` written; the pilot's own screen counts are no substitute
(the men's tops pilot of 2026-11-22 found its required word 긴팔 too narrow only after 35 cards were dropped).

The owner, 2026-11-22: the flow probes the listings (the queries, the words in the titles, the page's filters, the
adjacent category ids); the agent decides; it asks the operator only where it is unsure. The tool:
`.venv/bin/python scripts/listing_probe.py --category <leaf> [--leaf <section>] --query "<owner's query>" --query
"<candidate>" ... [--batches 3] [--alt-rules FILE]` (no job may run: it reads the listing the jobs read, in the
owner's Chrome, sorted 리뷰 많은순). Report: `scripts/output/probes/<category>-<section>-<UTC>/report.md`.

| Read | Where | Use it for |
|---|---|---|
| The rows by category, the sorted and the default totals | "by category", "rows read" | the query stays in the leaf; the size of the sorted listing (the sort drops products with no reviews' ranking) |
| The page's category tree (`filters.categories`) | "adjacent leaves" | the leaves the query reaches: the same goods under another id (50002798 점퍼 / 50002799 재킷; men's golf knits under 50002797 니트) |
| The screen's reasons with example titles | "reasons" | a rule that drops what fits (read the examples), a kind the query brings that the section does not sell |
| `--alt-rules` | "alt rules: adds / drops" | a wider or narrower rule measured on the same titles before it is written |
| The page's attributes (`filters.attributes`) | "the page's attributes" | what sellers mark (긴팔 / 반팔, the neck, the fibre): words for the screen; a filter of the listing itself where offered (only some queries have it) |
| The kept rows' reviews | "kept reviews" | the quality the query brings at its top |

The page's other places, checked 2026-11-22 and not worth a probe: the cards carry their category and reviews but no
attribute; the colour, delivery and benefit facets say nothing about the kind of product; `/products/search` (ns-portal)
is another surface, in the default order, with catalog cards the jobs never read (its price bands still show the
spread of the whole category).

Look before deciding (the owner, 2026-11-22: the agent judges itself whether its probes are good and fit the
category, the adjacent leaves first): every query has contact sheets of its listing cards (`q<n>/sheet*.jpg`, the
cards' own photos, grouped: "kept" grey, each screen reason red, each other leaf blue where the screen would keep it).
Read every sheet with the Read tool, then check a doubt by its `q<n>/index.tsv` line (title, category, reviews, link):
- "kept": every card the section's kind? A misfit there is a missing word of a screen rule;
- each reason group: any card that fits? Then that rule drops what the section sells (`--alt-rules` the fix);
- each other leaf, blue cards: the section's goods? The leaf is a `together` candidate; red cards there show what
  else it holds; a leaf the section takes already (`together`, or `together_leaf` for the probe's `--leaf`) counts
  as the category, screened by that leaf's own rules for the section (2026-11-22);
- a probe is good enough when the kept group is the section's kind at a glance and its share and reviews match the
  report; else probe another query or more batches before deciding.
Write the verdict in the probe's folder, `decision.md`: per query take / drop / add as a job's query; per adjacent leaf
together / own section / leave; per rule keep / widen / narrow; each with its numbers and the cards looked at.

Decide (the agent), from the flags (`attention`) and the sheets:
- `kept_low` (under half kept) or `requires_drops` (a required group drops a quarter): read the examples; widen the
  group with the garment words the titles use and measure it with `--alt-rules`; or add a query that brings more of
  the section (2026-11-22: 남성 골프 긴팔 카라티 kept 72 of 96, the owner's 가을 긴팔 티셔츠 46 of 97, its top summer
  base layers);
- `adjacent_category` (another leaf holds a fifth of the rows and its titles pass the screen): a `together` leaf when
  the section is the same and the leaf's other goods are kept out by the screen; a section of its own otherwise;
- `off_category`: the query belongs to another leaf: drop it, or probe that leaf;
- `attribute_filter`: note the attribute's words in the screen; the listing filter itself is not built.
Ask the operator only when a choice changes what the shop sells, beyond the probe's evidence: a new section or a
leaf feeding a reviewed category's other section, a required word of the owner's that drops what fits, a query of
his to replace.

## D. The order of a first run

0. Probe the listing (B0) with the owner's query and two or three candidates; write the title screen (A14) from it.
1. The package defaults (A1) yourself (E1); propose A2, A3, A5 with numbers and take the owner's yes (B1, B2, B6 for
   a shop are his). Write each down with the date and who decided.
2. Add the required rows (A1-A4; B1-B6). Do the quality rows the category needs (A7-A12). Decide on C.
3. `.venv/bin/python -m pytest scripts -q`, then update the registry tests (A1 `version`, B10).
4. A small job ([JOB_AGENT.md](JOB_AGENT.md)): `SHOP_STORE=<shop> .venv/bin/python scripts/job.py new --query "..."
   --category <leaf id> --count 5` reads and screens the listing only (a new category is not marked `reviewed`: with
   `--publish` its products go DRAFT, and `review due` is printed from 20 drafts: JOB_AGENT.md, Draft first). `category_mismatch` in its screen counts means
   a wrong id. Then `job.py run` collects, reads the images and prepares. `stop: prepare: ShopRulesMissing` means
   A2. `Untranslated` means the translation. OCR `off` is the owner's choice (`description_images=False`), not a
   missing rule.
   Cheap, popular categories carry many reviews: 50002787 scanned a median 134 reviews a product (sets: 1) and
   kept 19-20 with 20-36 photos, so collection took 47-186 s a product against 45-65 s. Since 2026-11-11 a product
   with more than 8 chosen reviews keeps the 8 best, 3 photos each, 12 in all (`review_pick`).
5. Read every product of the pilot by hand (E3): package fields and confidence, title, description. Run `placement.py <shop>` and check
   that nothing is `no_profile` or `unresolved` (A3). Then run `publish.py <shop> --dry-run`: it builds only what is
   ready, translated and placed. Read the price breakdown in `shops/<shop>/publish/payloads/<id>.json`: the
   variant's `fairwardgolf.price` and the product's `fairwardgolf.pricing`; the namespace is literal, see C1. The
   pilots publish DRAFT on their own (part E); activation only on the owner's word.
6. **What the new category did to the rest of the shop.** First `sweep.py <shop>` (offline, seconds: the old
   products' answers and groups a resend would send, worse 0; [SWEEP.md](SWEEP.md)), then
   `store_diff.py <shop>` (read only): the published products
   whose store data a publication would change, field by field, and those that cannot be built now (an untranslated
   paid variant, a lost placement: L1). Then `translation_dicts.py status`: read every new entry before the
   dictionaries' backup into git (L4; not the state backup, `state_backup.py`). Each product it lists is the owner's to decide; `--adopt` records `output` for the products the store
   already has, so a moved input alone sends nothing.
   Steps 4-6 are the pilot of 5 of part E; then E goes on to the pilot of 30 and the report.
7. Turn the checked products into fixtures (A13) and update the docs of each changed rule (no CHANGELOG entry: the
   owner, 2026-11-14; a release is the skill `release`).

## E. The pilot cycle: 5, then 30, then the owner

The owner, 2026-11-26: every new category, every shop. The agent runs the cycle itself, fixes and the rebuild of its
own drafts included, up to the decision on the next 100; there it reports in short and waits. A pilot is not a
check that the pipeline runs: it is where the data the pipeline misses is found, and the readers and rules are
improved so that the next 100 come in whole (the golf shoes, 2026-11-25/26: every one of 399 pairs kept the default box,
the review on the pilot the owner asked for never done).

| Step | The agent | Ends with |
|---|---|---|
| E1 | The package defaults (A1) its own: the probe's cards and 5-10 pages (the sellers' stated weights and sizes, the maker's box, the description images), the central box priced on a cheap and a dear product (`shop_pricing.POLICIES[shop].quote`); the row's `approved_by` "agent", a `basis` with the sources and "to review on the pilots of 5 and 30"; a baseline (a set in a container) stays the owner's | the row, its prices in the report |
| E2 | The pilot of 5, drafts: `job.py scroll --query "..." --category <id> <its paid flags> --publish --describe --count 5` (JOB_AGENT.md "Shorthand and per-category defaults"; the category not `reviewed`, so DRAFT), or the old mode `job.py new ... --count 5 --publish --describe` and `run` | 5 drafts or held products |
| E3 | Every one of the 5 read by hand, every phase (the table below) | findings |
| E4 | The fixes: a rule or a reader with its test and fixture where data is lost or wrong; the package row restamped when the real products say otherwise (A1: the table's `version` raised, the row's `defaults_version` equal to it, the pin in `test_package_measures.py`); then `run_transform.py <shop>`, `translate.py <shop> --offline` (the model only for the texts a fix changed: `--only <key>`), `describe.py <shop> --only <key>` where a description's input moved, `placement.py <shop>`, and the pilot's own drafts sent again (`publish.py <shop> --job <id>` or `--keys-file F`; never activated, so no owner's word: OWNER_RULES rule 1) | the drafts as today's build |
| E5 | The pilot of 30, drafts | 30 drafts or held products |
| E6 | The lens review of the 30 (skill `visual-review`; a workflow: find per card range, verify each finding from the data), every phase; the package summary over the 35 (per product the variants' `package.<field>.source`: `shop_view.py show <shop> --job <id> --raw prepared --path product.variants --json`, counted by source; the stated values against the default); the fixes as E4; every new rule run over all the category's products so far (0 live products hit, the holds it adds listed); `sweep.py <shop>`, `store_diff.py <shop>`, `translation_dicts.py status` | the drafts as today's build |
| E7 | A short report in the chat: what was found and fixed (numbers), what is held and why, the package values and their effect on the price, and the next step to choose: the next 100, or the fixes that need the owner's yes (a resend of live products, a section, a query, a held group, activation) | the owner's answer: wait for it |

The review of every phase (E3, E6): what a product loses when the reader does not catch it.

| Phase | Read | A finding becomes |
|---|---|---|
| Listing screen | the kept cards the section's kind; the `not_taken` reasons with titles (a rule dropping what fits) | a word of `listing_title_rules.json` measured on the probe |
| Collection | `specs_folded`, `collect_incomplete`, `options_unaligned`, `photos_incomplete`; a page whose options or rows the answer lacks | a collect again; a parser fix (server/: DEVELOPMENT_RULES.md) |
| Description, OCR | `description_images_*` notes; a size chart, a weight or a size in the images not taken | the OCR run again; a reader (`description_measures.py` profile) |
| Package | the five fields' sources per product (`source_stated`, `measures_from_images`, composed, `category_default`) against the weights and sizes the pages and images state; a pilot never ends with every product on the default | the reader fixed where a page states it (a fixture, `make_measures_fixture.py`); else the row restamped from the stated values (their median, the band from their spread; kinds when two kinds differ) and the drafts repriced |
| Transform | the held codes and notes, variants left out, sizes, gender, seconds, bundles, copies | a rule with its test, the seller's pattern (skill `seller-pattern-rule`) |
| Brand, title | `brand_source` none / title_word, a sound-spelled or invented brand, a title's lost codes, a model year or season left, the translation's failures | a dictionary entry, a title rule, a correction row |
| Description | describe's conflicts; a claim the page does not make | the profile or the brief (skill `prompt-change`) |
| Placement | the section, `unresolved`, the split | `placement_rules` |
| Price | the cheapest and dearest; the box's share of the price; an outlier | the package row, the price rule (owner) |
| The rest of the shop | `sweep.py`, `store_diff.py`: the published products a rule changed | the owner's word per product (OWNER_RULES rule 1) |

The owner's word stays needed for: activation and `reviewed`, any resend of a live product, a new section or a
change of his query or required words, a price coefficient or the duty, the A2 choices (paid variants, add-ons,
OCR), a baseline, and a held copy's fate (OWNER_RULES rule 2). Everything else in E1-E6 is the agent's: the
package row, rules and readers with tests, the rebuild and the resend of the pilot's own drafts, holds with a
`hold:` reason.

## History

Written against the code on 2026-11-11 (one shop, `fairwardgolf`, one category, 50002788 golf full sets), kept up
with each category since: 50002787 junior clubs (2026-11-11), 50002670 women's iron sets (2026-11-14), 50002783
wedge sets (2026-11-15), draft first (2026-11-16), 50002784 chippers (2026-11-18: one club, no kinds; paid variants
without paid add-ons; one section `chippers`; the shop's general price rule; title rules from 1,260 listing titles,
the listing full of garden wood chippers, air chisels and poker chips; a `chipper` describe profile; A12 not
needed for one club, A13 left until the first products are checked: nothing collected yet; the same day's review on
2,558 titles: the escapes widened, an agency's hand-치퍼 titles and used clubs left out; reviewed=True on the owner's word 2026-11-19, after pilots of 5, 50 and 100 and the lens review: the 90 drafts activated), 50002797 women's golf knit cardigans (2026-11-19, the first apparel, parent `apparel`: a folded knit's mailer (28 x 22 x 4 cm, the parcel never under 300 g); paid variants for plus sizes, no paid add-ons, the images read for the size charts; one section `womens-knit-cardigans` split by gender as 50002670; its own price rule (x1.10 at every level; the duty a flat 12.5 % for now, the owner's second word 2026-11-19, the rule by the chief fibre kept behind a TODO); US sizes and a size chart (`CategoryRules.sizes`, [SIZES.md](SIZES.md): an apparel category needs a size profile, else the Korean sizes reach the storefront); the title screen requires a women's word and a cardigan word (30 of the 96 sample titles kept; 레이디스 / 레이디 / 우먼 are not among the owner's women's words, to ask him); "no choice" option values dropped; a `knit_cardigan` describe profile that never states a size; the pilot of 30 drafts ran 2026-11-19; reviewed=True on the owner's word 2026-11-20, after wave 1 of 60 and its lens review: the 52 drafts activated), 50002798 women's golf windbreakers (2026-11-20, the second apparel: the owner gave the section `womens-windbreakers` under `apparel`, the collection existed, and delegated the rest; the knits' package row, rules, price and size profile; the title screen from 767 listing titles in 8 price bands: a women's word and a jacket word, padded / down jumpers, rainwear, vests, knit cardigans and top-and-bottom sets left out, 312 kept; a `windbreaker` describe profile; 456 of the 767 cards were catalog cards, which never reach the screen; reviewed=True on the owner's word 2026-11-21, after pilot 2 of 100 drafts and its review: 85 activated, 15 held), 50002799 재킷 (2026-11-21, the owner's decision: the same section as 50002798, Naver files the same windbreakers under either leaf (20 of the 47 cards of the 리뷰 많은순 listing's first batch); every row of 50002798 copied (package row with its own `defaults_version` 14, rules, price, placement, describe profile, brief, TITLE_SIZES, aspects, the dictionaries' backup as its start); a job of either category takes the other's listing rows (`listing_title_rules.json` `together`, `job.py` `category_of`); fleece and coats left out of both, with light down, vests and rainwear, for Rainwear & Midlayers, not built yet), 50002796 women's fall long-sleeve golf tops (2026-11-21, the third apparel: the owner gave the section `womens-fall-long-sleeve-tops` under `apparel`, the collection existed as "Women’s Long-Sleeve Golf Tops"; the windbreakers' rules, size profile and price rule (HTS 6109 kept for the rate by fibre); a lighter package row (product 120 / 250 / 600 g, package 300 / 350 / 800 g, `defaults_version` 15); the title screen from 768 listing titles in 8 price bands: a women's word; short sleeves, cardigans, vests, outerwear, bottoms and sets, arm sleeves, summer cooling tops and kids' left out, knit sweaters and base layers kept, 221 of the 272 store products kept; a `long_sleeve_top` describe profile; reviewed=True on the owner's word 2026-11-21, after the pilot of 30 and its review: 24 activated, 6 held; a second pilot of 100 drafts (`--draft`) 2026-11-22: 92 activated, 8 held), 50002796's second section mens-fall-long-sleeve-tops (2026-11-22, the owner: the same Naver category, its own query 남성 골프 가을 긴팔 티셔츠 and required words 남성|남자|men and 긴팔|long sleeve; the first category with two sections: title rules with `leaves` and the file's `default_leaf`, `job.py --leaf`, `CategoryRules.sizes_mens` = mens_tops (a new profile: the Korean label is the body chest, 100 = US M, the letter alone on the storefront), `draft_leaves` (its products DRAFT in the reviewed category until its pilot's review), placement split by gender, a unisex top only in the women's section (`CategoryPlacement.stated_only`: it keeps the women's sizes, until the owner decides); `--leaf` checked against the rules' sections; the men's Korean letters as Korea writes them (M = 95, a US S); the briefs name women's or men's; 2026-11-22, the probe of 남성 골프 니트 and the owner's word: the men's golf knits of 50002797 (sweaters, half-zips) feed it too: `listing_title_rules.json` `together_leaf` (a job of the men's section takes 50002797 rows, screened by 50002797's rules for that section; the women's tops and the cardigans' jobs do not), 50002797's own rules tagged `leaves` (its women's rules for womens-knit-cardigans, the file's default; the men's rules copied from 50002796 for the men's section), 50002797 placement split into both sections with `stated_only` mens, its `sizes_mens` and `draft_leaves`, the knit briefs titling a men's knit a sweater, never a cardigan; the men's pilot of 100 drafts by four queries of the probe's decision, its lens review: 15 held, 91 activated on the owner's word 2026-11-22, `draft_leaves` emptied), 50002802 Golf Skirts & Culottes (2026-11-22, the fourth apparel; the category agent's values as a recommendation, the rest the agent's: the listing probe of 5 queries and its decision.md came first (B0): the queries 여성 골프 플리츠 큐롯 스커트, 여성 골프 스커트, 골프 스커트; no women's word required (a skirt is women's: it dropped WAAC, 젝시믹스, 보에르 skirts), rain skirts, a trousers listing, a blanket and men's / kids' words out (480 of 490 probe cards kept); one section, no split; the tops' choices, package (a 200 g skirt) and price rule (HTS 6204.5 kept for the rate by fibre); a new size profile by the waist (`womens_bottoms`: a waist read only for it, inches and cm to the US band and number, the measures waist / hip / length); a `skirt` describe profile; the dictionaries start from 50002796's backup; the pilot of 31 drafts, its lens review: 6 held, reviewed=True on the owner's word 2026-11-22, the 25 activated), 50002801 Golf Pants (2026-11-23, the fifth apparel; the owner gave the section `golf-pants` (the collection existed empty), the query 가을 스트레치 골프 바지 and the required words (골프 / golf and 바지 / 팬츠 / pants), shorts left out on the owner's word; the rest the agent's: the probe of that query (147 cards, 114 kept: 68 men's, 41 women's, 4 unisex or none; the golf word drops 5 golf brands' trousers that name none, asked); one section, no split, men's and women's together: the first category whose sizes follow the stated gender without a section split (`CategoryRules.sizes` womens_pants, `sizes_mens` and the new `sizes_unisex` mens_bottoms: a new profile by the US waist, "W32"; no gender stated holds); the measures `trousers`; the skirts' choices, the apparel price rule (HTS 6203.4 / 6204.6 kept for the rate by fibre), a package row (a 380 g pair); a `pants` describe profile; the dictionaries start from 50002802's backup), 50002816 Rainwear & Midlayers (2026-11-24/25, the sixth apparel; the owner gave the section `rainwear-midlayers` under `apparel`, no split, Golf Pants' choices and price; the leaf alone, no adjacent leaves; the probe of 골프 레인코트; package kinds suit / light fitted on the pilot of 30 (table version 19, the words of a seller's search keyword fixed in 20); sizes on womens_tops / mens_tops by the stated gender; a `rainwear` describe profile; pilots of 30 and 100 drafts, the lens review: 22 drafts held (copies, not golf, a hidden size, seconds, a product phrase as the vendor), the owner's per-product sizes (`variants_by_owner.json` `sizes`); reviewed=True on the owner's delegation 2026-11-25, 117 activated), 50001740 BOA spikeless golf shoes (2026-11-25, the
first shoes and the first category of a new parent `shoes`: the owner gave two sections, `mens-boa-spikeless-shoes` and
`womens-boa-spikeless-shoes`, the queries and the required words (보아 / BOA and a gender word), then took the agent's
values: a BOA title with no gender word too, placed by its sizes; one section a pair (`CategoryPlacement.stated_only`
both, `shoe_sizes.section_gender`); the probes of 6 queries (decision.md: spiked shoes by word and model, winter boots
and boa fleece, kids', used and park-golf shoes left out); a shoe box row (34 x 23 x 13 cm, 1.3 kg, table version 21,
to review on the pilot's pages); the apparel price rule; sizes not by a garment profile but `CategoryRules.shoe_sizes`
(mm -> US men's / women's, the owner's chart; `shoe_sizes.py`); a `shoes` describe profile; the server's SHOES notice
nests 치수 {발길이, 굽높이}: read as rows since 2026-11-25 (every shoe page answered 500 before)), 50002791 Lightweight
Stand Bags (2026-11-26/27, the first category of the part E cycle and of a new parent `bags`: the owner gave the
section, the query 경량 스탠드 캐디백 and the required words (경량 and 스탠드), FedEx IP with x1.10 ("A"); the agent's duty
(17.6 %, HTS 4202.92), paid variants, no paid add-ons, the images read; the probe of 357 titles; a carton row of 95 x 35
x 30 cm, 3.3 kg; variants of another item left out (`variant_drop`: wheeled, half bag, Boston bag, pouch, hood cover);
a `stand_bag` describe profile. The pilot of 5 (a review telling of a defect gives no gallery photo) and the pilot of 30
(35 drafts, a workflow review of every phase: 54 findings, 2 refuted): the box from the bag's stated body and the bag +
1 kg of carton (PACKAGE.md `own_box`), a closing period of a notice pointer ("상세 이미지 참조.", the server and the
transform: it was a vendor), the year, a Latin echo and two divider counts out of a title (`translate.garment_title`),
바퀴형 out of the feature list; held: a tour bag, a catalog of 15 bags, two brands waiting for the owner's word).

### Learned on the first new category (50002787, 2026-11-11)

Each of these touched the shop's other products without a word; each is fixed, and each is a reason for part D's
last step.

| # | What happened | Now |
|---|---|---|
| L1 | Every job prepares the **whole shop** (`run_transform.run`). A `--paid` job prepared all 436 products with paid variants and add-ons: 101 published full sets stood untranslated (nothing was sent) | `run_transform.paid_choices`: each product takes its own job's paid choice from the jobs' files, every other one only what is free; a run by hand does the same. Pick the job's `--paid` / `--paid-variants` for its own products only |
| L2 | Package defaults are written when a product is **collected**, and kept runs are read-only (never edit them): a fixed table row did not reach the products already collected | the transform takes each default from today's table (`package_measures.current_defaults`); prepare again, then publish |
| L3 | `publish.py --dry-run` did not know the store: it wrote "maruman" for Maruman and the tenant's name before an own-brand title | `publish.offline_ids`: the brand dictionary's spellings and the tenant's name offline |
| L4 | A new dictionary entry of the new category changed four products of the old one (`구성` -> "Contents"); 8 of its 108 entries were wrong (an age lost, `호수` -> "Club Number") | dictionaries per category (C2); read every new entry before the dictionaries' backup (`translation_dicts.py status`) |
| L5 | A rule fixed earlier (a brand read in "치핑" / "쇼핑") had not reached a product published before the fix | `store_diff.py` (part D, step 6) finds such products |
| L6 | publish.py's skip compared its inputs: 18 of 20 products whose inputs moved would have sent what the store already had, and hid the two real changes | the ledger keeps `output`, the hash of what productSet sends (`publish.output_digest`): a product is skipped when that did not change |
| L7 | The first 30 junior products: a shop's or a supplier's name as the brand (세모물상점, 스퀘어홀딩), one brand spelled two ways (U.S.KIDSGOLF / U.S. Kids Golf) and written twice in a title, a bag alone and a toy published, two clubs priced as a set | trading names are no brand, brands compared by letters and digits, `publish.py --withdraw`, the category's `bag_only` rule and `two_clubs` kind. Read the new category's vendors and its cheapest and dearest prices after the first run |
| L8 | The next 100 junior products: a shop brand of one category is looked for in every category's images (GB in "golf bag" changed two adult sets), the cleaned brand of one product (던롭) took two XXIO sets' titles; ages and lofts after 클럽 read as a count (single clubs priced as sets, $709-729) | Latin brands as whole words, a brand inside a Korean branch's name last, `brand_fallback.clean` for the brand rows, measures out of the package words. After every run, `store_diff.py` over the **whole shop**, not only the new category. Then read the new category's no-brand, agency and dearest products: three no-name agency imports at $1499-1899 and a school pack of ten irons went out; `agency_needs_brand`, the title rule `group_pack` |
| L9 | The first 100 women's iron sets (50002670, 2026-11-15, a review in six phases): a brand row of "골프" (one junior product) made "Golf" the vendor of 55 published junior and full sets; a used set ([중고]) published as new; a phone number in an option name, a "contact us" variant and add-on; a brand spelled from its sound (제스타임 "Jestime", the maker writes ZESTAIM), a maker's longer brand lost (무쯔미혼마 as 혼마), a model line invented in a title (Prestigio for 로얄); four XXIO 14 and two V300 listings of one model the title-word dedupe does not see | `brand_fallback._NO_FIRM` (the sport, a gender word, a lone letter, a 정품 claim are no firm), the category's `used` title rule (not shared: 50002788 keeps used sets on purpose), a seller's note out of option values, contact notes dropped in the transform, the maker naming a longer brand the title names wins, the category brief's makers and lines. After the first run of a category: `review_grid.py`, then read its new brands against the makers' own Latin spelling |
| L10 | The first 60 wedge sets (50002783, 2026-11-15): 17 listings titled "웨지 세트 (또는 개별)" sold one wedge per variant (a loft, 1PC) and were published as sets; 16 agency imports held as agency_no_brand, 5 of them with the maker in the title (라즈러스, 야마토, 버뮤다 mid-title, GoSports); the job's dedupe kept 10 sellers out as copies of those held products, so the models reached the store from none | `sets_only` (a one-club variant out, a listing of them held `single_only`), `brand_fallback.as_word` (`title_word`: a dictionary brand as a word of its own, Korean or Latin) and the makers in the brand dictionary, a held job product leaves the dedupe index (`job.held_keys`). After the first run: read the held products' titles, not only their codes. The owner then turned the hold off: a no-brand import is sold under the shop's name (Fairward Golf) |
