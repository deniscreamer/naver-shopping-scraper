"""The "already in the shop" check: which Naver offers a Shopify store already has, read from its Admin API.

Read only. Every product of the store is read page by page, in any status (active, draft and archived alike:
a draft or an archived product is still "already there"), with the source key metafields the naver-harvester
writes: `<namespace>.source_offer_id`, and the older `<namespace>.naver_offer_key`; either one counts. A key is
`<namespace>:naver:<channelNo>:<productId>` (listing_filter.source_key). This check matches by the source key only,
never by name; one product sold by another store (another key) is dedupe.py's, after collect (job.py --dedupe).

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
    for node in catalog.paged(query, "products"): ...    # any connection, page by page (query takes $cursor)

The CLI (2026-11-16, the owner's five tools): read the store's products by hand. Read only (WRITES = False, the same
token and checks as above), check_shop() before anything; it writes no file of ours (dump writes only --out).

    .venv/bin/python scripts/shopify_catalog.py <shop> show <ref> [--variants] [--metafields [NS[.KEY]]] [--media] [--json]
    .venv/bin/python scripts/shopify_catalog.py <shop> dump [--fields F,F ...] [--query 'status:active'] [--limit N] --out F.jsonl
    .venv/bin/python scripts/shopify_catalog.py <shop> counts [--json]
    .venv/bin/python scripts/shopify_catalog.py <shop> vendors [--query Q] [--json]
    .venv/bin/python scripts/shopify_catalog.py <shop> collection <handle> [--count-by vendor,status,type] [--json]

show: <ref> is anything shop_view.resolve takes (a key, a Naver product id, a handle the ledger ever had, a store /
admin / Naver link) or a gid; the ledger's product_id for that key is read. A handle or number our files never had
is asked of the store itself (productByIdentifier / the gid). Several of our products match: exit 1 naming them.
Prints `field<TAB>value` lines (`price` the variants' min-max and currency, `url` the storefront link: the API's,
else the store's site + /products/<handle> for an ACTIVE product; 2026-11-16), then
`variant<TAB>sku<TAB>price<TAB>compare at<TAB>qty<TAB>Name=value; ...`, `metafield<TAB>ns.key<TAB>type<TAB>value`,
`media<TAB>n<TAB>type<TAB>status<TAB>url<TAB>alt` (shop_view.cell: a list comma-joined, every run of whitespace in a
value one space; --json for the exact values). dump: one JSON line a product, FIELDS' names (default id handle
status vendor title key), written to F.jsonl.<pid>.part and moved over F at the end (a failed dump leaves F as it
was). counts: `status<TAB>n` (active, draft, archived, all; n+ when Shopify only says "at least"). vendors:
`vendor<TAB>n`, the most first. collection: `handle<TAB>status<TAB>vendor<TAB>key<TAB>title` a product, or with
--count-by `v1[<TAB>v2]<TAB>n`.
Exit codes: 0 done; 1 not found (a ref none or several of ours match, a key never sent, a product or collection the
store does not have, a broken shop file); 2 usage (argparse: an unknown shop, field or --count-by); 3 the store is
not configured (ShopNotConfigured: ask the operator); 4 the catalog cannot be trusted (CatalogError: auth, another
shop, an API error, throttled).
"""
import http.cookiejar
import json
import os
import re
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterator

import requests

