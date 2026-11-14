"""products/specs (BETA): a product page's 상품정보 rows (label -> value),
read in the owner's Chrome through the adapter (extension/), the way a person
opens a product: naver.com -> 쇼핑 -> typed search -> click the product's card
-> "상품정보 펼쳐보기" when the list is folded -> the rendered page's HTML. All
decisions (path, selectors, walls) are here and in ext_listing; all parsing
is pure Python (naver_shopping/pdp.py, parsers.product_facts).

Why the page and why this way (probed 2026-11-01, PING G440K set
smartstore.naver.com/scarabee/products/13021362937):

  * The rows the seller fills in (종류, 성별, 총클럽개수, 원산지 ...) are in
    none of the store-backend answers products/details reads (simple-products,
    validation-products, contents, provided-notice). The backend's full product
    path /n/v2/channels/{uid}/products/{id} answers 204 for a smartstore
    channel inside the box; /i/v2/... and /n/v1/... answer 404.
  * The product page opened directly in the owner's Chrome redirects to the
    login page (nid.naver.com); reached by a click from the search page it
    renders. The page's __PRELOADED_STATE__ holds no product data (product.*
    null) when read, so the rendered 상품정보 list is the source; it shows 9
    rows and folds the rest behind a button (15 after the click).

The search tab stays (the owner 2026-11-07, one product per iteration of a job): the next read types its query
into that tab's own box (ext_listing.search_again) instead of the naver.com -> 쇼핑 path, and every other tab
the adapter drives (the product tab) is closed after each read, so the browser is back on the search tab. The
path is taken again when the tab is gone or is not a search page. A login gate is not waited for: the read
closes its tabs, the search tab included, and starts again from naver.com (once).

The same read from a held listing tab (ext_listing_tab, /listing-tabs/<id>/specs, 2026-11-14): _read_card from
the click on, the card wheeled in and steady first and a wrong product clicked once more (steady=True), the
listing tab kept instead of the search tab; _specs_tail is the answer for both.

Products/details stays on the box; this route only adds what the page has.
One adapter user at a time (listing_jobs.with_adapter): a running listing
job or a held listing tab makes a read busy (409). Walls are handled like the listing's
(ext_listing.check: a captcha is reported and waited for, a ban page stops)
and answer 503; only a `wall:` one is final. A 503's error starts with its kind
(the owner 2026-11-07, for a job that goes on by itself): "wall:" (captcha not
answered, ban page, login gate after the reset: stop), "naver error page:"
(K-21: Naver's maintenance page, passes in minutes: wait and retry),
"adapter error:" (a read that failed mid-way: retry).
"""
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import ext_listing
import listing_jobs
from cache import cached_call, forget
from ext_bridge import ExtError
from naver_shopping import api, measures, parsers, pdp
from naver_shopping import cache_config as ttl
from scraper_errors import NotFound

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "ext-product")
MORE_BUTTON = 'button[data-shp-area="pdinfo.more"]'     # "상품정보 펼쳐보기" (2026-11-01)
FULL_HTML = 8_000_000      # chars: a smartstore product page is ~0.6 MB
RENDER_TRIES = 8           # page reads, RENDER_WAIT_S apart, until the 상품정보 list is rendered
RENDER_WAIT_S = 2
ANSWER_TRIES = 5        # captures reads, RENDER_WAIT_S apart, until the page's product answer is in
# 2026-11-06 (pilot, 13425122164 "초중급 남성 골프채 풀세트 입문 골프클럽 초보 골프"): the card was on the first search
# page for the name's first 5 words, not for the full name nor for the listing's query; a long name's tail
# (초보, 골프 ...) ranks other cards first. One more search with the first words, only for the default query.
SHORT_QUERY_WORDS = 5
# Probe 2 (2026-11-14, the held listing tab, ext_listing_tab): before a click the card is wheeled until its top is
# STEADY_BAND px from the viewport's top (STEADY_MID aimed at, at most STEADY_DY a wheel, STEADY_WHEELS wheels), then
# its rect read until two reads STEADY_GAP_S apart agree (STEADY_READS reads): 30 clicks, 0 shifts (_steady)
STEADY_BAND, STEADY_MID, STEADY_DY, STEADY_WHEELS = (150, 650), 400, 2500, 8
STEADY_READS, STEADY_GAP_S = 6, 0.4


