"""Offline tests for the listing screen (listing_filter.py): the stop words as the harvester has them, the reason
order, the source key. Rows are the committed listing fixture's (a live listing, 2026-11-05).

    .venv/bin/python -m pytest scripts/test_listing_filter.py -q
"""
import json
import os

import pytest

from listing_filter import REASONS, Screen, load_exclusions, normalize, source_key, stop_word

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RULES = load_exclusions()["universal"]["rules"]


def rows():
    with open(os.path.join(FX, "listing_products.json"), encoding="utf-8") as f:
        out = json.load(f)["results"]
    assert all(r["store"]["channel_no"].isdigit() for r in out)       # captured live 2026-11-05
    return out


@pytest.mark.parametrize("name", [
    "골프채 풀세트 대여", "렌탈 골프클럽", "골프채렌털", "랜탈 풀세트", "골프 랜털", "골프채 렌트", "풀세트 랜트",
    "렌터카 아님 렌터", "골프채 임대", "ゴルフ レンタル", "Golf Rental set", "RENTALS ok", "rent a club",
    "１일 렌탈",                                      # full-width digit: NFKC makes it 1
])
def test_rental_names(name):
    assert stop_word(name, RULES) == "rental"


@pytest.mark.parametrize("name", [
    "여성용 풀세트 대여성",        # 대여 followed by 성
    "다섯 대여섯개",               # followed by 섯
    "3대여 세트",                  # preceded by a digit
    "휴대여행 가방",               # 휴대 + 여행
    "무료대여 이벤트 아님",         # preceded by 무료
    "토렌트 브렌트 플렌트",         # 렌트 after 토 / 브 / 플
    "클라렌트 드라이버",            # after 클라
    "플랜트 그랜트",               # 랜트 after 플 / 그
    "플렌터 화분",                 # 렌터 after 플
    "게임대 타임대 레임대",          # 임대 after 게 / 타 / 레
    "parental control", "current", "rentable",       # latin words only
    "남성 골프채 풀세트",
])
def test_not_rental(name):
    assert stop_word(name, RULES) is None


def test_reason_order_and_counts():
    data = rows()
    base = next(r for r in data if not r["is_ad"] and r["category_id"] == "50002788")
    key = source_key(base, "fairwardgolf")
    assert key == f"fairwardgolf:naver:{base['store']['channel_no']}:{base['product_id']}"
    screen = Screen("50002788", "fairwardgolf")
    assert screen.reason(base) is None
    cases = {
        "sponsored": {**base, "is_ad": True, "name": "렌탈"},             # the first reason wins
        "title_unavailable": {**base, "name": "  "},
        "rental": {**base, "name": base["name"] + " 렌탈", "category_id": "1"},
        "category_mismatch": {**base, "category_id": "50000029"},       # a parent category is not the leaf
        "key_unavailable": {**base, "store": {**base["store"], "channel_no": None}},
    }
    for code, row in cases.items():
        assert screen.reason(row) == code, code
    screen.set_published([key])
    assert screen.reason(base) == "already_published"
    screen.set_published([])
    screen.deferred = {key}
    assert screen.reason(base) == "deferred"
    assert set(screen.counts) <= set(REASONS) and sum(screen.counts.values()) == 7


def test_ads_kept_when_the_file_says_so():
    exclusions = load_exclusions()
    exclusions["universal"]["excludeSponsored"] = False
    row = {**rows()[0], "is_ad": True, "category_id": "50002788"}
    assert Screen("50002788", "fairwardgolf", exclusions=exclusions).check(row) is None


def test_normalize():
    assert normalize("ＲＥＮＴＡＬ") == "rental"


def test_the_harvester_file_as_it_is():
    data = load_exclusions()
    assert data["schemaVersion"] == "fairwardgolf-listing-exclusions/v1" and data["universal"]["excludeSponsored"]
    [rule] = data["universal"]["rules"]
    assert rule["code"] == "rental" and len(rule["tokens"]) == 13


@pytest.mark.parametrize("name", [                     # live listing 2026-11-05, 여성 골프채 풀세트
    "마제스티 프레스티지오 로얄 시니어 신형 여성 골프채 풀세트 제주도 골프채 대여 렌탈",
    "[제주골프채대여,렌탈] 젝시오11 여성 풀세트",
])
def test_live_rental_names(name):
    assert stop_word(name, RULES) == "rental"
