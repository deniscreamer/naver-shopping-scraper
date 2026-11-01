"""Template harvester: search a keyword, then fetch details for the store
products it finds, writing raw API answers as JSONL. It holds no Shopify (or
other export) logic; copy it for a new job.

What it encodes is the link handling the search results need:
- A store-product card's `link` is the slug-less
  https://smartstore.naver.com/main/products/<id>. Passing that to
  /products/details forces the server down an expensive validation ->
  name-search -> store path that can 404. So details are fetched with
  `<card.store.link>/products/<card.product_id>` instead.
- A catalog card (type == "catalog", link search.shopping.naver.com/catalog/<id>)
  is a price-comparison page, not a store product: reviewed through
  /catalogs/reviews?catalog=<catalog_id> with --catalogs, otherwise skipped.
- A card whose link or store link is not on smartstore.naver.com /
  brand.naver.com (e.g. link.coupang.com) is an external mall: skipped and logged.
- A store link whose slug is reserved (e.g. .../main, parsers can produce it
  from an unwrapped mallUrl) or a product id outside 6-14 digits would get a
  400 from refs: skipped and logged. A 400 that still comes back is logged and
  counted as failed, not retried.

Output: scripts/output/<run>/products.jsonl, one line per fetched record:
{fetched_at, endpoint, params, data}. A rerun with the same --out skips ids
already written, so an interrupted run can be resumed.

    .venv/bin/python scripts/example_search_harvest.py "raspberry pi" --limit 10
    .venv/bin/python scripts/example_search_harvest.py 목걸이 --out necklaces --catalogs
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from naver_api_client import ApiError, NaverApiClient

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
STORE_HOSTS = {"smartstore.naver.com", "m.smartstore.naver.com", "brand.naver.com", "m.brand.naver.com"}
_PRODUCT_ID_RE = re.compile(r"^[0-9]{6,14}$")          # refs._PRODUCT_PATH_RE
# refs._RESERVED_SLUGS: path segments that are not a store
RESERVED_SLUGS = {"inflow", "i", "n", "main", "products", "search", "category", "best", "lounge", "notice", "live"}


# ---- classification (pure, tested offline) --------------------------------------------

def _host(url):
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def classify_card(card):
    """One /products/search result -> (kind, target, reason).

    kind is "product" (target: the store product link for /products/details),
    "catalog" (target: the catalog id for /catalogs/reviews) or "skip"
    (target None, reason says why)."""
    card = card or {}
    if card.get("type") == "catalog":
        catalog_id = card.get("catalog_id")
        if catalog_id:
            return "catalog", str(catalog_id), None
        return "skip", None, "catalog card without catalog_id"
    link_host = _host(card.get("link"))
    if link_host not in STORE_HOSTS:
        return "skip", None, f"external link host {link_host or '-'}"
    store_link = ((card.get("store") or {}).get("link") or "").rstrip("/")
    if _host(store_link) not in STORE_HOSTS:
        return "skip", None, f"store link not a Naver store: {store_link or '-'}"
    slug = (urlparse(store_link).path.strip("/").split("/") or [""])[0]
    if not slug or slug.lower() in RESERVED_SLUGS:
        return "skip", None, f"store link has no store slug: {store_link}"
    product_id = str(card.get("product_id") or "")
    if not _PRODUCT_ID_RE.match(product_id):
        return "skip", None, f"no channel product id: {product_id or '-'}"
    return "product", f"{store_link}/products/{product_id}", None


# ---- output ----------------------------------------------------------------------------

def _record_key(endpoint, params):
    return endpoint + "|" + json.dumps(params, sort_keys=True, ensure_ascii=False)


def load_done(path):
    """Keys of the records already in a products.jsonl (for resuming)."""
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue                 # a line cut off by an interrupted run
            done.add(_record_key(row.get("endpoint"), row.get("params")))
    return done


def append_record(path, endpoint, params, data):
    row = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "endpoint": endpoint, "params": params, "data": data}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---- run -------------------------------------------------------------------------------

def harvest(api, query, limit, out_dir, catalogs=False, delay=0):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "products.jsonl")
    done = load_done(path)
    search = api.get("/products/search", query=query)
    cards = search.get("results") or []
    print(f"harvest: {query!r} -> {len(cards)} cards, writing {path}")
    fetched = skipped = failed = 0
    for card in cards:
        if limit and fetched >= limit:
            break
        kind, target, reason = classify_card(card)
        if kind == "skip" or (kind == "catalog" and not catalogs):
            skipped += 1
            print(f"harvest: skip {card.get('id')}: {reason or 'catalog (use --catalogs)'}")
            continue
        endpoint, params = ("/products/details", {"product": target}) if kind == "product" \
            else ("/catalogs/reviews", {"catalog": target})
        key = _record_key(endpoint, params)
        if key in done:
            continue
        try:
            data = api.get(endpoint, **params)
        except ApiError as e:
            failed += 1                  # a 400 means classify_card let a bad input through: report it
            print(f"harvest: {endpoint} {target} -> {e.status}: {(e.error or '')[:120]}")
            continue
        append_record(path, endpoint, params, data)
        done.add(key)
        fetched += 1
        print(f"harvest: {endpoint} {target} ok")
        if delay > 0:
            time.sleep(delay)
    print(f"harvest: fetched {fetched}, skipped {skipped}, failed {failed}")
    return fetched


def main(argv=None):
    parser = argparse.ArgumentParser(description="Search a keyword and harvest product details as JSONL.")
    parser.add_argument("query", help="search keywords, as on shopping.naver.com")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many new records (default: all)")
    parser.add_argument("--out", help="run name under scripts/output/ (default: a timestamp); reuse to resume")
    parser.add_argument("--catalogs", action="store_true", help="also fetch /catalogs/reviews for catalog cards")
    parser.add_argument("--delay", type=float, default=0, help="seconds to pause after each fetched record")
    parser.add_argument("--base-url", help="server URL (default: NAVER_API_URL or http://localhost:8000)")
    args = parser.parse_args(argv)

    run = args.out or datetime.now().strftime("%Y%m%d-%H%M%S")
    harvest(NaverApiClient(base_url=args.base_url), args.query, args.limit,
            os.path.join(OUTPUT_ROOT, run), catalogs=args.catalogs, delay=args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
