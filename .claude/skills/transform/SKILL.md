---
name: transform
description: The transform from collected lines to prepared products per shop (transform.py, run_transform.py), the five package fields (weight and size, category defaults, the description images' OCR) and the record types (shop_types.py). Use when a product is held, a package field or confidence looks wrong, prepare is slow or the prepare cache disagrees, a golden fixture changes, or the transform rules or record shapes change.
---

# Transform, package weight and size

Read `scripts/TRANSFORM.md` first; this skill is only the map.

What the doc covers:
- package weight and size: the seller's values, category averages and baselines, the OCR stage
  (`description_images.py`, `description_measures.py`), "More of the page", known limits;
- the transform: prepared product format, held codes, prices in KRW / USD, variants, reviews cleaning, the prepare cache;
- the record types (`shop_types.py`, TypedDicts of what the pipeline writes).

Commands (repo root, offline unless noted):
- `.venv/bin/python scripts/keep_run.py scripts/output/<run>` then `.venv/bin/python scripts/run_transform.py <shop>`
- `.venv/bin/python scripts/run_transform.py <shop> --verify` (cache vs afresh), `--full` (all afresh)
- `.venv/bin/python scripts/description_images.py <shop>` (networked OCR stage)
- `UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py` after a deliberate change: read the diff.

Rules:
- Category defaults and baselines are the owner's values, dated; never invent one (`CategoryDefaultsMissing` stops).
- A change that alters published products: ask the owner before republishing them (default: future products only).
- Add fixtures and tests from checked products; a behaviour change updates TRANSFORM.md in the same commit.

More: what sellers write `scripts/SELLER_DATA.md`; sections skill `placement`; the price skill `price`; a new
category skill `new-category-or-shop`.
