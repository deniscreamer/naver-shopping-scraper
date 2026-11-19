"""Offline: the golden prepared products (fixtures/prepared/, test_prepared_golden.py) match transform.Prepared and
shop_types.PreparedProduct: no unknown key, no wrong type (test_naver_types.mismatches), and a built product has
every key of PreparedProduct but the one run_transform adds (description_images_text). Their collected lines
(fixtures/collected/, prepare's input) match shop_types.CollectedLine, strictly.

    .venv/bin/python -m pytest scripts/test_shop_types.py -q
"""
import json
import os

import pytest

from shop_types import CollectedLine, PreparedProduct
from test_naver_types import mismatches
from transform import Prepared

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
PREPARED, COLLECTED = os.path.join(FX, "prepared"), os.path.join(FX, "collected")
NAMES = sorted(n for n in os.listdir(PREPARED) if n.endswith(".json"))
RUN_TRANSFORM_ADDS = {"description_images_text"}
CATEGORY_ADDS = {"composition_ko"}                 # CategoryRules.composition only (knit cardigans, 2026-11-19)


def test_there_are_golden_products():
    assert len(NAMES) >= 20
    assert sorted(n for n in os.listdir(COLLECTED) if n.endswith(".json")) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_collected_line_matches_the_type(name):
    with open(os.path.join(COLLECTED, name), encoding="utf-8") as f:
        assert mismatches(json.load(f), CollectedLine) == []


@pytest.mark.parametrize("name", NAMES)
def test_golden_prepared_matches_the_types(name):
    with open(os.path.join(PREPARED, name), encoding="utf-8") as f:
        prepared = json.load(f)
    assert mismatches(prepared, Prepared) == []
    assert set(prepared["product"]) == set(PreparedProduct.__annotations__) - RUN_TRANSFORM_ADDS - CATEGORY_ADDS


def test_an_image_text_flag_and_an_empty_product_match():
    assert mismatches({}, PreparedProduct) == []                      # collect_incomplete
    flag = {"state": "translated", "ko": "translation/1/description_images.ko.json",
            "en": "translation/1/description_images.en.json", "blocks": 3, "chars": 120, "sha256": "ab",
            "dropped": {"promo": 2}}
    assert mismatches({"description_images_text": flag}, PreparedProduct) == []
    assert mismatches({"description_images_text": {**flag, "blocks": "3"}}, PreparedProduct)
