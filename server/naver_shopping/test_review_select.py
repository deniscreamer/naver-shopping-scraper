"""Offline tests for the review choice (naver_shopping/review_select.py).

    python -m pytest server/naver_shopping/test_review_select.py -q

box_reviews_page1.json is a real query-pages answer (captured 2026-10-24): 20
reviews, 1 primary (193 letters, 10 photos, an avatar), 1 photo tier (178
letters, 10 photos, no avatar), 10 text, 8 too short.
"""
import json
import os

from naver_shopping import parsers as P, review_select as S

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def reviews():
    with open(os.path.join(FX, "box_reviews_page1.json"), encoding="utf-8") as f:
        return P.parse_reviews_page(json.load(f))[0]


def test_text_length_counts_letters_and_digits():
    assert S.text_length("좋아요!! 10점 :) 👍") == 6 and S.text_length(None) == 0


def test_tiers_in_order_and_caps():
    rs = reviews()
    chosen, mode = S.select(rs, "10302552667", 6686, target=20)
    assert mode == "quality" and [r["tier"] for r in chosen][:2] == ["primary", "photo"]
    assert [r["tier"] for r in chosen].count("text") == 10 and len(chosen) == 12
    assert all(len([a for a in r["attachments"] if a["type"] == "image"]) <= S.MAX_PHOTOS_PER_REVIEW for r in chosen)
    assert S.select(rs, "10302552667", 6686, target=1)[0][0]["tier"] == "primary"
    assert S.primary_count(rs) == 1


def test_other_products_and_duplicates_dropped():
    rs = reviews()
    assert S.select(rs + rs, "10302552667", 6686)[0] == S.select(rs, "10302552667", 6686)[0]
    assert S.select(rs, "999", 6686)[0] == []


def test_small_source_takes_any_text():
    rs = reviews()
    chosen, mode = S.select(rs, None, 20, target=20)
    assert mode == "small_source" and len(chosen) == 20 and {r["tier"] for r in chosen} == {"small"}


def test_photo_budget_per_product(monkeypatch):
    monkeypatch.setattr(S, "MAX_PHOTOS", 9)
    chosen, _ = S.select(reviews(), "10302552667", 6686)
    photos = [len([a for a in r["attachments"] if a["type"] == "image"]) for r in chosen]
    assert photos[:2] == [8, 1] and sum(photos) == 9
    assert chosen[0]["tier"] == "primary" and chosen[1]["tier"] == "photo"
    monkeypatch.setattr(S, "MAX_PHOTOS", 8)                     # the second review gets no photo: tier text
    assert [r["tier"] for r in S.select(reviews(), "10302552667", 6686)[0]][:2] == ["primary", "text"]


def test_primary_count_dedups_and_filters():
    rs = reviews()
    assert S.primary_count(rs + rs, "10302552667") == 1 and S.primary_count(rs, "999") == 0



# ---- the store-backend side: media filter and reviews/selected (api) ----------------------

RECORD = {"base": {"id": "10352481064", "origin_product_id": "10302552667", "name": "n", "link": "l"},
          "store": {"merchant_id": "500278691"}, "review_summary": {"count": 6686}}


def _backend(monkeypatch, pages):
    """A fake box: pages[media] = list of payloads (page 1, 2, ...); records every body sent."""
    from naver_shopping import api as A
    import cache
    sent = []

    def box_post(path, body, label):
        sent.append(dict(body))
        media = ",".join(body.get("reviewContentClassTypes") or ["ALL"])
        payloads = pages.get(media, [])
        return payloads[body["page"] - 1] if body["page"] <= len(payloads) else None
    monkeypatch.setattr(A, "_record", lambda product: RECORD)
    monkeypatch.setattr(A, "box_post", box_post)
    monkeypatch.setattr(cache, "_store", {})
    return A, sent


def _page(reviews_payload, page, total_pages):
    return dict(reviews_payload, page=page, totalPages=total_pages, totalElements=total_pages * 20)


