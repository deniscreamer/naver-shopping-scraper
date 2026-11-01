"""Example 6: Naver DataLab: a category's top keywords and a keyword's trend.

Category ids come from /categories/list (50002788 = golf full sets,
50001102 = golf clubs).

    .venv/bin/python scripts/example_06_datalab.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()

rank = api.get("/keywords/rank", category="50001102")
print("top keywords in", rank["category_name"], ":", ", ".join(k["keyword"] for k in rank["results"][:10]))

trend = api.get("/keywords/trend", keyword="골프채", category="50001102", period="weekly")
for point in trend["series"][-4:]:
    print(f"  {point['date']}  {point['value']}")
