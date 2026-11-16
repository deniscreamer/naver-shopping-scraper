---
name: publish
description: Publication of prepared, translated and placed products to the Shopify store (publish.py, shopify_payload.py, shopify_admin.py), with withdraw, restore and activate, store_diff.py, and the Shopify roadmap. Use when publishing, a dry run of the payload, a product must be withdrawn, restored or activated, the store and our files disagree, or the payload or metafields change.
---

# Publication to Shopify

The stage: `publish.py` sends prepared, translated and placed products to the Shopify store and keeps the ledger
`publish/published.jsonl`. The doc: `scripts/PUBLISH.md`.

| Task | `scripts/PUBLISH.md` section |
|---|---|
| What makes a product publishable (ready, translated, placed), what one publication sends | "Publication" |
| Draft first for a category not marked reviewed; the ledger | "Publication" |
| Withdraw, hold, restore, activate (the operator's procedure: skill `store-actions`) | "Withdraw, hold, restore, activate" |
| The owner's payload rules (title, vendor, price) | "The payload" |
| Metafields | "Metafields" |
| Credentials (never read them), tokens, uploads | "Access and uploads" |
| The Shopify roadmap, what the naver-harvester published | "Shopify roadmap", "What the naver-harvester published" |
| The store and our files disagree | `store_diff.py` below; skill `product-trace` |

Commands (repo root):
- `.venv/bin/python scripts/publish.py <shop> --dry-run` (payloads to `publish/payloads/`, nothing sent)
- `.venv/bin/python scripts/store_diff.py <shop>` (read only: what a publication would change)
- `.venv/bin/python scripts/publish.py <shop> --only <key>` (writes); `--withdraw <key> --reason "..."`,
  `--restore <key> --reason "..."`, `--activate <key>` (each repeatable)

Rules:
- Shopify writes go only through `publish.py` / `shopify_admin.py` (AGENTS.md rule 3).
- Publish, withdraw, hold, restore, activate, republish: `scripts/OWNER_RULES.md`.
- Never read credential files or `.env*`.

More: price skill `price`; placement skill `placement`; description skill `describe`; review by eye skill
`visual-review`; jobs skill `run-a-job`.