# Not UpstreamError / Blocked (502): scripts retry a 502, and a wall in the
# owner's Chrome is never retried (R-EXT-3). routes.call answers `status`.
class AdapterError(Exception):
    """The adapter could not read the page: not connected, or failed mid-read."""
    status = 503


class AdapterBusy(AdapterError):
    """A listing job (or another read) is using the adapter."""
    status = 409


class PageBlocked(AdapterError):
    """A captcha not solved in time, a ban page, or a login gate again after the reset."""


_home = {}          # the search tab kept between reads: {"tab": id}; one adapter user at a time (with_adapter)


class NotListed(NotFound):
    """The product's card is not on the search page for the query."""


class CardMissing(NotListed):
    """No card for the product on the search page (not: a card that opened something else, Naver's error page)."""


def search_queries(name, query=None):
    """The searches to try, in order: the caller's query alone; else (no query, or the name itself) the name, then
    its first SHORT_QUERY_WORDS words when it is longer. Pure."""
    name = " ".join((name or "").split())
    if query and " ".join(query.split()) != name:
        return [query]
    if not name:
        return []
    words = name.split()
    return [name, " ".join(words[:SHORT_QUERY_WORDS])] if len(words) > SHORT_QUERY_WORDS else [name]


def _card(bridge, tab, product_id):
    """The selector to click for the product's card on the search page, or None.
    Cards link to smartstore.naver.com/main/products/<id>?nl-query=... (2026-11-01). Seen 2026-11-05 (thegolf
    8357720534, 5543663553): that link is a transparent layer over the whole card (178 x 397), and the store's
    name link (smartstore.naver.com/inflow/outlink -> /thegolf, then Naver's login page) lies above it just under
    the photo, inside the middle band the adapter clicks in. So the card's photo is clicked (the product link layer
    covers it, nothing else does); the link itself only when a card has no such photo."""
    for link in (f'a[href*="/products/{product_id}?"]', f'a[href$="/products/{product_id}"]'):
        photo = f'[class*="product_card"]:has(> {link}) img[class*="productCardThumbnail_image"]'
        for sel in (photo, link):
            if (bridge.call("query", tabId=tab, selector=sel) or {}).get("count"):
                return sel
    return None


def _product_answer(bridge, tab, product_id):
    """The page's own product answer (/channels/<uid>/products/<id>, with options and stock), copied by the
    adapter; None when the page got none. Probed 2026-11-02: the smartstore page asks /i/v2/channels/<uid>/
    products/<id> (its server-rendered state has optionUsable false and stock 0: options come only from this
    call), the brand page /n/v2/channels/<uid>/products/<id>?withWindow=false; both carry a one-time page token
    (x-client-rtk) since that day. A first try can get 419, then the page reloads itself and gets 200, so a few
    reads are allowed."""
    for _ in range(ANSWER_TRIES):
        for answer in reversed(bridge.call("captures", tabId=tab, pattern=f"/products/{product_id}") or []):
            path = urlsplit(answer.get("url") or "").path
            if answer.get("status") != 200 or not path.endswith(f"/products/{product_id}"):
                continue                                   # a sub-answer (category-navigations, verticals ...)
            try:
                product = json.loads(answer.get("body") or "")
            except ValueError:
                continue
            if isinstance(product, dict):
                return product
        time.sleep(RENDER_WAIT_S)
    return None


