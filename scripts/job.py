"""A job: one shop, one listing query, one product at a time from the listing to prepared (and, later, translated
and published; placement.py puts the whole shop into its sections before publication), resumable at any point. The agent that runs it reads scripts/JOB_AGENT.md.

Why one product per iteration (the owner, 2026-11-07): fewer reads in a burst, so less risk of a Naver block, and
every product is done (collected, its description images read, prepared) before the next one opens; a stop loses
nothing. The browser side (server, ext_product): the job's search tab stays open, the next product is searched in
it, the product tab of the previous read is closed; a login gate is reset from naver.com; a captcha waits for the
owner as always.

    .venv/bin/python scripts/job.py new --query "남성 골프채 풀세트" --category 50002788 [--count 40] [--batches 2]
                                        [--paid] [--exclude-known] [--shops-root DIR]
    .venv/bin/python scripts/job.py run [--job ID] [--items N]
    .venv/bin/python scripts/job.py status [--job ID] [--json]

Files, scripts/output/jobs/<job id>/:

    job.json       shop, category, query(s), settings, the shops root, the listing job(s) read
    listing.jsonl  the screened snapshot in listing order (row + key)
    events.jsonl   what no other file records, append-only: not_taken / deferred / failed / stop / done, with time
    tmp/           a product's line and photos until they are kept (keep_run), then removed

A product's stage is read from the files, not from the log: collected = its key in the shop's kept runs
(run_transform.latest_lines); images = the category's switch off, or a current sidecar (description_images.current);
prepared = its key in prepared/products.jsonl; translated = its key `translated` (or `held`: the transform held it,
nothing to translate) in translation/translated.jsonl. A job created with translation (`new`, the default since
2026-11-08; `--no-translate` leaves it out) takes each product to translated: right after it is prepared, through
translate.py (only that product goes to the model; the chain and its fallback as there). A product the model could
not translate is `failed` (tried again after the fresh ones, MAX_FAILS times); every provider down stops the run
(`run` again resumes). Published is not built; placed is placement.py, run on the whole shop before publication.

`new --count N` reads the listings deeper (batches doubled, up to MAX_BATCHES; a listing is read from the top
every time) until N products pass the screen; when `run` uses up the snapshot with fewer than N prepared, it
reads them deeper again and appends the new products (`refresh` does that by hand). Probed 2026-11-08: 12 batches
of one query in 110 s, 583 unique rows, no stall. Each product prints a start line and a done line (stage
times), and every REPORT_EVERY products a `== progress:` line; now.json says what the runner does (status).

Waits and stops: 409 (adapter busy): 30 s, up to 12 times. The extension not connected or the API server not
answering: /health polled RECONNECT_S (15 min), then on. A captcha not answered in time (GET /captcha
timed_out, not a ban): read again, the owner asked again, CAPTCHA_TRIES times. A 503 "naver error page:" / "adapter error:" (ENDPOINTS):
120 s, 2 more tries, then the product is `failed` and the run goes on (a failed product is tried again after the
fresh ones, at most MAX_FAILS times). Anything else that stops the source (a wall, a refused CDN, the extension not
connected, the server down) stops the run: `run` again resumes. Two products in a row partial for the same reason
stop the run (collect_guard).
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")
STAGES = ("collected", "images", "prepared", "translated", "placed", "published")   # placed: placement.py, run on
                                                                                    # the shop before publication
BUILT = ("collected", "images", "prepared", "translated")
BUSY_WAIT_S, BUSY_TRIES = 30, 12
ERROR_WAIT_S, ERROR_TRIES = 120, 2
MAX_FAILS = 2
PAUSE_S = 2
RECONNECT_WAIT_S, RECONNECT_S = 30, 900      # the extension / server gone: poll /health this long, then stop
CAPTCHA_TRIES = 6                            # a captcha not answered in time: the read asks the owner again
MAX_BATCHES = 40                             # listing batches of ~50 per query (probed 2026-11-08: 12 in 110 s)
REPORT_EVERY = 10
RETRYABLE = ("naver error page:", "adapter error:")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- the job folder ------------------------------------------------------------------------------------------

class Job:
    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "job.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        self.shop, self.category = self.meta["shop"], self.meta["category"]
        self.shops_root = self.meta["shops_root"]

    @property
    def final(self) -> str:
        """The stage a product of this job is taken to: translated, or prepared for a job without translation (and
        for a job created before translation was built)."""
        return "translated" if self.meta.get("translate") else "prepared"

    @property
    def id(self) -> str:
        return os.path.basename(self.folder)

    def rows(self) -> list[dict[str, Any]]:
        with open(os.path.join(self.folder, "listing.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

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
        with open(os.path.join(self.folder, "now.json"), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "at": _now(), **now}, f, ensure_ascii=False)

    def now(self) -> dict[str, Any] | None:
        try:
            with open(os.path.join(self.folder, "now.json"), encoding="utf-8") as f:
                now = json.load(f)
            os.kill(now["pid"], 0)                       # the runner is still there
            return now
        except (OSError, ValueError, KeyError):
            return None

    def save_meta(self) -> None:
        with open(os.path.join(self.folder, "job.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=1)

    def log(self, key: str | None, event: str, **detail: Any) -> None:
        with open(os.path.join(self.folder, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now(), "key": key, "event": event, **detail}, ensure_ascii=False) + "\n")


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
    rules = rules_for(job.shop)
    out = {}
    for row in job.rows():
        key = row["key"]
        if key not in latest:
            continue
        if key in prepared:                         # prepared also with the images' note (failed / partial)
            out[key] = "translated" if key in translated and job.final == "translated" else "prepared"
            continue
        out[key] = "collected"
        line = latest[key][2]
        cat = (line.get("specs") or {}).get("category") or {}
        try:
            off = not rules.category(cat.get("id"), cat.get("name")).description_images
        except ShopRulesMissing:
            off = True
        if off or current(load_sidecar(job.shop, key.split(":")[3], job.shops_root), line):
            out[key] = "images"
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


def next_key(job: Job, done: dict[str, str]) -> str | None:
    """The first snapshot key not at the job's final stage and not closed; fresh ones before those that failed."""
    out = closed(job)
    failed = {e["key"] for e in job.events() if e["event"] == "failed"}
    todo = [r["key"] for r in job.rows() if done.get(r["key"]) != job.final and r["key"] not in out]
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


