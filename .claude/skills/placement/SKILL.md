---
name: placement
description: Placement of prepared products into the shop's sections (placement.py, placement_rules.py, attributes.py), the last stage before Shopify. Use when a product lands in the wrong section, placement reports unresolved or no_profile, a new shop or Naver category needs sections, or one Naver category must feed several shop sections (gender or another split).
---

# Placement

The stage: `placement.py` puts each prepared product into the shop's sections, the last stage before Shopify. The
doc: `scripts/PLACEMENT.md`.

| Task | `scripts/PLACEMENT.md` section |
|---|---|
| Run it, read `report.txt` | "How to run" |
| The idea: neutral attributes the seller states, a shop profile (data) that maps them to sections | "The idea" |
| Which change for which case | "What to change, by case" |
| A category with one section | "1. A category with one section" |
| One category, several sections (gender or another split) for another category or shop | "2. A category split by gender", "4. A split by a new kind of mark" |
| A new shop (tenant) | "3. Another shop (tenant)" |
| `unresolved` and conflicts, held rather than guessed | "5. What an unresolved product does" |
| Tests for a new rule | "Tests to add" |
| A wrong section on one product | skill `fix-a-product` |

Commands (repo root, offline):
- `.venv/bin/python scripts/placement.py <shop>`, then read `scripts/output/shops/<shop>/placement/report.txt`
- `.venv/bin/python -m pytest scripts/test_placement.py -q`

Rules:
- The sections and what to do with an unresolved value are the owner's decision; ask, never invent.
- A rule change moving published products: `store_diff.py <shop>`, then `scripts/OWNER_RULES.md` rule 1.
- New attributes are data (`Attribute`), with tests from real fixtures (skill `seller-pattern-rule`).

More: the transform skill `transform`; publication skill `publish`; a new category or shop skill
`new-category-or-shop`; checking sections by eye skill `visual-review`.
