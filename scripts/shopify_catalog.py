"""The "already in the shop" check: which Naver offers a Shopify store already has, read from its Admin API.

Read only. Every product of the store is read page by page, in any status (active, draft and archived alike:
a draft or an archived product is still "already there"), with the source key metafields the naver-harvester
writes: `<namespace>.source_offer_id`, and the older `<namespace>.naver_offer_key`; either one counts. A key is
`<namespace>:naver:<channelNo>:<productId>` (listing_filter.source_key). Products are never matched by name.

The check fails loudly instead of answering "not there" (the owner's rule, 2026-11-05):
  * the store has no Shopify values or no credentials yet: ShopNotConfigured, ask the operator, stop on that store;
  * the token is refused or lacks read_products, or the API answers for another shop: CatalogError;
  * a key in the wrong format, or one key on two products: CatalogError, the check stops.

The snapshot is kept at most MAX_AGE (5 minutes): `keys()` reads the catalog again when it is older, so call it
before the run and before each product. A product published after the snapshot is the publisher's final duplicate
check, not this one.

Access (fairwardgolf, checked 2026-11-05 with the operator's other agent and the harvester's shopify-client.ts):
there is no lasting Admin token. The store's Dev Dashboard app mints one from its client id and secret
(POST /admin/oauth/access_token, grant_type client_credentials), valid 24 h (expires_in 86399). So no token is kept
in a file: Credentials mints one per run, in memory, again REFRESH_MARGIN before it ends, and once more after a 401
in the middle of the work (then the request is repeated once; a second 401 stops). The client id and secret stay in
the credentials file the store names (shop_stores.Shopify.credentials_env -> a path, e.g. the harvester's
.env.fairwardgolf with PRODUCTS_API_CLIENT_ID / PRODUCTS_API_CLIENT_SECRET; the ADMIN_API_* app cannot read
products). That file must be mode 0600 and ignored by git (`git check-ignore`), and its values are never put in
os.environ. After each new token the API must answer as the store (`shop { id myshopifyDomain }`) with read_products
in `currentAppInstallation.accessScopes`, and a probe `products(first: 1)` must work. The token can also write
products; this module sends queries only and refuses a mutation. The token, the secret and the auth answer's body
never appear in an error, a repr or a print.

    from shop_stores import get_store
    from shopify_catalog import ShopCatalog
    catalog = ShopCatalog(get_store())
    keys = catalog.keys()            # {"fairwardgolf:naver:100568453:8450665186": "gid://shopify/Product/1", ...}
"""
import http.cookiejar
import os
import re
import stat
import subprocess
import time
from typing import Any, Callable

import requests

from naver_api_client import ENV_FILE
from shop_stores import Store

MAX_AGE = 300                    # seconds a catalog snapshot is trusted (the harvester's NAVER_CATALOG_MAX_AGE_MS)
PAGE = 100                       # products a page: ~302 cost points with the two metafields (bucket 1000 on a
                                 # standard plan; 250 a page would ask ~752 and throttle on a big catalog)
TIMEOUT = 30
RETRIES = 5                      # attempts on 429 / 5xx / THROTTLED
RETRY_WAIT = 2.0                 # seconds, times the attempt, when Shopify gives no better wait
MAX_WAIT = 60.0                  # seconds, the longest single wait
REFRESH_MARGIN = 600             # seconds: a token is replaced this long before it ends
DEFAULT_LIFETIME = 86399         # seconds, when the auth answer gives no expires_in
SCOPE = "read_products"
CLIENT_ID, CLIENT_SECRET = "PRODUCTS_API_CLIENT_ID", "PRODUCTS_API_CLIENT_SECRET"
KEYS = ("source_offer_id", "naver_offer_key")      # the current key, then the older one
KEY_RE = r"^{ns}:naver:\d+:\d+$"

VERIFY_QUERY = "query { shop { id myshopifyDomain } currentAppInstallation { accessScopes { handle } } }"
PROBE_QUERY = "query { products(first: 1) { nodes { id } } }"
PRODUCTS_QUERY = """
query Products($cursor: String) {
  products(first: %d, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id status %s }
  }
}"""
_MUTATION_RE = re.compile(r"^\s*mutation\b|\bmutation\s*[\w({]", re.I)


