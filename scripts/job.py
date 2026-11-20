"""A job: one shop, one listing query, one product at a time from the listing to prepared (and, later, translated
and published; placement.py puts the whole shop into its sections before publication), resumable at any point. The agent that runs it reads scripts/JOB_AGENT.md.

Why one product per iteration (the owner, 2026-11-07): fewer reads in a burst, so less risk of a Naver block, and
every product is done (collected, its description images read, prepared) before the next one opens; a stop loses
nothing. The browser side (server, ext_product): the job's search tab stays open, the next product is searched in
it, the product tab of the previous read is closed; a login gate is reset from naver.com; a captcha waits for the
owner as always.

    .venv/bin/python scripts/job.py new --query "남성 골프채 풀세트" --category 50002788 [--count 40 | --all] [--batches 2]
                                        [--paid | --paid-variants] [--exclude-known] [--shops-root DIR] [--publish [--describe]]
                                        [--dedupe off|log|on]
    .venv/bin/python scripts/job.py run [--job ID] [--items N]
    .venv/bin/python scripts/job.py scroll --query "남성 골프채 풀세트" --category 50002788 [--count 100] [--paid | ...]
    .venv/bin/python scripts/job.py scroll --job ID          # resume a scroll job (its listing from the top)
    .venv/bin/python scripts/job.py status [--job ID] [--json]
    .venv/bin/python scripts/job.py activate --job ID [--dry-run]   # the job's drafts live, on the owner's word
    .venv/bin/python scripts/job.py report [--job ID] [--event E] [--since T] [--table out.tsv] [--json]
    .venv/bin/python scripts/job.py where <ref> [--shop S]          # one product's events across the jobs
    .venv/bin/python scripts/job.py watch [--job ID] [--every 20] [--timeout S]   # returns when the owner must hear
                                                                    # (job_report.py: the outputs and exit codes)

Files, scripts/output/jobs/<job id>/:

    job.json       shop, category, query(s), settings, the shops root, the listing job(s) read (shop_types.JobMeta)
    listing.jsonl  the screened snapshot in listing order (row + key)
    screened.jsonl scroll: every row the screen left out, append-only (at, batch, product_id, name, reason: the
                   Screen's code, or known), once a product a run, for the audit of the leave-outs
    events.jsonl   what no other file records, append-only: not_taken / deferred / failed / stop / done, with time
    tmp/           a product's line and photos until they are kept (keep_run), then removed

A product's stage is read from the files, not from the log: collected = its key in the shop's kept runs
(run_transform.latest_lines); images = the category's switch off, or a current sidecar (description_images.current);
prepared = its key in prepared/products.jsonl, and its images read as above unless it is in the store (2026-11-17:
an earlier job's prepared product with no sidecar went out with the default package); translated = its key `translated` (or `held`: the transform held it,
nothing to translate) in translation/translated.jsonl. A job created with translation (`new`, the default since
2026-11-08; `--no-translate` leaves it out) takes each product to translated: right after it is prepared, through
translate.py (only that product goes to the model; the chain and its fallback as there). A product the model could
not translate is `failed` (tried again after the fresh ones, MAX_FAILS times); every provider down: tried again with growing waits, then the run stops
(`run` again resumes). A job made with `--publish` takes each translated product on: placement.py over the
whole shop (offline), then publish.py for this product (Shopify, ACTIVE, or DRAFT for a category not marked reviewed:
transform_shops.reviewed, 2026-11-16); published = its key in
publish/published.jsonl, or withdrawn there (replaced_by, a hold, the owner: done, not counted toward --count;
2026-11-18). A product not ready to publish (withdrawn, held, not placed) is `not_taken` with the gate it failed
(publish.Shop.not_ready); a refused write is
`failed` (tried again); a refused token or scope stops the run. With `--describe` too (the owner, 2026-11-10) the
product's description is written right before it is sent (describe.py, one model request; the answer is checked
and cut by the script, never a reason to hold the product); no provider answering stops the run.

`new --all` (the owner, 2026-11-12) has no count: whenever `run` uses up the snapshot it reads the listings deeper
the same way (up to MAX_BATCHES_ALL) and takes every new product, until the listings end (has_more false) or
stop; then the job is done.

`new --count N` reads the listings deeper (batches doubled, up to MAX_BATCHES; a listing is read from the top
every time) until N products pass the screen; when `run` uses up the snapshot with fewer than N prepared, it
reads them deeper again and appends the new products (`refresh` does that by hand). Probed 2026-11-08: 12 batches
of one query in 110 s, 583 unique rows, no stall. Each product prints a start line and a done line (stage
times), and every REPORT_EVERY products a `== progress:` line; now.json says what the runner does (status).

Waits and stops: the network down (a ConnectionError / Timeout, Shopify's "request failed", every model
provider down for translate or describe): the product is tried again from its stage, waits NET_WAIT_S doubled
up to NET_MAX_WAIT_S (tenacity, net_retry), for NET_GIVE_UP_S, then the run stops. 409 (adapter busy): 30 s, up to 12 times. The extension not connected or the API server not
answering: /health polled RECONNECT_S (15 min), then on. A captcha not answered in time (GET /captcha
timed_out, not a ban): read again, the owner asked again, CAPTCHA_TRIES times. A 503 "naver error page:" / "adapter error:" (ENDPOINTS):
120 s, 2 more tries, then the product is `failed` and the run goes on (a failed product is tried again after the
fresh ones, at most MAX_FAILS times). Anything else that stops the source (a wall, a refused CDN, the extension not
connected, the server down) stops the run: `run` again resumes. Two products in a row partial for the same reason
stop the run (collect_guard). An unexpected error in a product (a code defect: KeyError, TypeError ...; 2026-11-16)
is `failed` at stage `unexpected` (the reason with the innermost file:line, the traceback printed), the run goes on;
UNEXPECTED_STOP (3) in a row, any products, stop it. One outside a product (the run's context, the listing loop)
is a `stop` event `unexpected: ...`, exit 3; a broken shop file (LedgerError) stops naming <path>:<n>. No run ends
without an event (but SystemExit and a kill).

`scroll` (the owner, 2026-11-14; the other way to run a job, `new` + `run` unchanged): no snapshot, no search per
product. The server holds one listing tab open (POST /listing-tabs) and hands it out batch by batch (~50 rows);
each batch is screened like `new`'s rows (every row left out, with its reason, appended to screened.jsonl) and every row taken is appended to listing.jsonl and taken through the same
one() at once, its page opened by a click on its card in that tab (ctx["specs"]: the list is virtualized, a batch's
cards leave the page a few batches later), then the next batch, until the listing's end (has_more false) or
`--count` products at the job's final stage. job.json has `mode: scroll`, the listing's size (`total`, the first
batch's: /products/count does not predict it) and the open tab's id (`tab`; free a tab a dead job left with
`curl -X DELETE localhost:8000/listing-tabs/<id>`). A row is skipped only when its product is at the job's final
stage or closed: one cut off mid-read is read again when its card comes. Products with a stage left (collected to
translated, or failed once) are taken on without the tab, when the job starts and at the listing's end. The tab
gone (410: closed, a login gate, the server restarted, a card that opened in the listing itself): a pause, a new
tab from the top, done products skipped, REOPEN_MAX times in REOPEN_WINDOW_S, else the run stops. A captcha not
answered on a product page ("wall: captcha", the tab kept) is read again as above; any other wall stops. SIGTERM
or Ctrl+C closes the tab before the run ends. `run` and `refresh` refuse a scroll job; `scroll --job` resumes it
(its listing walked from the top again, done products skipped).

The shop's lock (2026-11-16, shop_files.py): `run`, `scroll` (before a new job's folder) and `refresh` hold
`<shops_root>/.<shop>.lock` for their whole life; another runner of the shop, or a hand command that rewrites the
shop's files or sends its products, is refused at once (`stop: <shop> is busy: job.py run <id> (pid N, since T)`,
exit 2). `status` and `new` take no lock. When `run` / `scroll` stops (3) or finishes (`done`), main() tells the
owner (tell_owner: scripts/notify.py, NAVER_NOTIFY_WEBHOOK else a macOS notification; the owner, 2026-11-16).

`--dedupe off|log|on` (`new` and `scroll`, the owner 2026-11-15; kept in job.json, read again on resume; on is the
default; off leaves the job as it was and writes no key): right after a product is collected, before its description
images, dedupe.py looks it up in an index built at the run's start (the shop's published and owner-withdrawn products
and the job's own collected ones): the same title key, another store, a price within x2, confirmed by the photos or
the variants. `log`: one event `duplicate_seen` (the would-be decision, the matches and their signals), nothing
else changes. `on`: a confirmed match withdrawn by the owner, or one the candidate is not strictly better than
(grade, then reviews): `not_taken` `duplicate_of_withdrawn:<key>` / `duplicate_of:<key>` (closed: no images, no
translation); strictly better: `duplicate_better {replaces}` and on, and once it is published the old product is
withdrawn (publish.withdraw, DRAFT, reason replaced_by:<new key>) if it is still published and the new product has
no fewer variants (`replaced`, else `replace_skipped`). A title match not confirmed is `duplicate_seen` (not_confirmed).
No confirmed match but the same UPC as a product under dedupe.upc_suspect (2026-11-17): `duplicate_seen` decision
`same_upc:<key>`, taken as usual; under `on` it is published as a draft and held at once (`held_same_upc`: withdrawn,
reason `hold: copy of live <key>, same UPC ...`, OWNER_RULES rule 2), the owner decides; under `log` the event only.
The same Naver catalog or style code (dedupe.same_item, 2026-11-20) is a flag only, never acted on (the owner: not
certain enough): decision `same_item:<key>`, `why` ["catalog <id>" / "code <code>"], the product goes on as usual;
status, the done line and the progress line print the open pairs (same_item_open) for the agent's review, and
`activate` leaves those drafts alone.
A draft (draft first, 2026-11-16) does not replace a live product (`replace_skipped`, "the new one is a draft"):
`activate` prints the withdraw line of the old one.

Draft first (2026-11-16): a publishing job in a category not marked reviewed says so when made; a draft's done
line reads `published (draft) ...`; the progress line adds `N drafts await the review`; from REVIEW_AFTER drafts
(on the progress line), at done and in `status` (and `--json` key `review`) the block `review due` names the skill
visual-review and the lens commands, then the owner's word. The scripts never run a lens.

`activate --job ID [--dry-run]` (draft first, 2026-11-16): the job's products the ledger has as drafts
(store_status DRAFT; a category not marked reviewed in transform_shops) set ACTIVE through publish.activate, on the
owner's word after the lens review; withdrawn ones are skipped; the store checked as publish.py does
(get_store(job.shop) + check_shop); no job event.
"""
import argparse
import glob
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict

from shop_files import LedgerError, ShopBusy, append_line, ensure_free, locked, read_jsonl, write_atomic
from shop_types import JobMeta

# run_transform takes the code's signature (its prepare cache key) when imported: import it before any other module of
# prepare's path is loaded for a job, so a file edited during the job's start is never hashed new while run old
# (2026-11-16, the phase 3 review)
import run_transform  # noqa: E402,F401

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")
STAGES = ("collected", "images", "prepared", "translated", "placed", "published")   # placed: placement.py, run on
                                                                                    # the shop before publication
BUILT = ("collected", "images", "prepared", "translated", "published")
BUSY_WAIT_S, BUSY_TRIES = 30, 12
ERROR_WAIT_S, ERROR_TRIES = 120, 2
MAX_FAILS = 2
UNEXPECTED_STOP = 3                          # products in a row failed by an unexpected error (a code defect): stop
PAUSE_S = 2
RECONNECT_WAIT_S, RECONNECT_S = 30, 900      # the extension / server gone: poll /health this long, then stop
CAPTCHA_TRIES = 6                            # a captcha not answered in time: the read asks the owner again
MAX_BATCHES = 40                             # listing batches of ~50 per query (probed 2026-11-08: 12 in 110 s)
MAX_BATCHES_ALL = 200                        # `new --all`: the server's cap (schemas.MAX_LISTING_BATCHES); the
                                             # listing's own end (has_more false) comes first (2026-11-12: the junior
                                             # queries ended at 19-31 batches)
