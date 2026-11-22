# Apparel sizes: Korean -> US (the mechanism)

The owner, 2026-11-19: on the fairwardgolf storefront a garment shows US sizes only. The Korean originals are kept
for the owner, never shown to buyers. The size chart is in US sizes and inches. Each product's own
designations come first. A profile's default grid is only the fallback when the product's own label and chart say
nothing.

This file is the shared mechanism. The parts:

| Part | Doc | Code |
|---|---|---|
| Reading a seller's size chart (text and OCR), the layouts, what is never read | [SIZE_CHARTS.md](SIZE_CHARTS.md) | `size_chart.py` (`MEASURE_SETS`) |
| A garment profile: its grid, its brand rows, its sellers' habits | `size_profiles/<profile>.md` | `size_profiles/<profile>.json` |
| Profiles today | [womens_tops](size_profiles/womens_tops.md) (knit cardigans 50002797, windbreakers 50002798 and 재킷 50002799, long-sleeve tops 50002796), [mens_tops](size_profiles/mens_tops.md) (50002796's men's section: `CategoryRules.sizes_mens`, a product the seller states men's, 2026-11-22) | |

Code: `size_labels.py` (the labels, every garment), `size_chart.py` (the chart), `apparel_sizes.py` (`resolve`,
`chart_html`: the one module the callers import), called by `transform.prepare` (a category with
`CategoryRules.sizes` = a profile's name) and shown by `shopify_payload`. Tests: `test_apparel_sizes.py`; golden
fixtures `fixtures/sizes/<pilot>.json`. Skill `apparel-sizes`.

## How to use

| You see | It means | Do |
|---|---|---|
| `held <key>: size_unmapped ('XXS(3)': not read as a size)`, `('66반': no US size ...)` | a size value no rule reads (a half size sits between two US sizes) | read the product's chart; a brand writes its own letters: a brand row in its profile with its evidence; never a guessed size |
| `held ...: size_unmapped (two Korean sizes on one US size: M (US 8-10))` | two different Korean values land on one US size (95 and 96) | look at the page: a typo (merge by a rule) or two cuts (a brand row) |
| note `size_values_merged: M(66) = M (66)` | one size written twice by the seller | nothing: one value, its rows merged (the buyable row kept) |
| `held ...: size_unmapped (M (66) written twice at two prices ...)` | the two spellings cost differently | look at the page: which is the real price |
| `held ...: size_unmapped (no size option, the chart lists 95, 100, 105, 110: which size is sold is unknown)` | no size option and no size fact, the chart has rows of two sizes or more: one unknown size is sold (13004790971, 2026-11-20) | look at the page: the size is in the title ("블랙, 105") or another listing; never a guessed size |
| `held ...: size_unmapped (no size option, the chart lists S, M, XL, 2XL ...)` from the chart's labels alone | one variant, no size option or fact, the chart names two sizes or more without measures (Nike 13660201494, 2026-11-21: its size S only in the title) | look at the page; never a guessed size |
| `held ...: size_unmapped ('선택하기': colour and size in one value ('Black/090'))` | no size option and one fact joining a colour and a size (Hazzys 13684467368, 2026-11-20): it reached the store as option "Select" | leave it held |
| `held ...: size_unmapped ('선택하기': colour and size in one option ('Ivory/085' ...))` | one option joins a colour and a size ("Ivory/085", "블랙 100 L", and the size first "FREE/그레이", "XL/크림": FREE counts beside another size, 2026-11-21): its values would reach the store in Korean sizes (2026-11-20) | leave it held; splitting the value is not built |
| (read since 2026-11-21) "S(44)모델착용사이즈", "55(S사이즈)", "1사이즈(44-55사이즈)", "2번(66-77)" | a seller's note after the size, 사이즈 in the brackets, a size's number before the women's sizes it fits (the long-sleeve tops pilot: 4 of its first 14 products held) | nothing: `size_labels.parse_label` reads the size; a half size ("1번(44-55반)") still holds |
| `held ...: size_unmapped ('WS': not read as a size)` | an option named a size (사이즈 / size) whose values none reads ("WS / WM / WL", "A.0 / B.1 / C.2", "0호 / 1호 / 2호", "S(상세사이즈 확인했습니다)"): before 2026-11-21 it was taken for no size option and went out raw, no US size | a brand row or a label rule with its evidence; never a guessed size |
| a size reads one up or down from what the photo or chart says | a wrong reading | the product's chart (`fixtures/sizes`), then the rule, with a test |
| no size chart on a product whose page has one | the chart's layout is not read | [SIZE_CHARTS.md](SIZE_CHARTS.md) "When a chart is not read" |
| `product.sizes.chart_conflicts` | a second one-size block nothing ties to a type | the first block is shown; look at the page |
| the owner asks "which Naver size do I order for this US size?" | the link | Shopify admin, the variant: `fairwardgolf.source.sizeKo` (and `optionsKo`); the product: `fairwardgolf.sizes.map` |

## The inputs (what one product gives)

1. **The size option**: found by its values, not its name (13665521998 named "PIL[핑크]" holds XS-L); an option
   named 사이즈 / size, or with most values sizes, is the size option too, and a value of it that does not read holds
   the product (never sent in Korean). A one-value size the transform keeps as a fact ("사이즈: FREE(44-66반)") is
   resolved the same way (`product.sizes.fact`). A label (`size_labels.parse_label`): a letter (XS..XXXL, LL, 2XL),
   a letter range (S/M), a Korean body chest (80..125; one outside the grid holds), a Korean women's size (44 / 55 /
   66 / 77 / 88 / 99, "66반" = 66.5), a range ("55-66", "77~"), a Japanese brand's 0..4, FREE / F / 프리 / ONE SIZE /
   원사이즈.
2. **The seller's chart** in the description text and the images' OCR rows: [SIZE_CHARTS.md](SIZE_CHARTS.md).
   A type option's values (not a size, not a colour) split one-size blocks by type.
3. **The brand** (brand_ko, else the title's first word): a row of the profile's "brands".
4. **The profile** (`CategoryRules.sizes`): its grid, its letters, its measure set.

## The order (one value's US size)

1. the seller's chart writes a **US** size for it (a `US` row): taken as written; a brand row with `system: "us"`
   (PXG) next: its letter is the US letter, a number in brackets beside it ignored;
2. the **value's own number**: "90", "M(90)", "0(85)"; a women's size via the profile's `kr_women` (55 = 90); a range
   gives a range ("L(55-66)" = "S-M (US 4-10)");
3. the **chart's pairing** of a letter with a number ("85 (S)", "Size / XS / S" over "Korea Size / 85 / 90"; a women's
   size too, "55~66(L)"); then the **seller's text** pairing a letter with one women's size ("L[55~66]/XL[77]",
   "M(55), L(66), XL(77)", pairs the OCR glued ("M(55)L(66)", Toosom 12566658191, 2026-11-21), an OCR row "L(55-66) / 48 / 20 / 58" whose measures are not read: `text_pair`,
   2026-11-20); a letter written with two different numbers is not paired, and a women's pairing counts only when
   every bare letter of the option has one (M/L/XL over "L[55~66]/XL[77]": today's letters for all);
4. the **brand row**'s letters (WAAC S = 90); a letter range "S/M" takes both letters' chests;
   bare letters that would all fall to step 5 over a chart whose rows are numbers alone, as many ("S / M / L" sold,
   "호칭 / 95 / 100 / 105" charted): the seller's sizes in order, S = 95 (`chart_position`, Kim Young Joo
   11074837484, 2026-11-20); another count leaves them to step 5;
5. the **profile's letters** (S = 90): the fallback; `basis` says `fallback_letters`.
After the chest is known, a brand row's `us_by_chest` (the maker's own printed US numbers: Superior 085..105 = US
2..10, 2026-11-21, the owner: "re-size by the US") replaces the grid's US numbers for the chests it lists: "S (US 6)",
the grid's letter holding the number, `basis` `brand_us_num:<brand>`.

