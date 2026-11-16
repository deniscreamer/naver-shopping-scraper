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
    # the junior scroll run, 2026-11-14/15: underwear, sneakers, a bag and a kit filed under junior clubs (withdrawn)
    ("주니어 스포츠브라 중학생 여아용 편안한 브라", "title:not_golf"),                       # 13726226449
    ("주니어 여아팬티 삼각 주니어속옷 초등학생 면스판 순면 편한 팬티 여아용", "title:not_golf"),  # 13734339115
    ("주니어 브라런닝 초등학생 런닝 주니어런닝 브라캐미솔 여아 인견 런닝나시", "title:not_golf"),  # 13727592833
    ("아디다스 그랜드코트 3.0 주니어 로우컷 캐주얼 운동화 (일본직배송)", "title:not_golf"),       # 13825101750
    ("학생 주니어 방과 후 취미 레슨 교육용 장비 자세 교정 기초", "title:not_golf"),              # 13829360410
    ("핑 Prodi G 주니어 가방 / 프로디 지", "title:bag_only"),                               # 12941462550
    ("브라운 주니어 골프채 세트 드라이버 아이언 퍼터", None),                               # brown stays
    ("PING 프로디지 주니어 아이언 7번", None),
    ("윌슨 주니어 프로파일 JGI 골프클럽 패키지 세트 스탠드백", None),
])
def test_junior_apparel_shoes_and_kits_are_left_out(title, code):
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


