"""A held listing tab (BETA, the extension transport): one search.shopping results tab kept open between HTTP
calls, walked batch by batch, its products read by a click on their cards in that same tab (job.py scroll).
Routes: POST /listing-tabs (open), POST /listing-tabs/<id>/next, GET /listing-tabs/<id>/specs, DELETE
/listing-tabs/<id>.

Why (the owner 2026-11-14): a job that searches each product by its name misses ~1.8% of them (card_not_found)
and loads a search page per product; here the listing is read once, top to bottom, and every product is one click
away. The other mode (POST /listings, then /products/specs per product) is unchanged.

Probed 2026-11-14 (research probes 1-3, query 남성 골프채 풀세트, then two narrow ones):
  * the listing tab survives the clicks: each card opens a NEW tab (newTabId in 16 + 30 + 4 clicks), closing it
    brings Chrome back to the listing tab, and a scroll after the clicks brings the next batch; 22 min idle was
    fine;
  * the list is virtualized: older batches leave the DOM (batch 1: 0 of 36 cards left after 10 batches, ~800-900
    cards held), the CURRENT batch is always whole in it: a batch's products are read right after it came;
  * a click right after a batch came opened another product 2 times in 16 (the layout shifting under the click):
    the card is wheeled in and steady first, the opened URL checked, one more click (ext_product._read_card
    steady=True; 0 wrong in 30);
  * the end: the last batch carries hasMore=false and the first batch's `total` is the listing's size (53 and 122
    seen; /products/count does not predict it). A scroll after the end brings nothing or a repeat of the last
    batch, so an ended tab answers next with has_more false without scrolling. No batch while hasMore is true is a
    stall: a stop, not the end.

One session at a time (one browser, one adapter user): it holds listing_jobs._adapter from open to close, so a
listing job or a /products/specs read meanwhile answers 409 naming it (listing_jobs.holder). A session lock keeps
its own calls in turn: next and specs answer 409 while another of its calls runs; open and close wait for it (a
call left running after a client's Ctrl+C must not close the next session's tabs). No idle timer: a job that died
without DELETE holds the adapter until the next open, a DELETE or a server restart.

410 (TabGone) is the one "the session is gone" signal: unknown id (closed, replaced, the server restarted), the
listing tab closed or no longer a search page, an adapter error on it, a login gate, a card that opened in the
listing tab itself (its product is still answered 200; the next call is 410). A caller opens a new tab and skips
what it has done. Walls as elsewhere (R-EXT-3): a ban, a refused batch or a stall end the session, 503 `wall:`; a
captcha not answered on a product page closes only that page's tab, 503 `wall: captcha ...`, the session lives.
"""
import os
import secrets
import threading
import time
from datetime import datetime, timezone

import ext_listing
import ext_product
import listing_jobs
from ext_bridge import ExtError
from naver_shopping import api, composite
from notify import notify

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "listing-tabs")
TAB_ID = listing_jobs.JOB_ID          # the same id format as a listing job's
NOT_CONNECTED = ("the browser extension is not connected: open Chrome with the naver-scrap adapter loaded "
                 "(extension/README.md)")

_lock = threading.Lock()     # the session's calls in turn: next / specs never wait (409), open / close do
_session = {}                # id, tab, query, batch, has_more, total, pending, out_dir


class TabGone(ext_product.AdapterError):
    """The listing tab session is gone (closed, replaced, lost its tab or its position): open a new one."""
    status = 410


# ---- session ------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bridge():
    """The connected bridge, else 503 (job.py waits for the extension and calls again)."""
    if listing_jobs.start_bridge() is None or not listing_jobs._bridge.wait_connected(0):
        raise ext_product.AdapterError(NOT_CONNECTED)
    return listing_jobs._bridge


def _end(why):
    """Close the session: every adapter tab, the holder text, the adapter lock. Under _lock; idempotent."""
    if not _session:
        return
    ext_listing.log(f"listing tab {_session['id']} closed: {why}")
    bridge = listing_jobs._bridge
    if bridge is not None:
        ext_product._close_tabs(bridge)          # the listing tab and anything it opened (never raises)
    _session.clear()
    listing_jobs.holder = None
    listing_jobs._adapter.release()


def _gone(sid, why):
    _end(why)
    return TabGone(f"listing tab {sid}: {why}; open a new one")


