"""Example 11: a product's reviews, complete, the original way (/products/reviews).

Everything /products/reviews gives per review, in the store's order, for as many
pages as asked: id, score, date, full text, the option bought, likes, the
writer (masked id, avatar link) and the attached photos / videos (links and
sizes; files are not downloaded). Plus the summary of the whole product
(count, average, stars, photo / video counts) that comes with every page.

Transport on the server: the store backend in the server's own Chrome (no
adapter). 20 reviews a page; sort: recent (newest first), ranking (the store's
default), score_high, score_low. There is no photo-only filter on this route.
Output: scripts/output/reviews-<product id>/reviews.jsonl, one review a line.

    .venv/bin/python scripts/example_11_reviews_full.py [product link] [pages, 0 = all] [sort]
"""
import json
import os
import sys

import naver_types as T
from naver_api_client import NaverApiClient

# Honma D1 set: 202 reviews, 11 pages (2026-11-01), enough to show the paging
PRODUCT = sys.argv[1] if len(sys.argv) > 1 else "https://smartstore.naver.com/thegolf/products/5543663553"
PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 3          # 0 = every page (up to the server's 500)
SORT = sys.argv[3] if len(sys.argv) > 3 else "recent"

api = NaverApiClient()
reviews: list[T.Review] = []
seen: set[str] = set()
summary: T.ReviewSummary | None = None
total: int | None = None

for page in api.reviews(PRODUCT, sort=SORT, max_page=PAGES or None):      # -> naver_types.ReviewsPage
    summary = summary or page["summary"]
    total = page["count"] if page["count"] is not None else total
    for review in page["results"]:
        key = review["id"] or json.dumps(review, sort_keys=True)          # pages shift as reviews arrive
        if key not in seen:
            seen.add(key)
            reviews.append(review)
    print(f"page {page['current_page']}/{page['total_pages']}: {len(reviews)} reviews so far")

product_id = PRODUCT.rstrip("/").split("/")[-1].split("?")[0]
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"reviews-{product_id}")
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "reviews.jsonl"), "w", encoding="utf-8") as f:
    for position, review in enumerate(reviews, 1):
        f.write(json.dumps({"position": position, "sort": SORT, **review}, ensure_ascii=False) + "\n")

if summary:
    counts = summary["score_counts"]                               # may be None
    stars = [counts["5"], counts["4"], counts["3"], counts["2"], counts["1"]] if counts else None
    print(f"\nsummary: {summary['count']} reviews, average {summary['average_score']}, "
          f"{summary['photo_count']} with photos, {summary['video_count']} with videos, stars 5..1: {stars}")
photos = sum(1 for r in reviews for a in r["attachments"] if a["type"] == "image")
with_photos = sum(1 for r in reviews if any(a["type"] == "image" for a in r["attachments"]))
videos = sum(1 for r in reviews for a in r["attachments"] if a["type"] == "video")
avatars = sum(1 for r in reviews if r["writer"]["profile_image"])   # null = no avatar (placeholder dropped)
print(f"read {len(reviews)} of {total} ({SORT}): {photos} photos in {with_photos} reviews, {videos} videos, "
      f"{avatars} with a real avatar -> {out_dir}/reviews.jsonl\n")

for position, review in enumerate(reviews[:5], 1):
    text = " ".join((review["text"] or "").split())
    media = ", ".join(f"{a['type']} {a['width']}x{a['height']}" for a in review["attachments"]) or "no media"
    print(f"{position}. {review['score']}*  {review['created_at']}  id {review['id']}  {review['writer']['masked_id']}")
    print(f"   option: {review['option'] or '-'}   likes: {review['likes']}   {media}")
    print(f"   {text[:200]}")
