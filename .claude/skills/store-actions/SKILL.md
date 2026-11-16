---
name: store-actions
description: Act on products already in the Shopify store on the owner's word: activate drafts (one key or a whole job), withdraw, hold a doubtful copy, restore, rehandle or force a resend, reprice, and the state backup with what to tell the owner. Use for "активируй", "сними", "придержи", "верни", "переоцени", "сделай бэкап", the owner's answer to a lens report, or any fix to be applied to published products.
---

# Store actions

Rules: [scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md). Every action: **show** what will happen (command,
keys, titles, numbers) -> the owner's **yes** -> **run** -> **report** what changed (key, handle, admin link, the
ledger row). A number from a lens sheet is a line of that lens's `index.tsv` (column `key`). Every `<key>` below
also takes a product id, a handle or a link, and `--keys-file F` (the owner's list, one a line) or `--job <id>
[--event published]` adds more: **show** with the same command and `--dry-run` (`<key>: would withdraw`, nothing
sent; `<key>: not published here` / `not withdrawn here` / `not a draft here`: the real call would refuse it, tell
the owner; a ref of two products stops with both keys: ask which). Details: scripts/PUBLISH.md
"Withdraw, hold, restore, activate"; refs: scripts/OPERATIONS.md "Naming a product".

A list for the owner (and for `--keys-file`) from the files, read only: `.venv/bin/python scripts/shop_view.py query
<shop> --store draft --category <id> --keys-out drafts.txt` (or `--where held=<code>`, `--job <id>`); the titles to
show: `shop_view.py show <shop> --keys-file drafts.txt --fields key,title,handle,price_krw`.

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
- **Check what was done** (read only, after every action): `.venv/bin/python scripts/shop_view.py history <shop>
  <key>` (the new ledger row); a batch: a plan `key<TAB>state<TAB>reason` (state active, draft, withdrawn; reason
  `hold:`, `replaced_by:`) -> `shop_view.py check <shop> plan.tsv`, every line `ok`; the store's side:
  `.venv/bin/python scripts/shopify_catalog.py <shop> show <key>` (status, handle) and `shopify_catalog.py <shop>
  counts` (active / draft). Report from these, not from memory.
- **State backup**: `.venv/bin/python scripts/state_backup.py --dry-run` (size), then without it (between jobs),
  then `--verify <folder>`; tell the owner: upload the whole folder (archives, MANIFEST.json, RESTORE.md), its size.

Never activate in the Shopify admin by hand, and never touch a product the owner did not name.
