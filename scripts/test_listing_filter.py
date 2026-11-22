"""Offline tests for the listing screen (listing_filter.py): the stop words as the harvester has them, the reason
order, the source key. Rows are the committed listing fixture's (a live listing, 2026-11-05).

    .venv/bin/python -m pytest scripts/test_listing_filter.py -q
"""
import json
import os

import pytest

from listing_filter import REASONS, Screen, load_exclusions, normalize, source_key, stop_word, title_rule

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
    # 칩퍼 / Chipper (KVV 13162968497, review 2026-11-17); 칩 퍼터 / 칩 퍼팅 are other words
    ("골프 웨지 KVV 프리미엄 샌드 남녀용 455560도 피칭 및 칩퍼 - 토너먼트 경기 적합 숏게임 향상 3-Chipper Set",
     "title:chipper"),
    ("Golf Chipper Wedge 35 Degree", "title:chipper"),
    ("칩 퍼터 겸용 골프 웨지 세트 52 56", None),
    ("칩퍼팅 연습 웨지 세트 52 56 60", None),
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
    # 50002784 chippers (the owner, 2026-11-18): 1,260 titles of 골프 치퍼 and 치퍼 that day (price slices), 482 out,
    # every word measured on all of them with no chipper hit
    ("정원 분쇄기 치퍼 나이프 교체품 부품용", "title:not_golf"),
    ("포레스트 마스터 나뭇가지 파쇄기 FM6DD 우드치퍼 엔진작동", "title:not_golf"),
    ("NKS 후렉스치퍼 12mm F-2 31310221 Air Flux Chipper", "title:not_golf"),
    ("프라이 커터 다기능 야채 치퍼 스테인레스 스틸 감자 25/49 홀 블레이드 주방 도구", "title:not_golf"),
    ("포커칩 100개 19mm 포커 칩 카운트 빙고 게임 카드 게임용 플라스틱", "title:not_golf"),
    ("여성용 3cm 실리콘 키높이 깔창 쿠션 아치깔창 치퍼 실리콘깔창 뒤꿈치깔창", "title:not_golf"),
    ("g6662 CHIPPER 니트 WOMEN(M)", "title:apparel"),
    ("남성 가을 겨울 다운 패딩 치퍼 조끼 남자 빅사이즈 5XL 민소매 자켓 간절기 아우터", "title:apparel"),
    ("쟈크뮈스 드 님 플리퍼 데님 탑 SHW00577AD00072 TP460796065", "title:apparel"),
    ("스릭슨 아담스ADAMS 드라이빙 아이언 치퍼 헤드커버", "title:accessory"),
    ("골프 치퍼 페이스 방향 지시기 숏게임 훈련 도구", "title:accessory"),
    ("HD 제품 골프 치퍼 및 퍼터 스탠드 힌지 클럽 샤프트가 지면에 닿지 않도록", "title:accessory"),
    ("PGM 말렛 골프 퍼터 86.4cm 34인치 남녀공용 오른손용", "title:putter"),
    ("골프 양면 퍼터 남녀공용 양손잡이용 탄소강 스테인리스 스틸 샤프트 양손퍼터", "title:putter"),
    ("미즈노 프로 T-1 웨지 [DYNAMIC GOLD HT]", "title:wedge"),
    ("클리블랜드 골프 여자 CBZ 풀페이스 웨지", "title:wedge"),
    ("윌슨 다이나파워 남자 골프 아이언", "title:other_club"),
    ("오딧세이 우타 치퍼 오른손 오디세이 골프 화이트 핫 OG 퍼터 Left", "title:other_club"),
    ("캘러웨이 오른손 치퍼 잡이 캘러웨이골프 패러덤X개별 아이언 Right", "title:other_club"),
    # ... and the chippers the words must not touch (the near misses of that day)
    ("골프 치퍼 양면 왼손잡이 겸용 퍼터 뒤땅 방지 PGM 골프채 칩샷", None),           # a chipper-putter
    ("PGM 웨지 퍼터 결합 골프클럽 치퍼 Chipper 스텐샤프트 35도 양면형 TUG006", None),   # 웨지퍼터 is no zip
    ("SiMSPEC 37도 골프 컷 퍼터 컷과 퍼팅 모두 가능 리거스 클럽 순펑 택배", None),       # 37°: no putter
    ("데이비드 2세대 우디치퍼 치기쉬운 골프채 골프치퍼 칩퍼 어프로치 + 자석티", None),   # 우디치퍼 is no wood chipper
    ("NITRO 왼손잡이 치퍼 왼손 니트로골프 LH 익스트림40", None),                     # 니트로 is no knit
    ("치퍼 플립퍼 뒷땅NO 탑핑NO 완벽한 어프로치", None),                              # 탑핑 is no top
    ("골프치퍼 양면형 연습용 아이언 골프채", None),
    ("남 여 용 좌타 왼손 오른손 양방향 듀얼 양면 퍼팅 골프 채 아이언 클럽 롱 치퍼 칩퍼", None),
    ("무츠미혼마 골프 치퍼 러닝 어프로치 피치 앤 런 아이언형 카본 샤프트", None),
    ("마쓰이 골프채 치퍼 CHIPPER 어프로치 칩샷 웨지 숏게임 헤드커버 701C 34 35", None),  # a cover included
    ("핑 런닝 어프로치 칩W 스틸 치핑 웨지 남성용 Z-Z115", None),                      # a chipping wedge
    ("핑 CHIP W 스틸 웨지 [Z-Z115]", None),
    ("클리블랜드 골프 여자 스마트 솔 풀페이스 웨지", None),
    ("프로기어 R55 여성 웨지 카본 샤프트 55도", None),
    ("오디세이 골프 치퍼 퍼터 웨지 우측 37도 스틸 34.5인치 블랙", None),
    ("클리브랜드 우타 치퍼 오른손 Wmn 스마트솔 풀페이스 S58 GRRH", None),
    # 2026-11-18 review (2,558 titles of 18 queries): chippers the first words dropped ...
    ("PGM 골프채 35도 치퍼 어프로치 칩퍼터 A.TUG071-아이언그레이36", None),            # 아이언그레이 is a colour
    ("PGM 골프채 35도 치퍼 어프로치 칩퍼터 벙커 클럽 TUG071 - 아이언 그레이 양면 컷", None),
    ("PGM 남녀공용 골프 퍼터 950 스틸 클럽 샌드 웨지 큐 드라이버 피칭 치퍼 아이언 TUG019", None),
    ("무각인 치퍼 아이언 미드 그립 치핑웨지 일본 직배송", None),
    ("MAZEL 마젤 골프 칩퍼 36도 개별 5번 아이언 2개 묶음", None),
    ("월드이글 CH809 남성용 웨지 골프 38도 오른손 왼손", None),                       # 38°: no wedge
    ("PGM 골프 칩핑 퍼터 남녀 공용, 거리 및 방향을 제어할 수 있는 짧은 커팅 도구 TUG069", None),
    ("[아화골프]하이브리드 치퍼 GM 고블몬스터 양면 칩퍼 아화", None),                   # 하이브리드 치퍼
    ("오디세이 치퍼 남성 골프 유틸리티 그린 주변 어프로치용 ODYSSEY CHIPPER 2025", None),
    ("Extreme 5 Chipper 우타 치퍼 오른손 잡이 오른손잡이 쁘띠 여성용 410~5", None),     # the agency's own chipper
    ("Intech EZ 왼손잡이 치퍼 왼손 왼손잡이인텍 EZ롤 쁘띠여성용 410인치~53인치", None),
    ("Rife 우타 치퍼 오른손 잡이 RIFE RX5 여성 쁘띠 길이 37도 오른손잡이 뉴 레", None),
    ("투어 엣지 핫 런칭 4 남성 왼손 치퍼 33 Left", None),
    ("골프가방 벤세이어스 M5 치퍼 실버 골프채", None),                                   # a chipper with a bag
    # ... and the misfits it kept
    ("Tangkula 우타 치퍼 오른손 잡이 탕쿨라 910피스 남성 완전 골프채 세트 460c", "title:agency_club"),
    ("ACHETE 오른손 치퍼 잡이 525660도 골프 웨지 골프채 폴 오른손잡이 스틸 전문", "title:agency_club"),
    ("ACHETE 우타 치퍼 오른손 골프채 남여공용 퍼터 알로이 스틸 로드 실리콘 그립 5인치", "title:agency_club"),
    ("마제크 왼손잡이 치퍼 왼손 좌타 Golf 남성 SW 하이브리드 레귤러 플렉스 뉴 유틸리티", "title:agency_club"),
    ("Juggernaut Non Conforming Hi COR cc 티타늄 골프 드라이버 남성용 RO8RB", "title:other_club"),
    ("22735144 ODYSSEY 오디세이 CHIPPER 25 여성 그립 5720425 제조 업체 정품", "title:accessory"),
    ("빅티스 말렛 퍼터 커버 가죽 마그네틱 트 핫 #5 로시 투어 엣지 치퍼 호환", "title:accessory"),
    ("SquEqu 골프공 리트리버 클립 그래버, 골프 끝을 위한 퍼터 그립 피커 픽업 도구", "title:accessory"),
    ("리얼스프링 뒷마당 골프 클럽 세트 게임용 조절 가능한 플라스틱 치핑 공 야외 실내 훈련", "title:accessory"),
    ("랙앤본 여성 파이퍼 울 스커트 Piper Wool Skirt 5999619 161005363", "title:apparel"),
    ("(중고) 지브이골프코리아 치퍼 GV-60Y", "title:used"),
    ("초중고 골프 치퍼 35도", None),                                                  # 초중고 is no condition
    # the review of the 100-chipper scroll (2026-11-18): a loose head, as 50002670's parts
    ("Acer XK Chipper Head 골프 치퍼 헤드만 오른손", "title:parts"),                    # 12409532747
    ("골프 치퍼헤드 35도 단조 오른손", "title:parts"),
    ("PGM 골프치퍼 골프채 샤프트 치퍼 헤드 35도 양면형 TUG006", None),                 # 9291749263: a whole club
    ("마쓰이 치퍼 골프채 헤드커버 포함 어퍼로치 칩샷 치핑 피칭샷 런닝 어프로치 chipper", None),
])
def test_chippers_leave_not_golf_clothes_putters_wedges_and_other_clubs_out(title, code):
    screen = Screen("50002784", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002784", "product_id": "1",
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


@pytest.mark.parametrize("title, code", [
    # 50002797, women's golf knit cardigans (the owner, 2026-11-19): a women's word and a cardigan word required;
    # real titles of the listing 여성 골프 니트 가디건 (category 50002797, the scouts' sample of 2026-11-19)
    ("여자 골프 방풍 니트 가디건 자켓", None),
    ("레노마골프 여성 조직감 방풍 집업 니트 가디건 RWSCN8208", None),
    ("PXG 여성골프웨어 바시티 브이넥 스웨터 니트 가디건", None),              # 스웨터 with a cardigan word stays
    ("캘러웨이 여성 가을 V넥 방풍 가디건", None),                              # no 니트: 가디건 is the knit word
    ("[AK수원점] 테일러메이드  여성 방풍 집업 니트 가디건 TWSCM8131-199", None),
    ("가이거 여성 캐시미어 가디건", None),
    ("울시 여성 UV차단 브이넥 가디건", None),
    ("카멜브리즈 GQ 배색가디건 여성 골프가디건 골프웨어", None),
    ("왁 Cashmere Whole Garment Cardigan WWWAW25731", "title:not_womens"),   # no women's word
    ("캘러웨이 방풍 집업 가디건 CWSC25F401", "title:not_womens"),
    ("엠유스포츠 아이코닉 듀오 니트 가디건 2종", "title:not_womens"),
    ("까스텔바작 구스 숏패딩 점퍼 BGBWSJ704", "title:not_womens"),
    ("울시 여성 후드집업+풀오버 니트 2종", "title:not_cardigan"),              # a 2-piece set, no cardigan word
    ("[울시] 여성 소프트터치 컴포트 후드집업+니트 2종 세트", "title:not_cardigan"),
    ("그린퀸 루네스 여성골프 니트집업", "title:not_cardigan"),
    # made up from the owner's words: a women's top that is no knit, a vest, a pullover
    ("여성 골프 구스 다운 점퍼", "title:not_knit"),
    ("여성 골프 니트 조끼 베스트", "title:not_cardigan"),
    ("LADIES golf knit pullover", "title:not_cardigan"),
    ("Women's Golf Cable Cardigan", None),
    # 2026-11-20: a windbreaker that calls itself a cardigan (12228093693); knit zip-ups named 자켓 / 바람막이 stay
    ("여성 골프 바람막이 테일러메이드 방풍 자켓 간절기 가디건 스윙 골프웨어 CO-72PP44", "title:jacket_no_knit"),
    ("Women's golf windbreaker cardigan", "title:jacket_no_knit"),
    ("여성골프방풍니트 가디건 집업 점퍼 자켓 골프복 골프웨어", None),
    ("여자 골프 방풍 니트 가디건 자켓 바람막이 겨울 티셔츠 여성골프웨어", None),
    ("볼빅골프웨어 여성 골프 패딩 하이브리드 방풍 가디건", None),             # no jacket word: left to the review
])
def test_knit_cardigans_need_a_womens_word_and_a_cardigan_word(title, code):
    screen = Screen("50002797", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002797", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


@pytest.mark.parametrize("title, code", [
    # 50002798, women's golf windbreakers (2026-11-20): real titles of the listing 여성 골프 바람막이 점퍼 (767 titles in
    # 8 price bands, the agent's sample of 2026-11-20)
    ("스윙서플라이 파스텔 여성 골프 바람막이 스윙 점퍼", None),
    ("레크레아 여성 골프 바스락 경량 허리셔링 크롭 바람막이 후드 자켓", None),
    ("다운블로우 여성 경량 스판 블루종 점퍼", None),                         # 다운블로우 is a brand
    ("클라터뮤젠 여성 베스트라 후드 자켓 집업 바람막이 블랙 507784", None),    # Vestra, a jacket
    ("여성 골프점퍼 바람막이 니트 방풍 자켓 여성골프웨어", "title:knit"),      # a knit is never a windbreaker
    ("티앤드 여성골프점퍼 골프가디건 바람막이 자켓 방풍 여자골프웨어", None),   # a cardigan word with a jacket word
    ("까스텔바작 여성골프 간절기 방풍 기모안감 후드 점퍼 BDFFJP502BK", None),
    ("밀라 라이트 쉴드 점퍼 MD262F0101JP", "title:not_womens"),
    ("남자골프잠바 바람막이", "title:not_womens"),
    ("스트링조절 여성 골프 조끼", "title:not_jacket"),
    ("고엑스오 웨얼이즈마이볼 여성 골프 카라 우븐 반팔집업", "title:not_jacket"),
    ("그리너리 여성 덕다운 경량 골프패딩 바람막이자켓 GWWOT1168 BK", "title:padded"),
    ("[ WAAC ] 여성 니블릭 다운 점퍼(WWUAW26800BKX)", "title:padded"),
    ("여성 골프 에센셜 마름모 튜브 구스 다운 경량 점퍼 WO992", "title:padded"),
    ("여성 골프 비옷 롱 레인코트 방수 방풍 우비 골프웨어 아우터 점퍼", "title:rainwear"),
    ("테일러메이드 어패럴 여성 골프웨어 3L 경량 스트레치 레인 점퍼 UO-Z1YY05", "title:rainwear"),
    ("여성 트레이닝 점퍼", None),                                          # 트레이닝 is no 레인
    ("여성 골프 레인지웨어 바람막이 점퍼", None),                            # range wear, 2026-11-20
    ("왁 골프 여성 반팔 바람막이 베스트 VAM2201BKX", "title:vest"),
    ("프아린 여성골프 니트 집업 가디건 여자간절기가디건 여성골프점퍼 니트점퍼", "title:knit"),
    ("데상트골프 여성 밑단 니트 하이브리드 점퍼", "title:knit"),
    ("여성 골프 가디건 점퍼", None),
    ("여성 골프 가디건 아우터 블루종", None),                                # 블루종 is a jacket word, 가디건 unless it
    ("여성 골프 집업 가디건", "title:not_jacket"),
    ("여성 골프 바람막이 상하세트", "title:two_piece_set"),
    ("프리덴 여성 골프 아노락 반바지 투피스 세트", "title:two_piece_set"),      # 10674911182 (2026-11-21)
    ("여성 골프 바람막이 셋업", "title:two_piece_set"),
    ("볼빅 여성 골프 부클 방풍 풀집업 점퍼 SOA11", "title:knit"),              # 13783173372, a bouclé (2026-11-21)
    # 2026-11-21 (the owner's decision: fleece, vests, light down and rainwear go to Rainwear & Midlayers): left out
    ("여성 골프 아노락 후리스 바람막이 점퍼 자켓 겨울 골프 골프복 연습복 할로", "title:fleece"),   # a 50002799 card
    ("여성 골프 플리스 집업 자켓", "title:fleece"),
    ("여성 골프 경량패딩 바람막이 점퍼", "title:padded"),                    # light down: midlayers
    ("여성 골프 하프 코트 자켓", "title:coat"),
    ("여성 골프 방수 방풍 바람막이 점퍼", None),                             # 방수 is a windbreaker's function
    ("여성 골프 기모 바람막이 점퍼", None),                                  # brushed lining: still a windbreaker
    ("WAAC 여성 에어홀 트리코트 점퍼 바람막이", None),                       # tricot is no coat (2026-11-21)
    ("여성 골프 레인코트 방수 점퍼", "title:rainwear"),                       # a rain coat is rainwear first
])
def test_windbreakers_need_a_womens_word_and_a_jacket_word_and_no_padding(title, code):
    screen = Screen("50002798", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002798", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code
    jackets = Screen("50002799", namespace="fairwardgolf")                # 재킷: the same rules (2026-11-21)
    assert jackets.check({"name": title, "category_id": "50002799", "product_id": "1",
                          "store": {"channel_no": "2"}}) == code


def test_a_windbreaker_job_takes_the_jackets_rows_too_by_their_own_rules(tmp_path):
    """2026-11-21, the owner: 점퍼 50002798 and 재킷 50002799 feed one section: a job of either takes the other's rows
    (`together`), each screened by its own category's rules; any other category is still a mismatch."""
    import listing_filter as LF
    assert LF.together("50002798") == ["50002799"] and LF.together("50002799") == ["50002798"]
    assert LF.together("50002797") == []
    row = {"name": "로로얼로이 여성골프점퍼 바람막이 아트레터링 후드", "product_id": "7045315598", "store": {"channel_no": "2"}}
    screen = Screen("50002798", namespace="fairwardgolf")
    assert screen.check({**row, "category_id": "50002799"}) is None and screen.takes("50002799")
    assert screen.check({**row, "category_id": "50002797"}) == "category_mismatch" and not screen.takes("50002797")
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"categories": {"1": [], "2": [{"code": "only_two", "tokens": [{"text": "바람"}]}]},
                                "together": {"1": ["2"]}}), encoding="utf-8")
    assert LF.together("1", str(path)) == ["2"] and LF.title_rules("2", str(path))[0]["code"] == "only_two"


