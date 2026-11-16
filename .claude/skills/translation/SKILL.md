---
name: translation
description: The translation stage (translate.py) of prepared Korean texts to English through the model API, its dictionaries, unit rules, prompts and review cleaning. Use when running or changing translate.py, a term is translated wrong, a product stays untranslated, a dictionary entry or prompt changes, a new shop or category needs its terms, or the translation quality is checked (translate_eval.py).
---

# Translation

Read `scripts/TRANSLATION.md` first; this skill is only the map.

What the doc covers:
- the owner's decisions (model, fallback, few tokens, what is not translated: the description is `describe`'s);
- the per-kind dictionaries (live / backup), unit rules, prompts and briefs;
- a new shop or Naver category, the quality check, what is still open.

Commands (repo root):
- `.venv/bin/python scripts/translate.py <shop> --offline` (no model: what the dictionaries and rules leave)
- `.venv/bin/python scripts/translate.py <shop> --limit 3` (the model, paid calls)
- `.venv/bin/python -m pytest scripts -q`

Rules:
- Models and efforts are `.env` settings, not code; never read `.env*` or the key files.
- A dictionary change can alter published products: `store_diff.py <shop>`, then `scripts/OWNER_RULES.md` rule 1. One product's
  title or term: skill `fix-a-product`.
- Model calls cost money: small runs first.

More: the description skill `describe`; the transform skill `transform`; jobs skill `run-a-job`; a new category
skill `new-category-or-shop`.
