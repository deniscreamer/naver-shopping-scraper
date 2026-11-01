"""Example 10: details of products you already know, the NEW way, by their full name.

You have product links (from a listing, a spreadsheet, an earlier run) and want
the product page's 상품정보 rows for each. The adapter cannot open a product page
directly (Naver sends that to the login page), so the server walks there like a
person: naver.com -> 쇼핑 -> search the product's FULL Korean name -> click the
card whose link carries THIS product id (not just the first card) -> unfold.

The full name comes from /products/details (fast, the server's own Chrome) and is
passed as `query` explicitly here; /products/specs uses the same default when
`query` is left out.

    .venv/bin/python scripts/example_10_known_products_specs.py [link ...]
"""
import sys
import time

from naver_api_client import ApiError, NaverApiClient

LINKS = sys.argv[1:] or [
    "https://smartstore.naver.com/scarabee/products/13021362937",   # PING G440K + Bridgestone V300 set
    "https://smartstore.naver.com/thegolf/products/5543663553",     # Honma D1 set
    "https://smartstore.naver.com/thegolf/products/12736318849",    # Callaway XR26 set
]

api = NaverApiClient()

for link in LINKS:
    product = api.product_details(link)                  # -> naver_types.ProductDetails
    name = product["name"]
    if not name:
        print(f"- {link}: no name to search for")
        continue
    print(f"- {name}")
    try:
        page = api.product_specs(link, query=name)       # the card is matched by id on that search page
    except ApiError as e:                                # 404 not on the page, 409 busy, 503 no extension / a wall
        print(f"  specs: {e.status} {e.error}")
        continue
    rows = {spec["label"]: spec["value"] for spec in page["specs"]}
    print(f"  {len(rows)} rows{'' if page['is_complete'] else ' [incomplete]'}: " +
          ", ".join(f"{label}={value}" for label, value in rows.items()))
    brand = page["facts"]["brand"]
    print(f"  brand: {brand['value'] + ' <- ' + brand['source'] if brand else '-'}")
    time.sleep(2)
