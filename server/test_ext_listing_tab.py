"""Offline tests for the held listing tab (ext_listing_tab.py, routes /listing-tabs): a fake Chrome with a listing tab,
cards that open product tabs and the page's own batch answers (the real fixtures composite_search_page.html and
composite_answer.json) stands in for the adapter. Also the two read paths of ext_product._read_card: the search tab
(read_page) and the listing tab keep their own tab. No network, no browser.

    python -m pytest server/test_ext_listing_tab.py -q
"""
import json
import os
import re
import threading

import pytest

import ext_listing
import ext_listing_tab
import ext_product
import listing_jobs
from naver_shopping import api
from test_listing_jobs import call

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naver_shopping", "fixtures")
SEARCH_URL = "https://search.shopping.naver.com/ns/search?query=q"
FIRST = ["8450665186", "8958060680", "13825089403"]           # composite_search_page.html: total 4385, hasMore
SECOND = ["12975257923", "7506388758", "10649210920", "12679637072"]   # composite_answer.json


def read(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


def answer(has_more=True, status=200):
    body = json.loads(read("composite_answer.json"))
    body["data"]["hasMore"] = has_more
    return {"url": "https://search.shopping.naver.com/ns/v1/search/paged-composite-cards?cursor=x", "status": status,
            "body": json.dumps(body)}


class Chrome:
    """A fake adapter: tabs, a listing tab whose scroll hands out the queued batch answers, cards that open
    product tabs (opens[pid]: the URLs the next clicks land on), product pages with the Honma 상품정보 list."""
    def __init__(self):
        self.connected = True
        self.tabs, self.next_id, self.ops = {}, 100, []
        self.scrolls = []           # per scroll: the answers the page fetches
        self.waiting = []           # answers fetched, not yet copied out
        self.cards = set(FIRST + SECOND)
        self.opens = {}             # pid -> [url, ...] for the next clicks; default its own product page
        self.in_tab = set()         # pids whose card opens in the listing tab itself
        self.nothing = set()        # pids whose card opens nothing (no new tab, the listing tab stays)
        self.product_html = read("pdp_specs_honma.html")
        self.hold = None            # an Event a click waits on (a call left running)

    def wait_connected(self, timeout=None):
        return self.connected

    def open(self, url):
        self.next_id += 1
        self.tabs[self.next_id] = url
        return self.next_id

    def call(self, op, **a):
        self.ops.append((op, a.get("tabId"), a.get("selector") or a.get("dy")))
        tab = a.get("tabId")
        if op == "tabs":
            return [{"tabId": t, "url": u} for t, u in self.tabs.items()]
        if op == "tab_close":
            self.tabs.pop(tab, None)
            return True
        if op in ("wait_load",):
            return True
        if op == "screenshot":
            return "data:image/png;base64,AAAA"
        if op == "page":
            url = self.tabs.get(tab, "")
            html = read("composite_search_page.html") if "search.shopping" in url else self.product_html
            return {"url": url, "title": "t", "html": html}
        if op == "scroll":
            if self.scrolls:
                self.waiting += self.scrolls.pop(0)
            return True
        if op == "captures":
            if a["pattern"] != ext_listing.LISTING:
                return []
            hit, self.waiting = self.waiting, []
            return hit
        if op == "query":
            pid = re.search(r"/products/(\d+)", a["selector"])
            if pid is None:
                return {"count": 0}
            here = pid.group(1) in self.cards
            return {"count": int(here), "visible": here, "rect": {"x": 768, "y": 300} if here else None}
        if op == "click":
            if self.hold is not None:
                self.hold.wait(5)
            pid = re.search(r"/products/(\d+)", a["selector"]).group(1)
            queued = self.opens.get(pid) or []
            url = queued.pop(0) if queued else f"https://smartstore.naver.com/shop/products/{pid}"
            if pid in self.nothing:
                return {}
            if pid in self.in_tab:
                self.tabs[tab] = url
                return {}
            return {"newTabId": self.open(url)}
        raise AssertionError(op)

    def count(self, op):
        return sum(o == op for o, _, _ in self.ops)


def details(product):
    pid = product.rsplit("/", 1)[1]
    return {"id": pid, "name": f"상품 {pid}", "link": product,
            "category": {"id": "50002788", "name": "풀세트", "path": [], "path_ids": []},
            "brand": None, "manufacturer": None, "model_name": None, "notice": None}


@pytest.fixture
def chrome(monkeypatch, tmp_path):
    b = Chrome()

    def open_search(bridge, query, out_dir, summary=None):
        return bridge.open(SEARCH_URL), None
    monkeypatch.setattr(listing_jobs, "_bridge", b)
    monkeypatch.setattr(listing_jobs, "_jobs", {})
    monkeypatch.setattr(listing_jobs, "OUTPUT_ROOT", str(tmp_path / "listings"))
    monkeypatch.setattr(ext_listing_tab, "OUTPUT_ROOT", str(tmp_path / "tabs"))
    monkeypatch.setattr(ext_product, "OUTPUT_ROOT", str(tmp_path / "product"))
    monkeypatch.setattr(ext_listing, "open_search", open_search)
    monkeypatch.setattr(ext_listing, "pause", lambda a, b: None)
    monkeypatch.setattr(ext_listing, "notify", lambda *a, **k: None)
    monkeypatch.setattr(ext_listing_tab, "notify", lambda *a, **k: None)
    monkeypatch.setattr(ext_listing, "SCROLLS_PER_BATCH", 3)
    monkeypatch.setattr(ext_listing, "HUMAN_WAIT_S", 0)
    monkeypatch.setattr(ext_product.time, "sleep", lambda s: None)
    monkeypatch.setattr(ext_product, "ANSWER_TRIES", 1)
    monkeypatch.setattr(api, "product_details", details)
    ext_product._home.clear()
    yield b
    with ext_listing_tab._lock:
        ext_listing_tab._end("test over")
    ext_product._home.clear()
    assert listing_jobs.holder is None and not listing_jobs._adapter.locked()


def link(pid):
    return f"https://smartstore.naver.com/shop/products/{pid}"


def opened(chrome):
    status, tab = call("POST", "/listing-tabs", query="남성 골프채 풀세트")
    assert status == 200, tab
    return tab


# ---- open / next / close ---------------------------------------------------------------

def test_open_answers_the_first_batch_and_holds_the_adapter(chrome):
    tab = opened(chrome)
    assert tab["batch"] == 1 and tab["has_more"] is True and tab["total"] == 4385
    assert tab["query"] == "남성 골프채 풀세트"
    assert [r["product_id"] for r in tab["results"]] == FIRST
    assert tab["results"][0]["batch"] == 1 and tab["results"][0]["query"] == "남성 골프채 풀세트"
    assert ext_listing_tab.TAB_ID.match(tab["id"])
    status, body = call("POST", "/listings", query="q")                           # a listing job: busy, says who
    assert status == 409 and f"listing tab {tab['id']}" in body["error"] and "DELETE" in body["error"]
    status, body = call("GET", "/products/specs", product=link(FIRST[0]))           # a product read: busy
    assert status == 409 and f"listing tab {tab['id']}" in body["error"]
    assert call("DELETE", f"/listing-tabs/{tab['id']}") == (200, {"id": tab["id"], "closed": True})
    assert not chrome.tabs and listing_jobs.holder is None and not listing_jobs._adapter.locked()
    assert call("DELETE", f"/naver-shopping/listing-tabs/{tab['id']}")[0] == 200       # idempotent


def test_open_is_busy_while_a_read_holds_the_adapter(chrome):
    assert listing_jobs._adapter.acquire(blocking=False)
    try:
        status, body = call("POST", "/listing-tabs", query="q")
        assert status == 409 and "another product page read" in body["error"] and listing_jobs.holder is None
    finally:
        listing_jobs._adapter.release()


def test_a_new_open_closes_the_old_session_and_orphan_tabs(chrome):
    first = opened(chrome)
    orphan = chrome.open("https://smartstore.naver.com/shop/products/1")
    ext_product._home["tab"] = orphan
    second = opened(chrome)
    assert second["id"] != first["id"] and orphan not in chrome.tabs and not ext_product._home
    assert list(chrome.tabs.values()) == [SEARCH_URL]                                   # only the new listing tab
    assert call("POST", f"/listing-tabs/{first['id']}/next")[0] == 410


def test_next_takes_pending_batches_first_then_ends_without_scrolling(chrome):
    tab = opened(chrome)
    chrome.scrolls = [[answer(), answer(has_more=False), answer(has_more=False)]]     # one scroll, three answers
    status, b2 = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 200 and b2["batch"] == 2 and b2["has_more"] and [r["product_id"] for r in b2["results"]] == SECOND
    scrolls = chrome.count("scroll")
    status, b3 = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 200 and b3["batch"] == 3 and b3["has_more"] is False and b3["total"] == 4385
    status, after = call("POST", f"/listing-tabs/{tab['id']}/next")                   # the end: the repeat dropped
    assert status == 200 and after["has_more"] is False and after["results"] == [] and after["batch"] == 3
    assert chrome.count("scroll") == scrolls                                         # no scroll after the end


def test_a_stall_or_a_refused_batch_ends_the_session(chrome):
    tab = opened(chrome)
    status, body = call("POST", f"/listing-tabs/{tab['id']}/next")                     # no answer while hasMore
    assert status == 503 and body["error"].startswith("wall:") and "stalled" in body["error"]
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410 and not listing_jobs._adapter.locked()
    tab = opened(chrome)
    chrome.scrolls = [[answer(status=418)]]
    status, body = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 503 and body["error"].startswith("wall:") and "refused" in body["error"]
    assert chrome.count("scroll") == 2 * 3 + 1                                       # never scrolled again
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410


def test_a_ban_while_scrolling_ends_the_session(chrome, monkeypatch):
    tab = opened(chrome)
    monkeypatch.setattr(chrome, "product_html", "접속이 일시적으로 제한")

    def banned(op, **a):
        if op == "page" and a.get("tabId") == min(chrome.tabs):
            return {"url": SEARCH_URL, "html": "접속이 일시적으로 제한"}
        return Chrome.call(chrome, op, **a)
    monkeypatch.setattr(chrome, "call", banned)
    status, body = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 503 and body["error"].startswith("wall:") and "while scrolling" in body["error"]
    assert not listing_jobs._adapter.locked()


def test_unknown_and_bad_ids(chrome):
    assert call("POST", "/listing-tabs/20261114-000000-abcd/next")[0] == 410
    assert call("GET", "/listing-tabs/20261114-000000-abcd/specs", product=link(FIRST[0]))[0] == 410
    assert call("POST", "/listing-tabs/not-an-id/next")[0] == 400
    assert call("POST", "/listing-tabs")[0] == 400                                     # query is required
    tab = opened(chrome)
    assert call("POST", f"/listing-tabs/{tab['id']}/next", x="1")[0] == 400            # unknown param
    assert call("GET", f"/listing-tabs/{tab['id']}/specs")[0] == 400                   # product is required


def test_the_listing_tab_checked_before_every_call(chrome):
    tab = opened(chrome)
    chrome.connected = False
    status, body = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 503 and "not connected" in body["error"]                          # the session lives
    chrome.connected = True
    listing = min(chrome.tabs)
    chrome.tabs[listing] = "https://www.naver.com/"
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 410 and "no longer a search page" in body["error"] and not chrome.tabs
    tab = opened(chrome)
    chrome.tabs.clear()                                                                 # the owner closed it
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410 and not listing_jobs._adapter.locked()


def test_an_adapter_error_on_the_listing_tab_is_gone(chrome, monkeypatch):
    tab = opened(chrome)

    def broken(op, **a):
        if op == "scroll":
            raise ext_listing_tab.ExtError("tab 101 is not ours")
        return Chrome.call(chrome, op, **a)
    monkeypatch.setattr(chrome, "call", broken)
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410 and not listing_jobs._adapter.locked()


# ---- specs ---------------------------------------------------------------------------

def test_specs_keeps_the_listing_tab_and_closes_the_product_tab(chrome):
    tab = opened(chrome)
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[1]))
    assert status == 200, body
    assert body["id"] == FIRST[1] and body["query"] == "남성 골프채 풀세트"
    assert [r["label"] for r in body["specs"]] == ["상품번호", "제조사", "원산지"]
    assert list(chrome.tabs.values()) == [SEARCH_URL]                                   # the product tab is closed
    assert chrome.count("click") == 1 and chrome.count("tab_open") == 0               # no search, one click
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 503                  # still alive (then stalls)


