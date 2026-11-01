"""Parsers for the search.shopping.naver.com listing (BETA, extension transport).

Two sources, one shape ({hasMore, cursor, total, data: [{card: {product}}]}),
seen 2026-11-01 for 남성 골프채 풀세트 (total 4385, 50 cards per batch):
  * the first batch rides inside the ns/search HTML: a Next.js App Router
    page whose data is self.__next_f.push([1, "<escaped RSC text>"]) chunks;
    the batch is the object after "initPagedCompositeCards":
  * every next batch is the page's own GET /ns/v1/search/paged-composite-cards
    answer, under "data" (captured by extension/capture_main.js).

Pure functions, no I/O; see server/docs/EXTENSION.md for why the listing is
read this way.
"""
import json
import re
from urllib.parse import parse_qs, urlparse

_RSC_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_INIT_KEY = '"initPagedCompositeCards":'
_NOT_STORES = ("main", "inflow", "products")          # path heads that are not a store slug
_STORE_HOSTS = ("smartstore.naver.com", "m.smartstore.naver.com", "brand.naver.com", "m.brand.naver.com")


def first_batch(html):
    """ns/search HTML -> the embedded first batch dict, or None."""
    try:
        rsc = "".join(json.loads('"' + c + '"') for c in _RSC_CHUNK.findall(html or ""))
    except ValueError:
        return None
    i = rsc.find(_INIT_KEY)
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(rsc, i + len(_INIT_KEY))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def batch_from_answer(body):
    """paged-composite-cards answer text -> its batch dict, or None (not JSON)."""
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    batch = data.get("data") if isinstance(data, dict) else None
    return batch if isinstance(batch, dict) else None


def products(batch):
    """Batch -> the product dicts (other card kinds are skipped)."""
    out = []
    for item in (batch or {}).get("data") or []:
        product = ((item or {}).get("card") or {}).get("product")
        if isinstance(product, dict):
            out.append(product)
    return out


def store_link(product):
    """The store home from mallUrl (its inflow/outlink ?url=..., or a direct store
    link), pc first -> https://{smartstore|brand}.naver.com/<slug>, or None."""
    for url in ((product.get("mallUrl") or {}).get("pcUrl"), (product.get("mallUrl") or {}).get("mobileUrl")):
        inner = (parse_qs(urlparse(url or "").query).get("url") or [""])[0] or url or ""
        parsed = urlparse(inner)
        slug = parsed.path.strip("/").split("/")[0] if parsed.path else ""
        if parsed.hostname in _STORE_HOSTS and slug and slug not in _NOT_STORES:
            host = parsed.hostname.removeprefix("m.")
            return f"https://{host}/{slug}"
    return None


def listing_row(product):
    """One product card -> the listing row, or None when it is not a Naver store product."""
    product_id = str(product.get("channelProductId") or "")
    store = store_link(product)
    if not product_id.isdigit() or not store:
        return None
    images = product.get("images") or []
    return {
        "product_id": product_id,
        "nv_mid": str(product.get("nvMid") or "") or None,
        "link": f"{store}/products/{product_id}",
        "name": product.get("productName"),
        "store": {"name": product.get("mallName"), "slug": store.rsplit("/", 1)[1], "link": store,
                  "grade": product.get("mallGradeType"), "is_brand_store": bool(product.get("isBrandStore"))},
        "pricing": {"sale_price": product.get("salePrice"), "discounted_price": product.get("discountedSalePrice"),
                    "discount_ratio": product.get("discountedRatio"), "currency": "KRW"},
        "category_id": product.get("ssCatId") or product.get("sCatId"),
        "reviews": {"count": product.get("totalReviewCount"), "average_score": product.get("averageReviewScore")},
        "stock_quantity": product.get("stockQuantity"),
        "image": (images[0] or {}).get("imageUrl") if images else None,
        "is_ad": product.get("cardType") == "AD",
    }
