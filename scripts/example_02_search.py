"""Example 2: search with filters, and count the matches.

/products/search answers up to 96 cards; /products/count says how many match.
For the full listing see example_07 (or harvest_listing.py).

    .venv/bin/python scripts/example_02_search.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()
query = "남성 골프채 풀세트"
filters = {"category": "50002788", "min_price": 300000, "max_price": 1000000}

count = api.count(query, **filters)                       # -> naver_types.CountResult
print(f"{count['total_count']} products match {query!r} {filters}")

search = api.search(query, **filters)                     # -> naver_types.SearchResult
for card in search["results"][:5]:                        # card: naver_types.SearchCard
    print(f"- {card['pricing']['discounted_price']:>9,} KRW  {(card['name'] or '')[:50]}  ({card['type']}: {card['link']})")