def test_a_card_that_opened_another_product_is_clicked_once_more(chrome):
    tab = opened(chrome)
    other = "https://smartstore.naver.com/shop/products/5543745139"
    chrome.opens[FIRST[0]] = [other]                                                  # a shift: right the 2nd time
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 200 and body["id"] == FIRST[0] and chrome.count("click") == 2
    chrome.opens[FIRST[1]] = [other, other]                                           # the thegolf card: always
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[1]))
    assert status == 404 and "card_opened_other" in body["error"]
    assert list(chrome.tabs.values()) == [SEARCH_URL]                                   # session alive, tabs closed
    assert ext_listing_tab._session["id"] == tab["id"]


def test_the_card_is_wheeled_in_before_the_click(chrome, monkeypatch):
    tab = opened(chrome)
    ys = iter([1900, 1900, 420, 420, 420])                                                # far below, then steady

    def far(op, **a):
        out = Chrome.call(chrome, op, **a)
        if op == "query" and out.get("rect") and "pdinfo" not in a["selector"]:
            out["rect"] = {"x": 768, "y": next(ys, 420)}
        return out
    monkeypatch.setattr(chrome, "call", far)
    assert call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[2]))[0] == 200
    wheels = [dy for op, _, dy in chrome.ops if op == "scroll"]
    assert wheels == [1500]                                                            # y - 400, once


