"""Iron sets and full sets filed under wedge sets (2026-11-16): the overnight wedge scroll (job
fairwardgolf-50002783-20261116T150134Z) published 9 iron sets into the wedge-sets section; Naver's category 50002783
lists them because their sellers filed them under 웨지. transform.not_wedge_set holds them (not_wedge_set) where the
category's wedge_sets is on; the same night it published full sets, wood sets and junior sets with no iron run and
under 6 clubs counted, and a listing of one numbered iron a variant: held too (WOOD_AND_JUNIOR_SETS, ONE_IRON_A_VARIANT).
The fixture is every 50002783 listing of the shop (502 on 2026-11-16, 604 at its refresh that night, 906 at the review
of 2026-11-17), title and variant rows (make_wedge_sets_fixture.py); its state columns are a snapshot, so the tests pin
keys, never counts; offline. The review of 2026-11-17 added shaft sets, tees and one loft with one wedge letter
(not_wedge_set), and the single clubs that only prepare reads (single_club: a loft glued to letters, a bare club name;
a title "set or single" with no option): test_single_clubs_of_the_review_are_held_single_only."""
import copy
import dataclasses
import json
import os

import pytest

import transform
from transform import not_wedge_set, prepare
from transform_shops import rules_for

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "wedge_sets", "50002783.json")
WEDGES = "50002783"

# the iron sets of the overnight scroll, all published (active) before the rule
IRON_SETS = {
    "13370424163": "an iron run ('5-PW')",                  # Cleveland ZipCore XL, Regular+4-PW / 5-PW / 6-PW
    "13370491895": "8 clubs",                               # Acer XV 7피스 8피스, ( 5-9/ PW/ GW)
    "13377696273": "an iron run ('5 6 7 8 9')",             # Yamato "아이언 개별 전체 세트 5 6 7 8 9 피윙"
    "13382551761": "an iron run ('5-P')",                   # TaylorMade P790 "웨지 ... 아이언 세트", Regular+4-P AW
    "13383002675": "an iron run ('4 Iron- PW')",            # Callaway Apex, Regular+3 Iron- PW
    "13383404156": "an iron run ('3456789')",               # MAZEL 9PCS 3456789피칭
    "13385696985": "an iron run ('5-P')",                   # TaylorMade Stealth, Stiff+5-P/A
    "13601554331": "an iron set in the title, no wedge set",  # PGM NSR V "아이언 세트 59 PW SW", no variants
    "13603085795": "an iron run ('123456789')",             # MAZEL DS-VH 9PCS 123456789
    "10774881312": "an iron set in the title, no wedge set",  # PRGR 04 "아이언 5개 세트" (#7 #8 #9 PW AW), after the 300th
    "10774926547": "an iron set in the title, no wedge set",  # PRGR 04 "아이언 5개 세트 MCI"
}
# full sets (and one junior set) with more clubs than a wedge set, also published as wedge sets
FULL_SETS = {
    "13163090198": "14 clubs",                              # Callaway Strata 12 / 14 / 16 Piece
    "13164534019": "10 clubs",                              # Callaway Edge 10피스
    "13367088670": "11 clubs",                              # Callaway REVA 8 / 11 PIECE
    "13370399414": "7 clubs",                               # TaylorMade junior "10-12 years: 7 Piece Set"
    "13385371710": "12 clubs",                              # PGM 912피스, 12 Piece
    "13386254317": "12 clubs",                              # PGM 12pcs Clubs
    "13386376196": "9 clubs",                               # Callaway Strata 9피스
    "13388598186": "16 clubs",                              # Callaway Strata 11 / 16 Piece
}
# full sets, wood sets and junior sets with no iron run and under 6 clubs counted, published the same night (and the
# first fix's missed ones), and listings that sell one numbered iron a variant (2026-11-16)
WOOD_AND_JUNIOR_SETS = {
    "13469122120": "'우드'",                   # women's wood set 3팩, driver + fairway 12 16 19도
    "13369466277": "'드라이버'",               # AGXGOLF XLT Executive, w드라이버 페어웨이
    "12178193064": "'우드'",                   # 골프클럽세트 우드 아이언 퍼터 웨지
    "13312275044": "'460CC'",                  # PGM III 18피스, 드라이 460CC
    "13312309860": "'드라이버'",               # Tivor: 퍼터 ... 아이언 웨지 드라이버 ... 스탠드
    "13370403487": "'주니어'",                 # TaylorMade junior 4 / 5 Piece Set
    "13163081877": "'클럽 세트'",              # US Kids, Ages 3 to 5 / 6 to 8 / 9 to 12 (its "클럽 세트" first)
    "13383629001": "'컴플리트'",               # Pro X 컴플리트 골프 세트
    "13383586259": "'컴플리트'",               # Artist Unknown 컴플리트 골프 세트
    "12918489634": "'컴플리트'",               # Wilson Profile SGI 컴플리트 골프 클럽 패키지 세트
    "13165737174": "'클럽 세트'",               # World Eagle 클럽 세트 11개 경량 캐디백
    "13163048070": "'하이브리드'",             # Olimar Stratos 하이브리드 아이언 클럽 세트, a Sand Wedge of it
    "13390699568": "'하이브리드'",             # Olimar Stratos 하이브리드 아이언, Sand / Gap Wedge of it
    "13366448074": "'주니어'",                 # Cleveland junior set, Ages 4-6 / 3 Clubs & Bag (published 21:53)
}
# a full set the first words missed ("완비", "이그제큐티브 골프 클럽 셋트"), a practice toy or one adjustable club:
# published as wedge sets by the overnight scroll 2026-11-16, after the 300th
MISSED_SETS = {"13603361909": "'완비'", "13384214680": "'이그제큐티브'",
               "13370640792": "'카트백'", "13312284857": "'카트백'"}   # Wilson Profile "카트백 골프 세트", after the 330th
