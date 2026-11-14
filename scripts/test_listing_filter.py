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
    screen = Screen("50002788", "fairwardgolf", exclude_sponsored=True)
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


def test_ads_kept_by_default():
    # the owner, 2026-11-06: an ad card is a product like the others, though the harvester file says exclude
    row = {**rows()[0], "is_ad": True, "category_id": "50002788"}
    assert load_exclusions()["universal"]["excludeSponsored"]
    assert Screen("50002788", "fairwardgolf").check(row) is None
    assert Screen("50002788", "fairwardgolf", exclude_sponsored=True).check(row) == "sponsored"
    assert Screen("50002788", "fairwardgolf").check({**row, "name": row["name"] + " 렌탈"}) == "rental"


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


@pytest.mark.parametrize("category, title, code", [
    # the listings of 2026-11-11 (listing_title_rules.json): what the category's section does not sell
    ("50002787", "어린이골프채 아기골프채 안전인증 교구 아이언 퍼터 우드 클럽", "title:toy"),
    ("50002787", "키즈스포츠 KC안전 초등용 아이언 7번 스틱 골프 70cm 유아골프 신체운동", "title:toy"),
    ("50002787", "골프채 장난감 세트 실내 연습 야외 운동 abs 플라스틱", "title:toy"),
    ("50002787", "주니어 골프 전용 장갑 어린이 반양피 골프장갑 (왼손에착용)1장", "title:glove"),
    ("50002787", "[A GRIND]에이그라인드주니어 아이언 헤드", "title:parts"),
    ("50002787", "래핑차일드 핑 G440 MAX 드라이버 S, 9도", "title:adult"),
    ("50002787", "US키즈골프 RS3 스윙 스피드 트레이너", "title:training_aid"),
    ("50002788", "SMB 프리미엄 파크 골프 풀세트", "title:park_golf"),
    ("50002788", "2025 핑 G440 MAX 풀세트 3종세트 드라이버 우드 유틸 9도 3번R", "title:woods_only"),
    # what fits stays
    ("50002787", "어린이 골프채 7번+양손 장갑", None),                         # a club with a glove
    ("50002787", "주니어 골프 세트 골프풀 아이언 헤드커버", None),              # 헤드커버 is not a loose head
    ("50002787", "안전성시험통과 주니어골프채 퍼터 어린이 골프클럽 아동 초등학생", None),
    ("50002787", "캘러웨이 XJ 주니어 골프채 풀세트 2026", None),
    ("50002788", "테일러메이드 13종세트 남성 골프채 풀세트", None),             # 13종세트 is no 3종세트
    ("50002788", "남성 골프채 풀세트 초보", None),
    ("50002789", "어린이 장난감 골프", None),                                  # a category without rules
])
def test_category_title_rules(category, title, code):
    screen = Screen(category, namespace="fairwardgolf")
    row = {"name": title, "category_id": category, "product_id": "1", "store": {"channel_no": "2"}}
    assert screen.check(row) == code


