---
name: prompt-change
description: Change a model prompt or brief (developer): the translation prompts (translate_system.md, translate_fix.md, a shop's or a Naver category's brief) or the description prompts (describe_system.md, a profile's brief), then measure it with translate_eval.py or a describe sample. Use before editing anything in scripts/prompts/, when a term, tone or description list reads wrong for many products, or when a new shop or category needs its brief.
---

# A prompt change

Where the prompts live, `scripts/prompts/`:
- translation: `translate_system.md` (the base), `translate_fix.md` (the fix round),
  `tenants/<shop>.md`, `categories/<Naver leaf id>.md`, assembled by `translate.system_prompt`;
- description: `describe_system.md` (no golf rule or term), `describe/<profile>.md`, the profiles in `describe.PROFILES`;
- the quality judge's prompt is in the code: `translate_eval.JUDGE_SYSTEM`.

| Task | Section |
|---|---|
| How the translation prompt is assembled, checked, fixed, its tokens | `scripts/TRANSLATION.md` "4. The model and its prompts" |
| A brief for a new shop or category | `scripts/TRANSLATION.md` "A new shop (tenant) or category" |
| Measure a translation prompt | `scripts/TRANSLATION.md` "Quality check"; past rounds "History" |
| The description's profiles, briefs, checks | `scripts/DESCRIBE.md` "The product's description" |
| A description model's cost and quality | `scripts/DESCRIBE.md` "Which model writes the descriptions" |
| A wrong term for every product (not a prompt) | `scripts/TRANSLATION.md` "2. Dictionaries" |
| A brand name or spelling | `scripts/TRANSLATION.md` "2. Dictionaries" (looked up first; `vendors`), `prompts/translate_system.md` "brand"; which brand a product has: `scripts/TRANSFORM.md` "A brand for every product" |

Steps:
1. Show the failure on real rows (`translation/texts.jsonl`, `translation/descriptions.jsonl`) and say why a prompt,
   not a dictionary entry or a rule, fixes it.
2. Edit the narrowest file: a category's brief before the base prompt.
3. Offline checks: `.venv/bin/python -m pytest scripts/test_translate.py scripts/test_describe.py -q`, then
   `scripts/check.sh`; `describe.py <shop> --only <key> --packet` prints what the model is given.
4. Measure, small, on the owner's go-ahead (paid calls): `.venv/bin/python scripts/translate_eval.py <shop>
   --products 12` (a scratch folder, empty dictionaries; the cost per product: its docstring), or
   `describe.py <shop> --only <key> --force` on a few products not in the store. A translation: compare the
   judge's flags with the last round in TRANSLATION.md "History". A description has no judge: read the sample
   against its packet; the checks' counts are `described: {ok, trimmed, fallback}` (DESCRIBE.md "How to use").
5. Same commit: the doc's section, and a dated line with the round's numbers: TRANSLATION.md "History"; a
   description under DESCRIBE.md "Which model writes the descriptions" (a model) or the profile's paragraph.

What it reaches: `translate.py` asks only for texts with no answer yet; a brand already in the shop's
`dictionaries/brand.json` never reaches the model (`translate.plan`), and `vendors` is sent only when a brand is
asked. `translate_eval.py` runs with empty dictionaries, so `vendors` is empty there and the vendor-reuse rule is
not measured by it: check it with `translate.py <shop> --only <key>` on an unpublished product whose brand has no
dictionary entry (the packet's `vendors`: `scripts/test_translate.py`). `describe.py` keeps a product's row
(the stale check hashes the packet, not the prompt). So a new prompt reaches new products; asking again for
products already in the store resends them: `scripts/OWNER_RULES.md` section 1 (`describe.py --published`).

Ask the owner first: any run beyond a small sample (money); asking again for published products; a model, effort
or provider change (`.env` settings, the owner's decisions: TRANSLATION.md "Decisions"). Never read `.env*` or
the key files.

More: skills `translation`, `describe`; one product's title or description: skill `fix-a-product`.
