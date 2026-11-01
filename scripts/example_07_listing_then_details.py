"""Example 7: the full search listing, then each product's details.

Step 1 - the listing: api.listing() asks the server for every product of a
search (not capped at 96). On the server this runs in your own Chrome through
the adapter extension, but the script only sees HTTP. Needs Chrome open with
the adapter loaded (example_01 says extension: connected).

Step 2 - details: every listing row carries the store product `link` that
/products/details takes; those calls go the server's usual way (its own
Chrome), not through the adapter. Same script, two transports, one API.

    .venv/bin/python scripts/example_07_listing_then_details.py
"""
import time

from naver_api_client import ApiError, NaverApiClient

QUERY = "남성 골프채 풀세트"
BATCHES = 1                                   # ~50 products; 0 = the whole listing
DETAILS = 3                                   # how many products to open in step 2

api = NaverApiClient()

listing = api.listing(QUERY, max_batches=BATCHES)        # -> naver_types.ListingResult
rows = [r for r in listing["results"] if not r["is_ad"]]
print(f"listing: {listing['job']['status']}, {len(listing['results'])} products ({len(rows)} not ads)\n")

for row in rows[:DETAILS]:
    try:
        product = api.product_details(row["link"])         # -> naver_types.ProductDetails
    except ApiError as e:
        print(f"- {row['link']}: {e.status} {e.error}")
        continue
    print(f"- {(product['name'] or '')[:50]}")
    summary = product["reviews"]                            # the types say it may be None: guard it
    reviews = summary["count"] if summary else None
    print(f"  {product['pricing']['discounted_price']:,} KRW, stock {product['stock_quantity']}, "
          f"{reviews} reviews, {len(product['variants'] or [])} options")
    time.sleep(2)                             # one at a time: the server's Chrome serves them in turn
