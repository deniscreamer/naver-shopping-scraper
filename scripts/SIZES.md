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
| Profiles today | [womens_tops](size_profiles/womens_tops.md) (knit cardigans 50002797, windbreakers 50002798 and 재킷 50002799, long-sleeve tops 50002796), [mens_tops](size_profiles/mens_tops.md) (50002796's men's section: `CategoryRules.sizes_mens`, a product the seller states men's, 2026-11-22), [womens_bottoms](size_profiles/womens_bottoms.md) (skirts and culottes 50002802, by the waist: `key: waist`, `pick: band`, a waist read only for it, 2026-11-22), [womens_pants](size_profiles/womens_pants.md) and [mens_bottoms](size_profiles/mens_bottoms.md) (Golf Pants 50002801, 2026-11-23: the women's by the skirts' grid with the trousers' measures; the men's and unisex by the US waist, "W32", `CategoryRules.sizes_mens` / `sizes_unisex`; no gender stated holds) | |

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
| `held ...: size_unmapped (no size option, the chart lists 95, 100, 105, 110: which size is sold is unknown)` | no size option and no size fact, the chart has rows of two sizes or more: one unknown size is sold (13004790971, 2026-11-20) | look at the page: the size is in the title ("블랙, 105") or another listing; never a guessed size. Read since 2026-11-24 (`transform.title_size`): one variant, no option, the title is the listing's name plus "colour, size", the size with a number (a letter alone not), a model name ending in another size leaves it unread |
| `held ...: size_unmapped (no size option, the chart lists S, M, XL, 2XL ...)` from the chart's labels alone | one variant, no size option or fact, the chart names two sizes or more without measures (Nike 13660201494, 2026-11-21: its size S only in the title) | look at the page; never a guessed size |
| `held ...: size_unmapped ('선택하기': colour and size in one value ('Black/090'))` | no size option and one fact joining a colour and a size (Hazzys 13684467368, 2026-11-20): it reached the store as option "Select" | read since 2026-11-24 when one variant and the size has a number (`apparel_sizes.single_joined`: "Dark Navy/090" -> fact 090, halfclub 12487907002, 13291281940, 13684467368); adidas' "AL (110)" since 2026-11-25 only when the product's own "주문사이즈" table pairs L with (110) (9998916822); a letter alone ("CW4742 화이트 L"), another adidas pair or several variants: leave it held |
| `held ...: size_unmapped ('선택하기': colour and size in one option ('Ivory/085' ...))` | one option joins a colour and a size that `transform._split_joined` could not split: a second size word in the rest (read since 2026-11-24 when each number has one rising letter: "오프화이트 85 XS"), adidas' Asian letters (a bare "AXL" or one with two numbers; "AL(95)" read since 2026-11-24), another option holding sizes already. Since 2026-11-22 (the men's tops pilot, 20 apparel products freed with the label shapes below) a joined option ("Ivory/085", "화이트_95", "모찌/S", "남성 골프 이너웨어__블랙 95", "FREE/그레이") is split: the colour stays, a new option 사이즈 holds the size | leave it held |
| (read since 2026-11-24) "30(당일발송)", "30당일발송)", "9부 S" beside "S", "블랙34", "151(블랙)30" | a shipping note after the size (`parse_label` drops it; one size with the bare "30", merged); a trousers' length before the size (`split_length`: an option 기장, 9부 / 10부, a bare size's 기본; past Shopify's three options it joins the option before it, "01_일자핏 9부", `transform._fold_length`); in a waist profile a waist or a letter glued to a Hangul colour or ")" (`_words`: split like "블랙 34"). The Golf Pants drafts' review: 6486608544, 10107163054, 4954391160 were held | nothing |
| (read since 2026-11-24, the size_unmapped review: 25 products) "LL(105호)", "75(44/S)", "85(XS.44)", "46(90)", "XL(100-여성77이상/남성M)", "WS", "FREE(44~55)모델착용컷", "AL(95)", "AS (85)" (tops); "46", "S(75) .. 2XL(95)", "A82 (32인치)", "33-30" (men's trousers); "2XL(32~33)", "M(26반~27)" (women's trousers); "블랙하운드55", "긴팔55", "화이트-S", "오프화이트 85 XS"; "L" beside "L（66사이즈）"; a fact "블랙(free)" | `size_labels.parse_label`: a letter with its chest in 호, LL / 3L too; a head number with a women's size and a letter in one bracket (the head dropped); a European 46..54 with the chest in brackets; who the chest fits after a dash (여성 / 남성 only); W and a letter; adidas' Asian letter with its chest (outside the waist profiles; each letter one number and each number one letter, else held: 5176506757); the men's waist to 46 in (the 4XL band W41-46); a women's waist profile's inch range up to 3 apart. `apparel_sizes`: a letter ladder in cm from under 80 in the men's trousers is a waist (`_waist_ladder`); adidas' "A82 (32인치)" is its inch, two codes on one inch never merge (`_resolve`); "33-30" a waist and an option 기장 "기장30" (`split_waist_length`); a women's size glued to a Hangul word, a letter after a Hangul colour and a dash (`_words`); "colour number letter" split by the number, held when the seller's letter disagrees (`number_letter_split`, `transform._sizes`); a bare letter sized by the chart's or text's pairing beside its numbered spelling on one US size merged (`_merge_bare_letter`). `transform`: one sleeve word before every size of a size option dropped (`_split_joined`); "블랙(free)" as a size fact is One Size (`_sizes`) | nothing; a set of SIMPLE options (7512705748) still holds (a bare "A79" and a women's model in a men's product: read since 2026-11-25, the row below) |
| (read since 2026-11-25, the size_unmapped review's second pass: 24 products) a top sold with trousers, a jacket or a summer cooling top as a design, a pants listing selling a polo, a tee, a belt or shorts (13762280030, 9177463189, 9068863945, 9037071653, 13740610318, 12659358151, 9435597606; 5534297375, 11017948766, 5815131892); "85(33)" beside "85(35)", "85(34)" beside "88(34)" (adidas trousers); a mixed product whose every size value is one gender's (7266270685, 6485458095, 8325761055); "남성용 XXL (여성용 88)" in a women's rain coat (5691897960); "라지(L)" / "프리(F)" and the chart's "F-프리(55~66)" with the tip "엑스라지(XL)사이즈 - 88이상" (7965635614); "25-27인치 free" over "FREE（44-66반）" / "XL（통통66반이상）" (5282622633); "S(55), M(66), L(77)" over the chart's "M(55) / L(66) / XL(77)" (9317474764); "L(28~29)" twice beside the chart's "L(27~29)" (12370291326); "XXS사이즈(약80)" (5460564989); "4XL" (11859489664); adidas' bare "A79" by the "주문사이즈" table (11493370731), "AL (110)" by its own table (9998916822), "82" and "M(32)" of two models (10076109143); a women's model's rows in a men's product (5489884876) | `transform._drop_off_section` (`CategoryRules.variant_drop`: 50002796 trousers, outerwear, cooling; 50002801 other_item, shorts; the rows left out before the cap, note `off_section_variants_left_out`; every row matching: held `off_section_variant` as before; two garment kinds or makers kept under the option: no size chart, note `size_chart_left_out`); `apparel_sizes._cm_inch_collisions` (men's trousers: one cm with two inches, the other spelling takes the cm_round inch, each its own Korean value (never merged since the second review), one US waist only through `combos`; two cm on one inch: the other takes its cm_round, `basis` `cm_round`); `transform._sizes_by_gender` (each gender's values on its own profile, "Women's S (US 4-6)" / "Men's M", `chart_html` by each value's profile; a value of both genders or unisex, or a hold: held since the second review, the trousers sized as men's); `transform._drop_both_genders` (the 성별 row and the title one gender) and `_words` ("M (55)" one word outside the waist profiles); `parse_label` (a Korean size word with its letter, "<letter>-<word>(<range>)", "N이상", "XXS사이즈(약80)"), `tip_floors`, a FREE beside other sizes takes its chart row's range, the "<lo>-<hi>인치 <letter or free>" line (`waist_text_pairs`, key FREE), `size_line`, `_ladder_pick`, "4XL" where the profile has it (mens_tops 120); `order_pairs`, `_adidas_codes_split`, `single_joined(pairs)`; `resolve(combos=...)`: one US waist for two models' spellings when no choice of the other options sells both (never merged; the Size option shows it once); `transform.options_and_variants(leave_out_model=...)`, note `womens_model_left_out` | nothing; a resend of the products already in the store is the owner's word (OWNER_RULES rule 1) |
| (2026-11-25, the two reviews of the second pass and the owner's yes answers) `held ...: size_unmapped (a mixed product whose size values are not each one gender's ...)`, `(a mixed product in a category with no men's size profile ...)` | a product with men's and women's variants whose sizes cannot be split by gender (Dennis 11287527628's 090..110 under both genders' models, Malbon 12375182812 unisex): sold on the women's profile the men's "110" read as a women's XXL | leave it held: never sized on one gender's profile (`transform._sizes_by_gender`; the trousers, sized as men's by the owner's 2026-11-23 rule, keep the one profile) |
| `held ...: size_unmapped ('2XL' XL-XXL (US 16-18) (chart_pair) overlaps 'XL' XL (US 16) (fallback_letters): one ladder read two ways)` | two neighbouring letters read two ways whose US sizes overlap (티앤드 5587004670: the OCR misread "XL(31~33)", 2XL took another style's chart row) | look at the page; never a guessed size (`apparel_sizes._ladder_broken`) |
| note `size_chart_left_out` (two models' sizes on one US size; adidas' Asian letters; a gender's rows not told apart) | the sizes are sold, the chart is not shown: two models' spellings share a US waist (10076109143; one cm written two ways, "85(33)" / "85(35)" 5815131892, keeps its row), the owner's adidas letters (the charts' numbers differ by model), or a mixed product's tables have no gender headings ("여성용" / "남성용 상세 사이즈": each gender's rows only from its own table, 8325761055); the genders' chart marks disagreeing (None included) are "mixed" (read by the number) | nothing; a chart wanted: the seller's table with its headings |
| adidas' Asian letters on a men's top: "AS" .. "A2XL" bare after a colour ("KG2154 화이트 AS", 13740514016), "AM (100)" beside another model's "AM (105)" (5176506757), the fact "AL (110)" (9998916822) | the owner, 2026-11-25: AS = 95, AM = 100, AL = 105, AXL = 110, A2XL = 115, the letter winning over the number in brackets: S / M / L / XL / XXL (`mens_tops.json` brand row `adidas`, `asian_letters`; the bare letters split from the colour only by that row; two models' "AM" share M through `combos`, each its own Naver value; no chart) | nothing; the women's tops ("AS(85)") keep the number; adidas trousers' A-codes are not this row (8116691038 stays held: IU2823's "A82 (32인치)" contradicts its own chart, 33) |
| `<shop>/variants_by_owner.json`, notes `variants_left_out_by_owner` / `variants_by_owner_unused` | the owner leaves a style whose sizes the seller writes inconsistently out of one product (2026-11-25: 8191027841's basic joggers -> W30..W40; 7455950253's 사선포켓 and 밀리터리 -> "30" / "30(XL)" W30 .. "40(6XL)" W40, "36(4XL)" .. "40(6XL)" read as the waist in the men's trousers; 6033600342's 기모 / 밍크기모 -> S XS (US 0-2), M S-M (US 4-10), L M-L (US 8-14), XL L-XL (US 12-16), the recommendation's second line of body sizes the letters' upper ends, `letter_cells`) | an entry only on the owner's word ([TRANSFORM.md](TRANSFORM.md) "The owner's variants left out"); then `run_transform.py <shop> --diff` |
| the same file's `sizes` block, notes `sizes_by_owner` / `sizes_by_owner_unused` | the owner's answer on how one held product is sized (2026-11-25, one product each, never a rule): `gender` "men" / "women" (adidas 9069946345 men's -> mens_bottoms, 76..92 = W30, W31, W32, W33, W34, W36), `read_as` {value: label} (WAAC 11814351207 2 / 3 / 4 read as S(90) / M(95) / L(100) -> S (US 4-6), M (US 8-10), L (US 12-14); Nike 13660201494's S read as XS -> XS (US 0-2), the womens_tops grid's XS = chest 85, US 0-2), `size` (12994831966: the title's 110 sold, its 모델명 ends 95 -> XXL (US 18)), `same_as` {value: value} (아크나인 7496732129: the winter type's bare S..XL merged into the 간절기 S(25~26인치)..XL(31~32인치), XS-S (US 0-6) .. L (US 12-14)); the value ordered (`sizeKo`, `optionsKo`) stays the seller's own | an entry only on the owner's word ([TRANSFORM.md](TRANSFORM.md) "The owner's sizes of one product"); then `run_transform.py <shop> --diff` |
| (read since 2026-11-25, the owner: "Все рекомендации", rainwear 50002816's size_unmapped) a Japanese maker's "O" / "XO" beside S / M / L (TaylorMade TL439 11859686166, 11534592689; UN003 12166562599), "SS" in a ladder to LL / 3L (Callaway C25989100 11616404746), "블랙ㅡXXL" (the Hangul ㅡ as a dash: 5706906040, 6672050974), "남성용-그레이L(100)" / "여성용-핑크M(66)" (Kasco KSRWL-002 505840359) | `size_labels.japanese_ladder` (opened by `apparel_sizes.resolve` for an option that holds the ladder, the chart's labels read the same way): O = XL, XO = XXL when the option holds two of S / M / L and no XL / LL / XXL / 3L (the seller: "O, LL = 한국 표기 XL / XO, 3L = 한국 표기 2XL"; TL439's body chart gives XO the chest of O, a typo, and is never read: 신장); SS = XS when it holds S and LL or 3L, no XS. Men's TL439 M..XO = US S, M, L, XL (11534592689's S = XS); women's UN003 S..O = S (US 4-6) .. XL (US 16), its chart's O column the XL row; Callaway SS..3L = XXS, XS, S, M, L, XL. `apparel_sizes._words`: ㅡ after a Hangul word and before a letter size that ends the value is a "-" (a number after it, "블랙ㅡ 95", keeps the space split). `transform._gender_colour_split` (`apparel_sizes.gender_colour_split`): the option split into 컬러 and 사이즈 "남성 L(100)" / "여성 M(66)", sized per gender (`_sizes_by_gender`: Women's M (US 8-10), Women's L (US 12-14), Men's M); each variant keeps the seller's whole value as `naver_options_ko` (optionsKo) and as `naver_size_ko` (sizeKo: "남성용-그레이L(100)", the value the owner orders on Naver; never the split "남성 L(100)", which Naver has not) | nothing; 11616404746 is a copy of draft 11859779078 (dedupe / parking holds it), 5706906040 is no golf garment (the store review's) |
| `held ...: size_unmapped (one chest for every size (62, 62, 63 cm): the letters L, XL, XXL are no chest sizes)` | bare letters every one of which would fall to the profile's chests while the seller writes one chest for each size, one number a line, as many lines as sizes, within 1.5 cm (`apparel_sizes.one_chest`, 2026-11-25): the letters are heights or lengths of one garment (6672050974's and 5029519026's EVA coat: L / XL / XXL for 150-165 / 165-175 / 175-190 cm, each "가슴:62" / 62 / 63) | leave it held: no US size is in the data; a body range ("가슴 104-112") or a row of cells is never such a line |
| `held ...: size_unmapped ('선택2': a second colour and size ('베이지M' ...): a set of two (1+1))` | after the split another option still joins a colour and a size: two garments a variant (내추럴모드 10821435743, 2026-11-24: "1+1구매시 ... 1장당") | leave it held: a set of two is not one pair |
| `held ...: size_unmapped ('S 95사이즈': not read as a size)` before 2026-11-22 | read since then: the chest after a bare letter ("S 95사이즈", "S 95~100사이즈"), "about" ("XS (85 전후)"), a gender before the size ("여성 55(M)"), a Korean letter word ("라지", "미디움", "스몰"), a note in brackets ("S(모델착용사이즈)", "S(상세사이즈 확인했습니다)") (`size_labels.parse_label`) | a new shape: a line in `parse_label` with a test |
| (read since 2026-11-21) "S(44)모델착용사이즈", "55(S사이즈)", "1사이즈(44-55사이즈)", "2번(66-77)" | a seller's note after the size, 사이즈 in the brackets, a size's number before the women's sizes it fits (the long-sleeve tops pilot: 4 of its first 14 products held) | nothing: `size_labels.parse_label` reads the size; a half size ("1번(44-55반)") still holds |
| `held ...: size_unmapped ('A.0': not read as a size)` | an option named a size (사이즈 / size) whose values none reads ("A.0 / B.1 / C.2", "0호 / 1호 / 2호"; "WS / WM / WL" read since 2026-11-24, 13483086996: W and a letter is the letter): before 2026-11-21 it was taken for no size option and went out raw, no US size | a brand row or a label rule with its evidence; never a guessed size |
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
   원사이즈; a letter with the free word in brackets ("L（FREE）", a one-size poncho, 2026-11-24) is one size; a letter
   with its chest in 호 ("S(90호)", "LL(105호)", "3L(110호)": Titleist Japan, 2026-11-24) is the letter and that chest;
   a Japanese maker's O / XO beside S / M / L (XL / XXL) and SS in a ladder to LL / 3L (XS) only inside that option's
   ladder (`size_labels.japanese_ladder`, 2026-11-25).
2. **The seller's chart** in the description text and the images' OCR rows: [SIZE_CHARTS.md](SIZE_CHARTS.md).
   A type option's values (not a size, not a colour) split one-size blocks by type.
3. **The brand** (brand_ko, else the title's first word): a row of the profile's "brands".
4. **The profile** (`CategoryRules.sizes`): its grid, its letters, its measure set.

## The order (one value's US size)

1. the seller's chart writes a **US** size for it (a `US` row): taken as written; a brand row with `system: "us"`
   (PXG) next: its letter is the US letter, a number in brackets beside it ignored;
2. the **value's own number**: "90", "M(90)", "0(85)"; a women's size via the profile's `kr_women` (55 = 90); a range
   gives a range ("L(55-66)" = "S-M (US 4-10)"); in a waist profile a cm size takes the **seller's inch**: its own
   "77(29)", its chart column's "77(29)" over the bare "77", or an 인치 row under the 호칭 row (`basis` `chart_inch`,
   2026-11-24: Kim Young Joo 5912038354 sold 77 as W30, JDX 10694535049 92 as W36), never cm_round; two cm sizes the
   chart gives different inches never merge (86 = 34, 88 = 35); the seller's body waist in inches beside a women's
   size ("S (55)" under "S / M / L" over "25-26 / 27-28 / 29-30", 11318914118; "55(25-26),66(27-28)", Toosom
   4716253463) wins over `kr_women` when every such value has one (`text_waist`);
3. the **chart's pairing** of a letter with a number ("85 (S)", "Size / XS / S" over "Korea Size / 85 / 90"; a women's
   size too, "55~66(L)"); then the **seller's text** pairing a letter with one women's size ("L[55~66]/XL[77]",
   "M(55), L(66), XL(77)", pairs the OCR glued ("M(55)L(66)", Toosom 12566658191, 2026-11-21), an OCR row "L(55-66) / 48 / 20 / 58" whose measures are not read: `text_pair`,
   2026-11-20; "S(44사이즈)", a chart row "M / 보통55 / 91", a line of letters over a line of women's sizes "~마른 55 /
   보통55 / 보통66 / 통통77" with the body words dropped: `letter_cells`, 2026-11-24, 10997837767, 6033600342); a
   letter written with two different numbers is not paired, and a women's pairing counts only when
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
  `sizeKo` is the seller's own value: the variant's Naver value of the size option (`naver_options_ko` when a merge
  changed it), or the whole value a colour and a size were split from (`naver_size_ko`, 505840359, 2026-11-25).
- The product's `fairwardgolf.sizes` (`fairwardgolf-sizes/1`): `map` [{us, ko, chestCm, basis}], `mergedKo`,
  `chartCm` (the seller's chart in cm), `brandRow`, `rules` (`apparel_sizes.VERSION`).
- The description ends with "Size chart (US)" (`apparel_sizes.CHART_MARK`): size, fits (the grid's body band), the
  garment's measures in inches to the half inch (a chest laid flat doubled); built in the payload, never by the
  model; one row per type for a one-size product sold in types. sweep reads descriptions without it. Built in the form
  Shopify stores it (`apparel_sizes._el`: one child inline, several a line each; 2026-11-19: Shopify rewrote the
  table with line breaks and every draft read as changed); a change to that form needs `publish.py --force` for the
  products it touches (the inputs digest does not move).

## Shoes (`shoe_sizes.py`, 2026-11-25)

Golf shoes (50001740, `CategoryRules.shoe_sizes`) do not use the garment profiles: a Korean shoe size is the foot
length in mm. The owner's chart (2026-11-25): men's 250 = US 7, 255 = 7.5 ... 280 = 10, 290 = 11, 300 = 12 (US =
(mm - 180) / 10); women's 220 = US 5 ... 250 = 8, 260 = 9 (US = (mm - 170) / 10).

| You see | It means | Do |
|---|---|---|
| `US 9 (270 mm)` / `US 8 (250 mm)` | a pair stated men's / women's (the 성별 row, the title, the variants) | nothing |
| `US M 9 / W 10 (270 mm)` | a unisex, mixed or unstated pair; a mixed pair whose every size value is one gender's (FootJoy's "XW 240" men's, "W 220" women's, 10239862675) takes each value's own label | nothing |
| `US 9 Wide (270 mm)`, `Extra Wide` | a width word beside the size (와이드, 광폭, 2E / 3E / EEE; FootJoy's W / XW right before the number) | nothing |
| `held ...: size_unmapped ('free': not read as a size in mm)`, `(no size option ...)`, `(two Korean sizes on one US size ...)` | a value without a size in mm (a US size alone, a colour joined), no size option, two spellings of one size | look at the page; a new shape: a line in `shoe_sizes.mm_of` with a test; never a guessed size |
| (read since 2026-11-25, the men's pilot) "JQ0993 화이트실버 245", "51143 W 화이트실버 245", "블랙(01001)_250" (adidas SPW 13103847433 / 13335983300, FootJoy Versafit 11886292855, ECCO 9887518096); since 2026-11-26 "(화이트그레이)250", the brackets dropped (FootJoy Flow 2.0 11442646718, New Balance 574B 12148138149); "255~260"; "스크래치 280" (MNX15 5402813627) | a colour or code and its size in one value: split into 컬러 and 사이즈 (`transform._split_joined_shoes`, `shoe_sizes.split_joined`; the seller's whole value stays `naver_size_ko`, the value ordered); one size covering two, "US 7.5-8 (255-260 mm)" (`mm_span`); a scratched, display or returned pair beside the sound ones left out (`shoe_sizes.SECONDS_RE`, `transform._drop_shoe_seconds`, note `seconds_left_out`) | nothing |
| (2026-11-25, the men's pilot's lens review) `US W 7 (240 mm)` beside `US M 7 (250 mm)`; a unisex title over a men's row; "51143 W 화이트실버 245"; "스파이크유무: 스파이크"; an option 스크래치상품 | a mixed product whose every size value is one gender's marks each (4978188842 "230 [여성용]", 8469384993 "여성225", 6289723254, 10239862675: a US number never shown twice unmarked); the title or the row saying unisex beside one gender gives both labels (13575338957); FootJoy's width after the style code goes with the size (11886292855); a spiked variant left out (note `spiked_left_out`, 11574034936); every pair a second: held `seconds` (4767184925) | nothing |
| `held ...: gender_vs_sizes (stated men's, sold only up to 245 mm)` | the title's or the row's gender contradicts the sizes sold | look at the page; ask the owner |
| placement flag `by_sizes`, evidence source `sizes` | the section was chosen by the sizes (`shoe_sizes.section_gender`): one section a pair; a unisex, mixed or unstated pair by its largest size, 270 mm or more men's, 250 mm or less women's, between: unisex / mixed men's, unstated unknown (placement holds it) | nothing; a pair in the wrong section: the owner's word |

The store gets the same as a garment: the `Size` option in US sizes, `sizeKo` the seller's own value, the product's
`fairwardgolf.sizes` (`kind: shoes`, `map` [{us, ko, basis: mm}]), and the description's "Size chart (US)" block:
the US size, the foot length in mm and in inches (`shoe_sizes.chart_html`). Tests: `test_shoe_sizes.py`.

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
- (2026-11-24) A women's letter is not sized by the chart's garment waist laid flat (doubled): on banded golf pants it
  is the band at rest, under the body it fits (4882015244: a 27-inch model wears the S of flat 32 cm, which would read
  "XS (US 2)"; 7073230788 S flat 30). A seller's "runs small, size up" / "tight, order one up" note (5611833883,
  10188121271) or "if you wear 30 pick 78" (JDX 10871474799) is the owner's to weigh: never a size change by itself.