PRACTICE = {"13163054038": "'조절식'", "13863445070": "'연습 세트'"}
# the listing's tail after the 330th (2026-11-17): no wedge at all, a plastic toy, or one club with no set in the title
TAIL = {
    "13621417627": 'one club: no set and no two lofts in the title',
    "12539223424": 'no wedge named',
    "13017276948": 'no wedge named',
    "11687969116": 'no wedge named',
    "13367831333": "a practice set or an adjustable club ('플라스틱')",
    "13384629323": 'no wedge named',
    "13110012279": 'one club: no set and no two lofts in the title',
    "13521216154": 'no wedge named',
    "12890200633": 'no wedge named',
    "13204672024": 'no wedge named',
    "12980298167": 'no wedge named',
    "13837017295": 'one club: no set and no two lofts in the title',
    "13799199015": 'one club: no set and no two lofts in the title',
    "7825655039": 'one club: no set and no two lofts in the title',
    # the review of 2026-11-17 (all published as wedge sets, withdrawn on the owner's word the same day)
    "13163052613": "a shaft set, no wedge ('샤프트 플렉스 선택 - 3개 세트')",   # Nippon N.S. Pro Modus, 3 shafts
    "13163054725": "a shaft set, no wedge ('샤프트 세트')",                    # True Temper Dynamic Gold, 3 shafts
    "13163078346": "tees, no wedge set ('대나무 티')",                         # Wedge Guys bamboo tees, 1000
    "13104702775": "one club: one loft and one letter",                       # Yonex Royal EZONE AW 49도
}
ONE_IRON_A_VARIANT = {"13762637990", "13762667328", "13830308916"}   # MAZEL WM-X "8번 아이언", "피칭 웨지", "아이언 2종"
# held single_only already (four single wedges by loft, "아이언세트" in the title; wedges by loft, "우드 드라이버" in
# the title): single_only stays their code
SINGLE_ONLY_TOO = {"12911658622", "12634260989", "13414645123"}


def listings() -> dict[str, dict]:
    with open(FIXTURE, encoding="utf-8") as f:
        return {r["key"].split(":")[-1]: r for r in json.load(f)}


def test_the_fixture_has_every_case():
    rows = listings()
    assert set(IRON_SETS) | set(FULL_SETS) | set(WOOD_AND_JUNIOR_SETS) | set(MISSED_SETS) | set(PRACTICE) | set(TAIL) \
        | ONE_IRON_A_VARIANT | SINGLE_ONLY_TOO \
        | set(WEDGE_SETS) <= set(rows)


