"""Offline tests for the search.shopping listing parsers (composite.py).

    python -m pytest server/naver_shopping/test_composite.py -q

Fixtures are trimmed real captures of 2026-11-01 (남성 골프채 풀세트):
composite_search_page.html carries the first batch in Next.js RSC chunks,
composite_answer.json is one paged-composite-cards answer. Tracking / ad /
session fields were removed. No network.
"""
import os

from naver_shopping import composite as C

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


def test_first_batch_from_html():
    batch = C.first_batch(fixture("composite_search_page.html"))
    assert batch["cursor"] == 35 and batch["hasMore"] is True and batch["total"] == 4385
    assert len(C.products(batch)) == 3


def test_first_batch_absent():
    assert C.first_batch("<html><body>no data</body></html>") is None
    assert C.first_batch(None) is None


def test_batch_from_answer():
    batch = C.batch_from_answer(fixture("composite_answer.json"))
    assert batch["cursor"] == 73 and batch["hasMore"] is True and batch["total"] == 4385
    assert len(C.products(batch)) == 4
    assert C.batch_from_answer("<!DOCTYPE html>418 page") is None


def test_listing_row_builds_store_link():
    rows = [C.listing_row(p) for p in C.products(C.batch_from_answer(fixture("composite_answer.json")))]
    assert all(rows)
    row = rows[0]
    assert row["link"] == f"https://smartstore.naver.com/{row['store']['slug']}/products/{row['product_id']}"
    assert row["product_id"].isdigit() and row["pricing"]["currency"] == "KRW" and row["image"].startswith("https://")
    assert row["is_ad"] is True                      # the first card of that answer is an ad
    assert any(r["store"]["is_brand_store"] for r in rows)
    assert all(r["store"]["channel_no"].isdigit() for r in rows)       # the card's channelNo, for shop keys
    assert all("clickUrl" not in r for r in rows)


def test_listing_row_rejects_non_store_products():
    assert C.listing_row({"channelProductId": "123", "mallUrl": {"pcUrl": "https://link.coupang.com/x"}}) is None
    assert C.listing_row({"mallUrl": {"pcUrl": "https://smartstore.naver.com/inflow/outlink/url?url="
                                               "https%3A%2F%2Fsmartstore.naver.com%2Fshop"}}) is None


def test_store_link_from_mobile_url():
    p = {"mallUrl": {"mobileUrl": "https://m.smartstore.naver.com/inflow/outlink/url?url="
                                  "https%3A%2F%2Fm.smartstore.naver.com%2Fgolfshop"}}
    assert C.store_link(p) == "https://smartstore.naver.com/golfshop"


def test_store_link_direct_and_reserved_paths():
    assert C.store_link({"mallUrl": {"pcUrl": "https://smartstore.naver.com/golfshop"}}) == \
        "https://smartstore.naver.com/golfshop"
    assert C.store_link({"mallUrl": {"pcUrl": "https://smartstore.naver.com/main/products/123"}}) is None


def test_the_search_pages_filters_are_read():
    """2026-11-22: the RSC object of MAIN:* filters (a trimmed real page of 여성 골프 바람막이 점퍼): the category tree
    (one entry per id, its full path), the sellers' attributes, the price bands, the facets' titles."""
    got = C.page_filters(fixture("search_page_filters.html"))
    paths = {c["id"]: " > ".join(c["path"]) for c in got["categories"]}
    assert paths["50002798"] == "스포츠/레저 > 골프 > 골프의류 > 점퍼" and paths["50000029"] == "스포츠/레저 > 골프"
    assert [a["name"] for a in got["attributes"]] == ["긴팔", "반팔", "나일론"]
    assert got["attributes"][0] == {"id": "10012485|M10574795", "group": "10012485", "name": "긴팔"}
    assert got["price"][0] == {"start": 10000, "end": 20000, "weight": 7}
    assert got["facets"] == ["공식브랜드", "특징", "가격", "카테고리"]
    assert C.page_filters("<html></html>") is None