def test_requires_is_all_of_the_groups_any_word_of_each_and_unless_still_wins():
    rules = [{"code": "x", "requires": [["a", "b"], ["c"]], "unless": ["zz"]}]
    assert title_rule("a c", rules) is None and title_rule("B C", rules) is None
    assert title_rule("a", rules) == "title:x" and title_rule("c", rules) == "title:x"
    assert title_rule("zz", rules) is None                                  # an unless word: the rule is off


def test_the_jackets_title_rules_are_the_windbreakers():
    """2026-11-21, the owner: 점퍼 50002798 and 재킷 50002799 feed one section; their title rules stay the same (only
    `why` differs)."""
    import listing_filter as LF
    strip = lambda rules: [{k: v for k, v in r.items() if k != "why"} for r in rules]   # noqa: E731
    assert strip(LF.title_rules("50002799")) == strip(LF.title_rules("50002798"))


@pytest.mark.parametrize("title, code", [
    # 50002796 women's fall long-sleeve golf tops (2026-11-21): real titles of the listing 여성 골프 가을 긴팔 티셔츠
    ("루이까스텔 여성 FW베이직 모크넥 티셔츠 7LOTS907 6컬러", None),
    ("PXG 골프긴팔티 KQF PKFPW4112-05 여성 하프 지퍼 하이넥 스웨터", None),           # a knit sweater is a top
    ("PUMPING 여성 골프이너웨어 발열기모 기능성티셔츠 국내생산", None),                 # a base layer
    ("말본 PXG골프긴팔티 GQT PJWCW4116-01 WOMEN WINTER WINDPROOF NEW HIGH NECK SWEATER", None),
    ("김영주골프 겨울기모 골프이너웨어 남성 봄가을 소프트 이너티셔츠 KMSMTS21", "title:not_womens"),
    ("와이드앵글 여성 골프 니트 가디건 스커트 세트", "title:cardigan"),
    ("와이드앵글 여성 골프 카라넥 니트 스커트 상하의 세트", "title:bottoms_or_set"),
    ("[골든베어] 여성 퀄팅 스웻 긴팔 티셔츠 + 와이드 롱팬츠 2종 택1", "title:bottoms_or_set"),
    ("파사디골프 여성 가을 가오리핏 뒤판 우븐배색 패딩 티베스트 P25FTV146X", "title:vest"),
    ("PXG 골프긴팔 KQF PKWPW4319-21 여성 사이드 오픈 우븐 하이브리드 다운 자켓", "title:outerwear"),
    ("여성 골프웨어 아이스 이너웨어 냉감 긴팔 골프 티셔츠", "title:cooling"),
    ("여성 볼레로토시 이너웨어", "title:arm_sleeves"),
    ("여성 골프 반팔 티셔츠", "title:short_sleeve"),
    ("여성 베스트셀러 긴팔 카라 티셔츠", None),                                   # best seller is no vest
    ("WAAC 여성 트리코트 긴팔 티셔츠", None),                                     # tricot is no coat
    ("말본골프 긴팔티 PQS M6322PKO13 스타디움 테리 풀오버 (WOMAN)", None),          # WOMAN (2026-11-21)
    ("말본 우먼스 하이넥 스웨터", None),
    ("말본 여성 컬러블록 피스테 긴팔 티셔츠", "title:outerwear"),                     # a piste (2026-11-21)
])
def test_long_sleeve_tops_need_a_womens_word_and_no_other_garment(title, code):
    screen = Screen("50002796", namespace="fairwardgolf")
    assert screen.check({"name": title, "category_id": "50002796", "product_id": "1",
                         "store": {"channel_no": "2"}}) == code


