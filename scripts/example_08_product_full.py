"""Example 8: one product, as complete as the API gets it (a men's golf club set).

Two calls, two transports, one product:

  * api.product_details(link) - the store backend (the server's own Chrome):
    prices, options, category path, the legal notice (상품정보제공고시), the
    description, and `facts` (brand / manufacturer / model / origin with the
    place each was read).
  * api.product_specs(link)   - the product page's 상품정보 list, read in YOUR
    Chrome through the adapter (open with the extension loaded, example_01 says
    extension: connected): the seller's rows (종류, 성별, 총클럽개수, 원산지 ...)
    and `facts` again, now with those rows first. ~30 s cold, cached a day.

    .venv/bin/python scripts/example_08_product_full.py [product link] [search query]
"""
import sys

import naver_types as T
from naver_api_client import ApiError, NaverApiClient

PRODUCT = sys.argv[1] if len(sys.argv) > 1 else "https://smartstore.naver.com/scarabee/products/13021362937"
QUERY = sys.argv[2] if len(sys.argv) > 2 else None        # None: the server searches the product's own name

api = NaverApiClient()
product = api.product_details(PRODUCT)                    # -> naver_types.ProductDetails
page: T.ProductSpecs | None
try:
    page = api.product_specs(PRODUCT, query=QUERY)        # -> naver_types.ProductSpecs
except ApiError as e:                                     # 409 busy, 503 no extension / a wall, 404 not listed
    print(f"specs unavailable: {e.status} {e.error}\n")
    page = None
facts = page["facts"] if page else product["facts"]       # page facts include the 상품정보 rows

print(product["name"])
print(f"{product['pricing']['discounted_price']:,} KRW   {product['link']}\n")

print("1. specs (상품정보, label -> value)" + ("" if page and page["is_complete"] else "  [incomplete]"))
for spec in (page["specs"] if page else []):
    print(f"   {spec['label']}: {spec['value']}")

print("\n2-3. facts")
for key in ("brand", "manufacturer", "model_name", "origin"):
    fact = facts[key]                                     # None when no source states it
    print(f"   {key:<12} {fact['value'] + '   <- ' + fact['source'] if fact else '-'}")

category = product["category"]
print("\n4. category")
print(f"   {category['id']}  {' > '.join(category['path'] or [])}")
if page:
    print(f"   read from the search: {page['query']!r}")

notice = product["notice"]                                # the legal notice; None when the store sent none
print("\n5. notice (상품정보제공고시)" + (f" type {notice['type']}" if notice else ": none"))
for row in (notice["items"] if notice else []):
    print(f"   {row['label']}: {'(see the description)' if row['is_see_description'] else row['value']}")

description = product["description"]
text = description["text"] if description else None
images = (description["images"] if description else None) or []
print("\n6. description text")
print(f"   {text[:600]}" if text else f"   no text (images only: {len(images)} snapshot images)")
