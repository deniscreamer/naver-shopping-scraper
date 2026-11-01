"""Runs the Naver Shopping calls only a real browser can make, with a Google
Chrome (patchright) on this machine.

Naver's store backend (brand.naver.com/n/...) serves every store's product
records, options, descriptions, reviews and best-seller lists, but answers
HTTP 429 to any plain HTTP client, even one replaying a browser's cookies.
Inside a real brand.naver.com page the same calls are answered. So
naver_shopping/fetch.py asks this module for them (`ExitPool.fetch_any`):
one Chrome per proxy opens a brand store page once, then runs each requested
call as a same-origin fetch() inside that page and returns the raw JSON —
naver_shopping/ parses it. The Chrome is kept open between requests, closed
after BROWSER_IDLE seconds unused, and relaunched when Naver refuses it.

Needs Google Chrome installed (patchright drives it); a window opens. If
Naver starts refusing your IP, set NAVER_SHOPPING_PROXY (see config.py).

Same interface as the hosted service's client for its browser servers:
ExitPool, fetch_any() and the exception classes, so naver_shopping/ runs
unchanged."""
import threading
import time

BRAND = "https://brand.naver.com"
ANCHOR = BRAND + "/samsung/best"
WALL_MARKERS = ('title="captcha"', "wtm_captcha", "ncpt.naver.com/v1/wcpt", "nidlogin.login", "에러페이지")
REFUSE_STATUSES = (403, 405, 429, 490)
BLOCK_RESOURCES = ("image", "font", "media")
BROWSER_IDLE = 300          # close a Chrome nobody used for this long
# headers a page-level fetch() must not carry (the browser sets its own)
_DROP_PREFIXES = ("sec-", "origin", "referer", "accept-language", "upgrade-", "host", "content-length",
                  "user-agent", "accept-encoding", "connection")


class BoxUnavailable(Exception):
    """Chrome could not start on this machine (not installed, no display)."""

    def __init__(self, message="", candidate=None):
        super().__init__(message)
        self.candidate = candidate
        self.proxy = None


class BoxRefused(Exception):
    """Naver refused this exit (captcha, login gate or 429 inside the page)."""

    def __init__(self, message="", candidate=None):
        super().__init__(message)
        self.candidate = candidate
        self.proxy = None


def walled(html):
    head = (html or "")[:8000]
    return any(m in head for m in WALL_MARKERS)


def _clean_headers(headers):
    return {k: v for k, v in (headers or {}).items() if not k.lower().startswith(_DROP_PREFIXES)}


# ---- one Chrome per proxy --------------------------------------------------------------

def _launch(proxy):
    try:
        from patchright_driver import PatchrightDriver
        return PatchrightDriver(proxy, headless=False, geoip_timezone=bool(proxy),
                                block_resources=list(BLOCK_RESOURCES))
    except Exception as e:
        raise BoxUnavailable(f"could not start Chrome: {type(e).__name__}: {e}")


class _Browser:
    def __init__(self, proxy):
        self.proxy = proxy
        self.lock = threading.Lock()
        self.driver = None
        self.last_use = time.monotonic()

    def warm(self):
        """Open the anchor brand store page once; every call then runs inside it."""
        self.driver = _launch(self.proxy)
        try:
            try:
                nav = self.driver.nav(ANCHOR, referer="https://www.naver.com/", mode="blocked") or {}
            except Exception as e:
                raise BoxRefused(f"naver-shopping: the anchor page failed to load ({type(e).__name__}: {str(e)[:160]})")
            status, url, html = nav.get("status"), nav.get("url") or "", nav.get("html") or ""
            if "nid.naver.com" in url:
                raise BoxRefused("naver-shopping: Naver sent this exit to its login page")
            if status in REFUSE_STATUSES or walled(html):
                raise BoxRefused(f"naver-shopping: Naver's captcha / rate wall on this exit (HTTP {status}); "
                                 "set NAVER_SHOPPING_PROXY to another IP")
            if "__PRELOADED_STATE__" not in html:
                raise BoxRefused(f"naver-shopping: the anchor page did not render (HTTP {status})")
        except Exception:
            self.close()
            raise

    def fetch_one(self, url, method, headers, body=None):
        method = (method or "GET").upper()
        headers = _clean_headers(headers)
        if method == "GET":
            r = self.driver.get(url, headers=headers or None, referrer=ANCHOR)
        else:
            r = self.driver.request(method, url, headers=headers or None, body=body, referrer=ANCHOR)
        if not r.status_code and r.error:
            raise BoxRefused(f"naver-shopping: in-page fetch failed: {r.error}")
        out = {"status": r.status_code, "headers": dict(r.headers or {}), "body": r.text, "final_url": r.url or url}
        if out["status"] in REFUSE_STATUSES or walled(out["body"]) or "nid.naver.com" in (out["final_url"] or ""):
            raise BoxRefused(f"naver-shopping: refused inside the browser (HTTP {out['status']})")
        return out

    def close(self):
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


