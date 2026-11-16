---
name: run-a-job
description: Run or watch a collection job (scripts/job.py, one product per iteration: collect, OCR, prepare, translate, place, publish). Use when the owner asks to start, continue, resume, scroll or check a job, gives the shorthand "Запусти scroll: query, category, N", when a job stopped or deferred products, or when `job.py status` needs reading.
---

# Running a job

Read `scripts/JOB_AGENT.md` first; this skill is only the map. Its last section, "A job", is the stage's reference.

What the doc covers:
- the two ways: `new` + `run` (a fixed listing) or `scroll` (a big target, the whole category);
- watching: the done / held / failed lines, `status --json`, when to stop and what to report;
- duplicates (`--dedupe`), draft first for a category not marked reviewed, activation after the review;
- after the job: placement, the review sheets, `review due`.

Commands (repo root, server running):
- `.venv/bin/python scripts/job.py new --query "<query>" --category <leaf id> --count N [--publish]`
- `.venv/bin/python scripts/job.py run` / `scroll ...` / `status [--json]`
- `.venv/bin/python scripts/job.py activate --job <id> --dry-run` (the real one only on the owner's word).

Rules:
- Publishing, activating drafts, withdrawing and marking a category `reviewed=True` wait for the owner's word.
- Fixes for products already in the store: ask the owner whether they apply there; the default is future products.
- Shopify writes go only through `publish.py`.

More: a new category first: skill `new-category-or-shop`; after a run: skill `visual-review`; each stage's own skill
(`transform`, `translation`, `describe`, `placement`, `price`, `publish`).
