"""A job's events read back for the agent that runs it and for the owner (the owner's five tools, 2026-11-16): what a
job did (report), where one product went across the jobs (where), and a watcher that returns at once when the owner
must hear something (watch). Local files only (job.json, events.jsonl, screened.jsonl, the shop's files for a ref),
nothing is sent, nothing is written but the --table file; it never takes the shop's lock and never starts, resumes
or stops a runner. job.py wires the subcommands:

    .venv/bin/python scripts/job.py report [--job ID] [--event E] [--since T] [--table out.tsv | -] [--json]
    .venv/bin/python scripts/job.py where <ref> [--shop S] [--jobs-root DIR] [--shops-root DIR] [--json]
    .venv/bin/python scripts/job.py watch [--job ID] [--every 20] [--timeout S] [--json]

`--job` left out: the latest job (as `status`). A full path works too.

report: one `section<TAB>name<TAB>value` line each (job, events, event counts, the not_taken / deferred / failed
reasons by code, held codes, model cost, stops, waits); `--event E` keeps only that event, `--since T` (ISO, a date
or a time; no zone = UTC) only events at or after T, and everything is counted on what is kept. `--table F` writes
one row a key (key, last event, status, reason, held, handle, events, first, last), `-` to stdout. Exit 0, 1 a
broken events file (LedgerError), 2 usage or no such job (the read tools' codes: shop_view.py's docstring).

where: a ref (key, Naver product id, handle, link: shop_view.resolve over the jobs' shops, or --shop) -> every job
event of that product and every screen leave-out of its product id (screened.jsonl), one
`job<TAB>at<TAB>event<TAB>detail` line each, oldest first. A product id no shop file knows (a product left out
before it was prepared: a duplicate, card_not_found, a screen reason) is still found by its id in the events and
screened files. Exit 0 found, 1 nothing found or the ref names several products (the candidates on stderr),
2 usage.

watch: polls events.jsonl (and the runner through job.py's Job.now) every POLL_S and returns on the first of:

    0  every Nth published (the job's published events crossed a multiple of --every since the watch started)
    3  a stop event                     4  waiting (the server / the extension, or a network wait at try LONG_TRY+)
    5  a captcha not answered in time (captcha_again)          6  the listing tab reopened (scroll)
    7  done (also when the job was already done at the start)
    8  no runner (gone after it was seen, or none within START_GRACE_S)
    9  --timeout seconds passed         1  a broken events file      2  usage or no such job

Only events written after the watch started count (but `done` as the last event). One line on exit (`--json`: the
dict). A pending captcha is not in the job's log (scripts/captcha_watch.py reads GET /captcha). Restart the
watcher after each exit, as the runner goes on by itself (JOB_AGENT.md, 3. Watch).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Iterable

from shop_files import read_jsonl
from shop_view import RefError, cell as one_line, is_key, iso_time, resolve      # one ref resolver, one TSV cell

POLL_S = 10                       # seconds between two reads of events.jsonl
START_GRACE_S = 60                # watch: a runner that has not written now.json yet (a job just started)
LONG_TRY = 3                      # network_wait: from this try on it is a long wait (JOB_AGENT.md: "past a few tries")
WAITS = ("waiting", "network_wait", "reopen", "captcha_again", "back")
REASONS = ("not_taken", "deferred", "failed")
TABLE = ("key", "last_event", "status", "reason", "held", "handle", "events", "first", "last")

EXIT_PUBLISHED, EXIT_BROKEN, EXIT_USAGE, EXIT_STOP, EXIT_WAITING = 0, 1, 2, 3, 4
EXIT_CAPTCHA, EXIT_REOPEN, EXIT_DONE, EXIT_NO_RUNNER, EXIT_TIMEOUT = 5, 6, 7, 8, 9

_KEY = re.compile(r"[^\s:]+:[^\s:]+:\d+:\d+")       # shop:source:channel:id
_NOT_READY = re.compile(r"^not ready to publish \((.*)\)$")


# ---- reading ---------------------------------------------------------------------------------------------------

def events(folder: str) -> list[dict[str, Any]]:
    """The job's events; a cut-off last line is left out (the runner appends), a bad middle one is a LedgerError."""
    return [e for e in read_jsonl(os.path.join(folder, "events.jsonl"), tail_ok=True) if isinstance(e, dict)]