# collected after the first rule (held by it in the scroll, never published): iron runs, 16 clubs, "아이언세트 8개";
# and those collected after the second rule up to the fixture's refresh after the 300th (737 listings);
# the single_only ones keep that code (POSSOT "5 Iron Single", PGM "1 Pcs (5 Iron)")
HELD_SINCE = {"13365547743", "13371801797", "13377603626", "13385700387", "13390592978", "13601371230",
              "13204761196", "10273552089",
              "10454438875", "10454495924", "13393745846", "13163051904", "13164524215", "13164578027",
              "13017346884", "13363829003", "13363833976", "13369513747", "13370375430", "13370550632",
              "13372009887", "13382172682", "13382899995", "13383279179", "13383675799", "13384486226",
              "13385326057", "13385600134", "13385675635", "13385973782", "13388599985", "13388851720",
              "13389314198", "13389378050", "13389676655", "13390089232", "13390573669", "13312215515",
              "13312250515", "13312276116", "13312283740", "13312287457", "10273623236",
              "13163086031", "13164550927", "13366156250", "13369476018", "13369497856", "13371087777", "13382791917", "13383263087",
              "13390539810", "13122159152", "13127564080", "13468917512", "13204957265", "13207752721", "13400292221", "13312273976",
              "11368559816", "9915142632", "10277536572", "13772575847", "13163079091", "13163085239", "13164570483", "11891765963",
              "13365502762", "13367215167", "13370542277", "13370591930", "13370657186", "13377534401", "13383281785", "13383398815",
              "13383793589", "13384520627", "13385269148", "13385553390", "13385684651", "13385945341", "13386161009", "13386664678",
              "13389318754", "13389349742", "13389485564", "13389674378", "13389736387", "13389997243", "13390701503", "13590272087",
              "13590416670", "13209378848", "13209387734", "13209552781", "12592963046", "12592973343", "13251646952", "13642238497",
              # collected after the refresh of the 330th, held before the review of 2026-11-17 (its refresh: 906)
              "13620800318", "13621409117", "13621410927", "13621412222", "13621413572", "13621414098",
              "12888330067", "13253060062", "13204497320", "13204959337", "13569960403", "13526583050",
              "13526752787", "13548176584", "13685984034"}
HELD = set(IRON_SETS) | set(FULL_SETS) | set(WOOD_AND_JUNIOR_SETS) | set(MISSED_SETS) | set(PRACTICE) | set(TAIL) | ONE_IRON_A_VARIANT | SINGLE_ONLY_TOO | HELD_SINCE


def test_every_iron_set_and_full_set_and_nothing_else_is_held():
    held = {pid: why for pid, r in listings().items() if (why := not_wedge_set(r["title"], r["rows"]))}
    assert set(held) == HELD
    for pid, why in {**IRON_SETS, **FULL_SETS}.items():
        assert held[pid].startswith(why), (pid, held[pid])
    for pid, word in PRACTICE.items():
        assert held[pid] == f"a practice set or an adjustable club ({word})", (pid, held[pid])
    for pid, word in {**WOOD_AND_JUNIOR_SETS, **MISSED_SETS}.items():
        assert held[pid] == f"a full set, a wood set or a junior set ({word})", (pid, held[pid])
    for pid, why in TAIL.items():
        assert held[pid] == why, (pid, held[pid])
    for pid in ONE_IRON_A_VARIANT:
        assert held[pid].startswith("one numbered iron a variant"), (pid, held[pid])


def test_the_published_wedge_sets_stay():
    """Every listing the store had (active, draft or withdrawn) when the fixture was made, not named above: a wedge set."""
    published = {pid: r for pid, r in listings().items() if r["state"] in ("active", "draft", "withdrawn")}
    assert len(published) > 300
    for pid, r in published.items():
        if pid not in HELD:
            assert not not_wedge_set(r["title"], r["rows"]), (pid, r["title"])


