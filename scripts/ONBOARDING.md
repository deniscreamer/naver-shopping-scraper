# A new Naver category or a new shop (tenant)

Where to add what, so that a new Naver leaf category in a shop, or a new shop, runs through the whole pipeline
(collect, transform, OCR, translate, describe, place, price, publish) without silent gaps. Checked against the
code on 2026-11-11 (today: one shop, `fairwardgolf`, one category, 50002788 golf full sets). Agents: the
`new-category-or-shop` skill (`.claude/skills/`) walks through this file.

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
| A1 | `scripts/category_measures.json` | A row with `category_id`, `category_name`, `fields` (low / central / high of the 5 package fields), `reliability`, `approved_by`, `approved_at`, `basis`. Optional: `plausible`; `baselines` (only a set of like items in a container; all of them or none); `kinds` (a category that mixes kinds of very different size, e.g. 50002787: single clubs and sets: each kind its own defaults, chosen by title and variant words, `package_measures.default_kind`). Before asking, price the central box (`shop_pricing.POLICIES[shop].quote`) on a cheap and a dear product of the listing: at level 1 (x2.50) one default box for a 25,000 KRW putter and a set came to $699. A row changed later reaches the products already collected when they are prepared again (`current_defaults`; kept runs are read-only, never edit them), then `publish.py --only` them. Append it after 50002788 (tests read `rows[0]`) and raise `version`, then update the pin in `test_package_measures.py::test_baselines_block_is_optional_and_the_operators`. | **stops**: `job.py new` exits 2 ("no category_measures.json row"); `CategoryDefaultsMissing` |
| A2 | `scripts/transform_shops.py` `RULES[shop].categories` | `CategoryRules(paid_variants, paid_addons, description_images)`, with the owner's reason in a comment | **stops**: `ShopRulesMissing` in `transform.prepare`; a job stops with `stop: prepare: ShopRulesMissing` |
| A3 | `scripts/placement_rules.py` `PROFILES[shop].categories` | `CategoryPlacement(parent, leaves, split_by, unresolved)` and its `Leaf(handle, product_type)` constants. How: [PLACEMENT.md](PLACEMENT.md) | **silent**: status `no_profile` (in `placements.jsonl` and the counts of `placement.py`), and `publish.py <shop>` skips the product without a word |
| A4 | `scripts/attributes.py` `ATTRIBUTES` | Only when the split is by something other than `gender`: a new `Attribute` | **stops**: `KeyError` in `placement.place` |
| A5 | Price, `scripts/shop_pricing.py` (the shop's `Delivered`) | Check level 1 (2.50) and the duty (12.5%) for this category. The rule is per shop, not per category: a different value needs a category override (new code). [README.md](README.md) "The price" | **silent**: priced with golf's coefficients and duty |
| A6 | Shopify admin | A smart collection for every new `Leaf` handle, condition tag = `<shop>:leaf:<handle>`. No code creates collections. Read what exists first (read-only: `ShopCatalog(store)._post("{ collections(first: 100) { nodes { handle ruleSet { rules { column condition } } } } }")`): fairwardgolf already has 36, empty ones included, and the `Leaf` handle is the tag's part, without the `fairwardgolf-` of the collection's handle | **silent**: products are ACTIVE but in no section |

### Quality: works without these, but worse

| # | Where | What | Without it |
|---|---|---|---|
| A7 | `scripts/prompts/categories/<id>.md` | The translation brief: what the products are, their terms, how buyers write. Model: `50002788.md` | **weaker**: the base prompt only, and it is golf-worded (C3) |
| A8 | `scripts/review_clean.py` `ASPECTS`, `PRODUCT_WORDS` | The category's review aspects and product words; plus a review fixture corpus `fixtures/reviews/<name>_<id>.jsonl` with its test | **weaker**: reviews rarely rate "full", and shipping-clause cuts keep only the generic product words |
| A9 | `scripts/translation_rules.py` `CATEGORY_RULES` | The category's glued codes, plus exceptions to the general rules (C4) | **weaker**, or **silent** where a general rule misreads the category |
| A10 | `scripts/describe.py` `PROFILES` and `scripts/prompts/describe/<profile>.md` | A profile with its lists (e.g. "What's included") and its brief. Ship the two together | **weaker**: `default` (highlights only). A profile without its `.md` **stops** with `FileNotFoundError` |
| A11 | `scripts/description_image_text.py` `GLOSSARIES` | The fixed Korean -> English terms of the images' text | **weaker**: terms are translated inconsistently |
| A12 | `scripts/description_measures.py` `CATEGORY_PROFILES` | Only a set of like items in a container (its tables of parts); otherwise the core is enough. [README.md](README.md) "More of the page" | **weaker**: no counts, no container, no composition. Unstated fields fall to the flat default (A1) |
| A14 | `scripts/listing_title_rules.json` | The category's title words for what its section does not sell (toys, gloves, loose heads, another sport), studied on 300-500 listing titles of the category: every rule checked on all of them, none may drop a product that fits (2026-11-11: 46 of 56 misfits of 50002787 with no false hit) | **weaker**: misfits are collected, translated and published; a person has to find them |
| A13 | Tests | Fixtures from the first checked products: `make_measures_fixture.py` (package), `fixtures/collected` with `test_placement.EXPECTED` (placement), the golden prepared files | regressions go unnoticed |

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
| B9 | The Shopify store | At least one publication (sales channel), one active location, the collections of A6. The theme must read the `custom.*` metafields (reviews, rating, add-ons, text fields) in the formats of [README.md](README.md) | **stops** at publish (`AdminError`: no publication / no active location); **silent**: the blocks are written but never shown |
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

### Learned on the first new category (50002787, 2026-11-11)

Each of these touched the shop's other products without a word; each is fixed, and each is a reason for part D's
last step.

| # | What happened | Now |
|---|---|---|
| L1 | Every job prepares the **whole shop** (`run_transform.run`). A `--paid` job prepared all 436 products with paid variants and add-ons: 101 published full sets stood untranslated (nothing was sent) | `run_transform.paid_choices`: each product takes its own job's paid choice from the jobs' files, every other one only what is free; a run by hand does the same. Pick the job's `--paid` / `--paid-variants` for its own products only |
| L2 | Package defaults are written when a product is **collected**, and kept runs are read-only (never edit them): a fixed table row did not reach the products already collected | the transform takes each default from today's table (`package_measures.current_defaults`); prepare again, then publish |
| L3 | `publish.py --dry-run` did not know the store: it wrote "maruman" for Maruman and the tenant's name before an own-brand title | `publish.offline_ids`: the brand dictionary's spellings and the tenant's name offline |
| L4 | A new dictionary entry of the new category changed four products of the old one (`구성` -> "Contents"); 8 of its 108 entries were wrong (an age lost, `호수` -> "Club Number") | dictionaries per category (C2); read every new entry before the backup (`translation_dicts.py status`) |
| L5 | A rule fixed earlier (a brand read in "치핑" / "쇼핑") had not reached a product published before the fix | `store_diff.py` (part D, step 6) finds such products |
| L6 | publish.py's skip compared its inputs: 18 of 20 products whose inputs moved would have sent what the store already had, and hid the two real changes | the ledger keeps `output`, the hash of what productSet sends (`publish.output_digest`): a product is skipped when that did not change |

## D. The order of a first run

1. Ask the owner for the values of A1, A2, A3, A5 (and B1, B2, B6 for a shop). Write them down with the date.
2. Add the required rows (A1-A4; B1-B6). Do the quality rows the category needs (A7-A12). Decide on C.
3. `.venv/bin/python -m pytest scripts -q`, then update the registry tests (A1 `version`, B10).
4. A small job ([JOB_AGENT.md](JOB_AGENT.md)): `SHOP_STORE=<shop> .venv/bin/python scripts/job.py new --query "..."
   --category <leaf id> --count 5` reads and screens the listing only. `category_mismatch` in its screen counts means
   a wrong id. Then `job.py run` collects, reads the images and prepares. `stop: prepare: ShopRulesMissing` means
   A2. `Untranslated` means the translation. OCR `off` is the owner's choice (`description_images=False`), not a
   missing rule.
   Cheap, popular categories carry many reviews: 50002787 scanned a median 134 reviews a product (sets: 1), so
   collection took 47-186 s a product against 45-65 s.
5. Read 2-3 products by hand: package fields and confidence, title, description. Run `placement.py <shop>` and check
   that nothing is `no_profile` or `unresolved` (A3). Then run `publish.py <shop> --dry-run`: it builds only what is
   ready, translated and placed. Read the price breakdown in `shops/<shop>/publish/payloads/<id>.json`: the
   variant's `fairwardgolf.price` and the product's `fairwardgolf.pricing`; the namespace is literal, see C1. Do the
   real publish only after the owner says yes.
6. **What the new category did to the rest of the shop.** `store_diff.py <shop>` (read only): the published products
   whose store data a publication would change, field by field, and those that cannot be built now (an untranslated
   paid variant, a lost placement: L1). Then `translation_dicts.py status`: read every new entry before the backup
   (L4). Each product it lists is the owner's to decide; `--adopt` records `output` for the products the store
   already has, so a moved input alone sends nothing.
7. Turn the checked products into fixtures (A13) and update [CHANGELOG.md](../CHANGELOG.md) and the docs of each
   changed rule.
