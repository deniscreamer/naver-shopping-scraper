---
name: price
description: The price rule per shop (shop_pricing.py: delivery, duty and margin inside the price), the delivery tariff (delivery_tariff.py, delivery_tariffs.json, ShopNShip captures) and repricing products already in the store (reprice.py). Use when a price looks wrong, the coefficients, duty, margin or tariff change, a new tariff is captured, or the owner asks to reprice products.
---

# The price

The stage: `shop_pricing.py` builds each variant's price (base, delivery in Korea, the box's delivery by tariff,
duty, margin, the coefficients by confidence); `reprice.py` for products already in the store. The doc:
`scripts/PRICE.md`.

| Task | `scripts/PRICE.md` section |
|---|---|
| Why is this product priced X | "Why is this product priced X (how to use)" |
| The rule: base, delivery, duty, margin, the coefficients | "The price: delivery, duty and margin inside it" |
| The tariff as data, its version and history, each traced to a dated capture | "The tariff" |
| In the flow, and products already in the store (`reprice.py`) | "In the flow, and products already in the store" |
| What the owner has not decided yet | "Open, not decided by the owner" |
| The box (the package fields) behind a price | skill `transform`, `scripts/PACKAGE.md` "How to use" |
| Repricing on the owner's word | skill `store-actions` |

Commands (repo root):
- `.venv/bin/python scripts/reprice.py <shop> [--only KEY]` (a dry-run table, offline)
- `.venv/bin/python -m pytest scripts/test_shop_pricing.py scripts/test_delivery_tariff.py -q`
- `.venv/bin/python scripts/shopnship_rates.py quote|capture|compare ...` (networked, by hand only)

Rules:
- Coefficients, duty and margin are the owner's values, dated; never invent one.
- `reprice.py --apply` and any resend: `scripts/OWNER_RULES.md` rule 1 (a new rule or tariff resends every product at the next
  publication); the repricing procedure: skill `store-actions`.
- ShopNShip's calculator is never in the price path.
- `UPDATE_GOLDEN=1` on the pricing fixtures only after a deliberate change: read the diff.

More: publication skill `publish`; package fields skill `transform`; a new category skill `new-category-or-shop`.