WEDGE_SETS = ("13163034573",      # KVV "아이언 세트", variants 6 Iron / 8 Iron / Sand Wedge: one club a variant, no iron
                                  # set (prepare holds it single_only since 2026-11-17: each value a bare club name)
                "10800343815",      # 혼마 베레스 NX 아이언 SW AW 웨지세트
                "11006400319",      # 혼마 투어월드 GS 11번(47도)/SW(56도) 웨지세트
                "13850694032",      # 테일러메이드 P8CB 웨지 세트 50도+56도 아이언 2개
                "13661086581",      # 장인 스탠다드 웨지 2개세트 어프로치 샌드웨지, 46도 50도 ...
                "13017111047",      # 마젝 여자 완비 웨지 세트 52 갭 웨지GW 56 샌드 웨지SW 60 롭 웨지
                "13312218924",      # 마젝 샌드 52 GW LW 60 시니어 ... SW 56 완비
                "13685621165",      # 클리브랜드 588 G 52도 + S 56도 + L 60도
                "5305572105",       # 맥그리거 NV201 50도 56도 [Aw,Sw]
                "13582215582",      # USPA P200T 웨지세트 (Aw Sw)
                "12178280377",      # 50-60도 입문용 웨지세트, 50/54/58도 세트 ...
                "12178241251",      # 50-70도 웨지세트
                "13830312687",      # 골프 웨지 세트 50°-69°
                "13164548371",      # 69도 ... 세트546069
                "13162815650",      # 52566070도 glued lofts
                "11585678496",      # 미우라 2개세트, 3개 (52Y 56Y 60C)
                "13164574170",      # 커클랜드 3피스 세트
                "13566630297",      # 690 3Piece / 4Piece Set
                "12701006618",      # TaylorMade MG5 SB 세트 3개
                "11252052400",      # 핑 프로디 G 주니어 골프 웨지 2종 세트: a junior wedge set
                "13017134183",      # 마젝 컴플리트 웨지 세트 52 갭 웨지GW 56
                "13383624548",      # 마제크 여성 컴플리트 세트 52° 갭 웨지GW 56°
                "13312219759",      # 마젝 웨지 60 GW 52 56 세트 ... 컴플리트 남성용 LW
                "13205011329",      # 올리마르 4피스 웨지 세트 (피칭 / 모래 롭 유틸리티 웨지)
                "13400000051",      # PGM 3 클럽 웨지 세트 ... 어프로치 스탠드
                "13122106279")      # 버뮤다 웨지 세트 ... 캐비티 백 디자인


def test_the_real_wedge_sets_stay():
    """Every other listing reads as a wedge set: 2-4 lofts, PW / AW / SW / GW / LW, 46-72°, iron-type wedges,
    approach + sand, gap / sand / lob (the 502 of 2026-11-16: 227 of them published then)."""
    rows = listings()
    for pid in WEDGE_SETS:
        assert not not_wedge_set(rows[pid]["title"], rows[pid]["rows"]), pid


@pytest.mark.parametrize("text", [
    "5-PW", "4~9", "#5-PW", "5번-PW", "4i-PW", "3 Iron- PW", "6-P/A", "3-SW", "5–9", "3456789", "56789",
    "123456789", "5 6 7 8 9 PW", "5, 6, 7, 8, 9"])
def test_an_iron_run(text):
    assert transform._iron_run(text), text


@pytest.mark.parametrize("text", [
    "7-9 years 5 Piece Set", "4-6 years", "52-56-60도", "48-60도", "50°-69°", "505254565860", "52566070",
    "52 56 60 Degree Set", "MG5 52.09 SB", "WA3817562", "11번(47도)/SW(56도)", "Ages 6 to 8", "LH01-52 56 60 Degree",
    "1 2 3", "5 6 7",
    # wedge titles that could come (review 2026-11-16): a numbered option, a model number, a day span
    "1-AW 52도 / 2-SW 56도", "옵션 1-PW 48도", "타입 2 - SW 56도", "클리브랜드 RTX 6 - SW 56도", "CBX 4 - AW/SW",
    "2-P 세트", "해외배송 7-9일 소요", "3~9일 출고", "5-9 days"])
def test_not_an_iron_run(text):
    assert not transform._iron_run(text), text


