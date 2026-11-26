# Running a job (for the agent)

A job takes one listing and works product by product: collect -> description images (OCR) -> prepare (reviews
sanitized) -> translate (the model API, `translate.py`; a job made with `new --no-translate`, or before 2026-11-08,
stops at prepare) -> with `new --publish`: placement (the whole shop, offline) and publication of this product
(`publish.py`: Shopify, ACTIVE, or DRAFT for a category not marked reviewed, every sales channel), then the next
product. It resumes where it stopped. Without `--publish`, placement (`placement.py <shop>`) and `publish.py <shop>`
run on the whole shop after the job. Code, files, waits and stops: the `scripts/job.py` docstring; the stages' own
docs: the map in [README.md](README.md), Docs.

**What waits for the owner** (publishing old products again, activating, withdrawing, holding a copy, the Never
list): [OWNER_RULES.md](OWNER_RULES.md). A job's own publication of its new products needs no question.

**How to use this doc**: read the section for the task, the rest only for an unusual case.

| Task | Section |
|---|---|
| "Запусти scroll: ..." | [Shorthand and per-category defaults](#shorthand-and-per-category-defaults-the-owner-2026-11-14) |
| Check before a start | [1. Before](#1-before) |
| Start (scroll, or the old mode) | [2. Start](#2-start) |
| Watch: what to report, what a line means | [3. Watch](#3-watch), [What stops, and who acts](#what-stops-and-who-acts) |
| Stop or resume | [4. Stop and resume](#4-stop-and-resume) |
| `review due`, activation, the look after a run | [5. After](#5-after), [Draft first](#draft-first-a-category-not-yet-reviewed-the-owner-2026-11-16) |
| `duplicate_of`, `replaced`, `--dedupe` | [Duplicates](#duplicates) -> [DEDUPE.md](DEDUPE.md) |
| scroll or `new` + `run`; which query | [Two ways to run a job](#two-ways-to-run-a-job-which-one-when), [The query](#the-query-what-a-listing-holds-2026-11-14-50002788) |
| `--paid`, `--paid-variants`, `--all`, `--draft` | [Flags](#flags) |

## Shorthand and per-category defaults (the owner, 2026-11-14)

"Запусти scroll: <запрос>, категория <id>[, N | до конца][, без публикации]" means one `job.py scroll`:

```sh
TRANSLATE_PROVIDERS=openai,anthropic .venv/bin/python -u scripts/job.py scroll --query "<запрос>" --category <id> \
    <paid flag> --publish --describe [--count N] \
    > scripts/output/jobs/_scroll-logs/<name>-<UTC stamp>.log 2>&1
```

`mkdir -p scripts/output/jobs/_scroll-logs` first. `<name>`: a short word for the category or query (e.g.
`wedge-sets`, `junior`); the stamp: `date -u +%Y%m%dT%H%M%SZ`.

| Category | Paid flag | Narrow query (the last jobs) |
|---|---|---|
| 50002788 full sets | `--paid-variants` | `남성 골프채 풀세트`, then `여성 골프채 풀세트`: two jobs, one after the other |
| 50002787 junior clubs | `--paid` | `주니어 골프채` |
| 50002670 women's iron sets | `--paid-variants` (its pilot, 2026-11-15) | `여성 골프 아이언 세트` |
| 50002783 wedge sets | `--paid-variants` (its pilots, 2026-11-15/16) | `골프 웨지 세트` |
| 50002784 chippers | `--paid-variants` (the owner, 2026-11-18: paid add-ons off for the category) | `골프 치퍼` |
| 50001740 BOA spikeless golf shoes (2026-11-25, DRAFT until reviewed) | `--paid-variants` | both sections in one job (the owner 2026-11-25): `보아 스파이크리스 골프화`, no `--leaf` (placement splits by gender and sizes); one gender's depth: `남성 보아 스파이크리스 골프화` `--leaf mens-boa-spikeless-shoes`, `여성 보아 스파이크리스 골프화` `--leaf womens-boa-spikeless-shoes` (the probes' decision.md) |

- N -> `--count N`; no N or "до конца" -> no `--count` (to the listing's end); "без публикации" -> no `--publish`
  and no `--describe`. `--dedupe on` is the default: no flag (the owner's yes after
  the W7 pilot, 2026-11-17: [Duplicates](#duplicates)). Another category: read its latest `job.json` under
  `scripts/output/jobs/` for the flags, or ask.
- `--draft` (2026-11-16) when the owner wants to decide the activation after the lens review (a reviewed
  category's new products go DRAFT; see Draft first). The four categories above are marked `reviewed=True` in
  `transform_shops.py` (2026-11-16): ACTIVE unless `--draft`. A category not marked reviewed (every new one; check
  `transform_shops.py`) publishes DRAFT anyway: say so to the owner before the start.
- Before: `curl -s localhost:8000/health` shows `"extension": "connected"`; `job.py status` shows no running job
  (no other runner of the shop).
- Run it in the background and watch the log: report to the owner every 20 products published, and at once on a
  `STOP`, a captcha, a listing tab reopen or a long network wait (`network down ... try N in S s` past a few tries).
  A pending captcha is not in the job's log (it prints only after the wait expired): run
  `.venv/bin/python scripts/captcha_watch.py` beside the job (or `--once`); see the table's captcha row.
  The table "What stops, and who acts" says what each one means.
- The old mode (`new` + `run`, below) only when the owner says "старым методом" or the run needs 2+ queries at once.

## 1. Before

- Server running (`.venv/bin/python server/run.py`), `/health` shows `extension: connected` (Chrome open with the
  adapter), `SHOP_STORE` set, the category has a row in `category_measures.json` (no row: ask the owner).
- No other job, listing or description_images run at the same time (one Chrome, one OCR lock per shop):
  `job.py status` shows no running job.
- For translation: `scripts/translate_keys.py check` shows the keys (SETUP.md); `run` stops at once without them.
- The shop's lock (2026-11-16, `shop_files.py`): `run`, `scroll` and `refresh` hold it for their whole life, so a
  second runner of the same shop, and by hand `run_transform.py`, `translate.py` (also `--offline`), `placement.py`,
  `publish.py` (sending), `describe.py` (with a model), `reprice.py --apply`, `description_images.py` and
  `store_diff.py --adopt`, are refused at once: `stop: <shop> is busy: job.py run <id> (pid N, since T): wait for it
  (job.py status) or stop it`. Free meanwhile: `status`, `new`, the lenses, `review_grid.py`, `dedupe.py --report`,
  `store_diff.py`, `publish.py --dry-run` / `--withdraw` / `--restore`, `run_transform.py --verify`. The lock goes
  with the process (kill -9 too): no stale lock to clear.

## 2. Start

**`scroll`** (the owner 2026-11-14; the default for one query), in the background (the shorthand's command, log in
`scripts/output/jobs/_scroll-logs/`, `mkdir -p` it):

```sh
.venv/bin/python -u scripts/job.py scroll --query "남성 골프채 풀세트" --category 50002788 --count 100 --paid
.venv/bin/python scripts/job.py status --json
```

No snapshot and no search per product: the server holds one listing tab open (`/listing-tabs`,
server/docs/EXTENSION.md) and the job takes it batch by batch, in Naver's 리뷰 많은순 order (a category that feeds several sections: `--leaf <section>` picks its required words, e.g. 50002796 `mens-fall-long-sleeve-tops`, 2026-11-22; none: the category's `default_leaf`; 2026-11-21: a job of 점퍼 50002798 takes 재킷 50002799 rows too and the other way
round, `listing_title_rules.json` `together`, one shop section; the owner 2026-11-21:
the best cards come first; a job begun before that date resumes in this order too, its done products skipped). Each batch is screened like `new`'s rows (every row
left out is appended to the job's `screened.jsonl`: at, batch, product_id, name, reason; the audit of the
leave-outs; an ad card is not clicked, reason `ad`: its link is Naver's ad redirect, the product is taken when it
comes as an ordinary card, else `new` + `run` reach it by its name), every row taken goes into `listing.jsonl` and
through the same stages at once, its page opened by a click on its card in that tab; then the next batch, until
the listing's end (`has_more` false) or `--count` products at the final stage. Products with a stage left
(collected to translated, failed once) are taken on without the tab, when the job starts and after the listing's
end. While the tab is open, `/products/specs` and `POST /listings` answer 409. `run` and `refresh` refuse a scroll
job (`scroll --job` resumes it); one query a job (a second query: another job).

**The old mode, `new` + `run`** (the owner's "старым методом", or 2+ queries):

```sh
.venv/bin/python scripts/job.py new --query "남성 골프채 풀세트" --query "여성 골프채 풀세트" --category 50002788 \
    --count 40 --paid                     # once: the listing, screened, saved as the job's snapshot
.venv/bin/python -u scripts/job.py run    # in the background; one line per product; --items N for a few
.venv/bin/python scripts/job.py status [--json]
.venv/bin/python scripts/job.py refresh --more 50  # by hand: the listings read deeper, new products appended
```

The browser stays on the job's search tab (the server searches the next product in it and closes the product tab).

## 3. Watch

Start the runner in the background and wait for it. The cadence (the owner, 2026-11-14): report to the owner every
20 products published, briefly, and at once on a `STOP`, a captcha, a listing tab reopen or a long network wait; no
detail hunting in the reports. Read `status --json` (stages per product, closed ones with why, held ones with their
codes, the last stop, the next product, `running`: the product and stage of this moment, with the runner's pid),
not the logs.

The watcher is `job.py watch` (2026-11-16, the owner's five tools; `job_report.py`): it reads `events.jsonl` every
10 s, takes no lock, never starts or restarts a runner, and returns with an exit code that says what to tell the
owner. Run it in the background, relay its one line, run it again with the `--from N` its line ends with
(`next --from N`; `--json`: "seen"), so what was logged after the event that ended it (a wait in the same read as a
published, a multiple of `--every` passed between two watches) is reported by the next one; no hand-made polling loop.

```sh
.venv/bin/python scripts/job.py watch --job <id> --every 20              # the first watch; one line on exit
.venv/bin/python scripts/job.py watch --job <id> --every 20 --from <N>   # each next one: N from the last line
.venv/bin/python scripts/job.py report --job <id>                        # what the job did so far (below)
```

| Exit | Seen | You |
|---|---|---|
| 0 | the job's published count crossed a multiple of `--every` | the brief report (`job.py report`), watch again |
| 3 | a `stop` event | the table below; tell the owner |
| 4 | `waiting` (server, extension) or a network wait at try 3+ | tell the owner (the table below) |
| 5 | `captcha_again` | relay it at once; a pending captcha is `captcha_watch.py`'s, not in the log |
| 6 | `reopen` (scroll: the listing tab reopened) | a brief line; watch again |
| 7 | `done` (also: the job was done when the watch started) | section 5 |
| 8 | no runner (gone after it was seen, or none within 60 s) | `job.py status`: a stop without an event is `recover-state` |
| 9 | `--timeout S` passed | watch again |
| 1 / 2 | a broken `events.jsonl` (the file and line named) / usage, no such job, a `--from` past the events | `recover-state` / the command |

`job.py report [--job ID] [--event E] [--since T] [--table F|-] [--json]` reads a job's events (`--job` left out: the
latest): `section<TAB>name<TAB>value` lines: the job, the event counts, the `not_taken` / `deferred` / `failed`
reasons by code (`duplicate_of`, `placement held: single_only`, ...), the held codes, the model cost, the stops and
waits. How to read them for the owner:

- `job goal published` is the job's setting (the stage it takes a product to), not an outcome;
- `event published N` counts publications, drafts and live alike (`shop_view.py query <shop> --job <id> --event
  published --fields key,state,handle,title` says which, with the titles);
- `held <code> N`: products this job prepared as held, by their last prepare's code; `not_taken <reason> N`: products
  the job did not take, by reason (`placement held: single_only` is the placement's hold, not the prepare's), so the
  two count different products and may differ for one code;
- a review due is not an event: `job.py status` prints `review due` (section Draft first).

`--table F` writes one row a product (key, last event, status, reason, held, handle, events, first, last; `-` to
stdout). `job.py where <ref>` lists one product's events across every job (and the screen's leave-outs of its product
id), oldest first: the ref is a key, a product id, a handle or a link; a product id no shop file knows is still found
in the events.

What the log says:

- a line when a product starts, one when it is done (with its stage times);
- scroll: one `batch N: R rows, T to take (listing total ..., has_more ...)` line per batch, then the product lines;
- every 10 products (`REPORT_EVERY`) a `== progress:` line: prepared of the target, ready / held / closed / failed,
  time a product, time left, and `; N drafts await the review` for drafts; a watcher can relay it to the owner;
- at the end: done, with how many were taken of the listing's `total` (scroll) and how many were not read (their
  card did not come again after a lost tab): the other mode can take those.

When `run` or `scroll` stops (exit 3) or finishes (`done`), the owner is told (2026-11-16, `scripts/notify.py`):
`job_stop` with the reason and the command that resumes, or `job_done`, to `NAVER_NOTIFY_WEBHOOK` when set, else a
macOS notification. Nothing for a refusal (2), Ctrl+C (130) or a run cut by `--items`. Still relay a stop yourself.

### A product's done line

- **Prepare** (2026-11-16): the transform still prepares the whole shop after each product, through the prepare
  cache (TRANSFORM.md, The prepare cache): about 5 s at 2,444 products; the `prepared` event carries `cache_miss`, 1 a
  product. The whole shop once (about 30 s) after any edit of `scripts/*.py` or the rules: expected. `cache_miss`
  equal to the whole shop on every product: another process with other code prepares the same shop; stop it,
  restart the job.
- **Translation**: the line ends with `translated (N calls, $cost)`. A product the model could not translate is
  `failed` (stage translate, the problems in the event) and is tried again after the fresh ones; every provider
  down: the product is tried again with growing waits (up to 2 h), then the run stops (`run` again resumes; nothing
  is asked twice). A line `dictionaries: a backup is due` (at done and in `status`): tell the owner;
  `translation_dicts.py status` lists the entries, the owner backs them up.
- **Description** (`new --publish --describe`, the owner 2026-11-10): before the product is sent the line says
  `described (ok)`, `described (trimmed, N cut)` or `described (fallback)` (the answer failed the checks and the
  description is the title as one sentence: tell the owner how many). No provider answering stops the run. The cuts,
  the origin decisions and the conflicts are in `shops/<shop>/translation/descriptions.jsonl`.
- **Publication** (`new --publish`): the line ends with `published <handle> $<price> <admin link>` (`$<min>-<max>`
  when the variants differ; the shop's price rule: [PRICE.md](PRICE.md) "The price"), or `published (draft)
  <handle>` (Draft first). A product Shopify refused (userErrors, a file not ready) is `failed` (stage publish) and
  tried again; one placement could not place, or held, is `not_taken` `not ready to publish (<gate>)`, the gate it
  failed: `withdrawn (<ledger reason>)`, `prepared <status> [codes]`, `translation <status>` or `placement <status>:
  <reason>` (`publish.Shop.not_ready`, 2026-11-18; tell the owner). A product the shop withdrew (`replaced_by:`, a
  `hold:`, the owner) is done for the job: never taken again by the drain, not counted toward `--count`; a refused
  token or a missing scope stops the run. A product that cannot be priced (a variant without a box, a box over the
  tariff's 50 kg) is not sent: `publish held: variant <sku>: <why>` (`failed`, stage publish); tell the owner.
- **Duplicates**: `duplicate_of`, `replaces ...`, `kept: <why>`: [DEDUPE.md](DEDUPE.md#what-a-jobs-events-mean-and-what-you-do).

### What stops, and who acts

| Seen | What the job did | You |
|---|---|---|
| `STOP ... wall:` (ban page, login gate twice, a captcha not answered 6 times), or `STOP ... 502 ... blocked the request` (after the client's two retries, 10 s and 30 s) | stopped, nothing marked | tell the owner; resume only after they say so, with a small count ([4. Stop and resume](#4-stop-and-resume)) |
| a pending captcha: `captcha_watch: CAPTCHA #<n> at <step>: <question> ...` (`scripts/captcha_watch.py`, `GET /captcha`, or the server log's `ext-listing: CAPTCHA ...`); nothing in the job's log yet | waits `NAVER_CAPTCHA_WAIT_S` (600 s) for the owner to answer it in Chrome | relay the question to the owner at once; never answer it (server/docs/EXTENSION.md, Effects and limits, Captcha) |
| `a captcha was not answered in time` | reads again: the owner is asked again (up to 6 times) | relay it to the owner |
| `network down (...): try N in S s` (Shopify or every model provider unreachable) | tries the product again after ~30 s, doubled up to 15 min; after 2 h the run stops | nothing; a `STOP` after it: tell the owner, `run` once the network is back |
| `waiting up to 15 min for the server and the extension` | waits, then goes on by itself | ask the owner to open Chrome / start the server |
| `STOP ... for 15 min` (they did not come back) | stopped | once they are back, `run` |
| `the snapshot is used up ... reading the listings deeper` | reads the listings again with twice the batches, adds new products (`new --all`: every new one, until the listings end; then done) | nothing |
| `STOP at <key>: two products in a row partial for '<reason>'` (RunStopped) | stopped; both products deferred | a collector defect: investigate, report; do not edit code during the job. `api_500` / `api_502` / `api_400`: the server answered that status (skill `api-error-triage`; the server's terminal prints `api: <status> <path> (<label>): ...`) |
| `failed` (a 503 `naver error page:` or `adapter error:` still there after 2 retries, 120 s apart; the extension dropping in the middle of a read lands here, not in the 15-min wait) | the next product; tried again at the end | nothing; twice failed: closed |
| `not_taken` / `deferred` | the next product | nothing; a defer is lifted only by the owner (`deferred_log.py allow`) |
| scroll: `the listing tab is gone after batch N (...): a new one in S s` (410: tab closed, login gate, server restart, a card that opened in the listing; or the connection lost during `next`) | waits 30-60 s, opens a new tab from the top, done products skipped; event `reopen` | nothing |
| scroll: `STOP: the listing tab lost 3 times in 60 min` | stopped (at most 2 reopens an hour) | tell the owner; `scroll --job <id>` once they say so |
| scroll: `STOP: listing tab: ... wall: ... stalled` (no batch while `has_more` was true) or `refused` | stopped: a stall is not the listing's end | tell the owner; `scroll --job <id>` only after they say so |
| scroll: `done (the listing's end)` with `has_more false` | the last batch read; no scroll after it | nothing; `left` products: the other mode, on the owner's word |
| `adapter busy ... waiting 30 s` with no other job running, or scroll's `the listing tab <id> was not closed` | waits 30 s, 12 times, then stops: a dead scroll job may hold the adapter (no idle timer; the 409 names `listing tab <id>`, so does that job's `job.json` `tab`) | when no `job.py scroll` runs: `curl -X DELETE localhost:8000/listing-tabs/<id>` (or restart the server) |
| `failed (unexpected): <Type>: <message> @ <file>:<line>` (a traceback before it) | the product is failed (stage `unexpected`), the next one; tried again at the end, twice failed: closed | report the line and the traceback (a code defect); do not edit code during the job |
| `STOP: 3 products in a row failed unexpectedly (the last: ...)` or `STOP: unexpected: ...` | stopped | a code defect: report it with the traceback; `run` again only after it is fixed |
| `stop: <shop> is busy: <holder> ...` (`run`, `scroll`, `refresh`, or a hand command) | refused at once, nothing written, exit 2 | another runner holds the shop: `job.py status`; wait for it or stop it, never start a second |
| `STOP ... LedgerError: <path>:<n>: not a JSON line` (a broken line in the ledger, a job's listing, prepared / translated / placements) | stopped, nothing marked | tell the owner the file and line; a rebuilt file: the command the message names (when no job runs); the ledger or a listing: fixed by hand on the owner's word, then `run` again |
| `held` codes in status | the product is prepared as held | read the codes ([TRANSFORM.md](TRANSFORM.md#held-codes) "Held codes"); report |
| `review due: N drafts ...` (draft first) | goes on; the drafts are not live | the skill `visual-review` with the printed commands; report; activate only on the owner's word (Draft first) |
| `sweep due: since the last sweep (<time>): a commit to the build code <time>, the live dictionaries <time>, job <id> done <time> (skill sweep)` or `sweep due: no sweep run yet (skill sweep)` / `no store part yet` (status only; `--json` key `sweep_due`; not printed while a runner holds the shop) | nothing: a hint, read only | after the job, once the shop is free: the skill `sweep`, read the report, tell the owner ([SWEEP.md](SWEEP.md), "When") |

`run` in this table means the resume command of the job's mode: `run` (old mode) or `scroll --job <id>` (scroll),
section 4.

A captcha is answered by the owner in Chrome while the read waits; a login page is reset by the server
(naver.com again), never waited for. The owner learns of it from the notification (`server/notify.py`); you, from
`scripts/captcha_watch.py`.

## 4. Stop and resume

- A product an earlier job prepared, of a category that reads description images, with no sidecar of its current
  collection goes through the images before it is published (2026-11-17, the wedge pilot: 20 such products went
  out with the category's default package, note `description_images_missing`); one in the store is never sent back.
- Resume: `job.py run` (old mode) or `job.py scroll --job <id>` (scroll: the listing from the top, done products
  skipped, ~20-40 s a done batch) after any stop: nothing is lost, done products are not read again. After a `STOP`
  the table above says whether the owner must clear it first. A runner killed without a `STOP` (kill -9, a power
  cut) shows `no runner`, `finished: False` and no new stop event: resume the same way (skill `recover-state`).
- After a captcha or a ban in the last 24 h: a small count, up to 50 ([Two ways to run a job](#two-ways-to-run-a-job-which-one-when)).
  `scroll --job <id>` keeps the job's own count (it reads no other flag): with more than 50 left, ask the owner
  first. The old mode: `job.py run --items 50`.
- Stop a runner: its pid is in `job.py status` (`running (pid N)`: the pid is alive and is the runner that wrote
  `now.json`: its start time matches, so a pid reused after a reboot shows `no runner`, 2026-11-16; skill `recover-state`). A scroll job closes its listing tab (DELETE)
  however the run ends, SIGTERM and Ctrl+C included. The shop's lock goes with the process.
- A running job keeps the code it loaded: restart it (stop, `run` again) after a code change.
- Prepared output looks stale, or before a release (a code change that should not change the output: compare the
  sha256 of `prepared/products.jsonl` before and after, or `store_diff.py`; `--verify` checks the records against
  the code they were made with): `run_transform.py <shop> --verify` (reads only, allowed while a job runs) must say
  `identical`; a difference: tell the owner the product and field it names.

## 5. After

1. A job of a category not marked reviewed (or made with `--draft`): `job.py status --job <id>` prints the review
   block; see Draft first below. Activation and withdrawals: [OWNER_RULES.md](OWNER_RULES.md), skill
   `store-actions`.
2. `.venv/bin/python scripts/placement.py <shop>` (a job without `--publish`: then `publish.py <shop>`, rule 1 of
   OWNER_RULES.md for products already in the store), then read `shops/<shop>/placement/report.txt`: the `unresolved`
   products (the attribute unknown or in conflict) and the `no_profile` ones go to the owner with their evidence;
   never pick a section for them. A new category or split: [PLACEMENT.md](PLACEMENT.md).
3. A look by eye (the owner, 2026-11-15; run by hand, never by itself): `.venv/bin/python scripts/review_grid.py
   <shop> --job <id>` (or `--category <id>`) writes numbered sheets of each published product's first photo
   (`sheet1.jpg` ..., 60 a sheet) and `index.tsv` (number, key, product id, title, handle, admin link) into the job's
   `grid/`. Read the sheets in one go (they are small JPGs), list what is not the section's product by number, show
   the owner; the owner decides what is withdrawn (`publish.py <shop> --withdraw <key> --reason ...`). Read only,
   offline.
4. Then the lenses (scripts/LENSES.md, skill `visual-review`): `lens.py price <shop> --category <id>` (singles and
   accessories at the cheap end), `lens.py held <shop> --job <id>` when many were prepared but not published (each
   hold beside its reason, a duplicate beside its match), `lens.py brand <shop> --source none [--category <id>]` for
   the products under the shop's own name.
5. `.venv/bin/python scripts/review_suspects.py <shop> [--job <id>]` (read only, offline; the owner, 2026-11-14: the
   screen of 50002788 is lenient in both ways to run a job, so what is doubtful is published and reviewed
   afterwards) lists the published products of the category (`--category`, default 50002788; `--job`: only that
   job's keys) that may not be a full set, each with its key, the store's product id and handle, today's price and
   the reasons: `single_club` (the transform's single-club test, 아이언개수 단품 / 총클럽개수 1개, a folding club),
   `few_clubs` (2-3 clubs: 2종 / 3종 / 2pcs / 3pcs, 총클럽개수 2-3개), `used` (중고, not 중고급), `junior` (주니어,
   어린이, kids, ...: no title rule leaves a junior set out, no other job collects the ones listed here) and
   `accessory` (the words of that title rule, its `unless` not applied, and golf balls). It prints the table and
   writes `suspects.csv` next to the job (else `shops/<shop>/review_suspects-<category>.csv`); give it to the owner,
   and change nothing in the store: a withdrawal is the owner's (`publish.py --withdraw`). The rows the screen left
   out are in the job's `screened.jsonl`.
6. Duplicates of the run: `dedupe.py --pairs <shop> --job <id>` ([DEDUPE.md](DEDUPE.md)).
   Then `.venv/bin/python scripts/sweep.py <shop>`: the job's new brands and terms reach old products; its groups go
   to the owner, nothing is resent unasked ([SWEEP.md](SWEEP.md), skill `sweep`).
7. The owner's summary: `job.py report --job <id>` (counts, reasons by code, cost; how to read it: 3. Watch); the
   published list with titles and draft / active: `shop_view.py query <shop> --job <id> --event published --fields
   key,state,handle,title`; the products of one outcome as a keys file for the next command:
   `job.py report --job <id> --event not_taken --table -` or
   `shop_view.py query <shop> --job <id> --where prepared=held --keys-out held.txt` (OPERATIONS.md, Reading the shop
   by hand); an action on them goes through `--keys-file` / `--job ID --event E` (skill `store-actions`).

### Draft first (a category not yet reviewed; the owner, 2026-11-16)

A job with `--draft` (with `--publish`; 2026-11-16, the owner: a pilot in a reviewed category he activates after the
lens review) creates its new products DRAFT in any category, the rest below the same.
A Naver category not marked `reviewed=True` in `transform_shops.py` (every new one) is published DRAFT: on every
sales channel, but not shown until activated. The ledger says `published` (`store_status: DRAFT`), so dedupe, the
lenses, `--count` and the job's stages count drafts as published: a pilot of 20 ends with 20 drafts, none live.
What the job prints: `draft first: ...` when it is made; `published (draft) <handle>` in a product's done line;
`; N drafts await the review` on the progress line; from 20 drafts (`REVIEW_AFTER`), on the progress line, at done
and in `status`: the block `review due: ...` with the lens commands (`status --json`: key `review`).

You: run the skill `visual-review` with exactly those commands, report the findings to the owner, and wait. On the
owner's word only: withdraw the wrong ones (`publish.py <shop> --withdraw <key> --reason ...`), then
`job.py activate --job <id>` (`--dry-run` first lists them), then run the old copies' `--withdraw` lines it prints.
`reviewed=True` for the category is a commit on the owner's word after the pilot (a dated comment); a running
`scroll` read `transform_shops` at its start, so the mark acts after a restart.

## Duplicates

`new` and `scroll` take `--dedupe on|log|off`, `on` by default (the owner, 2026-11-15): right after collect, a
product sold by another store too is closed (`not_taken: duplicate_of:<key>`) unless it is strictly better (store
grade, then reviews), and a better one replaces the old product once published. One sharing a live product's UPC
with no confirmed match (2026-11-17) is published as a draft and held (`held_same_upc`, `hold: copy of live <key>`):
list it for the owner. One of its Naver catalog or style code (2026-11-20, `same_item`) is parked once collected
(`not_taken: parked_same_item:<key>`, raw data only): status and the done line print `parked same-item candidates:
N`, review each pair (skill visual-review), report copy / versions / doubtful, and on the owner's word
`job.py release --job <id> <key>` the versions (the next `scroll --job` takes them on). The W7 pilot (2026-11-17, `--dedupe log`, 20 wedge sets published as drafts): every one was a
copy of a live product and `on` would have closed all 20; the owner said yes, `on` stays the default. The rule, the events, `--pairs`, `--report` and the pilots: [DEDUPE.md](DEDUPE.md).

## Flags

- `--all` instead of `--count` (`new`, the owner, 2026-11-12): no count, the job goes on until the listings have no
  more products (each used-up snapshot: the listings read deeper, no cap of our own: the server takes at most 200
  batches a query and rests between batches, EXTENSION.md).
- Paid choices: a job made without `--paid` (the owner's pilot, 2026-11-09) collects and prepares only the variants
  and add-ons that cost nothing extra; `--paid` takes them too. `--paid-variants` (the owner, 2026-11-11) takes the
  paid variants but no paid add-on. A job's choice holds for its own products only, whoever prepares the shop again
  (a job, or `run_transform.py` by hand): `run_transform.paid_choices` reads it from the jobs' files, the latest job
  of a product decides, and every other product takes only what costs nothing extra (2026-11-11: a `--paid` job of
  50002787 had turned the paid variants of 101 published full sets on).
- `--draft`: Draft first above. `--dedupe`: [DEDUPE.md](DEDUPE.md). `--publish`, `--describe`: the done line above.
- Reviews (the server, every job): the server chooses up to 20 (`/products/reviews/selected`); a product with more
  than 8 keeps the 8 that say most of the product (`review_pick`: review_clean's text quality, a full text,
  "helpful" votes, several photos; a purchase story without the product loses; sponsored ones go, a fair low score
  stays, a text repeated word for word is taken once), 3 photos each and 12 in all, before any photo is downloaded
  (the owner, 2026-11-11: 50002787's 19-20 reviews and 20-36 photos a product had doubled its collection time). The
  choice is in the collected line, `reviews.picked`. The per-product collect is `collect_product.collect`, shared
  with example_99.

## Two ways to run a job: which one when

`scroll` is faster to collect and has no `card_not_found` (the measurements: History, below).

- **`scroll`, the default for one query**: no typed search per product (one page load less each, no
  `card_not_found`), no listing burst up front, and it goes to the listing's end by itself (no `--count`). Most worth
  it for a big target (over ~100-200) or a category with look-alike names (the old mode's `card_not_found` over ~2%).
- **`new` + `run`**:
  - 2+ queries alternated (scroll takes one; a second query is a second scroll job);
  - a run that must stop for days and resume exactly where it was (the snapshot is fixed; `scroll --job` walks the
    listing from the top again, ~20-40 s a done batch);
  - given products, the `card_not_found` / `left` of a scroll job among them (`new --exclude-known`, `run --job`);
  - `refresh`;
  - other adapter reads wanted meanwhile (a scroll job holds the adapter until it ends: `/products/specs` and
    `/listings` answer 409).
- **Size**: the first batch's `total`, of the 리뷰 많은순 listing (2026-11-21: 3724 for 여성 골프 바람막이 점퍼, 4878 in the
  default order) (`/products/count` does not predict it: 289 vs 53, 1148 vs 122); to see it
  without a job, one search page load: `curl -X POST "localhost:8000/listing-tabs?query=<urlencoded>"`, read `total`,
  then `curl -X DELETE localhost:8000/listing-tabs/<id>`. A scroll job writes it into `job.json` (`total`). A listing
  whose top is already in the shop is scrolled past at ~10 s a batch (the pilot: 12 batches with 0-3 new products).
- **After a captcha or a ban in the last 24 h**: either mode, only with a small `--count` (up to 50).

### The query: what a listing holds (2026-11-14, 50002788)

A listing is always a search: a Naver category page needs a signed-in Naver account (probed 2026-11-14: the menu
path naver.com -> 쇼핑 -> 카테고리 -> hover -> click lands on nid.naver.com at every level), so it is not used. The
category is the screen's (`--category`): the card's category, which the seller sets. Both kinds of query work in both
ways to run a job; pick by what the run is for:

- **Narrow** ("남성 골프채 풀세트", "여성 골프채 풀세트", a model or brand): a smaller listing, mostly the category's
  real products. 50002788: 4,343 and ~4,000 rows; ~3% of 1,225 published were not sets (single clubs, 2-3 clubs).
  Two genders = two queries: two scroll jobs one after the other, or one `new` with two `--query`.
- **Generic** ("골프채 풀세트"): one listing for both genders, 13,336 rows, reaches sets whose titles name no gender.
  Measured over 126 products (2026-11-14): ~10% not sets (bags, covers, lead tape, ground-golf clubs, a display
  stand; sellers file them under full sets), ~23% left unplaced (gender unknown or in conflict: most of the non-sets,
  and ~13% real sets with no gender: lefty, unisex), 1 non-set published (a club cover). More review after the run.
- Anything doubtful that was published: `review_suspects.py` lists it (see "After").

## Never

The list is in [OWNER_RULES.md](OWNER_RULES.md), "Never", with the other rules that wait for the owner.

## History

- **The iterative way** (the owner, 2026-11-07): one listing, then each product in turn through every built stage
  (collect -> keep as a one-line run -> description images -> prepare) before the next opens; resumable at any
  point, the stage of each product read from the files. Translation, placement and publication are named stages
  (`job.py STAGES`): placement runs on the whole shop before publication (`placement.py`); translation runs per
  product, and in a job made with `--publish` placement and publication too. The owner's decisions (2026-11-07): one
  product per iteration (fewer reads in a burst: less risk of a block); publication goes straight to ACTIVE, right
  after translation; no age limit between collection and publication.
- Changed 2026-11-08: translation is a model API stage (`translate.py`, see TRANSLATION.md, Translation), not the
  session's agent; the description and the images' text are not translated (`describe.py` writes the description
  from them, 2026-11-10).
- Not built on purpose (the owner, 2026-11-08): OCR in parallel with the next collect, an incremental prepare
  (run_transform.run(shop) rebuilt the shop after each product: 1-2 s at 143 products, the pace did not drift over
  100), a guard memory across runs. 2026-11-16: at 2,444 products that rebuild took 30-63 s a product; built since as
  a per-product prepare cache (see TRANSFORM.md, The prepare cache): about 5 s, the steps across products
  still run over the whole shop.
- Checked live (2026-11-08, 50002788, own shops root): 40 sets in 53 min and 100 sets in 146 min, every one prepared
  `ready`, no stop, wait, captcha, login gate or Naver error page; ~80-88 s a product (collect median 52-56 s, page
  read 34-48 s, OCR median 21-22 s, prepare 1-2 s); the search tab reused for every read (`tabs left: 1`). A listing
  of 12 batches (one query) read in 110 s: 583 unique rows, no stall. Captcha, login reset, Naver's error page and a
  lost extension are covered by offline tests only (none came up live).
- `scroll` (the owner, 2026-11-14), the other way to run a job: products clicked from one held listing tab, no
  search per product. From its 100-product pilot (2026-11-14, 50002788, one query) against the old mode's 698
  (2026-11-13): collect 22 s against 51 s a product (median), the whole product ~115 s against ~120 s (translation,
  description and publication do not change), `card_not_found` 0 against 1.8%, captchas and login gates 0 in both,
  no reopen. One category and 100 products: revise when a longer run says otherwise.
- Changed 2026-11-12: `--all`. 2026-11-15: `--dedupe`, `on` the default ([DEDUPE.md](DEDUPE.md), History).
  2026-11-16: draft first (a category not marked reviewed, `transform_shops.CategoryRules.reviewed`, is published
  DRAFT, for the agent's lens review and the owner's activation), the shop's lock, the owner's notice, the prepare
  cache.
- 2026-11-16 (the owner's five tools): `job.py watch` (exit codes for what the owner must hear) in place of hand-made
  watchers, `job.py report` and `job.py where` (`job_report.py`).