def test_media_filter_is_sent(monkeypatch):
    """2026-11-01: reviewContentClassTypes [PHOTO, VIDEO] gave 91 of 202 (Honma D1 set)."""
    from naver_shopping import schemas
    A, sent = _backend(monkeypatch, {})
    data = schemas.ProductReviewsSchema().load({"product": "10352481064", "media": "photo_video", "sort": "recent"})
    assert A._reviews(**data)["media"] == "photo_video"
    assert sent[-1]["reviewContentClassTypes"] == ["PHOTO", "VIDEO"]
    A._reviews(**schemas.ProductReviewsSchema().load({"product": "10352481064"}))
    assert "reviewContentClassTypes" not in sent[-1]
    import pytest
    from marshmallow import ValidationError
    for bad in ({"product": "1", "media": "video"}, ):
        with pytest.raises(ValidationError):
            schemas.ProductReviewsSchema().load(bad)
    assert schemas.ProductReviewsSelectedSchema().load({"product": "10352481064"})["count"] == 20
    for bad in ({"product": "10352481064", "count": "0"}, {"product": "10352481064", "count": "101"}):
        with pytest.raises(ValidationError):
            schemas.ProductReviewsSelectedSchema().load(bad)


def test_selected_reads_photo_pages_then_text(monkeypatch):
    with open(os.path.join(FX, "box_reviews_page1.json"), encoding="utf-8") as f:
        payload = json.load(f)
    A, sent = _backend(monkeypatch, {"PHOTO,VIDEO": [_page(payload, 1, 1)], "TEXT": [_page(payload, 1, 2),
                                                                                       _page(payload, 2, 2)]})
    out = A.product_reviews_selected(product="10352481064", count=5)
    assert [p["media"] for p in out["passes"]] == ["photo_video"] and out["count"] == 5 and out["is_complete"]
    assert [r["tier"] for r in out["results"]][:2] == ["primary", "photo"]
    out = A.product_reviews_selected(product="10352481064", count=20)       # photos run out: text pages too
    assert [p["media"] for p in out["passes"]] == ["photo_video", "text"] and out["passes"][1]["is_exhausted"]
    assert out["count"] == 12 and out["is_complete"] and out["scanned"] == 20
    assert all(b["reviewSearchSortType"] == "REVIEW_CREATE_DATE_DESC" for b in sent)


def test_selected_pages_without_totals(monkeypatch):
    """A page without totalElements has total_pages None: read on while pages are full."""
    with open(os.path.join(FX, "box_reviews_page1.json"), encoding="utf-8") as f:
        payload = {k: v for k, v in json.load(f).items() if k != "totalElements"}
    A, sent = _backend(monkeypatch, {"PHOTO,VIDEO": [payload, payload], "TEXT": []})
    out = A.product_reviews_selected(product="10352481064", count=20)
    assert out["passes"][0]["pages"] == 3 and out["passes"][0]["is_exhausted"]


def test_selected_no_reviews_reads_nothing(monkeypatch):
    """2026-11-01, GV Tour set: no review summary, base reviews count 0."""
    monkeypatch.setitem(RECORD, "review_summary", None)
    monkeypatch.setitem(RECORD, "base", dict(RECORD["base"], reviews={"count": 0}))
    A, sent = _backend(monkeypatch, {})
    out = A.product_reviews_selected(product="10352481064", count=20)
    assert sent == [] and out["passes"] == [] and out["count"] == 0 and out["is_complete"]


def test_selected_small_source_reads_all(monkeypatch):
    with open(os.path.join(FX, "box_reviews_page1.json"), encoding="utf-8") as f:
        payload = json.load(f)
    monkeypatch.setitem(RECORD, "review_summary", {"count": 20})
    A, sent = _backend(monkeypatch, {"ALL": [_page(payload, 1, 1)]})
    out = A.product_reviews_selected(product="10352481064", count=20)
    assert out["mode"] == "small_source" and out["count"] == 20 and [p["media"] for p in out["passes"]] == ["all"]
