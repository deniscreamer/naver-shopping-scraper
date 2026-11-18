# The price

The price rule per shop (delivery, duty and margin inside the price), the delivery tariff and repricing products already in the store; split from scripts/README.md on 2026-11-16 (history: `git log --follow scripts/README.md`).

## Why is this product priced X (how to use)

A shop whose buyers pay no delivery carries everything in the variant's price: today fairwardgolf
(`shop_pricing.POLICIES`). A shop not there keeps `krw-cost/1`: cost = price = the Naver KRW at 1 000 KRW = 1 USD,
up to a whole dollar. The rule is `landed/2` (`shop_pricing.VERSION_DELIVERED`, raised on a change of its
arithmetic). Per variant, `Policy.quote(variant, product)` gives the cost per item, the price and the breakdown, in
USD:

```
purchase  = (the variant's Naver price + the seller's delivery in Korea) / 1000, up to a whole dollar
            the delivery in Korea: the listing's base fee when its fee type is PAID or UNIT_QUANTITY_PAID, else 0
cost      = purchase + 3 (ShopNShip's commission)            -> Shopify's cost per item
duty      = 12.5 % of the purchase, up to a cent             US import duty, always prepaid (PDD): in the price,
                                                             not in the cost per item
grid      = the tariff's price for the variant's box         (delivery_tariff.py, see The tariff)
inside    = 32.36 when the box is billed over 25 kg (the tariff holds the dimension fee there), else 0
level     = the lowest confidence of the box's three sides   (the package fields, 5 ... 1)
delivery  = (grid - inside) x coefficient(level) + inside
fee       = FedEx's dimension fee, KRW 35,600 = 35.60, when the box crosses its lines and inside is 0
base      = cost + duty + delivery + fee
margin    = 25 + 11 % of the base, never under 30
keep      = base + margin                                    what stays with the shop
price     = the first pretty number not under keep / 0.97: ending in 9 under 1000, in 99 from 1000
surplus   = price - 3 % of it - keep                         a reserve, kept by the shop
```

**Where each input comes from:**

