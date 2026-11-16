---
name: price
description: The price rule per shop (shop_pricing.py: delivery, duty and margin inside the price), the delivery tariff (delivery_tariff.py, delivery_tariffs.json, ShopNShip captures) and repricing products already in the store (reprice.py). Use when a price looks wrong, the coefficients, duty, margin or tariff change, a new tariff is captured, or the owner asks to reprice products.
---

# The price

Read `scripts/PRICE.md` first; this skill is only the map.

What the doc covers:
- the rule: base, delivery in Korea, the box's delivery by tariff, duty, margin, the coefficients by confidence;
- the tariff as data, its version and history, each traced to a dated capture;
- in the flow and for products already in the store (`reprice.py`).

Commands (repo root):
- `.venv/bin/python scripts/reprice.py <shop> [--only KEY]` (a dry-run table, offline)
- `.venv/bin/python -m pytest scripts/test_shop_pricing.py scripts/test_delivery_tariff.py -q`
- `.venv/bin/python scripts/shopnship_rates.py quote|capture|compare ...` (networked, by hand only)

Rules:
- Coefficients, duty and margin are the owner's values, dated; never invent one.
- `reprice.py --apply` only on the owner's word; a new rule or tariff resends every product at the next publication.
- ShopNShip's calculator is never in the price path.
- `UPDATE_GOLDEN=1` on the pricing fixtures only after a deliberate change: read the diff.

More: publication skill `publish`; package fields skill `transform`; a new category skill `new-category-or-shop`.
