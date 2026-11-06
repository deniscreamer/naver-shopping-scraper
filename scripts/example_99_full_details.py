"""Example 99: FULL product data for a category - the one to grow.

Everything the API knows about a product today, for the products of one
category, one product at a time. When the API learns more, add it here.

  0. Before the run (the owner's rules, 2026-11-05): the shop's Shopify values and token (shop_stores,
     .env), the category's package averages (category_measures.json: no row -> ask the operator, stop),
     the shop's catalog (shopify_catalog: what is already there) and its deferred journal (deferred_log).
  1. The category's products: the search listing for QUERY (your Chrome through
     the adapter), screened by listing_filter: ads, no name, rental, another category (exactly the leaf),
     already in the shop, deferred; each left out with its reason. (A category page entry is not built;
     the search + category id filter stands in for it.) The catalog is read again when older than 5 minutes.
  2. Per product, in turn (collect_guard: a partial product is tried once more, then deferred; a captcha /
     wall / refused CDN stops the run; two products in a row partial for the same reason stop the run):
     - details   /products/details           prices, stock, category path, notice, description, facts
     - specs     /products/specs             the page's 상품정보 rows, options, weight / size candidates
                                             (your Chrome: search -> card -> page)
     - variants  naver_variants.choose_variants: free variants only, or paid too with `paid` (the operator's
                 choice); sold-out ones kept and marked
     - package   package_measures: five shipping fields per variant, the seller's or the category's
     - reviews   /products/reviews/selected  up to 20 reviews worth showing, with photos (a video's poster
                 counts as a photo and is stored as one: naver_images.posters_as_photos)
     - photos    the gallery and the chosen reviews' photos, video posters + avatars, plain HTTP from the
                 image CDN, saved as the store's WebP (naver_images + image_prep; SHOP_STORE
                 in .env) into full-<category>/images/<product id>/: gallery <store>-<id>-001-<sha16>.webp
                 (short side down to 1500), reviews <store>-review-image|avatar-<sha16>.webp (1024 px)
  3. One JSON line per product in scripts/output/full-<category>/products.jsonl
     (`key`: the source key; `variants`: the variant choice, null when the page gave no options;
     `package`: the five fields per variant; `photos`: the gallery result, `review_media`: the review
     photos / avatars result).

Needs Chrome open with the adapter (example_01 says extension: connected).
Specs are read from the listing's own search first, then by the product's
name (a card deeper than the first page is not clickable from the search).

    .venv/bin/python scripts/example_99_full_details.py [products] [paid]
"""
import json
import os
import sys
import time
from collections import Counter

import naver_types as T
from collect_guard import CollectGuard, Outcome, RunStopped, SourceStopped
from deferred_log import DeferredLog
from listing_filter import Screen, source_key
from naver_api_client import ApiError, NaverApiClient
from naver_images import download_gallery, download_review_media, posters_as_photos
from naver_variants import choose_variants
from package_measures import CategoryDefaultsMissing, load_table, variant_measures
from shop_stores import get_store
from shopify_catalog import CatalogError, ShopCatalog, ShopNotConfigured

QUERY = "남성 골프채 풀세트"
CATEGORY_ID = "50002788"                      # 스포츠/레저 > 골프 > 골프클럽 > 풀세트
PRODUCTS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
PAID = len(sys.argv) > 2 and sys.argv[2] == "paid"        # the operator's choice: take paid variants too
REVIEWS = 20

api = NaverApiClient()
store = get_store()
table = load_table()
if not any(str(r["category_id"]) == CATEGORY_ID for r in table["rows"]):
    print(f"stop: {CategoryDefaultsMissing(CATEGORY_ID)}")
    sys.exit(2)
try:
    catalog = ShopCatalog(store)
    published = catalog.keys()
except (ShopNotConfigured, CatalogError) as e:
    print(f"stop: the shop check cannot run: {e}")
    sys.exit(2)
assert store.shopify                                  # ShopCatalog checked it
journal = DeferredLog(store.id.value)
guard = CollectGuard(journal)


def specs_for(link: str) -> T.ProductSpecs | None:
    """The specs, or None when the card is on neither search; a wall / busy adapter raises ApiError."""
    for query in (QUERY, None):                           # the listing's search, then the product's name
        try:
            return api.product_specs(link, query=query)
        except ApiError as e:
            if e.status != 404:
                raise
    return None