def _close_tabs(bridge, keep=None):
    """Close every tab the adapter drives but `keep` (the search tab); -> how many are left."""
    left = 0
    try:
        for t in bridge.call("tabs") or []:
            if t["tabId"] == keep:
                left += 1
                continue
            bridge.call("tab_close", tabId=t["tabId"])
    except ExtError:
        pass
    return left


def _search_tab(bridge, query, out_dir):
    """The search page for `query`: the kept tab searched again, else the naver.com path. -> tab id."""
    tab = _home.get("tab")
    if tab is not None:
        if ext_listing.search_again(bridge, tab, query, out_dir):
            if not ext_listing.check(bridge, tab, "search", out_dir):
                raise PageBlocked(f"wall: a wall on the search page for {query!r}")
            return tab
        _home.pop("tab", None)
        try:
            bridge.call("tab_close", tabId=tab)        # not usable: never left to be taken for another search
        except ExtError:
            pass
    tab, why = ext_listing.open_search(bridge, query, out_dir)
    if tab is None:
        raise PageBlocked(f"wall: {why}")
    _home["tab"] = tab
    return tab


def _rect(bridge, tab, selector):
    """The card's (x, y) in the viewport, rounded; None when it is not in the DOM."""
    rect = (bridge.call("query", tabId=tab, selector=selector) or {}).get("rect")
    return (round(rect.get("x", -1)), round(rect.get("y", -1))) if rect else None


def _steady(bridge, tab, selector):
    """Wheel the card to the middle of the viewport (the adapter's generic `scroll`), then read its rect until two
    reads STEADY_GAP_S apart agree. -> True when it stood still. Probe 2 (2026-11-14, listing tab, 30 clicks right
    after a batch came): the click's own scrollIntoView, while the page inserted a batch, opened another product
    2 times in 16 (probe 1); wheeled in and steady first, 0 in 30."""
    for _ in range(STEADY_WHEELS):
        at = _rect(bridge, tab, selector)
        if at is None or STEADY_BAND[0] <= at[1] <= STEADY_BAND[1]:
            break
        bridge.call("scroll", tabId=tab, dy=max(min(at[1] - STEADY_MID, STEADY_DY), -STEADY_DY))
        ext_listing.pause(0.6, 1.0)
    prev = _rect(bridge, tab, selector)
    for _ in range(STEADY_READS):
        time.sleep(STEADY_GAP_S)
        cur = _rect(bridge, tab, selector)
        if cur == prev:
            return True
        prev = cur
    return False


def _click_card(bridge, tab, selector, steady):
    """Click the card -> the tab it opened (`tab` itself when it opened there, or when nothing opened)."""
    if steady:
        _steady(bridge, tab, selector)
        # One click: the probes saw a new tab at every one of 50; a second click in a listing tab that may be
        # navigating in place would land on a page mid-load (_read_card tells "nothing opened" from "opened here")
        return bridge.call("click", tabId=tab, selector=selector).get("newTabId") or tab
    ext_listing.pause(1, 2.5)
    clicked = bridge.call("click", tabId=tab, selector=selector)
    if not clicked.get("newTabId"):
        # 2026-11-05: one photo click in 20 opened nothing (still on the search page): one more click
        ext_listing.pause(1.5, 3)
        if "/products/" not in ((bridge.call("page", tabId=tab, headChars=0) or {}).get("url") or ""):
            clicked = bridge.call("click", tabId=tab, selector=selector)
    return clicked.get("newTabId") or tab