@pytest.mark.parametrize("title, rows, held", [
    ("골프 웨지 세트 갭 52개 샌드 56개 롭 60개", [], False),      # lofts read as counts (Roiko imports)
    ("웨지 3종 세트 6개월 보증", [], False),
    ("단조 골프 웨지 아이언 세트 샤프트 제외, 60도", [], False),   # 13803938082: iron-type wedges
    ("웨지 6피스 세트", [], False),                             # a count right after 웨지 counts wedges
    ("웨지 6개 세트 48 50 52 54 56 58", [], False),
    ("골프 아이언 6피스 세트", [], True),
    ("풀세트 12개 구성", [], True),
    ("14본 세트", [], True),
    # gifts and limits are not clubs; a wedge pair to match an iron set is a wedge set (review 2026-11-16)
    ("웨지 세트 52 56 60 골프공 12개 증정", [], False),
    ("웨지 3종 세트 헤드커버 10개", [], False),
    ("10본 한정 웨지 세트", [], False),
    ("포틴 아이언 세트 추가용 웨지 AW SW 2개 세트", [], False),
    ("아이언세트 단품 웨지 50 56 2종 세트", [], False),
    ("Golf Iron Set Right", [["6 Iron"], ["56 Degree"]], False),         # a single loft is one club
    ("Golf Iron Set Right", [["Regular"], ["Stiff"]], True),
    ("Golf Iron Set Right", [["6 Iron"], ["Pitching Wedge"]], False),   # one club a variant: not an iron set
    # full sets, wood sets, junior sets (2026-11-16) and a putter or a bag as a gift or a case (never held)
    ("웨지 세트 드라이버", [], True),
    ("Golf Wedge Set", [["Driver + Fairway Wood"]], True),
    ("하이브리드 유틸 세트", [], True),
    ("풀세트 남성용", [], True),
    ("Complete Golf Set Right", [], True),
    ("스탠드백 퍼터 포함 클럽 세트", [], True),
    ("골프 아이언 퍼터 웨지 세트", [], True),
    ("골프 아이언 웨지 퍼터 세트", [], False),                            # "아이언 웨지": iron-type wedges
    ("Junior Golf Set", [["Ages 6 to 8"]], True),
    ("키즈 골프 클럽 세트 3-5세", [], True),
    ("웨지 세트 + 헤드커버", [], False),
    ("웨지 세트 52 56 60 웨지 케이스", [], False),
    ("웨지 세트 퍼터 증정", [], False),
    ("웨지 3종 세트 캐디백 증정", [], False),
    ("웨지 세트 52 56 퍼터", [], False),                                 # a putter with no other club family
    ("Iron-type wedge set with putter cover", [], False),
    ("아이언형 웨지 세트 퍼터", [], False),
    ("드라이버 헤드커버 증정 웨지 세트", [], False),
    ("우드 커버 포함 웨지 3종 세트", [], False),
    ("웨지 3종 풀세트", [], False),
    ("컴플리트 웨지 세트 52 56 60", [], False),
    ("마젝 여성 컴플리트 세트 52° 갭 웨지GW 56°", [], False),
    ("4피스 웨지 세트 피칭 샌드 롭 유틸리티 웨지", [], False),
    ("주니어 골프 웨지 2종 세트", [], False),
    ("주니어 웨지 52 56도 세트", [], False),
    ("할리우드 웨지 세트", [], False),
    # review probes (2026-11-16): wedge sets the full-set words must not hold, none in the shop yet
    ("클리브랜드 RTX 웨지 52-56 세트", [], False),                       # a loft span before 세트, not an age span
    ("웨지 52~56 세트", [], False),
    ("웨지 50-54-58 세트 스틸", [], False),
    ("포틴 웨지 2개 50-56 세트", [], False),
    ("RTX6 웨지 52-58 세트 다이나믹골드", [], False),
    ("시니어 50~60세 추천 웨지 클럽 세트", [], False),                   # a grown-up's age
    ("골프 백스핀 웨지 클럽 세트 52 56 60", [], False),                  # 백스핀, not a golf bag
    ("골프백스핀 웨지 클럽 세트", [], False),
    ("남성 골프 백스핀 웨지 세트 퍼터 증정", [], False),
    ("캐디 백스핀 웨지 클럽 세트", [], False),
    ("클리브랜드 스마트솔 하이브리드 웨지 2종 세트", [], False),          # hybrid wedges
    ("하이브리드 웨지 세트 52 56 60", [], False),
    ("웨지 세트 하이브리드 솔 52 56", [], False),
    ("페어웨이 벙커 러프 웨지 3종 세트", [], False),                      # where a wedge is used
    ("Golf Wedge Set for fairway bunker rough 52 56 60", [], False),
    ("웨지 3종 세트 우드티 증정", [], False),                             # a wood tee
    ("웨지 세트 우드 티 100개 증정", [], False),
    ("언더우드 웨지 세트 52 56", [], False),
    ("유틸리티 샌드 웨지 세트", [], False),
    ("웨지 세트 유틸리티 솔", [], False),
    ("웨지 세트 52 56 60 (드라이버 우드 커버 증정)", [], False),          # covers for a list of clubs
    ("웨지 클럽 세트 퍼터 헤드커버 포함", [], False),                     # the gear of a putter or a bag
    ("골프 웨지 클럽 세트 3종 퍼터 그립", [], False),
    ("골프 웨지 클럽 세트 52 56 60 캐디백 수납", [], False),
    ("Golf Club Set Wedge 52 56 60 with golf bag", [], False),
    ("무료 캐디백 웨지 클럽 세트", [], False),
    ("사은품 퍼터 골프 웨지 클럽 세트", [], False),
    ("풀세트 웨지 3종", [], False),                                       # a full wedge set by its count
    ("웨지 세트 풀세트 구성 3종", [], False),
    ("Complete Set of 3 Wedges", [], False),
    ("마젝 여성 컴플리트 세트 웨지 3종", [], False),
    ("풀세트 56° 남성용", [], True),                                      # one loft with ° is one loft, not two
    ("Kids set ages 9-12 yrs", [], True),
    ("골프 클럽 세트 4-6 years", [], True),
    ("골프 클럽 세트 경량 캐디백블랙", [], True),                         # a bag word glued to a colour
    # one numbered iron a variant: three irons or more, every variant one club
    ("MAZEL 웨지 세트", [["우측 8번 아이언"], ["우측 6번 아이언"], ["우측 4번 아이언"], ["우측 피칭 웨지"],
                        ["우측 아이언 2종 세트"]], True),
    ("Golf Wedge Set", [["7 Iron"], ["8 Iron"], ["9 Iron"]], True),
    ("Golf Wedge Set", [["7 Iron"], ["8 Iron"], ["52 56 Set"]], False),
    ("Golf Wedge Set", [["6 Iron"], ["8 Iron"], ["Sand Wedge"]], False),  # KVV: two irons
    # the review of 2026-11-17: a set of shafts (no wedge after the agency's "골프 웨지", no two lofts), not a wedge
    # set with its shafts; tees of a material, not a gift nor bonus tees of a written wedge set; one loft and one
    # letter are one club
    ("골프 웨지 일본 N S 프로 모더스 샤프트 플렉스 선택 - 3개 세트 레귤러 105g", [], True),
    ("골프 웨지 트루 템퍼 다이내믹 골드 투어 이슈 스피너 샤프트 세트 3개", [], True),
    ("골프 웨지 Golf Shaft Set of 3", [], True),
    ("Golf Wedge Shaft Set of 3", [], False),                           # a wedge named outside the agency's prefix
    ("조디아 WMS2 웨지 & ZNE 웨지 전용 샤프트 3개 세트", [["90", "48°/52°/56°"]], False),   # 13826837511
    ("골프 웨지 52 56 60 샤프트 세트", [], False),                        # lofts: wedges with their shafts
    ("웨지 3종 세트 샤프트 선택", [], False),
    ("골프 웨지 세트 3종 (샤프트 세트 포함)", [], False),                # the agency's wedge set (review of W3)
    ("골프 웨지 커클랜드 시그니처 3피스 세트 KBS 샤프트 세트", [], False),     # a set word before the shaft set
    ("골프 웨지 가이즈 대나무 티 3-14인치 100개 250개 또는 1000개 세트 초강력 내구성 및 목재 티보다 강함", [["1000"]], True),
    ("Bamboo Golf Tees 1000 pcs set 웨지", [], True),
    ("웨지 세트 + 대나무 티 50개 증정", [], False),
    ("웨지 3종 세트 52 56 60 bamboo tees", [], False),                   # a wedge set written: bonus tees
    ("웨지세트 52/56 블랙티 에디션", [], False),
    ("웨지 2종 세트 (나무티 포함)", [], False),
    ("웨지 세트 골프 티셔츠 증정", [], False),
    ("요넥스 YONEX 남성 로얄 이존 아이언 AW 로프트 49도 RX06RE 497 204293", [["R"], ["SR"]], True),
    ("웨지 AW 52도 SW 56도", [], False),                                  # two lofts, two letters
    ("혼마 웨지 AW SW 52 56", [], False),
    ("AW 52도 웨지 세트", [], False),                                     # a set word
])
def test_counts_and_the_title(title, rows, held):
    assert bool(not_wedge_set(title, rows)) is held