def meta(folder: str) -> dict[str, Any]:
    with open(os.path.join(folder, "job.json"), encoding="utf-8") as f:
        out: dict[str, Any] = json.load(f)
    return out


def _at(e: dict[str, Any]) -> datetime | None:
    try:
        return iso_time(str(e.get("at") or ""))
    except ValueError:
        return None


def reason_code(reason: str | None) -> str:
    """A reason without what changes product to product: `duplicate_of:<key>` -> duplicate_of, `not ready to publish
    (placement held: single_only)` -> placement held: single_only, `title:not_golf (why)` -> title:not_golf."""
    text = (reason or "").strip()
    m = _NOT_READY.match(text)
    if m:
        text = m.group(1)
    text = _KEY.sub("", text).split(" (")[0].strip().rstrip(":").strip()
    return text[:80] or "-"


def kept(evs: Iterable[dict[str, Any]], event: str | None = None, since: datetime | None = None) -> list[dict]:
    out = []
    for e in evs:
        if event and e.get("event") != event:
            continue
        if since:
            at = _at(e)
            if at is None or at < since:
                continue
        out.append(e)
    return out


# ---- report ----------------------------------------------------------------------------------------------------

def report(folder: str, event: str | None = None, since: datetime | None = None) -> dict[str, Any]:
    m, all_events = meta(folder), events(folder)
    evs = kept(all_events, event, since)
    reasons: dict[str, Counter] = {name: Counter() for name in REASONS}
    held_last: dict[str, list[str]] = {}
    cost: Counter = Counter()
    for e in evs:
        name = e.get("event")
        if name in reasons:
            reasons[name][reason_code(e.get("reason"))] += 1
        if name == "prepared" and e.get("key"):
            held_last[e["key"]] = list(e.get("held") or []) if e.get("status") == "held" else []
        if name in ("translated", "described") and isinstance(e.get("cost"), (int, float)):
            cost[name] += e["cost"]
    held = Counter(code for codes in held_last.values() for code in codes)
    final = "published" if m.get("publish") else "translated" if m.get("translate") else "prepared"
    return {
        "job": os.path.basename(os.path.normpath(folder)), "shop": m.get("shop"), "category": m.get("category"),
        "mode": m.get("mode") or "listing", "final": final, "created_at": m.get("created_at"),
        "filter": {"event": event, "since": since.isoformat() if since else None},
        "events": len(evs), "first": evs[0].get("at") if evs else None, "last": evs[-1].get("at") if evs else None,
        "keys": len({e["key"] for e in evs if e.get("key")}),
        "counts": dict(sorted(Counter(str(e.get("event")) for e in evs).items())),
        "reasons": {k: dict(v.most_common()) for k, v in reasons.items() if v},
        "held": dict(held.most_common()),
        "cost": {k: round(v, 4) for k, v in sorted(cost.items())},
        "stops": [{"at": e.get("at"), "key": e.get("key"), "reason": e.get("reason")} for e in evs
                  if e.get("event") == "stop"],
        "waits": [{"at": e.get("at"), "event": e.get("event"), "detail": _detail(e)} for e in evs
                  if e.get("event") in WAITS],
        "finished": bool(all_events) and all_events[-1].get("event") == "done",
    }


def report_lines(r: dict[str, Any]) -> list[str]:
    out = [f"job\t{k}\t{r[k]}" for k in ("job", "shop", "category", "mode", "final", "created_at", "finished")]
    out += [f"filter\t{k}\t{v}" for k, v in r["filter"].items() if v]
    out += [f"events\t{k}\t{r[k]}" for k in ("events", "keys", "first", "last")]
    out += [f"event\t{k}\t{v}" for k, v in r["counts"].items()]
    out += [f"{name}\t{code}\t{n}" for name, codes in r["reasons"].items() for code, n in codes.items()]
    out += [f"held\t{code}\t{n}" for code, n in r["held"].items()]
    out += [f"cost\t{k}\t{v}" for k, v in r["cost"].items()]
    out += [f"stop\t{s['at']}\t{one_line(s['reason'])}" for s in r["stops"]]
    out += [f"wait\t{w['at']}\t{w['event']}: {one_line(w['detail'])}" for w in r["waits"]]
    return out