def _land(bridge, page_tab, product_id, out_dir):
    """Wait for the opened page, check it for Naver's error page and walls -> the URL it landed on."""
    bridge.call("wait_load", tabId=page_tab, timeoutMs=45000)
    ext_listing.pause(3, 5)
    # 2026-11-06: a product whose page Naver cannot serve opens shopv.pstatic.net/web/maintenance/
    # internal-error.html (twice in a row on 10302181901): when the tab can be read it is not a wall, the
    # product is unavailable now (404). Mostly the adapter cannot read that host and the read fails before this
    # check, answered 503 "naver error page:" (KNOWN_ISSUES K-21); it passes in minutes
    tab_url = next((t.get("url") or "" for t in bridge.call("tabs") or [] if t.get("tabId") == page_tab), "")
    if "/web/maintenance/" in tab_url:
        raise NotListed(f"product {product_id}: Naver shows its error page ({tab_url[:80]})")
    if not ext_listing.check(bridge, page_tab, "product", out_dir):
        raise PageBlocked(f"wall: product {product_id}: a wall on the product page")
    return (bridge.call("page", tabId=page_tab, headChars=0) or {}).get("url") or ""


def _open_card(bridge, tab, product_id, selector, query, opened, steady):
    """Click the card -> the tab it opened, kept in opened["page_tab"]. steady (the listing tab): a click that
    opened nothing (no new tab, the listing tab still a search page) leaves page_tab None, the listing tab and its
    position intact, and the card counts as not found (NotListed card_opened_nothing)."""
    page_tab = opened["page_tab"] = _click_card(bridge, tab, selector, steady)
    if steady and page_tab == tab:
        ext_listing.pause(1.5, 3)
        url = (bridge.call("page", tabId=tab, headChars=0) or {}).get("url") or ""
        if "search.shopping.naver.com" in url and "/products/" not in url:
            opened["page_tab"] = None
            raise NotListed(f"product {product_id}: card_opened_nothing: its card in the listing for {query!r} "
                            "opened no page")
    return page_tab


def _read_card(bridge, tab, product_id, selector, query, out_dir, opened, steady=False):
    """From the click on the product's card in `tab` to the product page read: -> {url, title, html, product}.
    opened["page_tab"] is the tab the click opened (`tab` itself when the card opened there), set even when the
    read fails; closing tabs is the caller's (read_page keeps its search tab, a listing tab session its listing).
    steady (the held listing tab, ext_listing_tab): the card is wheeled in and steady before the click, a card
    that opened another product is closed and clicked once more (probe 2, 2026-11-14), one that opened nothing is
    not clicked again (_open_card)."""
    page_tab = _open_card(bridge, tab, product_id, selector, query, opened, steady)
    landed = _land(bridge, page_tab, product_id, out_dir)
    if steady and f"/products/{product_id}" not in landed:
        # Probe 2 (2026-11-14): one card in 30 (thegolf 8986473641) opened another product of its store at every
        # click, the layout standing still; a URL check catches it, one more click after a shift.
        if page_tab != tab:
            bridge.call("tab_close", tabId=page_tab)
            ext_listing.pause(1.5, 3)
            page_tab = _open_card(bridge, tab, product_id, selector, query, opened, steady)
            landed = _land(bridge, page_tab, product_id, out_dir)
        if f"/products/{product_id}" not in landed:
            raise NotListed(f"product {product_id}: card_opened_other: its card in the listing for {query!r} "
                            f"opened {landed[:80]}")
    # A click on the card's centre can land on its store link (2026-11-01: the Honma D1 card in the
    # 남성 골프채 풀세트 search opened smartstore.naver.com/thegolf); then the card counts as not found.
    if f"/products/{product_id}" not in landed:
        raise NotListed(f"product {product_id}: its card on the search page for {query!r} opened {landed[:80]}; "
                        "pass a query that finds it (its name)")
    # The list can render seconds after the load event (2026-11-01: a Honma
    # page read 3-5 s after load had none, 4 s later it had its 3 rows).
    page = {}
    for _ in range(RENDER_TRIES):
        page = bridge.call("page", tabId=page_tab, headChars=FULL_HTML) or {}
        if pdp.spec_rows(page.get("html")):
            break
        time.sleep(RENDER_WAIT_S)
    if (bridge.call("query", tabId=page_tab, selector=MORE_BUTTON) or {}).get("count"):
        bridge.call("click", tabId=page_tab, selector=MORE_BUTTON)
        ext_listing.pause(1.5, 2.5)
        page = bridge.call("page", tabId=page_tab, headChars=FULL_HTML) or {}
    html = page.get("html") or ""
    with open(os.path.join(out_dir, "product.html"), "w", encoding="utf-8") as f:   # local evidence, gitignored
        f.write(html)
    product = _product_answer(bridge, page_tab, product_id)
    if product is not None:
        with open(os.path.join(out_dir, "product.json"), "w", encoding="utf-8") as f:   # local evidence, gitignored
            json.dump(product, f, ensure_ascii=False)
    return {"url": page.get("url"), "title": page.get("title"), "html": html, "product": product}


