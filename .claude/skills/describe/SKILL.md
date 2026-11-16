---
name: describe
description: The English product description written by describe.py from the Korean texts and the description images' text, and which model writes it. Use when running or changing describe.py, a description is wrong or missing, the model or effort for descriptions is reconsidered, or a job runs with --describe.
---

# The product's description

Read `scripts/DESCRIBE.md` first; this skill is only the map.

What the doc covers:
- what `describe.py` reads (Korean texts, the images' text), what it writes, before and after the request;
- the model, effort and fallback for this stage, and why not the translation's settings;
- the comparison of models (2026-11-10): quality, cost, time.

Commands (repo root):
- `.venv/bin/python scripts/describe.py <shop> --offline` / `--packet` (no model)
- `.venv/bin/python scripts/describe.py <shop> --only <key>` / `--limit N` (the model, paid calls)
- `.venv/bin/python scripts/job.py new ... --publish --describe` (each product described before it is sent)

Rules:
- Model and effort are `.env` settings (`DESCRIBE_EFFORT`); never read `.env*` or key files.
- Rewriting descriptions of products already in the store: ask the owner first (default: future products only).
- Model calls cost money: small runs first.

More: translation skill `translation`; publication skill `publish`; the OCR stage skill `transform`.