from naver_api_client import ENV_FILE
from shop_files import LedgerError, read_jsonl
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

    def paged(self, query: str, path: str, variables: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Every node of one connection, page by page, as the pages come (stop iterating: no more pages are read).
        `query` takes `$cursor: String` and asks the connection at `path` (dotted: "products",
        "collection.products") with `pageInfo { hasNextPage endCursor }` and `nodes`. Queries only (a mutation is
        refused); the caller checks the shop first (check_shop). A missing connection or a next page without a
        cursor is a CatalogError."""
        cursor = None
        while True:
            page: Any = self._post(query, {**(variables or {}), "cursor": cursor})
            for name in path.split("."):
                page = page.get(name) if isinstance(page, dict) else None
            if not isinstance(page, dict):
                raise CatalogError(f"{self.shop.domain}: the answer has no {path}")
            yield from page.get("nodes") or []
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                return
            cursor = info.get("endCursor")
            if not cursor:
                raise CatalogError(f"{self.shop.domain}: a next page without a cursor")

    def read(self) -> dict[str, str]:
        """Every product's source keys -> {key: product gid}. Checks the shop first."""
        self.check_shop()
        fields = " ".join(f'{key}: metafield(namespace: "{self.shop.namespace}", key: "{key}") {{ value }}'
                          for key in KEYS)
        keys: dict[str, str] = {}
        for node in self.paged(PRODUCTS_QUERY % (PAGE, fields), "products"):
            for name in KEYS:
                value = ((node.get(name) or {}).get("value") or "").strip()
                if not value:
                    continue
                if not self.key_re.match(value):
                    raise CatalogError(f"{node.get('id')}: {self.shop.namespace}.{name} {value[:80]!r} is not "
                                       f"{self.shop.namespace}:naver:<channelNo>:<productId>")
                gid: Any = node.get("id")
                other = keys.get(value)
                if other and other != gid:
                    raise CatalogError(f"source key {value} is on two products: {other}, {gid}")
                keys[value] = gid
        return keys

    def keys(self) -> dict[str, str]:
        """The snapshot, read again when it is older than MAX_AGE."""
        # time.time, not time.monotonic: on macOS monotonic stops while the Mac sleeps, and the age must count it.
        # The age runs from the start of the read (its first page is the oldest data).
        if self._keys is None or self._clock() - self._read_at > MAX_AGE:
            started = self._clock()
            self._keys = self.read()
            self._read_at = started
        return self._keys


# ---- CLI: read the store's products by hand (2026-11-16, the owner's five tools) ------------------------------------

GID = "gid://shopify/Product/"
LIGHT_PAGE = 250                 # products a page for scalar fields only (cost ~ 1 a product)
SHOW = """query Show($id: ID!) { node(id: $id) { ... on Product {
  id handle title status vendor productType tags createdAt updatedAt publishedAt totalInventory onlineStoreUrl
  priceRangeV2 { minVariantPrice { amount currencyCode } maxVariantPrice { amount } }
  source_offer_id: metafield(namespace: "%(ns)s", key: "source_offer_id") { value }
  naver_offer_key: metafield(namespace: "%(ns)s", key: "naver_offer_key") { value }
  collections(first: 20) { nodes { handle } } variantsCount { count } mediaCount { count }
  %(more)s
} } }"""
VARIANTS = ("variants(first: 100) { nodes { id sku title price compareAtPrice inventoryQuantity "
            "selectedOptions { name value } } }")
METAFIELDS = "metafields(first: 100) { nodes { namespace key type value } }"
MEDIA = ("media(first: 100) { nodes { mediaContentType status alt "
         "... on MediaImage { image { url width height } } } }")
BY_HANDLE = "query ByHandle($handle: String!) { productByIdentifier(identifier: {handle: $handle}) { id } }"
COUNTS = "query Counts { %s }" % " ".join(
    f'{s}: productsCount({"" if s == "all" else f"query: {chr(34)}status:{s}{chr(34)}, "}limit: null) '
    "{ count precision }" for s in ("active", "draft", "archived", "all"))
COLLECTION = ("query Collection($handle: String!) { collectionByIdentifier(identifier: {handle: $handle}) "
              "{ id handle title productsCount { count } } }")
LIST = """query List($cursor: String%(args)s) {
  %(open)sproducts(first: %(first)d, after: $cursor%(query)s) {
    pageInfo { hasNextPage endCursor }
    nodes { %(fields)s }
  }%(close)s
}"""
def _getter(name: str) -> Callable[[dict[str, Any]], Any]:
    return lambda node: node.get(name)


# dump's fields: name -> (GraphQL, the value from a node); `key` is the source key (the current metafield, else
# the older one)
FIELDS: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {
    **{f: (f, _getter(f)) for f in ("id", "handle", "title", "status", "vendor", "productType",
                                                    "tags", "createdAt", "updatedAt", "publishedAt", "totalInventory")},
    "key": ('source_offer_id: metafield(namespace: "%(ns)s", key: "source_offer_id") { value } '
            'naver_offer_key: metafield(namespace: "%(ns)s", key: "naver_offer_key") { value }',
            lambda n: _source_key(n)),
    "variants": ("variantsCount { count }", lambda n: (n.get("variantsCount") or {}).get("count")),
    "media": ("mediaCount { count }", lambda n: (n.get("mediaCount") or {}).get("count")),
    "price_min": ("priceRangeV2 { minVariantPrice { amount } maxVariantPrice { amount } }",
                  lambda n: ((n.get("priceRangeV2") or {}).get("minVariantPrice") or {}).get("amount")),
    "price_max": ("priceRangeV2 { minVariantPrice { amount } maxVariantPrice { amount } }",
                  lambda n: ((n.get("priceRangeV2") or {}).get("maxVariantPrice") or {}).get("amount")),
    "collections": ("collections(first: 10) { nodes { handle } }",
                    lambda n: [c.get("handle") for c in (n.get("collections") or {}).get("nodes") or []]),
}
DUMP_DEFAULT = ("id", "handle", "status", "vendor", "title", "key")
COUNT_BY = {"vendor": "vendor", "status": "status", "type": "productType"}
EXIT_FOUND, EXIT_NONE, EXIT_USAGE, EXIT_NOT_CONFIGURED, EXIT_CATALOG = 0, 1, 2, 3, 4


class NotFound(Exception):
    """A ref, product or collection the command cannot name or the store does not have (exit 1)."""


def _source_key(node: dict[str, Any]) -> str | None:
    for name in KEYS:
        value = ((node.get(name) or {}).get("value") or "").strip()
        if value:
            return value
    return None


def _row(*cells: Any) -> str:
    from shop_view import cell                      # one TSV cell for the read tools: whitespace runs one space
    return "\t".join(cell(c) for c in cells)


def _list_query(catalog: ShopCatalog, fields: str, first: int, query: str | None = None,
                collection: bool = False) -> tuple[str, str]:
    """A products listing (of the store, or of one collection: variable $id) and the path of its connection."""
    text = LIST % {"args": (", $query: String" if query else "") + (", $id: ID!" if collection else ""),
                   "open": "collection(id: $id) { " if collection else "", "close": " }" if collection else "",
                   "first": first, "query": ", query: $query" if query else "",
                   "fields": fields % {"ns": catalog.shop.namespace}}
    return text, "collection.products" if collection else "products"


def product_id(catalog: ShopCatalog, ref: str, shops_root: str) -> str:
    """The product gid `ref` names: a gid, an admin link, or any ref of shop_view.resolve whose key the ledger sent;
    a handle or number our files never had is looked up in the store itself. NotFound when none or several."""
    from shop_view import RefError, RefIndex, is_key, resolve, store_number
    ref = ref.strip()
    if not ref:
        raise NotFound("an empty ref")
    number = store_number(ref)                              # a gid or an admin link: the store's own number
    if number:
        return GID + number
    shop = catalog.store.id.value
    index = RefIndex.of_shop(shop, shops_root)
    found: set[str] = set()
    try:
        found = index.matches(ref) if not is_key(ref) and ref not in index.known else {ref}
        key = resolve(index, ref)
    except RefError as e:
        if found:                                           # several of ours: name one, never the first
            raise NotFound(str(e)) from None
        if ref.isdigit():                                   # a Shopify product number our ledger never had
            return GID + ref
        handle = re.search(r"/products/([^/?#]+)", ref)
        if "://" in ref and not handle:
            raise NotFound(str(e)) from None
        answer = catalog._post(BY_HANDLE, {"handle": handle.group(1) if handle else ref})
        gid = (answer.get("productByIdentifier") or {}).get("id")
        if not gid:
            raise NotFound(f"{ref}: neither our files nor the store have it (a key, a Naver product id, a handle, "
                           f"a link, a gid)") from None
        return str(gid)
    sent = [r for r in read_jsonl(os.path.join(shops_root, shop, "publish", "published.jsonl"), tail_ok=True)
            if r.get("key") == key and r.get("product_id")]
    if not sent:
        raise NotFound(f"{ref}: {key} was never sent to the store (no product_id in the ledger)")
    return str(sent[-1]["product_id"])


def _price_range(node: dict[str, Any]) -> str:
    """`min-max CUR` (one price: `p CUR`) from priceRangeV2; "" when the answer has none."""
    r = node.get("priceRangeV2") or {}
    lo, hi = (r.get("minVariantPrice") or {}), (r.get("maxVariantPrice") or {})
    if lo.get("amount") is None:
        return ""
    span = lo["amount"] if hi.get("amount") in (None, lo["amount"]) else f"{lo['amount']}-{hi['amount']}"
    return f"{span} {lo.get('currencyCode') or ''}".strip()


def _store_url(catalog: ShopCatalog, node: dict[str, Any]) -> str:
    """The storefront link: onlineStoreUrl, else (null when the app cannot read the Online Store's publication) the
    store's site + /products/<handle> for an ACTIVE product; "" for a draft or an archived one (not on the store)."""
    if node.get("onlineStoreUrl"):
        return str(node["onlineStoreUrl"])
    if node.get("status") == "ACTIVE" and node.get("handle"):
        return f"{catalog.store.site.rstrip('/')}/products/{node['handle']}"
    return ""


def _show(catalog: ShopCatalog, a: Any) -> int:
    gid = product_id(catalog, a.ref, a.shops_root)
    more = [x for flag, x in ((a.variants, VARIANTS), (a.metafields is not None, METAFIELDS), (a.media, MEDIA))
            if flag]
    node = catalog._post(SHOW % {"ns": catalog.shop.namespace, "more": " ".join(more)}, {"id": gid}).get("node")
    if not node:
        raise NotFound(f"{a.ref}: {gid} is not in the store")
    if a.metafields:                                         # "ns" or "ns.key"
        ns, _, key = a.metafields.partition(".")
        node["metafields"]["nodes"] = [m for m in node["metafields"]["nodes"]
                                       if m.get("namespace") == ns and (not key or m.get("key") == key)]
    if a.json:
        print(json.dumps(node, ensure_ascii=False, indent=1))
        return EXIT_FOUND
    for name, value in (("id", node.get("id")), ("handle", node.get("handle")), ("title", node.get("title")),
                        ("status", node.get("status")), ("vendor", node.get("vendor")),
                        ("type", node.get("productType")), ("tags", node.get("tags")), ("key", _source_key(node)),
                        ("collections", [c["handle"] for c in (node.get("collections") or {}).get("nodes") or []]),
                        ("variant_count", (node.get("variantsCount") or {}).get("count")),
                        ("media_count", (node.get("mediaCount") or {}).get("count")),
                        ("inventory", node.get("totalInventory")), ("created", node.get("createdAt")),
                        ("updated", node.get("updatedAt")), ("published", node.get("publishedAt")),
                        ("price", _price_range(node)), ("url", _store_url(catalog, node))):
        print(_row(name, value))
    for v in (node.get("variants") or {}).get("nodes") or []:
        print(_row("variant", v.get("sku"), v.get("price"), v.get("compareAtPrice"), v.get("inventoryQuantity"),
                   "; ".join(f"{o['name']}={o['value']}" for o in v.get("selectedOptions") or [])))
    for m in (node.get("metafields") or {}).get("nodes") or []:
        print(_row("metafield", f"{m.get('namespace')}.{m.get('key')}", m.get("type"), m.get("value")))
    for n, m in enumerate((node.get("media") or {}).get("nodes") or [], 1):
        print(_row("media", n, m.get("mediaContentType"), m.get("status"), (m.get("image") or {}).get("url"),
                   m.get("alt")))
    return EXIT_FOUND


def _fields(names: list[str]) -> list[str]:
    out = [f.strip() for x in names for f in x.split(",") if f.strip()]
    bad = [f for f in out if f not in FIELDS]
    if bad:
        raise SystemExit(f"shopify_catalog: unknown field(s) {', '.join(bad)}; known: {', '.join(FIELDS)}")
    return list(dict.fromkeys(out))


def _dump(catalog: ShopCatalog, a: Any) -> int:
    names = _fields(a.fields) if a.fields else list(DUMP_DEFAULT)
    heavy = "collections" in names
    first = min(a.limit, 50 if heavy else PAGE) if a.limit else (50 if heavy else PAGE)
    text, path = _list_query(catalog, " ".join(dict.fromkeys(FIELDS[n][0] for n in names)), first, a.query)
    part, n = f"{a.out}.{os.getpid()}.part", 0
    try:
        with open(part, "w", encoding="utf-8") as f:
            for node in catalog.paged(text, path, {"query": a.query} if a.query else None):
                f.write(json.dumps({x: FIELDS[x][1](node) for x in names}, ensure_ascii=False) + "\n")
                n += 1
                if a.limit and n >= a.limit:
                    break
        os.replace(part, a.out)                              # the whole dump or the old file: never half of one
    finally:
        if os.path.exists(part):
            os.remove(part)
    print(f"dump {catalog.store.id.value}: {n} products -> {a.out}", file=sys.stderr)
    return EXIT_FOUND


def _counts(catalog: ShopCatalog, a: Any) -> int:
    answer = catalog._post(COUNTS)
    counts = {s: (answer.get(s) or {}).get("count") for s in ("active", "draft", "archived", "all")}
    if a.json:
        print(json.dumps(counts))
    for s, c in counts.items():
        if not a.json:
            print(_row(s, f"{c}{'' if (answer.get(s) or {}).get('precision') in (None, 'EXACT') else '+'}"))
    return EXIT_FOUND


def _count(nodes: Iterator[dict[str, Any]], by: list[str]) -> list[tuple[tuple[str, ...], int]]:
    counts: dict[tuple[str, ...], int] = {}
    for node in nodes:
        k = tuple(str(node.get(COUNT_BY[b]) or "") for b in by)
        counts[k] = counts.get(k, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _print_counts(rows: list[tuple[tuple[str, ...], int]], by: list[str], as_json: bool) -> None:
    if as_json:
        print(json.dumps([{**dict(zip(by, k)), "count": c} for k, c in rows], ensure_ascii=False))
        return
    for k, c in rows:
        print(_row(*k, c))


def _count_by(value: str) -> list[str]:
    by = [b.strip() for b in value.split(",") if b.strip()]
    bad = [b for b in by if b not in COUNT_BY]
    if bad or not by:
        raise SystemExit(f"shopify_catalog: --count-by takes {', '.join(COUNT_BY)} (comma separated)")
    return by


def _vendors(catalog: ShopCatalog, a: Any) -> int:
    text, path = _list_query(catalog, "vendor", LIGHT_PAGE, a.query)
    _print_counts(_count(catalog.paged(text, path, {"query": a.query} if a.query else None), ["vendor"]),
                  ["vendor"], a.json)
    return EXIT_FOUND


def _collection(catalog: ShopCatalog, a: Any) -> int:
    found = catalog._post(COLLECTION, {"handle": a.handle}).get("collectionByIdentifier")
    if not found:
        raise NotFound(f"{a.handle}: no collection with this handle in the store")
    by = _count_by(a.count_by) if a.count_by else None
    fields = "id handle status vendor productType title " + FIELDS["key"][0]
    text, path = _list_query(catalog, fields, LIGHT_PAGE if by else PAGE, collection=True)
    nodes = catalog.paged(text, path, {"id": found["id"]})
    if by:
        _print_counts(_count(nodes, by), by, a.json)
    elif a.json:
        print(json.dumps([{"id": n.get("id"), "handle": n.get("handle"), "status": n.get("status"),
                           "vendor": n.get("vendor"), "key": _source_key(n), "title": n.get("title")}
                          for n in nodes], ensure_ascii=False))
    else:
        for n in nodes:
            print(_row(n.get("handle"), n.get("status"), n.get("vendor"), _source_key(n), n.get("title")))
    print(f"collection {found.get('handle')} ({found.get('title')}): "
          f"{(found.get('productsCount') or {}).get('count')} products", file=sys.stderr)
    return EXIT_FOUND


def main(argv: list[str] | None = None, catalog: ShopCatalog | None = None) -> int:
    """The CLI (usage and exit codes: the module docstring). `catalog`: the tests' ShopCatalog on a fake session."""
    import argparse
    from shop_stores import get_store
    from shop_view import SHOPS_ROOT
    ap = argparse.ArgumentParser(prog="shopify_catalog.py", description="Read a store's products (read only).")
    ap.add_argument("shop")
    ap.add_argument("--shops-root", default=SHOPS_ROOT, help="where our files are (show's refs)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show", help="one product: a key, Naver product id, handle, store / admin link or gid")
    p.add_argument("ref")
    p.add_argument("--variants", action="store_true")
    p.add_argument("--metafields", nargs="?", const="", metavar="NS[.KEY]", help="all, or one namespace / key")
    p.add_argument("--media", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("dump", help="every product (or --query's) a JSON line")
    p.add_argument("--fields", nargs="+", metavar="F", help=f"comma or space separated; known: {', '.join(FIELDS)} "
                   f"(default {','.join(DUMP_DEFAULT)})")
    p.add_argument("--query", help="Shopify's search syntax, e.g. 'status:active' or 'vendor:Titleist'")
    p.add_argument("--limit", type=int, help="the first N products only")
    p.add_argument("--out", required=True, metavar="F.jsonl")
    p = sub.add_parser("counts", help="products by status (active, draft, archived, all)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("vendors", help="products a vendor, the most first")
    p.add_argument("--query")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("collection", help="one collection's products, or their counts")
    p.add_argument("handle")
    p.add_argument("--count-by", metavar="F[,F]", help=f"count by {', '.join(COUNT_BY)}")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if getattr(a, "limit", None) is not None and a.limit < 1:
        ap.error("--limit must be 1 or more")
    try:
        if a.cmd == "dump" and a.fields:
            _fields(a.fields)                                 # a usage error before any request
        if a.cmd == "collection" and a.count_by:
            _count_by(a.count_by)
    except SystemExit as e:
        ap.error(str(e).removeprefix("shopify_catalog: "))
    run = {"show": _show, "dump": _dump, "counts": _counts, "vendors": _vendors, "collection": _collection}[a.cmd]
    try:
        store = get_store(a.shop)
    except ValueError as e:
        ap.error(str(e))
    if catalog is not None and catalog.store.id != store.id:
        ap.error(f"the catalog is {catalog.store.id.value}, not {a.shop}")
    try:
        catalog = catalog or ShopCatalog(store)
        catalog.check_shop()
        return run(catalog, a)
    except ShopNotConfigured as e:
        print(f"shopify_catalog: {e}", file=sys.stderr)
        return EXIT_NOT_CONFIGURED
    except CatalogError as e:
        print(f"shopify_catalog: {e}", file=sys.stderr)
        return EXIT_CATALOG
    except (NotFound, ValueError, LedgerError) as e:         # ValueError: a RefError; LedgerError: a broken line
        print(f"shopify_catalog: {e}", file=sys.stderr)
        return EXIT_NONE


if __name__ == "__main__":
    sys.exit(main())