def test_card_missing_keeps_the_session(chrome):
    tab = opened(chrome)
    chrome.cards.discard(FIRST[0])
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 404 and "no card in the listing tab" in body["error"]
    assert call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[1]))[0] == 200


def test_a_captcha_not_answered_keeps_the_session_a_ban_ends_it(chrome):
    tab = opened(chrome)
    chrome.product_html = '<html><title="captcha"></html>'
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 503 and body["error"].startswith("wall: captcha")
    assert list(chrome.tabs.values()) == [SEARCH_URL] and ext_listing_tab._session["id"] == tab["id"]
    chrome.product_html = "<html>접속이 일시적으로 제한</html>"
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[1]))
    assert status == 503 and body["error"].startswith("wall:") and not body["error"].startswith("wall: captcha")
    assert not chrome.tabs and call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410


def test_a_login_gate_is_gone(chrome):
    tab = opened(chrome)
    chrome.opens[FIRST[0]] = ["https://nid.naver.com/nidlogin.login"]
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 410 and "login gate" in body["error"] and not chrome.tabs


def test_a_card_opened_in_the_listing_tab_is_answered_then_gone(chrome):
    tab = opened(chrome)
    chrome.in_tab.add(FIRST[0])
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 200 and body["id"] == FIRST[0]
    assert not chrome.tabs and not listing_jobs._adapter.locked()
    assert call("POST", f"/listing-tabs/{tab['id']}/next")[0] == 410


