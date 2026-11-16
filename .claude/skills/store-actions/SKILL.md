---
name: store-actions
description: Act on products already in the Shopify store on the owner's word: activate drafts (one key or a whole job), withdraw, hold a doubtful copy, restore, rehandle or force a resend, reprice, and the state backup with what to tell the owner. Use for "активируй", "сними", "придержи", "верни", "переоцени", "сделай бэкап", the owner's answer to a lens report, or any fix to be applied to published products.
---

# Store actions

Rules: [scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md). Every action: **show** what will happen (command,
keys, titles, numbers) -> the owner's **yes** -> **run** -> **report** what changed (key, handle, admin link, the
ledger row). A number from a lens sheet is a line of that lens's `index.tsv` (column `key`); a product id: skill
`product-trace` step 1. Details: scripts/PUBLISH.md "Withdraw, hold, restore, activate".

- **Activate one or a few**: `.venv/bin/python scripts/publish.py <shop> --activate <key>` (repeat `--activate`).
  `not a draft here`: the key is live, withdrawn or held already.
- **Activate a job's drafts**: `.venv/bin/python scripts/job.py activate --job <id> --dry-run` (show the list), then
  without `--dry-run`; then run the `--withdraw` lines it prints for old copies, again on the owner's word. A mixed
  answer ("activate 3, hold 2"): withdraw / hold first, then activate the rest (per key, or `job.py activate` when
  the rest is the whole job).
- **Withdraw**: `.venv/bin/python scripts/publish.py <shop> --withdraw <key> --reason "<the owner's why> (owner
  <date>)"`. A copy the owner judged a replacement: `--reason "replaced_by:<kept key>"`.
- **Hold** a doubtful copy (OWNER_RULES rule 2): `--withdraw <key> --reason "hold: ..."`, the exact reason in
  [OWNER_RULES.md](../../../scripts/OWNER_RULES.md) rule 2; versions instead: `lens.py dupes <shop> --versions <k>,<k> --note
  "..."`.
- **Restore**: `.venv/bin/python scripts/publish.py <shop> --restore <key> --reason "..."`; the next
  `publish.py <shop> --only <key>` sends today's data (ask: it re-sends).
- **Rehandle / force** (re-send, OWNER_RULES rule 1: say what changes and how many): first
  `.venv/bin/python scripts/store_diff.py <shop> --only <key>`, then `publish.py <shop> --only <key> --rehandle` or
  `--force`.
- **Reprice**: `.venv/bin/python scripts/reprice.py <shop> [--only <key>]` (table + TSV under `publish/`, offline):
  without `--only` it prints the whole shop's table, enough to show one category's rows; then `--apply` with the
  same scope. A category: its keys from `lens.py section <shop>
  --category <id>`'s `index.tsv`, as `--only` each (skill `price`).
- **State backup**: `.venv/bin/python scripts/state_backup.py --dry-run` (size), then without it (between jobs),
  then `--verify <folder>`; tell the owner: upload the whole folder (archives, MANIFEST.json, RESTORE.md), its size.

Never activate in the Shopify admin by hand, and never touch a product the owner did not name.
