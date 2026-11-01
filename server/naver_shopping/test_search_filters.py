"""Offline tests for the search filter params sent to ns-portal.

    python -m pytest server/naver_shopping/test_search_filters.py -q

The category depth comes from DataLab (api.categories_list); it is stubbed
here, so nothing goes to the network.
"""
import pytest

from naver_shopping import api as A
from naver_shopping.fetch import NaverNotFound

LEVELS = {"50000007": 1, "50000029": 2, "50001102": 3, "50002788": 4}


@pytest.fixture(autouse=True)
def levels(monkeypatch):
    def categories_list(category):
        if category not in LEVELS:
            raise NaverNotFound(f"category {category} not found")
        return {"id": category, "level": LEVELS[category]}
    monkeypatch.setattr(A, "categories_list", categories_list)


@pytest.mark.parametrize("category,expected", [
    ("50000007", "0150000007"), ("50000029", "0250000029"),
    ("50001102", "0350001102"), ("50002788", "0450002788"),
])
def test_category_prefix_is_depth(category, expected):
    assert A._filters({"category": category})["categoryIds"] == expected


def test_root_category_is_no_filter():
    assert "categoryIds" not in A._filters({"category": "0"})
    assert "categoryIds" not in A._filters({"category": None})


def test_unknown_category_is_not_found():
    with pytest.raises(NaverNotFound):
        A._filters({"category": "50099999"})


def test_other_filters_unchanged():
    out = A._filters({"category": "50002788", "min_price": 100000, "free_delivery": True})
    assert out == {"price": "100000|9999999999", "categoryIds": "0450002788", "isFreeDelivery": True}