class ShopNotConfigured(Exception):
    """The store's Shopify values or its credentials are missing or unsafe: ask the operator."""


class CatalogError(Exception):
    """The catalog cannot be trusted (auth refused, another shop, a bad or duplicated key, an API error): stop."""


class _Unauthorized(Exception):
    """A 401 from the GraphQL endpoint: the token ended or was revoked."""


def _session() -> requests.Session:
    session = requests.Session()
    session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))   # never keep a cookie
    return session


def check_env_file(path: str = ENV_FILE) -> None:
    """The repo-root .env (it may hold proxy credentials) must be readable by its owner only."""
    if os.path.exists(path) and stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise ShopNotConfigured(f"{path} is readable by others: run chmod 600 .env")


def _git_ignored(path: str) -> bool:
    """True when git ignores the file, or the file is not inside a git work tree."""
    folder, name = os.path.split(os.path.abspath(path))
    try:
        r = subprocess.run(["git", "-C", folder, "check-ignore", "-q", name], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False                 # inside a repo and not ignored: it could be committed
    return b"not a git repository" in r.stderr.lower()


def read_credentials(path: str, ignored: Callable[[str], bool] = _git_ignored,
                     names: tuple[str, str] = (CLIENT_ID, CLIENT_SECRET)) -> tuple[str, str]:
    """(client id, client secret) from a KEY=value file that is 0600 and ignored by git. Never into os.environ.
    A symlink is checked as the file it points to (mode and git both)."""
    path = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise ShopNotConfigured(f"credentials file {path} does not exist")
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise ShopNotConfigured(f"credentials file {path} is readable by others: chmod 600 it")
    if not ignored(path):
        raise ShopNotConfigured(f"credentials file {path} is not ignored by git: add it to that repo's .gitignore")
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ShopNotConfigured(f"credentials file {path} cannot be read: {type(e).__name__}") from None
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key.strip().removeprefix("export ").strip()] = value
    client_id, secret = values.get(names[0], ""), values.get(names[1], "")
    if not client_id or not secret:
        raise ShopNotConfigured(f"credentials file {path} lacks {names[0]} / {names[1]}")
    return client_id, secret


