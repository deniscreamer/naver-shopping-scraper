---
name: run-a-job
description: Run or watch a collection job (scripts/job.py, one product per iteration: collect, OCR, prepare, translate, place, publish). Use when the owner asks to start, continue, resume, scroll or check a job, gives the shorthand "Запусти scroll: query, category, N", when a job stopped or deferred products, or when `job.py status` needs reading.
---

# Running a job

Rules: [scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md). The doc: `scripts/JOB_AGENT.md`; read the section
for the task, the whole doc only for an unusual stop.

**"Запусти scroll: <запрос>, категория <id>[, N | до конца][, без публикации]"** (the owner, 2026-11-14) is one
`job.py scroll` with the per-category defaults of JOB_AGENT.md "Shorthand and per-category defaults":

- `TRANSLATE_PROVIDERS=anthropic`; 50002788: `--paid-variants`; 50002787: `--paid`; 50002670 and 50002783:
  `--paid-variants` (their pilots' job.json); then `--publish --describe`; another category: its latest job.json.
- N -> `--count N`; none or "до конца" -> no `--count`; "без публикации" -> no `--publish --describe`;
  `--dedupe on` is the default; `--draft` (2026-11-16) when the owner will decide the activation after the review.
- Narrow queries: full sets `남성 골프채 풀세트`, then `여성 골프채 풀세트` (two jobs); junior `주니어 골프채`.
- The old mode (`new` + `run`) only when the owner says "старым методом" or 2+ queries are needed.

Steps:
1. Preflight: `curl -s localhost:8000/health` shows `"extension": "connected"`; `.venv/bin/python scripts/job.py
   status` shows no running job (never a second runner).
2. Start it in the background, the log in `scripts/output/jobs/_scroll-logs/` (`mkdir -p` it):
   `TRANSLATE_PROVIDERS=anthropic .venv/bin/python -u scripts/job.py scroll --query "<q>" --category <id> <flags>
   > scripts/output/jobs/_scroll-logs/<name>-<UTC stamp>.log 2>&1`.
3. Watch the log: report every 20 products published, and at once on `STOP`, a captcha, a listing tab reopen or a
   long network wait. What each line means and who acts: JOB_AGENT.md "What stops, and who acts".
4. Resume: `job.py scroll --job <id>` (`run` for an old-mode job), only after a stop the owner cleared.
5. `review due` (drafts): skill `visual-review` with the printed commands; activation: skill `store-actions`.

Read: `.venv/bin/python scripts/job.py status [--job <id>] [--json]`. Old mode: `job.py new --query "<q>"
--category <id> [--count N | --all] <flags>`, then `job.py run`; `job.py refresh --more N` reads the listing deeper.

More: after a run skill `visual-review`; why one product is missing skill `product-trace`; a new category first
skill `new-category-or-shop`.
