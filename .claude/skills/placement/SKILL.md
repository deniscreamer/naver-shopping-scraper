---
name: placement
description: Placement of prepared products into the shop's sections (placement.py, placement_rules.py, attributes.py), the last stage before Shopify. Use when a product lands in the wrong section, placement reports unresolved or no_profile, a new shop or Naver category needs sections, or one Naver category must feed several shop sections (gender or another split).
---

# Placement

Read `scripts/PLACEMENT.md` first; this skill is only the map. Its last section, "Placement", is the stage's
reference.

What the doc covers:
- the idea: neutral attributes the seller states, a shop profile (data) that maps them to sections;
- `unresolved` and conflicts, held rather than guessed;
- turning a split on for another shop or category.

Commands (repo root, offline):
- `.venv/bin/python scripts/placement.py <shop>`, then read `shops/<shop>/placement/report.txt`
- `.venv/bin/python -m pytest scripts/test_placement.py -q`

Rules:
- The sections and what to do with an unresolved value are the owner's decision; ask, never invent.
- A rule change moving published products: check with `store_diff.py <shop>` and ask the owner before republishing.
- New attributes are data (`Attribute`), with tests from real fixtures.

More: the transform skill `transform`; publication skill `publish`; a new category or shop skill
`new-category-or-shop`; checking sections by eye skill `visual-review`.
