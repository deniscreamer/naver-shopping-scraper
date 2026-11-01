"""Listing jobs behind the HTTP API (BETA): POST /listings starts one
ext_listing.walk in a thread through the owner's Chrome (extension/), GET
/listings/<id> reports it, GET /listings/<id>/products pages its rows. Callers
(scripts/) never learn that a browser and an adapter are underneath.

Why a job and not one request: a whole listing takes minutes (~50 products
per batch, ~2-4 s a batch) and a captcha can hold it for HUMAN_WAIT_S while
the owner solves it. One job at a time: there is one browser, and Naver bans
bursts (server/docs/EXTENSION.md).

State: the job's summary dict (ext_listing.walk updates it batch by batch)
and its listing.jsonl under server/output/listings/<id>/. Jobs are kept in
memory; after a restart a finished job is still read from its summary.json.
"""
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone

import ext_listing
from ext_bridge import ExtBridge, ExtError

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "listings")
PER_PAGE = 50
JOB_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
PUBLIC = ("id", "query", "status", "max_batches", "batches", "kept", "ads", "total", "cursor", "has_more",
          "stop", "started_at", "finished_at")

_lock = threading.Lock()
_jobs = {}                  # id -> summary dict
_bridge = None


class Busy(Exception):
    """Another listing job is running."""


class NoExtension(Exception):
    """The adapter is not connected (Chrome closed, extension not loaded)."""


# ---- bridge -------------------------------------------------------------------------

def start_bridge():
    """Start the WebSocket bridge once, at server start. Never raises: without
    it (no websockets, port taken) /listings answers 503 and the rest works."""
    global _bridge
    if _bridge is None:
        try:
            _bridge = ExtBridge().start()
        except Exception as e:
            print(f"listing-jobs: extension bridge not started: {type(e).__name__}: {e}")
    return _bridge


def stop_bridge():
    if _bridge is not None:
        _bridge.stop()


def extension_status():
    if _bridge is None:
        return "off"
    return "connected" if _bridge.wait_connected(0) else "disconnected"


# ---- jobs ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _out_dir(job_id):
    return os.path.join(OUTPUT_ROOT, job_id)


def _run(job_id, summary):
    code = 1
    try:
        code = ext_listing.walk(_bridge, summary["query"], _out_dir(job_id), summary["max_batches"], False, summary)
    except Exception as e:                       # ExtError (adapter gone / op timeout) or a bug
        summary["stop"] = f"adapter error: {e}" if isinstance(e, ExtError) else f"job failed: {type(e).__name__}: {e}"
        try:
            ext_listing.finish(summary, _out_dir(job_id), 1)
        except OSError:
            pass
    finally:                                     # a job never stays "running"
        summary["status"] = "done" if code == 0 else "stopped"


def start(query, max_batches=0):
    """-> the new job's public view. Busy / NoExtension when it cannot start."""
    with _lock:
        running = [j for j in _jobs.values() if j["status"] in ("running", "captcha")]
        if running:
            raise Busy(running[0]["id"])
        if start_bridge() is None or not _bridge.wait_connected(0):     # a port freed later is picked up
            raise NoExtension()
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        os.makedirs(_out_dir(job_id), exist_ok=True)
        summary = _jobs[job_id] = {"id": job_id, "query": query, "status": "running", "max_batches": max_batches,
                                   "batches": 0, "kept": 0, "ads": 0, "stop": None, "started_at": _now()}
    threading.Thread(target=_run, args=(job_id, summary), daemon=True, name=f"listing-{job_id}").start()
    return view(summary)


def view(summary):
    return {k: summary.get(k) for k in PUBLIC}


def get(job_id):
    """-> the job's public view, or None. A job from before a restart is read from disk."""
    if not JOB_ID.match(job_id or ""):
        return None
    with _lock:
        summary = _jobs.get(job_id)
    if summary is not None:
        return view(summary)
    path = os.path.join(_out_dir(job_id), "summary.json")
    if not os.path.exists(path):
        if os.path.isdir(_out_dir(job_id)):      # the server stopped while it ran: its rows so far remain
            return view({"id": job_id, "status": "stopped", "stop": "server restarted mid-run"})
        return None
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    summary.update(id=job_id, status="done" if str(summary.get("stop", "")).startswith(("hasMore", "--max")) else "stopped")
    return view(summary)


def products(job_id, page):
    """-> {job_id, status, results, pagination} for one page of rows, or None (unknown job)."""
    job = get(job_id)
    if job is None:
        return None
    rows, count = [], 0
    start_at = (page - 1) * PER_PAGE
    path = os.path.join(_out_dir(job_id), "listing.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    break                        # the line being written right now
                if start_at <= count < start_at + PER_PAGE:
                    rows.append(json.loads(line))
                count += 1
    return {"job_id": job_id, "status": job["status"], "results": rows,
            "pagination": {"page": page, "items_per_page": PER_PAGE, "total_count": count,
                           "total_pages": -(-count // PER_PAGE)}}