def collect(row: T.ListingRow, media_dir: str) -> Outcome:
    try:
        details = api.product_details(row["link"])     # -> naver_types.ProductDetails
        reviews = api.selected_reviews(row["link"], count=REVIEWS)
        specs = specs_for(row["link"])
    except ApiError as e:
        # a wall (503 from the adapter, 502 "blocked the request" from the box: captcha, login, 403/418/429) or a
        # busy adapter (409, a listing job holds Chrome): the whole source stops, no product is marked
        if e.status in (409, 503) or e.status == 502 and "blocked the request" in (e.error or ""):
            raise SourceStopped(f"{e.status} {e.error}")
        if e.status == 404:
            return Outcome("not_taken", "not_found", e.error)
        return Outcome.partial(f"api_{e.status}", e.error)
    if specs is None:
        return Outcome("not_taken", "card_not_found")
    options = specs["options"]
    variants = choose_variants(options, details["pricing"]["discounted_price"], paid=PAID) if options else None
    category = (specs["category"] or {}).get("id")
    if category != CATEGORY_ID:                       # the page's category differs from the listing card's
        return Outcome("not_taken", "category_mismatch", f"page category {category}")
    package = variant_measures(specs, table)          # the run's table row was checked before the run
    photos = download_gallery(details["images"], media_dir, store, details["id"])
    if photos["stopped"]:
        raise SourceStopped(f"image CDN: {photos['stopped']}")
    review_media = download_review_media(reviews["results"], media_dir, store)
    if review_media["stopped"]:
        raise SourceStopped(f"image CDN: {review_media['stopped']}")
    reviews["results"] = [posters_as_photos(r) for r in reviews["results"]]   # a video is stored as its poster
    data = {"listing": row, "details": details, "specs": specs, "variants": variants, "package": package,
            "reviews": reviews, "photos": photos, "review_media": review_media}
    if options is None:
        return Outcome.partial("options_missing", "the page gave no product answer", data)
    if not photos["is_complete"]:
        return Outcome.partial("photos_incomplete", photos["failed"][:3], data)
    return Outcome("complete", data=data)


listing = api.listing(QUERY, max_batches=1)               # -> naver_types.ListingResult
screen = Screen(CATEGORY_ID, store.shopify.namespace, published, journal.blocked())
rows = [r for r in listing["results"] if screen.reason(r) is None]
print(f"category {CATEGORY_ID}: {len(rows)} products to read in the first batch for {QUERY!r} "
      f"(left out: {dict(screen.counts) or 'none'}); reading {PRODUCTS}\n")

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"full-{CATEGORY_ID}")
os.makedirs(out_dir, exist_ok=True)
taken = 0
with open(os.path.join(out_dir, "products.jsonl"), "w", encoding="utf-8") as out:
    for row in rows:
        if taken >= PRODUCTS:
            break
        key = source_key(row, store.shopify.namespace)
        assert key                                         # the screen left out rows without one
        try:
            fresh = catalog.keys()                         # published meanwhile? (read again every 5 minutes)
        except (ShopNotConfigured, CatalogError) as e:
            print(f"stop: the shop check failed: {e}")
            break
        if key in fresh:
            print(f"- {key}: already_published")
            continue
        try:
            outcome = guard.run(key, lambda: collect(row, os.path.join(out_dir, "images", row["product_id"])))
        except (SourceStopped, RunStopped) as e:
            print(f"stop: {e}")
            break
        if outcome.status == "not_taken":
            print(f"- {key}: not taken ({outcome.reason})")
            continue
        if outcome.status == "deferred":
            print(f"- {key}: deferred ({outcome.reason}; first: {outcome.first})")
            continue
        taken += 1
        d = outcome.data
        details, specs, variants, reviews = d["details"], d["specs"], d["variants"], d["reviews"]
        photos, review_media, package = d["photos"], d["review_media"], d["package"]
        out.write(json.dumps({"key": key, **d}, ensure_ascii=False) + "\n")
        brand = specs["facts"]["brand"]
        print(f"- {(details['name'] or '')[:60]}  ({key}{', retried' if outcome.attempts > 1 else ''})")
        chosen = (f"{len(variants['variants'])} variants ({variants['sold_out']} sold out, "
                  f"{variants['skipped_paid']} paid left out)" if variants else "options unknown")
        print(f"  {details['pricing']['discounted_price']} KRW, {chosen}, "
              f"{len(details['images'])} images, brand {brand['value'] if brand else '-'}")
        stats = reviews["summary"] or details["reviews"]          # no summary: a product with 0 reviews
        total = stats["count"] if stats else None
        tiers = ", ".join(r["tier"] for r in reviews["results"][:5])
        print(f"  specs: {len(specs['specs'])} rows; reviews: {reviews['count']} chosen of {total} ({tiers})")
        sources = Counter(f["source"] for v in package for f in v["fields"].values())
        print(f"  package: {len(package)} variant(s), fields {dict(sources)}, "
              f"{len(specs['measures']['references'])} references, {len(specs['measures']['review'])} to review")
        sizes = ", ".join(f"{f['width']}x{f['height']}" for f in photos["files"])
        saved = f"{len(photos['files'])}/{photos['total']} WebP, {photos['originals']} from originals"
        print(f"  photos: {saved} ({sizes})"
              + ("" if photos["is_complete"] else f"  INCOMPLETE: {photos['failed']}"))
        kinds = Counter(f["kind"] for f in review_media["files"])
        posters = sum(1 for f in review_media["files"] if f["from_video"])
        print(f"  review media: {kinds['review-image']} photos ({posters} video posters), "
              f"{kinds['review-avatar']} avatars, {len(review_media['failed'])} failed")
        time.sleep(2)
print(f"\n-> {out_dir}/products.jsonl")
