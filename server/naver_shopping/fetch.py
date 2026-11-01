"""Naver Shopping transport: plain curl_cffi for the open surfaces, one
parked brand.naver.com page on the browser box for the product JSON that
answers 429 to any non-browser client. No account, no cookies kept.

Why this shape (research 2026-10-23/24): every Naver Shopping page of its
own — search.shopping.naver.com/ns/*, the catalog pages,
smartstore.naver.com/<store>/products/<id>, shopping.naver.com — serves
Naver's WtmCaptcha (HTTP 405/490), a login redirect (nid.naver.com) or a
429 error page to every client we have (fresh real Chrome, Korean
residential exits, the natural click path from naver.com). The data is
served elsewhere:

  * SEARCH     GET ns-portal.shopping.naver.com/api/v3/shopping-paged-slot
               (+ /count) — the backend of the shopping widget on Naver's
               own search page (search.naver.com). It needs the widget's
               x-ns-* headers; any page / session id is accepted (verified
               2026-10-24, no page fetch needed). TREND view on a mobile
               device type answers 4 pages x 24 = 96 cards; filters are
               query params (price "min|max", categoryIds "03"+id, booleans).
  * STORE      GET smartstore.naver.com/<slug>/best (or brand.naver.com/
               <slug>/best) — server-rendered, carries the store record
               (channelUid, payReferenceKey = checkoutMerchantNo, grade,
               categories) while the store home / category / search pages
               redirect to login. 6/6 from a laptop and from KR exits.
  * BRAND PDP  GET brand.naver.com/<slug>/products/<id> — server-rendered
               (window.__PRELOADED_STATE__.simpleProductForDetailPage).
  * DATALAB    POST datalab.naver.com/shoppingInsight/*.naver — open JSON.
  * BOX        in-page fetch() on a parked brand.naver.com page
               (recipes/naver_shopping.py): the store backend
               brand.naver.com/n/v1|v2/* serves ANY store's products to a
               browser page (simple-products, validation-products,
               contents, provided-notice, review summary + pages, popular /
               best lists, category tree, catalog-reviews) and 429s every
               curl replay, cookies and headers included.

Egress: config.naver_shopping_proxy() (knob NAVER_SHOPPING_EXIT) for the
curl surfaces, one sticky exit per thread session, dropped on every
retryable failure; browser_client.ExitPool("naver-shopping", ...) for the
box browsers (knob NAVER_SHOPPING_BROWSER_EXIT), rotated on a refusal.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  NaverUpstreamError   transport failure / 5xx / empty answer   — retryable
  NaverBlocked         captcha / login redirect / 405 418 429    — retryable
  NaverBadRequest      upstream 400                              — never retried
  NaverNotFound        unknown product / store / catalog          — never retried
"""
import json
import os
import random
import string
import sys
import threading
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from naver_shopping.refs import BRAND, DATALAB, SEARCH_PORTAL, SMARTSTORE

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 30
JSON_TIMEOUT = 20
BOX_SITE = "naver-shopping"

SEARCH_SLOT_PATH = "/api/v3/shopping-paged-slot"
SEARCH_COUNT_PATH = "/api/v3/shopping-paged-slot/count"
DATALAB_PATH = "/shoppingInsight/"

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
DATALAB_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "origin": DATALAB,
    "referer": DATALAB + "/shoppingInsight/sCategory.naver",
}
BOX_HEADERS = {"accept": "application/json, text/plain, */*", "content-type": "application/json"}

CAPTCHA_MARKERS = ('title="captcha"', "wtm_captcha", "ncpt.naver.com/v1/wcpt")
LOGIN_HOST = "nid.naver.com"
NOT_OPERATING_TITLE = "현재 운영되고 있지 않습니다"   # brand host: slug is not a brand store
NO_PRODUCT_TITLE = "상품이 존재하지 않습니다"          # brand host: unknown product


class NaverUpstreamError(UpstreamError):
    """Transport failure, 5xx or an empty answer — retryable."""


class NaverBlocked(NaverUpstreamError, Blocked):
    """Captcha, login redirect, 405 / 418 / 429 / 490 — retryable on a fresh exit."""


class NaverBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class NaverNotFound(NotFound):
    """Product / store / catalog does not exist — never retried."""


# ---- curl sessions --------------------------------------------------------------
# One session per cheroot worker thread (a curl handle must not cross
# threads); keep-alive within the thread; dropped on every retryable
# failure so the retry rides a fresh exit.