def table(evs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row a key, first seen first: its last event, the last status / reason / held / handle any of its events
    had, how many events, the first and the last time."""
    rows: dict[str, dict[str, Any]] = {}
    for e in evs:
        key = e.get("key")
        if not key:
            continue
        row = rows.setdefault(key, {"key": key, "status": "", "reason": "", "held": "", "handle": "", "events": 0,
                                    "first": e.get("at")})
        row["last_event"], row["last"] = e.get("event"), e.get("at")
        row["events"] += 1
        for name in ("status", "reason", "handle"):
            if e.get(name):
                row[name] = str(e[name])
        if e.get("event") == "prepared":
            row["held"] = ",".join(e.get("held") or [])
    return list(rows.values())


def table_text(rows: list[dict[str, Any]]) -> str:
    return "\n".join(["\t".join(TABLE)] + ["\t".join(one_line(r.get(c, "")) for c in TABLE) for r in rows]) + "\n"


def _detail(e: dict[str, Any]) -> str:
    """The part of an event worth a line: status, reason, held codes, handle, a wait's attempt."""
    parts = []
    for name in ("status", "decision", "reason", "why", "replaces", "handle"):
        if e.get(name):
            parts.append(f"{name} {e[name]}" if name != "reason" else str(e[name]))
    if e.get("held"):
        parts.append("held " + ",".join(e["held"]))
    for name in ("attempt", "wait_s", "after_s", "batch", "run"):
        if e.get(name) is not None:
            parts.append(f"{name} {e[name]}")
    return "; ".join(parts)


# ---- where -----------------------------------------------------------------------------------------------------

def job_folders(jobs_root: str) -> list[str]:
    """The jobs (folders with a job.json), oldest first by their created_at (else the folder's name)."""
    found = []
    for path in glob.glob(os.path.join(jobs_root, "*", "job.json")):
        folder = os.path.dirname(path)
        try:
            created = str(meta(folder).get("created_at") or "")
        except (OSError, ValueError):
            continue
        found.append((created, os.path.basename(folder), folder))
    return [f for _, _, f in sorted(found)]


class WhereError(ValueError):
    """The ref names several products, or none and it is not a product id the jobs could know by itself."""


def where_key(ref: str, folders: list[str], shop: str | None = None, shops_root: str | None = None) -> str:
    """The key a ref names (shop_view.resolve over the jobs' shops, or `shop`), or the bare product id when the ref is
    one that no shop file knows (left out before it was prepared). WhereError for several or no match."""
    ref = ref.strip()
    if is_key(ref):
        return ref
    shops: set[tuple[str, str]] = set()             # (shop, shops root): a shop's jobs may use several roots
    for folder in folders:
        try:
            m = meta(folder)
        except (OSError, ValueError):
            continue
        if m.get("shop") and (shop is None or m["shop"] == shop):
            shops.add((m["shop"], shops_root or m.get("shops_root") or ""))
    if shop and shops_root:
        shops.add((shop, shops_root))
    found, errors = set(), []
    for name, root in sorted(shops):
        try:
            found.add(resolve(name, ref, root))
        except RefError as e:
            errors.append(str(e))
    if len(found) == 1:
        return found.pop()
    if len(found) > 1:
        raise WhereError(f"{ref}: {len(found)} products match in several shops, name one by its key: "
                         + "; ".join(sorted(found)))
    errors = list(dict.fromkeys(errors))
    several = [e for e in errors if "products match" in e]
    if several:
        raise WhereError("\n".join(several))
    if ref.isdigit():
        return ref
    raise WhereError("\n".join(errors) or f"{ref}: no job's shop to look it up in")


def where(key_or_pid: str, folders: list[str]) -> list[dict[str, Any]]:
    """Every event of the product (by key, or by its product id: the key's last part) and every screen leave-out of
    its product id, oldest first."""
    pid = key_or_pid.split(":")[-1]
    full = ":" in key_or_pid
    rows = []
    for folder in folders:
        job = os.path.basename(folder)
        for e in events(folder):
            key = e.get("key") or ""
            if (key == key_or_pid) if full else (key.split(":")[-1] == pid):
                rows.append({"job": job, "at": e.get("at"), "event": e.get("event"), "key": key, "detail": _detail(e)})
        for s in read_jsonl(os.path.join(folder, "screened.jsonl"), tail_ok=True):
            if isinstance(s, dict) and str(s.get("product_id")) == pid:
                rows.append({"job": job, "at": s.get("at"), "event": "screened", "key": None,
                             "detail": f"{s.get('reason')}; batch {s.get('batch')}"})
    return sorted(rows, key=lambda r: str(r["at"] or ""))


# ---- watch -----------------------------------------------------------------------------------------------------

def _trigger(e: dict[str, Any]) -> int | None:
    name = e.get("event")
    if name == "stop":
        return EXIT_STOP
    if name == "waiting" or (name == "network_wait" and int(e.get("attempt") or 0) >= LONG_TRY):
        return EXIT_WAITING
    if name == "captcha_again":
        return EXIT_CAPTCHA
    if name == "reopen":
        return EXIT_REOPEN
    if name == "done":
        return EXIT_DONE
    return None


WORDS = {EXIT_PUBLISHED: "published", EXIT_STOP: "STOP", EXIT_WAITING: "waiting", EXIT_CAPTCHA: "captcha",
         EXIT_REOPEN: "reopen", EXIT_DONE: "done", EXIT_NO_RUNNER: "no runner", EXIT_TIMEOUT: "timeout"}


def watch(folder: str, runner: Callable[[], Any], every: int = 20, timeout: float | None = None,
          poll: float = POLL_S, clock: Callable[[], float] = time.monotonic,
          sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Waits for the first thing the owner must hear (the module's docstring) -> {exit, why, job, published (the
    job's total), new (events since the start, by name), event (the one that ended it)}. `runner` returns the live
    runner's now.json or None (job.Job.now); `clock` / `sleep` are the test's."""
    every = max(1, every)
    t0 = clock()
    evs = events(folder)
    seen = len(evs)
    published = sum(1 for e in evs if e.get("event") == "published")
    start_published = published
    new: Counter = Counter()
    had_runner = False

    def done(code: int, e: dict[str, Any] | None = None) -> dict[str, Any]:
        why = WORDS[code] + (f": {one_line(_detail(e))}" if e and _detail(e) else "")
        return {"exit": code, "why": why, "job": os.path.basename(os.path.normpath(folder)), "published": published,
                "new_published": published - start_published, "new": dict(sorted(new.items())),
                "event": e}

    if evs and evs[-1].get("event") == "done":
        return done(EXIT_DONE, evs[-1])
    while True:
        alive = runner() is not None            # before the read: a runner that logs its stop and exits is seen
        had_runner = had_runner or alive
        evs = events(folder)
        for e in evs[seen:]:
            seen += 1
            new[str(e.get("event"))] += 1
            code = _trigger(e)
            if code is not None:
                return done(code, e)
            if e.get("event") == "published":
                published += 1
                if published // every > (published - 1) // every:
                    return done(EXIT_PUBLISHED, e)
        if not alive and (had_runner or clock() - t0 >= START_GRACE_S):
            return done(EXIT_NO_RUNNER)
        if timeout is not None and clock() - t0 >= timeout:
            return done(EXIT_TIMEOUT)
        sleep(poll if timeout is None else max(0.0, min(poll, timeout - (clock() - t0))))


def watch_line(r: dict[str, Any]) -> str:
    new = ", ".join(f"{k} {v}" for k, v in r["new"].items()) or "no new event"
    return f"watch {r['job']}: {r['why']}; published {r['published']} (+{r['new_published']}); since the start: {new}"


def print_rows(rows: Iterable[str]) -> None:
    for line in rows:
        print(line)
    sys.stdout.flush()