| Input | From |
|---|---|
| Naver price | the variant's `price_krw` in `shops/<shop>/prepared/products.jsonl` (the transform), as Naver showed it at collection, the discount included |
| Delivery in Korea | the product's `delivery` there: `base_fee` when `fee_type` is PAID or UNIT_QUANTITY_PAID, else 0 |
| The box and its level | the variant's `package` fields (sides in mm, packed weight in g, each with its `confidence`): the transform, [PACKAGE.md](PACKAGE.md) "The five fields" |
| Commission, duty rate, coefficients, margin, payment share | `shop_pricing.FAIRWARDGOLF` (the owner's numbers, dated in its `decided`) |
| Grid, inside, fee | `delivery_tariffs.json` through `delivery_tariff.box_cost` (The tariff, below) |

**Commands** (nothing sent, no state file changes, no credentials read; the dry run writes its payload to
`publish/payloads/<id>.json`, `reprice.py` its table to `publish/reprice-<UTC stamp>.tsv`):

```sh
grep '<product id>' scripts/output/shops/<shop>/publish/published.jsonl | tail -1   # what the store has
.venv/bin/python scripts/reprice.py <shop> --only <key>                             # what the rule gives now
.venv/bin/python scripts/publish.py <shop> --only <key> --dry-run                    # every number, per variant
```

- The ledger row: `prices_usd` [lowest, highest] and `pricing` (the rule's version) of the last publication; a
  row from before 2026-11-11 has neither.
- `reprice.py --only` (a product published and still ready): `<key>  <handle>  level <levels> x<coefficients>
  <old> -> <new>  <change>`, or `held: <why>  (stays at <old>)`; the old prices marked "(plain rule)" when the
  ledger has none.
- `publish.py --dry-run --only` (a product ready, translated, placed and not withdrawn) writes
  `shops/<shop>/publish/payloads/<product id>.json`: each variant's metafield `fairwardgolf.price` holds every line
  of the formula above (`naverKrw`, `koreaDeliveryKrw`, `box`, `level`, `coefficient`, `gridUsd`, `insideUsd`,
  `deliveryUsd`, `fees`, `baseUsd`, `marginUsd`, `priceUsd`, `surplusUsd` ...; the fields: [PUBLISH.md](PUBLISH.md)
  "Metafields"). The published variant carries the same metafield in the store.

**What to do on each result:**

- **Held** (`no package box to price the delivery`, `a box side without a readable confidence`, `the package box:
  ...`): the variant's `package` fields are missing or unreadable; fix them at the transform. Nothing was sent.
- **Held, `over the tariff's last step: no price (needs a quote)`**: the box is billed over 50 kg; no price
  until the owner decides.
- **Level 1 (x2.50)**: the category's flat default box; a box from the seller's figures or the operator's answer
  about the bag lowers the price (skill `fix-a-product`).
- **The new price differs from the ledger's**: the rule, the tariff or the inputs changed since the publication;
  the `reprice.py` table goes to the owner, `--apply` only on the owner's word
  ([OWNER_RULES.md](OWNER_RULES.md) rule 1).
- **The price looks high**: read `fees` (the dimension fee), `insideUsd` and the coefficient in the breakdown, then
  "Accepted as they are" below.

## The price: delivery, duty and margin inside it (`shop_pricing.py`, the owner 2026-11-11)

The box is the variant's `package` fields (sides in mm, the packed weight in g): a category default's central
value, else the larger end of a range. The duty (the owner, 2026-11-11): every parcel leaves Korea through
ShopNShip with the duty prepaid, 12.5 % of the purchase whatever the country of manufacture; it goes into the base
the price is made from, as a line of its own, and never into Shopify's cost per item (the owner, 2026-11-11: it is
not a purchase price). Shopify's cost per item is the purchase and the commission: its profit report (price - cost)
is therefore not the margin, it holds the duty, the delivery, the fee, the payment share and the surplus too.

The margin (the owner, 2026-11-11): 25 USD for each order plus 11 % of the base, and never under 30. The fixed part
pays the work an order takes whatever it costs; the share grows with every dollar, as the risks do (a dearer set
loses more on a refund, the payment share included). It is 36 at a base of 100, 80 at 500, 135 at 1 000, 190 at
1 500, 355 at 3 000, 575 at 5 000 (36 % to 11.5 % of the base). The rule before it: History, below.

The delivery in Korea: a fee type other than PAID and UNIT_QUANTITY_PAID is free (CONDITIONAL_FREE too; the owner,
2026-11-11). A variant without a box, or with a box over the tariff's last step, has no price
(`PriceError`): the product is held, nothing is sent.

**The coefficients** (the owner, 2026-11-11: one a level, on the grid's price; the fee is not multiplied):

| Level | Coefficient | The box | What it covers (golf sets, 50002788) |
|---:|---:|---|---|
| 5 | 1.00 | stated by the seller | the tariff as it is |
| 4 | 1.10 | the seller's, a weaker reading (an image) | a box 1.5 cm wider and higher with a bag, 0.5 cm without |
| 3 | 1.20 | composed from the seller's own figures | 3.5 cm with a bag, 1.5 cm without |
| 2 | 1.40 | composed with the operator's baselines | 7 cm with a bag; 3.5 cm without, or up to 11.5 kg |
| 1 | 2.50 | the category's flat default | whether the set has a bag is unknown |

Level 1 is 2.50 so the margin stays whole when the set does have a bag: the category's average box (about 124 x 28
x 23 cm) is 232-259 USD by the grid, a set with a bag 523-546, and under 2.33 the difference would come out of the
margin; without a bag the price carries 444-511 USD the delivery does not need, kept for the risks. 2.50 was derived
for 50002788: a new category in the shop needs its own check of level 1 (the coefficients are one table per shop,
`shop_pricing.FAIRWARDGOLF`). 50002787 junior clubs (the owner, 2026-11-11), 50002670 women's iron sets
(2026-11-14), 50002783 wedge sets (2026-11-15) and 50002784 chippers (the owner, 2026-11-18: the shop's general rule,
no override; one chipper's box, $259 for a 35,000 KRW chipper) keep them as they are, to be measured
on its first shipments like the sets. All five are starting estimates: no set had shipped yet. After the first 10-20 sets
shipped, compare each invoice with the variant's `fairwardgolf.price` (the box FedEx measured, the billable kg,
every fee line) and replace them with measured ones; check the first invoice of a set without a bag for FedEx's
18 kg minimum (the switch below). Where they come from: 1-6 cm more on the two short sides raises the grid's price
by up to x1.12-1.60 without a bag and x1.06-1.34 with one; the one real check, the Callaway Edge box the seller
states (121 x 20 x 16 cm, 10.8 kg, 183.30 USD), is passed by 1.40 with a step to spare (1.35 by 0.46 USD).

**The fee, once per box.** FedEx's Additional Handling Surcharge - Dimension (its 2026 rates for Korea; the owner,
2026-11-10): KRW 35,600 on a box whose longest side is over 121 cm, or the second over 76 cm, or length + girth
over 266 cm, or the volume over 169,901 cm3 (strict lines: 121 cm pays nothing), at 1 000 KRW = 1 USD. FedEx bills
it once per box. The partner's table already holds it over 25 kg of billable weight: every step from 26 kg is 32.36
USD over the per-kilogram line (25 -> 26 kg: +48.77 against +16.41 a kilogram; the same for Japan, the UK, Germany
and Canada), KRW 35,600 at the partner's 1 100. So a box billed over 25 kg (every set with a bag) does not pay it
again, and the part inside is not multiplied by the coefficient (the owner, 2026-11-11). The tariff names it
`included_surcharge`. Sources: https://www.fedex.com/content/dam/fedex/international/rates/fedex-rates-sur-en-kr-2026.pdf
and https://www.fedex.com/en-kr/shipping/surcharges/other-surcharges.html (fedex.com refuses plain HTTP requests:
open them in a browser). Read there too (2026-11-11): FedEx measures the box itself and may bill afterwards; an
outside that is not a cardboard box (a bag case, handles, straps) pays the same KRW 35,600 at any length, so the
price assumes cardboard; only the largest handling fee is billed per box; the amount is before tax and before any
contract discount; the Oversize charge (KRW 86,000: over 243 cm, length + girth over 330 cm, or 283,168 cm3) is
not reached by a set.

