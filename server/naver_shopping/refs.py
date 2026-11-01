"""Reference resolvers for /naver-shopping/* (ONE param per input, the
tofler / tripadvisor convention: a bare id OR the site's own link, never a
sibling `url` / `id` pair). Resolvers raise ValueError with a user-facing
message (schema_fields.RefField turns it into a 400).

Identifier shapes on Naver Shopping (captured 2026-10-24):

  * product      the channel product number in a store link
                 (smartstore.naver.com/<store>/products/<id>,
                 brand.naver.com/<store>/products/<id>, m. hosts too); the
                 search results link products as
                 smartstore.naver.com/main/products/<id> (no store slug).
                 Resolves to the canonical page link.
  * store        the store slug (smartstore.naver.com/<slug>,
                 brand.naver.com/<slug>) - resolves to the store's home link.
  * catalog      the price-comparison id (nvMid), 8-12 digits, as in
                 search.shopping.naver.com/catalog/<id> or any
                 shopping.naver.com link carrying nv_mid=<id>.
  * category     a DataLab / shopping category id: 8 digits starting with 5
                 (50000003 = 디지털/가전), "0" = the root.
"""
import re
from urllib.parse import parse_qs, urlparse

SMARTSTORE = "https://smartstore.naver.com"
BRAND = "https://brand.naver.com"
SEARCH_PORTAL = "https://ns-portal.shopping.naver.com"
SHOPPING_SEARCH = "https://search.shopping.naver.com"
DATALAB = "https://datalab.naver.com"
MAIN_SLUG = "main"          # the slug-less product link the search results use

_DIGITS_RE = re.compile(r"^[0-9]{6,14}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{2,60}$")
_CATEGORY_RE = re.compile(r"^(0|5[0-9]{7})$")
_PRODUCT_PATH_RE = re.compile(r"^/([A-Za-z0-9_.-]+)/products/([0-9]{6,14})(?:/|$)")
_STORE_PATH_RE = re.compile(r"^/([A-Za-z0-9_.-]+)(?:/|$)")
_CATALOG_PATH_RE = re.compile(r"/catalog/([0-9]{6,14})(?:/|$)")

_STORE_HOSTS = {
    "smartstore.naver.com": SMARTSTORE, "m.smartstore.naver.com": SMARTSTORE,
    "brand.naver.com": BRAND, "m.brand.naver.com": BRAND,
}
# store paths that are pages, not slugs
_RESERVED_SLUGS = {"inflow", "i", "n", "main", "products", "search", "category", "best", "lounge", "notice", "live"}


def _url(value):
    """A pasted link (with or without a scheme) -> urlparse result, or None."""
    value = (value or "").strip()
    if value.startswith("//"):
        value = "https:" + value
    elif not value.startswith(("http://", "https://")):
        if re.match(r"^(m\.)?(smartstore|brand)\.naver\.com/", value) or re.match(r"^[a-z]*search\.shopping\.naver\.com/", value):
            value = "https://" + value
        else:
            return None
    parsed = urlparse(value)
    return parsed if parsed.hostname else None


# ---- products -------------------------------------------------------------------

def product_link(product_id, slug=None, brand=False):
    base = BRAND if brand else SMARTSTORE
    return f"{base}/{slug or MAIN_SLUG}/products/{product_id}"


def resolve_product(value):
    """A channel product number or a store product link -> the canonical
    product page link (https://smartstore.naver.com/<store>/products/<id>,
    https://brand.naver.com/<store>/products/<id>, or the slug-less
    https://smartstore.naver.com/main/products/<id> for a bare number)."""
    raw = (value or "").strip()
    if _DIGITS_RE.match(raw):
        return product_link(raw)
    parsed = _url(raw)
    if parsed is None:
        raise ValueError("Must be a channel product number (e.g. 10352481064) or a smartstore.naver.com / "
                         "brand.naver.com product link (https://smartstore.naver.com/<store>/products/<id>).")
    base = _STORE_HOSTS.get(parsed.hostname.lower())
    if base is None:
        raise ValueError("Must be a smartstore.naver.com or brand.naver.com product link.")
    match = _PRODUCT_PATH_RE.match(parsed.path)
    if not match:
        raise ValueError("Must be a store product link (https://smartstore.naver.com/<store>/products/<id>).")
    slug, product_id = match.group(1), match.group(2)
    return product_link(product_id, slug, brand=(base == BRAND))