def test_a_card_that_opened_nothing_is_not_clicked_again_session_alive(chrome):
    tab = opened(chrome)
    chrome.nothing.add(FIRST[0])
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 404 and "card_opened_nothing" in body["error"] and chrome.count("click") == 1
    assert list(chrome.tabs.values()) == [SEARCH_URL] and ext_listing_tab._session["id"] == tab["id"]
    assert call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[1]))[0] == 200


def test_a_held_tab_makes_the_old_mode_busy_until_closed(chrome):
    tab = opened(chrome)
    with pytest.raises(listing_jobs.Busy, match=f"listing tab {tab['id']}"):                # a /products/specs read
        listing_jobs.with_adapter(lambda bridge: None)
    with pytest.raises(listing_jobs.Busy) as busy:                                         # a listing job
        listing_jobs.start("q")
    assert busy.value.args == (None,) and f"listing tab {tab['id']}" in listing_jobs.who()
    ext_listing_tab.close(tab["id"])
    assert listing_jobs.holder is None and not listing_jobs._adapter.locked()
    assert listing_jobs.with_adapter(lambda bridge: "read") == "read"                      # free again


def test_a_page_without_rows_is_an_adapter_error_session_alive(chrome):
    tab = opened(chrome)
    chrome.product_html = "<html>상품</html>"
    status, body = call("GET", f"/listing-tabs/{tab['id']}/specs", product=link(FIRST[0]))
    assert status == 503 and body["error"].startswith("adapter error:")
    assert ext_listing_tab._session["id"] == tab["id"]


