---
name: translation
description: The translation stage (translate.py) of prepared Korean texts to English through the model API, its dictionaries, unit rules, prompts and review cleaning. Use when running or changing translate.py, a term is translated wrong, a product stays untranslated, a dictionary entry or prompt changes, a new shop or category needs its terms, or the translation quality is checked (translate_eval.py).
---

# Translation

The stage: `translate.py` turns a prepared product's Korean texts into English (its own store, a dictionary, the
rules, then the model), before placement and publication. The doc: `scripts/TRANSLATION.md`.

| Task | `scripts/TRANSLATION.md` section |
|---|---|
| Run it, read `translated` / `untranslated` / `pending` / `held`, the dictionary backup reminder | "How to use" |
| What the stage translates and in which order (own store, dictionary, rules, model) | "Translation" |
| The owner's decisions: model, fallback, few tokens, what is not translated (the description is `describe`'s) | "Decisions" |
| A product's own title or review | "1. The product's own store" |
| A term wrong for every product; live / backup dictionaries | "2. Dictionaries" (judge, fix, back up, reach the products: skill `dictionaries`) |
| Units, sizes, 노브랜드 | "3. The rules" |
| Prompts, briefs, checks, fix rounds, fallback, batches, tokens, keys | "4. The model and its prompts" (a change: skill `prompt-change`) |
| Reviews cleaned wrong | "Review cleaning" |
| A new shop (tenant) or Naver category: its terms and briefs | "A new shop (tenant) or category" |
| The quality check (`translate_eval.py`) | "Quality check" |
| A known wrong case, what is still open | "Known limits", "Open" |

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