@pytest.mark.parametrize("title, code", [
    # 50002670 irons, sold as women's iron sets (the owner, 2026-11-14): 338 titles of 6 searches that day, 86 out
    ("ITOBORI 이토보리 25 아이언 헤드 VR.4 4세대 아이언헤드", "title:parts"),
    ("ZESTAIM 라제스타임 THE 레이디스 아이언 헤드 6-PW,G(6i)", "title:parts"),
    ("던롭 젝시오 13 5번 아이언 단품 여성용", "title:single"),
    ("테일러메이드 P790 여성용 5번단품 아이언 투어AD 50L", "title:single"),
    ("온오프 레디 아이언 단품 여성 경량 LP-425I", "title:single"),              # 425I is a model, not 5 irons
    ("[정식대리점] 젝시오14 여성용 아이언 단품 5번 낱개", "title:single"),
    ("주문제작 포틴 TB3 포지드 카본 낱개아이언 여성용 블랙 새틴 PA TOUR AD 50", "title:single"),
    ("재고보유 당일출고가능 ALL-NEW PXG 0211 DC 7아이언세트 남성 병행수입", "title:mens"),
    ("던롭 젝시오 13 레이디스 아이언 7개 세트 2024년 여성용", None),
    ("다이와 온오프 LP 425 아이언 세트 2025년 여성용 병행 AS보증 6개", None),
    ("혼마 골프 베레스 08 아이즈 aizu 여성 아이언 7개세트 카본 샤프트", None),   # 샤프트 stays
    ("젝시오 XXIO 12 블루 아이언 레이디스 5개세트 MP1200L블루 L샤프트", None),
    ("미즈노 JPX925 포지드 아이언 8개 세트 2024년", None),                     # no gender: placement holds it
    ("남녀공용 경량 카본 아이언 7개 세트", None),
    ("7아이언세트 단품 여성 카본", None),
    ("[중고] 중고 로마로 레이 알파 여성용 7아이언세트 블루 투어 AD 40 L 유니스골프", "title:used"),   # 11658140244
    ("젝시오 13 여성 아이언 리퍼 7개 세트", "title:used"),
    ("초중고 여성 입문용 아이언 7개 세트", None),
    ("중고급자 여성 아이언 세트 7i", None),
])
def test_iron_sets_leave_heads_singles_and_mens_out(title, code):
    screen = Screen("50002670", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002670", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


@pytest.mark.parametrize("title, code", [
    # 50002783 wedges, sold as wedge sets (the owner, 2026-11-15): 670 titles of 골프 웨지 세트 that day, 187 out
    ("[본사] 미라이골프 SUMMIT 웨지헤드 48도 52도 56도 60도", "title:parts"),
    ("단조 골프 웨지 세트 50 52 54 56 58 60도 헤드만", "title:parts"),
    ("발도 코르사 골프 웨지 세트 50 58도 단조 실버 샌드 (샤프트 미포함)", "title:parts"),
    ("골프웨지커버 웨지보호캡 골프가방 낱개골프채커버 골프채보호커버 쓱템", "title:accessory"),
    ("남녀공용 웨지 그루브 샤프너 골프 클럽 Blue", "title:accessory"),
    ("PGM 골프 클럽 세트 및 리그리핑 키트 웨지 Silver", "title:accessory"),
    ("골프 웨지 세트 초보자용 스키 팁 커넥터, 귀여운 감성 클립 훈련 보조기, 겨울 웨지", "title:accessory"),
    ("마쓰이 치퍼 701C 골프웨지 골프클럽", "title:chipper"),
    ("중고미즈노 JPX850 포지드 GS번 카본55R 웨지세트 (50088.85)", "title:used"),
    ("GUTE 에어 웨지 백 펌프 3팩 상업용 팽창식 도구", "title:not_golf"),
    ("스틸 해머 웨지 세트 목공용 클로 10개입", "title:not_golf"),
    ("미즈노 JPX925 핫메탈 프로 웨지 단품", "title:single"),
    ("타이틀리스트 보키 SM10 그라인드 골프 웨지 52도 12도 BV105 5212F", "title:single"),
    ("윅스 웨지 백스핀 잘먹는 비공인웨지 남성용", "title:single"),                 # 웨지백스핀 is no air wedge bag
    ("요이치 스틸 115S 525660도 웨지세트 커버없음", None),                         # 커버없음 is a set's word
    ("테일러메이드 MG5 웨지 SB 세트 3개 NS PRO 950 NEO S", None),
    ("1+1 [테일러메이드코리아] 밀드그라인드4 웨지 MG4 세트 (52도+56도) 남성 여성", None),
    ("커클랜드 시그니처 3피스 웨지 골프 세트", None),
    ("BYBOMYA 단조 골프 웨지 50 52 54 56 58 60 개별 또는 세트", None),
    ("미즈노골프 세트 왼손 미즈노 52도 56도 웨지 골프채 좌타 왼손잡이 단조헤드 샌드 갭", None),
])
def test_wedge_sets_leave_heads_accessories_and_singles_out(title, code):
    screen = Screen("50002783", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002783", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


@pytest.mark.parametrize("title, code", [
    # 2026-11-15, the visual lenses on 661 published junior sets: real titles of published misfits (left out now) ...
    ("F형 바 클램프 목공 고정 공구 DIY 작업 목재 접합 장비 바이스 12in", "title:not_golf"),
    ("집소 골프채 세트 놀이쿠션 유치원블록 어린이집블럭", "title:not_golf"),
    ("PGM 골프 주니어 플라스틱 교육용 연습용 클럽 골프채 조기 7번", "title:toy"),
    ("SDR - 골프채 어린이 소프트골프/안전한 실리콘", "title:toy"),
    ("SDR - 골프채 주니어용 드라이버/탄성, 반발력우수", "title:toy"),
    ("스포츠게임 어린이용 미니골프 클럽 골프채 체육시설 주니어용 체육센터 체육놀이", "title:toy"),
    ("키드짐 초등용 골프채 70cm 아이언 3번 클럽 어린이용", "title:toy"),
    ("어린이 골프채 초등용 70cm 퍼터1 공2개", "title:toy"),
    ("초등 아동 골프 59cm 유아 어린이 골프채 학생 어린이 골프 아동 골프채", "title:toy"),
    ("여성 골프클럽 풀세트 주니어겸용 경량 아이언 우드 드라이버 맞춤로고 가방포함", "title:adult"),
    ("골프 클럽 남성 풀세트 티타늄 합금 주니어 조합 중급자 골프채", "title:adult"),
    ("PGF 랩스 골드 TP BG77 남녀 골프 클럽 패키지 세트 14피스 플렉스 레귤러", "title:adult"),
    ("아스파이어 X1 여성용 완비 오른손잡이 골프 클럽 세트 일반 및 쁘띠 여성 Petite", "title:adult"),
    ("클리블랜드 골프 T 프레임 USA 70 퍼터 Right 35 Inches", "title:adult"),
    ("클리블랜드 골프 HB 소프트 밀드 퍼터", "title:adult"),
    ("Q 2세대 조절식 골프 클럽스틸 샤프트 - 내구성이 뛰어난 2부 여행 4 퍼터에서 60 Right", "title:adult"),
    # ... and real junior clubs the new words must not touch (the near misses measured that day)
    ("PGM 골프 클럽 어린이 아동 주니어 교육용 훈련용 연습용 입문용 조기 학습", None),
    ("여성용 핑크 세트 골프채 7번아이언 주니어골프채 연습용 카본 클럽 샤프트", None),
    ("주니어 골프클럽 세트 유치원 초등학생 입문용", None),
    ("스탠다드 주니어 골프 클럽 세트 3-5세", None),                 # sdr only as its own latin word
])
def test_junior_toys_adult_sets_and_not_golf_seen_on_the_sheets_are_left_out(title, code):
    screen = Screen("50002787", namespace="fairwardgolf")
    got = screen.check({"name": title, "category_id": "50002787", "product_id": "1",
                        "store": {"channel_no": "1"}})
    assert (got if got and got.startswith("title:") else None) == code