_browsers = {}
_browsers_lock = threading.Lock()


def _browser(proxy):
    with _browsers_lock:
        now = time.monotonic()
        for key, b in list(_browsers.items()):
            if key != proxy and b.driver is not None and now - b.last_use > BROWSER_IDLE and not b.lock.locked():
                b.close()
        b = _browsers.get(proxy)
        if b is None:
            b = _browsers[proxy] = _Browser(proxy)
        return b


def fetch(site, url=None, urls=None, method="GET", headers=None, body=None, proxy=None,
          variant="", session=None, timeout=None):
    """One call (or several) inside the kept Chrome for `proxy`."""
    b = _browser(proxy)
    with b.lock:
        b.last_use = time.monotonic()
        if b.driver is None:
            b.warm()
        try:
            if urls:
                return [b.fetch_one(u, method, headers, body) for u in urls]
            return b.fetch_one(url, method, headers, body)
        except BoxRefused:
            b.close()
            raise
        except Exception as e:
            b.close()
            raise BoxUnavailable(f"naver-shopping: Chrome failed: {type(e).__name__}: {e}")


def fetch_any(site, candidates, url=None, urls=None, method="GET", headers=None, body=None, variant="",
              timeout=None):
    """fetch() on the first candidate [(proxy, session), ...] -> (index, result);
    a refusal carries the index so the caller rotates that exit."""
    proxy = candidates[0][0] if candidates else None
    try:
        return 0, fetch(site, url=url, urls=urls, method=method, headers=headers, body=body, proxy=proxy,
                        variant=variant, timeout=timeout)
    except (BoxRefused, BoxUnavailable) as e:
        e.candidate = 0
        e.proxy = proxy
        raise


# ---- sticky exits per site (the hosted client's holder, unchanged) ------------------------

class ExitPool:
    """Sticky proxy exits for one site's browsers: `mint` returns a fresh
    proxy URL (or None for your own IP), `size` how many are kept per key.
    With NAVER_SHOPPING_PROXY there is exactly one exit, so every slot is
    the same proxy and rotate() only relaunches Chrome on it."""

    def __init__(self, site, mint, size=1):
        self.site = site
        self._mint = mint
        self._size = size
        self._lock = threading.Lock()
        self._slots = {}
        self._next = {}
        self._filled = {}

    def _n(self):
        n = self._size() if callable(self._size) else self._size
        return max(1, int(n or 1))

    def get(self, key=""):
        with self._lock:
            n = self._n()
            slots = self._slots.setdefault(key, [])
            filled = self._filled.setdefault(key, set())
            while len(slots) < n:
                slots.append(None)
            del slots[n:]
            i = self._next.get(key, 0) % n
            self._next[key] = (i + 1) % n
            if i not in filled:
                slots[i] = self._mint()
                filled.add(i)
            return slots[i]

    def all(self, key=""):
        with self._lock:
            n = self._n()
            slots = self._slots.setdefault(key, [])
            filled = self._filled.setdefault(key, set())
            while len(slots) < n:
                slots.append(None)
            del slots[n:]
            for i in range(n):
                if i not in filled:
                    slots[i] = self._mint()
                    filled.add(i)
            return list(slots)

    def fetch_any(self, site, key="", sessions=None, **kw):
        exits = self.all(key)
        candidates = [(p, sessions(p) if sessions else None) for p in exits]
        try:
            index, out = fetch_any(site, candidates, **kw)
        except (BoxRefused, BoxUnavailable) as e:
            if e.candidate is not None and 0 <= e.candidate < len(exits):
                e.proxy = exits[e.candidate]
            raise
        return exits[index], out

    def rotate(self, proxy, key=""):
        with self._lock:
            slots = self._slots.get(key) or []
            filled = self._filled.setdefault(key, set())
            for i, cur in enumerate(slots):
                if cur == proxy and i in filled:
                    slots[i] = self._mint()
                    return True
            return False

    def current(self, key=""):
        with self._lock:
            return list(self._slots.get(key) or [])

    def reset(self, key=None):
        with self._lock:
            if key is None:
                self._slots.clear(); self._next.clear(); self._filled.clear()
            else:
                self._slots.pop(key, None); self._next.pop(key, None); self._filled.pop(key, None)
