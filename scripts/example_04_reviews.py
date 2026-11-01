"""Example 4: a product's reviews, page by page (20 per page).

api.pages() drives `page` itself and stops at the last page; max_page bounds it.

    .venv/bin/python scripts/example_04_reviews.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()
product = "https://smartstore.naver.com/dailyromantic/products/8087042745"

for page in api.pages("/products/reviews", product=product, sort="recent", max_page=2):
    print(f"page {page['current_page']} of {page['total_pages']} ({page['count']} reviews)")
    for review in page["results"][:3]:
        print(f"  {review['score']}*  {' '.join((review['text'] or '').split())[:60]}")
