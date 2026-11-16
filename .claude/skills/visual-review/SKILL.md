---
name: visual-review
description: Look at a shop's products by eye through contact sheets (scripts/lens.py) and prove each doubt from the data. Use after a pilot or job (is every product the section's?), before withdrawing duplicates (one product or versions?), when many products were prepared but not published (was the hold right?), after a price, brand, placement or dedupe rule change, when a job or `job.py status` prints `review due` (drafts of a category not marked reviewed), or when the owner asks to check, compare or review products, a category or a section.
---

# Visual review of products

The stage: `lens.py` draws a shop's products as numbered contact sheets for one question; the agent reads them and
proves each doubt from the data. Read only and offline. The doc: `scripts/LENSES.md`.

| Task | `scripts/LENSES.md` section |
|---|---|
| The five rules of use (read only, the text proves, the owner decides, drafts) | "The rule of use" |
| The files, `index.tsv`, `summary.json` | "The tools" |
| Which lens for which question | "The lenses and when to use them" (`section`, `price`, `brand`, `dupes`, `held`, `products`) |
| How to read a sheet | "Reading a sheet (for an agent)" |
| The lens fixture, a new lens | "Tests and the fixture", "Adding a lens" |
| Duplicates: what dedupe decided | `scripts/DEDUPE.md` "How to use" |

Rules: `scripts/OWNER_RULES.md` (sections 2 and 3). The procedure:

1. **Pick the lens from the question.** A job printed a review block (`review due`): run exactly its commands
   (`job.py status --job <id> --json`, key `review.commands`), then go on from step 3.
   - Section content after a run: `section --leaf <leaf>` (or `--job <id>`).
   - Odd items among sets: `price --category <id>`.
   - Vendor doubts: `brand --category <id> --source none,title_word,description_row` (blue: one brand, several
     spellings).
   - Duplicates before a withdrawal: `dupes [--category <id>]`. Groups the owner judged versions:
     `dupes --versions <key>,<key> --note "..."` (on the owner's word only).
   - Too many products held, not taken, failed or deferred: `held --job <id>`.
   - One doubt, a comparison, a finding to show: `products <id> ...`.
2. **Run it** from the repo root:
   `.venv/bin/python scripts/lens.py <lens> <shop> [scope]`.
   It prints the card count, the red and blue numbers (the first 30 of each; all in `summary.json` meta), and the
   paths of the sheets, `index.tsv` and `summary.json`.
   It is read only and offline.
3. **Look at every sheet yourself** with the Read tool. Note the doubtful numbers and why, red and blue first, then
   anything else that looks wrong.
4. **Prove each doubt from the text.** Use its `index.tsv` line (title, price, variants, options, links). Run `lens.py products <shop> <ids>` when one photo cannot settle it. A photo alone is
   never the reason.
5. **If the doubt points to a rule** (a word missing from `listing_title_rules.json`, a dedupe kind, a brand source),
   say which rule and show the numbers. Fix it with a test only when the task is yours to fix (AGENTS.md rules).
6. **Report to the owner:**
   - the lens and its scope;
   - the cards looked at;
   - each finding with its number, key, title and reason;
   - what you could not settle;
   - the sheets' folder.
7. **Do not touch the store before the owner's word** (`scripts/OWNER_RULES.md`). A copy of a live product the
   rules missed: list both keys, titles and prices and ask; meanwhile hold it (rule 2). The owner's answer
   (activate, withdraw, hold, versions) is carried out with the skill `store-actions`.

More: one product's trace skill `product-trace`; a rule the review points to skill `seller-pattern-rule`.
