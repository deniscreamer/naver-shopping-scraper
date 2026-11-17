# Transform: collected to prepared

The transform of collected lines into prepared products per shop, the held codes, and the record types; split from
scripts/README.md on 2026-11-16 (history: `git log --follow scripts/README.md`). The five package fields (weight and
size, the category defaults, the description images' OCR) are in [PACKAGE.md](PACKAGE.md) since 2026-11-16.

## How to use

Offline, deterministic, no network (repo root). `job.py` runs the same per product; by hand:

```sh
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # keep the run before the next collection
.venv/bin/python scripts/run_transform.py fairwardgolf               # every kept run -> prepared/
.venv/bin/python scripts/run_transform.py fairwardgolf --full        # the same, every product prepared afresh
.venv/bin/python scripts/run_transform.py fairwardgolf --verify      # each cache record vs prepare afresh
.venv/bin/python scripts/run_transform.py fairwardgolf --diff        # then what changed, product by product
.venv/bin/python scripts/run_transform.py fairwardgolf --shops-root <copy> --copy-of scripts/output/shops --diff
.venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl [--fields status,brand,price] [--published-only] [--keys-out F]
```

`run_transform.py` takes the shop's lock (not while a job runs: `stop: <shop> is busy`, exit 2); `--verify` only
reads and runs anyway. It writes:

```
scripts/output/shops/<shop>/collected/<category>-<UTC time>/   products.jsonl, images/, manifest.json (read-only)
scripts/output/shops/<shop>/prepared/products.jsonl            one prepared product per line, rebuilt each run
scripts/output/shops/<shop>/prepared/report.txt                ready / held counts, held products and why
scripts/output/shops/<shop>/prepare_cache/<product id>.json    the prepare cache (below): derived, not backed up
```

What it prints, and what to do:

| result | means | do |
|---|---|---|
| `transform <shop>: N products from R run(s): X ready, Y held {codes}, notes {...}, T distinct texts to translate` | done, exit 0; ready products go on to translation and placement | the held ones: [Held codes](#held-codes) |
| `held <key>: <code> (<detail>)` (also in `report.txt`) | that product goes no further | its row in [Held codes](#held-codes) |
| `cache: H records used, M prepared afresh` | the prepare cache at work; any edit of `scripts/*.py` prepares the whole shop once | nothing |
| `stop: ...` (`ShopRulesMissing`), exit 2 | the shop or the category has no rules in `transform_shops.py` | ask the owner; skill `new-category-or-shop` |
| `stop: <shop> is busy: ...`, exit 2 | a job or another command holds the shop | wait for it (`job.py status`) |
| `--verify`: `identical`, exit 0 | every cache record equals a fresh prepare | nothing |
| `--verify`: `differs <key>: <field>`, exit 1 | a cache record is stale: an input missing from its signature | a code fault: report it; until fixed, `--full` |
| `--verify`: `nothing compared: no current record (run run_transform.py first)`, exit 0 | no cache record matches the current collected lines | run `run_transform.py <shop>` (no job running), then `--verify` again |
| a package field or its `confidence` looks wrong | the five fields | [PACKAGE.md](PACKAGE.md), How to use |
| a note in `notes` | never blocks | its rule below ([Prices, variants and options](#prices-variants-and-options), [Spec rows and the title vs variants](#spec-rows-and-the-title-vs-variants), [Description](#description)) |
| `test_prepared_golden.py` fails after a deliberate change | the golden prepared products differ | `UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py`, read the diff (R-TEST-5) |
| `--diff`: `run_transform: diff: O old, N new, C compared: A added, R removed, X changed (field n, ...), S the same`, then `key<TAB>change<TAB>field<TAB>old<TAB>new` lines | what this prepare changed (the snapshot is taken under the same lock, before the run; the exit code stays the run's) | read it; the changed products already in the store: [What changed](#what-a-rule-change-changed-prepared_diffpy) |
| `--diff`: `stop: --diff: <path>:<n>: not a JSON line`, exit 2 | the old prepared file has a broken line: nothing written | rebuild without `--diff` (it rewrites the file) |

## Held codes

A held product is kept with its codes (`held: [{code, detail}]`) and goes no further: not translated (translate.py
writes `status: held`, no codes of its own), not placed, not published. Where to see them: `prepared/report.txt`
(`held <key>: <code> (<detail>)`), `job.py status` (`held <key>: [codes]`), `placement/placements.jsonl` (`status`,
`reason`), a job's `events.jsonl` (`not_taken` with its `reason`). The table is checked against the code by
`scripts/test_docs_held_codes.py`: a new code needs its row.

| code | stage | what it means | what to do |
|---|---|---|---|
| `collect_incomplete` | transform | the collected line has no details, specs or options answer; nothing else is prepared | collect the product again (server running), keep the run, `run_transform.py` |
| `price_unknown` | transform | the details answer has no product price (`discounted_price` empty) | look at the page: no price there either (not on sale): leave it; else collect again |
| `no_variants` | transform | the listing has option groups and no variant was chosen; the detail says whether paid variants were allowed (`paid=`) | paid variants off for the category: the owner decides (`transform_shops.py` `paid_variants`); else leave it |
| `options_unaligned` | transform | variant rows that do not fit the option groups (a row's values not one per group); one of them alone is never published | leave it held; read the line's `specs.options` and report (a server parser change follows server/docs/DEVELOPMENT_RULES.md) |
| `specs_folded` | transform | the 상품정보 list stayed folded at collection (`specs.is_complete` false) | collect again |
| `axes_over_3` | transform | more than 3 option axes: Shopify has 3 options per product (`MAX_AXES`) | leave it held |
| `no_images` | transform | no gallery photo saved | collect again; still none: leave it |
| `images_over_50` | transform | more than 50 gallery photos (`MAX_IMAGES`) | leave it held; tell the owner |
| `single_only` | transform | a `sets_only` category's listing (wedges, 2026-11-15) that sells one club only: every variant one club, or the title sells one piece ("1개", "1pc") and no variant names a set | right as it is: the section sells sets. A set read as a single: the words in `transform.py` (`single_club`, `_ONE_PIECE_RE`), with a fixture |
| `not_wedge_set` | transform | a `wedge_sets` category's listing (50002783, 2026-11-16) that sells an iron set or a full set: an iron run in the title or a variant ("4-PW", "5-9", "3456789", "5 6 7 8 9"), a count of 6 to 16 clubs ("7피스", "12 Piece", "12개 세트"), a full set, a wood set or a junior set ("드라이버", "우드", "페어웨이", "460cc", "하이브리드", "유틸", "컴플리트" / "풀세트" / "완비" / "이그제큐티브" / "클럽 세트" with no wedge lofts, a putter or a bag with another club family or "클럽 세트", a bag with no wedge lofts ("카트백 골프 세트"), "주니어" / a child's age span ("Ages 6 to 8", "3-5세") with no "웨지 세트"; never a cover, a grip, a gift, a case or a wedge kind: "드라이버 우드 커버", "퍼터 증정", "무료 캐디백", "캐디백 수납", "하이브리드 웨지", "유틸리티 샌드 웨지", "우드티", "골프 백스핀", "컴플리트 웨지 세트", "풀세트 웨지 3종", a loft span "52-56 세트"), a practice set, a plastic toy or one adjustable club ("연습 세트", "연습용 폼 볼", "조절식", "플라스틱"), no wedge named at all (no 웨지 / wedge / AW-type letter / loft in degrees: stone splitters, golf pants, "Qi10"), one club (no set word and no two lofts in the title: "미라이 MW-25 ... 48도", "아이언 단품"), every variant one club with three numbered irons or more ("8번 아이언", "7 Iron": MAZEL WM-X), or "아이언 세트" / "아이언 5개 세트" in the title without "웨지 세트" (unless each variant is one club); the detail says which | right as it is: Naver files them under wedges. A wedge set held: the words in `transform.py` (`_iron_run`, `_CLUB_COUNT_RE`, `_WEDGE_SET_RE`), a case in `scripts/test_wedge_sets.py`. One already in the store: withdrawing it is the owner's word ([OWNER_RULES.md](OWNER_RULES.md)) |
| `agency_no_brand` | transform (run-level, `run_transform.py`) | a purchase agency's import (note `purchase_agency`) with no brand after the brand fallback (`brand_source: none`) where the category's `agency_needs_brand` is on; off in fairwardgolf since 2026-11-15 | the owner's brand in `<shop>/brand_by_owner.json` (skill `fix-a-product`), then `run_transform.py` |
| `held` | placement | the transform held it: not placed; `reason` is the transform's codes | the transform code's row |
| `unresolved` | placement | the category is split by an attribute (gender) and the product's value is unknown or in conflict (`reason`: `<attribute> <value>`), or no variant fits a section; the profile's `unresolved` is `hold` | read `evidence` in `placements.jsonl` / `report.txt`; a wrong attribute: skill `fix-a-product`; else the owner decides ([PLACEMENT.md](PLACEMENT.md), "What an unresolved product does") |
| `no_profile` | placement | the product's Naver category has no placement in `placement_rules.py`; `publish.py` skips it without a word | add the category's placement: skill `new-category-or-shop` ([ONBOARDING.md](ONBOARDING.md) A3) |
| `duplicate_of_withdrawn` | dedupe (job `--dedupe on`) | a confirmed copy of a product the owner withdrew: never taken (`not_taken duplicate_of_withdrawn:<key>`) | nothing; a copy held for the owner: [OWNER_RULES.md](OWNER_RULES.md) rule 2 |
| `duplicate_of` | dedupe | a confirmed copy that is not strictly better (store grade, then reviews) than the one kept: not taken (`not_taken duplicate_of:<key>`) | nothing; `dedupe.py --pairs <shop> --job <id>` shows the pairs side by side |
| `duplicate_better` | dedupe | a confirmed copy strictly better: taken, and the old product is withdrawn as `replaced_by:<key>` once this one is published (still published, no fewer variants) | nothing; `lens.py dupes <shop>` to look |

Not codes of this table: a placement `reason` of `fallback: <value>` is placed (the profile's `unresolved` is a
section handle, the fallback section); a job's `not_taken` `already_published` and `card_not_found`, and its other
events: [JOB_AGENT.md](JOB_AGENT.md); `publish.py`'s ledger row `status: held` (the payload refused:
`Untranslated` / `PayloadError`, the reason is the exception) and a withdrawal with a `hold:` reason (a doubtful copy,
[OWNER_RULES.md](OWNER_RULES.md) rule 2): skill `publish`, `store-actions`.

## Transform (collected -> prepared, per shop)

The step after collection and before translation and Shopify: offline, deterministic, no AI, no English, no
network. Korean stays Korean; each prepared product lists the Korean texts the translation stage must translate.

### The prepare cache

Since 2026-11-16, `run_transform.py` and `job.py` keep each product's `prepare()` output and its
images' text read (`image_read`: off / not_read / the blocks) in `prepare_cache/<product id>.json` (line 1 the
signature, then the record) and use it while the signature holds; `run(..., cache=False)`, the default of the
function (tests, example_15), and `--full` do not touch it. The signature: the bytes of every non-test
`scripts/*.py` (taken when `run_transform` is imported: a process keeps the code it loaded), the Python version, the
base rules and the measures table as loaded (per call), and per product the shop, run id and line number, the bytes
of the collected line and of the images' sidecar (read once for the hash and the record), and the rules variant of
its paid choice. `prepare()` reads no other file (`test_prepared_golden.py` pins it). Never from the cache: the
choice of the newest line, the paid choices, the store-wide banners, the `.ko` files and the images' text flag
(shared blocks, `en.json`), the brand fallback, the agency hold and the report: the same bytes as a full build. A
cut-off or broken record is prepared afresh and written again. Any edit of `scripts/*.py` prepares the whole shop
once (about 30 s at 2,444). `--verify` computes each record that the next run would use afresh and compares:
`identical`, exit 0; a record that differs (an input missing from the signature) is named with its first differing
field, exit 1; it writes nothing and runs while a job holds the shop. Records of products no longer chosen stay
(about 85 MB at 2,444); deleting the folder only costs one full prepare.

### What a rule change changed (`prepared_diff.py`)

After a change of a rule, a dictionary of brands or the code (2026-11-16, the owner's five tools): which products
moved, in which field, and which of them are in the store (those wait for the owner: OWNER_RULES.md rule 1).

- In place: `run_transform.py <shop> --diff` (the shop's lock: no job running). On a copy, the real shop untouched:
  `cp -cR scripts/output/shops/<shop> <scratch>/` (an APFS clone, seconds for 13 GB), then
  `run_transform.py <shop> --shops-root <scratch> --copy-of scripts/output/shops --diff`, or `prepared_diff.py` on
  the two `prepared/products.jsonl`. `--copy-of` is required on a copy: the paid choices come from the jobs made for
  the real root and the brand dictionary is loaded for it alone, so without it the copy is prepared with no paid
  variant and no dictionary brand, and the diff is false (2026-11-16: 752 of 2,451 "changed", 0 with `--copy-of`).
- `prepared_diff.py old new [--fields f,g] [--published-only] [--keys-out F] [--json]` compares each product by a
  short summary a field: `status`, `held` and `notes` ("code: detail"), `brand` ("brand_ko (brand_source)"), `title`
  (title_ko), `price` (the variants' price_krw, min-max), `variants` (the option labels, `[sold out]`),
  `package.<field>` ("min-max (source cN)"), `images` (count and digest), `other` (the names of other parts that
  differ, once, in the new column; `(old only)` / `(new only)` for a part on one side). A list field shows on each
  side only what the other lacks. `--published-only`: the keys whose last ledger row is `published` (`--shop`, else
  the new file's shop), read from `--shops-root` (default the real shops: give the clone's root with a clone's files);
  its summary says `(published only)`. The keys file's first line is a `# ...: N products` comment. `--keys-out F` ->
  `--keys-file F` of `store_diff.py`, `publish.py --dry-run`, `lens.py products`. Exit 0 the same, 1 differences
  listed, 2 a missing or broken file.
- 2026-11-16, measured on a clone with `--copy-of`: today's code prepares the shop as its prepared file says, 0 of
  2,451 changed (an earlier "752 changed, 477 in the store" was the clone prepared without the jobs' paid choices
  and the brand dictionary, not a rule change).

### Kept runs

example_99 overwrites its `products.jsonl`: a run not kept before the next collection is lost. The shop is the
namespace of the source keys, one shop and one category per run; a product in several runs comes from the newest.
A run is copied into `<run>.partial` and renamed when complete; only folders with a `manifest.json` are runs.

### Prepared product

The record (`transform.Prepared`, `format: prepared/5`; the versions: [History](#history)): `key`, `shop`, `status` (`ready` / `held`),
`held` and `notes` (`{code, detail}`), `source` (run, line, link, channel_no, product_id, category_id), `product`
(`title_ko`, `brand_ko`, `brand_source`, `attributes` (`{gender: {value, variants, evidence, flags}}`), `options` `[{name_ko, values_ko}]`, `facts`,
`variants` `[{source_id, naver_variant_id, options_ko, price_krw, price_usd, sku, available, package}]`, `pricing`,
`specs`, `personalization`, `addons`, `rating`, `reviews`, `images`), and `texts` `[{id, kind, ko}]`: the translation
worklist, `id = <kind>:<sha256(ko)[:16]>`, so the same Korean text has one id (one translation) in every product.

### Rules

Rules (`transform.py`, each from a real case, research 2026-11-05 on 23 collected sets: on 10 the naver-harvester
published, SKUs and prices equal on 201 of 201 variants):

### Prices, variants and options

- **Prices**: KRW = the product's price + the variant's `extra_price` (the page's own answer; option names are not
  parsed for money); USD = rounded up to the cent at the shop's rate (kept in the record; Shopify's cost and price
  are made at publication by the shop's price rule, see PRICE.md, The price); no compare-at, not taxable.
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
- **Rows that are not versions**: a row asking for a delivery message (배송메세지) is dropped, and so is a row or an
  add-on choice that only asks the buyer to contact the seller (문의, 연락주세요, 톡톡 with no club, shaft or count:
  2026-11-15); a phone number or a "(문의...)" note leaves an option name, and a seller's note leaves the values
  when they stay different ("L/세금미포함", "A(주문전문의)", "(오늘출발)" -> "L", "A"); a one-value axis named like a
  hidden row (상품번호) is not a fact.
- **Delivery**: `delivery` from the page (fee as charged, scope international / domestic, customs, lead time);
  notes `shipping_paid` and `overseas_shipping`. In a shop with the price rule the base fee of a PAID or
  UNIT_QUANTITY_PAID listing goes into the purchase; any other fee type counts as free (see PRICE.md, The price). An
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
- **Pilot 20 (2026-11-06)**: a variant carries `today_dispatch` (the seller's todayDispatch per variant: one of two
  may ship today); a tag every value starts with ("[당일출고]") and a "(선택)" in front of an option name are left out
  (the SKU keeps the raw tuple); past the cap the rows are taken in turn from each value of the first axis; notes
  `few_pieces` also from 총클럽개수 of 5 or fewer, `gift_hidden` (a hidden 사은품 row naming a thing in the box, not
  points or a coupon: "오리지널커버 증정"). `delivery.lead_time` passes through: check `today_off` before
  `today_cutoff`.
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

### Reviews

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
- **Reviews**: the selected reviews (video posters already photos), rating and count from Naver's summary.

### Spec rows and the title vs variants

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
  An import title's end that is one variant's option values in Latin, the page's first option the import tool appends
  ("... 골프 클럽 58 Degree Silver RH", 13468791008), is one span of the note too (`spec_variants.title_variant_tail`;
  2026-11-16) when that variant is not sold or is one of several sold; the words of the note inside it are not repeated.
  A tail with ", " or no letter (a bare loft "52") is not taken. It fires in every category: measured on the store
  76 notes change, 26 wedge sets and 50 junior sets ("Left, Putter" becomes "Left Hand Putter").
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

### Description

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

### A brand for every product

- **A brand for every product** (the owner, 2026-11-08: the Shopify vendor is never empty; no brand, at least the
  manufacturer). A seller who links no Naver brand leaves no 브랜드 row and no brandName, and Naver then knows none
  anywhere (6 of 143 sets: not in the product answer, the page's answer, the search cards, the notice, the page's
  ld+json). `brand_source` says where it came from: the row / brandName; else the manufacturer
  (`manufacturer:<source>`, never Naver's M0000000); else, run-level (`brand_fallback.py`), a brand the shop's other
  products state found in the title (`title`: 4 of the 6; the first one of a combination set), a brand of the
  dictionary starting the title (`title_known`) or standing as a word of its own in it, three letters at least, by
  its Korean name or its Latin spelling (`title_word`: 라즈러스, 버뮤다, GoSports in wedge imports, 2026-11-15), a Brand
  row of the description, the spec table an agency import copies (`description_row`: "Brand | WENGH", 2026-11-15;
  2026-11-16: a bullet "- Brand : X", the label 브랜드 이름 (a machine translation of Brand Name), a bare number
  "69" takes the Manufacturer / 제조사 row that starts with it ("69 Golf"), none / N/A / others / 다른 사람들 name
  no firm, and a Latin brand the brand dictionary spells another case takes the dictionary's spelling: pgm ->
  PGM, WILSON -> Wilson, HATACHI -> Hatachi, also on products whose row brand was read before, so their vendor
  spelling changes and translate asks the model for the title again),
  the importer in
  원산지's brackets (`origin`), the shop's brand most read in the images (`images_text`), a Latin brand phrase the
  images repeat 5+ times (`images_text_latin`: BEN SAYERS on 13425122164), or 노브랜드 (`none`: 13464713764, an
  unbranded putter; its vendor is the shop's name, Fairward Golf, and since 2026-11-15 a purchase agency's import
  with no brand is no longer held: `agency_needs_brand` off, the owner). These add the note `brand_fallback`
  (source, other candidates). No brand list is kept by hand; one product whose brand only its photo shows gets the
  owner's word in `<shop>/brand_by_owner.json` (`{entries: {key: {brand, why, at}}}`, source `owner`, before every
  step: ALVO and XINGGM stamped on the heads, 2026-11-15).
  A brand row the maker's own name extends, when the title names the maker too, gives way to the maker (혼마 /
  무쯔미혼마, 7186088743, 2026-11-15; a Korean branch's name never). No firm, dropped from a 브랜드 row and never a
  shop brand: the sport (골프, 골프용품, GOLF, 스포츠: one junior row's "골프" made "Golf" the vendor of 55 products,
  2026-11-14), who it is for (남성용, 여성용, 남녀공용: 32 titles got "Yoshino" through a dictionary guess), a lone letter
  (ㅊ) and an authenticity claim (정품), and Amazon's "Generic" / 제네릭 (two Bermuda wedge sets, 2026-11-15). A Korean
  shop brand counts in the title only where a word starts, as in the images (이디스 was read in 레이디스, 2026-11-15), and
  a Latin brand read once in the images, inside an all-Latin phrase of 3+ words, is a slogan ("PRECISE AIMING
  FEEDBACK" on a XINGGM set, 2026-11-15).

### Per-shop rules

**Per-shop rules** (`transform_shops.py`, data): SKU prefix, KRW per USD, variant cap, and per Naver leaf category
`paid_variants` / `paid_addons` / `description_images`, off by default, all on for fairwardgolf 50002788 and
50002787 (junior clubs, 2026-11-11), 50002670 (women's iron sets, 2026-11-14) and 50002783 (wedge sets,
2026-11-15; no parts profile: the core reading only). `sets_only` (wedges, 2026-11-15): a variant whose own words
sell one club (1PC, 단품, 개별, 싱글, or one loft 44-72 with no set word or count; "i60R" is a shaft) is left out, and a
product of such variants only is held `single_only` (17 one-wedge listings of the pilot filed as "웨지 세트 또는
개별"). A loft written again on a second axis that describes the same club ("Size: 56 Degree" + "Style Name: Black
56 Degree") counts once; on axes that are club slots (names equal but for a number: 옵션 1 / 옵션 2) each counts
(two Yamato imports published as sets, 2026-11-15). `wedge_sets` (50002783, 2026-11-16): an iron set or a full set
that sellers file under wedges is held `not_wedge_set` (`transform.not_wedge_set`, after `single_only`): an iron run in
the title or a variant's value (a start iron 3-7 to 9 / P / PW / AW / GW / SW, "#5", "5번", "4 Iron- PW"; single digits
ending at 9 together or apart: "3456789", "5 6 7 8 9"; not a run: "7-9 years" / "7-9일" (an age, a day span), a wedge
end followed by a loft ("RTX 6 - SW 56도"), a spaced dash to a wedge with no iron word ("CBX 4 - AW/SW"), two-digit
lofts), a count of 6 to 16 clubs ("7피스", "9PCS", "12 Piece"; "N개 / N본 / N자루" only before 세트 / 구성, so "골프공
12개 증정" and "52개 샌드 56개" are not; a count right after 웨지 counts wedges: "웨지 6개 세트"), or "아이언 세트" /
"iron set" in the title with no "웨지 (아이언) 세트" (lofts, wedge letters or a count may stand between: "웨지 AW SW 2개
세트") unless each variant is one club or one loft (KVV 13163034573: 6 Iron / 8 Iron / Sand Wedge). Then (the same
night, full sets with no iron run and under 6 clubs counted): a club no wedge set holds or a complete set in the title
or a variant (driver, 460cc, fairway, wood / 우드, hybrid, 유틸; not a cover or a grip, also after a list of clubs:
"드라이버 우드 커버"; not a hybrid or utility wedge or sole: "하이브리드 웨지", "유틸리티 샌드 웨지"; not a wood tee
"우드티" nor "언더우드"; 페어웨이 alone, with no wood word next to it, only where no wedge set is written: "페어웨이 벙커
러프 웨지 3종 세트" stays; 컴플리트 / complete / 풀세트 only where no wedge set is written and not right after 웨지: a
wedge set written is "웨지 (lofts) 세트", a wedge count "웨지 3종" / "3 Wedges", or two distinct lofts or wedge letters, a
loft with ° counted once, so Mazek's "컴플리트 웨지 세트 52° 갭 웨지GW" and "풀세트 웨지 3종" stay), a putter or a bag
(캐디백, 스탠드백, stand bag; not "골프 백스핀") with another club family, or "클럽 세트" where no wedge set is written
(a putter or a bag as a gift or with its gear counts for neither side: "퍼터 증정", "무료 캐디백", "퍼터 헤드커버 포함",
"캐디백 수납"; "아이언 웨지" / "iron-type wedge" is no iron), a junior word or a child's age span (both ages 15 or
under, not "52-56 세트" nor "50~60세") with a set word and no "웨지 세트" ("핑 프로디 G 주니어 골프 웨지 2종 세트"
stays), and a listing whose every
variant is one club (a numbered iron, a named wedge, "아이언 2종") with three numbered irons or more (MAZEL WM-X
"8번 아이언"; KVV's two irons stay). Measured on the shop's 502 listings: it held 9 iron sets and 8 full sets, all
published before; on the 604 of the same night (616 after its review) the second pass holds 16 more, all published (active), and none of the review's probe wedge sets (`test_counts_and_the_title`) (the fixture
`fixtures/wedge_sets/50002783.json`, `make_wedge_sets_fixture.py`; `test_wedge_sets.py`). The shop's
sections are not decided here (PLACEMENT.md). A shop or a category without rules: `ShopRulesMissing`, the
run stops and asks the operator.

### Not here

Not here (later stages): the shop's sections, tags and product type (PLACEMENT.md, `placement.py`), English (titles,
options, specs, reviews), vendor spelling (every product: the same brand
is written 캘러웨이 / 캘러웨이골프, PGM / 피지엠, 젝시오 / XXIO; a `brand_fallback` can be checked against its other
candidates), handle, alt texts, the seller's description prose (images only on the sets checked), publication.

## Record types (`shop_types.py`)

TypedDicts of what the pipeline itself writes (2026-11-16), for mypy and the reader: annotations only, the files
stay plain JSON and nothing is checked when one is read. Each mirrors the one place that builds the record:
`PreparedProduct` (+ `PreparedVariant`, `PreparedOption`, `PreparedPricing`, `PreparedImage`, ...) is
`transform.Prepared.product` as `prepare` builds it, plus `description_images_text` from run_transform.
`LedgerRow` is a line of `publish/published.jsonl` (publish.py's published / withdrawn / restored / activated rows,
store_diff's adopted; `key`, `status`, `at` always there).
`JobMeta` is a job's `job.json` (job.py `new` / `scroll`; only `shop`, `category`, `shops_root` are in every job, the
rest is read with `.get()`: older jobs lack newer keys, `mode` is only in scroll jobs). mypy checks a key written
or read with `[...]`, not one read with `.get()`: a misspelt `.get("key")` still passes.
`CollectedLine` is a line of `collected/<run>/products.jsonl`, `prepare`'s input: the API's answers as
`naver_types` names them (details, specs, the listing row) and what collect_product made of them.
`test_shop_types.py` checks the golden prepared products against them (no unknown key, no wrong type, every key of
a built product) and their collected lines against `CollectedLine`. A change of a record's shape updates its type
in the same commit.

## History

The prepared format's versions: 5 since 2026-11-10: package `confidence` is 1-5 (1-3 before) and a field may be `source: composed` with `parts`, `baseline` and `refused`; 4 since 2026-11-08: reviews sanitized; 3 since 2026-11-08: no shop leaves, `product.attributes`
instead (see PLACEMENT.md, The idea); 2 since 2026-11-07: a variant's `package` fields
may carry `how`, `quote`, `flags`, `from` (`description_text`: the quote is typed text, not an image's) and `compared` (the value not kept, see [PACKAGE.md](PACKAGE.md)), and `product` has
`description_images_text` (the images' text flag, see PACKAGE.md, The images' text).

2026-11-16: `run_transform.py --diff` and `--shops-root`, `prepared_diff.py` (the owner's five tools).