**Not counted, on purpose** (the owner, 2026-11-11):
- fuel and insurance: inside ShopNShip's tariff;
- FedEx's 18 kg minimum billable weight for a box that pays the dimension fee: not seen on real invoices of long
  boxes. The switch is the fee's `min_billable_kg` in `delivery_tariffs.json`: null is off, 18 bills such a box at
  18 kg at least (a new tariff version). A set without a bag would cost 133-139 USD more to ship: switch it on
  when an invoice shows it;
- FedEx's demand surcharges, the residential and inbound fees, remote areas (the tariff's `not_included`);
- the fuel percent FedEx puts on the dimension fee (52.25 % in the week of 2026-11-09: KRW 35,600 would be about
  54,200);
- the market rate: 1 000 KRW = 1 USD is the owner's constant (the market was about 1 335 on 2026-11-10: the
  constant hides a reserve larger than the whole margin on the catalogue, uneven, 4-18 % of a price, and zero if
  the won reaches 1 000);
- the 10 % Korean VAT inside Naver's price (no export refund counted) and the seller's extra fee for Jeju and the
  islands (ShopNShip's warehouse is on the mainland);
- the duty by country: every parcel pays it since the US de minimis ended (2025-08-29), and the owner's flat 12.5 %
  of the purchase is used instead of the per-country rates a search found (about 24 % for China);
- US sales tax: the variants are sent not taxable; a sales-tax duty would come out of the price;
- a change of Naver's price: the price is taken as Naver shows it, the discount included; a sync is a later stage;
- a dearer payment: 3 % is the payment system's average share, the rest is paid from the margin.

**Accepted as they are** (the owner, 2026-11-11, after a review of the rule on the 120 products):
- Level 1 sits between the two outcomes: 400-600 USD over the same set without a bag at level 2, up to 200 under
  one with a bag. An operator's answer about the bag moves the price either way.
- The coefficient's reserve is part of the base, so it earns margin and the 3 % too.
- The seam at 1000: no price between 999 and 1099; a keep just over the line takes the next hundred.
- The surplus is a reserve only on average: 0.59 to 96.70 USD a product, under 10 on 15 of the 125.
- Prices well above US retail for sets of US brands, and the bag's box adds 500-700 USD: the source is Korea's
  market, with delivery and the shop's margin.
- A bag sold as a paid add-on would ride in a box priced without it (390-400 USD of delivery not in the price):
  paid add-ons stay off for this rule (the site sells free choices only) until a box is priced per add-on. A paid
  variant is priced by its own box; on the 120 products each listing has one price (7583123963's variants have two
  gross weights in the same step).
- Prices move when a product is sent again: each send prices it anew (a new collection, a better box, a new
  tariff or rule version); level 1 to level 2 without a bag is 400-600 USD less.
- The "1+1" listing 5684497984 (two sets, two boxes) is priced as one box; three level-2 sets whose "no bag" is
  read from an image only (5479607864, 13753313321, 13741767690) lose money if they do have one.

### The tariff (`delivery_tariff.py`, `delivery_tariffs.json`)

The partner's prices are data: `delivery_tariffs.json`, one tariff per partner, carrier, service and route,
approved by the owner and traced to a dated capture of the partner's calculator; no amount is made up or
extrapolated in code. Which shops carry delivery in the price is `shop_pricing.POLICIES` (a `Delivered` rule names
its tariff); the file's `shops` map is the calculator's lookup and must agree with it (a test): today
`fairwardgolf` -> `shopnship-fedex-ip-kr-us` (ShopNShip, FedEx International Priority, Korea -> US, captured
2026-11-11, file version 1). A box's price, checked against the captures:

1. volumetric weight = L x W x H / 5000 (cm; the sides as they are, a fraction of a centimetre kept);
2. billable weight = the larger of the gross and the volumetric weight, rounded to hundredths (half up);
3. the price is the row of the first step not under it: 0.5 kg steps to 20.5 kg, whole kilograms from 21 to 50 kg,
   71 steps (0.5 kg 42.49 USD, 8 kg 136.12, 16 kg 232.01, 16.5 kg 258.78, 31 kg 523.48, 50 kg 809.67);
4. over 50 kg the calculator gives no FedEx price: the answer is `needs_quote`, and the variant has no price.

```python
from delivery_tariff import Box, load, box_cost
tariff = load().for_shop("fairwardgolf")          # None: no tariff named for this shop
box_cost(tariff, Box(124, 20, 16, 6), krw_per_usd=1000)
# base_usd "136.12", surcharges [fedex_ahs_dimension "35.60"], included None, total_usd "171.72"
```

```sh
.venv/bin/python scripts/shopnship_rates.py quote 124 20 16 6                      # one box: every carrier
.venv/bin/python scripts/shopnship_rates.py capture --out scripts/output/shopnship  # the grid, about 5 min
.venv/bin/python scripts/shopnship_rates.py compare scripts/output/shopnship/shopnship-us-<time>.json
                                                    # against the recorded table: the differences, exit 1 if any
```

The review is by hand (the owner, 2026-11-11), with versions and the captures kept to compare. Capture and compare
at least when FedEx publishes its 2027 rates for Korea (the fee's amount and lines are of the 2026 document), a week
after a capture (FedEx's fuel moves on Mondays: does the grid?), and after an invoice that differs; a grid 6 %
dearer moves 41 of the 125 prices, 40 by 100 USD.

Adopting a capture that differs: copy it to `scripts/fixtures/shopnship/` (the earlier captures stay: they are the
backups a later capture is compared with); in `delivery_tariffs.json` put its `table`, `source` and `checked_at`,
raise `version` and add a `history` line (version, date, tariff, source, what changed); fix the expected prices in
`test_delivery_tariff.py` (they are written out on purpose) and rewrite the pricing fixtures with `UPDATE_GOLDEN=1`
after reading the diff; the owner approves. Every price records its tariff: `tariff` {id, checkedAt, version, sha256} in
the variant's `fairwardgolf.price` and in the product's `pricing`; the sha256 is the tariff row's fingerprint, so
any edit (a step, a fee, the 18 kg switch) moves it even without a new version, and with it the publish digest:
after a change, run `reprice.py` (dry) and ask the owner before anything is sent. A new tariff id also changes
`shop_pricing.FAIRWARDGOLF.tariff`.

Where the table comes from: ShopNShip's public calculator (https://shopnship.co.kr/en/help/shipping_calculator.php;
no login, cookie or key; one line of five USD prices: DHL / FedEx / EMS / EMS Premium / ShopNShip Standard).
`shopnship_rates.py capture` asks the grid one box at a time with a pause, keeps each request with its raw answer,
and stops after three rows in a row without an answer. On the page itself, for a check by hand: a blank or zero
side prices by the gross weight only, and a comma cuts the weight ("9,5" is 9 kg); use the `quote` command, which
sends neither. The captures and what they showed: History, below.

### In the flow, and products already in the store (`reprice.py`)

New products: `job.py new ... --publish [--describe]` prices each product in its payload. The done line shows the
price (`published <handle> $1099 <admin link>`, `$<min>-<max>` when the variants differ); the job's `published`
event and the ledger row keep `prices_usd` [min, max], the row also `pricing` (the rule's version). A product that
cannot be priced is not sent: `publish held: variant <sku>: <why>` in a job, `held` with the reason in `publish.py`.

Products already in the store (published before the rule, or before a new rule or tariff version):

```sh
.venv/bin/python scripts/reprice.py fairwardgolf [--only KEY] [--apply] [--shops-root DIR]   # --only: repeat for several
```

A dry run by default, nothing sent: one line per product published and still ready (key, handle, the levels and
coefficients, the old prices min-max, the new min-max, the change), then a summary; the old prices are the ledger's
`prices_usd`, else what the plain rule (krw-cost/1) gives from the prepared record, marked "plain rule"; a
published product no longer ready is named on stderr; the same table goes to
`<shops_root>/<shop>/publish/reprice-<UTC time>.tsv`. A product that cannot be priced is shown held and the run
goes on. `--apply` sends the products that are not held through `publish.publish_one` (a product whose digest did
not change is skipped). The rule "ask the owner before touching published products" ([OWNER_RULES.md](OWNER_RULES.md) rule 1) holds:
`--apply` runs on the owner's word, after the table was read. The runs done so far: History, below.

## Open, not decided by the owner (2026-11-11)

- The 17 sellers who bring the set into Korea from abroad (transform note `overseas_shipping`): for 10 of them
  Korean duty and VAT (about 19 %, not checked) are not in Naver's price, and the rule does not add them.
- Returns and refused parcels: who pays the way back of a 1.2 m box (about the outbound price), what happens to a
  set the Naver seller will not take back; the payment share is not refunded. No reserve in the price.
- Naver's price at order time: 66 of the 125 sell at a discount; if every discount ended, 32 orders would lose
  money. Check the price before the payment is captured? How often to re-read published prices?
- Boxes at the fee's 121 cm line: 22 of the 120 computed boxes are 120.5-121.0 cm (5 mm decides) and carry no
  fee; FedEx remeasures. Add the fee to every set, or pack sets without a bag at 121 cm or less?
- Does a set with a bag travel as one box or two (two boxes cost less, the rule prices one)?
- Buyers outside the US: the price carries the US tariff; other destinations were not discussed.
- The level taken from the box's three sides only (not the weights): the agent's choice, not confirmed.
- Cost per item without the delivery: the plan's choice, not confirmed (without the duty: the owner, 2026-11-11).

## History

**The margin before `landed/2`.** The owner's first table (points 100 -> 30 ... 1 500 -> 200, joined by lines,
13.3 % over 1 500: `landed/1`) gave 10 % at 800-1 000 and a fifth of each dollar between 1 000 and 1 500; it was
replaced the same day (2026-11-11) by 25 + 11 %.

**Examples** (2026-11-11, tariff version 1; USD):

| Product | Level | Box cm, billable kg | Purchase | Cost | Duty | Grid | Delivery | Fee | Base | Margin | Price | Surplus |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| the seller's box, Korea fee 99 000 KRW (5818229550) | 5 | 121 x 20 x 16, 10.80 | 898 | 901.00 | 112.25 | 183.30 | 183.30 | 0 | 1196.55 | 156.62 | 1399 | 3.86 |
| a set without a bag (13498941795) | 2 | 120.5 x 20 x 16, 7.71 | 689 | 692.00 | 86.13 | 136.12 | 190.57 | 0 | 968.70 | 131.56 | 1199 | 62.77 |
| a set without a bag (12434254421) | 2 | 124 x 20 x 16, 7.94 | 2900 | 2903.00 | 362.50 | 136.12 | 190.57 | 35.60 | 3491.67 | 409.08 | 4099 | 75.28 |
| a set with a bag (13513786835) | 2 | 120.5 x 40 x 32, 30.85 | 899 | 902.00 | 112.38 | 523.48 | 719.93 | inside | 1734.31 | 215.77 | 2099 | 85.95 |
| the bag unknown (9868413561) | 1 | 123 x 28 x 23, 15.84 | 360 | 363.00 | 45.00 | 232.01 | 580.03 | 35.60 | 1023.63 | 137.60 | 1199 | 1.80 |

On the 120 products of the store (2026-11-11): levels 5 / 4 / 2 / 1 on 2 / 1 / 97 / 20 products (none at level 3),
every product priced; with the 5 of the pilot, 939 to 5 099 USD.

**The tariff's captures** (2026-11-11). Two captures (178 and 198 requests, no error, every repeat equal); the
second, `fixtures/shopnship/shopnship-us-20261111T072303Z.json`, is the tariff's `source`. Its steps to 20 kg equal
the owner's table on all 40; the steps from 20.5 to 50 kg are captured too and used instead of a fresh quote.
`shopnship_explore.py` then asked 427 more boxes in two rounds (length 50-400 cm, the second side, girth and volume
around the fee's lines, the order of the sides, weights across the steps in small increments, flat, thin and tiny
boxes, number formats, pounds and inches, other countries): every answer the model can predict was equal to it
(367 of 367; one weight written with 17 digits, which the server reads as a binary number, left out). What they
showed: the calculator knows only the billable weight (no dimension fee up to 25 kg, and no size limit: a 400 x 10
x 10 cm box gets a price FedEx would refuse); over 25 kg every step holds the fee; one box over 23 kg costs more
than two of the same total (32 kg 539.89 USD, 16 + 16 kg 464.02). All the answers are of one hour of one day:
whether the prices move with the day is not known. ShopNShip Standard ("5-15 business days, duties included")
priced the two set boxes at 159.57 and 635.98 USD and nothing over 30 kg.

**Repricing runs.** Done for the 120 products published before the rule on 2026-11-11 under `landed/1` (120 sent,
the 5 of the pilot unchanged; the store then held the rule's price and cost on all 1 127 variants). The same day the
rule became `landed/2` (the margin 25 + 11 %, the duty out of the cost per item), and on the owner's word all 125
products were sent again: 33 prices changed (329 475 -> 326 915 USD for the lowest prices), every cost per item lost
the duty; the store then held `landed/2` on all 1 127 variants, 939 to 5 099 USD.
