# Changelog

Versions follow `VERSION` at the repo root; `/health` reports it. The browser adapter in `extension/` has its own
version in `extension/manifest.json`.

## Unreleased

- **Brands** (the junior clubs' 30, 2026-11-12): a trading company's name is no brand (`brand_fallback.trade_name`:
  상점, 상사, 홀딩(스), 무역, 유통, 인터내셔널, ...; "X 협력사 / 협력업체" is X's): a shop wrote 세모물상점 as the
  brand, a supplier 스퀘어홀딩 stood in 원산지; the next source decides (the images said Inparo, PGM). One brand
  whatever its dots and spaces (`shopify_payload.brand_key`: "U.S.KIDSGOLF" is U.S. Kids Golf), written once in
  the title; a first word with the brand's letters swapped is the brand ("PMG" -> PGM).
- **`publish.py --withdraw <key> --reason`**: a published product goes DRAFT (off every channel, nothing deleted)
  and is never sent again. Withdrawn: a junior bag alone (314400655) and soft toddler clubs (4987660149).
- **Junior clubs**: a bag alone is left out of the listing (`bag_only`, with `unless` words for a set with a
  bag); two clubs get a box for two (`two_clubs`, 95 x 15 x 12 cm, 1.5 kg: the single club's with one more).
- **The junior clubs' 100** (2026-11-12): 100 published, 6 closed (card gone). The run showed: a seller's brand row
  is cleaned (`brand_fallback.clean`: a code, a note, a word twice, the product's words go; an age, a shop's name
  (상회, 만물상, 쇼핑, "X네") give none; a reselling shop's own name, its maker "<shop>협력사", is none); a Latin brand of the shop counts in the images as whole words only (GB in
  "golf bag" had made two Ben Sayers sets GB); 원산지's brackets split ("중국 oem / 인파로": 인파로); a brand inside a
  Korean branch's name comes last in a title (던롭스포츠코리아 젝시오: XXIO); an age, a height, a loft, a size or a
  year is no club count for the package kind (four single junior clubs had the set's box, $709-729 -> $259-289).
  Two measures fixtures (5396141262, 6849582078). 363 new dictionary entries read by a review and an adversarial check: 11 non-brands
  out of the brand dictionary, 20 entries corrected (option names fit to one product: 모델선택 "Age Group" -> Model).
- 18 junior products and one full set published again (brands, titles, two-club prices $749-799 -> $349-399,
  dictionary fixes), 7 with a new handle (the old one redirects); 24 dictionary entries set by hand, then backed up.

## 0.15.0 (2026-11-11)

- **A new category: 50002787 주니어용클럽** (the owner, 2026-11-11) for fairwardgolf's Junior Golf Clubs & Sets
  (`junior-clubs-sets`, one section, no split). The full sets' rules (paid variants and add-ons, the images read; no
  parts profile), the same price rule. **Two defaults** in one row: a set's box (105 x 28 x 25 cm, 4.5 kg) and a
  single club's (90 x 12 x 10 cm, 1 kg), by the title's and the variant's words (`kinds`,
  `package_measures.default_kind`). The transform takes each default from today's table (`current_defaults`). Its
  translation brief, a description profile `junior_clubs`, the sets' review aspects, glued-flex rule and glossary.
  10 real products published and checked in the collection; two measures fixtures. First run of the
  `new-category-or-shop` skill; ONBOARDING.md and the skill carry what it taught.
- **A job's paid choice stays with its own products** (`run_transform.paid_choices`, read from the jobs' files):
  the transform prepares the whole shop, and the `--paid` junior job had prepared 101 published full sets with
  their paid variants (nothing was sent: they stood untranslated). A run by hand now prepares the same way.
- **`publish.py --dry-run` spells the vendor as the real run** (`offline_ids`: the brand dictionary's spellings and the
  tenant's name without the store): it had written "maruman" for Maruman and "Fairward Golf <title>" for the
  shop's own brand, which read as a regression.
- **`store_diff.py`** (read only): what a publication would change in the store, field by field, and the published
  products that cannot be built now. **publish.py skips by what it sends** (`output` in the ledger,
  `output_digest`): the inputs' digest had moved on 18 of 20 products the store already matched. First run: 434
  of 435 products as in the store (`--adopt` recorded their `output`), one would get a new photo (12211893510).
- **Dictionaries per category**: brands stay the shop's (`dictionaries/brand.json`), every other kind is a Naver
  category's own (`dictionaries/<category id>/<kind>.json`); a new category starts empty. Split by what each
  category's products use: 50002788 1613 entries, 50002787 122; the whole shop translated offline as before and
  `store_diff` found nothing new.
- **Title rules per category** (`listing_title_rules.json`, read by `listing_filter.Screen`): a listing row whose
  title names what the section does not sell is left out before its page is read (`title:<code>`). Studied on
  515 titles of 50002787 (toys, play sticks, educational toys, gloves, an iron cover, loose heads and shafts, an
  adult-club store, a book: 46 of 56 misfits, no product that fits) and 351 of 50002788 (park golf, a woods-only
  "풀세트"). One published junior product matches (4987660149, soft clubs, 교구): left for the owner.
- **A cap on reviews** (`review_pick`, in `collect_product`): a product with more than 8 chosen reviews keeps the 8
  that say most of the product, 3 photos each and 12 in all, before any photo is downloaded; sponsored reviews go,
  a fair low score stays, a text repeated word for word is taken once. On the 10 junior products: 16-20 reviews
  and 13-36 photos -> 8 reviews and 8-12 photos. Full sets (1-2 reviews) are left as they came.
- Dictionaries: 108 entries of the junior run backed up, 8 set by hand first (an age lost from "01.9-12세 퍼터",
  호수 = Size, 선택하세요 = Option).

- **`scripts/ONBOARDING.md`** and the agents' skill `new-category-or-shop` (the owner, 2026-11-11): where to add what
  for a new Naver category or a new shop, what stops, what goes wrong silently, and the golf / fairwardgolf
  literals in shared code to decide on first (the metafield namespace before a second shop).

## 0.14.0 (2026-11-11)

- **`job.py --paid-variants`** (the owner, 2026-11-11): the job's own products get the category's paid variants and
  no paid add-on; the shop's other prepared records keep the free-only rules.
- **A brand of 기타 ("other") is no brand** (the owner: the tenant's name, Fairward Golf, at the end of the
  fallback): neither the brand nor the manufacturer, no "Brand: Other" spec row, the brand rule's last guard. In
  the images' text a Korean brand counts only where a word starts (쇼핑, 치핑 are not 핑) and a web address is no
  brand. Five published sets got their right brand (TaylorMade once, Ben Sayers three times, the tenant once).
- **Translation dictionaries cleaned**: all 1,676 entries reviewed, 40 wrong ones deleted and translated again;
  24 of the new answers repeated a mistake and were set by hand. The 23 published products that used them were
  published again.
- **More package weight and size read from the description** (the owner, 2026-11-11, after the 300-product run):
  small rules in `description_measures.py` (core and the golf-set profile) and the transform's hook, from a study
  of the 300 sets (29 patterns, each checked over all 300). The bag: machine-translated words, a bag as an item
  of the composition, gift bags as accessories, a bag table without the bag's name, a closed list of clubs (no
  bag), the typed "별매" over a bare title word, and the bag assumed when nothing says (flag `container_assumed`,
  confidence 2). The count: option values, 11PC / 11ps, the 풀세트구성 row and composition lines, a typed numbered
  list; one club filed as a set; a title or a list of clubs without a bag says no bag. The clubs' weights: OCR's label spellings and T/W(g), a weight in its label's
  cell / a row above / after an option index, head + shaft + grip columns, the #7 iron's weight for the clubs not
  weighed, a part table + its median for the rest, per-row tables that make the set, short sets. The length: a
  bag's accepted length and a shaft maker's table are not a club's, a driver over 46.5 in needs two rows, OCR's
  labels and a lost dot, the driver row of an L / A variant's flex.
  Core: shipping rules, a buyer, a shoe box never read; "풀세트 패키지" is the set; "크기,중량" is the product's
  weight. On the 426 products: the flat default weight from 109 to 23; 200 products get new fields (26 of them
  with the bag assumed). Two review rounds over the 300 changed the first cut (an option's "아이언 9개" is the
  irons', not the set; "(#5 기준)" is a wood's; a women's driver only for an L / A variant; the bag's own size is
  not the box). Fixtures: 18 new real products in `fixtures/measures/`, one per rule; the pins of the others
  moved where the rules read more.

## 0.13.0 (2026-11-11)

- **Prices with delivery, duty and margin inside them** (the owner, 2026-11-11). In fairwardgolf every variant's
  price comes from `shop_pricing.Policy.quote` under the rule `landed/2`: the purchase (the Naver price as shown,
  the discount included, plus the seller's delivery in Korea when the listing's fee is PAID or
  UNIT_QUANTITY_PAID; at the owner's constant 1 000 KRW = 1 USD, up to a dollar), ShopNShip's 3 USD, the US duty
  prepaid (PDD, 12.5 % of the purchase whatever the country of manufacture), the delivery by the partner's tariff
  times the coefficient of the box's least certain side (1.00 / 1.10 / 1.20 / 1.40 / 2.50 for levels 5 ... 1), FedEx's
  dimension fee once per box, the margin (25 USD + 11 % of the base, never under 30), the payment system's 3 %,
  then up to a number ending in 9 (99 from 1000). Shopify's cost per item is the purchase with the commission; the
  duty is a line of its own in the price, never in the cost per item (`landed/1` of the same day had the margin on
  the owner's points and the duty in the cost: replaced). A shop
  without the rule keeps `krw-cost/1` (price = cost). The rule, its numbers, what it leaves out on purpose
  (fuel and insurance are in the tariff, FedEx's 18 kg minimum is a switch, off) and the behaviours the owner
  accepted after a review on the 120 products: scripts/README.md, "The price".
- The delivery tariff as data (`delivery_tariff.py`, `delivery_tariffs.json` version 1 with a `history`):
  ShopNShip's FedEx International Priority, Korea -> US, 71 steps from 0.5 to 50 kg, captured from the partner's
  public calculator on 2026-11-11 (`shopnship_rates.py`: `quote`, `capture`, `compare`). The captures and two
  explorations (`shopnship_explore.py`, 427 requests, every modelled answer equal to the model but one weight of
  17 digits the server reads as a binary number) are in
  `scripts/fixtures/shopnship/`, the backups a new capture is compared with. Over 25 kg the partner's steps
  already hold FedEx's dimension fee (`included_surcharge`): it is not added again nor multiplied. A box over 50
  kg, or a variant without a box, has no price: the product is held. The review of the tariff is by hand: a new
  capture is compared, then adopted with a new version. AGENTS.md rule 3: the calculator is a new outside fetch,
  by hand only, never in the price path.
- Shopify: a new variant metafield `fairwardgolf.price` (`fairwardgolf-variant-price/1`: the whole breakdown, the
  tariff's id, date and version included); the product's `pricing` is `fairwardgolf-pricing/2` in a shop with the
  rule; the variant's `source.costUsd` is the cost per item. Add-ons: the rate only. The rule's
  numbers and the tariff's version are in the publish digest: the next whole-shop `publish.py` run would send
  every published product again.
- The ledger row keeps `pricing` (the rule's version) and `prices_usd` [min, max]; a job's `published` event and
  its done line show the price.
- `reprice.py <shop>` for products already in the store: a dry-run table of old -> new prices (also a TSV under
  `publish/`), `--apply` sends them through `publish.publish_one`, on the owner's word. New products get the rule
  in the full flow (`job.py new --publish`). The 120 products of the store were moved to `landed/1`, then all 125
  (with the 5 of a pilot job) to `landed/2` the same day, on the owner's word: every one of the 1 127 variants in the
  store checked against the rule (price and cost per item), 939 to 5 099 USD.
- Tests: `test_shop_pricing.py` on real products cut down to what the rule reads (`fixtures/pricing/`,
  `UPDATE_GOLDEN=1`), `test_delivery_tariff.py`, `test_shopnship_rates.py`, `test_shopnship_explore.py`, `test_reprice.py`;
  `scripts/conftest.py` fails any test of the folder that opens a network connection.

- Package weight and size of golf sets: the flat category default is now the last resort (the owner,
  2026-11-10; it replaces "the larger value wins" of 2026-11-07). A field takes the seller's own statement of it
  (the server path's value, never replaced; else a packed weight, a box or a set weight read in the description's
  typed text or images), else an estimate composed from the set's parts, each part from the product's own data
  when it is there and from the operator's baseline when it is not: product weight = clubs (the sum of one
  table, else the count x the median when the weights cover half the clubs, else the count x the baseline club)
  + bag (none, its stated weight, else the baseline bag); package weight = product weight + the baseline carton;
  package length = the driver read, else the baseline driver, + the baseline margin; width and height = a stated
  box, whole or not at all, else the baseline sides without / with a bag. The default stays only when the number
  of clubs or the bag's state cannot be told (21 of the 120 sets: the bag's state on 20, the count on 1). A
  composed field carries `source: composed`, `how`, `parts` (where each part came from), `baseline` and, as
  `compared`, the default it replaced.
- After a second independent check of that change (2026-11-10):
  - a known composition is never dropped for being under the band of a full set: 13302492097 and 12966969668 (a
    driver, a wood and a utility, no bag) are 1020 g and 3020 g packed, not the flat 5700 / 7000 g. The band's
    lower side now holds for statements read in the description only, its upper side for everything;
  - the seller's own club table goes before the listing's "pieces": a full table (one row or the rows under one
    header, 9 weights and up, the heaviest a putter's, 475 g and up) is the set when the listing counts up to 3
    more or states no count: its sum, its length the count (8053135821, "12개" with the bag and two head covers:
    3955 g for nine clubs, 5340 g before; 13657325637, "11피스": 3634 g; 5543663553 and 7674852369, no count
    stated, leave the flat default). The count is then the table's (`count_from: "table"`, `count_listed`),
    confidence 2;
  - a stated packed weight always goes before the composition, also under the composed product weight (it was
    refused as `below_contents`); under the seller's own product weight (4-5) it is taken with `flags:
    ["below_contents"]`;
  - "the weights cover half the clubs" counts clubs, not values: weights within 2 % of each other are one club's
    (a club by two flexes). Five sets go from the median to the baseline club (10816781893: 3 clubs of 9 weighed,
    3060 g, 2664 g before; 10816508198, 10839715113, 13747890950, 13229257286);
  - the same statement read in an image and in the typed text is the typed one (5, not 4).
  Known limits, left as they are: a "1+1" listing weighed as one set (5684497984); a table is not bound to a
  variant (the lightest of several whole tables for every variant); on a page of several models the bag's weight
  may be another model's and the longest driver stands for all (scripts/README.md, "Known limits").
- `category_measures.json` version 2: row 50002788 has a `baselines` block (the owner, 2026-11-10: club 340 g,
  bag 3800 g, carton 2000 g, longest club 1140 mm, length margin 100 mm, box sides 200 x 160 mm without a bag and
  400 x 320 mm with one; approximate until the first real shipment), with the basis of each amount; validated in
  `package_measures.check_row` (all amounts or no block). It replaces the optional `estimates` block, which no
  row ever had. A row without the block composes nothing.
- **Confidence is 1-5 on every package field (it was 1-3).** 5 stated in typed text with its kind (the old 3), 4
  stated with a weaker reading: an image, the kind left open, bound by count (the old 2), 3 composed wholly from
  the seller's own figures plus the carton / margin, 2 composed with a baseline or a weak part, 1 the flat
  default. Records written before this change carry the old 1-3: collected lines, prepared records of
  `prepared/4` and below, and what was published from them. Prepared records are now `prepared/5`; the transform
  puts a collected line's seller values on the new scale (`package_measures.on_scale`).
- Fixed in the description reader after an independent check: a stated box was merged side by side (a refused
  length left its width and height behind); the count x the median stood as a set's weight when the page gave the
  driver's shaft options only (8029218821, 13728931694); a shaft's model number was read as a club weight
  ("C1(ULT 250 J-L)", 9321714669); "클럽만의 ..." said the set has no bag; a paid add-on for the bag (a cover, a
  name tag) said so too; a table header whose first cell is the label was no header; the golf constants of the
  shared items code are profile data.
- Regression fixtures for the five package fields (`scripts/test_measures_fixtures.py`,
  `scripts/fixtures/measures/`): 17 of the 120 collected golf sets, cut down to what the measures code reads,
  with the fields each variant must get, checked by hand against the product's own lines (where a fixture's
  note says "approximate", the value pinned is the rule's present approximation, not the page's figure).
  Together they cover every level 1-5, every source and the paths of the rule: a typed box and packed weight, a
  box read from an image, the clubs' exact sum with and without a bag, the count x the median, the baseline
  club / bag / longest club, a bag sold as an add-on, the bag state from the 상품정보 row / unknown, the count
  unknown, the count from the clubs' table, a 3-club listing, counts that differ by variant, an accessory's
  size, a listing of several models, the server path's weight.
- Fixed while checking them: a "중량(g)" row of head weights was read as clubs. 7583123963's summary tables give
  the irons' heads (257-297 g) under the label of the woods' heads (198-233 g); 22 such values made the median
  club 296 g. A row of a weight label with only weights under a club's now makes the label a part's in that
  image (the clubs of that set: 4258 g for 13, 3854 g before; no other of the 120 sets has such rows).
- Nothing under `scripts/output/` was rewritten: at the next `run_transform` every prepared record of the
  category changes (new fields, levels, format), so every published product's digest changes. Whether products
  already in the store are sent again is the owner's decision.

## 0.12.0 (2026-11-10)

- Descriptions for all 110 products in the store (2026-11-10). After a check of the last 75 against their
  sources: a choice the seller's texts offer is not written when "What is sold" fixes the configuration (a
  "popular combination" was described as a free choice), features of another edition or colour are not a source,
  and an intro whose naming sentence was cut starts with the title instead of "It".

- Descriptions after a check of 35 against their sources (2026-11-10: 15 had a wrong club list or count, a fact
  of one choice told of all, or a lost "no bag" sentence): the stage asks at its own effort, `high` with
  thinking on (`DESCRIBE_EFFORT`; Sonnet 5.5 chosen after a comparison of Haiku 5.5, Sonnet 5.5, Opus 5.5 and
  Fable 5.2 at several efforts, the tables with prices are in scripts/README.md "Which model writes the
  descriptions"; `medium` did as well on 35 easy products and worse on the 75 harder ones); the tables read from the seller's images are sent in a section of their own (the set's
  clubs are listed there; a figure only a table gives is not stated); the prompt has the model compare the
  sources and add the clubs up, put the seller's own lists before the Naver spec rows, and tie a fact to the
  choice it holds for; a club inside a range the source gives passes the number check; a seller's disclaimer
  ("specs may differ") is cut; highlights are what sets the clubs apart, not raw measurements.

- Product descriptions (the owner, 2026-11-10): `describe.py` writes a minimalist English description in HTML
  for Shopify's `descriptionHtml`, one model request per product through translate.py's client. The script builds
  the packet (what is sold first, the shop's English, the seller's texts without OCR tables, paid extras, gifts,
  review screenshots and origin lines), decides the country of origin itself (stated when the sources name one
  country, silent when they disagree), checks every sentence and list item of the answer and renders the HTML. A
  product always gets a description, at the least its title as one sentence. `job.py new --publish --describe`
  describes each product before it is sent. The description enters the publish digest only for a product that
  has one: no `payload` version bump, products already in the store are not sent again.

- Title length (2026-11-10, a 137-character title on the store): the translation sends a title over 100 characters
  back to the model (`translate.ASK_SHORTER`, the shortest good answer kept when it never gets under), and the
  publication cuts whole facts, then whole words, to Google Merchant Center's 150 (`shopify_payload.fit_title`);
  the SEO title is cut at a word, not mid-word. `payload/10`: a whole-shop `publish.py` run would send every published product again; a job sends only its own.
- Rule for agents (the owner, 2026-11-10): a fix is for future products; whether products already in the store get
  it too is asked of the owner first (JOB_AGENT.md, Never).

## 0.11.0 (2026-11-09)

- Publication to Shopify, MVP (the owner, 2026-11-08): `publish.py` (CLI and the job's stage, `job.py new
  --publish`), `shopify_payload.py` (offline), `shopify_admin.py` (the products app and the files app),
  `shop_pricing.py` (1 000 KRW = 1 USD up to a whole dollar, cost = price until the margin rule exists). Per product:
  review photos, avatars and a JSON feed on Shopify Files; gallery photos with alt "<brand> <title> - photo N";
  productSet create or update by the source key; ACTIVE; the website publication; a ledger
  `publish/published.jsonl`. Variants on sale are sold without limit (sold-out ones too since 2026-11-09). Metafields:
  the site's `custom.*` in their formats, ours as `fairwardgolf.source` / `pricing` (product) and `source` /
  `package` (variant). No description, delivery, facts or compare-at yet. Three test products live.
- Publication follows the site's strict reader contract (checked on the site 2026-11-08): `custom.optional_addons`
  holds complimentary choices only, in its exact keys (a paid choice or an extra key hid the block); every add-on,
  paid ones with USD prices, goes to `fairwardgolf.addons`; a text field gets `maxLength` only when the seller set
  one; an update deletes the managed metafields a product no longer has.
- Reviews: a line holding only a tax or shipping cost ("세금 배송10", "관세 10만 배송비 2만") is cut; so are a line
  about dealing with the seller, the surprise that it came fast, and a service word left alone ("꼼꼼하게").
- The 100-product pilot (2026-11-09): every store product deleted first (a snapshot kept), 100 golf sets published
  through `job.py new --publish` (50 men's, 50 women's queries; no paid variant or add-on: a job without `--paid`
  now also prepares free-only, `run_transform.run(free_only=True)`). Checked product by product and by four review
  agents; fixed from their patterns:
  - reviews: the seller's service and advice, "I'll come back", what the seller sent, order dates and delivery
    time, weather and holidays, packing (bubble wrap, a torn box), discount and points as the reason to buy, a
    line left on a particle after a cut, `*^^*`;
  - titles: no loft / flex / shaft codes, no club list, no usage or gift words in the prompt; `clean_title` (a
    doubled word or code, "(Parallel Import)"); model spellings in the golf brief (Gloire, X HOT, EFIL-8);
  - vendor: a second brand cut, the brand dictionary's spelling, new vendors remembered within a run;
  - options: a one-variant product named by its remaining choice; seller numbering out of values; option names
    by the kind of choice in the prompt;
  - add-ons: gift words out; a required free choice of a one-variant product to `custom.required_selections`;
  - a title's gender beats a unisex 성별 row; package weight read from a description image's range; SEO title;
    a review ending on "and" closed; one wording for text-field labels.
- The owner's answers after the pilot (2026-11-09): review sentences about the price or value and ones naming
  another platform or a buying agent go (on the English, `review_clean.cut_english`); photo-only reviews get a
  short neutral line; a product with under 2 photos gets buyers' photos in its gallery (ranked: several photos first, useful reviews, no purchase snapshots; 5 photos in all); every variant buyable
  (sold out on Naver too, its state kept in the metafield); a "1+1" repeated option at one price is one option;
  every sales channel; a brand keeps the dictionary's case everywhere (vendor, title, new dictionary entries).
- Publication uploads in batches: review files and gallery photos staged in parallel, created and polled together
  (30 photos: 8 s instead of ~2 min); Shopify's throttling kept (GraphQL calls one at a time, waits on THROTTLED /
  429 / 5xx, the bucket uploads retried).
- A 10-product job published live (2026-11-09) and checked product by product; fixed on the way: " / " in an
  option name, the vendor's company form and spelling, the brand missing from a title, "AS가능" in titles,
  "Select" in option names, rating-only review rows; `publish.py --rehandle`.
- Titles are translated as the store's names: brand first, no shop, dispatch or distributor words.
- Reviews sanitized in the transform (`review_clean.py`, the owner 2026-11-08; `prepared/4`).
  - **Kept:** every review and its score; only sponsored ones are dropped.
  - **Cut** as whole clauses that never cross a product word: shipping, customs, Korean prices, the seller and
    service, packing, gifts, platforms, thanks and other filler, emoji, emoticons.
  - **Graded:** `text_grade` full / short / rating_only, plus `text_quality`.
  - **Patterns:** mined by agents on 666 real reviews, now a test fixture.
  - **On the 143 trial sets:** 448 of 448 kept.
- Dictionary backups carry `backed_up` (UTC) and `translation_dicts.py status` prints the last backup; first
  backup of the live dictionaries (2026-11-08, 372 entries).
- `translation_dicts.py status` is the sync helper: when the live copies were written, the last backup, new /
  changed entries, the ones only in git, and the advice (due at 20 entries or 7 days; changed ones read first),
  `--json` for scripts. The sync only adds: a run takes the entries only git has, a backup keeps git's others. A due backup is a reminder line in the translate report and in `job.py` done / status.
- `translate_eval.py`: the quality check (a varied sample translated with empty dictionaries, judged by a second
  model, a side-by-side report). `scripts/TRANSLATION.md`: decisions, a new shop or category, limits, open items.
- The job translates: `job.py` takes each product to translated, right after prepare (a job made with
  `--no-translate`, or before, stops at prepared). The model is asked only for that product. A product left
  untranslated is `failed` and tried again; every provider down stops the run. Quality rounds with a judge model:
  10 of 260 texts flagged (3.8%).
- Translation tokens: compact requests (short batch ids, no repeated glossary, vendors only with a brand), no
  thinking by default (`ANTHROPIC_TRANSLATE_THINKING`). Reviews are written as an American buyer would write them;
  titles drop the Korean distributor and add no name. A 브랜드 / 제조사 row takes the shop's vendor spelling.
- Translation in batches: a product's short texts by 40 items / 2 500 characters, its reviews apart by 8 / 2 500.
  Each batch is its own conversation with checks, fixes and fallback, and every id is checked at the end. The system
  prompt is the translator's role plus the shop's brief (`prompts/tenants/`) plus the category's brief
  (`prompts/categories/`).
- Translation (the owner, 2026-11-08): `translate.py` translates the prepared `texts` into English through Claude
  Sonnet 5.5 (effort low, JSON output). The texts are resolved in this order:
  - the product's own store (title, reviews, placeholder option names);
  - one dictionary per kind (`translation_dicts.py`: live copies out of git, backups in `scripts/dictionaries/`
    updated by hand);
  - unit rules and 노브랜드 -> the tenant's name (`translation_rules.py`);
  - the model, one request per product.

  Every answer is checked for ids, Hangul, numbers, codes, length and distinct option values. Failures are asked
  again in the same conversation, at most twice. OpenAI is the fallback when Anthropic is down (Anthropic then rests 10
  minutes) or declines a batch. The prompts are in `scripts/prompts/`. The keys are in one 600,
  git-ignored file named by `TRANSLATE_KEY_FILE`, installed by `translate_keys.py install <file>`. The models,
  efforts and chain order are `.env` settings (`TRANSLATE_PROVIDERS`, `*_TRANSLATE_MODEL`, `*_TRANSLATE_EFFORT`).
  The description and the images' text are not translated. New
  dependencies: `anthropic`, `openai`. Tests: `test_translate.py`, offline with fake models.
- Fixes from the quality check of the 100-product run (2026-11-08, 19 suspicious products re-read via
  /products/page): the images' text keeps the spec sheet a cross-sell sentence used to cut (a cut starts only at a
  heading), keeps table headings and rows repeated in other tables (a repeat is only a slice overlap for short and
  table rows), keeps short flex rows ("R / D1/296"), and cuts a store banner's address, hours, services and map
  labels and a notice card's lines; a one-frame GIF in a description is read (animated ones skipped as
  `gif_animated`); an iPhone HDR review photo (MPO with a gain map) is kept (its first picture); 제조사 `M0000000`
  (Naver's "none") is no spec and no hint. Fixture sidecar 6630856593 re-read (its 11 GIFs are animated).
- Placement, the last stage before Shopify (the owner, 2026-11-08): `placement.py` puts a shop's prepared products
  into its sections from the shop's profile (`placement_rules.py`: Naver category id -> sections, the attribute that
  splits one id, what an unresolved product does). The transform no longer decides shop leaves: it writes neutral
  `product.attributes` with their evidence (`attributes.py`; gender from each variant's option values, the 성별 row,
  the title; the listing query only flags) and the prepared format is `prepared/3`; `leaf_undecided` and
  `leaf_from_name` are gone. A product in two sections stays one Shopify product with both leaf tags; a set with
  men's and women's variants also gets a start variant per collection (`start_variants`);
  unknown / conflict is held for the owner. Same sections as before on 192 of 193 checked sets (the other: a women's
  variant in a men's listing, now in both). Tests: `test_placement.py` (the 50 fixtures, the rules case by case).
  `transform_shops.CategoryRules` loses `parent`, `by_row`, `leaves`, `by_title`; `Leaf` / `WOMENS` / `MENS` move to
  `placement_rules.py`. `job.py` STAGES names `placed` between `translated` and `published` (run on the whole shop,
  not by the job). How to add a split for another shop or category: `scripts/PLACEMENT.md`.
- Every prepared product has a brand (the owner, 2026-11-08): no brand stated, the manufacturer; still none,
  `brand_fallback.py` (run-level) takes a brand of the shop from the title, the importer in 원산지's brackets, the
  shop's brand most read in the images, a repeated Latin brand phrase in the images, or 노브랜드; note
  `brand_fallback`, `brand_source` says which. The note `brand_unstated` is gone. On the 143 trial sets: 4 from the
  title, 1 from the images, 1 노브랜드.

## 0.10.0 (2026-11-08)

- `scripts/job.py` (new, the owner 2026-11-07): a job takes one listing and works one product per iteration
  (collect -> one-line kept run -> description images -> prepare), resumable, each product's stage read from the
  files; 409 waits, Naver's error page waits and retries then skips, a wall stops; `new` / `run` / `status`.
  Translation and publication are named stages, not built. `scripts/JOB_AGENT.md`: how an agent runs it.
  `collect_product.py`: example_99's per-product collect, shared. `SourceStopped` carries the API status.
  Then: waits 15 min for the extension / server instead of stopping, asks the owner again for a captcha not answered
  in time (6 times), reads the listings deeper when too few products pass the screen or the snapshot is used up
  (`refresh`), a start / done line per product with stage times, a `== progress:` line every 10, `status` shows the
  running product and stage.
- /products/specs, /products/page: the search tab is kept between reads and the next product is searched in its
  own box; the product tab is closed after each read. A login page on the way is reset from naver.com (no wait;
  R-EXT-3 changed, decision log). A 503's error starts with its kind: `wall:`, `naver error page:`,
  `adapter error:` (ENDPOINTS, K-21).

## 0.9.0 (2026-11-07)

- No brand stated is no longer a hold (`brand_missing` removed): `brand_ko` stays null with the note
  `brand_unstated`, whose detail lists the page's hints (manufacturer, a name in brackets in 원산지); the vendor step
  decides from the title, the hints and the images' text. No brand list: brands are not known ahead of a run
  (the owner 2026-11-07; 2 of 40 sets held for it before).
- Description images (optional stage, the owner 2026-11-07): `scripts/description_images.py` reads a product's
  description images with RapidOCR (PP-OCRv5 Korean) into a sidecar per product. Images from Naver's CDN and any
  public HTTPS host the seller links (AGENTS.md rule 3; never http, an IP, localhost or a name resolving to a private
  address); banners, the first SmartEditor header strip, GIFs and tiny images out; Naver first: a tiled body read
  from its tiles, from the seller's own sources only when a tile fails; an image another product of the store already read is reused; equal
  slices read once (dHash). One fresh worker process per product (no memory build-up; a crash, a kill or a timeout
  is that product's error, one retry, then an error sidecar), one run per shop (a lock), Ctrl+C clean. Image status
  read / failed (5xx, read again) / gone (4xx, for good) / refused (a seller's hotlink block). Cache one folder per
  product, `--prune-cache`. Switch `CategoryRules.description_images`: off by default, on for 50002788.
- Size / weight from the images (`description_measures.py`), in the transform: a core for every category (stated
  packed / set / product weight and size, axis-letter sizes) and a parts profile per Naver category id
  (`CATEGORY_PROFILES`; 50002788 `GOLF_SET`: clubs x median weight + the bag, the longest club / bag, the bag's
  sides); per field the larger of the guess and today's value wins (`compared`: the other one, brief). Never taken:
  a guess above its band (operator > profile > core) or over 3x today's value, a single value read below OCR
  row confidence 0.9; an image's value is confidence 2 at most; an unknown bag drops a set's guesses to 1
  (`container_unknown`). A box never weighs less than its contents. Notes `measures_from_images`,
  `description_images_missing` / `_stale` / `_failed` / `_partial`.
- The images' text for the translation step (`description_image_text.py`): run_transform writes clean Korean blocks
  (text / table; repeats, low confidence, fragments, photo labels, prices, contacts, shop terms, store info, legal,
  promos, cross-sell out; a degree sign read as 0 put back; review screenshots in the images kept as context, the
  instructions say to leave them out) with instructions and the category's
  glossary to `shops/<shop>/translation/<product id>/description_images.ko.txt|.ko.json`; a block's `key` is the
  same in every listing that carries it (`shared`: how many of the store's do), so a store's spec sheet stays and is
  translated once. One flag per prepared product, `product.description_images_text.state`: off | not_read | empty |
  to_translate | translated (an `en.json` with `source_sha256` = the text's sha256). The translation itself is a
  later step.
- `scripts/example_15_description_collect.py`: one golf full set collected end to end with its description images
  (OCR) and prepared, in its own folder; prints where each package field and the images' text came from.
- Prepared format `prepared/2` (the package fields' `how` / `quote` / `flags` / `compared`, the text flag). New
  requirements rapidocr + onnxruntime (check_setup, SETUP.md, K-17). Regression: OCR sidecars of the 50 fixture
  products.
- Docs: the OCR study's durable results moved into the code and docs before its notes were deleted: engines
  and options rejected and why, RapidOCR misreads not repaired, image selection numbers, the cache size, Naver CDN
  facts for description images; a one-photo gallery is the seller's (the page holds one, checked via /products/page).

## 0.8.0 (2026-11-07)

- Run of 40 more (2026-11-07), generic fixes: spec rows vs variants read a part count in an axis name ("아이언 선택
  (8개)") as that part's, not the set's (a true 총클럽개수 row was dropped on 7 sets); notes `specs_contradict`,
  `specs_loft_near_miss`, `specs_lists_unsold`; title words of whole multi-word values; the variant cap covers value
  pairs; few_pieces from 종 / 하프세트, not on "10+1pcs"; 원산지 with the parts' countries kept; SIMPLE one-value
  options as facts; add-on codes and 택N numbering out; colour-named axes of flex values as placeholders.
- Description: table rows as one line ("a | b | c") in `description.text` (shape change, ENDPOINTS); cross-sell
  pairs, the store's genuine-goods pitch, section labels, tracking pixels, dispatch / holiday banners out; run-level
  store banners repeated across one store's listings (`shared_images.py`, note `description_shared_images`).
- Docs: [scripts/SELLER_DATA.md](scripts/SELLER_DATA.md), the seller data patterns behind the collection and
  transform rules. Regression fixtures: 19 more products of the run (50 in all).
- Listing screen: ad cards are kept by default (the owner, 2026-11-06); `Screen(exclude_sponsored=True)` leaves
  them out. Rental, another category, already in the shop and deferred stay screened.
- /products/specs, /products/page: when the card is not on the search page for the product's name (and no query was
  given), a second search with the name's first 5 words (13425122164).
- /products/specs delivery.lead_time: new `today_off` ("오늘출발 휴무"); `today_cutoff` is no longer filled from
  thisDayDispatchBasisTime on such a day (6540695739, 13553116678, 10816781893, 13302492097, 10816904599).
  `arrival_date_text` also read from the 네이버 배송 / 내일배송 "11.11.(수) 도착" line (13369469193).
- Description cleanup from the pilot 20: KRW price promos, cross-sell lines, whole contact sentences (만큼 / -면
  continuation) and contact closings, the store name without a 구매대행 prefix, junk-only text (None, note
  `description_junk`). Banner images: 톡톡 / 하단_상페 / 하단고정배너 names, Hangul typed on a QWERTY keyboard, and, with the
  description HTML, link banners (TalkTalk, Band, blog, Instagram, YouTube, Kakao, store pages) and spacer strips (new
  `clean_images(images, html)` argument, rules `link_banner`, `spacer`).
- transform: spec rows vs variants add the driver loft (드라이버 로프트각 vs 9도 / 9.5 SR values: dropped or bound like the
  shaft material), the description sentence "플렉스 R 모델의 아이언에는 카본 샤프트" as a material binding, and title/row number words
  with units (11.5 = 11.5도, 유틸4 / 4U = 4번 of a 유틸리티 axis, 5W) and the bag (+골프백 vs "캐디백 미포함" values). Pilot
  2026-11-06: 10816781893, 10816904599, 11635855564, 13369469193, 13413924099, 13553116678, 7166885441.
- Transform: per-variant `today_dispatch`; value tags ("[당일출고]") and "(선택)" on option names left out; the cap
  shared out in turn over the first axis; notes `few_pieces` from 총클럽개수, `gift_hidden`.
- Regression fixtures: 12 more saved pages from the pilot (31 in all).

## 0.7.0 (2026-11-06)

- **Transform** (`scripts/transform.py`, `transform_shops.py`, `run_transform.py`, `keep_run.py`): kept collection
  runs per shop -> prepared products (Korean, ready / held with codes, a translation worklist with content-hash text
  ids). Prices, options, SKU, leaves, spec rows, text fields, free add-ons, reviews. Checked on 23 collected sets:
  on 10 the naver-harvester published, SKUs and prices equal on 201 of 201 variants; a review-discount axis it
  published is dropped; 2 sets over 100 combinations held.
- **40-product run** (2026-11-05, research): fixes from checking every product against its saved page:
  `/products/specs` `delivery` (the fee as the page charges it, overseas, customs; a backend said free for a set
  shipped from Japan at 99,000 KRW per unit); `description.images` for SmartEditor ONE bodies (27 of 40 had none);
  "package weight" read as packed; page reads by the product's name first (the listing's search missed the card
  on 27 of 40, reading each page twice); image CDN pace 1 s; a folded 상품정보 list is a partial collection and
  held (`specs_folded`); delivery-message rows, 인증정보 rows and "(구매대행)" in 원산지 left out; log lines
  `api:` per failed answer and `ext-product:` per page read (R-STYLE-4).
- **Delivery, how fast and from where**: `/products/specs` `delivery.scope` (international / domestic) and
  `delivery.lead_time` (the store's average days from the page answer; today cutoff, average arrival days and
  probability, ship date from the purchase box); carried into the prepared product.
- **`/products/page`** (development and analysis): the product page as the owner's Chrome rendered it and its own
  answer, read like `/products/specs`, never cached; `scripts/product_page.py` saves it.
- **Captcha wait and watch**: `NAVER_CAPTCHA_WAIT_S` (default 600 s, was 60); the question text is read and logged,
  the page saved, the cursor put in the answer field (for an answer from a phone through remote desktop); a new
  captcha after a wrong answer is reported again. `GET /captcha` shows the state; `scripts/captcha_watch.py`, a
  separate process, reports each captcha / solved / timed out, so collection only waits. Still answered by the
  human only.
- **40 fresh pages checked** (2026-11-06, `/products/page`): `delivery.extra_fee_text` (the seller's regional fee
  text, "제주 도서산간 10,000"); `description.images` from every image of the body (SmartEditor ONE inline images,
  editor-NONE bodies; map images left out). Transform: paid variants and paid add-ons per category (`paid_variants`,
  `paid_addons`, off by default, both on for 50002788 sets: their photos show the extras), the variant choice made
  from the page's options; notes `paid_variants_left_out`,
  `title_names_one_variant`, `purchase_agency`; placeholder labels on facts and "옵션+..." names; gender words of
  option values add leaves; required add-on groups; 원산지 without a bracketed importer; single spaces in options.
- **Re-run on the same 40** (2026-11-06): the purchase box's new wording ("14:00 까지 결제 시 오늘 바로 발송",
  "11.11.(수) 도착 확률 98%") -> `lead_time.today_cutoff`, new `lead_time.arrival_date_text`; the cutoff also from
  the answer's `thisDayDispatchBasisTime`. Transform: title words that fit part of the values, new notes
  `specs_name_one_variant`, `option_values_duplicate`, `few_pieces`, `description_mentions_gifts`; the seller's
  numbering out of option values and add-ons; 원산지 with brackets inside brackets; the return fee typed as the
  regional fee text dropped (only when the notice states that same return fee); jump-link lines out of the description.
- Weight and size from the seller's text read more of what is written (`naver_shopping/measures.py`): more units (파운드,
  온스, 키로, kgs, 센치, 피트), decimal comma, packed / net words (포장 무게, 택배 무게, 박스 포함, 본품 무게) also after the number,
  tolerances and the same weight in two units, lb + oz, per piece and multipliers, every size triple with its own
  kind, two-side sizes, axes after the unit or in the label, "(단위: cm)", a weight inside a size row, td club tables.
  Sets are recognised from counts (6아이언, 12pcs, 3종); in a set the parts (club codes, bag, reference club "7번 기준", club
  headings) are components and a plain 중량 row is the set's weight. Weight candidates gain `count` and `flags`; new
  review reasons `value_list`, `other_part`, `decimal_comma`, `ambiguous_unit`; loads and capacities and unit-less
  ranges are no longer read. `package_measures`: stated set weights per variant (6630856593), 2% agreement,
  `below_stated_product` flag on a default package weight, optional operator `plausible` band. On the 40 golf sets:
  product weight now stated for 6630856593 (11.5 / 4.7 kg by club count) and 10639350746 (14 lb); 3 more products gain
  correctly tagged club-part candidates; the other 35 are unchanged.
- Description text and images no longer carry SmartEditor cards that are not the product: link cards (other products
  of the store, TalkTalk), the store map and address, and shopping cards' posters. In-page jump links ("▲ 이동(상단)") and
  bare hashtag lines are dropped. **Shape change:** `description.text` now has one empty line between SmartEditor
  components.
- Transform: new `description_clean.py` strips the seller's boilerplate from `description_ko` and `description_images`
  (return / delivery / customs notices, contact and phone lines, greetings and signatures, duties, lead time, promo
  and store claims, the monitor disclaimer, gift blocks when promotions are hidden, banner images by name), with notes
  for a 모음전 page and for banners inside snap tiles.
- Transform: spec rows are checked against the sold variants by fact (shaft material class, club count of stated
  totals and part lists, the composition rows as one set, model year). A row true of no variant, or one every variant
  already states, is dropped with a note. A row true of some variants only is kept with `for_ko`, the option values it
  fits. New notes: `specs_fit_no_variant`, `specs_stated_by_variants`, `specs_bound_to_variants`,
  `specs_composition_undecided`. The `title_names_one_variant` note is less noisy: the title's own span ("XR26"), no
  gender word without a rival, no 백포함 vs 백세트포함, and title counts that name a part list ("(클럽10개)").
- Package fields carry `confidence` 1-3 (3 stated with its kind, 2 stated with the kind open or the binding
  worked out, 1 the category default): 6630856593's 11.5 / 4.7 kg is used at 2.
- Transform: more variants than the shop's cap are no longer held: the first ones are offered (in stock and cheaper
  first, one per option value first so every value stays on sale), note `variants_capped` (an XXIO 14 set: 486 ->
  100).
- Regression fixtures from saved pages (DEVELOPMENT_RULES R-TEST-5): `server/naver_shopping/fixtures/pages/` (cut by
  `page_fixtures.py`, replayed by `test_pages.py` through the new pure `ext_product.specs_from_page`),
  `scripts/fixtures/collected/` and `scripts/fixtures/prepared/` (`collected_fixtures.py`, `test_prepared_golden.py`);
  `UPDATE_GOLDEN=1` rewrites them after a deliberate change.
- **Product page click** (`ext_product._card`): the card's photo is clicked, not the card's middle band, where the
  store name link lies (it opened the store, then Naver's login page; seen twice on thegolf cards, 2026-11-05).

## 0.6.0 (2026-11-05)

- **Listing screen** (`scripts/listing_filter.py`): every listing row left out gets a reason: `sponsored`,
  `title_unavailable`, `rental` (the naver-harvester's stop words as they are, `listing_exclusions.json`),
  `category_mismatch` (exact leaf only), `key_unavailable`, `already_published`, `deferred`. Listing rows add
  `store.channel_no`.
- **Already in the shop** (`scripts/shopify_catalog.py`): the store's Admin API catalog, read only, any status, by
  the source key metafields `source_offer_id` / `naver_offer_key` (never by name); the shop is checked before each
  read; a bad or duplicated key stops the check; snapshot at most 5 minutes. Store values in `shop_stores.Shopify`
  (fairwardgolf given; the others wait for the operator). No stored token: a 24 h token is minted per run from the
  store app's client id + secret (a 0600, git-ignored file whose path is in `.env`), checked for the shop and
  `read_products`, renewed before it ends and once after a 401; queries only; never printed.
- **Deferred products** (`scripts/deferred_log.py`, `scripts/collect_guard.py`): partial -> one retry -> deferred
  with the first error; the owner allows one retry of one product (`deferred_log.py allow`); a wall stops the run
  without marking; two products in a row partial for the same reason stop the run.
- **Video posters as photos**: `/products/reviews/selected` counts a video's poster as a photo (tiers and caps);
  `naver_images` saves it as a review photo (`from_video`), `posters_as_photos` stores the video as its poster.
- **Weight and size candidates**: `/products/specs` `measures` (`naver_shopping/measures.py`): the seller's values
  from the rows, the notice, the description, JSON-LD and description tables, with quote, place, kind, scope,
  variant binding; pointers and doubtful lines kept apart. `scripts/package_measures.py`: five shipping fields per
  variant, the operator's category averages (`category_measures.json`) where the seller gives none; no row -> the run
  stops and asks. 50002788 풀세트 is filled (owner, 2026-11-05): the median of the harvester's estimates on the 55
  fairwardgolf sets in Shopify, `reliability: estimated_average` (the weakest level; delivery will add a coefficient).
- `example_99` runs all of it; it needs the shop's credentials file (`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`) and the
  category's averages. A wall (503, 502 "blocked the request") or a busy adapter (409) stops the run without
  marking a product. Verified live 2026-11-05: 2 sets collected; 25 published products found in a listing, all with
  the same source key as in Shopify.
- Stop words: `scripts/listing_exclusions.json` is now the harvester's file byte for byte.

## 0.5.0 (2026-11-02)

- **Options from the product page** (Naver change, 2026-11-02): the store backend's `validation-products` answers
  419 to the box (the page now sends a one-time token with its product call), so `/products/details` has null
  `option_groups` / `variants` / `supplements`, and a slug-less link answers 404. `/products/specs` now returns
  `options` from the product answer the page itself fetched, copied by the adapter (filter `/channels/` +
  `/products/`; the token is never copied, R-EXT-1): every variant with `extra_price`, `stock_quantity` and the new
  `is_available` (false = sold out, (품절); kept), text options (CUSTOM), simple options, add-ons. Decision log
  R-EXT-2 / R-NAVER-2. Adapter 0.4.4: reload it in `chrome://extensions`.
- **Variant choice** (`scripts/naver_variants.py`): free variants only by default; paid ones (more or less than
  the product's price) when the operator passes `paid`; a name stating another amount "(+N원)" counts as paid and
  is reported; a bare "+" joining a set's parts is not money. `example_14_product_options.py` on real golf sets;
  `example_99` writes `variants` (argument `paid`).
- **Text fields** (a name on a tag, an engraving): `options.text_options[]` adds what the product page shows of
  each field: `label` ("네임스티커 성함 (필수)"), `required`, `placeholder`, `hint`, `min_length`, `max_length`,
  `pattern` (`pdp.text_fields`, the attributes the naver-harvester reads). Null when the page has no such field.
- **Types**: `Variant.is_available`, `PageOptions`, `SimpleOption`, `TextOption`, `ProductSpecs.options`.

## 0.4.0 (2026-11-01)

- **`/products/specs` (beta)**: a product page's 상품정보 rows (label -> value: 제조사, 브랜드, 원산지 and the seller's
  attributes such as 종류, 성별, 총클럽개수), read in the owner's Chrome through the adapter (search -> card click ->
  unfold), parsed in Python (`naver_shopping/pdp.py`). The adapter itself is unchanged. 409 while a listing job runs,
  503 for a wall / no extension (scripts do not retry them). Decision log R-NAVER-1.
- **`/products/details`**: `facts` (brand, manufacturer, model, origin, each with its source); notice rows carry
  `is_see_description` ("상품상세참조"-style pointers); `description.text` is a text-node walk (lines per block,
  null for image-only descriptions instead of `"\u200b ..."`).
- **Types / scripts**: `ProductSpecs`, `ProductFacts`, `Fact`, `SpecRow`; `NoticeRow.is_see_description`;
  `NaverApiClient.product_specs()`; fixtures re-captured.
- **Examples**: `example_08_product_full.py` (one product, every field), `example_09_listing_then_specs.py` (a
  listing, then details the new way), `example_10_known_products_specs.py` (known links, matched by full name + id).
- **Reviews**: `writer.profile_image` is null for Naver's no-avatar placeholder (`profile-phinf.pstatic.net/404/`);
  `example_11_reviews_full.py` reads a product's reviews completely (all fields, order, media links) to JSONL.
- **Reviews, way 2**: `/products/reviews/selected` chooses up to `count` reviews worth showing (photo + 50+ letters +
  avatar first, then photo + text, then text; all with text for 20 or fewer), reading only the pages it needs;
  `/products/reviews` takes `media` (`all`, `photo_video`, `text`: the backend's `reviewContentClassTypes`).
  Researched against the product page's review window: same JSON, ~10x slower, so no adapter for reviews.
- **Product photos**: `scripts/naver_images.py` downloads the gallery `/products/details` links (the original files:
  the largest real size of every rendition, measured on 25 photos; fallback to `m10000_10000_no_rotate`, then
  `o1000`, recorded per file) and the chosen reviews' photos + avatars, with a plain HTTP GET (no page, no adapter:
  the gallery matched the page's 1:1). Only a store's WebP is written, the source stays in memory:
  `scripts/image_prep.py` (Pillow, one algorithm for every store: gallery short side down to 1500, Merchant Center's
  recommendation, long side <= 5000; reviews long side 1024; never enlarged; <= 1 MB by quality 85-80-75, then
  smaller sizes; sRGB, EXIF orientation, animation -> first frame, old EXIF/GPS/IPTC/ICC/XMP dropped, a new XMP with
the store as publisher, read back and checked).
  `scripts/shop_stores.py`: our Shopify stores as a `StoreId` enum + profiles (fairwardgolf, skinsli, kyobooks,
  banafish), picked by `SHOP_STORE` in `.env`. Names `<slug|store-id>-001-<sha16>.webp`,
  `<store>-review-image|avatar-<sha16>.webp`; optional reviewed English `ImageSeo` (slug, title, alt <= 125, brand).
  `example_13_product_images.py`; `example_12` and `example_99` save review photos / avatars too.
- **Review videos**: attachments with `reviewAttachmentType` "M" are `video` now (they came as `image`); the link
  is the poster frame. Paging checked on 6782 reviews (340 pages, all unique, newest first).
- **FULL example**: `example_99_full_details.py` (a category's products -> details + specs + selected reviews),
  `example_12_reviews_selected.py`; `/products/specs` treats a card click that opened the store as not found.
- **Docs**: "Product details: two ways" (`/products/details` vs `/products/specs`, the full-flow catch, the two ways
  in) in ENDPOINTS.md and scripts/README.md.

## 0.3.0 (2026-11-01)

- **Setup for a new machine / agent**: `SETUP.md` (step by step, the agent does it itself and asks the operator only
  for what needs them: loading the adapter into their Chrome, secrets); `.env.example` (every per-machine value:
  what, where to get it, an example) and a dependency-free `.env` loader in the server and the scripts client
  (the shell wins).
- **Checklist**: `scripts/check_setup.py` (Python, packages, Chrome, `.env`, server, version, adapter, bridge port;
  `--live` one Naver call per transport, `--notify` a webhook test) -> READY / NOT READY.
- **Rules**: R-SETUP (a new requirement adds its check, `.env.example` line and SETUP step; secrets only in `.env`).

## 0.2.0 (2026-11-01)

- **Rules**: R-TYPE in `server/docs/DEVELOPMENT_RULES.md` (requests typed by marshmallow schemas, answers by
  TypedDicts + strict fixtures, nullable fields guarded, typed client methods, mypy for scripts); scripts conventions.
- **Scripts on typed methods**: `harvest_listing.py` and `example_search_harvest.py` use `api.search()` /
  `product_details()` / `catalog_reviews()`; every script passes `mypy`.
- **Types**: `scripts/naver_types.py` names every API answer (TypedDicts, written from real captured answers and the
  parser code); `test_naver_types.py` checks the captures strictly; typed client methods (`search`,
  `product_details`, `reviews`, `listing`, ...); examples use them and pass `mypy`.

## 0.1.0 (2026-11-01)

First release of this fork (based on
[omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper)).

- **Structure**: the API server lives in `server/` (import root), HTTP-only consumers in `scripts/`, docs in
  `server/docs/` with a binding rulebook (`DEVELOPMENT_RULES.md`); root `README.md` / `AGENTS.md` index everything.
  Docker moved to `archive/docker/`; macOS is the supported platform.
- **Fix**: the search category filter works at any category depth (`categoryIds` = depth + id; was a fixed `03`).
- **Listing (beta)**: `POST /listings` reads the whole search.shopping listing for a query through the owner's own
  Chrome with the adapter extension (`extension/` 0.4.2, `server/docs/EXTENSION.md`); `GET /listings/<id>` and
  `/listings/<id>/products` report and page the rows. Captchas are notified and waited for, bans stop the job.
- **Scripts**: `NaverApiClient` (`get`, `pages`, `listing`, `health`), runnable examples `example_01..07`,
  `harvest_listing.py` (widget listing past 96 cards by price slices), `smoke_endpoints.py`.
- **Tests**: 129 server + 42 scripts offline tests.
