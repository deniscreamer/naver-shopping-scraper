# Placement: one Naver category, several shop sections

How a shop's sections are chosen at the last stage before Shopify, and how to turn the same mechanism on for
another shop (tenant) or another category. The code: `attributes.py` (what the seller states), `placement_rules.py`
(each shop's profile, data), `placement.py` (the stage). Its place in the pipeline: [README.md](README.md)
"Placement".

## The idea

- **The transform states facts only.** It writes neutral `product.attributes` from the seller's own words, each
  with its value, the value of each variant, the evidence and flags (`attributes.py`). It never names a shop
  section.
- **Placement decides the shop's sections from the shop's profile.** It runs after the transform and the
  translation, right before publication. A profile can change at any time; running `placement.py` again applies
  it to the products already collected.
- **A product in several sections stays one Shopify product.** It carries the leaf tags of all its sections and
  is shown in each tag collection. When a section shows only part of the card, `start_variants` gives that
  collection a start variant.
- **Only a stated value places.** `unknown` and `conflict` are held (`unresolved`), or go to the profile's
  fallback section. A value is never guessed.

## What to change, by case

| Case | Code? | Files |
|---|---|---|
| A category of a configured shop with no split (one section), like 50002787 junior clubs | no | `placement_rules.py` (and `transform_shops.py` if the transform has no rules for it yet) |
| A category of a configured shop that sells one side of a split only, like 50002670 irons (2026-11-14: `split_by="gender"`, the one leaf `womens`; men's and unknown are held) | no | `placement_rules.py` |
| A category of a configured shop with one section and no split, like 50002783 wedges (2026-11-15: `leaves={None: WEDGES}`, every gender to wedge-sets; singles are left out by the title screen) | no | `placement_rules.py` |
| A category split by gender, like 50002788 | no | `placement_rules.py` |
| The same in another shop (tenant) | no | `shop_stores.py` (the shop), `transform_shops.py`, `placement_rules.py` |
| A split by a new kind of mark (function, size, material ...) | data only | `attributes.py` (a new `Attribute`), `placement_rules.py` |
| A split no word can state (needs a new evidence source) | yes | `attributes.decide` (a new source, its own tests) |

Every case adds tests (below) and a line in CHANGELOG.

## 1. A category with one section

Every Naver category a shop collects needs a placement, or its products come out `no_profile`.

```python
# placement_rules.py, in the shop's PlacementProfile.categories
"50002810": CategoryPlacement(parent="putting", leaves={None: Leaf("putting-mats", "Putting Mats")}),
```

The transform needs the category too (`transform_shops.py`: `"50002810": CategoryRules()`; without it the
transform stops with `ShopRulesMissing`).

## 2. A category split by gender (another category or shop)

The gender attribute already exists; a profile names it and maps its values:

```python
"50002796": CategoryPlacement(parent="apparel", split_by="gender",
                              leaves={"mens": Leaf("mens-fall-long-sleeve-tops", "Men’s Long Sleeve Tops"),
                                      "womens": Leaf("womens-fall-long-sleeve-tops", "Women’s Long Sleeve Tops")},
                              unresolved="hold"),
```

The values are `mens` / `womens`. `unisex` goes to both, because `GENDER.implies` says so, and `mixed` goes to
every section one of its variants fits. A title naming one gender beats a 남녀공용 (unisex) row: sellers fill the row
from a template (the owner's pilot, 2026-11-09: a "PGM 여성골프채풀세트" went to the men's section too). A category whose 상품정보 row is not named 성별 needs that label added to
`GENDER.rows`. A category whose sellers write other words needs those words added to `GENDER.words`. Both are data.

## 3. Another shop (tenant)

1. **Register the shop.** `shop_stores.py`: its `StoreId`, domain, Shopify namespace, credentials env name
   ([SETUP.md](../SETUP.md)).
2. **Add its transform rules.** `transform_shops.py`: a `ShopRules` (SKU prefix, KRW per USD, variant cap) with a
   `CategoryRules` for each Naver category (paid variants / add-ons, description images).
3. **Add its placement profile.** `placement_rules.py`: a `PlacementProfile` with a `CategoryPlacement` for each
   category, as in 1 and 2. Its `tags` patterns default to `{shop}:leaf:{leaf}`, `{shop}:parent:{parent}` and
   `{shop}:showcase`. Set them to the shop's own tag scheme if it differs.
4. **Run the stage.**

   ```sh
   .venv/bin/python scripts/run_transform.py <shop>
   .venv/bin/python scripts/placement.py <shop>
   ```

   Then read `shops/<shop>/placement/report.txt`: counts per status and section, and every `unresolved` product
   with its evidence.

## 4. A split by a new kind of mark

Write the mark as an `Attribute` in `attributes.py` and add it to `ATTRIBUTES`. Example: Naver 50002814 holds
laser rangefinders and GPS devices.

```python
DEVICE = Attribute(
    "device",
    words={"both": ("레이저+GPS", "레이저 GPS"), "laser": ("레이저",), "gps": ("GPS", "위성")},
    rows=("측정방식",),                        # a 상품정보 row that states it, if sellers fill one
    implies={"both": ("laser", "gps")},        # a value that means several sections
    opposite={},                               # values that exclude each other; empty: no conflict check by pairs
)
ATTRIBUTES = {a.name: a for a in (GENDER, DEVICE)}
```

Then a profile entry: `CategoryPlacement(parent="gps", split_by="device", leaves={"laser": ..., "gps": ...})`.

**The order of evidence is fixed for every attribute.** The variants' option values come first: a variant that
names a value is that value, and a set naming several values is `mixed`. Then the attribute's 상품정보 rows, then
the title. The listing query is only checked against the result (the flag `listing_disagrees`).

**How the words match.**
- Longest first: a matched span is not matched again, so 남녀공용 is not also read as 남녀.
- Latin words match as whole words only, so MEN is not found inside WOMEN.
- A word that also appears in unrelated text is a risk: put the precise forms first, and add a test for the text
  it must not match.

## 5. What an unresolved product does

- `unresolved="hold"` is the default. The product is not placed, and the report lists it with its evidence. The
  owner, or the agent with the owner's word, decides.
- `unresolved="<a section handle of leaves>"` places unknown and conflict products in that section instead. Use
  this only where a wrong section costs little, for example a general section.

## Tests to add

All tests are offline and fast, in `test_placement.py`.

- **Cases of the rules.** Call `attributes.decide` with words from real sellers:
  - one value from a row, one from the title, one from a variant;
  - a conflict;
  - unknown, for text with no mark, such as a flex or a model name;
  - text the words must not match.
- **The profile.** Call `placement.place` with a small prepared product for:
  - each value;
  - mixed, checking the start variants;
  - unresolved;
  - a category with no split.
- **Real products.** If the category has fixture products (`fixtures/collected/`, made with
  `collected_fixtures.py`), add a table of the sections each one goes to, as `EXPECTED` does for 50002788.

When `attributes.py` changes, the prepared golden files change too
(`UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py`): read the diff before committing
(R-TEST-5).

## Checked (2026-11-08, fairwardgolf 50002788)

- **Trial sets:** 143 sets placed with no unresolved ones, 73 men's and 72 women's section memberships.
- **Fixtures:** the 50 fixture sets go to the same sections as before, when the transform still decided leaves.
- **The one change:** 13425122164, a men's listing with a women's variant, now goes to both sections.
- **GVTOUR 8514409092:** 46 men's and 23 women's variants, each collection opening its own variant, as the
  harvester's live check found on 2026-09-26.

## Placement: the shop's sections, the last stage before Shopify (`placement.py`)

The owner (2026-11-08): a shop is split into its sections at the last stage before Shopify, from its own profile,
not while a job collects; one Naver category id can be several sections (50002788 풀세트: men's and women's sets),
and another shop may split other categories by other marks. So the transform only states what the seller says, as
neutral **attributes** with their evidence (`attributes.py`, data: a value's words, the 상품정보 rows that state it,
what a value implies), and placement maps them to the shop's sections by **profile** (`placement_rules.py`, data:
Naver category id -> parent, the attribute that splits it, value -> section (collection handle, product type, tags),
what an unresolved product does: `hold` or a fallback section). A new split is a new attribute and a profile entry.

One product, several collections: a product in two sections stays ONE Shopify product (card, variants, stock
shared, never a second copy) carrying the leaf tags of both (`tags`: fairwardgolf:leaf:mens-complete-sets and
...:womens-complete-sets), shown by both tag collections; `product_type` is the primary section's (the most
variants). A section showing only part of the card (a set with separate men's and women's variants) gets a
start-variant hint (`start_variants` {leaf: sku}, for publication's metafield of start variants per collection: from
the men's collection the men's variant opens), never a removal of the other variants. A stated unisex goes to both;
an unknown gender is not unisex and goes nowhere (held).