@pytest.mark.parametrize("title, mens, womens", [
    # 2026-11-21: 50002796 feeds two sections, each job its own required words (--leaf); the women's job names none
    ("타이틀리스트 남성 골프 긴팔 티셔츠", None, "title:not_womens"),
    ("PXG MEN'S 긴팔 폴로", None, "title:not_womens"),
    ("PXG WOMEN 긴팔 티셔츠", "title:not_mens", None),                  # "men" inside "women" is no men's word
    ("남성 골프 반팔 티셔츠", "title:not_long_sleeve", "title:not_womens"),
    ("남성 골프 반팔 카라 티셔츠", "title:not_long_sleeve", "title:not_womens"),
    ("기모 남성 골프맨투맨 남자골프티셔츠", None, "title:not_womens"),          # a sweatshirt is long-sleeved (11-22)
    ("[국내매장판] 나이키 골프 남성 쿼터 집업 탑 써마 핏 빅토리 DN1948", None, "title:not_womens"),
    ("말본골프 긴팔 PQS M6321PKT07NVY M 캐시 혼방 크루넥 니트스웨터 NAVY (MAN)", None, "title:not_womens"),
    ("푸마 남성 골프 카라티 티셔츠 골프웨어", "title:not_long_sleeve", "title:not_womens"),   # a polo: sleeve unsaid
    ("람다골프 남성골프웨어 윈드브레이커 V넥 풀오버", "title:outerwear", "title:not_womens"),
    ("남성 여름 골프 냉감 이너웨어 긴팔 쿨티셔츠", "title:cooling", "title:not_womens"),
    ("남성 골프 긴팔 카라 티셔츠 가디건", "title:cardigan", "title:not_womens"),  # the shared rules bind both
    ("레디스 긴팔 garment dyed 폴로", "title:not_mens", "title:not_womens"),     # garment is no men's word (11-22)
    ("멘즈 골프 긴팔 티셔츠", None, "title:not_womens"),
])
def test_each_section_of_the_long_sleeve_tops_has_its_own_required_words(title, mens, womens):
    row = {"name": title, "category_id": "50002796", "product_id": "1", "store": {"channel_no": "2"}}
    assert Screen("50002796", namespace="fairwardgolf", leaf="mens-fall-long-sleeve-tops").check(row) == mens
    assert Screen("50002796", namespace="fairwardgolf").check(row) == womens


