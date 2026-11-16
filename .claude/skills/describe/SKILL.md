---
name: describe
description: The English product description written by describe.py from the Korean texts and the description images' text, and which model writes it. Use when running or changing describe.py, a description is wrong or missing, the model or effort for descriptions is reconsidered, or a job runs with --describe.
---

# The product's description

The stage: `describe.py` writes each product's English description from its Korean texts and the description
images' text, after translation and before publication. The doc: `scripts/DESCRIBE.md`.

| Task | `scripts/DESCRIBE.md` section |
|---|---|
| What `describe.py` reads (Korean texts, the images' text), what it writes, before and after the request | "The product's description" |
| A sentence or list dropped, `fallback`, the caps, what nothing checks | "The product's description" (the checks) |
| A category's profile and brief (`describe.PROFILES`, `prompts/describe/<profile>.md`) | "The product's description" (profiles) |
| `stale`, `--force`, products already in the shop | "The product's description" (the answers) |
| The model, effort and fallback, and why not the translation's settings; the comparison (2026-11-10): quality, cost, time | "Which model writes the descriptions" |
| The images' text it reads | `scripts/PACKAGE.md` "The images' text, read by `describe.py`" |
| A prompt or brief change | skill `prompt-change` |

Commands (repo root):
- `.venv/bin/python scripts/describe.py <shop> --offline` (no model); `--only <key> --packet` prints what the model
  would be given
- `.venv/bin/python scripts/describe.py <shop> --only <key>` / `--limit N` (the model, paid calls)
- `.venv/bin/python scripts/job.py new ... --publish --describe` (each product described before it is sent)

Rules:
- Model and effort are `.env` settings (`DESCRIBE_EFFORT`); never read `.env*` or key files.
- Products already in the store (`--published`, `--force` on one): `scripts/OWNER_RULES.md` rule 1. One product's fix: skill
  `fix-a-product`.
- Model calls cost money: small runs first.

More: translation skill `translation`; publication skill `publish`; the OCR stage skill `transform`.