def more_batches(listings: list[dict], batches: int) -> int | None:
    """The next listing depth to try when there are too few rows: double, while any listing has more; else None."""
    if batches >= MAX_BATCHES or not any(x.get("has_more") and x.get("status") == "done" for x in listings):
        return None
    return min(batches * 2, MAX_BATCHES)


def cmd_new(args: argparse.Namespace) -> int:
    from keep_run import SHOPS_ROOT
    from naver_api_client import NaverApiClient
    from package_measures import load_table
    from shop_stores import get_store
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
    meta = {"shop": store.id.value, "category": args.category, "queries": args.query, "paid": args.paid,
            "reviews": args.reviews, "shops_root": shops_root, "created_at": _now(), "count": args.count,
            "batches": batches, "listings": listings, "screen": counts, "excluded_known": len(known),
            "exclude_known": args.exclude_known, "translate": not args.no_translate}
    with open(os.path.join(folder, "job.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "listing.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"job {job_id}: {len(rows)} products ({batches} batches a query; screen: {counts}; known left out: "
          f"{len(known)})")
    return 0


def refresh(job: Job, api: Any, store: Any, need: int) -> int:
    """`need` more products for the job: the listings again, deeper (more_batches), rows not in the job appended.
    -> how many were added (0: the listings have no more)."""
    batches = more_batches(job.meta.get("listings") or [], job.meta.get("batches") or 2)
    if batches is None:
        return 0
    have = {r["key"] for r in job.rows()}
    known = known_ids() if job.meta.get("exclude_known") else set()
    rows, listings, counts = read_listings(api, store, job.meta["queries"], job.category, batches, have, known)
    rows = rows[:need]
    with open(os.path.join(job.folder, "listing.jsonl"), "a", encoding="utf-8") as f:
        f.write("".join(json.dumps({**r, "refresh": batches}, ensure_ascii=False) + "\n" for r in rows))
    job.meta.update(batches=batches, listings=listings)
    job.meta.setdefault("refreshes", []).append({"at": _now(), "batches": batches, "added": len(rows),
                                                 "screen": counts})
    job.save_meta()
    job.log(None, "refresh", batches=batches, added=len(rows))
    return len(rows)


def cmd_refresh(args: argparse.Namespace) -> int:
    from naver_api_client import NaverApiClient
    from shop_stores import get_store
    job = open_job(args.job)
    added = refresh(job, NaverApiClient(), get_store(), args.more)
    print(f"job {job.id}: {added} products added")
    return 0


# ---- run -----------------------------------------------------------------------------------------------------

class Stop(Exception):
    """The run must stop here (a wall, the extension, the server): `run` again resumes."""


def collect_with_waits(job: Job, api: Any, store: Any, table: dict, guard: Any, row: dict, tmp: str) -> Any:
    """CollectGuard over collect_product.collect, with the job's waits; -> Outcome, or None when the product failed
    (logged); raises Stop."""
    import requests
    from collect_guard import SourceStopped
    from collect_product import collect
    busy = errors = captchas = 0
    while True:
        try:
            return guard.run(row["key"], lambda: collect(
                api, store, table, row, os.path.join(tmp, "images", str(row["product_id"])),  # type: ignore[arg-type]
                query=row.get("query"), category=job.category, paid=job.meta["paid"], reviews=job.meta["reviews"]))
        except SourceStopped as e:
            error = str(e.error or "")
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
            if e.status == 503 and captchas < CAPTCHA_TRIES and _captcha_status(api) == "timed_out":
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


def one(job: Job, ctx: dict, key: str, stage_now: str | None, n: int = 0) -> str:
    """Take one product from its stage to prepared. -> what happened (for the line printed)."""
    import description_images
    import run_transform
    row = next(r for r in job.rows() if r["key"] == key)
    pid = str(row["product_id"])
    t0 = time.monotonic()
    if stage_now is None:
        try:
            published = ctx["catalog"].keys()                   # published meanwhile (read again every 5 min)
        except Exception as e:                                  # CatalogError / ShopNotConfigured: no shop check
            raise Stop(f"shop check: {type(e).__name__}: {e}") from None
        if key in published:
            job.log(key, "not_taken", reason="already_published")
            return "not taken: already published"
        tmp = os.path.join(job.folder, "tmp", pid)
        shutil.rmtree(tmp, ignore_errors=True)
        job.beat(key=key, n=n, stage="collect", since=_now())
        outcome = collect_with_waits(job, ctx["api"], ctx["store"], ctx["table"], ctx["guard"], row, tmp)
        if outcome is None:
            return "failed (collect)"
        if outcome.status in ("not_taken", "deferred"):
            job.log(key, outcome.status, reason=outcome.reason)
            shutil.rmtree(tmp, ignore_errors=True)
            return f"{outcome.status}: {outcome.reason}"
        kept = keep_line(job, {"key": key, **outcome.data}, tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        job.log(key, "collected", run=os.path.basename(kept), seconds=round(time.monotonic() - t0))
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
    if stage_now != "prepared":
        job.beat(key=key, n=n, stage="prepare", since=_now())
        try:
            run_transform.run(job.shop, None, job.shops_root)
        except Exception as e:                                   # a transform defect: stop, never loop on it
            raise Stop(f"prepare: {type(e).__name__}: {e}") from None
    done = {p["key"]: p for p in _prepared(job)}
    p = done.get(key)
    t3 = time.monotonic()
    if stage_now != "prepared":
        job.log(key, "prepared", status=p and p["status"], held=[h["code"] for h in (p or {}).get("held") or []],
                images_s=round(t2 - t1), prepare_s=round(t3 - t2))
    what = f"prepared: {p and p['status']}" + (f" {[h['code'] for h in p['held']]}" if p and p["held"] else "")
    times = f"collect {round(t1 - t0)} s, images {round(t2 - t1)} s, prepare {round(t3 - t2)} s"
    if job.final == "translated" and p:
        job.beat(key=key, n=n, stage="translate", since=_now())
        what += "; " + translate_one(job, ctx, key)
        times += f", translate {round(time.monotonic() - t3)} s"
    return f"{what} ({times})"


def translate_one(job: Job, ctx: dict, key: str) -> str:
    """The product through translate.py (only it goes to the model). -> what happened. A product the model could not
    translate is `failed` (tried again later); every provider down stops the run."""
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
        raise Stop(f"translate: no provider answered: {problems}"[:300])
    job.log(key, "failed", stage="translate", reason=problems[:300])
    return f"translate failed: {problems}"[:200]


def _prepared(job: Job) -> list[dict]:
    path = os.path.join(job.shops_root, job.shop, "prepared", "products.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def cmd_run(args: argparse.Namespace) -> int:
    from collect_guard import CollectGuard, RunStopped
    from deferred_log import DeferredLog
    from naver_api_client import NaverApiClient
    from package_measures import load_table
    from shop_stores import get_store
    from shopify_catalog import ShopCatalog
    job = open_job(args.job)
    store = get_store()
    if store.id.value != job.shop:
        print(f"stop: SHOP_STORE is {store.id.value}, the job is for {job.shop}")
        return 2
    ctx = {"api": NaverApiClient(), "store": store, "table": load_table(), "catalog": ShopCatalog(store),
           "guard": CollectGuard(DeferredLog(store.id.value))}
    if job.final == "translated":
        import translate
        try:
            ctx["translator"] = translate.build_chain(translate.keys_from_env())
        except translate.TranslateError as e:
            print(f"stop: translation: {e} (a job without it: job.py new ... --no-translate)")
            return 2
    taken = 0
    started = time.monotonic()
    print(f"job {job.id}: run ({len(job.rows())} products in the snapshot, target {job.meta.get('count') or 'all'})",
          flush=True)
    while not args.items or taken < args.items:
        done = stages(job)
        key = next_key(job, done)
        if key is None:
            target = job.meta.get("count") or 0
            have = sum(1 for r in job.rows() if done.get(r["key"]) == job.final)
            if target and have < target:
                print(f"the snapshot is used up with {have} of {target} {job.final}: reading the listings deeper",
                      flush=True)
                try:
                    added = refresh(job, ctx["api"], store, target - have)
                except Exception as e:
                    job.log(None, "stop", reason=f"refresh: {type(e).__name__}: {e}"[:300])
                    print(f"STOP: refresh: {e}\n   run again to resume", flush=True)
                    return 3
                print(f"   {added} products added", flush=True)
                if added:
                    continue
            job.log(None, "done")
            print(f"done: every product of the job is {job.final} or closed", flush=True)
            break
        n = [r["key"] for r in job.rows()].index(key) + 1
        name = (next(r for r in job.rows() if r["key"] == key).get("name") or "")[:50]
        print(f"[{n}/{len(job.rows())}] {key.split(':')[3]} {name}", flush=True)
        try:
            what = one(job, ctx, key, done.get(key), n)
        except (Stop, RunStopped) as e:
            if isinstance(e, RunStopped):                 # the guard deferred this product before it stopped
                job.log(key, "deferred", reason="run_stopped")
            job.log(key, "stop", reason=str(e)[:300])
            print(f"STOP at {key}: {e}\n   run again to resume", flush=True)
            return 3
        except (OSError, ConnectionError) as e:
            job.log(key, "stop", reason=f"{type(e).__name__}: {e}"[:300])
            print(f"STOP at {key}: {type(e).__name__}: {e}\n   run again to resume", flush=True)
            return 3
        taken += 1
        print(f"[{n}/{len(job.rows())}] {key.split(':')[3]} {what}", flush=True)
        if taken % REPORT_EVERY == 0:
            print("== " + progress(job, taken, time.monotonic() - started), flush=True)
        job.beat(key=None, n=n, stage="pause", since=_now())
        time.sleep(PAUSE_S)
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
            f"~{round(per)} s a product, ~{round(left * per / 60)} min left")


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
            "finished": bool(events) and events[-1]["event"] == "done"}


def cmd_status(args: argparse.Namespace) -> int:
    s = summary(open_job(args.job))
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
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, SCRIPTS)
    p = argparse.ArgumentParser(description="A job: one listing, one product at a time to prepared.")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--query", action="append", required=True, help="a listing query; twice for two (alternated)")
    n.add_argument("--category", required=True)
    n.add_argument("--count", type=int, default=0, help="keep the first N screened products (0: all)")
    n.add_argument("--batches", type=int, default=2, help="listing batches of ~50 per query to start with; doubled "
                   "(up to MAX_BATCHES) while fewer than --count products pass the screen")
    n.add_argument("--paid", action="store_true", help="paid variants too")
    n.add_argument("--reviews", type=int, default=20)
    n.add_argument("--exclude-known", action="store_true", help="leave out products collected before anywhere")
    n.add_argument("--shops-root", help="the shops folder (default scripts/output/shops)")
    n.add_argument("--no-translate", action="store_true", help="stop each product at prepared (no model API)")
    r = sub.add_parser("run")
    r.add_argument("--job")
    r.add_argument("--items", type=int, default=0, help="stop after N products (0: to the end)")
    f = sub.add_parser("refresh")
    f.add_argument("--job")
    f.add_argument("--more", type=int, default=50, help="add up to N products (the listings read deeper)")
    s = sub.add_parser("status")
    s.add_argument("--job")
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    return {"new": cmd_new, "run": cmd_run, "status": cmd_status, "refresh": cmd_refresh}[args.cmd](args)


if __name__ == "__main__":                 # description_images spawns workers that import this file again
    sys.exit(main())
