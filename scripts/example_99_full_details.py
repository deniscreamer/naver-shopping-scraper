"""Example 99: FULL product data for a category - the one to grow.

Everything the API knows about a product today, for the products of one
category, one product at a time. When the API learns more, add it here.

  1. The category's products: the search listing for QUERY (your Chrome through
     the adapter), kept to CATEGORY_ID, ads dropped. (A category page entry is not
     built; the search + category id filter stands in for it.)
  2. Per product, in turn:
     - details   /products/details           prices, options, stock, category path, notice, description, facts
     - specs     /products/specs             the page's 상품정보 rows (your Chrome: search -> card -> page)
     - reviews   /products/reviews/selected  up to 20 reviews worth showing, with photos
     - photos    the gallery and the chosen reviews' photos + avatars, plain HTTP from the
                 image CDN, saved as the store's WebP (naver_images + image_prep; SHOP_STORE
                 in .env) into full-<category>/images/<product id>/: gallery <store>-<id>-001-<sha16>.webp
                 (short side down to 1500), reviews <store>-review-image|avatar-<sha16>.webp (1024 px)
  3. One JSON line per product in scripts/output/full-<category>/products.jsonl
     (`photos`: the gallery result, `review_media`: the review photos / avatars result).

Needs Chrome open with the adapter (example_01 says extension: connected).
Specs are read from the listing's own search first, then by the product's
name (a card deeper than the first page is not clickable from the search).

    .venv/bin/python scripts/example_99_full_details.py [products]
"""
import json
import os
import sys
import time
from collections import Counter

import naver_types as T
from naver_api_client import ApiError, NaverApiClient
from naver_images import download_gallery, download_review_media
from shop_stores import get_store

QUERY = "남성 골프채 풀세트"
CATEGORY_ID = "50002788"                      # 스포츠/레저 > 골프 > 골프클럽 > 풀세트
PRODUCTS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
REVIEWS = 20

api = NaverApiClient()
store = get_store()


def specs_for(link: str) -> T.ProductSpecs | None:
    for query in (QUERY, None):                           # the listing's search, then the product's name
        try:
            return api.product_specs(link, query=query)
        except ApiError as e:
            if e.status != 404:                            # 409 busy / 503 no extension or a wall
                print(f"  specs: {e.status} {e.error}")
                return None
    return None


listing = api.listing(QUERY, max_batches=1)               # -> naver_types.ListingResult
rows = [r for r in listing["results"] if not r["is_ad"] and r["category_id"] == CATEGORY_ID]
print(f"category {CATEGORY_ID}: {len(rows)} products in the first batch for {QUERY!r}; reading {PRODUCTS}\n")

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"full-{CATEGORY_ID}")
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "products.jsonl"), "w", encoding="utf-8") as out:
    for row in rows[:PRODUCTS]:
        try:
            details = api.product_details(row["link"])     # -> naver_types.ProductDetails
            reviews = api.selected_reviews(row["link"], count=REVIEWS)
        except ApiError as e:
            print(f"- {row['link']}: {e.status} {e.error}")
            continue
        specs = specs_for(row["link"])
        media_dir = os.path.join(out_dir, "images", details["id"] or "product")
        photos = download_gallery(details["images"], media_dir, store, details["id"])
        review_media = (download_review_media(reviews["results"], media_dir, store) if not photos["stopped"]
                        else None)
        out.write(json.dumps({"listing": row, "details": details, "specs": specs, "reviews": reviews,
                              "photos": photos, "review_media": review_media}, ensure_ascii=False) + "\n")
        facts = specs["facts"] if specs else details["facts"]
        brand = facts["brand"]
        print(f"- {(details['name'] or '')[:60]}")
        print(f"  {details['pricing']['discounted_price']} KRW, {len(details['variants'] or [])} options, "
              f"{len(details['images'])} images, brand {brand['value'] if brand else '-'}")
        stats = reviews["summary"] or details["reviews"]          # no summary: a product with 0 reviews
        total = stats["count"] if stats else None
        tiers = ", ".join(r["tier"] for r in reviews["results"][:5])
        rows_read = len(specs["specs"]) if specs else 0
        print(f"  specs: {rows_read} rows; reviews: {reviews['count']} chosen of {total} ({tiers})")
        sizes = ", ".join(f"{f['width']}x{f['height']}" for f in photos["files"])
        saved = f"{len(photos['files'])}/{photos['total']} WebP, {photos['originals']} from originals"
        print(f"  photos: {saved} ({sizes})"
              + ("" if photos["is_complete"] else f"  INCOMPLETE: {photos['stopped'] or photos['failed']}"))
        if review_media:
            kinds = Counter(f["kind"] for f in review_media["files"])
            print(f"  review media: {kinds['review-image']} photos, {kinds['review-avatar']} avatars, "
                  f"{len(review_media['failed'])} failed")
        if photos["stopped"] or (review_media and review_media["stopped"]):   # the CDN refused: stop the run
            break
        time.sleep(2)
print(f"\n-> {out_dir}/products.jsonl")
