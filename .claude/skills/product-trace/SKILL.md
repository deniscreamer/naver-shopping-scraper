---
name: product-trace
description: Answer why one product (a Naver product id, a key, a Shopify handle or link) is not in the store, held, a draft, withdrawn, not taken, or has an odd price, section or brand, by a fixed read-only lookup through the shop's files. Use for "почему товара нет", "почему он висит / в драфте / снят", "what happened to <id>", "why is <handle> priced X / in that section / under that brand".
---

# Trace one product

Read only: no command here writes or sends. `S=scripts/output/shops/<shop>`, `J=scripts/output/jobs`; `<id>` is the
Naver product id, the key is `<shop>:naver:<channel>:<id>`.

1. **The key**: `grep -ho '"key": "[^"]*:<id>"' $S/prepared/products.jsonl $S/publish/published.jsonl | head -1`
   (a handle: `grep '"handle": "<handle>"' $S/publish/published.jsonl | tail -1`). No key anywhere: go to step 3.
2. **The ledger**: `grep '"key": "<key>"' $S/publish/published.jsonl | tail -1` (the last row wins): `status`
   (published / withdrawn), `store_status` (DRAFT = not live), `reason` (`replaced_by:<key>`, `hold: ...`, the
   owner's why), `activated`, `restored`, `admin_url`.
3. **The jobs**: `grep -h '<id>' $J/*/events.jsonl`: `not_taken` with its `reason` (`duplicate_of:<key>`,
   `duplicate_of_withdrawn:<key>`, `category_mismatch`, `card_not_found`, a placement hold), `failed` (stage,
   reason), `deferred`, `duplicate_seen` / `duplicate_better` / `replaced` / `replace_skipped`. Then the screen:
   `grep -h '"product_id": "<id>"' $J/*/screened.jsonl` (`ad`, `already_published`, `title:<rule>`, `rental`,
   `category_mismatch`, `deferred`) and `.venv/bin/python scripts/deferred_log.py --store <shop> list`.
   Not in any listing, screen or event: never listed by a job (another query or category).
4. **Prepared**: `grep '"key": "<key>"' $S/prepared/products.jsonl`: `status`, `held` codes, `notes`,
   `product.brand_source` / `brand_ko`, the variants' prices (codes: TRANSFORM.md "Transform", Held).
5. **Translated**: `grep '"key": "<key>"' $S/translation/translated.jsonl`: `status`, `problems`, `missing`.
6. **Placed**: `grep '"key": "<key>"' $S/placement/placements.jsonl`: `status` (placed / unresolved / no_profile),
   `reason`, `evidence`, `leaves`.
7. **The store**, still read only: `.venv/bin/python scripts/store_diff.py <shop> --only <key>` (what a publication
   would change); the price breakdown: `.venv/bin/python scripts/publish.py <shop> --dry-run --only <key>`, then
   `fairwardgolf.price` per variant in `$S/publish/payloads/<id>.json`. Photos: `.venv/bin/python scripts/lens.py
   products <shop> <id>`.

Report, short and fixed: the key; the stage it stopped at; the evidence (file, field, value); who acts next (nothing,
a rerun, the owner's decision, a rule to change); the command that would act, not run. Stop there: any change goes
through the skills `store-actions` or `fix-a-product` and waits for the owner ([scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md)).
