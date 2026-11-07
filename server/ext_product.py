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

Products/details stays on the box; this route only adds what the page has.
One adapter user at a time (listing_jobs.with_adapter): a running listing
job makes a read busy (409). Walls are handled like the listing's
(ext_listing.check: a captcha is reported and waited for, a ban page stops)
and answer 503, which scripts do not retry.
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


# Not UpstreamError / Blocked (502): scripts retry a 502, and a wall in the
# owner's Chrome is never retried (R-EXT-3). routes.call answers `status`.
class AdapterError(Exception):
    """The adapter could not read the page: not connected, or failed mid-read."""
    status = 503


class AdapterBusy(AdapterError):
    """A listing job (or another read) is using the adapter."""
    status = 409


class PageBlocked(AdapterError):
    """A captcha not solved in time, a login gate or a ban page on the way to the product page."""


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


def _close_tabs(bridge):
    try:
        for t in bridge.call("tabs") or []:
            bridge.call("tab_close", tabId=t["tabId"])
    except ExtError:
        pass


def read_page(bridge, product_id, query, out_dir):
    """-> {url, title, html, search_url}: the product page after a click from
    the search for `query`, its 상품정보 list unfolded. Closes its tabs."""
    os.makedirs(out_dir, exist_ok=True)
    started = time.monotonic()
    try:
        tab, why = ext_listing.open_search(bridge, query, out_dir)
        if tab is None:
            raise PageBlocked(f"product {product_id}: {why}")
        search_url = (bridge.call("page", tabId=tab, headChars=0) or {}).get("url")
        selector = _card(bridge, tab, product_id)
        if not selector:
            raise CardMissing(f"product {product_id} is not on the search page for {query!r}; "
                              "pass a query that finds it (its name, or a shorter part of it)")
        ext_listing.pause(1, 2.5)
        clicked = bridge.call("click", tabId=tab, selector=selector)
        if not clicked.get("newTabId"):
            # 2026-11-05: one photo click in 20 opened nothing (still on the search page): one more click
            ext_listing.pause(1.5, 3)
            if "/products/" not in ((bridge.call("page", tabId=tab, headChars=0) or {}).get("url") or ""):
                clicked = bridge.call("click", tabId=tab, selector=selector)
        page_tab = clicked.get("newTabId") or tab
        bridge.call("wait_load", tabId=page_tab, timeoutMs=45000)
        ext_listing.pause(3, 5)
        # 2026-11-06: a product whose page Naver cannot serve opens shopv.pstatic.net/web/maintenance/
        # internal-error.html (twice in a row on 10302181901): when the tab can be read it is not a wall, the
        # product is unavailable now (404). Mostly the adapter cannot read that host and the read fails before this
        # check, answered 503 (KNOWN_ISSUES K-21); it passes in minutes
        tab_url = next((t.get("url") or "" for t in bridge.call("tabs") or [] if t.get("tabId") == page_tab), "")
        if "/web/maintenance/" in tab_url:
            raise NotListed(f"product {product_id}: Naver shows its error page ({tab_url[:80]})")
        if not ext_listing.check(bridge, page_tab, "product", out_dir):
            raise PageBlocked(f"product {product_id}: a wall on the product page")
        # A click on the card's centre can land on its store link (2026-11-01: the Honma D1 card in the
        # 남성 골프채 풀세트 search opened smartstore.naver.com/thegolf); then the card counts as not found.
        landed = (bridge.call("page", tabId=page_tab, headChars=0) or {}).get("url") or ""
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
        card = "link" if selector.startswith("a[") else "photo"
        folded = ", folded" if pdp.specs_collapsed(html) else ""
        print(f"ext-product: {product_id} read in {time.monotonic() - started:.0f} s: card by {card}, "
              f"{len(pdp.spec_rows(html))} rows{folded}, options {'yes' if product else 'NO'}", flush=True)
        return {"url": page.get("url"), "title": page.get("title"), "html": html, "search_url": search_url,
                "product": product}
    except ExtError as e:
        raise AdapterError(f"product {product_id}: adapter error: {e}")
    finally:
        _close_tabs(bridge)


def _read_listed(bridge, product_id, queries, out_dir):
    """read_page for the first query whose search page has the card; the next query only when the card was not
    there (CardMissing), within the same adapter turn (one adapter user at a time) and still from a search page
    (R-NAVER-1). -> the page dict plus "query" (the one that listed it)."""
    for i, query in enumerate(queries):
        try:
            return {**read_page(bridge, product_id, query, out_dir), "query": query}
        except CardMissing:
            if i == len(queries) - 1:
                raise
            print(f"ext-product: {product_id} not listed for {query!r}, trying {queries[i + 1]!r}", flush=True)
            ext_listing.pause(2, 4)
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
    if not pdp.spec_rows(page["html"]):   # every product page lists at least 상품번호: not rendered, or changed
        raise AdapterError(f"product {product_id}: no 상품정보 list on the product page {page['url']} "
                           f"(saved to {out_dir}); retry, or the page layout changed")
    return specs_from_page(details, page["html"], page.get("product"), page["query"])


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
