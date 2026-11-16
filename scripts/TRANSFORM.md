# Transform: collected to prepared

The transform of collected lines into prepared products per shop, the five package fields (weight and size, with the description images' OCR) and the record types; split from scripts/README.md on 2026-11-16 (history: `git log --follow scripts/README.md`).

## Package weight and size

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
outside it is not taken (`contradiction`, `reason: implausible_for_category`) and the default fills the field; no row
has a band yet, and none is made up. A row may also carry **`baselines`** (the owner, 2026-11-10), the operator's
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
code. The table's `version` is 2 since the block. A missing field comes from
`category_measures.json`, the operator's table (per leaf category: low / central / high of the five fields, who
approved it and when, the table's version), as `source: category_default`; a seller's value is never overwritten.
No row for the category: `CategoryDefaultsMissing`, the run stops and asks the operator (values are never made
up). Every row carries `reliability`; today one level, `estimated_average` (the weakest: an average of estimates,
not measured); the price rule's coefficient goes by the lowest `confidence` of the box's three sides, not by this (see The price).
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
the title screen. Version 6 since.
Product sizes (not the package: kind product or unknown) are kept apart, optional.
Every field carries `confidence`, **1 to 5** (the owner, 2026-11-10):

| level | meaning |
|---|---|
| 5 | the seller states this field itself in typed text and says what it is: a net weight, a weight with the package, the box's sides (the server path); a typed box or packed weight in the description |
| 4 | the seller states it, a weaker reading: read from an image, or its kind left open (a plain 중량 11.5kg: with the box or not), or bound to the variant by club count, or a per-piece weight times the count |
| 3 | worked out wholly from the seller's own figures for this product, plus the operator's carton / margin: the clubs' exact sum with the bag absent or its weight stated (the count and the bag's state from the listing or the typed text); the length from the driver read; a package weight on such a product weight |
| 2 | composed with a baseline or a weak part: the count x the median, a baseline club / bag / longest club, the baseline box sides, the bag's state known only from an image's sentence or a closed list of clubs, the count read from the images or taken from the clubs' table alone; the bag assumed (`flags: ["container_assumed"]`: the clubs are known and nothing says whether the bag ships, so the baseline bag, the heavy side; the owner 2026-11-11) |
| 1 | the flat category default: the composition is unknown |

**The scale changed on 2026-11-10** (it was 1-3 since 2026-11-06: 3 stated with its kind, 2 stated with the kind
open or the binding worked out, 1 the default). Records written before the change carry the old numbers: collected
lines (`package` is computed at collection), prepared records of `format: prepared/4` and below, and what was
published from them; `prepared/5` is on the new scale. The transform puts a collected line's seller values on
today's scale from their own evidence (`package_measures.on_scale`: the old 3 is 5, the old 2 is 4), so one prepared
record never mixes the two. Of candidates that agree, the most certain is taken.

### From the description images (optional stage, the owner 2026-11-07)

The images are most of a description (golf sets: ~12x the page's text) and state what the page does not: a box,
a product's weight and size, or, for sets, each part's. The stage reads them; the transform takes from that text
what the seller states of the five fields and, for a set, composes the rest from its parts ("The order of
sources" below; until 2026-11-10 the larger of the guess and today's value won). The same reader also gets
the lines of the seller's typed description (`details.description.text`, 2026-11-10) as one more block of rows:
no OCR doubt, table cells joined by " | " ("패키지 무게 : 10.8kg", "클럽 무게(g) | R: 294 / S: 297 | ... | 528"). A
value read there says so in its evidence (`from: description_text`; `source` stays `description_image`). It is
read with the images or not at all (no sidecar, or a stale one: neither is read).

**The operator's (or an agent's) order of commands**, after each collection:

```sh
.venv/bin/python scripts/example_99_full_details.py                  # 1. collect (server running)
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # 2. keep the run
.venv/bin/python scripts/description_images.py fairwardgolf          # 3. read the description images (network)
.venv/bin/python scripts/run_transform.py fairwardgolf               # 4. prepare (offline)
```

Step 3 is not part of the collection on purpose: it is slow (~20 s a product, ~3.5 h per 1000), needs only the
image hosts (no server, no Chrome) and can be run, stopped and resumed on its own. It reads only the categories
whose shop rules set `description_images` (transform_shops; off by default, on for 50002788). Skipped, the
transform still runs: the products get the note `description_images_missing` and today's values.
`--products <id> ...` reads some products only, `--force` reads again.

**What it fetches.** Each kept product's `details.description.images`, in order: seller banners out (by name, link,
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

**Memory and failures.** Each product is read in a fresh worker process (one at a time, synchronous,
`read_isolated`); the OCR engine and the image bytes die with it, so a long run never accumulates RapidOCR's memory
(live: the worker up to ~2.1 GB, the run ~50 MB). A worker that crashes, is killed (memory) or outlives
PRODUCT_TIMEOUT (900 s) is that product's error: one more try, then an error sidecar (note
`description_images_failed`; `--force` reads it again); the run goes on. Ctrl+C stops cleanly (exit 130). One run
per shop at a time (a lock; a second run stops with exit 4). A script that calls `description_images.run()` keeps its
work under `if __name__ == "__main__":`: the spawned worker imports the calling script again (example_15 hung once
without it, its worker collecting a second product).

