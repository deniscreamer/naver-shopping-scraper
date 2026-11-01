"""Example 5: a store's profile and its best-sellers.

`store` takes a store slug or its smartstore / brand link.

    .venv/bin/python scripts/example_05_store.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()
store = api.get("/stores/details", store="dailyromantic")
print(store["name"], "-", store["link"], "- grade", store.get("grade"))

best = api.get("/stores/products", store="dailyromantic", list="best", period="weekly")
for product in best["results"][:5]:
    print(f"- {product['name'][:50]}  {product['link']}")