REPORT_EVERY = 10
REVIEW_AFTER = 20                            # drafts of a job: the lens review is due (the owner, 2026-11-16)
DRAFT_WHY = "the new one is a draft"         # replace_skipped: the old one stays live until the new one is activated
# the network down (2026-11-13: Shopify, then both model providers, unreachable for minutes): the product is tried
# again (tenacity) after 30 s, doubled each time up to 15 min, +-10 s jitter; after 2 h of it the run stops
NET_WAIT_S, NET_MAX_WAIT_S, NET_JITTER_S, NET_GIVE_UP_S = 30, 900, 10, 7200
RETRYABLE = ("naver error page:", "adapter error:")
# scroll: the held listing tab gone (410), opened again after REOPEN_WAIT_S, at most REOPEN_MAX times in
# REOPEN_WINDOW_S (2026-11-14: no login gate in ~710 products of the old mode; the pilot measures it)
REOPEN_MAX, REOPEN_WINDOW_S, REOPEN_WAIT_S = 2, 3600, (30, 60)
# scroll: the 404s of /listing-tabs/<id>/specs that mean "not read from this tab" (card_not_found), by their text
# (ext_listing_tab.specs, ext_product._read_card / _land, 2026-11-14); any other 404 is the product's (not_found)
CARD_404 = ("has no card in the listing tab", "card_opened_other", "card_opened_nothing", "Naver shows its error page")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Context(TypedDict, total=False):
    """ctx: what one() and its steps use in a run. _context makes api, store, table, catalog, guard (translator for a
    job that translates, dedupe and dedupe_records for --dedupe log / on); the rest is added on first use."""
    api: Any                           # naver_api_client.NaverApiClient
    store: Any                         # shop_stores.get_store()
    table: dict[str, Any]              # package_measures.load_table()
    catalog: Any                       # shopify_catalog.ShopCatalog: the shop's published keys
    guard: Any                         # collect_guard.CollectGuard
    translator: Any                    # translate.build_chain
    dedupe: Any                        # dedupe.Index, built at the run's start
    dedupe_records: dict[str, Any]     # dedupe.collected: key -> collected line
    dedupe_catalogs: dict[str, Any]    # dedupe.catalogs: the catalog backfill by product id (2026-11-20)
    describer: Any                     # describe.build_chain, at the first description
    publisher: tuple[Any, Any, dict[str, Any]]   # publish.clients, at the first publication
    specs: Any                         # scroll: the listing tab's specs reader (Tab.specs)


# ---- the job folder ------------------------------------------------------------------------------------------

class Job:
    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "job.json"), encoding="utf-8") as f:
            self.meta: JobMeta = json.load(f)
        self.shop, self.category = self.meta["shop"], self.meta["category"]
        self.shops_root = self.meta["shops_root"]

    @property
    def final(self) -> str:
        """The stage a product of this job is taken to: translated, or prepared for a job without translation (and
        for a job created before translation was built)."""
        if self.meta.get("publish"):
            return "published"
        return "translated" if self.meta.get("translate") else "prepared"

    @property
    def id(self) -> str:
        return os.path.basename(self.folder)

    def rows(self) -> list[dict[str, Any]]:
        """The listing's rows; a cut-off last line (scroll killed while appending a row) is ignored, a bad middle
        line is a LedgerError (shop_files)."""
        return read_jsonl(os.path.join(self.folder, "listing.jsonl"), tail_ok=True)

    def events(self) -> list[dict[str, Any]]:
        path = os.path.join(self.folder, "events.jsonl")
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding="utf-8") as f:
            for x in f:
                try:
                    out.append(json.loads(x))
                except ValueError:
                    pass                          # a torn last line (a crash while writing): ignored
        return out

    def beat(self, **now: Any) -> None:
        """now.json: what the runner does at this moment (status shows it while the runner is alive)."""
        write_atomic(os.path.join(self.folder, "now.json"),
                     json.dumps({"pid": os.getpid(), "started": _my_start(), "at": _now(), **now}, ensure_ascii=False))

    def now(self) -> dict[str, Any] | None:
        """now.json while its runner lives, else None. A live pid alone is not proof: after a reboot or a long pause
        the system may give the dead runner's pid to another program (2026-11-16), so the pid's start time must be
        the one the runner wrote ("started"); a now.json written before that field: the pid must run job.py."""
        try:
            with open(os.path.join(self.folder, "now.json"), encoding="utf-8") as f:
                now = json.load(f)
            pid = int(now["pid"])
            os.kill(pid, 0)                              # some process has the pid
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if now.get("started"):
            return now if _proc(pid, "lstart") == now["started"] else None
        args = (_proc(pid, "command") or "").split()
        return now if any(os.path.basename(x) == "job.py" for x in args) else None

    def save_meta(self) -> None:
        write_atomic(os.path.join(self.folder, "job.json"), json.dumps(self.meta, ensure_ascii=False, indent=1))

    def log(self, key: str | None, event: str, **detail: Any) -> None:
        append_line(os.path.join(self.folder, "events.jsonl"),
                    json.dumps({"at": _now(), "key": key, "event": event, **detail}, ensure_ascii=False))