def test_calls_take_turns_close_waits(chrome):
    tab = opened(chrome)
    chrome.hold = threading.Event()
    out = {}
    reader = threading.Thread(target=lambda: out.update(r=ext_listing_tab.specs(tab["id"], link(FIRST[0]))))
    reader.start()
    for _ in range(200):
        if chrome.count("click"):
            break
        threading.Event().wait(0.01)
    status, body = call("POST", f"/listing-tabs/{tab['id']}/next")
    assert status == 409 and "busy" in body["error"]
    closer = threading.Thread(target=lambda: out.update(c=ext_listing_tab.close(tab["id"])))
    closer.start()
    closer.join(0.2)
    assert closer.is_alive()                                                            # waits for the read
    chrome.hold.set()
    reader.join(5)
    closer.join(5)
    assert out["r"]["id"] == FIRST[0] and out["c"]["closed"] and not listing_jobs._adapter.locked()


# ---- the two read paths keep their own tab (ext_product._read_card) ---------------------

def test_read_page_still_keeps_its_search_tab(chrome, tmp_path, monkeypatch):
    chrome.tabs.clear()
    ext_product._home["tab"] = chrome.open(SEARCH_URL)
    monkeypatch.setattr(ext_listing, "search_again", lambda bridge, tab, query, out_dir: True)
    out = ext_product.read_page(chrome, FIRST[0], "q", str(tmp_path))
    assert out["url"].endswith(f"/products/{FIRST[0]}") and out["search_url"] == SEARCH_URL
    assert list(chrome.tabs) == [ext_product._home["tab"]]                               # the search tab kept
    assert chrome.count("scroll") == 0                                                   # the old click: no wheel
    chrome.opens[FIRST[1]] = ["https://smartstore.naver.com/shop/products/1"]
    with pytest.raises(ext_product.NotListed, match="pass a query"):                      # no second click
        ext_product.read_page(chrome, FIRST[1], "q", str(tmp_path))
    assert chrome.count("click") == 2 and list(chrome.tabs) == [ext_product._home["tab"]]
    chrome.in_tab.add(FIRST[2])                                                          # opened in the search tab
    ext_product.read_page(chrome, FIRST[2], "q", str(tmp_path))
    assert not ext_product._home and not chrome.tabs                                     # not kept, as before


def test_specs_tail_needs_the_list(tmp_path):
    with pytest.raises(ext_product.AdapterError, match="^adapter error:"):
        ext_product._specs_tail(details(link("42")), {"url": "u", "html": "<html></html>"}, "q", str(tmp_path))
