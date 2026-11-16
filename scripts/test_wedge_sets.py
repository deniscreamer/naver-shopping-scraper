"""Iron sets and full sets filed under wedge sets (2026-11-16): the overnight wedge scroll (job
fairwardgolf-50002783-20261116T150134Z) published 9 iron sets into the wedge-sets section; Naver's category 50002783
lists them because their sellers filed them under 웨지. transform.not_wedge_set holds them (not_wedge_set) where the
category's wedge_sets is on. The fixture is every 50002783 listing of the shop then (502 on 2026-11-16), title and variant rows
(make_wedge_sets_fixture.py); its state columns are a snapshot, so the tests pin keys, never counts; offline."""
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
# held single_only already (four single wedges by loft, "아이언세트" in the title): single_only stays their code
SINGLE_ONLY_TOO = {"12911658622", "12634260989"}


def listings() -> dict[str, dict]:
    with open(FIXTURE, encoding="utf-8") as f:
        return {r["key"].split(":")[-1]: r for r in json.load(f)}


def test_the_fixture_has_every_case():
    rows = listings()
    assert set(IRON_SETS) | set(FULL_SETS) | SINGLE_ONLY_TOO | set(WEDGE_SETS) <= set(rows)


def test_every_iron_set_and_full_set_and_nothing_else_is_held():
    held = {pid: why for pid, r in listings().items() if (why := not_wedge_set(r["title"], r["rows"]))}
    assert set(held) == set(IRON_SETS) | set(FULL_SETS) | SINGLE_ONLY_TOO
    for pid, why in {**IRON_SETS, **FULL_SETS}.items():
        assert held[pid].startswith(why), (pid, held[pid])


WEDGE_SETS = ("13163034573",      # KVV "아이언 세트", variants 6 Iron / 8 Iron / Sand Wedge: one club a variant
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
                "13370403487")      # TaylorMade junior 4 / 5 Piece Set ("4-6 years", "7-9 years": ages, not irons)


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