def _live(sid):
    """The session's bridge and listing tab, checked at the top of next / specs. -> (bridge, tab)."""
    if not _session or _session["id"] != sid:
        raise TabGone(f"listing tab {sid} is gone (closed, replaced by a new one, or the server restarted); "
                      "open a new one")
    bridge = _bridge()
    tab = _session["tab"]
    try:
        url = next((t.get("url") or "" for t in bridge.call("tabs") or [] if t.get("tabId") == tab), None)
    except ExtError as e:
        raise _gone(sid, f"the adapter failed on the listing tab ({e})")
    if url is None:
        raise _gone(sid, "the listing tab was closed")
    if "search.shopping.naver.com" not in url:            # the same check as ext_listing.search_again
        raise _gone(sid, f"the listing tab is no longer a search page ({url[:80]})")
    return bridge, tab


def _turn(sid):
    """next / specs take the session lock without waiting."""
    if not _lock.acquire(blocking=False):
        raise ext_product.AdapterBusy(f"listing tab {sid} is busy with another call, retry when it is done")


def _rows(batch, batch_no, query):
    """The batch's Naver store products as listing rows (/listings/<id>/products' shape), unique in the batch;
    repeats across batches are the caller's to drop (no seen set here)."""
    rows, ids = [], set()
    for product in composite.products(batch):
        row = composite.listing_row(product)
        if row is None or row["product_id"] in ids:
            continue
        ids.add(row["product_id"])
        row.update(query=query, batch=batch_no, seen_at=_now())
        rows.append(row)
    return rows


def _take():
    """The next pending batch -> the answer. A batch with hasMore=false ends the listing: what is left pending
    (a repeat of it) is dropped and no scroll is made after it."""
    batch = _session["pending"].pop(0)
    _session["batch"] += 1
    _session["has_more"] = bool(batch.get("hasMore"))
    if not _session["has_more"]:
        _session["pending"] = []
    rows = _rows(batch, _session["batch"], _session["query"])
    ext_listing.log(f"listing tab {_session['id']}: batch {_session['batch']}, {len(rows)} rows, cursor "
                    f"{batch.get('cursor')} of total {_session['total']}, has_more {_session['has_more']}")
    return _answer(rows)


def _answer(rows):
    return {"id": _session["id"], "query": _session["query"], "batch": _session["batch"],
            "has_more": _session["has_more"], "total": _session["total"], "results": rows}


# ---- calls --------------------------------------------------------------------------

def open_tab(query):
    """A new session on the listing for `query` (a previous one is closed first) -> its first batch."""
    with _lock:
        _end("replaced by a new open")
        bridge = _bridge()
        if not listing_jobs._adapter.acquire(blocking=False):
            raise ext_product.AdapterBusy(f"the adapter is busy ({listing_jobs.who()}), retry when it is done")
        sid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        out_dir = os.path.join(OUTPUT_ROOT, sid)
        _session.update(id=sid, tab=None, query=query, batch=0, has_more=True, total=None, pending=[],
                        out_dir=out_dir)
        listing_jobs.holder = f"listing tab {sid} (since {_now()}); free it with DELETE /listing-tabs/{sid}"
        try:
            os.makedirs(out_dir, exist_ok=True)
            ext_product._close_tabs(bridge)      # orphans of an earlier session or read (a restart, a 410)
            ext_product._home.pop("tab", None)   # ... the kept search tab among them
            tab, why = ext_listing.open_search(bridge, query, out_dir)
            if tab is None:
                raise ext_product.PageBlocked(f"wall: {why}")
            _session["tab"] = tab
            first = composite.first_batch(
                (bridge.call("page", tabId=tab, headChars=ext_listing.FULL_HTML) or {}).get("html"))
            if first is None:
                raise ext_product.AdapterError("adapter error: no first batch in the search page HTML "
                                               "(layout changed?)")
            _session.update(total=first.get("total"), pending=[first])
            ext_listing.log(f"listing tab {sid} open for {query!r}: tab {tab}, total {first.get('total')}")
            return _take()
        except Exception as e:                   # the session never stays half-open: tabs, holder, adapter freed
            _end(f"open failed: {type(e).__name__}: {e}")
            if isinstance(e, ExtError):
                raise ext_product.AdapterError(f"adapter error: opening the listing for {query!r}: {e}")
            raise


