---
name: product-trace
description: Answer why one product (a Naver product id, a key, a Shopify handle or link) is not in the store, held, a draft, withdrawn, not taken, or has an odd price, section or brand, by a fixed read-only lookup through the shop's files. Use for "почему товара нет", "почему он висит / в драфте / снят", "what happened to <id>", "why is <handle> priced X / in that section / under that brand".
---

# Trace one product

Nothing is sent and no state file changes; step 6's dry run writes its payload to `publish/payloads/<id>.json`. Each
command is written out in full, from the repo root (no shell variable for it: zsh does not split it into words). A
`<ref>` is a key, a Naver product id, a handle (an older one too) or a link (store, admin, Naver). The tools:
[scripts/OPERATIONS.md](../../../scripts/OPERATIONS.md) "Reading the shop by hand"; exit 1 with `no product ...
matches` or `N products match` (the candidates listed: trace each, never the first) means what it says.

1. **Everything at once**: `.venv/bin/python scripts/shop_view.py show <shop> <ref>`: the key, `prepared` with `held`
   and `notes`, `brand` and `brand_source`, the titles, `price_krw`, `translation`, `description`, `placement` and
   `leaves` (an odd spec row or gender: a note `specs_by_owner` is the owner's row from
   `scripts/output/shops/<shop>/specs_by_owner.json`), `state` (none = never sent, withdrawn, draft, active), `store_status`, `reason` (`replaced_by:<key>`,
   `hold: ...`, the owner's why), `handle`, `admin`. No product: not in the shop's files, go to step 3.
2. **The ledger's story**: `.venv/bin/python scripts/shop_view.py history <shop> <ref>`: every row with its event
   (created, sent, withdrawn, restored, activated), oldest first; `(never sent)` when none. A full key no file has is
   `in none of <shop>'s files` (exit 1): a typo, or a product never collected here.
3. **The jobs**: `.venv/bin/python scripts/job.py where <ref>`: every job event of the product and every screen
   leave-out of its product id, oldest first (a product id no shop file knows is still found): `not_taken` with its
   reason (`duplicate_of:<key>`, `duplicate_of_withdrawn:<key>`, `category_mismatch`, `card_not_found`, a placement
   hold), `failed` (stage, reason), `deferred`, `duplicate_*` / `replaced`, `screened` (`ad`, `already_published`,
   `title:<rule>`, `rental`, ...). Then `.venv/bin/python scripts/deferred_log.py --store <shop> list`. Nothing: never
   listed by a job (another query or category). The job events are as of their time (a `prepared` event's held code is
   the prepare of that day; the code may have changed since): the current held code is step 1's `show`.
4. **One stage's record in full**: `.venv/bin/python scripts/shop_view.py show <shop> <ref> --raw
   prepared|translated|placement|ledger|description|collected [--path product.variants.0]` (JSON): prepared's variants
   and package, translated's `problems` / `missing`, placement's `reason` / `evidence`, the newest collected line
   (codes: TRANSFORM.md "Held codes").
5. **Siblings** (same seller, same reason): `.venv/bin/python scripts/shop_view.py query <shop> --grep '<channel>'
   --in key` or `.venv/bin/python scripts/shop_view.py query <shop> --where held=<code> --category <id>`.
6. **The store**, still read only: `.venv/bin/python scripts/shopify_catalog.py <shop> show <ref> [--variants]` (what
   the store holds now: status, handle, vendor, collections); `.venv/bin/python scripts/store_diff.py <shop> --only
   <ref>` (what a publication would change); the price breakdown: `.venv/bin/python scripts/publish.py <shop>
   --dry-run --only <ref>`, then `fairwardgolf.price` per variant in `publish/payloads/<id>.json`; the formula:
   `scripts/PRICE.md` "Why is this product priced X (how to use)" (skill `price`). Photos: `.venv/bin/python
   scripts/lens.py products <shop> <ref>`.

By hand, when a tool is down: `grep '"key": "<key>"' scripts/output/shops/<shop>/publish/published.jsonl | tail -1`
(the last row wins), the same for prepared / translation / placement, `grep '<id>' scripts/output/jobs/*/events.jsonl`.

Report, short and fixed: the key; the stage it stopped at; the evidence (file, field, value); who acts next (nothing,
a rerun, the owner's decision, a rule to change); the command that would act, not run. Stop there: any change goes
through the skills `store-actions` or `fix-a-product` and waits for the owner ([scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md)).
