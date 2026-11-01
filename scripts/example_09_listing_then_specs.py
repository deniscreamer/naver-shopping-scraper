"""Example 9: the full search listing, then each product's details the NEW way.

Like example 7, but step 2 asks for /products/specs as well: the product page's
상품정보 rows (종류, 성별, 총클럽개수, 원산지 ...) that /products/details does not
have. Use it to collect products you do not know yet, straight from a search.

Step 1 - the listing (your Chrome via the adapter), as in example 7.
Step 2 - per product: product_details() (the server's own Chrome, fast) and
product_specs(link, query=QUERY) (your Chrome again: naver.com -> 쇼핑 -> the
same search -> click the card whose link has this product id -> unfold the list;
~30-60 s each, one at a time). A product deeper in the listing than the first
search page is not clickable from there (404): it is then looked up by its
full name instead (the way example 10 does).

    .venv/bin/python scripts/example_09_listing_then_specs.py
"""
import time

import naver_types as T
from naver_api_client import ApiError, NaverApiClient

QUERY = "남성 골프채 풀세트"
BATCHES = 1                                   # ~50 products; 0 = the whole listing
DETAILS = 3                                   # how many products to open in step 2

api = NaverApiClient()


def specs_for(link: str) -> T.ProductSpecs | None:
    """From the listing's search first; by the product's own name when its card is not on that page."""
    for query in (QUERY, None):
        try:
            return api.product_specs(link, query=query)
        except ApiError as e:
            if e.status != 404:                        # 409 busy / 503 no extension or a wall: stop trying
                print(f"  specs: {e.status} {e.error}")
                return None
    print("  specs: the card was not found, by the search nor by the name")
    return None


listing = api.listing(QUERY, max_batches=BATCHES)        # -> naver_types.ListingResult
rows = [r for r in listing["results"] if not r["is_ad"]]
print(f"listing: {listing['job']['status']}, {len(listing['results'])} products ({len(rows)} not ads)\n")

for row in rows[:DETAILS]:
    try:
        product = api.product_details(row["link"])        # -> naver_types.ProductDetails
    except ApiError as e:
        print(f"- {row['link']}: {e.status} {e.error}")
        continue
    print(f"- {(product['name'] or '')[:60]}")
    print(f"  {product['pricing']['discounted_price']:,} KRW   category {' > '.join(product['category']['path'] or [])}")
    page = specs_for(row["link"])                         # -> naver_types.ProductSpecs | None
    facts = page["facts"] if page else product["facts"]
    for key in ("brand", "manufacturer", "origin"):
        fact = facts[key]
        print(f"  {key}: {fact['value'] + ' (' + fact['source'] + ')' if fact else '-'}")
    if page:
        print(f"  {len(page['specs'])} rows via {page['query']!r}" + ("" if page["is_complete"] else " [incomplete]"))
        for spec in page["specs"]:
            print(f"    {spec['label']}: {spec['value']}")
    time.sleep(2)                             # one at a time: both Chromes serve requests in turn