def _read_log(product_id, started, selector, page):
    card = "link" if selector.startswith("a[") else "photo"
    folded = ", folded" if pdp.specs_collapsed(page["html"]) else ""
    print(f"ext-product: {product_id} read in {time.monotonic() - started:.0f} s: card by {card}, "
          f"{len(pdp.spec_rows(page['html']))} rows{folded}, options {'yes' if page['product'] else 'NO'}", flush=True)


def _adapter_error(product_id, e):
    """An ExtError mid-read -> the 503 that says its kind."""
    if "maintenance" in str(e) or "internal-error" in str(e):
        return AdapterError(f"naver error page: product {product_id}: {e}")
    return AdapterError(f"adapter error: product {product_id}: {e}")


def read_page(bridge, product_id, query, out_dir):
    """-> {url, title, html, search_url, product}: the product page after a click from
    the search for `query`, its 상품정보 list unfolded. Closes every tab but the search tab."""
    os.makedirs(out_dir, exist_ok=True)
    started = time.monotonic()
    opened = {}
    tab = None
    try:
        tab = _search_tab(bridge, query, out_dir)
        search_url = (bridge.call("page", tabId=tab, headChars=0) or {}).get("url")
        selector = _card(bridge, tab, product_id)
        if not selector:
            raise CardMissing(f"product {product_id} is not on the search page for {query!r}; "
                              "pass a query that finds it (its name, or a shorter part of it)")
        page = _read_card(bridge, tab, product_id, selector, query, out_dir, opened)
        _read_log(product_id, started, selector, page)
        return {**page, "search_url": search_url}
    except ext_listing.LoginGate:
        _home.pop("tab", None)                     # the reset: every tab goes, the next read starts at naver.com
        raise
    except ExtError as e:
        raise _adapter_error(product_id, e)
    finally:
        if tab is not None and opened.get("page_tab") == tab:   # the card opened in the search tab: not kept
            _home.pop("tab", None)
        left = _close_tabs(bridge, keep=_home.get("tab"))
        print(f"ext-product: tabs left: {left} (search tab {'kept' if left else 'none'})", flush=True)


def _read_listed(bridge, product_id, queries, out_dir):
    """read_page for the first query whose search page has the card; the next query only when the card was not
    there (CardMissing), within the same adapter turn (one adapter user at a time) and still from a search page
    (R-NAVER-1). A login gate: every tab closed, once more from naver.com. -> the page dict plus "query"."""
    resets = 0
    i = 0
    while i < len(queries):
        query = queries[i]
        try:
            return {**read_page(bridge, product_id, query, out_dir), "query": query}
        except ext_listing.LoginGate as e:
            if resets >= 1:
                raise PageBlocked(f"wall: product {product_id}: a login gate again after the reset ({e})")
            resets += 1
            print(f"ext-product: {product_id} login gate ({e}); every tab closed, from naver.com again", flush=True)
            ext_listing.pause(3, 6)
            continue
        except CardMissing:
            if i == len(queries) - 1:
                raise
            print(f"ext-product: {product_id} not listed for {query!r}, trying {queries[i + 1]!r}", flush=True)
            ext_listing.pause(2, 4)
            i += 1
    raise NotListed(f"product {product_id}: no name to search for; pass query")


