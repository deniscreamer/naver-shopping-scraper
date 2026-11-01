"""Offline: the saved real API responses (fixtures/*.json, captured live
2026-11-01, lists trimmed to 5 items) match the types in naver_types.py.

Strict both ways: a missing required key, an unknown key or a wrong type
fails. When the server changes a response shape, refresh the fixture and the
type together.

    .venv/bin/python -m pytest scripts/test_naver_types.py -q
"""
import json
import os
import types
import typing

import pytest

import naver_types as T

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

FIXTURES = {
    "health.json": T.Health,
    "products_search.json": T.SearchResult,
    "products_count.json": T.CountResult,
    "products_details.json": T.ProductDetails,
    "products_reviews.json": T.ReviewsPage,
    "stores_details.json": T.StoreDetails,
    "stores_products.json": T.StoreProducts,
    "catalogs_reviews.json": T.CatalogReviews,
    "categories_list.json": T.CategoryList,
    "keywords_rank.json": T.KeywordRankPage,
    "keywords_trend.json": T.KeywordTrend,
    "categories_trend.json": T.CategoryTrend,
    "listing_job.json": T.ListingJob,
    "listing_products.json": T.ListingProductsPage,
}


def mismatches(value, tp, path="$"):
    """-> a list of 'path: problem' strings ([] when value matches tp)."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if tp is typing.Any:
        return []
    if origin in (typing.Union, types.UnionType):
        tries = [mismatches(value, a, path) for a in args]
        return [] if any(not t for t in tries) else min(tries, key=len)
    if origin is typing.Literal:
        return [] if value in args else [f"{path}: {value!r} not in {args}"]
    if tp is type(None):
        return [] if value is None else [f"{path}: expected null, got {type(value).__name__}"]
    if typing.is_typeddict(tp):
        if not isinstance(value, dict):
            return [f"{path}: expected object {tp.__name__}, got {type(value).__name__}"]
        hints = typing.get_type_hints(tp)
        out = [f"{path}.{k}: missing (required in {tp.__name__})" for k in tp.__required_keys__ if k not in value]
        out += [f"{path}.{k}: not in {tp.__name__}" for k in value if k not in hints]
        for k, v in value.items():
            if k in hints:
                out += mismatches(v, hints[k], f"{path}.{k}")
        return out
    if origin is list:
        if not isinstance(value, list):
            return [f"{path}: expected list, got {type(value).__name__}"]
        return [m for i, v in enumerate(value) for m in mismatches(v, args[0], f"{path}[{i}]")]
    if origin is dict:
        if not isinstance(value, dict):
            return [f"{path}: expected dict, got {type(value).__name__}"]
        return [m for k, v in value.items() for m in mismatches(v, args[1], f"{path}.{k}")]
    if tp is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif tp is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, tp)
    return [] if ok else [f"{path}: expected {getattr(tp, '__name__', tp)}, got {type(value).__name__} {value!r:.60}"]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_matches_type(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        data = json.load(f)
    assert mismatches(data, FIXTURES[name]) == []


def test_every_fixture_is_checked():
    assert sorted(f for f in os.listdir(FX) if f.endswith(".json")) == sorted(FIXTURES)


def test_checker_catches_problems():
    class Box(typing.TypedDict):
        n: int
        s: str | None
    assert mismatches({"n": 1, "s": None}, Box) == []
    assert mismatches({"n": "1", "s": None}, Box)
    assert mismatches({"n": 1}, Box)
    assert mismatches({"n": 1, "s": "x", "extra": 2}, Box)
