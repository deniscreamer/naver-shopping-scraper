# Package weight and size

The five package fields of every variant (the product's weight, the package's weight and its three sides), the
category defaults (the agent's since 2026-11-26) and the owner's baselines, and the optional stage that reads the description images (OCR) for
them; split from TRANSFORM.md on 2026-11-16 (history: `git log --follow scripts/TRANSFORM.md`, and
scripts/README.md before it). Measurements and history are at the end.

## How to use

The five fields are on every prepared variant: `product.variants[].package` in
`scripts/output/shops/<shop>/prepared/products.jsonl` (written by `run_transform.py`, [TRANSFORM.md](TRANSFORM.md)).
Read one product's fields (offline):

```sh
grep '"key": "<key>"' scripts/output/shops/<shop>/prepared/products.jsonl | python3 -c \
  'import json,sys; p=json.load(sys.stdin); [print(v["sku"], k, f) for v in p["product"]["variants"] for k, f in v["package"].items()]'
```

Each field says where it came from (`source`) and how sure it is (`confidence`, 1-5: [Confidence](#confidence)):

| `source` | what it is | what to do |
|---|---|---|
| `source_stated` | the seller's own value from the server's `/products/specs` `measures` (`quote`, `binding`, `kind`) | nothing: it is never overwritten; a wrong one is the seller's (`compared` shows what the description says) |
| `description_image` | a statement read in the description images or the typed text (`from: description_text`), with `quote` | check `quote` against the image when it looks odd: [Reading the description](#reading-the-description-the-guess) |
| `composed` | built from the set's parts with the operator's baselines: `how`, `parts`, `baseline` | read `parts` (which part was stated, which a baseline): [The order of sources](#the-order-of-sources) |
| `category_default` | the flat category default (`low` / `central` / `high`), confidence 1: the composition is unknown | normal for a product that states nothing; many of one category: the description images stage did not run, the row has no `baselines`, or the category needs a parts profile |

Flags and notes that ask for a look:

| seen | means | do |
|---|---|---|
| flag `below_stated_product` | a default package weight under the seller's product weight | nothing; with the row's `baselines` the transform makes it the product weight + the carton |
| flag `below_contents` | a stated packed weight under the seller's own product weight (left only where the product weight is not sent above it: [No product weight above the package](#no-product-weight-above-the-package)) | the owner decides (two statements of the seller) |
| `compared.rejected: implausible_for_count` | the listing's one weight is another count's (a pair's on a 3-wedge set) | nothing: [A weight against the variant's count](#a-weight-against-the-variants-count) |
| `compared.rejected: above_package`, flags `item_weight_as_packed`, `capped_to_package` | a product weight above the package's | nothing: [No product weight above the package](#no-product-weight-above-the-package) |
| flag `container_assumed` | nothing says whether the bag ships: the baseline bag is counted | nothing: the heavy side, on purpose (the owner 2026-11-11) |
| `compared.rejected`, `refused` | a value outside the band, or over 3x today's (`far_above_today`) | nothing: [Absurd values](#absurd-values) |
| note `description_images_missing` | the category reads its images, this product has no sidecar | run `description_images.py <shop>`, then `run_transform.py <shop>` |
| note `description_images_stale` | the sidecar was read from other links | the same: run the stage again |
| note `description_images_failed` | the worker failed twice: an error sidecar | `description_images.py <shop> --products <id> --force` |
| note `description_images_partial` | some images not read: `failed` (5xx / network), `gone` (4xx / not an image), `refused` (a hotlink block) | nothing; `failed` ones are read again at the next run of the stage |
| note `measures_from_images` | fields stated in the images / typed text or composed, per variant count | nothing: information |
| note `weights_bound` / `weights_unbound` | the stated weights bound per variant (count per weight and way) / variants left at the heaviest (`conflict`, `unbound`) | nothing: information (the owner decides any republish) |
| `CategoryDefaultsMissing` | the category has no row in `category_measures.json` | write the row yourself (the agent's since 2026-11-26: ONBOARDING.md E1): [Category defaults](#category-defaults-category_measuresjson) |

The stage's own exits (`description_images.py`): 0 done (the counts printed); 2 `stop:` the shop has no rules, or the
shop is busy (a job or another command holds its lock: wait, `job.py status`); 3 Naver's image CDN refused (403 /
429: the sidecars so far are kept, wait and run again); 4 another run of the stage holds the shop; 130 stopped by
Ctrl+C (run again to go on). Commands and files: [The description images stage](#the-description-images-stage).

A category default is the agent's (the owner, 2026-11-26): written from the probe and the pages, then refined on the
pilots of 5 and 30 from the real products' stated weights and sizes, or the reader improved where a page states
them and it missed them (ONBOARDING.md part E); each change dated in `category_measures.json` with a new
`defaults_version`. A baseline stays the owner's. A change that reaches published products:
[OWNER_RULES.md](OWNER_RULES.md) rule 1.

## The five fields

`/products/specs` `measures` holds the seller's weight and size candidates (server: `naver_shopping/measures.py`,
contract in ENDPOINTS.md). `package_measures.variant_measures(specs, load_table())` turns them into five fields per
variant: `product_weight_g` (net or unspecified, never a part's; in a set only the whole set's), `package_weight_g`
(only a weight with the package), `package_length_mm` / `package_width_mm` / `package_height_mm` (only a triple marked
as the package, longest side first). A value belongs to a variant when its binding is the product or names that
variant; values that disagree are a contradiction and are not taken. Values within 2% agree (6.35 kg and 14 lb are one
weight). A set weight stated per composition is each variant's own (6630856593: 11.5 kg on the 12-club variants, 4.7
kg on the 4-club ones). Parts' weights (club spec tables) are never added up into the set's: their sums leave out the
bag and covers. A default package weight below the seller's product weight is kept but flagged `flags:
["below_stated_product"]` (at collection; in the transform, with the row's `baselines`, that package weight becomes
the seller's product weight + the carton). A table row may carry `plausible: {field: {min, max}}`, the operator's band: a stated value
outside it is not taken (`contradiction`, `reason: implausible_for_category`) and the default fills the field; a box
is one statement, so one side out of its band refuses the other two (`box_not_whole`, 2026-11-17). A band given after
a line's collection reaches it when it is prepared again (`package_measures.current_bands`, before `current_defaults`;
2026-11-18, the chipper row's band and 7004743758's notice 962 g). Two rows have a
band since 2026-11-17 (table version 7; the agent from the data on the owner's delegation, the wedge-set
review, commit 2f2262f): 50002783 웨지, product 800-3500 g, package 1000-4000 g, box height
40-400 mm (a set of 2-6 wedges: a one-club weight or box on a set's page, 0.45 kg, 1.04 lb, 13 mm, is refused);
50002787 주니어용클럽, product 150-8000 g, package 300-10000 g (13586027489's "529 Pounds"); since 2026-11-18 (table
version 9) 50002784 치퍼, product 300-650 g (7004743758's 962 g, a shipping weight); since table version 10
(2026-11-18) product 350-600 g, package 350-5000 g, length 850-1500 mm (a head's 330 g, a parcel too small for the
club). None is made up.
Why these (2026-11-17): the 800 g low is 2 x the single club's 400 and sits in the data's gap (726-1090 g: 25
one-club readings refused, 47 sets taken; 900-2800 would refuse 13480790720's 2840 g while its twins pass); the
package low is 1000, not 1500 (1500 refuses 16 real boxes of 1110-1470 g, Yamato 2PCS, BombTech / Detroit / XINGGM
52/56/60, and the C09 and C10 paths would disagree; with 1000, 33 live prices fall, none rises); the height low is 40,
not 50 mm (real boxes of 46 mm, 13372276089, and 48 mm, 13370268119); 50002787 has no height band (real junior
single-club boxes are 12.7-20 mm: 13388597147, 13369106775, 13381488170); no length or width band (not delegated;
13163078346's 407 mm was tees, held `not_wedge_set`). A row may also carry **`baselines`** (the owner, 2026-11-10), the operator's
amounts for the parts of a set of like items in a container; all of them or no block (`check_row`):

| key | what | 50002788 (the owner, 2026-11-10) | basis |
|---|---|---|---|
| `item_g` | one item (a club) | 340 g | the median of the sellers' club tables (332 g) over the 120 sets |
| `container_g` | the container (the bag) | 3800 g | the median of the 11 bag weights sellers state (2.6-4.8 kg) |
| `carton_g` | the box and its packing | 2000 g | a Callaway Edge 10-club set: clubs 3.7 kg, boxed 6 kg |
| `longest_item_mm` | the longest item (the driver), when its length is not read | 1140 mm | the 118 stated drivers are 1105-1168 mm |
| `length_margin_mm` | the box's length over the longest item | 100 mm | the one stated box, 121 cm, against its 111 cm driver |
| `sides_mm` | the box's [width, height] without the container | 200 x 160 mm | that stated box, 20 x 16 cm |
| `sides_with_container_mm` | the same with the container | 400 x 320 mm | the caddie bags stated on 4 sets, 39-40 x 31 cm |

plus `approved_by`, `approved_at` and `basis` (where each amount comes from; the owner: approximate until the first
real shipment, low certainty). With the block a field the seller does not state is **composed from the set's
parts** and the row's flat averages are the last resort (see "The order of sources" below); a row without the
block composes nothing: a field is the seller's statement or the flat average. No amount is ever made up in
code. The table's `version` is 2 since the block.

## Category defaults (`category_measures.json`)

A missing field comes from
`category_measures.json`, the category defaults (the agent's, ONBOARDING.md E1; per leaf category: low / central / high of the five fields, who
approved it and when, the table's version), as `source: category_default`; a seller's value is never overwritten.
No row for the category: `CategoryDefaultsMissing`, the run stops: the agent writes the row from the probe and the
pages (ONBOARDING.md E1; never a number without a source) and reviews it on the pilots. Every row carries `reliability`; today one level, `estimated_average` (the weakest: an average of estimates,
not measured); the price rule's coefficient goes by the lowest `confidence` of the box's three sides, not by this (see PRICE.md, The price).
50002788 풀세트 is filled (owner, 2026-11-05):
the median (central) and about the 10th / 90th percentile (low / high) of the naver-harvester's AI estimates on the
55 fairwardgolf sets in Shopify, sets with and without a bag together (none of their values was seller-stated).
50002787 주니어용클럽 (owner, 2026-11-11) holds single clubs and sets, so its row has **two defaults**: the row's
own fields are a junior set's (105 x 28 x 25 cm, 4.5 kg central) and its `kinds` entry `single_club` a single
club's (90 x 12 x 10 cm, 1 kg). `default_kind()` takes the kind per variant: a club word (퍼터, 드라이버, 아이언, ...)
in the title and the variant's words with no set word (세트, N종, N개, 가방, 구성, ...), or 단품 in the variant's
own words, or a variant that names one club when the title has no strong set word (풀세트, N종, N개, 구성, a bag); a
set word otherwise keeps the set's box, the larger one. The title and the variant are read apart ("...클럽" +
"6~8세" is no count). Such a default carries `kind`. The table's `version` is 3 since that row. A kept run is never
rewritten, so the transform takes each default as today's table gives it (`current_defaults`): a changed row
reaches the product when it is prepared again; a default already today's stays as collected.
50002670 아이언 (owner, 2026-11-14), sold as women's iron sets: a set of 5-8 irons in a carton, no bag (100 x 25 x
12 cm, 3.5 kg central), and a `single_club` kind (98 x 11 x 8 cm, 1 kg) for an iron sold alone (단품 with no set word
or count); singles are left out by the title screen, so the kind is for one that slips through. Version 5 since.
50002783 웨지 (owner, 2026-11-15), sold as wedge sets: a set of 2-3 wedges in a carton, no bag (98 x 20 x 10 cm,
2.2 kg central), and a `single_club` kind (96 x 11 x 8 cm, 1 kg) for a variant that sells one wedge of a set-or-single
listing (단품, 개별, 싱글, 낱개 in the variant) or 단품 in a title with no set word; single-wedge titles are left out by
the title screen. Version 6 since. Version 7 (2026-11-17, the agent from the data on the owner's delegation,
the wedge-set review C16, commit 2f2262f): the count kinds `two_wedges` (98 x 15 x 10 cm, 1.7 kg, wedges 920 g: the variable box, -$30 to
-$40 a variant at level 1) and `four_plus` (the base box, 2.65 kg, wedges 1840 g: no price change), after
`single_club`. The base 3-wedge row was kept on purpose (C16-a): the measured Amazon boxes (median 99 x 11.5 x 6.3 cm,
p90 107 x 17.8 x 10.2, at most 3.86 kg, Kirkland) are imports' only, no Korean seller's, and lowering it would cut
about 364 live prices. Rejected: two_wedges at Yamato's 99 x 11.4 x 5.3 (one box; a level-1 default covers the p90),
98 x 17 x 10 (-$10, a 3-wedge width), four_plus at 102 x 22 x 12 (+$50; both measured 4-wedge boxes fit the base), a
general "package = stated product + carton" (C16-d: it moves every category; the owner's 2026-11-05 flag
`below_stated_product` stands); Hireko's 122.6 cm box is an outlier (it would cross FedEx's 121 cm length line). A count kind carries `lofts` [min, max]: the variant's own count (2개 / 2종 / 2P / 2pcs / 2피스 / 2자루 /
2본; 4-6 for four_plus) or that many distinct lofts in its value ("56 60 Degree Tarnish", not a range "52-56", not
"52개"), else the title's count when the listing has one variant or every variant names as many lofts; never the
title's own list of lofts, never with a larger count, 단품 / 개별 / 싱글 / 낱개 or a bag anywhere. In doubt the base
3-wedge box. A variant value Naver cut at 25 characters ("Black Titanium Layer-50/5") counts as one loft: base box.
A loft counts when it carries 도 / ° / degree or stands in a run of lofts ("52/56/60", "52Y 56Y"): a lone bare number
is a shaft's weight or flex ("50도 / Diamana 60 S" is one loft); 세트 after a loft is no age ("왼손 52 56 60 세트" is
three) and a model code's dash no range ("LH01-52 56 60 Degree" is three) (the W8 review, 2026-11-17).
Known limit: a listing whose title states a count ("웨지세트(4종)") and whose variants each name one loft ("50도",
"52도", ...) gives every variant the title's count (the review's decision C16, word for word), though a variant may sell one
wedge; seen on 394381329 (held, no live effect).
The row's `compose_by_count` block (C17, 2026-11-17): a set's `product_weight_g` the seller does not state, from its
clubs' labelled weights, see [The clubs' weights of a wedge set](#the-clubs-weights-of-a-wedge-set).
50002816 레인코트 (golf rainwear, 2026-11-24, reviewed 2026-11-25): one rain coat in a 28 x 22 x 5 cm mailer, a kind
`suit` (a jacket with its trousers: 상하 / 세트 / 레인슈트 / 레인수트 / 투피스 / 우의바지 / 비옷바지, 32 x 26 x 8 cm,
850 g) and a kind `light` (a poncho, cape or rain skirt: 판초 / 케이프 / 스커트 / 치마 / 앞치마 / 망토, 24 x 20 x 4 cm,
280 g), the suit read first. Sellers type 레인슈트 and 세트 as search keywords on things that are no suit (the owner,
2026-11-25, "Все рекомендации"), so: a 세트 after 선물 (a gift set), a bag (웨이스트백) or 파우치 is no suit word; the
suit's `unless`, read on the title and on the variant apart, refuses the suit where the text names one coat, poncho,
cape or cloak (코트 / 판초 / 케이프 / 망토) and no second garment (상하 / 상의 / 하의 / 세트 / 셋트 / 투피스 / 바지 /
팬츠 / 스커트 / 치마 / "+"), and where the suit is deselected ("레인슈트 미선택+비치마", "상의 선택안함"); a variant
whose own words name the two garments ("상하세트", "레인슈트(상하)", "판초+바지 세트": the suit's `always`) is the suit
whatever its title names, so a coat's or a poncho's title never moves a suit variant. Then the light
kind or the row's coat: the rain skirt 9595746260 "골프선물세트" and the cape 10603405721 "골프레인슈트 ... 판초우의
케이프" light, the long coat 13415919469 "레인슈트 레인코트" and the coat with a waist bag 11428436186 "웨이스트백 세트"
the row's, 10608961987's skirt-only variant light (its "레인슈트+비치마" stay suit), 8785829126's "2.우비 레인코트"
variants the row's (its "1.우비 상하의세트" stay suit). A real suit, a suit + skirt and a two-piece of a poncho and a
skirt (12182231084 "판초우의 비치마 투피스 세트", 10436091287) stay suit. Table version 20, the row's
`defaults_version` 19 (no number moved).
Product sizes (not the package: kind product or unknown) are kept apart, optional.

**`own_box`** (2026-11-27, the stand bags' pilot of 30; `description_measures.own_box`, checked by `check_row`, never
beside `baselines`): an item that is its own container, one stand bag. On the pilot 34 of 35 bags kept the default box
and 15 the default weight though the pages state them. With the block, in this order after a stated box:

| key | what | 50002791 (the agent's) |
|---|---|---|
| `carton_g` | the carton and filling: the package weight is the item's weight + it (`_boxed`) | 1000 g |
| `length_margin_mm`, `side_margin_mm` | the box over the item's stated body: length, each other side | 50, 20 mm |
| `long_mm`, `side_mm` | which size is the body: its longest side, its other two (the height with the hood up, 123-129 cm, a bag laid flat, "87 x 15.5 x 35cm", a Boston bag's 48 cm: none of them; a 7.5 in top bag is 19 cm deep) | 800-1000, 180-450 mm (the side 200 until the review of 100, 2026-11-27) |
| `weight_g` | the band of the item's weight the reader takes in more places (`read_rows(own_g=...)`) | 800-4500 g |

The reader then also takes the bag's weight written as "-무게3.7kg", "•무게:2kg", "다양한 포켓 구성 / 무게 / 1.4 kg", "중량 /
2220g", "약 2.6kg (스트랩 무게 포함)", "Weight (kg) | 2.8kg", one weight on a size row ("크기 / 9.0인치/2.5kg/6구") or under
a 중량 head, and the body in W / H / D cells ("H : 88cm W : 24cm D : 36cm"); never a bare headline ("2.3kg 초경량"),
another item's row (보스턴, 파우치, 더플, 하프백 on it or 3 rows above) or two body sizes 30 mm apart (two models). The
pilot: weights read 20 -> 31 of 35, boxes 1 -> 7; prices moved on 5 (Inparo SD-280K, 42 x 28 x 90 cm: $549 -> $729).

The review of 100 (2026-11-27) added: "패킹사이즈 / 40cm x 29cm x 99cm" is the carton (a stated box, not the body:
9145583325); a unit or an axis after each number of a size ("15.00인치 x 16.00인치 x 34.00인치", '37" H x 9.5" W x 13"
D', "24.5(가로) x 86(세로) x 19(폭) (cm)"; a general reading of sizes, used by `own_box` only); centimetres marked mm
("7.5인치 (29 x 90 x 19mm)") read as cm when only that is a body; with the block, a typed label line joined to its
value line ("무게" over "6.5파운드", as with LONG_UNITS), pounds after the label ("- 무게: 5.35파운드"), a particle
after the label ("무게는 2 KG 입니다.", "무게가 2kg(4.5파운드)", never "무게가 1kg 가벼워진"), the kg after its own
pound value ("*5.5lbs,약 2.49kg", within 10 %) and one kg as a cell of a spec line of the bag's words
("5분할/7포켓/2.8kg"; not the headline "2.3Kg 경량14구 넉넉한 수납"). On the 50002791 products collected so far:
9 bags gain a weight none was read for (the others keep theirs), 6 boxes change (5 new, 9145583325 now its stated
carton). Weights per variant: bound since 2026-11-27 (below; until then one bag's weight for the listing).

**Stated weights bound to the variants** (2026-11-27, Lightweight Stand Bags; `description_measures.bind_weights`,
called by the transform's `_bound_weights`). Without a profile `guess` took the heaviest stated weight for every
variant: Titleist 7115158598 gave its six Players 5 bags (typed "무게 - 1.95KG") the Sport bag's 2.6 kg. Now, with no
profile, two variants or more and two stated product weights more than 2 % apart inside the field's band, each
variant takes the weight whose own words name it (the band is the category row's own `plausible` block: a category
without one, apparel, binds nothing, so a model's "Weight : 52kg" opens nothing):

| `bound.by` | the words | confidence | case |
|---|---|---|---|
| `same_row` | a row of two weights, each value's segment (the bracket after it, else the text before it; the text after it when only the row's tail names words, "무게 / 2.5kg 블랙 / 2.3kg 화이트"; both named: one fact, the heaviest) | 4 | Vessel 13454840028 "무게 / 약 3.8kg (DXR Black 약 3.4kg)"; YONEX 12952984359 "(J135)1.8kg, / ,(j120)1.7kg" |
| `label_above` | the rows above it in its image, at most 8, never past the image's previous weight row nor above a spec header (상세스펙, 제품정보, Product Info) | 4 | PGM 10647003177 "컬러:블랙그레이" ... "중량:3.12kg"; Kolon 6817963449 |
| `typed_label` | the same in the typed text | 4 | Titleist 7115158598 |
| `image_heading` | the image's first 5 rows, when no weight row comes before it there | 3 | PXG 7223000254 "3.페어웨이 카모 / 캐리 스탠드백" |
| `row_default` | the unlabelled value of a row that labels its other value | 4 | Vessel's other 14 colours 3.8 kg |
| `title_model` | the weight left names two words of the title | 4 | Nike 10121431552 블랙 / 카키 2.01 kg ("나이키골프스포츠 라이트") |
| `two_models` | an axis of two values, one bound, the other left | 3 | Titleist's Sport bag 2.6 kg, Keiro 11012444977's 14분할 2.4 kg |

A value names the words by its model code (J135, CB-137), its text (Hangul of 2+ letters; Latin of 3+ on word bounds:
"BL" in "fashionable" is not CB-947 BL, WinWin 5941086854), all its words, or, all-Hangul in Latin text, by its
consonants (4 or more: 멀티 아이콘 카모 in "WINWIN MULTI ICON CAMO", 고파이트 네온 in "GO FIGHT! NEON"; 10046033303). A text
match inside a longer named value is dropped (Black inside DXR_Black); the variants named are cut to the values of
another axis every named value occurs with (Keiro's "네이비 / 블랙 / 그레이" is the 7분할 bag's list). Never bound: a
weight naming every variant or none; a variant named by two weights (`conflict`) or by none keeps today's heaviest,
and the note `weights_unbound` says how many (5941086854 and PXG Woven 13204844211: none). The field carries `bound`
{`by`, `label`, `weights`: every stated weight}; `how` "stated weight, bound to the variant"; the note `weights_bound`
counts the variants per weight and way. On the shop's 5029 lines 10 listings change (9 stand bags, 1 junior set);
each change moves the package weight (+ the 1 kg carton) and so the price.

**`pair_of`** (2026-11-27, golf shoes 50001740, the review of 223 live shoes; `description_measures.pair_weight`,
checked by `check_pair_of`, called by the transform's `_pair_of`): an item sold as a pair. 61 of the 223 shoes state a
weight, none a box, and 54 of the 61 state one shoe; the server had bound one shoe's weight to the reference size's
variant as the pair's (New Balance 13651508341 "● 무게 : 470g (27.5cm 외발)" on its 275 variant alone, Descente
12153299165 "실측(240) ... 중량292g" on its three 240 variants: 7 products, 9 variants). With the block:

| key | what | 50001740 (the agent's) |
|---|---|---|
| `item` | the item a pair is of | shoe |
| `carton_g` | the shoe box and filling: the package weight is the pair + it (`_boxed`) | 500 g (the row's 1300 g less its 800 g pair) |
| `one_g` | a stated value with no word in this band is one item: x2 | 200-500 g |
| `pair_g` | a stated value with no word in this band is the pair; between `one_g` and it (500-600 g) nothing is read | 600-1100 g |

Read for the whole product (every variant; the reference size, "25.5cm", "260기준", is never a variant's: sizes differ
by about 10 %, under any price step), the heaviest pair of the labelled grams of the images (at NUMBER_CONF), the
typed text and the server's own weight rows (the notice's "중량: 255mm / 약425g (1pcs)"): the label then the grams
("무게 : 약 425g(한쪽발 25.5cm)", "25.5cm 기준 중량 : 약 430g", "무게 | WEIGHT | 260기준/396(g)", "중량(한쪽발) / 약
420g", "치수 / 220~250mm/중량약220g"), a header over its values ("소재 / 제품무게(260기준) / 제조사" over "... / 738 g /
..."), the values over their header (PAYNTR "280g / 35mm / 95mm" over "한쪽당무게 / 굽높이 / 발볼넓이"), a label line
over its value line ("【중량】" / "약 385g (한쪽, 25.5cm 기준)"). A one-shoe word (한쪽, 한쪽발, 한쪽당, 1쪽, 외발, 편측,
편족, 한짝, 한 발, 단일화, 1pcs) gives x2 inside `one_g`, a pair word (켤레, OCR 한컬레 / 한결레) the value inside
`pair_g`. Never: a range wider than 15 % (a narrower one: its middle), an upper bound ("약 300g 이하", 12415931375), a
band or comparison ("500g대인 보통 골프화와 비교했을 때"), insoles ("일반 깔창 약 21g", 8752851422), a shoe bag or socks,
a cross-sell block or a review, an unlabelled value (a rangefinder ad's "125g", 6520680652; a scale photo's "775"), a
comparison chart (대비, 기존 모델, 타사, 경쟁: "WEIGHT" over "기존 모델 450g" / "신모델 330g" gives nothing). An
approximation's words keep the row (9172681706, the notice's "중량: 800g 내외"; 오차, "차이가 있을", "다를 수"): the core's
skip drops such a row, the shoe reader does not. Limits: grams only, three digits or a pair's four ("1020g", "1,020g");
a kg weight ("0.85kg") is not read, and the variant keeps the default (no collected shoe states one). The block is
checked when the transform loads the table (`transform.check_pair_row`: whole, never beside `baselines` or `own_box`).
The server's product weight of a variant goes back to the default (`compared`, `rejected: one_shoe_on_a_size`)
whether or not a pair is read; its stated box or packed weight stays. Confidence 5: typed with its word; 4: an
image's, or by the value alone; the package 3 (`composed`, "product weight + carton"). The default row (800 / 1300
g, 34 x 23 x 13 cm) is kept: the pairs' median is men's 816 g, women's 653 g, and only the box moves a price (any
package up to 2.5 kg bills at the default box's 2.5 kg step). On the shop's 399 collected shoes 81 read a pair (10608981549
850 g, package 1350 g; 13651508341 940 g for every size; 4873054855 738 g as a pair; 2533527296 440 g); 8752851422
and 6520680652 keep the default. Table version 23, the row's `defaults_version` 21 (no number moved).

## Confidence

Every field carries `confidence`, **1 to 5** (the owner, 2026-11-10):

| level | meaning |
|---|---|
| 5 | the seller states this field itself in typed text and says what it is: a net weight, a weight with the package, the box's sides (the server path); a typed box or packed weight in the description |
| 4 | the seller states it, a weaker reading: read from an image, or its kind left open (a plain 중량 11.5kg: with the box or not), or bound to the variant by club count or by the words naming it (`bound`), or a per-piece weight times the count |
| 3 | worked out wholly from the seller's own figures for this product, plus the operator's carton / margin: the clubs' exact sum with the bag absent or its weight stated (the count and the bag's state from the listing or the typed text); the length from the driver read; a package weight on such a product weight; a stated weight bound to the variant by its image's heading or as the other of two models (`bound.by` image_heading, two_models) |
| 2 | composed with a baseline or a weak part: the count x the median, a baseline club / bag / longest club, the baseline box sides, the bag's state known only from an image's sentence or a closed list of clubs, the count read from the images or taken from the clubs' table alone; the bag assumed (`flags: ["container_assumed"]`: the clubs are known and nothing says whether the bag ships, so the baseline bag, the heavy side; the owner 2026-11-11) |
| 1 | the flat category default: the composition is unknown |

Of candidates that agree, the most certain is taken.
Records written before 2026-11-10 carry the older 1-3 scale: [History](#history).

## The description images stage

Optional, the owner 2026-11-07.

The images are most of a description (golf sets: ~12x the page's text) and state what the page does not: a box,
a product's weight and size, or, for sets, each part's. The stage reads them; the transform takes from that text
what the seller states of the five fields and, for a set, composes the rest from its parts ("The order of
sources" below; until 2026-11-10 the larger of the guess and today's value won). The same reader also gets
the lines of the seller's typed description (`details.description.text`, 2026-11-10) as one more block of rows:
no OCR doubt, table cells joined by " | " ("패키지 무게 : 10.8kg", "클럽 무게(g) | R: 294 / S: 297 | ... | 528"). A
value read there says so in its evidence (`from: description_text`; `source` stays `description_image`: renaming it
`description_text` was rejected 2026-11-17, the wedge-set review C18, as the metafield of 70 published products would
drift). It is
read with the images or not at all (no sidecar, or a stale one: neither is read).

The operator's (or an agent's) order of commands, after each collection:

```sh
.venv/bin/python scripts/example_99_full_details.py                  # 1. collect (server running)
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # 2. keep the run
.venv/bin/python scripts/description_images.py fairwardgolf          # 3. read the description images (network)
.venv/bin/python scripts/run_transform.py fairwardgolf               # 4. prepare (offline)
```

Step 3 is not part of the collection on purpose: it is slow (~20 s a product, ~3.5 h per 1000), needs only the
image hosts (no server, no Chrome) and can be run, stopped and resumed on its own. It reads only the categories
whose shop rules set `description_images` (transform_shops; off by default, on for all five fairwardgolf categories:
50002788, 50002787, 50002670, 50002783, 50002784). Skipped, the
transform still runs: the products get the note `description_images_missing` and today's values.
`--products <id> ...` reads some products only, `--force` reads again.

### What it fetches

Each kept product's `details.description.images`, in order: seller banners out (by name, link,
spacer, 1x1 pixel: description_clean.clean_images), animated GIFs out (a one-frame GIF is read: 9942710033's whole
description is one), images smaller than 60 px out (`tiny`: counters,
icons), a link repeated in one body once. Hosts: Naver's image CDN and any public HTTPS host the seller links (the
owner, 2026-11-07; never http, an IP, localhost, or a name that resolves to a private / local address; AGENTS.md
rule 3). On 50 golf sets 8 products have 35 such images
(igearmall / esmplus pages with the product copy and the clubs' spec tables, percenty shop-policy pages, rakuten /
mercari photos): checked by eye, they are the description, with the same boilerplate and photos as Naver-hosted
ones. A SmartEditor link is fetched without `?type` (the original). naver_images fetch rules: HTTPS, no
redirects, MAX_BYTES, image types only, one request a second; a 403 / 429 from Naver's CDN stops the stage (the
sidecars so far are kept); from a seller's host it fails that image only (`refused`, not retried: hotlink blocks).

### Memory and failures

Each product is read in a fresh worker process (one at a time, synchronous,
`read_isolated`); the OCR engine and the image bytes die with it, so a long run never accumulates RapidOCR's memory
(live: the worker up to ~2.1 GB, the run ~50 MB). A worker that crashes, is killed (memory) or outlives
PRODUCT_TIMEOUT (900 s) is that product's error: one more try, then an error sidecar (note
`description_images_failed`; `--force` reads it again); the run goes on. Ctrl+C stops cleanly (exit 130). One run
per shop at a time (a lock; a second run stops with exit 4). A script that calls `description_images.run()` keeps its
work under `if __name__ == "__main__":`: the spawned worker imports the calling script again (example_15 hung once
without it, its worker collecting a second product). A worker that died with exit -11 (SIGSEGV) on every try was a Pillow 13 array taken on a crop of a tall image (2026-11-19, 12814122019's 1000 x 10295 PNG): `description_ocr.Engine` copies each slice before the array; the rows of products read before are the same.

### Files

Per shop, under `scripts/output/shops/<shop>/description_images/`:

```
<product id>.json            the sidecar: the rows as read per image and slice, skipped links with their rule,
                             each image's host (naver / seller), the engine and its settings
cache/<product id>/<sha>.bin the downloaded bytes of that product: `--prune-cache [--products ...]` deletes them
                             (the sidecars stay; a --force run fetches again)
```

The cache holds ~6 MB a product (~6 GB per 1000, 2026-11-07): prune it once the sidecars are good (whether to keep
it by default is still open with the owner).

### When a product is read again

A product is read again when its links or the engine (rapidocr, onnxruntime, params) changed, or when an image
failed last time with a 5xx / network error (`failed`); a 4xx or a non-image (`gone`, e.g. an expired proxy-smartstore
token) and a seller's hotlink block (`refused`) are not retried; the transform notes them (`description_images_partial`).
Naver first (the owner, 2026-11-07): a body Naver cut into snap tiles is read from the tiles; the seller's own `<img>`
sources in its HTML (7583123963: 45 instead of 113) are fetched only when a tile does not read, and used when every
source reads (a seller's host can be 5x slower: 13369469193 266 s vs 54 s; its proxy-smartstore links expire; the
tiles also carry the store's banners, which the text rules cut). To fetch less, an image another product of the store
already read is reused from its
sidecar (`reused`), equal slices in one product are read once (dHash), and a first SmartEditor image lower than
400 px (the store's header strip) is skipped (`first_header`).
Not done on purpose: a per-slice "has text" detector (it costs more than the OCR it saves) and a height rule
before the download (set contents sit on small cards: >= 1000 px loses 49 of the 330 useful slices). The download,
not the OCR, sets the time (~13 s against ~7 s a product). A store's first product costs the most (~10 requests,
6.6 MB); later ones reuse its banners. Run step 3 soon after step 2: proxy-smartstore links seemed to expire within
about a day (2026-11-07, not re-checked), and an expired one is `gone`, not retried. Not checked yet: a batch well
over 20 products for the worker's memory and time per product.

## Reading the description: the guess

The guess (`description_measures.py`, offline, in the transform) has two layers:

* the **core**, for every category: what a seller writes of the product itself: a packed weight / box (박스 / 포장 /
  택배 / 패키지), a set / product weight (세트 / 본품 / 제품 / 상품 무게; a row labelled 무게 / 중량 / weight with kg,
  even when OCR split the label: "무 / 0.6kg"), a product size triple (크기 / 사이즈 / 규격 / size, or with a unit:
  "W53 x D38 x H62.5 cm"; read as a fact and, since 2026-11-10, no field's: a product is not its box). Since
  2026-11-17: in a category of `description_measures.LONG_UNITS` (50002783, whose row has a band) also kilograms,
  pounds and 파운드 ("- Package Weight : 1.45 Kilograms", "Item Weight: 3.2 Pounds"; not "0.454 Kilograms"); and a
  typed label line with its value alone on the next line is one row ("포장 박스 크기" / "38 x 4.5 x 4 inches"), except
  Item Weight / 품목 무게 (often one club's weight on a set's page). Live check
  2026-11-07 on other categories: a camping chair (625 x 530 x 380 mm), a kettle (0.6 kg, 170 x 170 x 100 mm); a
  kettle and desks whose images give sizes only as photo callouts: nothing;
* a **parts profile**, only where the category is sold as a set of like items in a container. Profiles are data
  (description_measures `Profile`: the items' weight / length ranges and labels, part labels that are never an item,
  the container's words and ranges, accessory words, count words, a count row, the 상품정보 row that names the
  container and its "no" values, plausible bands; since 2026-11-10 also what the shared items code held for golf:
  the spread of a set's weights, the rows under a table's header, a part maker's table, the things sold for the
  container), mapped by the **Naver leaf category id** in `CATEGORY_PROFILES`:

  | Naver category | profile | items / container |
  |---|---|---|
  | 50002788 골프클럽 > 풀세트 | `GOLF_SET` | clubs (their weight and length tables, see The clubs; 샤프트 / 헤드 / 그립 are parts) / the bag (weight, height, mouth, sides) |

  A category with no profile gets the core only. Add a profile only when the core cannot read a category's images
  (its own tables of parts); a new category is otherwise just its shop rule's `description_images` switch.

Never read in either layer: a shop rule, customs, a person, a price, a disclaimer, anything after a cross-sell
heading to the end of the image. The heading is "함께 / 같이 구매하면 ...", "추천 상품" or "관련 상품" (2026-11-10): the
returns text "다른 상품으로 교환하는 경우" and "원하시는퍼터를함께구매하시어 ..." are sentences, and on a description
that is one tall image they cut the whole spec away (3 of 120 sets lost their tables, 12606747315 at row 19 of 311).
With a profile, a row is the container's when the nearest row that names one, on it or up to 10 rows above, names
the container; when that row names an **accessory** (the profile's word list: a Boston bag, a shoe bag, a pouch, a
half bag) its size and weight are neither the product's nor the container's (13513786835: the add-on Boston bag's
"L48×W24×H30CM" was the package's width and height). A row naming both is the container's ("총무게:(캐디백+보스턴백)
약4.95kg"). Not a weight: "약1.5kg경량화되어" (1.5 kg lighter); not a club: "47인치 대응" (what the bag takes).

### The clubs

The clubs are the profile's items (mined on the 120 collected sets, 2026-11-10). Their tables come two ways: a
labelled row with the values after the label ("클럽길이(inch) / 45.5 / 43", "총중량(g) / 308 / 326 / ... / 545"; the
label in any cell, OCR's spellings too: 클럼무게, 충중량, 길치), or a header naming the columns with one club per row
below ("클럽넘 / 로프트 / 라이각 / 전체길이 / 스윙웨이트 / 플렉스 / 헤드중량 / 총중량", then "1W / 10.5 / 58 / 45.25 inch /
D0 / R / 197g / 320g"; up to 18 rows; the SR and S rows of a club are the same club; a shaft maker's table, TIP /
Butt 외경 in its header, is not the clubs').

* **Length.** Inches (32-48.5) and cm (81-124) never meet, so a value needs no unit mark ("110.49/43.5", "약114cm",
  "45,25", two cells glued: "116.84107.32"); a cm value alone on its row counts too ("(114.935cm)"). Lengths are
  read at any OCR confidence: a row's confidence is its weakest cell and the driver's short row is the one that
  fell under 0.9, so an iron's or a putter's clean row stood as the longest club (25 of 120 sets). **The longest
  club is the largest length stated, taken only in the driver's band** (the profile's `longest_mm`, 42.5-48.5 in:
  the 118 stated drivers are 43.5-46.0 in, a ladies' 3-wood 41-42.5 in); below the band the driver's row was not
  read and the baseline driver stands in, never a shorter club. A row that lists several flexes or optional
  shafts gives the longest of them, 6-25 mm over the one sold on 7 sets (six ladies' sets with an R row, one
  optional shaft; left as it is: the margin covers it).
  On the 120 sets: 116 of the 118 stated drivers (81 before, 25 a shorter club, 12 nothing); the two not read:
  11775161460 ("길이(인처) / 445": the decimal point lost), 11061911792 (the row's label read "3()").
* **Weight.** One club's total is 240-650 g (the lightest stated is 252 g; a wood's head 197-235 g). A row of a
  weight label that holds only weights under a club's makes the label a part's in that image, on its other rows
  too ("중량(g) / 198 / 202 / 207 / 233" over "중량(g) / 257 / 263 / ... / 297": the woods' and the irons' heads,
  which made the median club of 7583123963's 13-club set 296 g; the only set of the 120 with such rows). 스윙웨이트
  beside a total is the balance, not a part. A bare number after a name is the shaft's model, not a club ("약256g /
  C1(ULT 250 J-L)" gave a 250 g club on three rows of 9321714669). Read for 94 of the 120 sets (80 before).

### More of the page

On 2026-11-11 (the 300 sets of the fairwardgolf job; the products on the flat default weight
went from 109 to 23 of 426, every one of the rules below a regex or a condition; one fixture per rule in
`fixtures/measures/`, made with `make_measures_fixture.py` from a real product):

* core (every category): shipping rules ("5kg내외", "2kg까지는", "160cm이상"), a buyer's height and weight, the
  returns' shoe box are never read; "풀세트 패키지" is the set, not its box; the notice's "크기,중량 1230mm/10kg" is
  the product's weight.
* golf sets, the bag: machine-translated bag words (볼백, 볼 가방, 공 봉투, 건백); the bag as an item of a
  composition line, or "8개+캐디백"; a gift's 레디백 / 버킷백 / 텀블러백 is an accessory; a bag table with no bag
  word in reach (its mouth "9형"); a list of the clubs from the driver to the putter with no bag, or a title that
  lists the clubs ("[드라이버+우드+유틸리티]", "드라이버 10.5도 R, 아이언 6개"), says no bag (weak); the typed "<캐디백
  별매>" beats a bare bag word in the title (9266324198: "레프트 캐디백" there is a cavity back); nothing says:
  the bag assumed (flagged).
* golf sets, the count: an option value's "11개", "12+볼백", "10클럽"; "11PC" / "11ps"; the 풀세트구성 row and
  composition lines kind by kind ("드라이버 1개/아이언8개/퍼터 1개", "드라이버, 7아이언세트, 유틸리티, 퍼터", the
  typed "1> 드라이버 ... 4> 아이언 / 6,7,8,9,P,S / 5> 퍼터"); a single club filed as a set (치퍼, 드라이빙 아이언,
  접이식 / 실내 골프채, options of one club's lofts x shafts) is one club without a bag; an option's "N개" beside
  other options ("8개구성 NS820", "아이언 9개") is the irons', not the set.
* golf sets, the clubs' weights: OCR's labels (총 종량, 클럽 증량, 무계, Club중량, 클립 무게, T/W(g)); a weight in
  its label's cell, one row above its label, or after an option index ("1378(S:#7)"); head + shaft + grip columns
  (PGM, SMACK) summed per club; the #7 iron's weight ("410(#7)", "#7 약320g", "(7번 R 기준)") for the clubs no row
  weighs in the same image ("(#5 기준)" is a wood's own); a table of half the set or more plus its own median for
  the rest (in place of the count x the page's median); per-row tables that together are the set, summed; a set
  of 3-4 clubs needs a spread of 1.1 only.
* golf sets, the length: a bag's "대응 / 지원" length and a shaft maker's table (CPM, torque, kick point) are not a
  club's; a driver over 46.5 in needs two rows; OCR's labels (같이(inch), 집이(nch), "길 / 이"), inch spellings
  (인츠, 인체, 인처) and a lost dot ("4375": 43.75); an L / A variant takes the driver row of its flex when it is
  within 30 mm of the longest (a wood's L row never stands for the driver).
* **Count**, in the order of trust: the variant's own option values ("스틸12P+캐디백" / "스틸9P+캐디백": the variants
  of a listing are different sets), the title / 모델명 ("12pc", "9종", then the profile's "클럽 10개", "10개 풀세트",
  "[11개]"), the 상품정보 row 총클럽개수 (it disagrees with the title on 5 of the 120 and the title is right on 4:
  10481094198, "10개 풀세트" with a row of "3개"; the row is right on 9321714669, title "클럽9개", row "11개" with
  two gift clubs: left as it is), the images (the weakest, a weak part of a composition: a page shows other sets; a
  head's make, "4피스 티타늄 페이스", "4PCS단조", is no count). **The seller's own club table goes before a count of
  pieces** (Total, below): a listing's "12개" may count the bag and the head covers, and some listings state no
  count at all.
* **Total.** When one table gives exactly one weight per club of the set (as many values as the count, the
  heaviest at least 1.25x the lightest), the total is their **sum** (`how`: "sum of N club weights"); of several
  such tables (an R and an S set) the lightest. A table is one row, the rows of one image (or of the typed text)
  under one label, or the rows under one header.
  Else **a full table before the listing's pieces** (2026-11-10): when the listing's count is larger than a full
  table by up to 3, or nothing states a count, the total is that table's sum and the club count is its length.
  8053135821, 총클럽개수 "12개" (the box's "12-Piece": nine clubs, a stand bag, two head covers): the nine rows
  "Driver / ... / 336" to "Putter / ... / 532" are 3955 g, where 12 x the median said 5340. 13657325637, "11피스"
  with the bag (typed "10개의 클럽으로 구성"): the ten typed weights, 3634 g. No count stated: 5543663553 (two rows
  of ten), 7674852369 (twelve clubs under one header). **Full** is one row or the rows under one header (not rows
  gathered under one label: the two rows of 13446843026 hold 11 of its 12 clubs), at least 9 weights, the
  heaviest 475 g and up: the ladder runs to the putter (the putters stated are 485-549 g, the heaviest wedge
  462 g). Without the putter the table is short of the set and the listing's count stands (X HOT, "총 11개
  클럽": its ten weights end at the SW, 8974646004). On the 120 the shortest set tabled is 9 clubs and the longest
  part of one that holds a putter 7 (13627933340); the two listings seen to count pieces are 1 and 3 over. With no
  count, full tables of two lengths are two sets: no count. The three numbers are the profile's (`full_items`,
  `full_last_g`, `pieces_over`). A count the table gives is a weaker source than the title: confidence 2
  (`count_from: "table"`; `count_listed` keeps what the listing said).
  Else "N clubs x median club weight", only when the weights read **cover at least half of the clubs**: as many
  clubs as half the count, the heaviest at least 1.25x the lightest (the profile's `set_spread`). Clubs, not
  values: weights within 2 % of each other are one club's (the profile's `same_item`), so a club by two flexes
  is not two (10816781893, 9 clubs: the driver "약252 / 약255", the utility "약292 / 약296", the #7 iron "약320g /
  약321g" are 3 clubs, and 9 x 296 = 2664 g stood; an iron's step is about 2 % too, so a ladder of irons counts
  about half its clubs: the baseline club then, never a median of too few). A driver by nine shafts, two woods
  and a utility (8029218821: 18 weights, 292-340 g, 3090 g for a set of about 3.8 kg) or the driver's and the
  wood's four weights of nine clubs (13728931694) are not the set. Else "N clubs x baseline club weight" (the
  operator's `item_g`). On the 120 sets the composed weight holds: a sum on 25 (21 with the listing's count,
  each equal to the research's sum checked by hand; 4 with the table's own count), the median on 22, the
  baseline club on 51; 22 have none (21 the default, 1 the seller's own weight).

### Whether the variant has the container

In the order of trust (2026-11-10; the first that says it decides):

1. the variant's own option values ("+골프백", "백미포함");
2. the title, 모델명 and the product's one-value facts ("캐디백 포함", "백세트제외", "10개세트 클럽만");
3. the profile's 상품정보 row, 골프백포함여부: "미포함" is no, any other value ("캐디백", "스탠드백", "캐디백, 보스턴백")
   yes (on 81 of the 120 sets; the row and its "no" values are the profile's data);
4. a container sold as a paid add-on (`specs.options.supplements`: "젝시오 골프백 추가 구매" 350,000): the set has
   none. An accessory add-on ("RB LADY 여성용 보스턴백", "4. 골프백 / 럭셔리 신발가방") says nothing, nor does a thing
   for the bag (the profile's `container_trim`: "캐디백 항공커버", "캐디백 네임택");
5. a sentence of the typed text ("골프 가방 불포함 상품 입니다.", "캐디백은 포함되어 있지 않습니다."), then one of the
   images ("본 풀세트는 골프백 미포함 제품입니다", "캐디백까지 포함된"; a weak part: confidence 2 at most); a no wins
   over a yes. "클럽만" says no bag ("[클럽만]", "10개세트 클럽만"), the clubs' own does not ("클럽만의 기술력").

Weak signs (a "조합" title, a composition list without a bag) are not used.

## The order of sources

The owner, 2026-11-10; `merge_fields`. The flat category default is the last resort. A
field takes the first of:

1. **the seller's own statement of that field.** The server path's value (`source_stated`) is kept whatever the
   description says. Else a statement read in the description (`guess`): a packed weight ("패키지 무게 : 10.8kg"), a
   box (its three sides), a set's or, outside a parts profile, a product's weight. It takes the default's place
   whatever its size (13495098284: the box "-패키지크기:L20×W16×H121cm" read from an image used to lose to the
   default 1250 x 280 x 230 only because it is smaller). Typed: 5; read from an image, or a set / product weight
   (its kind is open): 4; the same line read both ways is the typed one. A row OCR read below 0.9 (its weakest
   cell) gives no statement (research: ~38 % of such digit boxes were wrong). A triple may be in inches ("48.2 x
   12.7 x 8.5 inches"). A stated packed weight goes before the composition also when it is under the composed
   product weight (that weight rests on baselines; the statement is the seller's).
2. **the composition from the set's parts** (`compose`, `_items_total`, `_boxed`), only when the category's row
   has the `baselines` block and the category a parts profile. Each part comes from the product's own data when
   it is there, from the operator's baseline when it is not:

   | field | composed as | `how` |
   |---|---|---|
   | product_weight_g | the clubs (the sum of one table, else the count x the median when the weights cover half the clubs, else the count x `item_g`) + the bag (nothing when the set has none, its stated weight, else `container_g`) | "clubs + bag", "clubs, no bag" |
   | package_weight_g | the product's weight as the field ends up (the seller's, a statement, the composition) + `carton_g` | "product weight + carton" |
   | package_length_mm | the longest club read (the driver), else `longest_item_mm`, + `length_margin_mm` | "longest club + margin" |
   | package_width_mm, package_height_mm | `sides_mm` for a set without a bag, `sides_with_container_mm` with one | "box side, no bag", "box side, with bag" |

   Confidence 3 when it is worked out wholly from the seller's own figures (the levels above), else 2.
3. **the flat category default** (1), only when the composition is unknown: the weight when the number of clubs
   or the bag's state cannot be told, the two sides when the bag's state cannot (the length needs neither). The
   package's weight follows the product's: no weight to put a carton on, no composition. A known composition is
   never dropped for being small: 13302492097 and 12966969668 are a driver, a wood and a utility without a bag
   (총클럽개수 "3개"), 3 x 340 = 1020 g and 3020 g packed, not the flat 5700 / 7000 g of a full set.

A composed field says how it was built: `source: composed`, `how`, `parts` (`[{part, value, from, quote}]`:
`from` is "stated", the clubs' total as it was made ("sum of 10 club weights", "11 clubs x median club weight",
"10 clubs x baseline club weight"), "baseline", "not in the set", or the field it is; a clubs part says where the
count came from, `count_from`: "listing", "description_image" or "table" (the clubs' own full table; then
`count_listed` is the listing's count it set aside), a bag or box-side part who said the bag's state, `said_by`:
"listing", "description_text", "description_image"), `baseline` (who approved the operator's amounts in it, and when) and,
as `compared`, the default it replaced. Under a seller's value `compared` is the description's statement or the
composition, for the reader. 11659201020 ("클럽10개 백포함 R세트"): the R table's ten weights, 3892 g, + the bag's
stated 3.8 kg = 7692 g (3), + the carton = 9692 g (3), the 45.25 in driver + 100 mm = 1249 mm (3), 400 x 320 (2).

**A box is one statement**: its three sides are taken whole or not at all (`box_not_whole`). Of a gift's "증정
골프공 패키지 사이즈 30 x 20 x 10cm" the 300 mm length is refused, and 200 x 100 must not stay as the width and
height of a 1250 mm package (2026-11-10; before, the sides were merged field by field).

### The clubs' weights of a wedge set

50002783 only, by the row's `compose_by_count` block (`description_measures.compose_by_count`, in the transform after
the merge; 2026-11-17, the wedge-set review C17, commit 2f2262f). In place of the flat default of `product_weight_g` only (the package and
its sides stay: PGM's 8 lofts x 462 g would have raised a box): the lines of the typed text, the 상품정보 rows and the
images' rows read at NUMBER_CONF that carry a weight label, no part word (head, shaft, grip) and 3-digit weights in
380-520 g (the value may stand on the next line). As many weights as the set's clubs: their sum, confidence 3 (USPA
414 + 412 = 826 g, Maruman 380 + 385); one weight: it x the count, confidence 2 (PRGR 448 g, Toho 460 g). The count:
the variant's own (a count word or its lofts), else the title's when it states one. Not on a #7 / #5 reference or 기준
/ 추정 / 상정 (Yamaha RMX, FITTAS), Amazon's Item Weight / Product weight / 품목 무게 (GoSports 424 g), more weights
than clubs (the MG5 / RMX / Honma shaft tables), men's and women's weights in one listing, a title listing more
lofts than any variant, a held product, a single club's variant. The field: `source: composed`, `how`, `parts`
(each club's weight and its line), `count_from` (variant | title), the block's `approved_by` / `approved_at`,
`compared` (the default). No price moves (no `baselines` in the row). Measured on a shop copy 2026-11-17: 8 products
(6 in the store); MG5 13699940318 (men's and women's weights) is skipped. Not firing, on purpose: PGM
13261483119's "Product weight: 462G" (the Amazon skip wins, the cautious side), USPA 13582215582's "(Aw Sw)" (no
count). Rejected: the median x count for the shaft tables (MG5, RMX); a `baselines` block (`check_row` needs a
container, wedges have none); a CATEGORY_PROFILES entry (`guess()` drops plain product weights: 3 description_image
weights of golden 13468791008 would move); Amazon's Item Weight x count (GoSports: 424 g on one listing, 1590 g on a
sibling).

### A weight against the variant's count

50002783 only (a row with count kinds `lofts` and `compose_by_count`; 2026-11-17, the resend review D1). A weight
the listing states once (a product-scope row of the server, a statement of the description) is one count's figure:
Yamato 13164555233's "Package Weight : 1.13 Kilograms" is a pair's, Mile High Life 12178280377's 1610 g a 3-wedge
set's. For a variant whose count is known, its product and package weight must lie from n x 380 g (the block's
`item_g.min`: 760 for two, 1140 for three, 1520 for four) to the count's kind's high (two_wedges 1100 / 2200, the
base row 2800 / 3800, four_plus 2800 / 3600), or up to n + 1 clubs' lowest when that is more (Yamato's 2-packs state
1.11 and 1.13 kg: the pairs' product band is 760-1140). Outside: `compared.rejected: implausible_for_count`, the
field the variant's default (`package_measures.count_band`, `off_count` for the server's product-scope weight, also
with no current description sidecar, `merge_fields(counted=...)` for the description's; then `compose_by_count` may fill the product weight). The count:
the variant's kind (`two_wedges`, `four_plus`; the variant's own count inside it), or for the base row a variant
naming three lofts or one count word of 3. Never the title's: agency titles are cut (13383747280 "... 52° 갭
웨지GW 56° 샌드" is the 3-piece of UPC 792713116504, with 13312228253 / 13468925033: its 1814 g is right) or list a
menu (13372037781 "52 56 60 72도 세트"). A weight bound to the variant stays. Measured on a shop copy 2026-11-17:
4 products, 20 product weights and 3 package weights (13164555233's 3-wedge sets: $429 -> $439, $459 -> $469);
no other price moves.

### No product weight above the package

Every category and every product (2026-11-17, the resend review D2; `description_measures.product_over_package`, in
the transform after `compose_by_count`; with no current description sidecar, `description_images_missing` /
`_stale`, or in a category that reads no images, the server's statements alone are checked, the count check of
[A weight against the variant's count](#a-weight-against-the-variants-count) with them: `transform._stated_weights`).
A box weighs at least what is in it. The seller's product weight (the server's or the description's) above the
variant's package weight:
- A label that says neither product nor box, Amazon's "Item Weight" / "Product Weight" / "품목 무게" or a bare "무게" /
  "중량" / "Weight" ("무게 : 약 5kg", 13024454637), over a default package, inside the package's band (the row's
  `plausible` and the count's): read as the package's weight (`flags: ["item_weight_as_packed"]`, confidence 4: its
  kind is open). A labelled product weight ("제품 무게") is not. These imports' Item Weight is the shipping weight: 69 Golf 13480790720 "Item Weight | 2.84
  Kilograms", its siblings 13370257430 / 13164548371 state 2.84 / 2.79 kg as "Package Weight"; Detroit 13370268119
  "Item Weight : 3.2 Pounds" (1451 g) beside "Package Weight : 1.45 Kilograms".
- The product weight then, or else, the variant's category default (`compared.rejected: above_package`); when the
  default is above the box too, the box's own weight (`flags: ["capped_to_package"]`, 13388597147: 363 g over 360 g).
  The package's `below_contents` / `below_stated_product` flags go with it.
- A default product weight above a stated box is not the seller's and stays (13372006463, the owner's decision).
- Kept (owner delegated, 2026-11-17): every category, not 50002783 only (it moves 13388597147, 13024454637 in
  50002787 and 13024231444 in 50002788, no price), and a refused weight falls to the default, not an assembly
  estimate (13024231444: 5700 g, not 7540 g).
Measured on a shop copy 2026-11-17: 8 products, 20 product weights (13370268119, 13372131108, 13389498451,
13468741368, 13480790720; 13388597147 and 13024454637 in 50002787, 13024231444 in 50002788), 3 package
weights read (13480790720, 13468741368: under the volumetric weight, no price moves); with the bare label 4
(13024454637: 5000 g in place of the 4500 g default box, under its 11.5 kg volumetric weight). The check without a
sidecar moved nothing that day (145 products without one, none with a stated weight above its box).

## Absurd values

Absurd values are never taken (`compared.rejected`; `refused` on the composition that stood in): a statement
outside the field's band (the operator's `plausible` in category_measures.json, else the profile's, else the
core's: weight 10 g - 200 kg, a side up to 3 m), any value above the band or more than 3x today's value
(`far_above_today`: a misread "45.5kg", another product). The band's lower side is for statements only: a
composition under it is a small set, not a misread (three clubs). A stated packed weight under the product's
weight is taken all the same; when that product weight is the seller's own (4-5) the field carries `flags:
["below_contents"]` (a box weighs at least what is in it: two statements of the seller, the operator decides); since
2026-11-17 the transform then puts the product weight back ([No product weight above the package](#no-product-weight-above-the-package)).

## Known limits

Left as they are (2026-11-10). A "1+1" listing ships two sets and is weighed as one
(5684497984: about half its weight). A table is not bound to a variant: of several whole tables the lightest
stands for every variant (the S세트 variants of 11659201020 and 5543663553 get the R row, about 300-350 g under;
the two women's variants of 7674852369 get the men's twelve clubs). On a page of several models the bag's
weight may be another model's bag (12696567111: the XR24 stand bag's 4.1 kg on the XR26 set) and the longest
driver stands for every variant. The median is the page's, also of clubs that are not in the set (12965394174:
the add-on woods and utilities; 7583123963: no iron's weight is read).

The owner's rule on parts (never summed) holds for the
seller's candidates (`specs.measures`); for the composition, summing the items is the point. Read as facts and no
field's since 2026-11-10: a product's size, the bag's length, mouth and sides (the box's sides are the baseline's;
7583123963 states a bag of 130 cm in total where the driver + the margin gives 1230 mm).

## Notes on the product

The package notes (they never hold a product):
`measures_from_images` (fields no longer today's: stated in the images or the typed text, or composed; per variant count),
`weights_bound` / `weights_unbound` (the stated weights bound per variant / variants left at the heaviest: [Stated
weights bound to the variants](#category-defaults-category_measuresjson)), `description_images_missing` (switch on, no
sidecar; never holds), `description_images_stale` (the sidecar was read from other links, an older collection:
not used; run the stage again).

## The images' text, read by `describe.py`

Checked by eye against the images (2026-11-07, 20 live sets): prose reads near-exact, spec tables ~95 % (a digit
lost now and then, a degree sign read as 0), small lettering on photos poorly; the rows as read are not a text yet.
`run_transform` turns each product's current sidecar into clean Korean blocks (`description_image_text.py`) and
writes them for `describe.py`, which reads the Korean blocks itself (the owner, 2026-11-10: the images' text is not
translated; nothing writes `description_images.en.json` any more, [TRANSLATION.md](TRANSLATION.md) Decisions). Fixed after the 100-run check (2026-11-08): a
cross-sell cut starts only at a heading (a sentence cut 292-330 rows of three Sterna listings' spec sheets), a table
heading or row repeated in another table is kept (only a slice overlap is a repeat), short flex rows ("R / D1/296")
are table rows, and a store banner's address, hours, services and map labels are cut:

```
scripts/output/shops/<shop>/translation/<product id>/
    description_images.ko.txt    the blocks to read: a header (format, sha256), then "[b01 text image 1]" / "[b02
                                 table image 3]" and the block; table rows are cells "a | b | c"
    description_images.ko.json   {format: description_image_text/1, product_id, key, sha256, blocks: [{id, kind:
                                 text | table, image, text}]}
```

**One flag** on every prepared product says where it stands; `describe.py` (and any checker) reads the flag,
never the folder: `product.description_images_text = {state, blocks, chars, sha256, dropped, ko, en}`, `state`:

| state | meaning | `describe.py` |
|---|---|---|
| `off` | the category does not read its images | no images' text |
| `not_read` | it does; description_images.py has not read this product's current links | no images' text (run the stage first) |
| `empty` | read; nothing left (photos, the shop's own blocks) | no images' text |
| `to_translate` | `ko` written: the normal final state (the name is older than the 2026-11-10 decision) | reads the `ko` blocks |
| `translated` | an old `description_images.en.json` with `source_sha256 = sha256` (written before 2026-11-10) | reads the `ko` blocks, as above |

What is cut (counts per rule in `dropped`): rows repeated in the product (slice overlaps), low OCR confidence (<
0.6), fragments and photo labels ("B4", "POWER TRAJECTORY"), prices (KRW, yen), contacts (phones, addresses, URLs),
the shop's terms (delivery, returns, orders, A/S), store info (branches, hours, channels, events), legal notices,
promotions and dealer claims, everything after a cross-sell heading in an image, an image that is mostly the
shop's own notice, and the page text's sentence rules (description_clean.clean: greetings, store claims, ...).

**Kept on purpose, for the agent who writes the description to leave out** (the owner, 2026-11-07: this step
gathers context; a little extra text is fine): screenshots of buyers' reviews that some sellers put in the
description images (13777887875: a "재팬잇 Customer's Real Review" banner with masked ids "ridb*", dates "25.10.23",
"사이즈:240", "175cm, 77~79kg", reviews of shoes and a cap). They read as text like the rest; they are never the
product's description or facts, and may name other products and buyers' body data. The instructions in every
`.ko.txt` / `.ko.json` say so.
A store's block repeated in several listings (a model's spec sheet) **stays**: its `key` (sha256 of its text, 16 hex)
is the same in each, `shared` says in how many of the store's products, and the translation step translates one key
once; `shared` is not part of the product's sha256, so another product's change never resets a translation. On the
20 live sets: 4369 rows -> ~500 blocks, ~60k characters. A degree sign read as 0 is put back in angle rows ("+1.00"
-> "+1.0°"). The `.ko.txt` header and the `.ko.json` carry the instructions for the translator (OCR faults to
expect, keep numbers / units / model names / table cells, do not invent, translate a key once) and the category's
glossary (`GLOSSARIES` by Naver category id; 50002788: 로프트각 = loft, 라이각 = lie angle, ...); neither is part of
the sha256.

## Measurements

Measured in memory on the 120 collected sets (2026-11-10; products per level, by the first variant):

| field | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| product_weight_g | 0 | 1 | 7 | 91 | 21 |
| package_weight_g | 2 | 1 | 5 | 91 | 21 |
| package_length_mm | 2 | 1 | 113 | 4 | 0 |
| package_width_mm | 2 | 1 | 0 | 97 | 20 |
| package_height_mm | 2 | 1 | 0 | 97 | 20 |

The 21 weights left to the default: the bag's state unsaid (20; 8 of them with no club count in the listing
either), no club count anywhere, in the listing or as a full table (1: 9266336330). The figures came from a one-off
research script over the 120, not kept.

The description images' slices: Measured 2026-11-07 on the 977 slices of the 50 golf
sets: 53 % useful (copy 26 %, spec tables 17 %, set contents 9 %), photos 30 % (cheap to read), store boilerplate
17 %.

## History

**The scale changed on 2026-11-10** (it was 1-3 since 2026-11-06: 3 stated with its kind, 2 stated with the kind
open or the binding worked out, 1 the default). Records written before the change carry the old numbers: collected
lines (`package` is computed at collection), prepared records of `format: prepared/4` and below, and what was
published from them; `prepared/5` is on the new scale. The transform puts a collected line's seller values on
today's scale from their own evidence (`package_measures.on_scale`: the old 3 is 5, the old 2 is 4), so one prepared
record never mixes the two.

**Table version 20 (2026-11-25, the owner: "Все рекомендации").** 50002816's kind `suit` read narrower (a seller's
search keyword 레인슈트 / 세트 is no suit; see the 50002816 paragraph under the category defaults): the words of a
kind only, no number moved, so the row's `defaults_version` stays 19, as version 10's bands kept 9 (a raise would
have restamped 37 rainwear products' defaults 19 -> 20 with no number changed, and the stamp travels in the package
metafield). Measured on a copy of the shop: 6 products move, 9595746260 and 10603405721 (3 variants) to light,
10608961987's skirt-only variant to light, 13415919469, 11428436186 and 8785829126's 45 coat variants to the row's
coat; nothing else.

**Table versions 18 and 19 (2026-11-24 / 25).** The row of 50002816 레인코트 (golf rainwear) with its kinds `suit`
and `light`, its `defaults_version` 18; reviewed on the 30 pilot drafts (a coat 350 g in a 28 x 22 x 5 cm mailer, a
poncho or rain skirt 200 g in 24 x 20 x 4 cm, a suit kept), its `defaults_version` 19.

**Table version 13 (2026-11-20).** The row of 50002798 점퍼 (women's golf windbreakers): the knit's values on the
owner's delegation (a shell packs as small as a knit): product 150 / 350 / 800 g, package 300 / 400 / 900 g (plausible
300-1500 g), box 25 x 20 x 3 / 28 x 22 x 4 / 35 x 25 x 8 cm; kind `insulated` (기모 / 방한 / 퀼팅 / 하이브리드 / 보온 /
후리스 ...: the knit's 0.7 kg, 30 x 24 x 6 cm). Its `defaults_version` 13; the other rows keep theirs.

**Table version 16 (2026-11-22).** The row of 50002802 스커트 (women's golf skirts and culottes): the tops' box and
kind, a skirt 120 / 200 / 500 g. Its `defaults_version` 16; the other rows keep theirs.

**Table version 17 (2026-11-23).** The row of 50002801 바지 (men's and women's golf pants): a folded pair in the tops'
mailer, 30 x 24 x 5 cm, product 250 / 380 / 700 g, package 350 / 480 / 900 g, the skirts' kind insulated. Its
`defaults_version` 17; the other rows keep theirs.

**Table version 15 (2026-11-21).** The row of 50002796 티셔츠 (women's long-sleeve golf tops): the windbreakers' box and
kind, a lighter top (product 120 / 250 / 600 g, package 300 / 350 / 800 g). Its `defaults_version` 15; the other rows
keep theirs.

**Table version 14 (2026-11-21).** The row of 50002799 재킷, the same section as 50002798 (the owner's decision): its
values and kind. Its `defaults_version` 14; the other rows keep theirs.

**Table version 12 (2026-11-20, the owner's word on the pilot report).** Row 50002797 gets the kind `insulated`
(`match` 방풍 / 다운 / 구스 / 덕다운 / 패딩 / 충전재 / 솜털 / 웰론 / 하이브리드 in the title or the variant): a
windproof-lined, down or padded knit, product 450 / 600 / 1000 g, package 500 / 700 / 1200 g, box central 30 x 24 x 6
cm (0.864 kg volumetric: the tariff's 1 kg step, about +10 USD); 10 of the 30 pilot products are such (9717223659
states 673 g). Its `defaults_version` 12; the other rows keep theirs.

**Table version 11 (2026-11-19, the owner).** The row of 50002797 니트 (women's golf knit cardigans, a folded garment in
a mailer): product 250 / 400 / 800 g, package 300 / 400 / 900 g with a plausible band 300-1500 g (the owner: a parcel
is never under about 0.3-0.4 kg; a stated value outside is not taken), box low 25 x 20 x 3, central 28 x 22 x 4
(0.49 kg volumetric: the tariff's 0.5 kg step, 42.49 USD), high 35 x 25 x 8 cm. Its `defaults_version` 11; the other
rows keep theirs, so no other product moves. No kinds, no baselines (sizes and 2-piece sets are not told apart yet).

**Table version 10 (2026-11-18, the review of the 100-chipper scroll; the agent on the owner's delegation).** Bands
only, row 50002784: `product_weight_g` 300-650 -> 350-600 (the 51 club totals the 217 collected chippers state are
358-582.5 g; MYKUJA's Amazon "Item Weight 330 Grams" is the head, as MAZEL 11775287147 types "헤드 무게 330g";
13492844017's "Item Weight 0.64 kg" a shipping weight), `package_weight_g` min 350 and `package_length_mm` min 850
(the lightest stated club 358 g, the shortest 32 in = 813 mm: rockible 13261416672's Amazon "Item Package Dimensions
13.77 x 5.9 x 2.75 inches" / "Package Weight 0.3 Pounds", 350 mm and 136 g, cannot hold its 90 cm club; its box is
refused whole, `box_not_whole`). The maxima 5000 g and 1500 mm only close the band (the stated boxes are 960-1000
mm). `defaults_version` stays 9: no default is restamped. Measured read only (`run_transform.run(cache=False)`, every
write suppressed, 3,390 latest lines, against the same run on version 9): 6 products move, all 50002784, nothing
elsewhere: 13261416672 (withdrawn, `hold:`) its four package fields to the defaults ($139 -> $259 on the default
box); the product weight of 13551983071 and 13492844017 (published drafts, 2 variants), 13325891959, 13037712071 and
13037712605 (never sent) to the 470 g default. No published price moves (the price reads the package weight and the
box only); the two drafts are sent again only on the owner's word. Fixtures 13261416672, 13551983071.

**Table version 9 (2026-11-18, the chipper review; the agent on the owner's delegation).** Row 50002784 measured: 33 of
the 59 collected chippers state the club's total (notice, spec rows, description, the images' OCR), one median per
product: min 358, p10 395, median 465, mean 472, p90 545.5, max 548 g; the product weight 430 / 500 / 600 -> 380 /
470 / 560 (5 of the 33 were under 430). Stated club lengths: median 34.75 in, longest 35.75 in (908 mm): the length's
low 900 -> 920 (central 960 and high 1000 kept). `plausible: product_weight_g 300-650`: 7004743758's notice "중량:
962g" (a UK import's shipping weight) and 13478213249's Amazon "Item Weight 0.68 Kilograms" (the shipping weight in
these imports) are no longer the club's. The package weight 800 / 1000 / 1300 and the box sides stay the owner's (one
stated box only, 12181419107's 12.5 x 12.5 x 100 cm); the price reads only the package weight and the box, so no
price moves (the lever is the box sides' confidence: one box measured by the owner would take about $100 off each
chipper). The row's `defaults_version` 9, the others keep 7; the band reaches the lines collected before it
(`current_bands`). Measured read only (`run_transform.run(cache=False)`, every write suppressed, against
`prepared/products.jsonl`, 3,232 lines): all 59 chippers' defaults restamped (product weight, the length's low,
`table_version` 9), the two stated weights above refused; outside 50002784 one product moves, 13595174592 (50002787,
withdrawn) whose "Item Weight: 4.54 g" falls out of the junior row's band of 2026-11-17 and takes its 3500 g default.
No price, SKU or status changes.

**Table version 8 (2026-11-18).** The row of 50002784 치퍼 (the owner, sold as single chippers, one club of 34-35 in):
one chipper in a club box, no bag, 96 x 11 x 8 cm and 1000 g central, the product about 500 g (low / high the
agent's range: product 430-600 g, package 800-1300 g, length 90-100 cm, sides as 50002783's `single_club`). One
default, no kinds, no plausible band, no baselines (one club, no set). At level 1 (x2.50) the box prices a 35,000 KRW
chipper at $259, 90,000 KRW at $329, 250,000 KRW at $539 (`shop_pricing` quote, billable 1.69 kg). Every row now
carries `defaults_version`, the version its defaults stamp (`table_version`, `package_measures.row_version`), raised
only with that row's own fields or kinds: the version alone would have restamped 92 prepared products of the other
rows from 7 to 8 with no number changed (`current_defaults` stamps a default whose numbers moved since its
collection). The four rows before carry 7, what their restamped defaults had; 50002784 carries 8 (9 since its measured
row, version 9 above). Measured
2026-11-18 (read only, all 3,173 latest lines prepared afresh with their sidecars against `prepared/products.jsonl`):
all identical.

**Table version 7 (2026-11-17, the wedge-set review W8).** The first `plausible` bands (50002783, 50002787), the
50002783 count kinds `two_wedges` / `four_plus` (`lofts`) and its `compose_by_count` block; a box refused whole on
the server path too (C11, kept (owner delegated, 2026-11-17): 13372006463's 945 x 51 x 25 mm box refused, sent at
$639 by the 50002783 default box); kilograms / pounds in the description for 50002783; the typed label / value lines (50002783
only: in 50002787 they would have moved two published junior PGM clubs, 10259486834 $749 -> $219 and 10259500908
$309 -> $209, through "패키지 치수" / "100*12.5*12.5cm"; widening waits for the owner). A default
whose numbers did not change keeps its collected `table_version`; one that did (a two-wedge variant) is stamped 7
when prepared again (`current_defaults`). The server's own reading (`measures`: bullets, flex rows, split lines,
colour-only variants, a package weight under a club heading) reaches a product only when it is collected again;
measured 2026-11-17, outside 50002783 that will move 3 published 50002788 full sets' package 7000 -> 10165 g (composed,
dearer), 5 50002788 sets' product to 5.85-9.07 kg, 4 published 50002787 products' to 4082-4990 g, and give 5 junior
50002787 products a stated package of 3175-4990 g in place of the 4500 g default.

**The count and the box (2026-11-17, the resend review D1 / D2).** A weight the listing states once is checked
against each variant's count of wedges (50002783: [A weight against the variant's count](#a-weight-against-the-variants-count));
no product weight is kept above the package (every category: [No product weight above the package](#no-product-weight-above-the-package)).
The `below_contents` flag stays only where the product weight is not the seller's. No table change (version 7).
