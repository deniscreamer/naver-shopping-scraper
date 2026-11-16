---
name: dedupe-rule
description: Change the duplicate rule (developer): scripts/dedupe.py's signals, strong, title_only, long_title, alike, the kinds (_KINDS, _DIMS, _MODEL_WORDS, _SAME, _FILLER) and thresholds, then measure it on the store's old groups and the owner's reviewed versions, and pilot it with --dedupe log before on. Use before editing dedupe.py, when a lens review or --pairs shows a missed copy or a false merge, or for "дубли не ловятся", "склеил разные товары", "поправь правило дублей", "dedupe rule".
---

# A change to the duplicate rule

The doc is `scripts/DEDUPE.md`, and the code's own description is the `dedupe.py` docstring. What waits for the owner
is in `scripts/OWNER_RULES.md`. Read the doc's section for the task; the rules are not copied here.

| Task | Read |
|---|---|
| What the rule does now: title key, confirmed, agency imports, `strong`, better | `DEDUPE.md` "The rule" |
| Why each part exists (pilot, wedge pilot, the store's cleanup) | `DEDUPE.md` "History"; the dated comments in `dedupe.py` |
| The job side: `log` / `on`, events, replacement | `DEDUPE.md` "How to use" and its `--dedupe` modes subsection, "What a job's events mean, and what you do" |
| Groups in the store, `title only` | `DEDUPE.md` "`--report`: groups in the store"; `scripts/LENSES.md` "`dupes`: one product or versions?" |
| The fixtures and tests | `test_dedupe.py` (real fairwardgolf cases); `LENSES.md` "Tests and the fixture" (`fixtures/lens/cases.json`) |
| A copy the rule missed, found by eye | `OWNER_RULES.md` "2. Duplicates the rules missed (the owner, 2026-11-16)" |

Procedure (offline unless noted; no command changes the shop's state: `lens.py` writes only its contact sheets
under `scripts/output/shops/<shop>/lens/`, `make_lens_fixture.py` the fixture, `--pairs` the job's `pairs/`):
1. Pin the case: both keys, their titles, signals (`grep '<id>' scripts/output/jobs/*/events.jsonl` for
   `duplicate_seen` / `not_taken` / `duplicate_better`; `lens.py products <shop> <id1> <id2>`, the visual-review skill).
   Write the failing test first in `scripts/test_dedupe.py`, with real product ids, beside its neighbours. Include a
   must-not-match case: Orlimar club / putter, 27ZXI-RKT / LS, Wilson JGI sizes, Aged 3-5 / 9-12.
2. Measure before the edit. Save the output to the scratchpad. The groups cover the whole ledger, including the
   2026-11-15 cleanup's `replaced_by:` copies. Also check the owner's reviewed versions:
   ```sh
   .venv/bin/python -I -c "
   import sys; sys.path.insert(0, 'scripts'); import dedupe as d
   shop = sys.argv[1]; rec = d.collected(shop)
   es = [d.entry(rec[k], r['status']) for k, r in d.ledger(shop).items() if k in rec and r.get('status') in ('published', 'withdrawn')]
   gs = [{e['key'] for e in g} for g in d.groups(es)]
   for g in gs: print('group', ' '.join(sorted(g)))
   for r in d._jsonl(f'scripts/output/shops/{shop}/lens/reviewed.jsonl'):
       print('versions', 'JOINED' if any(set(r['keys']) <= g for g in gs) else 'apart', ' '.join(r['keys']))
   " fairwardgolf | sort > <scratchpad>/before.txt
   .venv/bin/python scripts/dedupe.py --report fairwardgolf --list > <scratchpad>/report_before.txt
   ```
3. Edit `dedupe.py`. Add a dated comment at the constant or function that names the real case (house style).
4. Run the same commands into `after.txt`, then `diff`:
   - A group that is new or larger is a possible false merge. Look at it on photos (`lens.py products`) before you
     keep the change.
   - A `versions` row that changed from `apart` to `JOINED` contradicts the owner's word, so the change is wrong.
     The two BG-100 and REVA rows are `JOINED` today (title words only, by design).
   - A group that is gone or smaller can mean lost copies. Check that it was meant.
5. `.venv/bin/python -m pytest scripts/test_dedupe.py scripts/test_lens_fixture.py scripts/test_lens.py -q`, then
   `scripts/check.sh`. If the lens fixture must pin a new case, add a `CASES` line in `make_lens_fixture.py` that says
   why. Then run `.venv/bin/python -I scripts/make_lens_fixture.py` and read the diff.
6. The pilot runs on the owner's word, through the run-a-job skill: `job.py new|scroll ... --dedupe log`. It changes
   nothing but `duplicate_seen` events. Then run `dedupe.py --pairs <shop> --job <id>`, which writes the sheets in the
   job's `pairs/`, and show the owner the pairs. Only after his yes does the rule run under `on`, which is the default.

Same commit (AGENTS.md rule 6): `dedupe.py` and its docstring; `test_dedupe.py`; `DEDUPE.md` "The rule" and a
"History" line; the lens fixture if a case was added. A new or renamed decision also changes the `TRANSFORM.md`
"Held codes" row (`test_docs_held_codes.py` checks it) and the events table. A new `--dedupe` mode changes the
`job.py` help and docstring and `shop_types.py` `dedupe`. Changed marks change `LENSES.md` `dupes`.

The owner's word:
- New groups the change finds in the store are only listed (`dedupe.py --report`, `lens.py dupes`). Withdrawing a
  copy (`replaced_by:` or a `hold:`) and marking versions (`lens.py dupes --versions`, which writes
  `reviewed.jsonl`) wait for him (`OWNER_RULES.md` rules 1 and 2, the store-actions skill).
- Known gap: one product listed with other variant text or other colour photos is not caught. Such copies are
  held as drafts with a `hold:` reason, and he decides each one (`OWNER_RULES.md` rule 2). Do not widen the rule
  for this gap unasked; ask him first.
- Price never decides "better". A threshold change (`PRICE_RATIO`, `PHOTOS_SHARED`, `VARIANTS_JACCARD`,
  `STRONG_PHOTOS`, `WORDS_ALIKE`) is shown to the owner with the measured diff before the commit.