def split_product_link(link):
    """The canonical link -> {"id": str, "slug": str|None, "is_brand": bool}."""
    parsed = urlparse(link)
    match = re.match(r"^/([^/]+)/products/([0-9]+)", parsed.path)
    slug = match.group(1)
    return {"id": match.group(2), "slug": None if slug == MAIN_SLUG else slug,
            "is_brand": parsed.hostname == "brand.naver.com"}


# ---- stores ---------------------------------------------------------------------

def store_link(slug, brand=False):
    return f"{BRAND if brand else SMARTSTORE}/{slug}"


def resolve_store(value):
    """A store slug or a smartstore.naver.com / brand.naver.com store link ->
    the store's home link (https://smartstore.naver.com/<slug> or
    https://brand.naver.com/<slug>)."""
    raw = (value or "").strip()
    parsed = _url(raw)
    if parsed is None:
        if _SLUG_RE.match(raw) and raw.lower() not in _RESERVED_SLUGS and not _DIGITS_RE.match(raw):
            return store_link(raw)
        raise ValueError("Must be a store slug (e.g. bauato) or a smartstore.naver.com / brand.naver.com "
                         "store link (https://smartstore.naver.com/<store>).")
    base = _STORE_HOSTS.get(parsed.hostname.lower())
    if base is None:
        raise ValueError("Must be a smartstore.naver.com or brand.naver.com store link.")
    match = _STORE_PATH_RE.match(parsed.path)
    if not match or match.group(1).lower() in _RESERVED_SLUGS:
        raise ValueError("Must be a store link (https://smartstore.naver.com/<store>); the slug-less "
                         "/main/products/<id> product links carry no store.")
    return store_link(match.group(1), brand=(base == BRAND))


def split_store_link(link):
    parsed = urlparse(link)
    return {"slug": parsed.path.strip("/").split("/")[0], "is_brand": parsed.hostname == "brand.naver.com"}


# ---- catalogs -------------------------------------------------------------------

def catalog_link(catalog_id):
    return f"{SHOPPING_SEARCH}/catalog/{catalog_id}"


def resolve_catalog(value):
    """A price-comparison catalog id (nvMid) or a shopping.naver.com catalog
    link / bridge link (nv_mid=...) -> the id."""
    raw = (value or "").strip()
    if _DIGITS_RE.match(raw):
        return raw
    parsed = _url(raw)
    if parsed is None or not parsed.hostname.lower().endswith("shopping.naver.com"):
        raise ValueError("Must be a catalog id (e.g. 61626354397) or a search.shopping.naver.com/catalog/<id> link.")
    match = _CATALOG_PATH_RE.search(parsed.path)
    if match:
        return match.group(1)
    nv_mid = parse_qs(parsed.query).get("nv_mid") or parse_qs(parsed.query).get("nvMid")
    if nv_mid and _DIGITS_RE.match(nv_mid[0]):
        return nv_mid[0]
    raise ValueError("Must be a search.shopping.naver.com/catalog/<id> link or a shopping.naver.com link with nv_mid=<id>.")


# ---- categories -----------------------------------------------------------------

def resolve_category(value):
    """A Naver shopping category id (8 digits, 50000003) or 0 for the root."""
    raw = (value or "").strip()
    if _CATEGORY_RE.match(raw):
        return raw
    raise ValueError("Must be a Naver shopping category id (8 digits, e.g. 50000003 for 디지털/가전; "
                     "0 lists the top-level categories).")