def test_a_job_may_name_only_a_known_section():
    import listing_filter as LF
    assert LF.leaves_of("50002796") == {"womens-fall-long-sleeve-tops", "mens-fall-long-sleeve-tops"}
    assert LF.leaves_of("50002788") == set()


def test_the_mens_tops_job_takes_the_mens_knits_and_the_womens_jobs_do_not():
    """2026-11-22: together_leaf: a job of 50002796 for the men's section takes 50002797 rows, screened by its men's
    rules; the women's tops job and the knit cardigans' job keep their own."""
    import listing_filter as LF
    assert LF.together("50002796", leaf="mens-fall-long-sleeve-tops") == ["50002797"]
    assert LF.together("50002796") == [] and LF.together("50002797") == []
    men = Screen("50002796", namespace="fairwardgolf", leaf="mens-fall-long-sleeve-tops")
    row = {"name": "캘러웨이 남성 골프 니트 반집업 스웨터", "category_id": "50002797", "product_id": "1",
           "store": {"channel_no": "2"}}
    assert men.check(row) is None
    assert men.check({**row, "name": "남성 골프 니트 가디건"}) == "title:cardigan"
    assert men.check({**row, "name": "여성 골프 니트 가디건"}) == "title:not_mens"
    # the probe of 남성 골프 니트 (2026-11-22): a season's best seller is no vest, a summer cool knit is no fall top
    assert men.check({**row, "name": "(시즌베스트입고)제이린드버그골프 남성 투어 메리노울 반집업 니트"}) is None
    assert men.check({**row, "name": "남성 골프 니트 베스트"}) == "title:vest"
    assert men.check({**row, "name": "애플라인드 26SS 남성 인견 썸머 쿨니트 3종"}) == "title:cooling"
    # the men's pilot review (2026-11-22): down-filled pullovers, a cooling stretch polo and summer tops
    tee = {**row, "category_id": "50002796"}
    assert men.check({**tee, "name": "마스터베어 오리털 티셔츠 W 0401 골프 긴팔티 골프웨어 남성용"}) == "title:outerwear"
    assert men.check({**tee, "name": "테일러메이드 어패럴 남성 골프웨어 골프 티셔츠 카라 긴팔 기본 쿨 스판 26-P1741C"}) == "title:cooling"
    assert men.check({**tee, "name": "남자 골프 티셔츠 여름 긴팔 카라티 기능성 셔츠 빅사이즈"}) == "title:summer"
    assert men.check({**tee, "name": "김영주골프 남성 골프웨어 긴팔 카라 티셔츠 기능성 봄 여름 가을 골프복 상의(M7ST57)"}) is None
    assert men.check({**row, "name": "남성 여름 골프 니트 스웨터"}) == "title:summer"
    assert Screen("50002796", namespace="fairwardgolf").check({**row, "name": "여성 골프 니트 스웨터"}) == "category_mismatch"
    knits = Screen("50002797", namespace="fairwardgolf")                    # the cardigans' job: as before
    assert knits.check({**row, "name": "여성 골프 니트 가디건"}) is None
    assert knits.check(row) == "title:not_womens"