_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.naver_shopping_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        # the shopping widget's identity for this session: ns-portal accepts
        # any value, it only refuses requests that carry none
        _local.widget_ids = (_token(24) + "-" + "".join(random.choices(string.digits, k=6)), _token(24))
        # Since 2026-10-29 ns-portal answers 418 to a request carrying no
        # naver.com cookie at all, on every exit (pod, datacenter, KR
        # residential); any one naver.com cookie passes, a made-up NNB (the
        # browser-id cookie every Naver page sets, 13 uppercase letters /
        # digits) included. One per session: the same NNB seen from several
        # exits within seconds was refused on the residential pool.
        sess.cookies.set("NNB", nnb_cookie(), domain=".naver.com")
        _local.session = sess
    return sess


def _token(n):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def nnb_cookie():
    """A value shaped like Naver's own NNB browser id (EHHTOF73MDNWU)."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=13))


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (NaverUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except NaverUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _looks_blocked(text):
    head = (text or "")[:4000]
    return any(m in head for m in CAPTCHA_MARKERS)


def _title(text):
    import re
    match = re.search(r"<title>([^<]*)</title>", text or "")
    return match.group(1).strip() if match else ""


def _classify(resp, label):
    """Map a curl response to the taxonomy; return the body text."""
    final = str(getattr(resp, "url", "") or "")
    if LOGIN_HOST in final:
        raise NaverBlocked(f"login gate on {label}")
    text = resp.text
    if resp.status_code in (405, 418, 429, 490, 403) or _looks_blocked(text):
        raise NaverBlocked(f"HTTP {resp.status_code} (captcha / rate wall) on {label}")
    if resp.status_code == 404:
        raise NaverNotFound(f"{label} not found")
    if resp.status_code == 400:
        raise NaverBadRequest(resp.text[:200])
    if resp.status_code != 200:
        raise NaverUpstreamError(f"HTTP {resp.status_code} on {label}")
    return text


def _get(url, label, headers=None, params=None, timeout=PAGE_TIMEOUT):
    def once():
        try:
            resp = _session().get(url, headers={**PAGE_HEADERS, **(headers or {})}, params=params,
                                  timeout=timeout, allow_redirects=True)
        except Exception as e:
            raise NaverUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


# ---- search (ns-portal) ---------------------------------------------------------

def _widget_headers(device):
    _session()
    page_id, session_id = _local.widget_ids
    host = "https://m.search.naver.com" if device == "mobile" else "https://search.naver.com"
    return {
        "accept": "*/*", "content-type": "application/json",
        "origin": host, "referer": host + "/",
        "x-ns-rev": "4", "x-ns-page-id": page_id, "x-ns-session-id": session_id,
        "x-ns-device-type": device, "x-ns-view-type": "TREND", "x-ns-route": "s",
        "x-ns-referer": "-", "x-ns-client-hint": "{}",
    }


def _portal_json(path, params, label):
    def once():
        try:
            resp = _session().get(SEARCH_PORTAL + path, params=params, headers=_widget_headers("mobile"),
                                  timeout=JSON_TIMEOUT)
        except Exception as e:
            raise NaverUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label)
        try:
            payload = json.loads(text)
        except ValueError:
            raise NaverBlocked(f"non-JSON answer on {label}: {text[:120]!r}")
        if not isinstance(payload, dict) or "data" not in payload:
            # {} = the widget headers were refused; a fresh session rolls new ids
            raise NaverUpstreamError(f"empty answer on {label} (widget headers refused)")
        return payload["data"]
    return _retrying(once)


def search_params(query, filters=None):
    """The ns-portal query: the widget's fixed keys + the caller's filters."""
    params = {"isFastDelivery": "false", "isArriveGuarantee": "false", "query": query, "source": "shp_tli"}
    for key, value in (filters or {}).items():
        if value is None or value is False or value == []:
            continue
        params[key] = ("true" if value is True else ",".join(map(str, value)) if isinstance(value, list) else str(value))
    return params


def fetch_search(query, filters=None):
    """-> the list of slot pages ([{page, pageSize, slots: [{slotType, data}]}])."""
    data = _portal_json(SEARCH_SLOT_PATH, search_params(query, filters), f"search {query!r}")
    return data if isinstance(data, list) else []


def fetch_search_count(query, filters=None):
    """-> the site's total match count (int) or None."""
    data = _portal_json(SEARCH_COUNT_PATH, search_params(query, filters), f"search count {query!r}")
    return data if isinstance(data, int) else None


# ---- store + brand pages (curl) ---------------------------------------------------

