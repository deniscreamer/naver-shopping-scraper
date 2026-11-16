# Operations

Running the scripts, the state backup, the shop's shared files and the conventions. What waits for the owner, and
the Never list: [OWNER_RULES.md](OWNER_RULES.md).

## How to use

| Task | Section |
|---|---|
| Start the server, the entry points and their skills | [Running](#running) |
| Before a commit: the offline checks | [Running](#running) (`scripts/check.sh`) |
| Back up the state (before a risky change, after each release), verify, restore | [Backup](#backup-state_backuppy-the-owner-2026-11-16) |
| Code that writes or reads a shop's files; a `busy` refusal; a `LedgerError` | [Shared files](#shared-files-shop_filespy-2026-11-16) |
| Code that calls the API: typed calls, sequential, cache, status codes, pagination, env, naming, style | [Conventions](#conventions) |
| An error from the API or a job | skill `api-error-triage` |

Commands (repo root), what they print and what you do:

| Command | Prints | You |
|---|---|---|
| `scripts/check.sh` | the tail of each of `server`, `scripts`, `mypy`, then `== results:` with `ok` / `FAILED` per step | non-zero exit: fix the `FAILED` step before the commit |
| `.venv/bin/python scripts/state_backup.py --dry-run` | the files left out (and why), `plan -> <folder>`, each archive's files and sizes, the estimate and the free space; `WARNING: a job is running` | a warning: back up between jobs; then run it without `--dry-run` |
| `.venv/bin/python scripts/state_backup.py` | `writing <archive> ...` per archive, then `for the cloud:` and the files | upload that folder to the cloud by hand; `refused: ...` (exit 2): not enough space, a folder inside the repository, or an archive already there (another `--dest`, or delete it yourself) |
| `.venv/bin/python scripts/state_backup.py --verify <folder>` | `ok` / `FAIL: ...` per archive, then `verify: ok` or `verify: N FAILED` (exit 1) | a failure: make the backup again |
| `.venv/bin/python scripts/state_backup.py --restore <folder> --to <empty folder> [--phase state,...]` | `  <archive>: N files -> <to>` per archive (exit 0); `nothing to restore from <folder> for <phases>` (exit 1); `refused: <to> is not empty` or `refused: <to> is the repository or holds it; ...` (exit 2); `refused: <archive>: missing from <folder>` or `refused: <archive>: sha256 differs from MANIFEST.json` (exit 1) | restore only into an empty (or new) folder outside the repository, never over a working repository; every chosen archive is checked against MANIFEST.json before anything is unpacked; a missing or changed archive: `--verify` the folder, use another copy (the cloud's); then compare and move the folders you need into the repository by hand (stop any job first; the folder's `RESTORE.md`) |
| A command refused with `<tool>: stop: <shop> is busy: <holder>: ...` (exit 2) | another process holds the shop's lock | wait for it (`job.py status`) or stop it; see [Shared files](#shared-files-shop_filespy-2026-11-16) |
| `LedgerError: <path>:<n>: ...` (a job: `STOP ... LedgerError`) | a line of a shop's file is not JSON | fix the line by hand; a rebuilt file: the command that rebuilds it |

## Running

Start the server first, in another terminal (setup, requirements and the adapter: [SETUP.md](../SETUP.md)):

```sh
.venv/bin/python server/run.py          # http://localhost:8000
```

Then the scripts. The entry points, each with its skill:

```sh
.venv/bin/python scripts/job.py status [--json]               # jobs: scroll / new + run (skill run-a-job)
.venv/bin/python scripts/lens.py <lens> <shop> [scope]         # products by eye, read only (skill visual-review)
.venv/bin/python scripts/publish.py <shop> --dry-run           # payloads, nothing sent (skill publish)
.venv/bin/python scripts/reprice.py <shop>                     # a dry-run price table (skill price)
.venv/bin/python scripts/state_backup.py --dry-run             # the state backup, below
.venv/bin/python scripts/smoke_endpoints.py                    # the live smoke of the API (networked)
```

**Checks before a commit** (offline): `scripts/check.sh` runs the server suite, the scripts suite
(`.venv/bin/python -m pytest scripts -q`, not part of the default `pytest` run) and mypy, each in its own process,
prints the three results and exits non-zero when any fails. It is the authority on "the tests pass"; the docs give
no test counts.

## Backup (`state_backup.py`, the owner 2026-11-16)

The data on disk (ledger, translations, prepared, jobs, dictionaries, photos, description images, saved pages) is
in no git and no cloud: back it up before a risky change and after each release, then upload the folder to the
cloud by hand (the script uploads nothing).

```sh
.venv/bin/python scripts/state_backup.py --dry-run            # the plan: archives, files, sizes, what is left out
.venv/bin/python scripts/state_backup.py                      # all five phases -> ~/Desktop/naver-backups/<date>/
.venv/bin/python scripts/state_backup.py --phase state        # one phase (adds to the folder's MANIFEST.json)
.venv/bin/python scripts/state_backup.py --verify ~/Desktop/naver-backups/<date>
.venv/bin/python scripts/state_backup.py --restore ~/Desktop/naver-backups/<date> --to /tmp/restored --phase state
```

Five archives, paths inside relative to the repository root: `01-state` (shops without photos, description images
and `prepare_cache/`; jobs, journal, live dictionaries, `research/`; zstd-19), `02-photos` (`collected/<run>/images/`, zstd-3),
`03-description-images-partNN` (`description_images/cache/<id>/`, parts of at most 4 GB uncompressed, a product never
split, zstd-3), `04-server-pages` (`server/output/`, zstd-19), `05-archive` (the rest of `scripts/output/`, zstd-19).
Text compresses 17-37x at level 19; images are compressed already, so level 3. Left out by name: `.env*`, secret-like
names, `*.part`, `*.lock`, `prepare_cache/`, `__pycache__/`, `.venv/`. A folder inside the repository is refused, an
existing archive is never overwritten, a running job is warned about (back up between jobs).

## Shared files (`shop_files.py`, 2026-11-16)

A shop's files are read and written by a job, by hand commands and by the lenses, often at once. New code that
writes them goes through `shop_files.py`:

- **A rewritten file** (`prepared/products.jsonl`, `translation/translated.jsonl`, `placement/placements.jsonl`, a
  job's `job.json` / `now.json`): `write_atomic(path, text)`: `<path>.<pid>.part` beside it, then a rename. A killed
  process leaves the old file whole (and maybe a `.part`, never read: delete it by hand); a reader never sees half.
- **An append-only file** (the ledger, `files.jsonl`, a job's `events.jsonl` / `listing.jsonl` / `screened.jsonl`,
  `texts.jsonl`, `descriptions.jsonl`, the journal, `lens/reviewed.jsonl`): `append_line(path, *lines)`: one write of
  whole lines; when the file does not end with a line end (a cut-off row, a hand edit), one comes first, so the new
  row stays readable and the fragment becomes a bad line the reader names.
- **Reading**: `read_jsonl(path, tail_ok=False)`: a line that is not JSON is `LedgerError: <path>:<n>: ...` (fix the
  line by hand; a rebuilt file: the command that rebuilds it). Only an append-only file (`tail_ok`) may end in a
  cut-off line: ignored with one warning (the next append turns it into a middle line, named). Strict this way:
  `publish.py`'s reads (the ledger, `files.jsonl`, prepared, translated, placements), `dedupe.ledger`, a job's
  `listing.jsonl` (`Job.rows`, `run_transform.paid_choices`); a job stops on it (`STOP ... LedgerError`). Left
  tolerant on purpose (a lost row costs one retry or one question again): a job's `events.jsonl` (the job, the
  lenses, `review_grid`, `dedupe --pairs`), `texts.jsonl`, `descriptions.jsonl`, the journal.
- **The shop's lock**: a command that rewrites a shop's shared files or sends its products takes
  `<shops_root>/.<shop>.lock` (`fcntl.flock`) in its `main()` for its whole life and refuses at once, never waits,
  when another process holds it: `<tool>: stop: <shop> is busy: <holder>: wait for it (job.py status) or stop it`,
  exit 2. Taken by `job.py run` / `scroll` (before a new job's folder) / `refresh`, `run_transform.py` (not
  `--verify`), `translate.py` (also `--offline`), `placement.py`, `publish.py` when it sends, `describe.py` with a
  model,
  `reprice.py --apply`, `description_images.py`, `store_diff.py --adopt`. Not by the library functions (`run`,
  `publish_one`): a job calls them in its own process under its own lock. Free: `job.py status` / `new`, the lenses,
  reports, `store_diff.py`, `publish.py --dry-run` / `--withdraw` / `--restore` / `--activate`, `job.py activate`. The kernel frees it when the
  process dies (kill -9 too). The lock is advisory: an editor or a heredoc into a `.jsonl` is not stopped, so a
  new writer of shared files uses `shop_files` and a new sending command takes the lock.

## Conventions

- **Typed calls.** Use the typed client methods (`api.search()`, `api.product_details()`, `api.listing()`, ...) and
  the shapes in `naver_types.py`; guard every `X | None` field (`product["reviews"]`, `product["variants"]`, names).
  Run mypy on what you write (see COLLECT.md, Response types). Rules: server/docs/DEVELOPMENT_RULES.md R-TYPE.
- **Sequential by default.** The server keeps one Chrome per proxy
  (`config.NAVER_SHOPPING_BROWSER_SLOTS = 1`), and box calls serialize on that
  Chrome's lock. Parallel calls just queue up inside the server (cheroot has
  16 threads) and make blocks more likely. Add a pause (`--delay`) for long
  runs.
- **Lean on the server cache.** A repeat call within the TTL is free. TTLs are
  in `server/naver_shopping/cache_config.py`, from 2 h for search to 7 d for
  the category list. `/products/details` and `/products/reviews` share one
  cached product record (`api._record`), so calling reviews after details
  costs no extra fetch.
- **Status handling** (`routes.call`):
  - `404`: the entity does not exist. Skip it and log it.
  - `400`: the input is wrong. Fix the script; do not retry.
  - `502`: blocked or an upstream failure. Back off. The client retries twice
    (10 s, 30 s).
  - `500`: a server parser bug. Report it.
  - Read timeout: the server is still working. Do not retry blindly, because
    the retry would queue duplicate work behind the same Chrome.
  - Connection errors: the client retries only a failure to open the
    connection (`ConnectTimeout`, or refused / DNS). requests also raises
    `ConnectionError` for a dropped connection or a read timeout mid-body,
    after the request was sent; those are raised, not retried.
- **Pagination.** Use `client.pages()`. It increments `page` until `next` is
  null or `results` is empty, stops at the schema cap (500 for
  `/products/reviews`, 25 for `/keywords/rank`, also under the
  `/naver-shopping/` prefix), and treats a 400 whose `errors` name `page` as
  the end once a page was yielded; any other 400 raises. It never follows
  the absolute `next` URL. The server builds that URL from its own request
  host, which is wrong behind a proxy.
- **Config from env, no secrets in files.**
  - `NAVER_API_URL` (default `http://localhost:8000`)
  - `NAVER_API_READ_TIMEOUT` (default 900 s; the connect timeout is 5 s)
- **Naming.** One script per job, with an argparse CLI. Module names must not
  collide with server top-level modules (`config`, `cache`, `routes`, `main`,
  `run`, `browser_client`, ...), because pytest puts `server/` on `sys.path`.
- **Style.** Follow the server's style:
  - a module docstring that says why;
  - `# ---- section ----` banners;
  - `print("<script>: ...")` with a prefix;
  - type hints in new and changed code, checked by mypy (R-TYPE-5; the server stays untyped, R-STYLE-3).

## History

- 2026-11-16: split from scripts/README.md (history: `git log --follow scripts/README.md`); the backup
  (`state_backup.py`, the owner) and the shared files (`shop_files.py`) added the same day.