def _proc(pid: int, field: str) -> str | None:
    """One `ps -o <field>=` value of a process (macOS / BSD and Linux ps), None when it cannot be read."""
    try:
        out = subprocess.run(["ps", "-o", f"{field}=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


_START: list[str | None] = []


def _my_start() -> str | None:
    """This process's start time as ps prints it, read once (Job.now compares it with the pid's)."""
    if not _START:
        _START.append(_proc(os.getpid(), "lstart"))
    return _START[0]


def latest_job(root: str = JOBS_ROOT) -> str:
    found = sorted(glob.glob(os.path.join(root, "*", "job.json")), key=os.path.getmtime)
    if not found:
        raise SystemExit("no job yet: job.py new ...")
    return os.path.dirname(found[-1])


def open_job(job_id: str | None, root: str = JOBS_ROOT) -> Job:
    return Job(os.path.join(root, job_id) if job_id else latest_job(root))


# ---- stages read from the files ------------------------------------------------------------------------------

def stages(job: Job) -> dict[str, str]:
    """{key: the furthest built stage reached} for every snapshot key that has one."""
    from description_images import current, load_sidecar
    from run_transform import latest_lines
    from transform_shops import ShopRulesMissing, rules_for
    latest = latest_lines(job.shop, None, job.shops_root) if os.path.isdir(
        os.path.join(job.shops_root, job.shop, "collected")) else {}
    prepared = set()
    path = os.path.join(job.shops_root, job.shop, "prepared", "products.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            prepared = {json.loads(x)["key"] for x in f if x.strip()}
    translated = set()
    path = os.path.join(job.shops_root, job.shop, "translation", "translated.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
        translated = {r["key"] for r in rows if r.get("status") in ("translated", "held")}
    published = set()
    if job.final == "published":                # a product the shop withdrew (replaced_by, a hold, the owner) is done
        from publish import Shop                # too: the end-of-run drain sent replaced ones to publish_step again,
        shop = Shop(job.shop, job.shops_root)   # "not ready to publish (placement placed: None)" (2026-11-18, chippers)
        published = set(shop.ledger()) | shop.withdrawn()
    rules = rules_for(job.shop)

    def images_read(key: str, line: dict[str, Any]) -> bool:
        """The category reads no images, or this collection's are read (a sidecar of its links)."""
        cat = (line.get("specs") or {}).get("category") or {}
        try:
            off = not rules.category(cat.get("id"), cat.get("name")).description_images
        except ShopRulesMissing:
            off = True
        return off or current(load_sidecar(job.shop, key.split(":")[3], job.shops_root), line)

    out = {}
    for row in job.rows():
        key = row["key"]
        if key not in latest:
            continue
        line = latest[key][2]
        # prepared also with the images' note (failed / partial: the sidecar is there, current); but one prepared
        # by an earlier job with no sidecar of this collection goes through the images first (2026-11-17, the
        # wedge pilot: 20 products prepared before got the category's default package, description_images_missing);
        # one in the store already is never sent back (its next publication reads the images through a new run)
        if key in prepared and (key in published or images_read(key, line)):
            out[key] = ("published" if key in published else "translated") if key in translated and \
                job.final in ("translated", "published") else "prepared"
            continue
        out[key] = "images" if images_read(key, line) else "collected"
    return out


def closed(job: Job) -> dict[str, str]:
    """{key: why it is out of this job}: not_taken, deferred, or failed MAX_FAILS times."""
    fails: Counter = Counter()
    out = {}
    for e in job.events():
        if e["event"] in ("not_taken", "deferred"):
            out[e["key"]] = f"{e['event']}: {e.get('reason')}"
        elif e["event"] == "failed":
            fails[e["key"]] += 1
            if fails[e["key"]] >= MAX_FAILS:
                out[e["key"]] = f"failed {fails[e['key']]}x: {e.get('reason')}"
    return out


def held_keys(job: Job) -> set[str]:
    """This job's products its last `prepared` or `translated` event left held (the transform's or the translation's
    hold: agency_no_brand, ...): not published by this job, so a duplicate of one is no reason to skip a seller."""
    last: dict[str, str] = {}
    for e in job.events():
        if e["event"] in ("prepared", "translated"):
            last[e["key"]] = e.get("status") or ""
    return {k for k, status in last.items() if status == "held"}


def next_key(job: Job, done: dict[str, str], staged: bool = False) -> str | None:
    """The first snapshot key not at the job's final stage and not closed; fresh ones before those that failed.
    `staged`: only keys with a stage (collected on; scroll takes them on without its listing tab)."""
    out = closed(job)
    failed = {e["key"] for e in job.events() if e["event"] == "failed"}
    todo = [r["key"] for r in job.rows() if done.get(r["key"]) != job.final and r["key"] not in out
            and (not staged or r["key"] in done)]
    fresh = [k for k in todo if k not in failed]
    return (fresh or todo or [None])[0]


# ---- new -----------------------------------------------------------------------------------------------------

def known_ids() -> set[str]:
    """Product ids collected before anywhere in scripts/output and in the fixtures (a trial takes new ones)."""
    ids = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(SCRIPTS, "fixtures", "collected", "*.json"))}
    for f in glob.glob(os.path.join(SCRIPTS, "output", "**", "products.jsonl"), recursive=True):
        with open(f, "rb") as fh:
            for x in fh.read().split(b"\n"):
                if x.strip():
                    try:
                        ids.add(json.loads(x)["key"].split(":")[3])
                    except (ValueError, KeyError, IndexError):
                        pass
    return ids


def read_listings(api: Any, store: Any, queries: list[str], category: str, batches: int, skip: set[str],
                  known: set[str]) -> tuple[list[dict], list[dict], dict]:
    """Every query's listing (from the top: a listing has no cursor to resume, EXTENSION.md) up to `batches`,
    screened (listing_filter.Screen: category, rental, stop words, in the shop, deferred), without `skip` (already in
    the job) and `known`; the queries alternated. -> (rows, listing jobs, screen counts)."""
    from deferred_log import DeferredLog
    from listing_filter import Screen, source_key
    from shopify_catalog import ShopCatalog
    screen = Screen(category, store.shopify.namespace, ShopCatalog(store).keys(), DeferredLog(store.id.value).blocked())
    by_q: list[list[dict]] = []
    seen, listings = set(skip), []
    for query in queries:
        listing = api.listing(query, max_batches=batches)
        job_info = {k: listing["job"].get(k) for k in ("id", "status", "batches", "kept", "has_more", "stop")}
        listings.append({"query": query, **job_info})
        if listing["job"].get("status") == "stopped":
            print(f"warning: the listing for {query!r} stopped: {listing['job'].get('stop')} (rows so far kept)")
        rows = []
        for row in listing["results"]:
            key = source_key(row, store.shopify.namespace) or ""
            if key and screen.reason(row) is None and str(row.get("product_id")) not in known and key not in seen:
                seen.add(key)
                rows.append({**row, "query": query, "key": key})
        by_q.append(rows)
    mixed = [r for group in zip(*by_q) for r in group] + [r for g in by_q for r in g[min(map(len, by_q)):]]
    return mixed, listings, dict(screen.counts)


def more_batches(listings: list[dict], batches: int, cap: int = MAX_BATCHES) -> int | None:
    """The next listing depth to try when there are too few rows: double, while any listing has more; else None."""
    if batches >= cap or not any(x.get("has_more") and x.get("status") == "done" for x in listings):
        return None
    return min(batches * 2, cap)


def batch_cap(meta: JobMeta) -> int:
    """How deep the job's listings may be read: to their end for a `new --all` job, else MAX_BATCHES."""
    return MAX_BATCHES_ALL if meta.get("until_end") else MAX_BATCHES


def counted(job: "Job", done: dict[str, str]) -> int:
    """The job's products at its final stage toward `--count`: a withdrawn one is done (stages) but not counted, its
    replacement is (as before 2026-11-18)."""
    gone: set[str] = set()
    if job.final == "published":
        from publish import Shop
        gone = Shop(job.shop, job.shops_root).withdrawn()
    return sum(1 for r in job.rows() if done.get(r["key"]) == job.final and r["key"] not in gone)


def wanted(job: "Job", done: dict[str, str]) -> int | None:
    """The snapshot is used up: how many more products to read the listings deeper for (None: the job is done).
    A `--count N` job wants what is missing to N; a `--all` job wants every new row, while the listings have more."""
    if job.meta.get("until_end"):
        return 0
    target = job.meta.get("count") or 0
    n = counted(job, done)
    return target - n if target and n < target else None


def cmd_new(args: argparse.Namespace) -> int:
    from keep_run import SHOPS_ROOT
    from naver_api_client import NaverApiClient
    from package_measures import load_table
    from shop_stores import get_store
    if args.describe and not args.publish:
        print("stop: --describe needs --publish (a job without publication: describe.py <shop> after it)")
        return 2
    if args.all and args.count:
        print("stop: --all and --count: one or the other")
        return 2
    api, store = NaverApiClient(), get_store()
    if not any(str(r["category_id"]) == args.category for r in load_table()["rows"]):
        print(f"stop: no category_measures.json row for {args.category}: ask the operator")
        return 2
    assert store.shopify
    shops_root = os.path.abspath(args.shops_root or SHOPS_ROOT)
    known = known_ids() if args.exclude_known else set()
    batches = args.batches
    while True:
        rows, listings, counts = read_listings(api, store, args.query, args.category, batches, set(), known)
        nxt = more_batches(listings, batches) if args.count and len(rows) < args.count else None
        if nxt is None:
            break
        print(f"{len(rows)} screened rows with {batches} batches a query, fewer than {args.count}: {nxt} batches")
        batches = nxt
    rows = rows[:args.count] if args.count else rows
    job_id = f"{store.id.value}-{args.category}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    folder = os.path.join(JOBS_ROOT, job_id)
    os.makedirs(folder)
    meta: JobMeta = {"shop": store.id.value, "category": args.category, "queries": args.query,
            "paid": args.paid or args.paid_variants, "paid_variants": args.paid_variants,
            "reviews": args.reviews, "shops_root": shops_root, "created_at": _now(), "count": args.count,
            "batches": batches, "listings": listings, "screen": counts, "excluded_known": len(known),
            "exclude_known": args.exclude_known, "translate": not args.no_translate or args.publish,
            "publish": args.publish, "describe": args.describe,
            "until_end": args.all,                    # 2026-11-12, the owner: no count, to the listings' end
            "free_only": not args.paid}                   # 2026-11-09: no paid variant / add-on in the transform either
                                                          # (--paid-variants: this job's products take paid variants)
    if getattr(args, "draft", False):                     # 2026-11-16: only when set (job.json as before otherwise)
        meta["draft"] = True
    if args.dedupe != "off":                              # 2026-11-15: off writes no key (job.json as before)
        meta["dedupe"] = args.dedupe
    write_atomic(os.path.join(folder, "job.json"), json.dumps(meta, ensure_ascii=False, indent=1))
    write_atomic(os.path.join(folder, "listing.jsonl"), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"job {job_id}: {len(rows)} products ({batches} batches a query; screen: {counts}; known left out: "
          f"{len(known)})")
    _draft_first_line(args.publish, store.id.value, args.category, getattr(args, "draft", False))
    return 0


def refresh(job: Job, api: Any, store: Any, need: int) -> int:
    """`need` more products for the job (0: all there are): the listings again, deeper (more_batches), rows not in
    the job appended. -> how many were added (0: the listings have no more)."""
    batches = more_batches(job.meta.get("listings") or [], job.meta.get("batches") or 2, batch_cap(job.meta))
    if batches is None:
        return 0
    have = {r["key"] for r in job.rows()}
    known = known_ids() if job.meta.get("exclude_known") else set()
    rows, listings, counts = read_listings(api, store, job.meta["queries"], job.category, batches, have, known)
    rows = rows[:need] if need else rows                  # need 0: every new row (a `--all` job)
    if rows:
        append_line(os.path.join(job.folder, "listing.jsonl"),
                    *(json.dumps({**r, "refresh": batches}, ensure_ascii=False) for r in rows))
    job.meta.update({"batches": batches, "listings": listings})
    job.meta.setdefault("refreshes", []).append({"at": _now(), "batches": batches, "added": len(rows),
                                                 "screen": counts})
    job.save_meta()
    job.log(None, "refresh", batches=batches, added=len(rows))
    return len(rows)


def cmd_refresh(args: argparse.Namespace) -> int:
    from naver_api_client import NaverApiClient
    from shop_stores import get_store
    job = open_job(args.job)
    if _scroll_job(job):
        return 2

    def body() -> int:
        added = refresh(job, NaverApiClient(), get_store(), args.more)
        print(f"job {job.id}: {added} products added")
        return 0
    return locked(job.shops_root, job.shop, f"job.py refresh {job.id}", body)


# ---- run -----------------------------------------------------------------------------------------------------

class Stop(Exception):
    """The run must stop here (a wall, the extension, the server): `run` again resumes."""


class NetworkStop(Stop):
    """The network or every model provider is down: the product is tried again with growing waits (net_retry)."""


class TabLost(Stop):
    """scroll: the held listing tab is gone (410): a new one is opened, done products skipped (REOPEN_MAX)."""


def net_retry(job: "Job", key: str) -> Any:
    """Tries one product again while it ends in NetworkStop (a ConnectionError / Timeout counts too): waits from
    NET_WAIT_S doubled up to NET_MAX_WAIT_S, for NET_GIVE_UP_S in all, then the last error goes up (the run stops).
    Each try starts from the product's stage read from the files: what was done is not done again."""
    import requests
    import tenacity

    def waiting(state: Any) -> None:
        e = state.outcome.exception()
        wait = round(state.next_action.sleep)
        job.log(key, "network_wait", attempt=state.attempt_number, wait_s=wait, reason=str(e)[:200])
        print(f"   network down ({str(e)[:120]}): try {state.attempt_number + 1} in {wait} s", flush=True)
    return tenacity.Retrying(
        retry=tenacity.retry_if_exception_type((NetworkStop, ConnectionError, requests.exceptions.ConnectionError,
                                                requests.exceptions.Timeout)),
        wait=tenacity.wait_exponential_jitter(multiplier=NET_WAIT_S, max=NET_MAX_WAIT_S, jitter=NET_JITTER_S),
        stop=tenacity.stop_after_delay(NET_GIVE_UP_S), before_sleep=waiting, reraise=True,
        sleep=lambda s: time.sleep(s))


def _network(e: Exception) -> bool:
    """A CatalogError that is the network, not the shop (shopify_catalog: "request failed: <requests error>")."""
    return "request failed" in str(e)


def collect_with_waits(job: Job, api: Any, store: Any, table: dict, guard: Any, row: dict, tmp: str,
                       specs: Any = None) -> Any:
    """CollectGuard over collect_product.collect, with the job's waits; -> Outcome, or None when the product failed
    (logged); raises Stop (TabLost: a scroll job's listing tab is gone). `specs`: collect's (None: its search)."""
    import requests
    from collect_guard import SourceStopped
    from collect_product import collect
    busy = errors = captchas = 0
    how = {"specs": specs} if specs else {}
    scroll = job.meta.get("mode") == "scroll"
    while True:
        try:
            return guard.run(row["key"], lambda: collect(
                api, store, table, row, os.path.join(tmp, "images", str(row["product_id"])),  # type: ignore[arg-type]
                query=row.get("query"), category=job.category, paid=job.meta["paid"], reviews=job.meta["reviews"],
                **how))
        except SourceStopped as e:
            error = str(e.error or "")
            if e.status == 410 and scroll:            # only /listing-tabs answers 410; elsewhere a plain Stop
                raise TabLost(f"{e}") from None
            if e.status == 409 and busy < BUSY_TRIES:
                busy += 1
                print(f"   adapter busy, waiting {BUSY_WAIT_S} s ({busy}/{BUSY_TRIES})", flush=True)
                time.sleep(BUSY_WAIT_S)
                continue
            if e.status == 503 and error.startswith(RETRYABLE):
                if errors < ERROR_TRIES:
                    errors += 1
                    print(f"   {error[:90]}; waiting {ERROR_WAIT_S} s ({errors}/{ERROR_TRIES})", flush=True)
                    time.sleep(ERROR_WAIT_S)
                    continue
                job.log(row["key"], "failed", stage="collect", reason=error[:200])
                return None
            if e.status == 503 and "extension is not connected" in error:
                wait_service(job, api, "the browser extension is not connected")
                continue
            # scroll: only the server's own words (the tab kept): /captcha stays timed_out until the next captcha,
            # and a ban after one would be read again (Fable review 5, 2026-11-14)
            if e.status == 503 and captchas < CAPTCHA_TRIES and (
                    error.startswith("wall: captcha") if scroll else _captcha_status(api) == "timed_out"):
                captchas += 1                              # not a ban: the owner did not answer in time
                job.log(row["key"], "captcha_again", attempt=captchas)
                print(f"   a captcha was not answered in time: reading again, the owner is asked again "
                      f"({captchas}/{CAPTCHA_TRIES})", flush=True)
                time.sleep(BUSY_WAIT_S)
                continue
            raise Stop(f"{e}") from None
        except requests.exceptions.ConnectionError:
            wait_service(job, api, "the API server does not answer")


def _captcha_status(api: Any) -> str | None:
    try:
        return api.captcha().get("status")
    except Exception:
        return None


def wait_service(job: Job, api: Any, why: str) -> None:
    """Wait for the server and the extension (RECONNECT_S, polling /health); raises Stop when they do not come."""
    import requests
    job.log(None, "waiting", reason=why)
    print(f"   {why}: waiting up to {RECONNECT_S // 60} min for the server and the extension", flush=True)
    t0 = time.monotonic()
    while time.monotonic() - t0 < RECONNECT_S:
        time.sleep(RECONNECT_WAIT_S)
        try:
            if api.health().get("extension") == "connected":
                print(f"   back after {round(time.monotonic() - t0)} s", flush=True)
                job.log(None, "back", after_s=round(time.monotonic() - t0))
                return
        except (requests.exceptions.RequestException, Exception):
            pass
    raise Stop(f"{why} for {RECONNECT_S // 60} min")


def keep_line(job: Job, line: dict, tmp: str) -> str:
    """The product's line as a one-line kept run (keep_run); -> the run folder. keep_run names a run by its
    products.jsonl time (a second): a run id already taken moves the file's time a second on."""
    from keep_run import KeepError, keep
    path = os.path.join(tmp, "products.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    for _ in range(3):
        try:
            return keep(tmp, job.shops_root)
        except KeepError as e:
            if "already kept as" in str(e):
                return str(e).rsplit(" ", 1)[-1]
            if not str(e).endswith("exists"):
                raise
            later = os.path.getmtime(path) + 1           # the next second: a run id of its own
            os.utime(path, (later, later))
    raise Stop(f"keep: {path}: run id taken three times")


DEDUPE_EVENTS = ("duplicate_seen", "duplicate_better")


def dedupe_step(job: Job, ctx: Context, key: str, line: dict | None) -> str | None:
    """--dedupe log / on, right after collect: the product against ctx["dedupe"] (dedupe.Index). -> what happened
    when it is not taken (on: a confirmed duplicate not strictly better), else None (go on). A product decided before
    (a resume) is not looked up again."""
    import dedupe
    index = ctx["dedupe"]
    if any(e.get("key") == key and e["event"] in DEDUPE_EVENTS for e in job.events()):
        return None
    # this job's own products closed or held meanwhile block nothing (2026-11-15, the wedge pilot: 10 sellers of
    # 5 models skipped as duplicates of a product held as agency_no_brand: the model reached the store from none)
    for k in {*closed(job), *held_keys(job)}:
        if (index.by_key.get(k) or {}).get("status") == "job":
            index.drop(k)
    if line is None:
        line = (ctx.get("dedupe_records") or {}).get(key)  # read once at the run's start
    if line is None:
        from run_transform import latest_lines
        line = latest_lines(job.shop, None, job.shops_root)[key][2]
    cand = dedupe.entry(line, "job", ctx.get("dedupe_catalogs"))   # an old record's catalog from the backfill
    d = index.decide(cand)
    if d["decision"] is None and d.get("same_upc"):         # a hold candidate, never a decision (2026-11-17)
        job.log(key, "duplicate_seen", decision=f"same_upc:{d['same_upc'][0]}", same_upc=d["same_upc"],
                upc=d.get("upc"), grade=cand["grade"], reviews=cand["reviews"], price=cand["price"],
                matches=d["matches"])
        index.add(cand)
        return None
    if d["decision"] is None and d.get("same_item"):        # the same Naver catalog or style code (2026-11-20)
        job.log(key, "duplicate_seen", decision=f"same_item:{d['same_item'][0]}", same_item=d["same_item"],
                why=d.get("why"), grade=cand["grade"], reviews=cand["reviews"], price=cand["price"],
                matches=d["matches"])
        index.add(cand)
        return None
    if not d["matches"]:
        index.add(cand)
        return None
    if job.meta.get("dedupe") == "log" or d["decision"] is None:
        job.log(key, "duplicate_seen", decision=f"{d['decision']}:{d['of']}" if d["decision"] else "not_confirmed",
                grade=cand["grade"], reviews=cand["reviews"], price=cand["price"], matches=d["matches"])
        if d["decision"] in (None, "duplicate_better"):    # log builds the index on mode would build
            index.add(cand)
        return None
    if d["decision"] in ("duplicate_of_withdrawn", "duplicate_of"):
        reason = f"{d['decision']}:{d['of']}"
        job.log(key, "not_taken", reason=reason, grade=cand["grade"], reviews=cand["reviews"], price=cand["price"],
                matches=d["matches"])
        index.drop(key)
        return f"not taken: {reason}"
    job.log(key, "duplicate_better", replaces=d["of"], grade=cand["grade"], reviews=cand["reviews"],
            price=cand["price"], matches=d["matches"])
    index.add(cand)
    return None


def replace_step(job: Job, ctx: Context, shop: Any, key: str) -> str:
    """--dedupe on, after `key` is published: the product it replaces (its duplicate_better event) withdrawn when it is
    still published and `key` has no fewer variants. -> a note for the printed line ("" when nothing to do)."""
    import dedupe
    import publish
    from shopify_catalog import CatalogError
    events = [e for e in job.events() if e.get("key") == key]
    old = next((e.get("replaces") for e in reversed(events) if e["event"] == "duplicate_better"), None)
    if not old or any(e["event"] in ("replaced", "replace_skipped") for e in events):
        return ""
    ledger = shop.ledger()
    new_n, old_n = dedupe.variant_count(job.shop, key, job.shops_root), dedupe.variant_count(job.shop, old,
                                                                                            job.shops_root)
    # draft first (2026-11-16): a live product is not swapped for a draft; `job.py activate` prints its withdraw line
    why = ("not published" if key not in ledger else "the old one is not published" if old not in ledger
           else DRAFT_WHY if ledger[key].get("store_status") == "DRAFT" and ledger[old].get("store_status") != "DRAFT"
           else f"fewer variants ({new_n} < {old_n})" if (new_n or 0) < (old_n or 0) else None)
    if why:
        job.log(key, "replace_skipped", replaces=old, why=why)
        return f"; {old.split(':')[3]} kept: {why}"
    try:
        publish.withdraw(shop, old, ctx["publisher"][0], reason=f"{dedupe.REPLACED}{key}")
    except CatalogError as e:                                   # the new one stays; the owner withdraws by hand
        job.log(key, "replace_skipped", replaces=old, why=f"withdraw failed: {e}"[:300])
        return f"; {old.split(':')[3]} not withdrawn: {e}"[:200]
    if "dedupe" in ctx:                     # old stays in, leading its later copies in this job to key (2026-11-16)
        ctx["dedupe"].replace(old, key)
    job.log(key, "replaced", replaces=old, variants=[new_n, old_n])
    return f"; replaces {old.split(':')[3]} (withdrawn)"


def same_upc_of(job: Job, key: str) -> tuple[str, list[str]] | None:
    """(the key, the UPCs) of `key`'s last `duplicate_seen` same_upc event, None without one. A same_item event (the
    Naver catalog or style code, 2026-11-20) is a flag only, never a hold: same_item_open."""
    for e in reversed(job.events()):
        if e.get("key") == key and e["event"] == "duplicate_seen":
            decision = str(e.get("decision") or "")
            return (decision.split(":", 1)[1], list(e.get("upc") or [])) if decision.startswith("same_upc:") else None
    return None


def same_item_open(job: Job) -> list[dict[str, Any]]:
    """The job's same-item candidates still to review (the owner, 2026-11-20: a flag, never an automatic hold):
    [{key, of, why}] per pair from the last `duplicate_seen` same_item event of each key, both products still
    published (draft or live), the pair not judged versions (lens/reviewed.jsonl, `lens.py dupes --versions`)."""
    import dedupe
    from publish import Shop
    ledger = Shop(job.shop, job.shops_root).ledger()
    judged = dedupe.judged(job.shop, job.shops_root)
    last: dict[str, dict[str, Any]] = {}
    for e in job.events():
        if e["event"] == "duplicate_seen":
            last[e["key"]] = e
    out = []
    for key, e in last.items():
        if not str(e.get("decision") or "").startswith("same_item:") or key not in ledger:   # ledger(): published
            continue
        for of, why in zip(e.get("same_item") or [], e.get("why") or []):
            if of in ledger and not dedupe.is_judged(key, of, judged):
                out.append({"key": key, "of": of, "why": why})
    return out


def upc_hold_step(job: Job, ctx: Context, shop: Any, key: str) -> str:
    """--dedupe on, after `key` is published: a product sharing a live product's UPC (dedupe.upc_suspect, no confirmed
    match) held at once as a draft for the owner (2026-11-17, the wedge review: 14 groups of copies with one UPC, titles
    shuffled apart; OWNER_RULES rule 2). -> a note for the printed line ("" when nothing to do)."""
    import publish
    from shopify_catalog import CatalogError
    flag = same_upc_of(job, key)
    if flag is None or any(e.get("key") == key and e["event"] == "held_same_upc" for e in job.events()):
        return ""
    of, upc = flag
    ledger = shop.ledger()
    if key not in ledger or ledger[key].get("status") != "published":
        return ""
    live = (ledger.get(of) or {}).get("status") == "published"
    reason = (f"hold: {'copy of live' if live else 'same UPC as'} {of}, same UPC {' '.join(upc)}, kept as a draft for "
              f"a separate decision (dedupe same_upc)")
    try:
        publish.withdraw(shop, key, ctx["publisher"][0], reason=reason)
    except CatalogError as e:
        job.log(key, "held_same_upc", of=of, why=f"withdraw failed: {e}"[:300])
        return f"; same UPC as {of.split(':')[3]}, not held: {e}"[:200]
    job.log(key, "held_same_upc", of=of, reason=reason)
    return f"; held (same UPC as {of.split(':')[3]})"


def one(job: Job, ctx: Context, key: str, stage_now: str | None, n: int = 0) -> str:
    """Take one product from its stage to prepared. -> what happened (for the line printed)."""
    import description_images
    import run_transform
    row = next(r for r in job.rows() if r["key"] == key)
    pid = str(row["product_id"])
    t0 = time.monotonic()
    line = None
    if stage_now is None:
        try:
            published = ctx["catalog"].keys()                   # published meanwhile (read again every 5 min)
        except Exception as e:                                  # CatalogError / ShopNotConfigured: no shop check
            raise (NetworkStop if _network(e) else Stop)(f"shop check: {type(e).__name__}: {e}") from None
        if key in published:
            job.log(key, "not_taken", reason="already_published")
            return "not taken: already published"
        tmp = os.path.join(job.folder, "tmp", pid)
        shutil.rmtree(tmp, ignore_errors=True)
        job.beat(key=key, n=n, stage="collect", since=_now())
        outcome = collect_with_waits(job, ctx["api"], ctx["store"], ctx["table"], ctx["guard"], row, tmp,
                                     ctx.get("specs"))
        if outcome is None:
            return "failed (collect)"
        if outcome.status in ("not_taken", "deferred"):
            job.log(key, outcome.status, reason=outcome.reason)
            shutil.rmtree(tmp, ignore_errors=True)
            return f"{outcome.status}: {outcome.reason}"
        line = {"key": key, **outcome.data}
        kept = keep_line(job, line, tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        job.log(key, "collected", run=os.path.basename(kept), seconds=round(time.monotonic() - t0))
    # every product the job takes on, whatever stage it resumes at (2026-11-15, the wedge pilot: products a first
    # job had collected and the transform had held came back ready and went from "prepared" to the store without a
    # look: 13 copies of 5 models); one published by this job already is not looked up again
    if ctx.get("dedupe") is not None and not any(e.get("key") == key and e["event"] == "published"
                                                 for e in job.events()):
        dropped = dedupe_step(job, ctx, key, line)
        if dropped:
            return dropped
    if stage_now == "translated":                               # only the publication is left
        return publish_step(job, ctx, key, n)
    t1 = time.monotonic()
    if stage_now in (None, "collected"):
        job.beat(key=key, n=n, stage="images", since=_now())
        try:
            r = description_images.run(job.shop, products=[pid], shops_root=job.shops_root,
                                       log=lambda m: print("   " + m, flush=True))
        except description_images.StageBusy as e:
            raise Stop(f"images: {e}") from None
        except description_images.CdnRefused as e:
            raise Stop(f"images: the image CDN refused: {e}") from None
        if r["counts"].get("errors"):
            job.log(key, "failed", stage="images", reason="description_images error sidecar")
    t2 = time.monotonic()
    result = None
    if stage_now != "prepared":
        job.beat(key=key, n=n, stage="prepare", since=_now())
        try:                                                    # each product with its own job's paid choices;
            result = run_transform.run(job.shop, None, job.shops_root, cache=True)   # the prepare cache, 2026-11-16
        except Exception as e:                                   # a transform defect: stop, never loop on it
            raise Stop(f"prepare: {type(e).__name__}: {e}") from None
    # the product from the run just made, not the 65 MB products.jsonl parsed again (2026-11-16: with the cache
    # that parse was a visible part of prepare_s); the file only when prepare did not run here
    done = {p["key"]: p for p in (result["prepared"] if result is not None else _prepared(job))}
    p = done.get(key)
    t3 = time.monotonic()
    if result is not None:                                       # cache_miss: the whole shop once after a code change
        job.log(key, "prepared", status=p and p["status"], held=[h["code"] for h in (p or {}).get("held") or []],
                images_s=round(t2 - t1), prepare_s=round(t3 - t2), cache_miss=result["cache"]["miss"])
    what = f"prepared: {p and p['status']}" + (f" {[h['code'] for h in p['held']]}" if p and p["held"] else "")
    times = f"collect {round(t1 - t0)} s, images {round(t2 - t1)} s, prepare {round(t3 - t2)} s"
    if job.final in ("translated", "published") and p:
        job.beat(key=key, n=n, stage="translate", since=_now())
        translated = translate_one(job, ctx, key)
        what += "; " + translated
        times += f", translate {round(time.monotonic() - t3)} s"
        if job.final == "published" and translated.startswith("translated ("):
            t4 = time.monotonic()
            what += "; " + publish_step(job, ctx, key, n)
            times += f", publish {round(time.monotonic() - t4)} s"
    return f"{what} ({times})"


def publish_step(job: Job, ctx: Context, key: str, n: int = 0) -> str:
    """Placement (the whole shop, offline) and then this product to Shopify (publish.py). -> what happened.
    A product placement cannot place or a refused write is `failed` (tried again later); a token or scope problem
    stops the run."""
    import placement
    import publish
    import shopify_payload
    from shopify_catalog import CatalogError, ShopNotConfigured
    job.beat(key=key, n=n, stage="publish", since=_now())
    placement.run(job.shop, job.shops_root)
    shop = publish.Shop(job.shop, job.shops_root)
    gate = shop.not_ready(key)                                  # withdrawn, held by the transform or the
    if gate is not None:                                        # translation, or not placed: closed, the owner decides
        reason = f"not ready to publish ({gate})"
        job.log(key, "not_taken", reason=reason[:300])
        return reason
    described = describe_one(job, ctx, key) + "; " if job.meta.get("describe") else ""
    try:
        if "publisher" not in ctx:
            ctx["publisher"] = publish.clients(job.shop)
        products, files, ids = ctx["publisher"]
        held = job.meta.get("dedupe") == "on" and same_upc_of(job, key) is not None    # never live, even a moment
        row = publish.publish_one(shop, key, products, files, ids, draft=bool(job.meta.get("draft")) or held)
    except ShopNotConfigured as e:
        raise Stop(f"publish: {e}") from None
    except (shopify_payload.Untranslated, shopify_payload.PayloadError) as e:
        job.log(key, "failed", stage="publish", reason=f"{type(e).__name__}: {e}"[:300])
        return f"publish held: {e}"[:200]
    except CatalogError as e:
        if "token" in str(e) or "401" in str(e) or "lacks" in str(e):
            raise Stop(f"publish: {e}") from None
        if _network(e):                                         # not the product's fault: not counted as failed
            raise NetworkStop(f"publish: {e}") from None
        job.log(key, "failed", stage="publish", reason=str(e)[:300])
        return f"publish failed: {e}"[:200]
    job.log(key, "published", product_id=row.get("product_id"), handle=row.get("handle"), status=row["status"],
            prices_usd=row.get("prices_usd"))
    price = "-".join(dict.fromkeys(str(p) for p in row.get("prices_usd") or []))
    replaced = replace_step(job, ctx, shop, key) + upc_hold_step(job, ctx, shop, key) \
        if job.meta.get("dedupe") == "on" else ""
    draft = "(draft) " if row.get("store_status") == "DRAFT" else ""
    return (f"{described}published {draft}{row.get('handle')} {f'${price} ' if price else ''}"
            f"{row.get('admin_url') or ''}".strip() + replaced)


def describe_one(job: Job, ctx: Context, key: str) -> str:
    """The product's description (describe.py: one model request; a product that has one is not asked again).
    -> what happened. A refused key or no provider answering stops the run: a job made with --describe does not
    publish a product without its description. An answer that fails the checks is never a stop: the script cuts
    what failed, down to the title as one sentence."""
    import describe
    import translate
    try:
        if "describer" not in ctx:                               # its own chain: the same models at a higher effort
            ctx["describer"] = describe.build_chain(translate.keys_from_env())
        r = describe.run(job.shop, ctx["describer"], job.shops_root, only=key)
    except translate.TranslateError as e:
        raise Stop(f"describe: {e}") from None
    except describe.NoProvider as e:
        raise NetworkStop(f"describe: {e}") from None
    row = r["rows"][0] if r["rows"] else None
    if row is None:
        return "description kept"
    cut = len(row["dropped"])
    job.log(key, "described", status=row["status"], cut=cut, origin=row["origin"], origin_note=row["origin_note"],
            conflicts=len(row["conflicts"]), cost=round(translate.cost(r["usage"])[0], 4))
    return f"described ({row['status']}" + (f", {cut} cut" if cut else "") + ")"


def translate_one(job: Job, ctx: Context, key: str) -> str:
    """The product through translate.py (only it goes to the model). -> what happened. A product the model could not
    translate is `failed` (tried again later); every provider down is a NetworkStop (net_retry)."""
    import translate
    try:
        r = translate.run(job.shop, ctx["translator"], job.shops_root, only=key)
    except translate.TranslateError as e:                         # a refused key: nothing will work
        raise Stop(f"translate: {e}") from None
    rec = next((x for x in r["records"] if x["key"] == key), None)
    status = rec and rec["status"]
    calls, cost = (rec or {}).get("model_calls", 0), translate.cost(r["usage"])[0]
    if status in ("translated", "held"):
        job.log(key, "translated", status=status, calls=calls, provider=(rec or {}).get("provider"), cost=round(cost, 4))
        return f"translated ({calls} calls, ${cost:.3f})" if status == "translated" else "translate: held, nothing"
    problems = "; ".join(f"{p.get('id')}: {', '.join(p.get('problems') or [])}" for p in (rec or {}).get("problems", [])[:3])
    if status == "pending" and "provider down" in problems:      # every provider down for a batch
        raise NetworkStop(f"translate: no provider answered: {problems}"[:300])
    job.log(key, "failed", stage="translate", reason=problems[:300])
    return f"translate failed: {problems}"[:200]


def _prepared(job: Job) -> list[dict]:
    path = os.path.join(job.shops_root, job.shop, "prepared", "products.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _context(job: Job) -> tuple[Context | None, int]:
    """What one() needs for the job (the API, the store, the shop's catalog, the guard, the translator): -> (ctx, 0),
    or (None, 2) with the reason printed."""
    from collect_guard import CollectGuard
    from deferred_log import DeferredLog
    from naver_api_client import NaverApiClient
    from package_measures import load_table
    from shop_stores import get_store
    from shopify_catalog import ShopCatalog
    store = get_store()
    if store.id.value != job.shop:
        print(f"stop: SHOP_STORE is {store.id.value}, the job is for {job.shop}")
        return None, 2
    ctx: Context = {"api": NaverApiClient(), "store": store, "table": load_table(), "catalog": ShopCatalog(store),
           "guard": CollectGuard(DeferredLog(store.id.value))}
    if job.final in ("translated", "published"):
        import translate
        try:
            ctx["translator"] = translate.build_chain(translate.keys_from_env())
        except translate.TranslateError as e:
            print(f"stop: translation: {e} (a job without it: job.py new ... --no-translate)")
            return None, 2
    if job.meta.get("dedupe") in ("log", "on"):
        import dedupe
        gone = closed(job)
        ctx["dedupe_records"] = dedupe.collected(job.shop, job.shops_root)
        ctx["dedupe_catalogs"] = dedupe.catalogs(job.shop, job.shops_root)
        ctx["dedupe"] = dedupe.load(job.shop, job.shops_root, [r["key"] for r in job.rows() if r["key"] not in gone],
                                    records=ctx["dedupe_records"])
    return ctx, 0


def _scroll_job(job: Job) -> bool:
    """A scroll job: `run` / `refresh` refuse it (no snapshot to read deeper; its tab is scroll's)."""
    if job.meta.get("mode") != "scroll":
        return False
    print(f"stop: job {job.id} is a scroll job: resume it with job.py scroll --job {job.id}")
    return True


def take(job: Job, ctx: Context, key: str, stage_now: str | None, run: dict) -> int | None:
    """One product through one() (net_retry: the network down is waited out), with its start and done lines, the
    progress line every REPORT_EVERY and the pause after it. -> None, or 3 when the run stops (logged, printed).
    TabLost goes up: scroll opens a new tab and the product is read again when its card comes."""
    from collect_guard import RunStopped
    rows = job.rows()
    n = [r["key"] for r in rows].index(key) + 1
    name = (rows[n - 1].get("name") or "")[:50]
    print(f"[{n}/{len(rows)}] {key.split(':')[3]} {name}", flush=True)
    try:
        for attempt in net_retry(job, key):
            with attempt:
                what = one(job, ctx, key, stage_now if attempt.retry_state.attempt_number == 1
                           else stages(job).get(key), n)
    except TabLost:
        raise
    except (Stop, RunStopped) as e:
        if isinstance(e, RunStopped):                 # the guard deferred this product before it stopped
            job.log(key, "deferred", reason="run_stopped")
        job.log(key, "stop", reason=str(e)[:300])
        print(f"STOP at {key}: {e}\n   {run['again']} to resume", flush=True)
        return 3
    except (OSError, ConnectionError, LedgerError) as e:         # a broken shop file stops: it names <path>:<n>
        job.log(key, "stop", reason=f"{type(e).__name__}: {e}"[:300])
        print(f"STOP at {key}: {type(e).__name__}: {e}\n   {run['again']} to resume", flush=True)
        return 3
    except Exception as e:
        # 2026-11-16: anything else (a KeyError, a TypeError from dedupe, translate, describe or publish) killed the
        # run with no event, and resume took the same product again. Now the product is failed (stage unexpected,
        # closed at MAX_FAILS like any failure) and the run goes on; UNEXPECTED_STOP in a row (any products) stop
        # it: a code defect must not close a whole listing. SystemExit is not caught (publish.withdraw raises it).
        traceback.print_exc()
        reason = _where(e)
        job.log(key, "failed", stage="unexpected", reason=reason[:300])
        print(f"[{n}/{len(rows)}] {key.split(':')[3]} failed (unexpected): {reason}"[:400], flush=True)
        run["unexpected"] = run.get("unexpected", 0) + 1
        if run["unexpected"] >= UNEXPECTED_STOP:
            why = f"{UNEXPECTED_STOP} products in a row failed unexpectedly (the last: {reason})"
            job.log(key, "stop", reason=why[:300])
            print(f"STOP: {why}"[:400] + f"\n   {run['again']} to resume", flush=True)
            return 3
        return None
    run["taken"] += 1
    run["unexpected"] = 0
    print(f"[{n}/{len(rows)}] {key.split(':')[3]} {what}", flush=True)
    if run["taken"] % REPORT_EVERY == 0:
        print("== " + progress(job, run["taken"], time.monotonic() - run["started"]), flush=True)
        _review_reminder(job, due_only=True)                    # from REVIEW_AFTER drafts on
        _same_item_reminder(job)
    job.beat(key=None, n=n, stage="pause", since=_now())
    time.sleep(PAUSE_S)
    return None


def _where(e: BaseException) -> str:
    """'<Type>: <message> @ <file>:<line>' of the innermost frame, for an event's reason."""
    tb = traceback.extract_tb(e.__traceback__)
    return f"{type(e).__name__}: {e}" + (f" @ {os.path.basename(tb[-1].filename)}:{tb[-1].lineno}" if tb else "")


def _guarded(job: Job, again: str, body: Any) -> int:
    """A run's body (its context included) -> its exit code; an error nothing else caught is a stop event, the STOP
    line and 3, so no run ends without an event (a LedgerError: the file and line, no traceback). SystemExit and
    KeyboardInterrupt go up as before."""
    try:
        return body()
    except LedgerError as e:
        job.log(None, "stop", reason=f"LedgerError: {e}"[:300])
        print(f"STOP: LedgerError: {e}\n   {again} to resume", flush=True)
        return 3
    except Exception as e:
        traceback.print_exc()
        reason = f"unexpected: {_where(e)}"
        job.log(None, "stop", reason=reason[:300])
        print(f"STOP: {reason}"[:400] + f"\n   {again} to resume", flush=True)
        return 3


def cmd_run(args: argparse.Namespace) -> int:
    job = open_job(args.job)
    if _scroll_job(job):
        return 2
    args.ran = job.folder                                      # main() tells the owner how it ended
    return locked(job.shops_root, job.shop, f"job.py run {job.id}",
                  lambda: _guarded(job, "run again", lambda: _run(job, args)))


def _run(job: Job, args: argparse.Namespace) -> int:
    ctx, code = _context(job)
    if ctx is None:
        return code
    store = ctx["store"]
    run = {"taken": 0, "started": time.monotonic(), "again": "run again"}
    goal = "to the listings' end" if job.meta.get("until_end") else job.meta.get("count") or "all"
    print(f"job {job.id}: run ({len(job.rows())} products in the snapshot, target {goal})",
          flush=True)
    while not args.items or run["taken"] < args.items:
        done = stages(job)
        key = next_key(job, done)
        if key is None:
            need = wanted(job, done)
            if need is not None:
                print(f"the snapshot is used up with {counted(job, done)} {job.final} (target {goal}): reading the "
                      "listings deeper", flush=True)
                try:
                    added = refresh(job, ctx["api"], store, need)
                except Exception as e:
                    job.log(None, "stop", reason=f"refresh: {type(e).__name__}: {e}"[:300])
                    print(f"STOP: refresh: {e}\n   run again to resume", flush=True)
                    return 3
                print(f"   {added} products added", flush=True)
                if added or more_batches(job.meta.get("listings") or [], job.meta.get("batches") or 2,
                                         batch_cap(job.meta)) is not None:
                    continue                          # none passed the screen at this depth: deeper still
            job.log(None, "done")
            print(f"done: every product of the job is {job.final} or closed", flush=True)
            _dictionaries_reminder(job)
            _review_reminder(job)
            _same_item_reminder(job)
            break
        stop = take(job, ctx, key, done.get(key), run)
        if stop:
            return stop
    return 0


def progress(job: Job, taken: int, seconds: float) -> str:
    """One line: where the job is (for the log and a watcher)."""
    s = summary(job)
    st = s["stages"]
    target = job.meta.get("count") or s["products"]
    per = seconds / taken if taken else 0
    left = max(target - st[job.final], 0)
    return (f"progress: {st[job.final]} of {target} {job.final} (ready {s['ready']}, held {len(s['held'])}), closed "
            f"{st['closed']}, failed once {len(s['failed_once'])}; this run {taken} in {round(seconds / 60)} min, "
            f"~{round(per)} s a product, ~{round(left * per / 60)} min left"
            + (f"; {s['review']['drafts']} drafts await the review" if s["review"] else ""))


# ---- scroll: a held listing tab, its cards clicked (the owner, 2026-11-14) -----------------------------------

class Tab:
    """The job's held listing tab on the server (/listing-tabs): open / next / specs / close, its id in job.json
    while it is open. specs() is collect_product.collect's `specs=`."""

    def __init__(self, job: Job, api: Any):
        self.job, self.api, self.id = job, api, None
        self.opening = False                       # an open sent and not answered (the server may hold a tab)

    def _keep(self, answer: dict) -> dict:
        self.id = answer["id"]
        self.job.meta.update({"tab": self.id, "batches": answer["batch"]})
        self.job.save_meta()
        return answer

    def open(self) -> dict:
        self.opening = True
        answer = self._calls(lambda: self.api.listing_tab_open(self.job.meta["queries"][0]))
        self.opening = False
        self.job.meta["total"] = answer["total"]                  # the listing's size (2026-11-14: 53, 122 seen)
        return self._keep(answer)

    def next(self) -> dict:
        return self._keep(self._calls(lambda: self.api.listing_tab_next(self.id), resend=False))

    def specs(self, api: Any, link: str, query: str | None) -> Any:
        """The page's specs by a click on its card, None when the tab has no card for it (or it opened another
        product, or nothing; or Naver's error page): not_taken card_not_found, as a search that did not show it.
        Another 404 (the product itself gone) goes up: collect's not_found."""
        from naver_api_client import ApiError
        if self.id is None:
            raise ApiError(410, "no listing tab open", path="/listing-tabs")
        try:
            return api.listing_tab_specs(self.id, link)
        except ApiError as e:
            if e.status != 404 or not any(w in (e.error or "") for w in CARD_404):
                raise
            return None

    def lost(self) -> None:
        """The server has no session for it any more (410): nothing to close."""
        self.id = None
        self.job.meta["tab"] = None
        self.job.save_meta()

    def close(self) -> None:
        """DELETE it (idempotent); never raises: it runs in the run's finally."""
        if self.id is None:
            if self.opening:                           # interrupted mid-open: the server may have finished it
                print("   an open of the listing tab was cut off: if the server finished it, the tab holds the "
                      "adapter until the next scroll, a server restart or the DELETE a 409 names", flush=True)
            return
        try:
            self.api.listing_tab_close(self.id)
        except Exception as e:                         # the server down: a restart frees the adapter anyway
            print(f"   the listing tab {self.id} was not closed ({type(e).__name__}: {e}); free it with "
                  f"curl -X DELETE localhost:8000/listing-tabs/{self.id}", flush=True)
        self.lost()

    def _calls(self, call: Any, resend: bool = True) -> dict:
        """open / next with the job's waits: 409 (adapter busy) BUSY_TRIES times, the extension or the server gone
        (wait_service); 410 -> TabLost; anything else (a wall, a stall, a refused batch) -> Stop. resend False
        (next): a connection lost after the call was sent is TabLost once the server is back, not a second next
        (the server may have handed out the batch: sent again, it would answer the one after it)."""
        import requests
        from naver_api_client import ApiError
        busy = 0
        while True:
            try:
                return call()
            except ApiError as e:
                if e.status == 410:
                    raise TabLost(f"{e}") from None
                if e.status == 409 and busy < BUSY_TRIES:
                    busy += 1
                    print(f"   adapter busy ({e.error}), waiting {BUSY_WAIT_S} s ({busy}/{BUSY_TRIES})", flush=True)
                    time.sleep(BUSY_WAIT_S)
                    continue
                if e.status == 503 and "extension is not connected" in str(e.error or ""):
                    wait_service(self.job, self.api, "the browser extension is not connected")
                    continue
                raise Stop(f"listing tab: {e}") from None
            except requests.exceptions.ConnectionError:
                wait_service(self.job, self.api, "the API server does not answer")
                if not resend:
                    raise TabLost("the connection was lost during next: a new tab, done products skipped") from None


def new_scroll_job(args: argparse.Namespace, shop: str, shops_root: str, root: str = JOBS_ROOT) -> Job:
    """A scroll job's folder: job.json (`new`'s settings, so paid_choices and status read it the same way, plus
    mode, total, tab, reopens) and an empty listing.jsonl that grows with each row taken."""
    job_id = f"{shop}-{args.category}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    folder = os.path.join(root, job_id)
    os.makedirs(folder)
    meta: JobMeta = {"shop": shop, "category": args.category, "queries": [args.query], "mode": "scroll",
            "paid": args.paid or args.paid_variants, "paid_variants": args.paid_variants,
            "reviews": args.reviews, "shops_root": shops_root, "created_at": _now(), "count": args.count,
            "excluded_known": 0, "exclude_known": args.exclude_known,
            "translate": not args.no_translate or args.publish, "publish": args.publish, "describe": args.describe,
            "free_only": not args.paid, "total": None, "tab": None, "batches": 0, "reopens": [], "screen": {}}
    if getattr(args, "draft", False):                     # 2026-11-16: only when set
        meta["draft"] = True
    if getattr(args, "dedupe", "off") != "off":
        meta["dedupe"] = args.dedupe
    write_atomic(os.path.join(folder, "job.json"), json.dumps(meta, ensure_ascii=False, indent=1))
    write_atomic(os.path.join(folder, "listing.jsonl"), "")
    return Job(folder)


def _reached(job: Job) -> bool:
    count = job.meta.get("count") or 0
    if not count:
        return False
    return counted(job, stages(job)) >= count


def _drain(job: Job, ctx: Context, run: dict) -> int | None:
    """The products with a stage left (collected to translated, and those that failed once), without the tab:
    the same next_key / one() as `run`. -> None, or 3 (a stop)."""
    while True:
        done = stages(job)
        key = next_key(job, done, staged=True)
        if key is None:
            return None
        code = take(job, ctx, key, done.get(key), run)
        if code:
            return code


def _reopen(job: Job, why: str, batch: int) -> int | None:
    """TabLost: a pause and then a new tab (None), or 3 when it is the REOPEN_MAX+1-th in REOPEN_WINDOW_S."""
    now = time.time()
    recent = [r for r in job.meta.get("reopens") or [] if now - r.get("t", 0) < REOPEN_WINDOW_S]
    if len(recent) >= REOPEN_MAX:
        reason = f"the listing tab lost {len(recent) + 1} times in {REOPEN_WINDOW_S // 60} min: {why}"
        job.log(None, "stop", reason=reason[:300])
        print(f"STOP: {reason}\n   scroll --job {job.id} to resume", flush=True)
        return 3
    wait = random.uniform(*REOPEN_WAIT_S)
    job.meta.setdefault("reopens", []).append({"at": _now(), "t": now, "batch": batch, "reason": why[:200]})
    job.save_meta()
    job.log(None, "reopen", batch=batch, reason=why[:300])
    print(f"   the listing tab is gone after batch {batch} ({why[:120]}): a new one in {round(wait)} s, done "
          "products skipped", flush=True)
    time.sleep(wait)
    return None


def _batch_rows(job: Job, answer: dict, screen: Any, known: set[str], out: dict[str, str],
                taken: set[str]) -> list[dict]:
    """The batch's rows to take: through the screen (once a product: `out` keeps why it was left out), not
    `known`, not taken in this tab; a product already in the job is skipped only at its final stage or closed.
    Every row left out is appended to screened.jsonl (at, batch, product_id, name, reason), once a product a run, so
    each leave-out can be audited (the owner, 2026-11-14: a lenient screen, nothing lost unseen)."""
    from listing_filter import source_key
    done, gone = stages(job), closed(job)
    keep: list[dict] = []
    left_out: list[dict] = []
    for row in answer["results"]:
        pid = str(row.get("product_id"))
        if pid in out:
            continue
        if row.get("is_ad"):
            # 2026-11-14 (골프채 풀세트, batch 1-2): an ad card links through Naver's ad redirect, not /products/<id>, so
            # the tab cannot click it (6 of 6 were card_not_found). Not taken here; the same product is taken when it
            # comes as an ordinary card, else `new` + `run` reach it by a search of its name. Logged once a run.
            if "ad:" + pid not in out:
                out["ad:" + pid] = "ad"
                left_out.append({"at": _now(), "batch": answer.get("batch"), "product_id": pid,
                                 "name": row.get("name"), "reason": "ad"})
            continue
        key = source_key(row, screen.namespace) or ""
        why = screen.reason(row) if key else "key_unavailable"
        if why is None and pid in known:
            why = "known"
        if why is not None:
            out[pid] = why
            left_out.append({"at": _now(), "batch": answer.get("batch"), "product_id": pid, "name": row.get("name"),
                             "reason": why})
            continue
        if key in taken or done.get(key) == job.final or key in gone:
            continue
        keep.append({**row, "key": key})
    if left_out:
        append_line(os.path.join(job.folder, "screened.jsonl"), *(json.dumps(x, ensure_ascii=False) for x in left_out))
    return keep


def scroll(job: Job, ctx: Context, tab: Tab, screen: Any, known: set[str]) -> int:
    """The scroll loop: the products with a stage first, then the listing batch by batch, each row taken at once,
    until has_more false or --count; then the products with a stage left. -> the exit code."""
    run = {"taken": 0, "started": time.monotonic(), "again": f"scroll --job {job.id}"}
    code = _drain(job, ctx, run)
    if code:
        return code
    out: dict[str, str] = {}                                   # product id -> why the screen left it out
    taken: set[str] = set()                                    # keys taken from this tab (reset with a new tab)
    batch = 0
    while not _reached(job):
        try:
            job.beat(key=None, n=0, stage="listing", since=_now())
            answer = tab.next() if tab.id else tab.open()
            batch = answer["batch"]
            try:
                screen.set_published(ctx["catalog"].keys())    # one() checks it again before a product
            except Exception:
                pass
            rows = _batch_rows(job, answer, screen, known, out, taken)
            job.meta["screen"] = dict(screen.counts)
            job.save_meta()
            job.log(None, "batch", batch=batch, rows=len(answer["results"]), taken=len(rows),
                    has_more=answer["has_more"])
            print(f"batch {batch}: {len(answer['results'])} rows, {len(rows)} to take (listing total "
                  f"{job.meta.get('total')}, has_more {answer['has_more']})", flush=True)
            have = {r["key"] for r in job.rows()}
            for row in rows:
                if _reached(job):
                    break
                if row["key"] not in have:
                    append_line(os.path.join(job.folder, "listing.jsonl"), json.dumps(row, ensure_ascii=False))
                taken.add(row["key"])
                code = take(job, ctx, row["key"], stages(job).get(row["key"]), run)
                if code:
                    return code
            if not answer["has_more"]:
                break
        except TabLost as e:
            tab.lost()
            taken.clear()
            code = _reopen(job, str(e), batch)
            if code:
                return code
        except Stop as e:
            job.log(None, "stop", reason=str(e)[:300])
            print(f"STOP: {e}\n   {run['again']} to resume", flush=True)
            return 3
        except LedgerError as e:
            job.log(None, "stop", reason=f"{type(e).__name__}: {e}"[:300])
            print(f"STOP: {type(e).__name__}: {e}\n   {run['again']} to resume", flush=True)
            return 3
        except (OSError, ConnectionError) as e:
            job.log(None, "stop", reason=f"listing tab: {type(e).__name__}: {e}"[:300])
            print(f"STOP: listing tab: {type(e).__name__}: {e}\n   {run['again']} to resume", flush=True)
            return 3
    tab.close()                                                # the adapter is free before the rest
    code = _drain(job, ctx, run)
    if code:
        return code
    done = stages(job)
    gone = closed(job)
    left = [r["key"] for r in job.rows() if done.get(r["key"]) != job.final and r["key"] not in gone]
    cards = sum(1 for why in gone.values() if why == "not_taken: card_not_found")
    job.log(None, "done", total=job.meta.get("total"), products=len(job.rows()), left=len(left),
            card_not_found=cards)
    end = f"--count {job.meta['count']} reached" if _reached(job) else "the listing's end"
    print(f"done ({end}): every product of the job is {job.final} or closed; {len(job.rows())} taken of the "
          f"listing's {job.meta.get('total')}" + (f"; {len(left)} not read (their card did not come again)"
                                                    if left else "")
          + (f"; {cards} card_not_found" if cards else "")
          + ("; the other mode can take them (new --exclude-known)" if left or cards else ""), flush=True)
    _dictionaries_reminder(job)
    _review_reminder(job)
    _same_item_reminder(job)
    return 0


def run_scroll(job: Job, ctx: Context, tab: Tab, screen: Any, known: set[str]) -> int:
    """scroll() with the tab closed however it ends: SIGTERM is turned into KeyboardInterrupt so the finally runs
    (by default SIGTERM skips it and the tab keeps the adapter: Fable review 4, 2026-11-14)."""
    def term(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt("SIGTERM")
    before = signal.signal(signal.SIGTERM, term)
    try:
        return scroll(job, ctx, tab, screen, known)
    except KeyboardInterrupt as e:
        job.log(None, "stop", reason=f"interrupted ({e or 'Ctrl+C'})")
        print(f"STOP: interrupted\n   scroll --job {job.id} to resume", flush=True)
        return 130
    finally:
        tab.close()
        signal.signal(signal.SIGTERM, before)


def cmd_scroll(args: argparse.Namespace) -> int:
    from keep_run import SHOPS_ROOT
    from package_measures import load_table
    from shop_stores import get_store
    if args.job:
        old = open_job(args.job)
        if old.meta.get("mode") != "scroll":
            print(f"stop: job {old.id} is not a scroll job: job.py run --job {old.id}")
            return 2
        job: Job | None = old
        shop, shops_root, what = old.shop, old.shops_root, f"job.py scroll --job {old.id}"
    else:
        if not args.query or not args.category:
            print("stop: a new scroll job needs --query and --category (or --job ID to resume one)")
            return 2
        if args.describe and not args.publish:
            print("stop: --describe needs --publish (a job without publication: describe.py <shop> after it)")
            return 2
        if not any(str(r["category_id"]) == args.category for r in load_table()["rows"]):
            print(f"stop: no category_measures.json row for {args.category}: ask the operator")
            return 2
        job, shop, shops_root = None, get_store().id.value, os.path.abspath(args.shops_root or SHOPS_ROOT)
        what = f"job.py scroll (a new job, {args.category} {args.query!r})"
    # the lock before a new job's folder: a refusal leaves no empty job for latest_job to pick
    return locked(shops_root, shop, what, lambda: _scroll(args, job, shop, shops_root))


def _scroll(args: argparse.Namespace, job: "Job | None", shop: str, shops_root: str) -> int:
    if job is None:
        job = new_scroll_job(args, shop, shops_root)
        print(f"job {job.id}: scroll {job.meta['queries'][0]!r} (target {args.count or 'the listing end'})",
              flush=True)
        _draft_first_line(args.publish, shop, args.category, getattr(args, "draft", False))
    sjob = job
    args.ran = sjob.folder                                     # main() tells the owner how it ended
    return _guarded(sjob, f"scroll --job {sjob.id}", lambda: _scroll_run(sjob))


def _scroll_run(job: Job) -> int:
    from deferred_log import DeferredLog
    from listing_filter import Screen
    ctx, code = _context(job)
    if ctx is None:
        return code
    store = ctx["store"]
    assert store.shopify
    try:
        published = ctx["catalog"].keys()
    except Exception as e:
        job.log(None, "stop", reason=f"shop check: {type(e).__name__}: {e}")   # no run ends without an event
        print(f"stop: shop check: {type(e).__name__}: {e}")
        return 3
    screen = Screen(job.category, store.shopify.namespace, published, DeferredLog(store.id.value).blocked())
    known = known_ids() - {str(r["product_id"]) for r in job.rows()} if job.meta.get("exclude_known") else set()
    job.meta["excluded_known"] = len(known)                    # its own products are not "known before"
    tab = Tab(job, ctx["api"])
    ctx["specs"] = tab.specs
    return run_scroll(job, ctx, tab, screen, known)


# ---- activate (draft first, 2026-11-16) ----------------------------------------------------------------------

def drafts(job: Job) -> list[str]:
    """The job's products published as drafts (ledger store_status DRAFT), in listing order; withdrawn ones are not
    published, so they are not here."""
    from publish import Shop
    ledger: Mapping[str, Mapping[str, Any]] = Shop(job.shop, job.shops_root).ledger()
    return [r["key"] for r in job.rows() if (ledger.get(r["key"]) or {}).get("store_status") == "DRAFT"]


def withdraw_lines(job: Job) -> list[str]:
    """`publish.py --withdraw` lines for the old copies a draft did not replace (replace_skipped, DRAFT_WHY) and that
    are still published: run on the owner's word once the new one is live."""
    import dedupe
    from publish import Shop
    ledger = Shop(job.shop, job.shops_root).ledger()
    pairs = {(e["key"], e.get("replaces")) for e in job.events()
             if e["event"] == "replace_skipped" and e.get("why") == DRAFT_WHY}
    return [f".venv/bin/python scripts/publish.py {job.shop} --withdraw {old} --reason {dedupe.REPLACED}{new}"
            for new, old in sorted(pairs) if old in ledger and new in ledger]


def cmd_activate(args: argparse.Namespace) -> int:
    """Every draft of the job live (publish.activate), on the owner's word after the lens review; --dry-run lists
    them. No job event (summary's `finished` reads the last one). Exit 1 when one failed."""
    import publish
    import transform_shops
    from shopify_catalog import CatalogError
    job = open_job(args.job)
    flagged = {p["key"] for p in same_item_open(job)}     # not activated before the review (2026-11-20)
    keys = [k for k in drafts(job) if k not in flagged]
    admin = None
    if keys and not args.dry_run:
        from shop_stores import get_store
        from shopify_admin import ProductsAdmin
        admin = ProductsAdmin(get_store(job.shop))
        admin.check_shop()
    shop, done, failed = publish.Shop(job.shop, job.shops_root), 0, 0
    for key in keys:
        if args.dry_run:
            print(f"{key}: would be activated")
            continue
        try:
            row = publish.activate(shop, key, admin)
        except CatalogError as e:
            failed += 1
            print(f"{key}: failed: {e}"[:300])
            continue
        done += row is not None                    # "not a draft here" (the ledger moved meanwhile) is not counted
        print(f"{key}: activated ({row['store_status']}) {row.get('admin_url', '')}" if row else
              f"{key}: not a draft here")
    print(f"activate {job.id}: {len(keys)} drafts" + ("" if args.dry_run else f", {done} activated, {failed} failed"))
    for key in sorted(flagged & set(drafts(job))):
        print(f"{key}: left a draft: a same-item candidate not reviewed (job.py status --job {job.id}); "
              f"publish.py {job.shop} --activate {key} on the owner's word after the review")
    lines = withdraw_lines(job)
    if lines:
        print("the old copies the drafts were to replace, still live (withdraw them on the owner's word once the new "
              "ones are live):")
        for line in lines:
            print("  " + line)
    if not transform_shops.reviewed(job.shop, job.category):
        print(f"category {job.category} is not marked reviewed: set reviewed=True in transform_shops.py on the "
              "owner's word (a dated comment)")
    return 1 if failed else 0


# ---- status --------------------------------------------------------------------------------------------------

def summary(job: Job) -> dict[str, Any]:
    done = stages(job)
    out = closed(job)
    events = job.events()
    counts = Counter(done.get(r["key"], "queued") if r["key"] not in out else "closed" for r in job.rows())
    held = {p["key"]: [h["code"] for h in p["held"]] for p in (_prepared(job) if os.path.exists(os.path.join(
        job.shops_root, job.shop, "prepared", "products.jsonl")) else []) if p["key"] in done and p["held"]}
    stops = [e for e in events if e["event"] == "stop"]
    ready = sum(1 for e in {e["key"]: e for e in events if e["event"] == "prepared"}.values()
                if e.get("status") == "ready" and done.get(e["key"]) == job.final)
    now = job.now()
    return {"ready": ready, "running": now, "job": job.id, "shop": job.shop, "category": job.category, "products": len(job.rows()),
            "stages": {s: counts.get(s, 0) for s in ("queued",) + BUILT + ("closed",)},
            "final": job.final, "not_built": [s for s in STAGES if s not in BUILT], "closed": out, "held": held,
            "failed_once": sorted({e["key"] for e in events if e["event"] == "failed"} - set(out)),
            "last_stop": stops[-1] if stops else None, "next": next_key(job, done),
            "finished": bool(events) and events[-1]["event"] == "done", "review": review_due(job)}


def cmd_status(args: argparse.Namespace) -> int:
    s = summary(open_job(args.job))
    try:                                            # a hint never breaks status
        s["sweep_due"] = sweep_due(open_job(args.job))
    except Exception:                               # noqa: BLE001
        s["sweep_due"] = None
    try:
        s["same_item"] = same_item_open(open_job(args.job))
    except Exception:                               # noqa: BLE001
        s["same_item"] = None
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    print(f"job {s['job']}: {s['products']} products; " + ", ".join(f"{k} {v}" for k, v in s["stages"].items()))
    for k, why in s["closed"].items():
        print(f"  closed {k}: {why}")
    for k, codes in s["held"].items():
        print(f"  held {k}: {codes}")
    if s["last_stop"]:
        print(f"  last stop: {s['last_stop']['at']} {s['last_stop']['reason']}")
    now = s["running"]
    if now:
        print(f"  running (pid {now['pid']}): [{now.get('n')}] {now.get('key')} {now.get('stage')} since "
              f"{now.get('since')}")
    else:
        print("  no runner")
    print(f"  ready {s['ready']}; next: {s['next']}; finished: {s['finished']}; not built yet: {s['not_built']}")
    _dictionaries_reminder(open_job(args.job))
    _review_reminder(open_job(args.job))
    _same_item_reminder(open_job(args.job))
    if s["sweep_due"]:
        print(f"  sweep due: {s['sweep_due']} (skill sweep)")
    return 0


# what builds a product, in git (sweep's "When", 2026-11-19): the scripts but their tests, the rule tables, the
# prompts and the dictionaries' backups
SWEEP_PATHS = (":(glob)scripts/*.py", ":(glob,exclude)scripts/test_*.py", ":(glob,exclude)scripts/conftest.py",
               ":(glob)scripts/*.json", "scripts/prompts", "scripts/dictionaries")


def code_changed_at() -> float | None:
    """The newest commit time of SWEEP_PATHS (git log, read only); None without git or a commit."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", *SWEEP_PATHS], cwd=os.path.dirname(SCRIPTS),
                             capture_output=True, text=True, timeout=10)
        return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _dicts_updated() -> float | None:
    """The newest mtime of the live dictionary files (translation_dicts' own list: a writer's .tmp file is not one of
    them); a file replaced or gone meanwhile is skipped."""
    import translation_dicts
    times = []
    for f in translation_dicts._files(translation_dicts.LIVE_ROOT, translation_dicts.BACKUP_ROOT):
        try:
            times.append(os.path.getmtime(f[2]))
        except OSError:
            continue
    return max(times) if times else None


def _utc(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(t))


def sweep_due(job: Job) -> str | None:
    """Why the shop's sweep (sweep.py) is older than what it judges: a commit to the build code (SWEEP_PATHS), the
    live dictionaries, this job's finish. The sweep's time is its older part (answers.json, store.json: --answers or
    --store alone refresh one); a part missing is due too. None when sweep/latest/ is newer, the shop has no publish
    ledger, or a runner holds the shop's lock (a sweep waits for it: no line while a job runs)."""
    shop_dir = os.path.join(job.shops_root, job.shop)
    if not os.path.exists(os.path.join(shop_dir, "publish", "published.jsonl")):
        return None
    try:
        ensure_free(job.shops_root, job.shop)
    except ShopBusy:
        return None
    runs = {n: os.path.getmtime(p) for n, p in ((n, os.path.join(shop_dir, "sweep", "latest", f"{n}.json"))
                                                 for n in ("answers", "store")) if os.path.exists(p)}
    if not runs:
        return "no sweep run yet"
    missing = [f"no {n} part yet" for n in ("answers", "store") if n not in runs]
    since = min(runs.values())
    events = job.events()
    done = (datetime.fromisoformat(events[-1]["at"]).timestamp()
            if events and events[-1]["event"] == "done" and events[-1].get("at") else None)
    newer = [f"{what} {_utc(t)}" for what, t in (("a commit to the build code", code_changed_at()),
                                                 ("the live dictionaries", _dicts_updated()),
                                                 (f"job {job.id} done", done))
             if t is not None and t > since]
    if not newer and not missing:
        return None
    return ", ".join(missing + ([f"since the last sweep ({_utc(since)}): " + ", ".join(newer)] if newer else []))


# ---- report, where, watch (job_report.py; read only, no lock) ------------------------------------------------

def _open(job_id: str | None) -> Job | None:
    """The job, or None (said on stderr) when there is no such job or its job.json lacks shop / category /
    shops_root."""
    try:
        return open_job(job_id)
    except (OSError, ValueError) as e:
        print(f"job.py: no job {job_id}: {e}", file=sys.stderr)
    except KeyError as e:
        print(f"job.py: job {job_id}: job.json has no {e}", file=sys.stderr)
    except SystemExit as e:
        print(f"job.py: {e}", file=sys.stderr)
    return None


def cmd_report(args: argparse.Namespace) -> int:
    import job_report
    job = _open(args.job)
    if job is None:
        return job_report.EXIT_USAGE
    folder = job.folder
    try:
        r = job_report.report(folder, args.event, args.since)
        rows = job_report.table(job_report.kept(job_report.events(folder), args.event, args.since)) \
            if args.table else []
    except LedgerError as e:
        print(f"job.py report: {e}", file=sys.stderr)
        return job_report.EXIT_BROKEN
    if args.table == "-":
        sys.stdout.write(job_report.table_text(rows))
        return 0
    if args.table:
        with open(args.table, "w", encoding="utf-8") as f:
            f.write(job_report.table_text(rows))
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        job_report.print_rows(job_report.report_lines(r))
    if args.table:
        print(f"table\t{args.table}\t{len(rows)}", file=sys.stderr)
    return 0


def cmd_where(args: argparse.Namespace) -> int:
    import job_report
    folders = job_report.job_folders(args.jobs_root)
    try:
        key = job_report.where_key(args.ref, folders, args.shop, args.shops_root)
        rows = job_report.where(key, folders)
    except job_report.WhereError as e:
        print(str(e), file=sys.stderr)
        return 1
    except LedgerError as e:
        print(f"job.py where: {e}", file=sys.stderr)
        return job_report.EXIT_BROKEN
    if args.json:
        print(json.dumps({"ref": args.ref, "key": key, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print(f"key\t{key}")
        job_report.print_rows(f"{r['job']}\t{r['at']}\t{r['event']}\t{job_report.one_line(r['detail'])}"
                              for r in rows)
    if not rows:
        print(f"{args.ref}: no job touched it", file=sys.stderr)
    return 0 if rows else 1


def cmd_watch(args: argparse.Namespace) -> int:
    import job_report
    job = _open(args.job)
    if job is None:
        return job_report.EXIT_USAGE
    try:
        r = job_report.watch(job.folder, job.now, args.every, args.timeout, start=args.start)
    except ValueError as e:                   # --from past the job's events
        print(f"job.py watch: {e}", file=sys.stderr)
        return job_report.EXIT_USAGE
    except LedgerError as e:
        print(f"job.py watch: {e}", file=sys.stderr)
        return job_report.EXIT_BROKEN
    print(json.dumps(r, ensure_ascii=False, indent=1) if args.json else job_report.watch_line(r), flush=True)
    return int(r["exit"])


def _dictionaries_reminder(job: Job) -> None:
    """A job that translates grows the live dictionaries: one line when their backup is due."""
    if job.final in ("translated", "published"):
        from translation_dicts import reminder
        line = reminder()
        if line:
            print("  " + line, flush=True)


def review_due(job: Job) -> dict[str, Any] | None:
    """Draft first (2026-11-16): the job's drafts awaiting the agent's lens review -> {drafts, category_reviewed,
    due (REVIEW_AFTER drafts, or the job done), commands (the lenses to run), withdraw (publish.py lines of the old
    copies the drafts did not replace)}; None for a job that does not publish or has no draft. The scripts never
    run a lens: they say when and which."""
    if job.final != "published":
        return None
    import transform_shops
    n = len(drafts(job))
    if not n:
        return None
    events = job.events()
    lens = ".venv/bin/python scripts/lens.py"
    return {"drafts": n, "category_reviewed": transform_shops.reviewed(job.shop, job.category),
            "due": n >= REVIEW_AFTER or (bool(events) and events[-1]["event"] == "done"),
            "commands": [f"{lens} section {job.shop} --job {job.id}",
                         f"{lens} price {job.shop} --category {job.category}",
                         f"{lens} held {job.shop} --job {job.id}",
                         f"{lens} brand {job.shop} --source none --category {job.category}",
                         f"{lens} dupes {job.shop} --category {job.category}"],
            "withdraw": withdraw_lines(job)}


def _same_item_reminder(job: Job) -> None:
    """The open same-item pairs (the Naver catalog or style code, 2026-11-20): never held, the product may be live;
    printed beside the review block (done, status, progress), independent of drafts."""
    try:                                            # a hint never breaks a run
        pairs = same_item_open(job)
    except Exception:                               # noqa: BLE001
        return
    if not pairs:
        return
    print(f"  same-item candidates: {len(pairs)} pairs of job {job.id} not reviewed (same Naver catalog or style "
          f"code; not held, live in a reviewed category): the agent checks each pair (skill visual-review: "
          f".venv/bin/python scripts/dedupe.py --pairs {job.shop} --job {job.id}), the owner decides", flush=True)
    for p in pairs[:10]:
        print(f"    {p['key'].split(':')[3]} ~ {p['of'].split(':')[3]} ({p['why']}): .venv/bin/python scripts/lens.py "
              f"products {job.shop} {p['key']} {p['of']}", flush=True)
    if len(pairs) > 10:
        print(f"    ... {len(pairs) - 10} more: job.py status --job {job.id} --json, key same_item", flush=True)


def _review_reminder(job: Job, due_only: bool = False) -> None:
    """The review block (draft first): the lenses to run through the skill visual-review, then the owner's word.
    Printed where the dictionaries' reminder is (done, status) and, `due_only`, on the progress line once due."""
    r = review_due(job)
    if not r or (due_only and not r["due"]):
        return
    if not r["due"]:
        print(f"  {r['drafts']} drafts await the lens review (due at {REVIEW_AFTER} drafts or when the job is done)",
              flush=True)
        return
    print(f"  review due: {r['drafts']} drafts of job {job.id} are not live; run the skill visual-review with:",
          flush=True)
    for c in r["commands"]:
        print("    " + c, flush=True)
    print("  report to the owner; then, on the owner's word only: withdraw the wrong ones (publish.py "
          f"{job.shop} --withdraw <key> --reason ...), .venv/bin/python scripts/job.py activate --job {job.id}"
          + ("" if r["category_reviewed"] else
             f", and mark category {job.category} reviewed=True in transform_shops.py"), flush=True)
    for line in r["withdraw"]:
        print("    once the new one is live: " + line, flush=True)


def _draft_first_line(publish: bool, shop: str, category: str, draft: bool = False) -> None:
    """One line at a job's creation: its products go DRAFT (a category not marked reviewed, or --draft)."""
    import transform_shops
    if publish and draft and transform_shops.reviewed(shop, category):
        print(f"draft: this job's new products go to the store as DRAFT (--draft); the lens review is due at "
              f"{REVIEW_AFTER} drafts or at the end (job.py status lists the commands), activation is the owner's "
              "word: job.py activate --job <id>", flush=True)
    elif publish and not transform_shops.reviewed(shop, category):
        print(f"draft first: category {category} is not marked reviewed: its products go to the store as DRAFT "
              f"(--count counts drafts); the lens review is due at {REVIEW_AFTER} drafts (job.py status lists the "
              "commands), activation is the owner's word", flush=True)


def _job_flags(p: argparse.ArgumentParser) -> None:
    """The settings `new` and `scroll` share."""
    p.add_argument("--paid", action="store_true", help="paid variants (and the category's paid add-ons) too; "
                   "without it the job collects and prepares only what costs nothing extra")
    p.add_argument("--paid-variants", action="store_true", help="the job's products take paid variants but no paid "
                   "add-on (the owner, 2026-11-11); the shop's other prepared records stay as they were")
    p.add_argument("--reviews", type=int, default=20)
    p.add_argument("--exclude-known", action="store_true", help="leave out products collected before anywhere")
    p.add_argument("--shops-root", help="the shops folder (default scripts/output/shops)")
    p.add_argument("--no-translate", action="store_true", help="stop each product at prepared (no model API)")
    p.add_argument("--publish", action="store_true", help="take each product on to Shopify (ACTIVE, "
                   "DRAFT in a category not marked reviewed) after translation: placement, then publish.py")
    p.add_argument("--describe", action="store_true", help="with --publish: write each product's description "
                   "before it is sent (describe.py: one model request a product)")
    p.add_argument("--draft", action="store_true", help="with --publish: the job's new products go DRAFT even in a "
                   "reviewed category (a pilot the owner activates after the lens review: job.py activate --job)")
    p.add_argument("--dedupe", choices=("off", "log", "on"), default="on", help="duplicates of a product sold by "
                   "another store (dedupe.py): on (the default, the owner 2026-11-15): skip and replace, hold a "
                   "same-UPC copy as a draft; log: the decisions only; off: none (JOB_AGENT.md)")


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, SCRIPTS)
    p = argparse.ArgumentParser(description="A job: one listing, one product at a time to prepared.")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--query", action="append", required=True, help="a listing query; twice for two (alternated)")
    n.add_argument("--category", required=True)
    n.add_argument("--count", type=int, default=0, help="keep the first N screened products (0: all of the "
                   "first read)")
    n.add_argument("--all", action="store_true", help="no count: whenever the snapshot is used up, read the "
                   "listings deeper (doubled, up to MAX_BATCHES_ALL) until they have no more products")
    n.add_argument("--batches", type=int, default=2, help="listing batches of ~50 per query to start with; doubled "
                   "(up to MAX_BATCHES) while fewer than --count products pass the screen")
    _job_flags(n)
    c = sub.add_parser("scroll", help="the listing in one held tab, each product read by a click on its card")
    c.add_argument("--query", help="the listing query (one)")
    c.add_argument("--category")
    c.add_argument("--count", type=int, default=0, help="stop once N products are at the job's final stage "
                   "(0: to the listing's end)")
    c.add_argument("--job", help="resume this scroll job (its own settings; the other flags are not read)")
    _job_flags(c)
    r = sub.add_parser("run")
    r.add_argument("--job")
    r.add_argument("--items", type=int, default=0, help="stop after N products (0: to the end)")
    f = sub.add_parser("refresh")
    f.add_argument("--job")
    f.add_argument("--more", type=int, default=50, help="add up to N products (the listings read deeper)")
    s = sub.add_parser("status")
    s.add_argument("--job")
    s.add_argument("--json", action="store_true")
    a = sub.add_parser("activate", help="every draft of the job live (ACTIVE), on the owner's word")
    a.add_argument("--job", required=True)
    a.add_argument("--dry-run", action="store_true", help="list what would be activated; no store call")
    import job_report
    since = job_report.iso_time
    rp = sub.add_parser("report", help="what a job did, from its events (read only)")
    rp.add_argument("--job")
    rp.add_argument("--event", help="only this event (published, not_taken, failed, ...)")
    rp.add_argument("--since", type=since, help="only events at or after this ISO time (a date, or no zone: UTC)")
    rp.add_argument("--table", metavar="F", help="one row a key to this .tsv (- for stdout)")
    rp.add_argument("--json", action="store_true")
    wh = sub.add_parser("where", help="one product's events and screen leave-outs across the jobs (read only)")
    wh.add_argument("ref", help="a key, a Naver product id, a handle or a link")
    wh.add_argument("--shop", help="the shop to resolve the ref in (default: the jobs' shops)")
    wh.add_argument("--jobs-root", default=JOBS_ROOT)
    wh.add_argument("--shops-root", help="default: each job's own shops root (job.json)")
    wh.add_argument("--json", action="store_true")
    wa = sub.add_parser("watch", help="wait until the owner must hear something; distinct exit codes (job_report)")
    wa.add_argument("--job")
    wa.add_argument("--every", type=int, default=20, help="return at every Nth published product of the job")
    wa.add_argument("--timeout", type=float, help="return (exit 9) after this many seconds")
    wa.add_argument("--from", dest="start", type=int, metavar="N",
                    help="count the events after the first N (the `next --from` of the last watch), not only new ones")
    wa.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    code = {"new": cmd_new, "run": cmd_run, "status": cmd_status, "refresh": cmd_refresh,
            "scroll": cmd_scroll, "activate": cmd_activate, "report": cmd_report, "where": cmd_where,
            "watch": cmd_watch}[args.cmd](args)
    if args.cmd in ("run", "scroll") and getattr(args, "ran", None):
        tell_owner(args.ran, code)
    return code


def tell_owner(folder: str, code: int) -> None:
    """How a run ended, to the owner (the owner, 2026-11-16; scripts/notify.py: NAVER_NOTIFY_WEBHOOK, else a macOS
    notification): 3 -> job_stop with the last stop's reason and the command that resumes; 0 with the job's `done`
    event last -> job_done. Nothing for 2 (refused), 130 (the owner's own Ctrl+C) or a run cut by --items. Never
    raises: a failed notice must not turn a stop into a traceback."""
    import notify
    try:
        job = Job(folder)
        events = job.events()
        again = f"job.py scroll --job {job.id}" if job.meta.get("mode") == "scroll" else f"job.py run --job {job.id}"
        if code == 3:
            stop: dict[str, Any] = next((e for e in reversed(events) if e["event"] == "stop"), {})
            notify.notify("job_stop", f"{job.id}: {stop.get('reason') or 'stopped'}"[:300], job=job.id,
                          key=stop.get("key"), resume=again)
        elif code == 0 and events and events[-1]["event"] == "done":
            st = summary(job)["stages"]
            notify.notify("job_done", f"{job.id}: done, {st[job.final]} {job.final}, {st['closed']} closed",
                          job=job.id, stages=st)
    except Exception as e:
        print(f"notify: not sent ({type(e).__name__}: {e})", flush=True)


if __name__ == "__main__":                 # description_images spawns workers that import this file again
    sys.exit(main())