@pytest.mark.parametrize("title, code", [
    # 50002802, Golf Skirts & Culottes (2026-11-22): the probe's cards, 480 of 490 kept
    ("여성 골프스커트 앞뒤 언발란스 플리츠 골프치마 여자골프웨어", None),
    ("왁 골프 플리츠 큐롯스커트 KCM22401BUX", None),                       # no women's word: a skirt is women's
    ("클래식 테니스스커트 주름스커트 보에르", None),
    ("DAYSILY GOLF 여성 골프웨어 플레인 주름치마 골프스커트 여자골프복 연습복 필드룩", None),   # 플레인 is no rain
    ("[카파 공식몰] 골프 포켓 스커트팬츠 여성 3컬러", None),
    ("J2M골프 비치마 주머니가 달려 편리한 레인스커트", "title:rain"),
    ("골프 비치마 주머니있는 레인스커트 남녀공용 방수 우비치마", "title:rain"),
    ("화이트베어 허리밴딩 스판 여성 골프바지 9부 부츠컷 반바지 치마 스커트 플리츠 큐롯", "title:trousers"),
    ("수이골프 만능 담요 치마 바지위 치마위 착용 무릎 스포츠 여성 학생 사무실 겨울", "title:not_garment"),
    ("여성 골프 반바지 숏팬츠", "title:not_skirt"),
    ("남성 골프 스커트", "title:mens"),
])
def test_skirts_need_a_skirt_word_and_leave_out_rain_and_trousers(title, code):
    assert Screen("50002802", namespace="fairwardgolf").check(
        {"name": title, "category_id": "50002802", "product_id": "1", "store": {"channel_no": "2"}}) == code
