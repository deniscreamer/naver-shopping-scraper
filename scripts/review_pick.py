"""The reviews a product keeps when it has many (the owner, 2026-11-11, after the junior clubs: cheap, popular
products brought 19-20 chosen reviews and 20-36 photos each, against 1 review for a full set, and their collection
took 47-186 s against 45-65 s; the time goes on the photos' download, their translation and upload, not on the
review pages, ~3 s for 7 of them).

The server still chooses up to `count` candidates (/products/reviews/selected: text, photo and avatar tiers). When
there are more than KEEP, this picks the KEEP best by what they say of the product, before any photo is fetched:

    score = text quality (review_clean.clean: the aspects named, the length; 0..100)
          + 20 a full text (it names the product)   - 30 nothing left but the rating
          + 10 per "helpful" vote (3 at most)       + 10 several photos, + 5 one photo
          - 25 a text that tells of the purchase (seller, packing, shipping, gifts) and names no aspect
    sponsored reviews (체험단, 협찬) are not taken; the score's stars play no part (a fair low score stays).

Equal scores keep the server's order (newest first); a text already taken (one buyer's review of another order,
word for word) is not taken again. The kept reviews keep that order too. Photos: PER_REVIEW
at most per review, PER_PRODUCT in all, the best reviews' first. A product with KEEP reviews or fewer is left as it
came (a full set's one or two reviews). The choice is recorded in the collected line (`reviews.picked`).

    from review_pick import pick
    results, summary = pick(picked["results"], category_id)
"""
import re
from collections.abc import Mapping, Sequence
from typing import Any

from review_clean import clean

KEEP = 8                    # reviews a product keeps when it has more
PER_REVIEW = 3              # photos of one review
PER_PRODUCT = 12            # photos of all its reviews
PURCHASE = {"seller", "packing", "shipping", "gift"}       # review_clean's topics that tell of the Korean purchase
RULE = "review_pick/1"


def score(review: Mapping[str, Any], category_id: str | None) -> float | None:
    """How much a review says of the product, higher first; None: not taken (sponsored)."""
    photos = len(review.get("attachments") or [])
    v = clean(review.get("text") or "", bool(photos), category_id)
    if not v.keep:
        return None
    raw = review.get("likes")
    likes = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
    out = float(v.quality)
    out += {"full": 20, "short": 0}.get(v.grade, -30)
    out += 10 * min(max(likes, 0), 3)
    out += 10 if photos >= 2 else 5 if photos == 1 else 0
    out -= 25 if set(v.cut) & PURCHASE and v.grade != "full" else 0
    return out


def pick(results: Sequence[Mapping[str, Any]], category_id: str | None, keep: int = KEEP, per_review: int = PER_REVIEW,
         per_product: int = PER_PRODUCT) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """(the reviews kept, in the server's order, their photos capped; the summary, None when nothing was cut)."""
    if len(results) <= keep:
        return [dict(r) for r in results], None
    scored = [(s, i) for i, r in enumerate(results) if (s := score(r, category_id)) is not None]
    best: list[int] = []
    seen: set[str] = set()
    for _, i in sorted(scored, key=lambda x: (-x[0], x[1])):
        text = re.sub(r"\W+", "", results[i].get("text") or "")[:80]
        if text and text in seen:                           # one buyer's text again (another order, 4987660149)
            continue
        seen.add(text)
        best.append(i)
        if len(best) == keep:
            break
    room = per_product
    capped: dict[int, dict[str, Any]] = {}
    for i in best:                                          # the best reviews take the photo budget first
        attachments = list(results[i].get("attachments") or [])[:max(0, min(per_review, room))]
        room -= len(attachments)
        capped[i] = {**results[i], "attachments": attachments}
    kept = [capped[i] for i in sorted(capped)]
    photos_in = sum(len(r.get("attachments") or []) for r in results)
    summary = {"rule": RULE, "from": len(results), "kept": len(kept), "photos_from": photos_in,
               "photos_kept": sum(len(r["attachments"]) for r in kept),
               "scores": {str(results[i].get("id")): round(s, 1) for s, i in scored}}
    return kept, summary
