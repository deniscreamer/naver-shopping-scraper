"""The single HTTP gateway from scripts/ to a running Naver Shopping API
server (server/run.py). Scripts never import server modules: the server needs
a headed Chrome, owns the cache, the retries and the exit rotation, and
registers routes as an import side effect. Everything here is plain HTTP
against the contract in server/docs/ENDPOINTS.md.

Why the read timeout is long (900 s): a cold /products/details can include a
Chrome launch, the anchor navigation, several sequential in-browser box calls
and curl page loads, possibly twice (box attempts), while queued behind the
per-proxy Chrome lock. The server has no request timeout of its own.

Why a ReadTimeout is never retried: the server keeps working after the client
disconnects, so a retry would queue duplicate work behind the same Chrome.
Only a 502 (block / upstream failure) or a failure to open the connection
(ConnectTimeout, or a ConnectionError wrapping urllib3's NewConnectionError:
refused, DNS) is retried, at most twice, with 10 s / 30 s backoff. Any other
ConnectionError is raised: requests also uses it for a dropped connection and
for a read timeout hit mid-body (requests.models), after the request was sent.

    from naver_api_client import NaverApiClient, ApiError
    api = NaverApiClient()                      # NAVER_API_URL or http://localhost:8000
    api.get("/products/search", query="raspberry pi")
    for page in api.pages("/products/reviews", product="..."):
        ...
"""
import os
import time

import requests
from urllib3.exceptions import NewConnectionError

DEFAULT_URL = "http://localhost:8000"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 900
RETRY_BACKOFF = (10, 30)            # seconds before retry 1 and retry 2
RETRY_STATUSES = (502,)
SITE_PREFIX = "/naver-shopping"     # routes.mount also serves every path under it
# the schema page limits (server/naver_shopping/schemas.py MAX_REVIEW_PAGE / MAX_RANK_PAGE)
PAGE_CAPS = {"/products/reviews": 500, "/keywords/rank": 25}


class ApiError(Exception):
    """A non-200 answer: status 400 (fix the input), 404 (skip), 500 (server
    parser bug) or 502 (blocked / upstream failure, after the retries)."""

    def __init__(self, status, error=None, errors=None, path=None):
        self.status = status
        self.error = error
        self.errors = errors
        self.path = path
        super().__init__(f"{path or ''} -> {status}: {error or ''}".strip())


# ---- client -------------------------------------------------------------------------

class NaverApiClient:
    def __init__(self, base_url=None, connect_timeout=CONNECT_TIMEOUT, read_timeout=None, session=None,
                 sleep=time.sleep):
        self.base_url = (base_url or os.environ.get("NAVER_API_URL") or DEFAULT_URL).rstrip("/")
        read = read_timeout or os.environ.get("NAVER_API_READ_TIMEOUT") or READ_TIMEOUT
        self.timeout = (float(connect_timeout), float(read))
        self.session = session or requests.Session()
        self.sleep = sleep

    def get(self, path, **params):
        """GET an unprefixed path (/products/search); None params are dropped.
        Returns the decoded JSON body of a 200, raises ApiError otherwise."""
        url = self.base_url + "/" + path.lstrip("/")
        params = {k: v for k, v in params.items() if v is not None}
        attempt = 0
        while True:
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.ReadTimeout:
                raise                    # the server is still working on it: never retry
            except requests.exceptions.ConnectionError as e:
                if not _never_connected(e) or attempt >= len(RETRY_BACKOFF):
                    raise
                print(f"naver_api_client: {path} connection failed ({type(e).__name__}), "
                      f"retry in {RETRY_BACKOFF[attempt]} s")
            else:
                if resp.status_code == 200:
                    return resp.json()
                body = _json_or_none(resp)
                error = ApiError(resp.status_code, body.get("error") if body else resp.text[:200],
                                 body.get("errors") if body else None, path)
                if resp.status_code not in RETRY_STATUSES or attempt >= len(RETRY_BACKOFF):
                    raise error
                print(f"naver_api_client: {path} -> {resp.status_code}, retry in {RETRY_BACKOFF[attempt]} s")
            self.sleep(RETRY_BACKOFF[attempt])
            attempt += 1

    def pages(self, path, max_page=None, **params):
        """Yield each page of a paginated endpoint, driving `page` ourselves.
        The response's absolute `next` URL is only read as a has-more flag,
        never followed (the server builds it from its own host, which is wrong
        behind a proxy). Stops on a null `next` or an empty `results` (the
        ENDPOINTS.md client rule), at the schema cap or max_page, and on a 400
        whose `errors` name `page` once a page was yielded. Any other 400 raises.
        The cap is found for both /path and /naver-shopping/path."""
        key = "/" + path.lstrip("/")
        if key.startswith(SITE_PREFIX + "/"):
            key = key[len(SITE_PREFIX):]
        cap = PAGE_CAPS.get(key)
        if max_page is not None:
            cap = min(cap, max_page) if cap else max_page
        page = int(params.pop("page", None) or 1)
        yielded = False
        while cap is None or page <= cap:
            try:
                data = self.get(path, page=page, **params)
            except ApiError as e:
                if e.status == 400 and yielded and "page" in (e.errors or {}):
                    return
                raise
            yield data
            yielded = True
            if not data.get("next") or data.get("results") == []:
                return
            page += 1

    def health(self):
        return self.get("/health")


def _never_connected(exc):
    """True when the request cannot have reached the server."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return True
    cause = exc.args[0] if exc.args else None
    return isinstance(getattr(cause, "reason", cause), NewConnectionError)


def _json_or_none(resp):
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None