def test_prepare_holds_an_iron_set_only_where_the_category_sells_wedge_sets():
    """End to end on a real 50002783 line (13468791008 XINGGM wedges) given the Cleveland ZipCore XL's words."""
    with open(os.path.join(HERE, "fixtures", "collected", "13468791008.json"), encoding="utf-8") as f:
        line = json.load(f)
    rules = rules_for("fairwardgolf")
    assert rules.categories[WEDGES].wedge_sets
    assert prepare(copy.deepcopy(line), rules, "50002783-fixtures", 1)["status"] == "ready"
    line["details"]["name"] = "클리브랜드 골프 집코어 XL 아이언 세트 Left"
    groups = line["specs"]["options"]["option_groups"]
    base = line["specs"]["options"]["variants"][0]
    line["specs"]["options"]["variants"] = [
        {**base, "id": str(i), "options": [v] + [base["options"][1]] * (len(groups) - 1), "extra_price": 0}
        for i, v in enumerate(["Regular+4-PW", "Stiff+5-PW/GW"])]
    p = prepare(copy.deepcopy(line), rules, "50002783-fixtures", 1)
    assert p["status"] == "held" and [h["code"] for h in p["held"]] == ["not_wedge_set"]
    off = dataclasses.replace(rules, categories={**rules.categories,
                                                 WEDGES: dataclasses.replace(rules.categories[WEDGES],
                                                                             wedge_sets=False)})
    assert "not_wedge_set" not in {h["code"] for h in prepare(copy.deepcopy(line), off, "50002783-fixtures", 1)["held"]}