**Files**, per shop, under `scripts/output/shops/<shop>/description_images/`:

```
<product id>.json            the sidecar: the rows as read per image and slice, skipped links with their rule,
                             each image's host (naver / seller), the engine and its settings
cache/<product id>/<sha>.bin the downloaded bytes of that product: `--prune-cache [--products ...]` deletes them
                             (the sidecars stay; a --force run fetches again)
```

The cache holds ~6 MB a product (~6 GB per 1000, 2026-11-07): prune it once the sidecars are good (whether to keep
it by default is still open with the owner).

A product is read again when its links or the engine (rapidocr, onnxruntime, params) changed, or when an image
failed last time with a 5xx / network error (`failed`); a 4xx or a non-image (`gone`, e.g. an expired proxy-smartstore
token) and a seller's hotlink block (`refused`) are not retried; the transform notes them (`description_images_partial`).
Naver first (the owner, 2026-11-07): a body Naver cut into snap tiles is read from the tiles; the seller's own `<img>`
sources in its HTML (7583123963: 45 instead of 113) are fetched only when a tile does not read, and used when every
source reads (a seller's host can be 5x slower: 13369469193 266 s vs 54 s; its proxy-smartstore links expire; the
tiles also carry the store's banners, which the text rules cut). To fetch less, an image another product of the store
already read is reused from its
sidecar (`reused`), equal slices in one product are read once (dHash), and a first SmartEditor image lower than
400 px (the store's header strip) is skipped (`first_header`). Measured 2026-11-07 on the 977 slices of the 50 golf
sets: 53 % useful (copy 26 %, spec tables 17 %, set contents 9 %), photos 30 % (cheap to read), store boilerplate
17 %. Not done on purpose: a per-slice "has text" detector (it costs more than the OCR it saves) and a height rule
before the download (set contents sit on small cards: >= 1000 px loses 49 of the 330 useful slices). The download,
not the OCR, sets the time (~13 s against ~7 s a product). A store's first product costs the most (~10 requests,
6.6 MB); later ones reuse its banners. Run step 3 soon after step 2: proxy-smartstore links seemed to expire within
about a day (2026-11-07, not re-checked), and an expired one is `gone`, not retried. Not checked yet: a batch well
over 20 products for the worker's memory and time per product.

**The guess** (`description_measures.py`, offline, in the transform) has two layers:

* the **core**, for every category: what a seller writes of the product itself: a packed weight / box (박스 / 포장 /
  택배 / 패키지), a set / product weight (세트 / 본품 / 제품 / 상품 무게; a row labelled 무게 / 중량 / weight with kg,
  even when OCR split the label: "무 / 0.6kg"), a product size triple (크기 / 사이즈 / 규격 / size, or with a unit:
  "W53 x D38 x H62.5 cm"; read as a fact and, since 2026-11-10, no field's: a product is not its box). Live check
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

**The clubs** (the profile's items; mined on the 120 collected sets, 2026-11-10). Their tables come two ways: a
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

**More of the page, 2026-11-11** (the 300 sets of the fairwardgolf job; the products on the flat default weight
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

**Whether the variant has the container**, in the order of trust (2026-11-10; the first that says it decides):

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

**The order of sources** (the owner, 2026-11-10; `merge_fields`). The flat category default is the last resort. A
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

**Absurd values are never taken** (`compared.rejected`; `refused` on the composition that stood in): a statement
outside the field's band (the operator's `plausible` in category_measures.json, else the profile's, else the
core's: weight 10 g - 200 kg, a side up to 3 m), any value above the band or more than 3x today's value
(`far_above_today`: a misread "45.5kg", another product). The band's lower side is for statements only: a
composition under it is a small set, not a misread (three clubs). A stated packed weight under the product's
weight is taken all the same; when that product weight is the seller's own (4-5) the field carries `flags:
["below_contents"]` (a box weighs at least what is in it: two statements of the seller, the operator decides).

**Known limits** (2026-11-10, left as they are). A "1+1" listing ships two sets and is weighed as one
(5684497984: about half its weight). A table is not bound to a variant: of several whole tables the lightest
stands for every variant (the S세트 variants of 11659201020 and 5543663553 get the R row, about 300-350 g under;
the two women's variants of 7674852369 get the men's twelve clubs). On a page of several models the bag's
weight may be another model's bag (12696567111: the XR24 stand bag's 4.1 kg on the XR26 set) and the longest
driver stands for every variant. The median is the page's, also of clubs that are not in the set (12965394174:
the add-on woods and utilities; 7583123963: no iron's weight is read).

The owner's rule on parts (never summed) holds for the
seller's candidates (`specs.measures`); for the composition, summing the items is the point. Read as facts and no
field's since 2026-11-10: a product's size, the bag's length, mouth and sides (the box's sides are the baseline's;
7583123963 states a bag of 130 cm in total where the driver + the margin gives 1230 mm). Notes:
`measures_from_images` (fields no longer today's: stated in the images or the typed text, or composed; per variant count), `description_images_missing` (switch on, no
sidecar; never holds), `description_images_stale` (the sidecar was read from other links, an older collection:
not used; run the stage again).

### The images' text, ready for the translation step

Checked by eye against the images (2026-11-07, 20 live sets): prose reads near-exact, spec tables ~95 % (a digit
lost now and then, a degree sign read as 0), small lettering on photos poorly; the rows as read are not a text yet.
`run_transform` turns each product's current sidecar into clean Korean blocks (`description_image_text.py`) and
writes them for the next step, translation (not done here). Fixed after the 100-run check (2026-11-08): a
cross-sell cut starts only at a heading (a sentence cut 292-330 rows of three Sterna listings' spec sheets), a table
heading or row repeated in another table is kept (only a slice overlap is a repeat), short flex rows ("R / D1/296")
are table rows, and a store banner's address, hours, services and map labels are cut:

```
scripts/output/shops/<shop>/translation/<product id>/
    description_images.ko.txt    the blocks to read: a header (format, sha256), then "[b01 text image 1]" / "[b02
                                 table image 3]" and the block; table rows are cells "a | b | c"
    description_images.ko.json   {format: description_image_text/1, product_id, key, sha256, blocks: [{id, kind:
                                 text | table, image, text}]}
    description_images.en.json   written by the translation step: {format: description_image_translation/1,
                                 source_sha256: the .ko sha256 it translated, blocks: [{id, text}]}
```

**One flag** on every prepared product says where it stands; the translation step (and any checker) reads the flag,
never the folder: `product.description_images_text = {state, blocks, chars, sha256, dropped, ko, en}`, `state`:

| state | meaning | the translation step |
|---|---|---|
| `off` | the category does not read its images | nothing to do |
| `not_read` | it does; description_images.py has not read this product's current links | run the stage first |
| `empty` | read; nothing left (photos, the shop's own blocks) | nothing to do |
| `to_translate` | `ko` written; no translation of this exact text | translate `ko`, write `en` with `source_sha256 = sha256` |
| `translated` | `en` exists with `source_sha256 = sha256` | done (a changed Korean text goes back to `to_translate`) |

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

## Transform (collected -> prepared, per shop)

The step after collection and before translation and Shopify: offline, deterministic, no AI, no English, no
network. Korean stays Korean; each prepared product lists the Korean texts the translation stage must translate.

```sh
.venv/bin/python scripts/keep_run.py scripts/output/full-50002788    # keep the run before the next collection
.venv/bin/python scripts/run_transform.py fairwardgolf               # every kept run -> prepared/
.venv/bin/python scripts/run_transform.py fairwardgolf --full        # the same, every product prepared afresh
.venv/bin/python scripts/run_transform.py fairwardgolf --verify      # each cache record vs prepare afresh
```

```
scripts/output/shops/<shop>/collected/<category>-<UTC time>/   products.jsonl, images/, manifest.json (read-only)
scripts/output/shops/<shop>/prepared/products.jsonl            one prepared product per line, rebuilt each run
scripts/output/shops/<shop>/prepared/report.txt                ready / held counts, held products and why
scripts/output/shops/<shop>/prepare_cache/<product id>.json    the prepare cache (below): derived, not backed up
```

**The prepare cache** (2026-11-16): `run_transform.py` and `job.py` keep each product's `prepare()` output and its
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

example_99 overwrites its `products.jsonl`: a run not kept before the next collection is lost. The shop is the
namespace of the source keys, one shop and one category per run; a product in several runs comes from the newest.
A run is copied into `<run>.partial` and renamed when complete; only folders with a `manifest.json` are runs.

**Prepared product** (`transform.Prepared`, `format: prepared/5`; 5 since 2026-11-10: package `confidence` is 1-5 (1-3 before) and a field may be `source: composed` with `parts`, `baseline` and `refused`; 4 since 2026-11-08: reviews sanitized; 3 since 2026-11-08: no shop leaves, `product.attributes`
instead (see Placement); 2 since 2026-11-07: a variant's `package` fields
may carry `how`, `quote`, `flags`, `from` (`description_text`: the quote is typed text, not an image's) and `compared` (the value not kept, see Package weight and size), and `product` has
`description_images_text` (the images' text flag, see The images' text)): `key`, `shop`, `status` (`ready` / `held`),
`held` and `notes` (`{code, detail}`), `source` (run, line, link, channel_no, product_id, category_id), `product`
(`title_ko`, `brand_ko`, `brand_source`, `attributes` (`{gender: {value, variants, evidence, flags}}`), `options` `[{name_ko, values_ko}]`, `facts`,
`variants` `[{source_id, naver_variant_id, options_ko, price_krw, price_usd, sku, available, package}]`, `pricing`,
`specs`, `personalization`, `addons`, `rating`, `reviews`, `images`), and `texts` `[{id, kind, ko}]`: the translation
worklist, `id = <kind>:<sha256(ko)[:16]>`, so the same Korean text has one id (one translation) in every product.

Rules (`transform.py`, each from a real case, research 2026-11-05 on 23 collected sets: on 10 the naver-harvester
published, SKUs and prices equal on 201 of 201 variants):

- **Prices**: KRW = the product's price + the variant's `extra_price` (the page's own answer; option names are not
  parsed for money); USD = rounded up to the cent at the shop's rate (kept in the record; Shopify's cost and price
  are made at publication by the shop's price rule, see The price); no compare-at, not taxable.
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
  UNIT_QUANTITY_PAID listing goes into the purchase; any other fee type counts as free (see The price). An
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
- **Pilot 20 (2026-11-06)**: a variant carries `today_dispatch` (the seller's todayDispatch per variant: one of two
  may ship today); a tag every value starts with ("[당일출고]") and a "(선택)" in front of an option name are left out
  (the SKU keeps the raw tuple); past the cap the rows are taken in turn from each value of the first axis; notes
  `few_pieces` also from 총클럽개수 of 5 or fewer, `gift_hidden` (a hidden 사은품 row naming a thing in the box, not
  points or a coupon: "오리지널커버 증정"). `delivery.lead_time` passes through: check `today_off` before
  `today_cutoff`.
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
- **Reviews**: the selected reviews (video posters already photos), rating and count from Naver's summary.
- **Held**: `collect_incomplete`, `price_unknown`, `no_variants`,
  `options_unaligned` (rows that do not fit the groups), `specs_folded` (the 상품정보 list stayed folded), `axes_over_3`,
  `no_images`, `images_over_50`.
- **A brand for every product** (the owner, 2026-11-08: the Shopify vendor is never empty; no brand, at least the
  manufacturer). A seller who links no Naver brand leaves no 브랜드 row and no brandName, and Naver then knows none
  anywhere (6 of 143 sets: not in the product answer, the page's answer, the search cards, the notice, the page's
  ld+json). `brand_source` says where it came from: the row / brandName; else the manufacturer
  (`manufacturer:<source>`, never Naver's M0000000); else, run-level (`brand_fallback.py`), a brand the shop's other
  products state found in the title (`title`: 4 of the 6; the first one of a combination set), a brand of the
  dictionary starting the title (`title_known`) or standing as a word of its own in it, three letters at least, by
  its Korean name or its Latin spelling (`title_word`: 라즈러스, 버뮤다, GoSports in wedge imports, 2026-11-15), a Brand
  row of the description, the spec table an agency import copies (`description_row`: "Brand | WENGH", 2026-11-15),
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

**Per-shop rules** (`transform_shops.py`, data): SKU prefix, KRW per USD, variant cap, and per Naver leaf category
`paid_variants` / `paid_addons` / `description_images`, off by default, all on for fairwardgolf 50002788 and
50002787 (junior clubs, 2026-11-11), 50002670 (women's iron sets, 2026-11-14) and 50002783 (wedge sets,
2026-11-15; no parts profile: the core reading only). `sets_only` (wedges, 2026-11-15): a variant whose own words
sell one club (1PC, 단품, 개별, 싱글, or one loft 44-72 with no set word or count; "i60R" is a shaft) is left out, and a
product of such variants only is held `single_only` (17 one-wedge listings of the pilot filed as "웨지 세트 또는
개별"). A loft written again on a second axis that describes the same club ("Size: 56 Degree" + "Style Name: Black
56 Degree") counts once; on axes that are club slots (names equal but for a number: 옵션 1 / 옵션 2) each counts
(two Yamato imports published as sets, 2026-11-15). The shop's
sections are not decided here (Placement). A shop or a category without rules: `ShopRulesMissing`, the
run stops and asks the operator.

Not here (later stages): the shop's sections, tags and product type (Placement, `placement.py`), English (titles,
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

