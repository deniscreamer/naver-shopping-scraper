---
name: fix-a-product
description: Correct one product's wrong brand / vendor, title, price, section or description at its source, then republish that product only on the owner's word. Use for "у товара не тот бренд / название / цена / раздел / описание", "fix product X", or a finding from a lens review that one product reads wrong.
---

# Fix one product

Rules: [scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md). First trace it (skill `product-trace`): the key,
the stage, the evidence. `S=scripts/output/shops/<shop>`. Hand edits wait for the end of a running job of the shop
(`job.py status`), except the read-only steps.

1. **Find the source** of the wrong value (`shop_view.py show <shop> <ref>` gives every field below at once;
   `--raw prepared|translated|placement|description` the whole record):
   - brand: `product.brand_source` / `brand_ko` in `$S/prepared/products.jsonl` (the order: TRANSFORM.md
     "A brand for every product"); `lens.py brand <shop> --category <id>` shows its neighbours;
   - title: its rows in `$S/translation/texts.jsonl` (`kind` title, the last row wins; `by` model or `review-<date>`);
   - price: the breakdown, skill `product-trace` step 6 (box, level, tariff), rule: skill `price`;
   - section: `$S/placement/placements.jsonl` (`evidence`, `reason`), rule: skill `placement`;
   - description: its row in `$S/translation/descriptions.jsonl` (`dropped`, `conflicts`, `origin`).
2. **Pick the lever**, the narrowest that fixes it:
   - a brand only the photo shows: an entry in `$S/brand_by_owner.json` (`{entries: {<key>: {brand, why, at}}}`, the
     owner's word), then `.venv/bin/python scripts/run_transform.py <shop>`; the title is asked again for the new
     brand: `.venv/bin/python scripts/translate.py <shop> --only <key>` (one model call);
   - a wrong spelling or term: the live dictionary entry (`scripts/output/dictionaries/`, skill `dictionaries`). It
     changes **every** product that uses it: list them (`shop_view.py query <shop> --grep '<term>' --store
     published --keys-out affected.txt`, then `store_diff.py <shop> --keys-file affected.txt`) before asking;
   - a title: a correction row appended to `$S/translation/texts.jsonl` (`key`, `id`, `kind: title`, `ko` as in the
     last row, `en`, `by: "review-<date>"`, `at`; no `brand_ko`: never asked again; append with
     `shop_files.append_line`), then `.venv/bin/python scripts/translate.py <shop> --offline`;
   - a description: `.venv/bin/python scripts/describe.py <shop> --only <key> --packet` (its input), then
     `--only <key> --force` (one model call);
   - a section: `.venv/bin/python scripts/placement.py <shop>` after the cause is fixed; never pick a section by hand;
   - a rule (transform, placement, price, dedupe, prompt) that is wrong for many: stop, hand it to a developer with
     the evidence (skill of the stage, `scripts/SELLER_DATA.md`).
3. **Check**: `.venv/bin/python scripts/store_diff.py <shop> --only <key>` (read only): exactly the intended change.
   A lever that went through `run_transform.py` (brand_by_owner, a rule): run it with `--diff` (or
   `prepared_diff.py` on a copy, scripts/TRANSFORM.md "What a rule change changed") and read which other products
   moved; `prepared_diff.py ... --published-only --keys-out F` lists those in the store for the owner (rule 1).
4. **Republish** only on the owner's word: `.venv/bin/python scripts/publish.py <shop> --only <key>` (several:
   `--keys-file F`); report the field before and after, the handle and admin link
   (`shopify_catalog.py <shop> show <key>` reads the store's side).