class Credentials:
    """Mints the store's Admin token from the app's client id + secret; keeps it in memory only."""

    def __init__(self, domain: str, client_id: str, secret: str, session: requests.Session,
                 clock: Callable[[], float] = time.time):
        self.domain, self._client_id, self._secret = domain, client_id, secret
        self._session, self._clock = session, clock
        self._token: str | None = None
        self._ends = 0.0
        self.minted = 0                                  # tokens minted this run (tests, diagnostics)

    def __repr__(self) -> str:
        return f"Credentials({self.domain})"

    def fresh(self) -> bool:
        return self._token is not None and self._clock() < self._ends - REFRESH_MARGIN

    def token(self) -> str:
        if not self.fresh():
            self.mint()
        assert self._token
        return self._token

    def drop(self) -> None:
        self._token, self._ends = None, 0.0

    def mint(self) -> str:
        try:
            r = self._session.post(f"https://{self.domain}/admin/oauth/access_token",
                                   data={"grant_type": "client_credentials", "client_id": self._client_id,
                                         "client_secret": self._secret},
                                   timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as e:
            raise CatalogError(f"{self.domain}: authentication request failed: {type(e).__name__}") from None
        if r.status_code != 200:                         # the body may echo what was sent: never shown
            raise CatalogError(f"{self.domain}: authentication refused (HTTP {r.status_code})")
        try:
            body = r.json()
            token = str(body["access_token"]).strip()
            lifetime = float(body.get("expires_in") or DEFAULT_LIFETIME)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise CatalogError(f"{self.domain}: authentication answer is not a token") from None
        if not token:
            raise CatalogError(f"{self.domain}: authentication answer is not a token")
        if lifetime <= REFRESH_MARGIN:
            raise CatalogError(f"{self.domain}: the token lives only {lifetime:.0f} s")
        self._token, self._ends = token, self._clock() + lifetime
        self.minted += 1
        return token


def _retry_after(r: Any) -> float | None:
    value = (getattr(r, "headers", None) or {}).get("Retry-After")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _cost_wait(body: dict[str, Any]) -> float | None:
    """Seconds until the query's cost is back in the bucket (extensions.cost of a THROTTLED answer)."""
    cost = (body.get("extensions") or {}).get("cost") or {}
    status = cost.get("throttleStatus") or {}
    try:
        missing = float(cost["requestedQueryCost"]) - float(status["currentlyAvailable"])
        return max(0.0, missing) / float(status["restoreRate"]) + 1.0
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


class ShopCatalog:
    """One store's catalog of source keys, read through the Admin GraphQL API (queries only). The writing clients of
    shopify_admin.py subclass it with their own app keys, scope and WRITES = True."""
    NAMES = (CLIENT_ID, CLIENT_SECRET)            # the app's keys in the credentials file
    SCOPE = SCOPE                                 # the scope a new token must have
    PROBE = True                                  # a new token must read products(first: 1)
    WRITES = False                                # a mutation is refused

    def __init__(self, store: Store, session: requests.Session | None = None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 env_file: str = ENV_FILE, wall_clock: Callable[[], float] = time.time,
                 ignored: Callable[[str], bool] = _git_ignored):
        if store.shopify is None:
            raise ShopNotConfigured(f"{store.id.value}: no Shopify values yet (domain, shop id, API version, "
                                    f"credentials variable, namespace); ask the operator")
        self.store, self.shop = store, store.shopify
        check_env_file(env_file)
        path = os.environ.get(self.shop.credentials_env, "").strip()
        if not path:
            raise ShopNotConfigured(f"{store.id.value}: {self.shop.credentials_env} is not set; put the path of the "
                                    f"store app's credentials file ({CLIENT_ID}, {CLIENT_SECRET}) in .env")
        self._session = session or _session()
        self.credentials = Credentials(self.shop.domain, *read_credentials(path, ignored, self.NAMES),
                                       session=self._session, clock=wall_clock)
        self._clock, self._sleep = clock, sleep
        self._keys: dict[str, str] | None = None
        self._read_at = 0.0
        self.key_re = re.compile(KEY_RE.format(ns=re.escape(self.shop.namespace)))
        self.url = f"https://{self.shop.domain}/admin/api/{self.shop.api_version}/graphql.json"

    def __repr__(self) -> str:                 # no token in a traceback or a print
        return f"ShopCatalog({self.store.id.value}, {self.shop.domain})"

    # ---- API ------------------------------------------------------------------------------

    def _token(self) -> str:
        """The current token; a new one is verified (shop, scope, probe) before it is used, and dropped when not."""
        if self.credentials.fresh():
            return self.credentials.token()
        token = self.credentials.mint()
        try:
            self.verify(token)
        except BaseException:
            self.credentials.drop()
            raise
        return token

    def _post(self, query: str, variables: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
        if not self.WRITES and _MUTATION_RE.search(query):
            raise CatalogError("shopify_catalog reads only: a mutation is refused")
        try:
            return self._send(query, variables, token or self._token())
        except _Unauthorized:
            if token:                                    # verifying a new token: no second mint
                raise CatalogError(f"{self.shop.domain}: the new token is refused (HTTP 401)") from None
        self.credentials.drop()                          # a 401 mid-run: the token ended; one new one, one repeat
        try:
            return self._send(query, variables, self._token())
        except _Unauthorized:
            raise CatalogError(f"{self.shop.domain}: HTTP 401 again with a new token") from None

    def _send(self, query: str, variables: dict[str, Any] | None, token: str) -> dict[str, Any]:
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        for attempt in range(1, RETRIES + 1):
            try:
                r = self._session.post(self.url, json={"query": query, "variables": variables or {}},
                                       headers=headers, timeout=TIMEOUT, allow_redirects=False)
            except requests.RequestException as e:
                raise CatalogError(f"{self.shop.domain}: request failed: {type(e).__name__}") from None
            if r.status_code == 401:
                raise _Unauthorized()
            throttled = r.status_code == 429 or r.status_code >= 500
            wait = _retry_after(r) if r.status_code == 429 else None
            body: dict[str, Any] = {}
            if not throttled:
                if r.status_code != 200:
                    raise CatalogError(f"{self.shop.domain}: HTTP {r.status_code}"
                                       + (" (the token is refused)" if r.status_code == 403 else ""))
                try:
                    body = r.json()
                except ValueError:
                    raise CatalogError(f"{self.shop.domain}: the answer is not JSON") from None
                codes = {(e.get("extensions") or {}).get("code") for e in body.get("errors") or []}
                throttled = "THROTTLED" in codes
                wait = _cost_wait(body) if throttled else None
                if body.get("errors") and not throttled:
                    messages = "; ".join(str(e.get("message"))[:120] for e in body["errors"])
                    raise CatalogError(f"{self.shop.domain}: {messages}")
            if not throttled:
                return body.get("data") or {}
            if attempt < RETRIES:
                self._sleep(min(MAX_WAIT, wait if wait is not None else RETRY_WAIT * attempt))
        raise CatalogError(f"{self.shop.domain}: throttled {RETRIES} times")

    def verify(self, token: str) -> None:
        """A new token: the right shop, read_products granted, products readable."""
        data = self._post(VERIFY_QUERY, token=token)
        shop = data.get("shop") or {}
        if (shop.get("id"), shop.get("myshopifyDomain")) != (self.shop.shop_id, self.shop.domain):
            raise CatalogError(f"{self.store.id.value}: the API answered for {shop.get('myshopifyDomain')} "
                               f"({shop.get('id')}), not {self.shop.domain} ({self.shop.shop_id})")
        scopes = {s.get("handle") for s in ((data.get("currentAppInstallation") or {}).get("accessScopes") or [])}
        if self.SCOPE not in scopes:
            raise CatalogError(f"{self.store.id.value}: the app's token lacks {self.SCOPE}")
        if self.PROBE and "products" not in self._post(PROBE_QUERY, token=token):
            raise CatalogError(f"{self.store.id.value}: products(first: 1) gave no products field")

    def check_shop(self) -> None:
        """The shop answers as itself (before every catalog read)."""
        shop = self._post("query { shop { id myshopifyDomain } }").get("shop") or {}
        if (shop.get("id"), shop.get("myshopifyDomain")) != (self.shop.shop_id, self.shop.domain):
            raise CatalogError(f"{self.store.id.value}: the API answered for {shop.get('myshopifyDomain')} "
                               f"({shop.get('id')}), not {self.shop.domain} ({self.shop.shop_id})")

    def read(self) -> dict[str, str]:
        """Every product's source keys -> {key: product gid}. Checks the shop first."""
        self.check_shop()
        fields = " ".join(f'{key}: metafield(namespace: "{self.shop.namespace}", key: "{key}") {{ value }}'
                          for key in KEYS)
        query = PRODUCTS_QUERY % (PAGE, fields)
        keys: dict[str, str] = {}
        cursor = None
        while True:
            page = (self._post(query, {"cursor": cursor}).get("products") or {})
            for node in page.get("nodes") or []:
                for name in KEYS:
                    value = ((node.get(name) or {}).get("value") or "").strip()
                    if not value:
                        continue
                    if not self.key_re.match(value):
                        raise CatalogError(f"{node.get('id')}: {self.shop.namespace}.{name} {value[:80]!r} is not "
                                           f"{self.shop.namespace}:naver:<channelNo>:<productId>")
                    other = keys.get(value)
                    if other and other != node.get("id"):
                        raise CatalogError(f"source key {value} is on two products: {other}, {node.get('id')}")
                    keys[value] = node.get("id")
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                return keys
            cursor = info.get("endCursor")
            if not cursor:
                raise CatalogError(f"{self.shop.domain}: a next page without a cursor")

    def keys(self) -> dict[str, str]:
        """The snapshot, read again when it is older than MAX_AGE."""
        # time.time, not time.monotonic: on macOS monotonic stops while the Mac sleeps, and the age must count it.
        # The age runs from the start of the read (its first page is the oldest data).
        if self._keys is None or self._clock() - self._read_at > MAX_AGE:
            started = self._clock()
            self._keys = self.read()
            self._read_at = started
        return self._keys
