---
name: transform
description: The transform from collected lines to prepared products per shop (transform.py, run_transform.py), the five package fields (weight and size, category defaults, the description images' OCR) and the record types (shop_types.py). Use when a product is held, a package field or confidence looks wrong, prepare is slow or the prepare cache disagrees, a golden fixture changes, or the transform rules or record shapes change.
---

# Transform, package weight and size

The stage: `run_transform.py` turns a shop's collected lines into prepared products (prices, variants, texts,
brand, the five package fields), offline. Two docs; read the one section the task needs, not the whole doc. Both
open with "How to use".

| Task | Section |
|---|---|
| Run the transform, read its output and exit codes | `scripts/TRANSFORM.md` "How to use" |
| A product is held / not placed / not taken: what the code means, what to do | `scripts/TRANSFORM.md` "Held codes" |
| The prepare cache: slow, or `--verify` says `differs` | `scripts/TRANSFORM.md` "The prepare cache" |
| What a rule or code change changed, which of those are in the store (`--diff`, `prepared_diff.py`) | `scripts/TRANSFORM.md` "What a rule change changed" |
| The prepared record's fields | `scripts/TRANSFORM.md` "Prepared product", "Record types" |
| A price in KRW / USD, variants, options, SKU, delivery, a note in `notes` | `scripts/TRANSFORM.md` "Prices, variants and options" |
| Reviews cleaned wrong | `scripts/TRANSFORM.md` "Reviews" |
| A spec row bound to the wrong variant, `specs_*` notes, `title_names_one_variant` | `scripts/TRANSFORM.md` "Spec rows and the title vs variants" |
| The description's boilerplate cut, store banners | `scripts/TRANSFORM.md` "Description" |
| A brand / vendor wrong or empty | `scripts/TRANSFORM.md` "A brand for every product" |
| `paid_variants`, `paid_addons`, `description_images`, `sets_only`, `ShopRulesMissing` | `scripts/TRANSFORM.md` "Per-shop rules" |
| A package field or its `confidence` looks wrong: what `source`, flags and notes mean | `scripts/PACKAGE.md` "How to use" |
| A category default, `kinds`, baselines, `CategoryDefaultsMissing` | `scripts/PACKAGE.md` "The five fields", "Category defaults" |
| Which source wins (stated, composed, default) | `scripts/PACKAGE.md` "The order of sources", "Confidence" |
| Run the OCR stage, its files, exits, re-reads | `scripts/PACKAGE.md` "The description images stage" |
| The images misread: clubs' tables, count, bag | `scripts/PACKAGE.md` "Reading the description: the guess", "The clubs", "More of the page", "Whether the variant has the container" |
| A value refused as absurd, a known wrong case | `scripts/PACKAGE.md` "Absurd values", "Known limits" |
| The images' Korean text for `describe.py` (`description_images_text.state`) | `scripts/PACKAGE.md` "The images' text, read by `describe.py`" |
| A seller's pattern -> a rule, a fixture, a test | skill `seller-pattern-rule` |

Commands (repo root, offline unless noted):
- `.venv/bin/python scripts/keep_run.py scripts/output/<run>` then `.venv/bin/python scripts/run_transform.py <shop>`
- `.venv/bin/python scripts/run_transform.py <shop> --verify` (cache vs afresh), `--full` (all afresh), `--diff`
  (then what changed, product by product), `--shops-root <copy>` (a clone of the shop: `cp -cR`)
- `.venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl [--fields ...] [--published-only] [--keys-out F]`
- `.venv/bin/python scripts/description_images.py <shop>` (networked OCR stage)
- `UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py` after a deliberate change: read the diff.

Rules:
- Category defaults and baselines are the owner's values, dated; never invent one (`CategoryDefaultsMissing` stops).
- A change that alters published products: `run_transform.py <shop> --diff` (or `prepared_diff.py
  --published-only`) for which ones and how, `store_diff.py <shop> --keys-file F` for what the store would get,
  then `scripts/OWNER_RULES.md` rule 1.
- Add fixtures and tests from checked products (no need to ask: R-TEST-5); a behaviour change updates TRANSFORM.md
  or PACKAGE.md in the same commit.
- A new held code (transform), placement status or dedupe decision gets its row in TRANSFORM.md "Held codes" in the
  same commit: `scripts/test_docs_held_codes.py` fails otherwise.

More: what sellers write `scripts/SELLER_DATA.md`; sections skill `placement`; the price skill `price`; a new
category skill `new-category-or-shop`.
