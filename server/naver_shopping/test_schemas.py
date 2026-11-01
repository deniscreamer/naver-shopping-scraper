"""Offline tests for the /naver-shopping/* request schemas.

    python -m pytest naver_shopping/test_schemas.py -q
"""
import os
import sys
from datetime import date, timedelta

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from naver_shopping import schemas  # noqa: E402


def test_search_schema_defaults_and_filters():
    loaded = schemas.ProductsSearchSchema().load({"query": " 아이폰 "})
    assert loaded["query"] == "아이폰" and loaded["min_price"] is None and loaded["free_delivery"] is None
    loaded = schemas.ProductsSearchSchema().load({"query": "아이폰", "min_price": "100000", "max_price": "300000",
                                                  "category": "50001519", "free_delivery": "yes", "min_rating": "4.8"})
    assert loaded["min_price"] == 100000 and loaded["category"] == "50001519" and loaded["free_delivery"] is True
    assert loaded["min_rating"] == "4.8"


@pytest.mark.parametrize("params,field", [
    ({}, "query"),
    ({"query": "x", "min_price": "-1"}, "min_price"),
    ({"query": "x", "min_price": "500", "max_price": "100"}, "min_price"),
    ({"query": "x", "category": "123"}, "category"),
    ({"query": "x", "min_rating": "4.5"}, "min_rating"),
    ({"query": "x", "free_delivery": "maybe"}, "free_delivery"),
    ({"query": "x", "page": "2"}, "page"),
])
def test_search_schema_rejects(params, field):
    with pytest.raises(ValidationError) as e:
        schemas.ProductsSearchSchema().load(params)
    assert field in e.value.normalized_messages()


def test_product_schema():
    assert schemas.ProductSchema().load({"product": "10352481064"}) == \
        {"product": "https://smartstore.naver.com/main/products/10352481064"}
    assert schemas.ProductSchema().load({"product": "https://m.brand.naver.com/drbrian/products/4685898105"}) == \
        {"product": "https://brand.naver.com/drbrian/products/4685898105"}
    with pytest.raises(ValidationError) as e:
        schemas.ProductSchema().load({"product": "https://example.com/x/products/1"})
    assert "product" in e.value.normalized_messages()
    with pytest.raises(ValidationError):
        schemas.ProductSchema().load({"product": "10352481064", "url": "x"})   # no sibling params


def test_reviews_schema():
    loaded = schemas.ProductReviewsSchema().load({"product": "10352481064"})
    assert loaded["page"] == 1 and loaded["sort"] == "REVIEW_RANKING"
    loaded = schemas.ProductReviewsSchema().load({"product": "10352481064", "page": "500", "sort": "Recent"})
    assert loaded["page"] == 500 and loaded["sort"] == "REVIEW_CREATE_DATE_DESC"
    loaded = schemas.ProductReviewsSchema().load({"product": "10352481064", "sort": "score_low"})
    assert loaded["sort"] == "REVIEW_SCORE_ASC"
    # oldest / photos / helpful are not sorts the review backend serves
    for bad in ({"product": "10352481064", "page": "501"}, {"product": "10352481064", "sort": "newest"},
                {"product": "10352481064", "sort": "oldest"}, {"product": "10352481064", "sort": "helpful"},
                {"product": "10352481064", "sort": "photos"}):
        with pytest.raises(ValidationError):
            schemas.ProductReviewsSchema().load(bad)


def test_store_schemas():
    assert schemas.StoreSchema().load({"store": "bauato"}) == {"store": "https://smartstore.naver.com/bauato"}
    loaded = schemas.StoreProductsSchema().load({"store": "https://brand.naver.com/samsung"})
    assert loaded == {"store": "https://brand.naver.com/samsung", "list": "popular", "period": "DAILY"}
    loaded = schemas.StoreProductsSchema().load({"store": "bauato", "list": "BEST", "period": "weekly"})
    assert loaded["list"] == "best" and loaded["period"] == "WEEKLY"
    with pytest.raises(ValidationError):
        schemas.StoreProductsSchema().load({"store": "bauato", "list": "new"})
    with pytest.raises(ValidationError):
        schemas.StoreSchema().load({"store": "https://smartstore.naver.com/main/products/1"})


def test_catalog_schema():
    assert schemas.CatalogSchema().load({"catalog": "https://search.shopping.naver.com/catalog/61626354397"}) == \
        {"catalog": "61626354397"}
    with pytest.raises(ValidationError):
        schemas.CatalogSchema().load({"catalog": "abc"})


def test_datalab_window_defaults():
    loaded = schemas.KeywordsRankSchema().load({"category": "50000003"})
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert loaded["end_date"] == yesterday and loaded["start_date"] < loaded["end_date"]
    assert loaded["period"] == "date" and loaded["page"] == 1 and loaded["device"] is None and loaded["age"] is None
    loaded = schemas.KeywordsRankSchema().load({"category": "50000003", "period": "weekly", "device": "mobile",
                                                "gender": "female", "age": "20, 30", "page": "25",
                                                "start_date": "2026-01-01", "end_date": "2026-03-01"})
    assert loaded["period"] == "week" and loaded["device"] == "mo" and loaded["gender"] == "f"
    assert loaded["age"] == ["20", "30"] and loaded["page"] == 25


@pytest.mark.parametrize("params,field", [
    ({}, "category"),
    ({"category": "50000003", "page": "26"}, "page"),
    ({"category": "50000003", "start_date": "2026-10-01", "end_date": "2026-09-01"}, "start_date"),
    ({"category": "50000003", "start_date": "2016-01-01"}, "start_date"),
    ({"category": "50000003", "end_date": "2099-01-01"}, "end_date"),
    ({"category": "50000003", "age": "70"}, "age"),
    ({"category": "50000003", "device": "tablet"}, "device"),
    ({"category": "50000003", "start_date": "2026/01/01"}, "start_date"),
    ({"category": "0"}, "category"),
])
def test_datalab_rank_rejects(params, field):
    with pytest.raises(ValidationError) as e:
        schemas.KeywordsRankSchema().load(params)
    assert field in e.value.normalized_messages()


def test_keyword_trend_and_categories():
    loaded = schemas.KeywordsTrendSchema().load({"keyword": "아이폰", "category": "50000003"})
    assert loaded["keyword"] == "아이폰" and loaded["category"] == "50000003"
    with pytest.raises(ValidationError):
        schemas.KeywordsTrendSchema().load({"category": "50000003"})
    assert schemas.CategoriesTrendSchema().load({"category": "50000003"})["category"] == "50000003"
    assert schemas.CategoriesListSchema().load({}) == {"category": "0"}
    assert schemas.CategoriesListSchema().load({"category": "50000003"}) == {"category": "50000003"}
    with pytest.raises(ValidationError):
        schemas.CategoriesListSchema().load({"category": "x"})
