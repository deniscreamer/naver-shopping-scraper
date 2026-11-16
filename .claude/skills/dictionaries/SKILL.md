---
name: dictionaries
description: The translation dictionaries (brand for the shop, the other kinds per Naver category; live copies and their git backups), translation_dicts.py status / backup, reading new and changed entries before a backup, fixing or deleting a wrong entry, the owner's brands (brand_by_owner.json), and how a dictionary change reaches products already in the store. Use for "словарь", "бэкап словарей", "dictionaries: a backup is due", "неправильный перевод термина у всех товаров", "бренд пишется по-разному", a new category's first entries, or after a run that grew the dictionaries.
---

# Dictionaries

One Korean text -> one English per kind, read before the model is asked (`translation_dicts.py`). Rules:
[scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md). `S=scripts/output/shops/<shop>`.

| Task | Doc "Section" |
|---|---|
| Where they live, scopes, live vs backup, the sync, the thresholds | `scripts/TRANSLATION.md` "2. Dictionaries", "Decisions" |
| The backup reminder of a run or a job | `scripts/TRANSLATION.md` "How to use" |
| A new category's first entries | `scripts/TRANSLATION.md` "A new shop (tenant) or category" (5); `scripts/ONBOARDING.md` "D. The order of a first run" (6), L4 and L8 in "Learned on the first new category (50002787, 2026-11-11)" |
| How a brand is chosen; the owner's brand for one product | `scripts/TRANSFORM.md` "A brand for every product"; skill `fix-a-product` |
| The vendor's spelling from the brand dictionary | `scripts/PUBLISH.md` "The payload (`shopify_payload.py`)" |
| The disk state backup (live dictionaries, `brand_by_owner.json`) | `scripts/OPERATIONS.md` "Backup (`state_backup.py`, the owner 2026-11-16)" |

Where: live `scripts/output/dictionaries/brand.json` and `<category id>/<kind>.json` (out of git, grown by runs);
backup `scripts/dictionaries/` (same layout, in git, stamped `backed_up`). Kinds: `brand` (the shop's) and per
category `option_name`, `option_value`, `spec_label`, `spec_value`, `fact_label`, `fact_value`, `addon_group`,
`addon_name`, `text_label`, `text_placeholder`. A file: `{"format": "dictionary/1", "kind", "entries": {ko: en}}`.

1. **Read** (no writes): `.venv/bin/python scripts/translation_dicts.py status` (or `--json`, field `action`).
   Lines: `+ ko -> en` new, `~ ko: old -> new` changed (git -> live), `< ko -> en (only in git)` (the next run takes
   it). `advice` / `action`: `none` in sync; `wait` below 20 entries and 7 days; `backup` due, read the `+` lines;
   `review` due with changed entries, read the `~` lines first (the backup writes the live English over git's).
2. **Judge each entry** against the category brief (`scripts/prompts/categories/<id>.md`) and the maker's own Latin
   spelling: a lost age or gender word, a flex letter glued to the next club, a sound-spelled brand, a sport or
   "Generic" as a brand (TRANSFORM.md "A brand for every product" lists the no-firm words). A new category: every
   entry before its first backup.
3. **Fix** a wrong one in the live file's `entries`, after the shop's running job ends (`job.py status`; no lock
   guards the dictionaries). Delete for good: both copies, else the next run pulls the backup's back. Unsure of a
   brand or term: ask the owner, never invent one (OWNER_RULES "3. Never").
4. **Back up**: `.venv/bin/python scripts/translation_dicts.py backup` (live -> `scripts/dictionaries/`, prints
   `backed up: ...; commit scripts/dictionaries/`); the commit is the developer's, when asked.
5. **Reach the products**: the change alters every product that reads the entry, in every later build. Rebuild
   offline: `.venv/bin/python scripts/translate.py <shop> --offline` (rewrites `translation/translated.jsonl`, no
   model; a brand entry also feeds the transform's brand fallback: first `run_transform.py <shop>`). Then
   `.venv/bin/python scripts/store_diff.py <shop>` (read only; `--category <id>` narrows) lists the published
   products and fields a publication would change. Applying it to them is the owner's word each time
   (OWNER_RULES "1. Products already in the store"); the commands: skill `store-actions`.

**`$S/brand_by_owner.json`**: `{entries: {<key>: {brand, why, at}}}`, one product whose brand only its photo shows
(brand source `owner`, before every other step). An entry only with the owner's brand; then `run_transform.py <shop>`
and `translate.py <shop> --only <key>` (the title asked again, one model call): skill `fix-a-product` step 2.

Needs the owner: a brand or term not on the page or maker (ask), any `brand_by_owner.json` entry, re-sending
published products. Free: `status`, reading, `store_diff.py` without `--adopt`, new brands entering by runs.
