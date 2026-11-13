"""BETA: the search.shopping.naver.com listing for a query, read through the
owner's own Chrome (extension/ + ext_bridge.py). Why not over HTTP or our own
Chrome, and why not a direct fetch: server/docs/EXTENSION.md.

    .venv/bin/python server/ext_listing.py "남성 골프채 풀세트"
    .venv/bin/python server/ext_listing.py "남성 골프채 풀세트" --max-batches 20 --out golf-mens

Path, like a person (2026-11-01): www.naver.com -> mouse click on 쇼핑 (it
opens a new tab) -> click the shopping search box, type the query key by key,
Enter -> search.shopping.naver.com/ns/search. The first batch is read from
that page's HTML; every next batch is loaded by the PAGE when the wheel
scrolls to the end of the list, and the adapter copies the page's own
paged-composite-cards answer. Until hasMore=false or --max-batches.

Walls: a captcha is reported (notify.py) and waited for HUMAN_WAIT_S while
the human solves it in that Chrome window; a ban page ("접속이 일시적으로 제한",
HTTP 418) or any refused batch stops the run, never retried. A login gate
(nid.naver.com) is never waited for (the owner 2026-11-07: there is no account;
the naver.com -> 쇼핑 path again resets the session): check raises LoginGate,
open_search closes its tabs and takes the path again (LOGIN_RESETS times).

Output under server/output/ext-listing/<run>/:
  listing.jsonl  one line per unique Naver store product (composite.listing_row
                 + query / batch / seen_at); ads are kept, flagged is_ad
  summary.json   counts, last cursor, total, stop reason
summary.json is written on every exit. Exit code: 0 done or --max-batches reached;
1 stalled, layout changed (no search box / no first batch) or an adapter error;
2 the extension did not connect; 3 a wall (captcha not solved, login gate after the resets, ban page, refused batch).
"""
import argparse
import base64
import html as html_lib
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone

import config
from ext_bridge import ExtBridge, ExtError
from naver_shopping import composite
from notify import notify

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "ext-listing")
HOME = "https://www.naver.com/"
SHOPPING_LINK = 'a.link_service[href="https://shopping.naver.com/ns/home"]'
SEARCH_BOXES = ('input[class*="_searchInput_search_text"]', 'input[placeholder]', 'input[type="search"]')
LISTING = "paged-composite-cards"
CONNECT_WAIT_S = 600       # for the extension to (re)connect
HUMAN_WAIT_S = config.NAVER_CAPTCHA_WAIT_S     # a captcha is reported and waited for this long (default 600 s)
CAPTCHA_INPUT = 'input[type="text"]'           # the answer field on Naver's captcha page (2026-11-05)
SCROLLS_PER_BATCH = 25     # wheel scrolls before a batch counts as stalled
# 2026-11-12, the owner: a long listing read (jobs read 32 to 200 batches a query from the top) is spread out, not
# one burst: a short random rest before each next batch is scrolled for, a longer one every REST_EVERY batches
BATCH_REST_S = (3, 7)
REST_EVERY, LONG_REST_S = 10, (20, 40)
FULL_HTML = 5_000_000      # chars: the whole ns/search document (~0.7 MB)
# a human clears these in the window; NOT "ncpt.naver.com" alone (real pages load it too);
# the login gate is told by the URL (nid.naver.com): "nidlogin.login" is also an ordinary header link
HUMAN_WALLS = ('title="captcha"', "wtm_captcha")
# these end the run
HARD_WALLS = ("접속이 일시적으로 제한", "internal-error", "에러페이지")
LOGIN_RESETS = 2           # a login gate: the naver.com path again, this many times
# the search page's own box and its clear button (probed 2026-11-07: the clear button is the visible one; the
# "_searchInput_button_delete" one is 0 x 0); typing without clearing inserts at the caret
SEARCH_BOX = 'input[class*="_searchInput_search_text"]'
SEARCH_CLEAR = 'button[class*="_searchInput_button_clear"]'


class LoginGate(Exception):
    """Naver's login page (nid.naver.com) on the way: not waited for, the path is taken again."""


def log(msg):
    print(f"ext-listing: {msg}", flush=True)