def _with_adapter(product_id, queries, out_dir):
    try:
        return listing_jobs.with_adapter(lambda bridge: _read_listed(bridge, product_id, queries, out_dir))
    except listing_jobs.Busy as e:
        raise AdapterBusy(f"the adapter is busy ({e}), retry when it is done")
    except listing_jobs.NoExtension:
        raise AdapterError("the browser extension is not connected: open Chrome with the "
                           "naver-scrap adapter loaded (extension/README.md)")


def _specs(product, query):
    details = api.product_details(product)
    product_id = details["id"]
    out_dir = os.path.join(OUTPUT_ROOT, datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{product_id}")
    page = _with_adapter(product_id, search_queries(details["name"], query), out_dir)
    return _specs_tail(details, page, page["query"], out_dir)


def _specs_tail(details, page, query, out_dir):
    """The /products/specs answer from a page read ({url, html, product}), however the card was reached (the
    search here, a held listing tab in ext_listing_tab). `details` is read before the click (the box: its failure
    costs no page load)."""
    if not pdp.spec_rows(page["html"]):   # every product page lists at least 상품번호: not rendered, or changed
        raise AdapterError(f"adapter error: product {details['id']}: no 상품정보 list on the product page "
                           f"{page['url']} (saved to {out_dir}); retry, or the page layout changed")
    return specs_from_page(details, page["html"], page.get("product"), query)


def specs_from_page(details, page_html, product_answer, query=None):
    """The /products/specs answer from the product record and the page as read: pure (no browser, no clock but
    read_at), so saved pages replay offline (naver_shopping/fixtures/pages/, test_pages.py)."""
    product_id = details["id"]
    rows = pdp.spec_rows(page_html)
    options = parsers.parse_page_options(product_answer, pdp.text_fields(page_html)) if product_answer else None
    return {
        "id": product_id,
        "name": details["name"],
        "link": details["link"],
        "query": query,
        "category": details["category"],
        "specs": rows,
        "is_complete": not pdp.specs_collapsed(page_html),
        "facts": parsers.product_facts(details, details["notice"], rows),
        "options": options,
        "delivery": parsers.parse_page_delivery(product_answer, pdp.delivery_promise(page_html))
        if product_answer else None,
        "measures": measures.measures(rows, details["notice"], details.get("description"), page_html, product_id,
                                      options, details["name"], details["category"]),
        "read_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def product_page(product, query=None):
    """The /products/page answer, for development and analysis: the product page itself as the owner's Chrome
    rendered it (상품정보 unfolded), and the page's own product answer, read the same way as /products/specs
    (search -> card -> page). Never cached: every call reads the page."""
    details = api.product_details(product)
    queries = search_queries(details["name"], query)
    if not queries:
        raise NotListed(f"product {product}: no name to search for; pass query")
    out_dir = os.path.join(OUTPUT_ROOT, datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{details['id']}")
    page = _with_adapter(details["id"], queries, out_dir)
    return {"id": details["id"], "link": details["link"], "query": page["query"], "url": page.get("url"),
            "title": page.get("title"), "search_url": page.get("search_url"), "html": page.get("html") or "",
            "product_answer": page.get("product"), "saved_to": out_dir,
            "read_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def product_specs(product, query=None):
    """The /products/specs answer. `query` (the search that lists the product)
    defaults to the product's name, then its first words (search_queries)."""
    query = query or api.product_details(product)["name"]
    if not query:
        raise NotListed(f"product {product}: no name to search for; pass query")
    key = {"product": product, "query": query}
    result = cached_call("naver_shopping.product_specs", key, _specs, ttl.PRODUCT_SPECS_CACHE)
    # A list left folded, or no product answer from the page (options unknown): answer it, but the next call
    # reads the page again.
    if not result["is_complete"] or result["options"] is None:
        forget("naver_shopping.product_specs", key)
    return result
