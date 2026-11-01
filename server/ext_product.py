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
import os
import time
from datetime import datetime, timezone

import ext_listing
import listing_jobs
from cache import cached_call, forget
from ext_bridge import ExtError
from naver_shopping import api, parsers, pdp
from naver_shopping import cache_config as ttl
from scraper_errors import NotFound

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "ext-product")
MORE_BUTTON = 'button[data-shp-area="pdinfo.more"]'     # "상품정보 펼쳐보기" (2026-11-01)
FULL_HTML = 8_000_000      # chars: a smartstore product page is ~0.6 MB
RENDER_TRIES = 8           # page reads, RENDER_WAIT_S apart, until the 상품정보 list is rendered
RENDER_WAIT_S = 2


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


def _card(bridge, tab, product_id):
    """The selector of the product's card link on the search page, or None.
    Cards link to smartstore.naver.com/main/products/<id>?nl-query=... (2026-11-01)."""
    for sel in (f'a[href*="/products/{product_id}?"]', f'a[href$="/products/{product_id}"]'):
        if (bridge.call("query", tabId=tab, selector=sel) or {}).get("count"):
            return sel
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
    try:
        tab, why = ext_listing.open_search(bridge, query, out_dir)
        if tab is None:
            raise PageBlocked(f"product {product_id}: {why}")
        search_url = (bridge.call("page", tabId=tab, headChars=0) or {}).get("url")
        selector = _card(bridge, tab, product_id)
        if not selector:
            raise NotListed(f"product {product_id} is not on the search page for {query!r}; "
                            "pass a query that finds it (its name, or a shorter part of it)")
        ext_listing.pause(1, 2.5)
        clicked = bridge.call("click", tabId=tab, selector=selector)
        page_tab = clicked.get("newTabId") or tab
        bridge.call("wait_load", tabId=page_tab, timeoutMs=45000)
        ext_listing.pause(3, 5)
        if not ext_listing.check(bridge, page_tab, "product", out_dir):
            raise PageBlocked(f"product {product_id}: a wall on the product page")
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
        return {"url": page.get("url"), "title": page.get("title"), "html": html, "search_url": search_url}
    except ExtError as e:
        raise AdapterError(f"product {product_id}: adapter error: {e}")
    finally:
        _close_tabs(bridge)


def _specs(product, query):
    details = api.product_details(product)
    product_id = details["id"]
    out_dir = os.path.join(OUTPUT_ROOT, datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{product_id}")
    try:
        page = listing_jobs.with_adapter(lambda bridge: read_page(bridge, product_id, query, out_dir))
    except listing_jobs.Busy as e:
        raise AdapterBusy(f"the adapter is busy ({e}), retry when it is done")
    except listing_jobs.NoExtension:
        raise AdapterError("the browser extension is not connected: open Chrome with the "
                           "naver-scrap adapter loaded (extension/README.md)")
    rows = pdp.spec_rows(page["html"])
    if not rows:            # every product page lists at least 상품번호: not rendered, or the layout changed
        raise AdapterError(f"product {product_id}: no 상품정보 list on the product page {page['url']} "
                           f"(saved to {out_dir}); retry, or the page layout changed")
    return {
        "id": product_id,
        "name": details["name"],
        "link": details["link"],
        "query": query,
        "category": details["category"],
        "specs": rows,
        "is_complete": not pdp.specs_collapsed(page["html"]),
        "facts": parsers.product_facts(details, details["notice"], rows),
        "read_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def product_specs(product, query=None):
    """The /products/specs answer. `query` (the search that lists the product)
    defaults to the product's name."""
    query = query or api.product_details(product)["name"]
    if not query:
        raise NotListed(f"product {product}: no name to search for; pass query")
    key = {"product": product, "query": query}
    result = cached_call("naver_shopping.product_specs", key, _specs, ttl.PRODUCT_SPECS_CACHE)
    if not result["is_complete"]:          # a list left folded: answer it, but the next call reads the page again
        forget("naver_shopping.product_specs", key)
    return result