Gender (50002788, fairwardgolf): each sold variant's option values first ("여성용-그라파이트": that variant is
women's; a set with both is `mixed` and goes to both sections, each with its own start variant; when the seller marks only
one gender's variants beside a unisex row, the unmarked ones are the other), else the 성별 row, else the title
(여성 / 레이디스 / LADIES, 남성 / MEN'S, 남녀공용 -> both). A row and a title naming opposite genders, or every
variant the opposite of the row: `conflict`; nothing says it: `unknown`; both are held (`unresolved`) for the owner,
never guessed from a flex, a colour or a model. The job's listing query is evidence only (flag `listing_disagrees`).
Checked on the 143 trial sets and the 50 fixtures (2026-11-08): the same sections as the transform's leaves before
on all but one (13425122164: a men's listing with a women's variant: both sections, 2 and 1 variants). GVTOUR
8514409092: 46 men's and 23 women's variants, as the harvester's live check pinned them (2026-09-26).

```sh
.venv/bin/python scripts/placement.py fairwardgolf      # -> shops/<shop>/placement/placements.jsonl, report.txt
```

**The same case in another shop or category**, or a split by another mark: step by step in
[PLACEMENT.md](PLACEMENT.md) (which file for which case, the profile entry, a new attribute, the unresolved policy,
the tests to add). In short: the category's transform rules (`transform_shops.py`), its profile entry
(`placement_rules.py`: parent, `split_by`, value -> section, `unresolved`), and for a new mark an `Attribute` in
`attributes.py`; no code.