def pause(a, b):
    time.sleep(random.uniform(a, b))


# ---- walls --------------------------------------------------------------------------

def screenshot(bridge, tab, out_dir, name):
    try:
        data = bridge.call("screenshot", tabId=tab)
        path = os.path.join(out_dir, f"{name}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data.split(",", 1)[1]))
        return path
    except Exception as e:
        return f"(no screenshot: {e})"


# The captcha the adapter is waiting on, for GET /captcha (a separate watcher relays it to the owner; the collection
# only waits). {"status": "none"} until the first captcha; then waiting / solved / timed_out with its details.
_captcha_lock = threading.Lock()
_captcha = {"status": "none"}


def captcha_state():
    with _captcha_lock:
        return dict(_captcha)


def _set_captcha(**state):
    with _captcha_lock:
        _captcha.clear()
        _captcha.update(state, at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


_TAG_RE = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.S | re.I)
_QUESTION_RE = re.compile(r"[^\n.!]{8,200}\?")


def captcha_question(page_html):
    """The question a captcha page asks (seen 2026-11-05: "What is the first number of the store's phone number?"
    under a receipt picture), or None."""
    text = html_lib.unescape(_TAG_RE.sub("\n", page_html or ""))
    found = [q.strip() for q in _QUESTION_RE.findall(text) if q.strip()]
    return found[-1] if found else None


def walls(bridge, tab):
    page = bridge.call("page", tabId=tab) or {}
    html, url = page.get("html") or "", page.get("url") or ""
    hard = [m for m in HARD_WALLS if m in html]
    human = [m for m in HUMAN_WALLS if m in html]
    if "nid.naver.com" in url:
        raise LoginGate(url[:120])
    return page, hard, human


def check(bridge, tab, step, out_dir, summary=None):
    """True to go on. Waits HUMAN_WAIT_S for a human on a captcha; False on a ban; raises LoginGate on a login page.
    summary["status"] reads "captcha" while it waits (the HTTP job shows it)."""
    summary = summary if summary is not None else {}
    page, hard, human = walls(bridge, tab)
    log(f"[{step}] {page.get('url')} title={page.get('title')!r}")
    if hard:
        shot = screenshot(bridge, tab, out_dir, f"{step}-blocked")
        log(f"STOP at {step}: {hard}; {shot}")
        notify("blocked", f"Naver blocked the listing at {step}", url=page.get("url"), markers=hard, screenshot=shot)
        return False
    if not human:
        return True
    shot, question = _show_captcha(bridge, tab, out_dir, step, page, human, 1)
    log(f"CAPTCHA at {step}: {human}; waiting {HUMAN_WAIT_S} s for a human; question: {question!r}; {shot}")
    summary["status"] = "captcha"
    t0 = time.monotonic()
    seen = 1
    _set_captcha(status="waiting", step=step, attempt=1, question=question, screenshot=shot, url=page.get("url"),
                 wait_s=HUMAN_WAIT_S)
    while time.monotonic() - t0 < HUMAN_WAIT_S:
        time.sleep(3)
        page, hard, human = walls(bridge, tab)
        if hard:
            log(f"STOP at {step} after the captcha: {hard}")
            _set_captcha(status="blocked", step=step, attempt=seen, after_s=int(time.monotonic() - t0))
            return False
        if not human:
            log(f"[{step}] captcha solved after {int(time.monotonic() - t0)} s")
            _set_captcha(status="solved", step=step, attempt=seen, after_s=int(time.monotonic() - t0))
            summary["status"] = "running"
            pause(2, 3)
            return True
        if captcha_question(page.get("html")) != question:          # a wrong answer: a new captcha
            seen += 1
            shot, question = _show_captcha(bridge, tab, out_dir, step, page, human, seen)
            log(f"CAPTCHA again at {step} (#{seen}): question: {question!r}; {shot}")
            _set_captcha(status="waiting", step=step, attempt=seen, question=question, screenshot=shot,
                         url=page.get("url"), wait_s=HUMAN_WAIT_S - int(time.monotonic() - t0))
    log(f"STOP: captcha at {step} not solved in {HUMAN_WAIT_S} s")
    _set_captcha(status="timed_out", step=step, attempt=seen, after_s=HUMAN_WAIT_S)
    notify("captcha-timeout", f"Captcha at {step} not solved in {HUMAN_WAIT_S} s; listing stopped")
    return False


def _show_captcha(bridge, tab, out_dir, step, page, human, n):
    """Screenshot + question + the page itself (local evidence), the cursor put in the answer field so a human can
    type at once (at the Mac or through a remote-desktop app on a phone), and a notice. -> (screenshot, question).
    Nothing is typed here: the human answers (R-EXT-3)."""
    suffix = "" if n == 1 else f"-{n}"
    shot = screenshot(bridge, tab, out_dir, f"{step}-captcha{suffix}")
    question = captcha_question(page.get("html"))
    try:
        with open(os.path.join(out_dir, f"{step}-captcha{suffix}.html"), "w", encoding="utf-8") as f:
            f.write(page.get("html") or "")
        if (bridge.call("query", tabId=tab, selector=CAPTCHA_INPUT) or {}).get("count"):
            bridge.call("click", tabId=tab, selector=CAPTCHA_INPUT)
    except (OSError, ExtError):
        pass                                       # the notice still goes out
    notify("captcha", f"Captcha at {step}: answer it in Chrome within {HUMAN_WAIT_S // 60} min"
           + (f" (attempt {n})" if n > 1 else ""), url=page.get("url"), markers=human, question=question,
           screenshot=shot)
    return shot, question


# ---- path ---------------------------------------------------------------------------

def open_search(bridge, query, out_dir, summary=None):
    """naver.com -> 쇼핑 -> typed search -> (results tab id, None) or (None, why it stopped). A login gate on the
    way closes the path's tabs and takes it again from naver.com (LOGIN_RESETS times)."""
    for attempt in range(LOGIN_RESETS + 1):
        opened = []
        try:
            return _open_search(bridge, query, out_dir, summary, opened)
        except LoginGate as e:
            log(f"login gate on the way ({e}); closing {len(opened)} tab(s), naver.com again "
                f"({attempt + 1} of {LOGIN_RESETS})")
            for other in opened:
                try:
                    bridge.call("tab_close", tabId=other)
                except ExtError:
                    pass
            pause(3, 6)
    return None, f"login gate after {LOGIN_RESETS} resets"


def _open_search(bridge, query, out_dir, summary, opened):
    tab = bridge.call("tab_open", url=HOME)["tabId"]
    opened.append(tab)
    pause(2.5, 4)
    if not check(bridge, tab, "naver", out_dir, summary):
        return None, "wall at naver.com"
    for _ in range(5):              # 2026-11-05: once in ~50 reads the 쇼핑 link was not drawn yet 3-4 s after load
        if (bridge.call("query", tabId=tab, selector=SHOPPING_LINK) or {}).get("visible"):
            break
        pause(1.5, 2.5)
    clicked = bridge.call("click", tabId=tab, selector=SHOPPING_LINK)
    tab = clicked.get("newTabId") or tab
    opened.append(tab)
    bridge.call("wait_load", tabId=tab, timeoutMs=45000)
    pause(2.5, 4)
    if not check(bridge, tab, "shopping-home", out_dir, summary):
        return None, "wall at the shopping home"
    box = next((s for s in SEARCH_BOXES if (bridge.call("query", tabId=tab, selector=s) or {}).get("visible")), None)
    if not box:
        log(f"STOP: no search box on the shopping home; {screenshot(bridge, tab, out_dir, 'home')}")
        return None, "no search box on the shopping home (layout changed?)"
    pause(1.5, 3)
    bridge.call("click", tabId=tab, selector=box)
    pause(0.4, 0.9)
    bridge.call("type", tabId=tab, text=query)
    pause(0.5, 1.1)
    before = {t["tabId"] for t in bridge.call("tabs") or []} - {tab}   # e.g. a kept search tab of another query
    bridge.call("key", tabId=tab, key="Enter")
    for _ in range(40):                       # the site routes to search.shopping (same tab or a new one)
        time.sleep(0.5)
        hit = [t for t in bridge.call("tabs") if "search.shopping.naver.com" in (t.get("url") or "")
               and t["tabId"] not in before]
        if hit:
            tab = hit[-1]["tabId"]
            break
    opened.append(tab)
    bridge.call("wait_load", tabId=tab, timeoutMs=45000)
    pause(3, 5)
    if not check(bridge, tab, "search", out_dir, summary):
        return None, "wall at the search page"
    for other in set(opened) - {tab}:             # the naver.com / shopping-home tabs are done
        try:
            bridge.call("tab_close", tabId=other)
        except ExtError:
            pass
    return tab, None


def search_again(bridge, tab, query, out_dir):
    """A new search typed into an open search page's own box, as a person does (clear, type, Enter): the same tab
    shows the results for `query`. -> True, or False when the tab is not a usable search page (gone, another page,
    no box); a wall raises / returns like check (LoginGate; False on a ban is reported by the caller's check)."""
    url = next((t.get("url") or "" for t in bridge.call("tabs") or [] if t.get("tabId") == tab), "")
    if "search.shopping.naver.com" not in url:
        return False
    if not (bridge.call("query", tabId=tab, selector=SEARCH_BOX) or {}).get("visible"):
        return False
    bridge.call("click", tabId=tab, selector=SEARCH_BOX)
    pause(0.6, 1.2)
    if (bridge.call("query", tabId=tab, selector=SEARCH_CLEAR) or {}).get("visible"):
        bridge.call("click", tabId=tab, selector=SEARCH_CLEAR)
        pause(0.4, 0.9)
    if (bridge.call("query", tabId=tab, selector=SEARCH_BOX) or {}).get("value"):
        return False                              # not cleared: typing would insert at the caret
    bridge.call("type", tabId=tab, text=query)
    pause(0.5, 1.1)
    bridge.call("key", tabId=tab, key="Enter")
    pause(1.5, 2.5)
    bridge.call("wait_load", tabId=tab, timeoutMs=45000)
    pause(2.5, 4)
    return True


# ---- listing ------------------------------------------------------------------------

class Listing:
    """listing.jsonl writer, one line per unique store product."""

    def __init__(self, out_dir, query):
        self.path = os.path.join(out_dir, "listing.jsonl")
        self.query = query
        self.seen = set()
        self.kept = self.ads = self.skipped = 0

    def add(self, batch, batch_no):
        new = 0
        with open(self.path, "a", encoding="utf-8") as f:
            for product in composite.products(batch):
                row = composite.listing_row(product)
                if row is None:
                    self.skipped += 1
                    continue
                if row["product_id"] in self.seen:
                    continue
                self.seen.add(row["product_id"])
                self.kept += 1
                self.ads += row["is_ad"]
                new += 1
                row.update(query=self.query, batch=batch_no,
                           seen_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return new


def rest(batches):
    """Before the page is scrolled for batch `batches + 1`: a short rest, a longer one after every REST_EVERY."""
    pause(*(LONG_REST_S if batches % REST_EVERY == 0 else BATCH_REST_S))


def next_batches(bridge, tab):
    """The page's listing answers copied so far; if none yet, wheel-scroll until
    the page fetches its next batch -> [captures] in arrival order ([] = stalled)."""
    answers = bridge.call("captures", tabId=tab, pattern=LISTING) or []
    for _ in range(0 if answers else SCROLLS_PER_BATCH):
        bridge.call("scroll", tabId=tab, dy=random.randint(700, 1100))
        pause(0.8, 1.5)
        answers = bridge.call("captures", tabId=tab, pattern=LISTING) or []
        if answers:
            break
    return answers


def run(query, out_dir, max_batches, keep_tab):
    os.makedirs(out_dir, exist_ok=True)
    summary = {"query": query, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "batches": 0, "stop": None}
    try:
        bridge = ExtBridge().start()
    except OSError as e:
        summary["stop"] = f"bridge port taken ({e}): stop the API server or use POST /listings"
        return finish(summary, out_dir, 2)
    log(f"waiting up to {CONNECT_WAIT_S // 60} min for the extension (Chrome open, adapter loaded) ...")
    if not bridge.wait_connected(CONNECT_WAIT_S):
        summary["stop"] = "the extension did not connect"
        return finish(summary, out_dir, 2)
    try:
        return walk(bridge, query, out_dir, max_batches, keep_tab, summary)
    except ExtError as e:                         # an op failed / timed out / the adapter went away
        summary["stop"] = f"adapter error: {e}"
        return finish(summary, out_dir, 1)


def walk(bridge, query, out_dir, max_batches, keep_tab, summary):
    tab, why = open_search(bridge, query, out_dir, summary)
    if tab is None:
        summary["stop"] = why
        return finish(summary, out_dir, 1 if why.startswith("no search box") else 3)
    listing = Listing(out_dir, query)
    batch = composite.first_batch((bridge.call("page", tabId=tab, headChars=FULL_HTML) or {}).get("html"))
    if batch is None:
        summary["stop"] = "no first batch in the search page HTML (layout changed?)"
        return finish(summary, out_dir, 1)
    pending, code = [batch], 0                    # answers the page fetched while loading are kept
    try:
        while pending:
            batch = pending.pop(0)
            summary["batches"] += 1
            new = listing.add(batch, summary["batches"])
            summary.update(total=batch.get("total"), cursor=batch.get("cursor"), has_more=batch.get("hasMore"),
                           kept=listing.kept, ads=listing.ads, skipped=listing.skipped)
            log(f"batch {summary['batches']}: cursor {batch.get('cursor')} of total {batch.get('total')}, "
                f"+{new} new (kept {listing.kept}, ads {listing.ads})")
            if not batch.get("hasMore"):
                summary["stop"] = "hasMore=false"
                break
            if max_batches and summary["batches"] >= max_batches:
                summary["stop"] = f"--max-batches {max_batches}"
                break
            if pending:
                continue
            rest(summary["batches"])
            captures = next_batches(bridge, tab)
            if not captures:
                try:
                    walled = not check(bridge, tab, f"batch-{summary['batches'] + 1}", out_dir, summary)
                except LoginGate:
                    walled = True                 # mid-scroll: the rows so far are kept; a new listing starts over
                if walled:
                    summary["stop"], code = "wall while scrolling", 3
                    break
                captures = next_batches(bridge, tab)
            if not captures:
                summary["stop"], code = "stalled: the page loaded no next batch", 1
                notify("stalled", f"Listing for {query!r} stalled after {summary['batches']} batches")
                break
            for capture in captures:
                parsed = composite.batch_from_answer(capture.get("body"))
                if capture.get("status") != 200 or parsed is None:
                    shot = screenshot(bridge, tab, out_dir, "batch-refused")
                    summary["stop"], code = f"batch refused: HTTP {capture.get('status')}", 3
                    log(f"STOP: {summary['stop']}; {shot}")
                    notify("blocked", f"Listing for {query!r} refused (HTTP {capture.get('status')})", screenshot=shot)
                    pending = []
                    break
                pending.append(parsed)
            if code:
                break
    finally:
        if not keep_tab:
            try:
                bridge.call("tab_close", tabId=tab)
            except ExtError:
                pass                              # the adapter may be gone: keep the real stop reason
    return finish(summary, out_dir, code)


def finish(summary, out_dir, code):
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    log(f"done ({summary['stop']}): {json.dumps(summary, ensure_ascii=False)} -> {out_dir}")
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description="search.shopping listing through the owner's Chrome (beta).")
    parser.add_argument("query", help="search keywords, e.g. 남성 골프채 풀세트")
    parser.add_argument("--max-batches", type=int, default=0, help="stop after N batches of ~50 (default: all)")
    parser.add_argument("--out", help="run name under server/output/ext-listing/ (default: a timestamp)")
    parser.add_argument("--keep-tab", action="store_true", help="leave the results tab open")
    args = parser.parse_args(argv)
    out_dir = os.path.join(OUTPUT_ROOT, args.out or datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        return run(args.query, out_dir, args.max_batches, args.keep_tab)
    except KeyboardInterrupt:
        log("interrupted")
        return 1


if __name__ == "__main__":
    sys.exit(main())
