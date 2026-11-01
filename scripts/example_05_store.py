"""Example 5: a store's profile and its best-sellers.

`store` takes a store slug or its smartstore / brand link.

    .venv/bin/python scripts/example_05_store.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()
store = api.store_details("dailyromantic")                         # -> naver_types.StoreDetails
print(store["name"], "-", store["link"], "- grade", store.get("grade"))

best = api.store_products("dailyromantic", list="best", period="weekly")   # -> StoreProducts
for product in best["results"][:5]:
    print(f"- {(product['name'] or '')[:50]}  {product['link']}")
