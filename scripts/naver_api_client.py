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
from collections.abc import Iterator

import requests
from urllib3.exceptions import NewConnectionError

import naver_types as T

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def load_env_file(path=ENV_FILE):
    """The repo-root .env (KEY=value lines) into os.environ, never overriding
    a variable already set. Same rules as server/config.load_env_file (scripts
    do not import server code)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip().removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if key and value and key not in os.environ:
                os.environ[key] = value


load_env_file()

DEFAULT_URL = "http://localhost:8000"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 900
RETRY_BACKOFF = (10, 30)            # seconds before retry 1 and retry 2
RETRY_STATUSES = (502,)
SITE_PREFIX = "/naver-shopping"     # routes.mount also serves every path under it
# the schema page limits (server/naver_shopping/schemas.py MAX_REVIEW_PAGE / MAX_RANK_PAGE)
PAGE_CAPS = {"/products/reviews": 500, "/keywords/rank": 25}
LISTING_POLL = 5                    # seconds between job status checks


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
        return self._request("GET", path, params)

    def post(self, path, **params):
        """POST with query params (POST /listings); answers 200 / 202 are returned."""
        return self._request("POST", path, params)

    def _request(self, method, path, params):
        url = self.base_url + "/" + path.lstrip("/")
        params = {k: v for k, v in params.items() if v is not None}
        attempt = 0
        while True:
            try:
                resp = self.session.request(method, url, params=params, timeout=self.timeout)
            except requests.exceptions.ReadTimeout:
                raise                    # the server is still working on it: never retry
            except requests.exceptions.ConnectionError as e:
                if not _never_connected(e) or attempt >= len(RETRY_BACKOFF):
                    raise
                print(f"naver_api_client: {path} connection failed ({type(e).__name__}), "
                      f"retry in {RETRY_BACKOFF[attempt]} s")
            else:
                if resp.status_code in (200, 202):
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

    # ---- typed endpoint methods: the same get(), named and typed (naver_types) ----------
    # Filters / window params are passed through as keyword args, exactly as the
    # endpoint takes them (server/docs/ENDPOINTS.md); None values are dropped.

    def health(self) -> T.Health:
        return self.get("/health")

    def search(self, query: str, **filters) -> T.SearchResult:
        """Up to 96 cards; filters: min_price, max_price, category, min_rating, free_delivery, ..."""
        return self.get("/products/search", query=query, **filters)

    def count(self, query: str, **filters) -> T.CountResult:
        return self.get("/products/count", query=query, **filters)

    def product_details(self, product: str) -> T.ProductDetails:
        """`product`: a store product link or the bare product id."""
        return self.get("/products/details", product=product)

    def product_specs(self, product: str, query: str | None = None) -> T.ProductSpecs:
        """The product page's 상품정보 rows (server-side: the owner's Chrome through the adapter,
        ~30 s cold, cached a day). `query`: a search that lists the product (default: its name).
        ApiError 404 = its card was not on that search page, 409 = the adapter is busy (a listing job),
        503 = the extension is not connected, a wall, or the page did not render. Neither is retried here."""
        return self.get("/products/specs", product=product, query=query)

    def reviews(self, product: str, sort: str | None = None, max_page: int | None = None) -> Iterator[T.ReviewsPage]:
        """Review pages (20 each), page 1 first; sort: ranking, recent, score_high, score_low."""
        return self.pages("/products/reviews", max_page=max_page, product=product, sort=sort)

    def store_details(self, store: str) -> T.StoreDetails:
        return self.get("/stores/details", store=store)

    def store_products(self, store: str, list: str = "popular", period: str | None = None) -> T.StoreProducts:
        """list: popular (20) or best (30, period: realtime / daily / weekly / monthly)."""
        return self.get("/stores/products", store=store, list=list, period=period)

    def catalog_reviews(self, catalog: str) -> T.CatalogReviews:
        return self.get("/catalogs/reviews", catalog=catalog)

    def categories(self, category: str | None = None) -> T.CategoryList:
        """A category and its children; none / 0 = the top level."""
        return self.get("/categories/list", category=category)

    def keywords_rank(self, category: str, max_page: int | None = None, **window) -> Iterator[T.KeywordRankPage]:
        """Top keyword pages (20 each, up to 25 pages); window: start_date, end_date, period, device, ..."""
        return self.pages("/keywords/rank", max_page=max_page, category=category, **window)

    def keyword_trend(self, keyword: str, category: str, **window) -> T.KeywordTrend:
        return self.get("/keywords/trend", keyword=keyword, category=category, **window)

    def category_trend(self, category: str, **window) -> T.CategoryTrend:
        return self.get("/categories/trend", category=category, **window)

    def listing(self, query: str, max_batches: int = 0, poll: float = LISTING_POLL) -> T.ListingResult:
        """The full search listing for a query (server-side: the owner's Chrome
        through the adapter; this client does not care). Starts a job, waits
        while it runs (a captcha only shows as status "captcha"), then reads
        every row. -> {"job": <final job>, "results": [rows]}; a stopped job
        returns what it got, job["stop"] says why. ApiError 409 = another
        listing runs (or a /products/specs read: job_id null), 503 = the browser extension is not connected."""
        job = self.post("/listings", query=query, max_batches=max_batches or None)
        last = None
        while job["status"] in ("running", "captcha"):
            if job["status"] != last:
                print(f"naver_api_client: listing {job['id']} {job['status']} ({job.get('kept') or 0} rows)")
                last = job["status"]
            self.sleep(poll)
            job = self.get(f"/listings/{job['id']}")
        print(f"naver_api_client: listing {job['id']} {job['status']}: {job.get('kept')} rows, stop: {job.get('stop')}")
        rows: list[T.ListingRow] = []
        for page in self.pages(f"/listings/{job['id']}/products"):
            rows.extend(page.get("results") or [])
        return {"job": job, "results": rows}


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
