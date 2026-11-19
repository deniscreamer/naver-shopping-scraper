# A new Naver category or a new shop (tenant)

Where to add what, so that a new Naver leaf category in a shop, or a new shop, runs through the whole pipeline
(collect, transform, OCR, translate, describe, place, price, publish) without silent gaps. Agents: the
`new-category-or-shop` skill (`.claude/skills/`) walks through this file. The rows' ids (A1-A14, B1-B10, C1-C11,
L1-L10) are cited from code and other docs: keep them. When was what written: [History](#history).

## How to use

| Task | Section |
|---|---|
| A category in an existing shop: what stops without it | [A. Required](#required) (A1-A6) |
| What works without, but worse | [A. Quality](#quality-works-without-these-but-worse) (A7-A14) |
| A new shop (tenant) | [B](#b-a-new-shop-tenant) (B1-B10), then A for each of its categories |
| Golf or `fairwardgolf` in shared code: decide before the first run | [C](#c-golf-or-fairwardgolf-in-shared-code-decide-before-the-first-run) (C1-C11) |
| The first run, in order | [D](#d-the-order-of-a-first-run) |
| What earlier categories did to the rest of the shop, and the fix | [Learned](#learned-on-the-first-new-category-50002787-2026-11-11) (L1-L10) |

First, ask the owner for the values (A1, A2, A3, A5; for a shop B1, B2, B6), never invent them. Then the first run
(part D) prints, and you:

| Command | Result | You |
|---|---|---|
| `SHOP_STORE=<shop> .venv/bin/python scripts/job.py new --query "..." --category <leaf id> --count 5` | `stop: no category_measures.json row for <id>: ask the operator` (exit 2) | A1 |
| the same | `category_mismatch` in the screen counts | a wrong id: use the leaf id (below) |
| `job.py run` | `stop: prepare: ShopRulesMissing` | A2 (a new shop: B4) |
| `job.py run` (a job made with `--publish`) or `publish.py <shop>` | a product `failed` at stage publish / `held` with `Untranslated: ...` (a text the product needs has no English) | the translation (skill `translation`): [TRANSLATION.md](TRANSLATION.md#how-to-use), status `untranslated`: fix the brief, rule or dictionary entry, then `translate.py <shop> --only <key>` |
| `.venv/bin/python scripts/placement.py <shop>` | `no_profile` or `unresolved` in the counts; a new shop without a profile: `PlacementRulesMissing` | A3; B5 |
| `.venv/bin/python scripts/publish.py <shop> --dry-run` | builds only what is ready, translated and placed; payloads in `shops/<shop>/publish/payloads/<id>.json` | read the price breakdown (D step 5); the real publish only after the owner says yes |
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
a product only when its page's category equals the run's exactly (`collect_product.py`, `listing_filter.Screen`).
A parent or a near id collects nothing: every product ends `category_mismatch`, and only the counts show it.

**The operator gives the values.** Package defaults, prices, coefficients, sections and the paid-variant choice
are the owner's decisions. They are never made up. Ask, then write each one down with its date.

## A. A new category in an existing shop

### Required

| # | Where | What | Without it |
|---|---|---|---|
| A1 | `scripts/category_measures.json` | A row with `category_id`, `category_name`, `fields` (low / central / high of the 5 package fields), `reliability`, `approved_by`, `approved_at`, `basis`. Optional: `plausible`; `baselines` (only a set of like items in a container; all of them or none); `kinds` (a category that mixes kinds of very different size, e.g. 50002787: single clubs and sets: each kind its own defaults, chosen by title and variant words, `package_measures.default_kind`; a count kind may carry `lofts`, e.g. 50002783 two_wedges); `compose_by_count` (50002783: a set's weight from its clubs' labelled weights, PACKAGE.md). Before asking, price the central box (`shop_pricing.POLICIES[shop].quote`) on a cheap and a dear product of the listing: at level 1 (x2.50) one default box for a 25,000 KRW putter and a set came to $699. A row changed later reaches the products already collected when they are prepared again (`current_defaults`; kept runs are read-only, never edit them), then `publish.py --only` them. Append it last, after the existing rows (50002788 stays first: tests read `rows[0]`), raise `version` and give the row `defaults_version` equal to it (a row whose fields or kinds change later gets the new version there too; 2026-11-18: the other rows' restamped defaults keep theirs), then update the pin in `test_package_measures.py::test_baselines_block_is_optional_and_the_operators`. | **stops**: `job.py new` exits 2 ("no category_measures.json row"); `CategoryDefaultsMissing` |
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

## D. The order of a first run

1. Ask the owner for the values of A1, A2, A3, A5 (and B1, B2, B6 for a shop). Write them down with the date.
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
5. Read 2-3 products by hand: package fields and confidence, title, description. Run `placement.py <shop>` and check
   that nothing is `no_profile` or `unresolved` (A3). Then run `publish.py <shop> --dry-run`: it builds only what is
   ready, translated and placed. Read the price breakdown in `shops/<shop>/publish/payloads/<id>.json`: the
   variant's `fairwardgolf.price` and the product's `fairwardgolf.pricing`; the namespace is literal, see C1. Do the
   real publish only after the owner says yes.
6. **What the new category did to the rest of the shop.** First `sweep.py <shop>` (offline, seconds: the old
   products' answers and groups a resend would send, worse 0; [SWEEP.md](SWEEP.md)), then
   `store_diff.py <shop>` (read only): the published products
   whose store data a publication would change, field by field, and those that cannot be built now (an untranslated
   paid variant, a lost placement: L1). Then `translation_dicts.py status`: read every new entry before the
   dictionaries' backup into git (L4; not the state backup, `state_backup.py`). Each product it lists is the owner's to decide; `--adopt` records `output` for the products the store
   already has, so a moved input alone sends nothing.
7. Turn the checked products into fixtures (A13) and update the docs of each changed rule (no CHANGELOG entry: the
   owner, 2026-11-14; a release is the skill `release`).

## History

Written against the code on 2026-11-11 (one shop, `fairwardgolf`, one category, 50002788 golf full sets), kept up
with each category since: 50002787 junior clubs (2026-11-11), 50002670 women's iron sets (2026-11-14), 50002783
wedge sets (2026-11-15), draft first (2026-11-16), 50002784 chippers (2026-11-18: one club, no kinds; paid variants
without paid add-ons; one section `chippers`; the shop's general price rule; title rules from 1,260 listing titles,
the listing full of garden wood chippers, air chisels and poker chips; a `chipper` describe profile; A12 not
needed for one club, A13 left until the first products are checked: nothing collected yet; the same day's review on
2,558 titles: the escapes widened, an agency's hand-치퍼 titles and used clubs left out; reviewed=True on the owner's word 2026-11-19, after pilots of 5, 50 and 100 and the lens review: the 90 drafts activated), 50002797 women's golf knit cardigans (2026-11-19, the first apparel, parent `apparel`: a folded knit's mailer (28 x 22 x 4 cm, the parcel never under 300 g); paid variants for plus sizes, no paid add-ons, the images read for the size charts; one section `womens-knit-cardigans` split by gender as 50002670; its own price rule (x1.10 at every level, the duty by the chief fibre: wool 16 %, cotton 16.5 %, cashmere 4 %, man-made or unread 32 %); the title screen requires a women's word and a cardigan word (30 of the 96 sample titles kept; 레이디스 / 레이디 / 우먼 are not among the owner's women's words, to ask him); "no choice" option values dropped; a `knit_cardigan` describe profile that never states a size; no pilot run yet).

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