def test_single_only_stays_the_code_of_single_wedges_with_an_iron_set_title():
    """12911658622 "에잇룸 골프웨지 블랙밀러 아이언세트": four single wedges by loft; not_wedge_set reads it too, but the
    single_only hold comes first and stays its code."""
    with open(os.path.join(HERE, "fixtures", "collected", "13468791008.json"), encoding="utf-8") as f:
        line = json.load(f)
    rules = rules_for("fairwardgolf")
    line["details"]["name"] = "에잇룸 골프웨지 블랙밀러 아이언세트 골프채 아이언"
    groups = line["specs"]["options"]["option_groups"]
    base = line["specs"]["options"]["variants"][0]
    line["specs"]["options"]["variants"] = [
        {**base, "id": str(i), "options": [v] + [base["options"][1]] * (len(groups) - 1), "extra_price": 0}
        for i, v in enumerate(["밀러웨지52도", "밀러웨지56도", "블랙웨지52도", "블랙웨지56도"])]
    assert not_wedge_set(line["details"]["name"], [[v] for v in ["밀러웨지52도"]])
    p = prepare(copy.deepcopy(line), rules, "50002783-fixtures", 1)
    assert p["status"] == "held" and [h["code"] for h in p["held"]] == ["single_only"]


def test_only_wedge_sets_categories_hold_iron_sets():
    """The iron sets' own category (50002670) and the full sets' (50002788, 50002787) never hold their own products."""
    rules = rules_for("fairwardgolf")
    assert [c for c, r in rules.categories.items() if r.wedge_sets] == [WEDGES]