def fetch_store_page(slug, is_brand=False):
    """GET <host>/<slug>/best -> HTML carrying the store record. The brand
    host answers a non-brand slug with an 'not operating' page (NotFound
    here; the caller then tries the smartstore host)."""
    base = BRAND if is_brand else SMARTSTORE
    label = f"store {slug}"
    text = _get(f"{base}/{quote(slug)}/best", label)
    if NOT_OPERATING_TITLE in _title(text):
        raise NaverNotFound(f"{label} not found")
    return text


def fetch_brand_product_page(slug, product_id):
    """GET brand.naver.com/<slug>/products/<id> -> HTML (server-rendered product)."""
    label = f"product {product_id}"
    text = _get(f"{BRAND}/{quote(slug)}/products/{product_id}", label)
    if NO_PRODUCT_TITLE in _title(text):
        raise NaverNotFound(f"{label} not found")
    return text


# ---- DataLab --------------------------------------------------------------------

def fetch_datalab(action, form):
    """POST datalab.naver.com/shoppingInsight/<action>.naver -> JSON."""
    label = f"datalab {action}"

    def once():
        try:
            resp = _session().post(DATALAB + DATALAB_PATH + action + ".naver", data=form,
                                   headers=DATALAB_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise NaverUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 500:
            # DataLab answers a parameter it cannot serve (unknown category id,
            # an impossible window) with a plain 500: not an outage, not retried
            raise NaverBadRequest(f"DataLab rejected the parameters of {label}")
        text = _classify(resp, label)
        try:
            return json.loads(text)
        except ValueError:
            raise NaverBlocked(f"non-JSON answer on {label}: {text[:120]!r}")
    return _retrying(once)


# ---- the browser box (brand.naver.com in-page fetches) ---------------------------
# The box keeps one browser per proxy URL; the SAME URL must reach every
# call that should land on that browser (browser_client.ExitPool), and a
# refusal (captcha / login / 429 inside the page) rotates the exit.

_EXITS = browser_client.ExitPool(BOX_SITE, config.naver_shopping_browser_proxy,
                                 size=lambda: config.NAVER_SHOPPING_BROWSER_SLOTS)

BOX_RETRY_STATUSES = (500, 502, 503, 504)


def _box_call(label, **kw):
    """A box fetch on whichever sticky exit's browser the box finds free
    (every exit is offered: ExitPool.fetch_any), rotating the one it used on
    a refusal (up to NAVER_SHOPPING_BOX_ATTEMPTS); a box outage is retryable
    upstream."""
    last = None
    for _ in range(max(1, int(config.NAVER_SHOPPING_BOX_ATTEMPTS))):
        try:
            return _EXITS.fetch_any(BOX_SITE, **kw)[1]
        except browser_client.BoxRefused as e:
            if e.candidate is not None:
                _EXITS.rotate(e.proxy)
            last = NaverBlocked(f"{label}: refused in the box browser: {e}")
        except browser_client.BoxUnavailable as e:
            raise NaverUpstreamError(f"{label}: browser box unavailable: {e}")
    raise last


def _box_answer(res, label):
    """One in-page answer -> parsed JSON, None for an empty / unknown answer
    (204, 400, 404, 419), Blocked for a wall, Upstream for a 5xx."""
    status = int(res.get("status") or 0)
    body = res.get("body") or ""
    if status in (204, 400, 404, 419):
        return None
    if status in (403, 405, 418, 429, 490) or _looks_blocked(body):
        raise NaverBlocked(f"HTTP {status} inside the box browser on {label}")
    if status in BOX_RETRY_STATUSES or status == 0:
        raise NaverUpstreamError(f"HTTP {status} inside the box browser on {label}")
    try:
        return json.loads(body)
    except ValueError:
        raise NaverUpstreamError(f"non-JSON answer inside the box browser on {label}: {body[:120]!r}")


def box_get_many(paths, label):
    """Several brand.naver.com backend GETs on ONE box call -> one parsed
    answer per path (None where the backend had nothing)."""
    if not paths:
        return []
    outs = _box_call(label, urls=[BRAND + p for p in paths], method="GET", headers=BOX_HEADERS)
    if not isinstance(outs, list) or len(outs) != len(paths):
        raise NaverUpstreamError(f"{label}: box answered {len(outs) if isinstance(outs, list) else 'one'} "
                                 f"results for {len(paths)} urls")
    return [_box_answer(o, f"{label} {p.split('?')[0]}") for o, p in zip(outs, paths)]


def box_get(path, label):
    return box_get_many([path], label)[0]


def box_post(path, body, label):
    """One brand.naver.com backend POST (JSON body) on the box."""
    out = _box_call(label, url=BRAND + path, method="POST", headers=BOX_HEADERS,
                    body=json.dumps(body, ensure_ascii=False))
    return _box_answer(out, label)
