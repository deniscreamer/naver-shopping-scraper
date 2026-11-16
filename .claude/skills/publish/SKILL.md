---
name: publish
description: Publication of prepared, translated and placed products to the Shopify store (publish.py, shopify_payload.py, shopify_admin.py), with withdraw, restore and activate, store_diff.py, and the Shopify roadmap. Use when publishing, a dry run of the payload, a product must be withdrawn, restored or activated, the store and our files disagree, or the payload or metafields change.
---

# Publication to Shopify

Read `scripts/PUBLISH.md` first; this skill is only the map.

What the doc covers:
- what makes a product publishable (ready, translated, placed) and what one publication sends;
- draft first for a category not marked reviewed; the ledger `publish/published.jsonl`;
- the owner's payload rules (title, vendor, price, metafields); withdraw, hold, restore, activate (the operator's
  procedure: skill `store-actions`);
- the Shopify roadmap and what the naver-harvester published.

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
