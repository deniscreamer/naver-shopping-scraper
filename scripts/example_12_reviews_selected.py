"""Example 12: reviews, way 2 - the reviews worth showing, chosen on the server.

api.selected_reviews(link, count) returns up to `count` reviews picked like
this (the server reads only as many pages as it needs, newest first):

  1. primary - 50+ letters / digits, at least one photo, a real avatar;
  2. photo   - the same text and photo, no avatar;
  3. text    - the same text, no photo (read from the text-only filter);
  small      - a product with 20 reviews or fewer: every review with text.

Score plays no part (critical reviews count the same); at most 8 photos a
review, 100 a product. Photo links are originals; avatars are null when the
writer has none. Way 1 (example 11) reads every review instead. Both come from
the store backend in the server's own Chrome: no adapter, a few seconds.

    .venv/bin/python scripts/example_12_reviews_selected.py [product link] [count]
"""
import json
import os
import sys
from collections import Counter

from naver_api_client import NaverApiClient

PRODUCT = sys.argv[1] if len(sys.argv) > 1 else "https://smartstore.naver.com/thegolf/products/5543663553"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 20

api = NaverApiClient()
picked = api.selected_reviews(PRODUCT, count=COUNT)            # -> naver_types.SelectedReviews
summary = picked["summary"]                                    # may be None

print(picked["product"]["name"])
if summary:
    print(f"{summary['count']} reviews, average {summary['average_score']}, {summary['photo_count']} with photos")
for p in picked["passes"]:
    end = ", to the end" if p["is_exhausted"] else ""
    print(f"read {p['media']}: {p['pages']} page(s) of {p['total_count']}{end}")
print(f"chose {picked['count']} of {picked['scanned']} read ({picked['mode']}): "
      f"{dict(Counter(r['tier'] for r in picked['results']))}" + ("" if picked["is_complete"] else "  [incomplete]"))

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       f"reviews-selected-{picked['product']['id'] or 'product'}")
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "reviews.jsonl"), "w", encoding="utf-8") as f:
    for review in picked["results"]:
        f.write(json.dumps(review, ensure_ascii=False) + "\n")
print(f"-> {out_dir}/reviews.jsonl\n")

for review in picked["results"][:5]:
    photos = [a for a in review["attachments"] if a["type"] == "image"]
    print(f"[{review['tier']}] {review['score']}*  {review['created_at']}  {review['writer']['masked_id']}  "
          f"{len(photos)} photo(s), avatar {'yes' if review['writer']['profile_image'] else 'no'}")
    print(f"   {' '.join((review['text'] or '').split())[:160]}")