The letter alone never decides: S is 85 at one seller and 90 at another. The number, matched to the profile's grid
within 2.5 cm, gives the US letter and its US numeric range: "S (US 4-6)".

## What the store gets

- The `Size` option: "S (US 4-6)" ... or "One Size"; values in size order; "Size" is reserved for it (another
  option the translation calls Size becomes "Size 1"). No Korean value on the storefront.
- The variant's `fairwardgolf.source`: `optionsKo` (as always) plus `sizeKo` and `sizeUs`: the order on Naver.
- The product's `fairwardgolf.sizes` (`fairwardgolf-sizes/1`): `map` [{us, ko, chestCm, basis}], `mergedKo`,
  `chartCm` (the seller's chart in cm), `brandRow`, `rules` (`apparel_sizes.VERSION`).
- The description ends with "Size chart (US)" (`apparel_sizes.CHART_MARK`): size, fits (the grid's body band), the
  garment's measures in inches to the half inch (a chest laid flat doubled); built in the payload, never by the
  model; one row per type for a one-size product sold in types. sweep reads descriptions without it. Built in the form
  Shopify stores it (`apparel_sizes._el`: one child inline, several a line each; 2026-11-19: Shopify rewrote the
  table with line breaks and every draft read as changed); a change to that form needs `publish.py --force` for the
  products it touches (the inputs digest does not move).

## Adding a profile (another garment)

1. `size_profiles/<name>.json` (`format: size-profile/1`, `name` = the file's stem): `measures` (a
   `size_chart.MEASURE_SETS` key: read by the code), `kr_women` / `letters` / `grid`, `brands`; `labels` and `fit`
   name the label kind and the body measure of the grid's band, **descriptive only today** (2026-11-19): no code
   dispatches on them. What is fixed for tops now and a new kind must open up, with tests:
   - `size_labels.parse_label` classifies numbers as a chest (80..125), a women's size (44..99) or 0..4; trousers'
     waist (24..36 in, 61..91 cm) or shoes' mm (220..290) need a label kind chosen by `labels`;
   - `apparel_sizes.resolve` matches a number to the grid's `chest_cm`, and `chart_html` prints "Fits bust" from
     `bust_in`; the metafield's `chestCm`: a key per `fit` (waist_cm, foot_mm) and the column's name from `fit`;
   - `size_chart.MEASURE_SETS` gets the garment's set (trousers: waist, hip, rise, thigh, inseam, hem) with its own
     never-read words (밑단 is a top's hem but a trouser's leg opening).
   Never change the tops' readings for another garment.
2. `size_profiles/<name>.md`: the grid and why, its brand rows' evidence, its sellers' habits.
3. `CategoryRules.sizes = "<name>"` on the category; a golden fixture of its pilot's products.

## Changing it

- **A brand that sizes its own way**: a row in its profile's "brands" (matched on brand_ko, else the title's
  first word: a one-letter alias "왁" never matches "왁스") with `aliases`, `letters` (or `system: "us"`) and its
  `evidence` (the product id, what shows it, the date). Then `run_transform.py <shop> --diff`.
- **A rule change**: `UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_apparel_sizes.py`, read the fixture's
  diff value by value (R-TEST-5), then `run_transform.py <shop> --diff` and `store_diff.py <shop>`: resending the
  products already in the store is the owner's word (OWNER_RULES rule 1).

## Not done yet (2026-11-19)

- The buyers' reviews keep their own words ("I usually wear a 66"): not rewritten, the owner's word 2026-11-19.
- The composition from the description and the OCR (the duty by fibre's input): the duty is a flat 12.5 % meanwhile.
