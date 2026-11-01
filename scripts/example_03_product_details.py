"""Example 3: one product's details: prices, options, stock, review stats.

`product` takes a store product link or the bare product id. The first call
may take ~10 s (the server opens its Chrome once); the next ones are fast.

    .venv/bin/python scripts/example_03_product_details.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()
product = api.get("/products/details", product="https://smartstore.naver.com/dailyromantic/products/8087042745")

print(product["name"])
print("price:  ", product["pricing"]["discounted_price"], product["pricing"]["currency"])
print("stock:  ", product["stock_quantity"])
print("reviews:", product["reviews"]["count"], "avg", product["reviews"]["average_score"])
print("store:  ", product["store"]["name"], product["store"]["link"])
for variant in product["variants"][:3]:
    print(f"  option: {variant['name']}  +{variant['extra_price']} KRW  stock {variant['stock_quantity']}")