@pytest.mark.parametrize("values, single", [
    # a loft glued to the letters before it (Yamato left-hand wedges 13312155382 / 13312109978, review 2026-11-17)
    (["LH0160 Degree"], True), (["LH0156 Degree"], True), (["left hand60 degree"], True), (["RH52도"], True),
    (["SW56-10 Degree"], False), (["1056도"], False), (["i60R"], False), (["LH01-52 56 60 Degree"], False),
    (["Loft 10 Degree"], False), (["LH0152 56 Degree Set"], False),
])
def test_a_loft_glued_to_letters_is_one_club(values, single):
    assert transform.single_club(values) is single


@pytest.mark.parametrize("values, bare, single", [
    # a bare club name is one club only with bare (where not_wedge_set has no reason: KVV 13163034573)
    (["Sand Wedge"], True, True), (["6 Iron"], True, True), (["8번 아이언"], True, True), (["PW"], True, True),
    (["Sand Wedge"], False, False), (["6 Iron"], False, False),
    (["Sand Wedge", "Steel"], True, True),
    (["Sand Wedge + Gap Wedge"], True, False), (["PW AW SW"], True, False), (["52 56 Sand Wedge Set"], True, False),
    (["Sand Wedge 52 56"], True, False), (["우측 8번 아이언"], True, False),
])
def test_a_bare_club_name_is_one_club(values, bare, single):
    assert transform.single_club(values, (), bare=bare) is single


def _line(title: str, values: list[str]) -> dict:
    """The XINGGM line (13468791008) with another title and one value a variant on its first axis."""
    with open(os.path.join(HERE, "fixtures", "collected", "13468791008.json"), encoding="utf-8") as f:
        line = json.load(f)
    line["details"]["name"] = title
    groups = line["specs"]["options"]["option_groups"]
    base = line["specs"]["options"]["variants"][0]
    line["specs"]["options"]["variants"] = [
        {**base, "id": str(i), "options": [v] + [base["options"][1]] * (len(groups) - 1), "extra_price": 0}
        for i, v in enumerate(values)]
    return line


def test_single_clubs_of_the_review_are_held_single_only():
    """Review 2026-11-17: Yamato's glued lofts (13312155382), KVV's bare club names (13163034573) and a title "set or
    single" with no option (13312300055) are held single_only; MAZEL's numbered irons keep not_wedge_set."""
    rules = rules_for("fairwardgolf")

    def held(line):
        return [(h["code"], h["detail"]) for h in prepare(copy.deepcopy(line), rules, "50002783-fixtures", 1)["held"]]

    assert held(_line("야마토 왼손잡이 세트 개별 CNC 골프 단조 – 52 샌드 56 웨지 밀드 60 LH0160 Degree",
                      ["LH0160 Degree", "LH0156 Degree"])) == [("single_only", "2 variants, each one club")]
    assert held(_line("골프 웨지 KVV 아이언 세트 남성용 강철 샤프트 오른손용 Sand Wedge",
                      ["Sand Wedge", "6 Iron", "8 Iron"])) == [("single_only", "3 variants, each one club")]
    assert [c for c, _ in held(_line("MAZEL 웨지 세트", ["7 Iron", "8 Iron", "9 Iron"]))] == ["not_wedge_set"]
    kept = _line("골프 웨지 KVV 세트 남성용", ["Sand Wedge", "52 56 Set"])
    assert prepare(copy.deepcopy(kept), rules, "50002783-fixtures", 1)["status"] == "ready"

    line = _line("AS PREMIUM 남성용 또는 52 웨지 세트 싱글 페이스 웨지 CM 골프 밀드 50", [])
    line["specs"]["options"] = {**line["specs"]["options"], "has_options": False, "option_groups": [], "variants": []}
    line["details"]["description"]["text"] = "AS PREMIUM 밀드 웨지"
    assert held(line) == [("single_only", "the title sells a set or a single, no option chooses it")]
    named = copy.deepcopy(line)                     # a spec row that names the set: sold as written
    named["specs"]["specs"].append({"label": "구성", "value": "웨지 2개 세트"})
    assert held(named) == []
    plain = copy.deepcopy(line)                     # no "or single" in the title: not this hold
    plain["details"]["name"] = "AS PREMIUM 남성용 52 웨지 세트 페이스 웨지 CM 골프 밀드 50"
    assert held(plain) == []
