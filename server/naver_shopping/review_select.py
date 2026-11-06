"""Which reviews to keep (/products/reviews/selected). Pure: parsed reviews
(parsers.parse_review, newest first) in, the chosen ones out, each with the
tier that let it in. api.product_reviews_selected feeds it the store backend's
photo/video pages first, then text-only pages, only as far as needed.

The policy (adapted 2026-11-01 from a catalog project's review collector):

  * primary: text of at least MIN_TEXT letters / digits, at least one photo and
    a real avatar (parsers.parse_review already turns Naver's no-avatar
    placeholder into None);
  * photo: the same text and photo, without an avatar;
  * text: the same text, no photo needed;
  * small source: when the product has SMALL_SOURCE reviews or fewer, every
    review with any letter or digit is taken, tier "small".

A video's poster counts as a photo (the owner's rule, 2026-11-05): a review with
only a video still qualifies for primary / photo, and the poster takes a place
under the photo caps. Only a video with a poster link counts; the attachment
keeps type "video" (scripts/naver_images saves the poster as a photo).

Up to `target` reviews, primary first, then photo, then text, each tier in
the order they came (newest first). Score plays no part:
critical reviews qualify the same way. Photos are capped per review
(MAX_PHOTOS_PER_REVIEW) and per product (MAX_PHOTOS); a review keeps its
text when the product cap is spent. Reviews of another product are dropped
by origin_product_id; a review read twice counts once.
"""
import unicodedata

MIN_TEXT = 50
SMALL_SOURCE = 20
MAX_PHOTOS_PER_REVIEW = 8
MAX_PHOTOS = 100


def text_length(text):
    """Letters and digits after NFC; spaces, punctuation and emoji do not count."""
    return sum(1 for ch in unicodedata.normalize("NFC", text or "") if ch.isalnum())


def _photos(review):
    """Photos and video posters, in the review's order."""
    return [a for a in review.get("attachments") or [] if a.get("type") == "image"
            or a.get("type") == "video" and a.get("link")]


def tier(review, small=False):
    """The tier a review qualifies for, or None."""
    length = text_length(review.get("text"))
    if small:
        return "small" if length else None
    if length < MIN_TEXT:
        return None
    if _photos(review):
        return "primary" if (review.get("writer") or {}).get("profile_image") else "photo"
    return "text"


def select(reviews, origin_product_id=None, review_count=None, target=20):
    """reviews: parsed reviews (parsers.parse_review) in page order, every pass
    concatenated. -> (chosen, mode): chosen reviews with "tier" added,
    mode "small_source" or "quality"."""
    small = review_count is not None and 0 < review_count <= SMALL_SOURCE
    tiers = {"primary": [], "photo": [], "text": [], "small": []}
    for review in _unique(reviews, origin_product_id):
        name = tier(review, small)
        if name:
            tiers[name].append(review)
    ordered = tiers["small"] if small else tiers["primary"] + tiers["photo"] + tiers["text"]
    chosen, budget = [], MAX_PHOTOS
    for review in ordered[:max(0, target)]:
        photos = _photos(review)[:min(MAX_PHOTOS_PER_REVIEW, budget)]
        budget -= len(photos)
        others = [a for a in review.get("attachments") or [] if a not in _photos(review)]   # videos with no poster
        name = tier(review, small)
        if not photos and name in ("primary", "photo"):     # the product's photo budget is spent
            name = "text"
        chosen.append({**review, "attachments": photos + others, "tier": name})
    return chosen, "small_source" if small else "quality"


def _unique(reviews, origin_product_id=None):
    """Each review once, only this product's."""
    seen = set()
    for review in reviews:
        key = review.get("id")
        if key in seen:
            continue
        seen.add(key)
        product = review.get("product") or {}
        if origin_product_id and product.get("origin_product_id") not in (None, str(origin_product_id)):
            continue
        yield review


def primary_count(reviews, origin_product_id=None):
    return sum(1 for r in _unique(reviews, origin_product_id) if tier(r) == "primary")