def next_batch(sid):
    """The session's next batch: one already fetched, else a scroll for it; after the end, has_more false and no
    rows, without a scroll."""
    _turn(sid)
    try:
        bridge, tab = _live(sid)
        if _session["pending"]:
            return _take()
        if not _session["has_more"]:
            return _answer([])
        n = _session["batch"] + 1
        try:
            ext_listing.rest(_session["batch"])
            captures = ext_listing.next_batches(bridge, tab)
            if not captures:
                try:
                    walled = not ext_listing.check(bridge, tab, f"batch-{n}", _session["out_dir"])
                except ext_listing.LoginGate as e:
                    raise _gone(sid, f"a login gate while scrolling ({e})")
                if walled:
                    _end(f"a wall while scrolling for batch {n}")
                    raise ext_product.PageBlocked(f"wall: listing tab {sid}: a wall while scrolling for batch {n}")
                captures = ext_listing.next_batches(bridge, tab)
            # the same stall / refused-batch stops as ext_listing.walk: a change here is made there too
            if not captures:
                notify("stalled", f"Listing tab for {_session['query']!r} stalled after {n - 1} batches")
                _end(f"stalled before batch {n}")
                raise ext_product.PageBlocked(f"wall: listing tab {sid}: stalled, the page loaded no batch {n} "
                                              "while hasMore was true")
            for capture in captures:
                parsed = composite.batch_from_answer(capture.get("body"))
                if capture.get("status") != 200 or parsed is None:
                    shot = ext_listing.screenshot(bridge, tab, _session["out_dir"], "batch-refused")
                    notify("blocked", f"Listing tab for {_session['query']!r} refused (HTTP {capture.get('status')})",
                           screenshot=shot)
                    _end(f"batch {n} refused: HTTP {capture.get('status')}")
                    raise ext_product.PageBlocked(f"wall: listing tab {sid}: batch {n} refused: "
                                                  f"HTTP {capture.get('status')}")
                _session["pending"].append(parsed)
        except ExtError as e:                    # every op here is on the listing tab
            raise _gone(sid, f"the adapter failed on the listing tab ({e})")
        return _take()
    finally:
        _lock.release()


def specs(sid, product):
    """The /products/specs answer for `product`, its card clicked in the session's listing tab (no search)."""
    _turn(sid)
    try:
        bridge, tab = _live(sid)
        query = _session["query"]
        details = api.product_details(product)       # before the click: a box failure costs no page load
        product_id = details["id"]
        out_dir = os.path.join(ext_product.OUTPUT_ROOT, datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{product_id}")
        os.makedirs(out_dir, exist_ok=True)
        started = time.monotonic()
        captcha_before = ext_listing.captcha_state()
        opened = {}
        try:
            try:
                selector = ext_product._card(bridge, tab, product_id)
            except ExtError as e:
                raise _gone(sid, f"the adapter failed on the listing tab ({e})")
            if not selector:
                raise ext_product.CardMissing(f"product {product_id} has no card in the listing tab for {query!r} "
                                              f"(batch {_session['batch']})")
            page = ext_product._read_card(bridge, tab, product_id, selector, query, out_dir, opened, steady=True)
        except ext_listing.LoginGate as e:
            raise _gone(sid, f"a login gate on product {product_id} ({e})")
        except ext_product.PageBlocked as e:
            captcha = ext_listing.captcha_state()
            if captcha != captcha_before and captcha.get("status") == "timed_out":
                raise ext_product.PageBlocked(f"wall: captcha not answered on product {product_id}; the listing tab "
                                              "is kept")
            _end(f"a wall on product {product_id}")
            raise ext_product.PageBlocked(f"{e}; the listing tab is closed")
        except ExtError as e:
            if opened.get("page_tab") in (None, tab):
                raise _gone(sid, f"the adapter failed on the listing tab ({e})")
            raise ext_product._adapter_error(product_id, e)
        finally:
            if _session.get("id") == sid:
                left = ext_product._close_tabs(bridge, keep=tab)
                if opened.get("page_tab") == tab:            # the card opened in the listing tab: position lost
                    _end(f"product {product_id}'s card opened in the listing tab itself")
                else:
                    print(f"ext-product: tabs left: {left} (listing tab {'kept' if left else 'none'})", flush=True)
        ext_product._read_log(product_id, started, selector, page)
        return ext_product._specs_tail(details, page, query, out_dir)
    finally:
        _lock.release()


def close(sid):
    """End the session `sid` (waits for a call of it still running). Idempotent: an unknown id is closed too."""
    with _lock:
        if _session.get("id") == sid:
            _end("closed by its caller")
    return {"id": sid, "closed": True}
