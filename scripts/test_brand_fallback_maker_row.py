"""Offline tests for brand_fallback.described: a Brand row with a bullet or the label 브랜드 이름, and a bare-number
brand that takes the maker's row (the owner's wedge-set review, 2026-11-16). Real descriptions in
scripts/fixtures/brand_rows/<product id>.json.

    .venv/bin/python -m pytest scripts/test_brand_fallback_maker_row.py -q
"""
import json
import os

import pytest

import brand_fallback as B

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "brand_rows")


def _real(pid: str) -> dict:
    with open(os.path.join(HERE, f"{pid}.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("pid,brand", [
    ("13370257430", "69 Golf"),     # "- Brand : 69", "- Manufacturer : 69 Golf" (specs' 브랜드 / 제조사: "69")
    ("13016152694", "69 Golf"),     # "Brand Name | 69", "Manufacturer | 69 Golf" (no specs rows)
    ("12178085899", "pgm"),         # "브랜드 이름 | pgm" (published as Fairward Golf)
])
def test_real_descriptions_name_the_brand(pid, brand):
    d = _real(pid)
    assert B.described(d["description_ko"]) == [brand]
    assert B.decide(d["title_ko"], None, [], [], [], d["description_ko"]) == (brand, "description_row", [])


def test_a_bullet_and_the_label_brand_name_in_korean():
    assert B.described("- Brand : WENGH") == ["WENGH"]
    assert B.described("• 브랜드 이름 : MAZEL") == ["MAZEL"]
    assert B.described("브랜드이름 | pgm") == ["pgm"]
    assert B.described("브랜드명: 야마토") == ["야마토"]


@pytest.mark.parametrize("text", [
    "- Brand new design: a forged face",                    # not a label
    "브랜드 이름은 상세페이지 참조",                                 # no row separator
    "- 브랜드 이름 | 골프",                                       # no firm
    "Brand | 69",                                            # a bare number, no maker
    "Brand Name | 69\nManufacturer | Shenzhen Sports Co",    # the maker does not start with the number
    "Brand Name | 69\nManufacturer | 690 Golf",              # another number
    "Brand Name | 69\nManufacturer | 69 cm",                 # the maker's row is a size
    "Brand Name | 69\nManufacturer | 69",                    # the maker is the bare number too
    "Brand Name | 69\nGolf Club Loft | 69 Golf",             # not the maker's row
])
def test_these_name_no_brand(text):
    assert B.described(text) == []


def test_a_named_brand_keeps_its_own_name_over_the_maker():
    assert B.described("Brand | WENGH\nManufacturer | WENGH Golf Ltd") == ["WENGH"]
    assert B.described("Brand Name | 69\nManufacturer | 69 Golf\nBrand | 69 Golf") == ["69 Golf"]   # once
    assert B.described("제조사 | 69 Golf\n브랜드 | 69") == ["69 Golf"]                               # either order


@pytest.mark.parametrize("word", ["NONE", "none", "N/A", "Others", "다른 사람들"])
def test_a_translated_none_is_no_brand(word):
    # 13024224352 "브랜드 이름 | NONE", 13024206977 "브랜드 이름 | 다른 사람들" (2026-11-16)
    assert B.clean(word) is None
    assert B.described(f"브랜드 이름 | {word}\nBrand Name | GAMEN GOLF") == ["GAMEN GOLF"]     # 13024241901


def test_a_row_brand_takes_the_dictionary_spelling():
    # "브랜드 이름 | pgm" where the shop's PGM products say PGM: one spelling per brand in the shop. Intended for rows
    # read before as well (2026-11-16, measured: pgm -> PGM on 7, WILSON -> Wilson on 3, HATACHI, yamato; their vendor
    # spelling changes and translate asks for the title again)
    d = _real("12178085899")
    assert B.decide(d["title_ko"], None, [], [], ["피지엠", "PGM"], d["description_ko"]) == (
        "PGM", "description_row", [])
    assert B.decide("웨지 세트", None, [], [], ["Lazrus"], "Brand | LAZRUS GOLF") == (
        "LAZRUS GOLF", "description_row", [])                               # another name: its own
    assert B.decide("웨지 세트", None, [], [], ["핑"], "Brand | 핑") == ("핑", "description_row", [])
    assert B.decide("주니어 세트", None, [], [], ["Wilson"], "Brand | WILSON") == ("Wilson", "description_row", [])