@pytest.mark.parametrize("title, code", [
    ("주니어골프백(스탠드형) 어린이 골프가방", "title:bag_only"),           # 314400655, published then withdrawn
    ("록스프랜드 주니어 7번아이언 학교/단체 세트(10개) 아화", "title:group_pack"),   # 10348222504, withdrawn
    ("전선 케이블 망 메쉬 인입 풀링 그립 2눈 경량 중량 메쉬그립", "title:not_golf"),   # 13753814944
    ("주니어 골프채 단체용 7번 아이언 10개", "title:group_pack"),
    ("US키즈골프 UL7 주니어 스탠드 골프백", "title:bag_only"),
    ("재미있는 주니어 골프세트 스탠드 골프백 골프채 3종", None),           # a set with a bag stays
    ("어린이 골프채 3종 + 골프가방 세트 주니어 퍼터 아이언 드라이버 아동 캐디백", None),
    ("PGM 주니어 어린이 골프채 골프클럽 세트 가방포함", None),
])
def test_a_junior_bag_alone_is_left_out(title, code):
    screen = Screen("50002787", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002787", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


@pytest.mark.parametrize("title, code", [
    # the owner, 2026-11-14 (50002788, lenient: only what is certainly not a set; the doubtful ones are published
    # and reviewed afterwards, review_suspects.py). Past titles of the category:
    ("IMIKEYA 미니 골프 카트: 다이 캐스트 메탈 모델 골프 카트 미니 1:20 스케일 카트 다이캐스트 모델 카트", "title:accessory"),
    ("어린이용 발광 피클볼 라켓 세트 야간용 초보자용 라켓 Type-C 충전", "title:accessory"),
    ("입문용 성인 골프채 접이식 실내 골프채 좌타 남성", "title:folding"),          # 13464713764, one club, 27,800 KRW
    ("접이식 성인용 골프채 가족 휴대용 골프채 남성 여성", "title:folding"),        # 13742222509, 풀세트구성 퍼터
    # made up: an accessory alone
    ("레이저 골프 거리측정기 고급형", "title:accessory"),
    ("투어 골프그립 교체용 남성", "title:accessory"),
    # what stays: junior sets (no other job collects them: the review lists them), balls (a set given with balls
    # may name no set word), a set that comes with an accessory or a folding item, an adult word, a used set
    ("캘러웨이 XJ3 주니어 골프채 풀세트 7개 캐디백 포함 어린이용", None),
    ("Tour Edge Hot Launch HLJ Junior Sets RIGHT HAND Kids GREEN SET Ages 710yrs", None),
    ("기가골프 R3 주니어 풀세트 골프백 포함 9~13세", None),
    ("골프공 3구 세 박스 비거리 골프볼", None),
    ("핑 G430 드라이버 우드 아이언 퍼터 + 골프공", None),
    ("혼마 남성 골프채 풀세트 + 접이식 카트 증정", None),
    ("노션몰 뛰어난접착력 고급 골프납테이프 훅 슬라이스 뜬볼 방지, 30개, 5 X 1.3, GL20 납테이프", None),  # to the review
    ("혼마 베레스 남성 골프채 풀세트 + 골프공 증정", None),
    ("젝시오 13 풀세트 거리측정기 사은품", None),
    ("테일러메이드 풀셋 캐디백 골프장갑 포함", None),
    ("중고 그립교체 완료 핑 G430 풀세트", None),
    ("AS가능/ 여성/ 왼손/ 테일러메이드/ 풀세트 골프채 좌타 여자 L강도 레프티 캐디백 레이디 골프 쥬니어 주니어", None),
    ("골프 퍼터, 남성용 투웨이 여성 오른손/왼손잡이, 어린이용 미니 클럽 세트, 골프공 2개", None),
    ("성인 및 주니어용가능 입문 골프채 풀세트", None),
    ("야마하 인프레스 남성 골프채 풀세트 10개", None),
])
def test_the_lenient_rules_of_full_sets(title, code):
    screen = Screen("50002788", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002788", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


def test_published_full_set_titles_pass_the_screen():
    """2026-11-14: published 50002788 titles (a sample; the offline study: none left out but the three folding clubs)."""
    screen = Screen("50002788", namespace="fairwardgolf")
    for title in ("[클럽] 스크린 전용 1+1 남성용 야마모토 쇼군 풀세트 12피스 -연습용 라운딩 골프용품",
                  "요넥스 뉴 이존 3.0 엘리트+ PRGR 고반발 드라이버 조합 여성골프채풀세트",
                  "정품 요넥스 뉴 이존엘리트 3.0 여성 11개구성 여성 입문골프채풀세트"):
        assert screen.check({"name": title, "category_id": "50002788", "product_id": "1",
                             "store": {"channel_no": "2"}}) is None
