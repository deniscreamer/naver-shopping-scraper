---
name: shop-data
description: Answer questions about many of a shop's products from its files, its jobs and the store, read only, with the owner's read tools (shop_view.py show / query / ledger / history / check, job.py report / where, prepared_diff.py, shopify_catalog.py show / counts / vendors / collection / dump) instead of grep or hand-written Python. Use for "сколько товаров ...", "какие товары ...", "список ключей для ...", "сколько в магазине / в драфте / снято", "что изменилось после правила", "сверь план с ledger", a list of keys to feed an action (--keys-file), or the store's side of our files.
---

# Shop data, read only

Nothing here sends or writes but the `--keys-out` / `--table` / `--out` file you name (keep it in the scratchpad).
The doc: `scripts/OPERATIONS.md` "Reading the shop by hand" (fields, filters, outputs, exit codes); refs (key,
product id, handle, link): "Naming a product". One product's why: skill `product-trace`. Run from the repo root, each
command written out in full (no shell variable for it: zsh does not split one into words, and an agent's commands
share no shell state).

| Question | Command |
|---|---|
| How many products by stage / hold / store state | `.venv/bin/python scripts/shop_view.py query <shop> --count-by prepared` (or `held`, `state`, `placement`, `brand_source`, `leaves`) |
| Which products match (a list, a keys file) | `.venv/bin/python scripts/shop_view.py query <shop> --where prepared=held --where held=single_only [--category C] [--leaf L] [--store draft] [--keys-out F]` |
| Titles or brands that contain a word | `.venv/bin/python scripts/shop_view.py query <shop> --grep '<RE>' [--in title_en,brand_en] [--store published]` |
| A product's fields, or several as a table | `.venv/bin/python scripts/shop_view.py show <shop> <ref...> [--fields key,state,title,price_krw,handle]`; `--keys-file F` for a list |
| One stage's record as JSON | `.venv/bin/python scripts/shop_view.py show <shop> <ref> --raw prepared\|translated\|placement\|ledger\|description\|collected [--path a.b.0]` |
| What the ledger did (today, by event or reason) | `.venv/bin/python scripts/shop_view.py ledger <shop> [--since 2026-11-16] [--status withdrawn] [--count-by event\|reason_code\|day]` |
| One product's ledger story | `.venv/bin/python scripts/shop_view.py history <shop> <ref>` |
| Did a batch of actions land as planned | a TSV `ref<TAB>state[<TAB>reason prefix]` -> `.venv/bin/python scripts/shop_view.py check <shop> plan.tsv` (exit 0: every line ok) |
| What a job did; one outcome's products | `.venv/bin/python scripts/job.py report --job <id> [--event not_taken] [--table -]` |
| Where a product went across the jobs | `.venv/bin/python scripts/job.py where <ref>` |
| Old model answers (titles, option names, descriptions) a new rule, dictionary or prompt judges wrong; what a resend would change for products in the store (groups, worse) | `.venv/bin/python scripts/sweep.py <shop> [--answers \| --store] [--json] [--only <ref> \| --keys-file F]` (writes only `sweep/`, its keys files and `groups/<id>.keys`; what each check, group and guard means and what to do: `scripts/SWEEP.md`) |
| What a prepare / rule change changed, which are in the store | `.venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl --published-only [--keys-out F]` (skill `transform`) |
| The store's own counts, vendors, a collection, one product | `.venv/bin/python scripts/shopify_catalog.py <shop> counts \| vendors \| collection <handle> [--count-by vendor,status] \| show <ref>` |
| A snapshot of the store's products | `.venv/bin/python scripts/shopify_catalog.py <shop> dump [--fields id,handle,status,vendor,key] [--query 'status:active'] --out <scratch>/store.jsonl` |

Rules:
- Every row is `TAB`-separated (lists comma-joined); `--json` for anything parsed further. Exit 1 with `N products
  match`: name the key, never take the first; exit 1 with `<path>:<n>: not a JSON line`: skill `recover-state`.
- A keys file (`--keys-out`) feeds `--keys-file` of publish, translate, describe, store_diff, reprice and
  `shop_view.py show`; any action on it is the owner's word first (skill `store-actions`, OWNER_RULES.md rule 1).
- `shopify_catalog.py` reads the Admin API (one query a command, a page of 100): use it for the store's side, our
  files for the rest; never read the credential files yourself (exit 3: the store is not configured, ask the operator).
- Report numbers with the command that produced them.
