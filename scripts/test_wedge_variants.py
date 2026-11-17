"""Variants and options of the wedge-set review (2026-11-17, wave W5: C01, C08, C37, C50, C51, C52, C54, C55, C56, C57,
C70, C72). Real collected lines of fairwardgolf (fixtures/collected/, their prepared golden in fixtures/prepared/) and
the rows and texts they carry; offline.

  C01  a picker's club slots (TaylorMade MG5): no loft repeated on two slots ("56+56", the owner's value), one row
       per set (an order of a set already offered is that set); only a wedge-sets category
  C08  a switch cell of the description ("헤드 커버 | 있음없음"): the picked choice
  C37  a bare "P" glued to a model word ("D3P", "NX-1 P/A", "db4P") is no club count
  C50  a Latin placeholder option name ("Color" over lofts): asked of the model, the rule's English until it answers
  C51  a one-value colour axis whose value is a set ("Color: Wedge Set"): the fact without its label
  C52  values Naver cut at 25 characters, whole again from the description's option list; Amazon's index left out
  C54  raw lofts in 50002783's option values ("5056", "56.12 SB", "50°56°", "52 56 60 Degree") as a loft list
  C55  "Sliver" -> "Silver"
  C56  Amazon's two axes saying one thing (Size / Style Name "Black ..."): the rows where they agree
  C57  framed free headings over paid shafts are no add-ons; "헤드만" over paid shafts: heads_only
  C70  "Hand Orientation: Left" in the description and nowhere else: 사용방향 왼손용
  C72  a 웨지 로프트각 row with none of the title's lofts: dropped with 바운스각 (specs_contradict)
"""
import copy
import dataclasses
import json
import os

import pytest

import translate as T
import transform
from description_clean import picked_switches
from spec_variants import check_specs
from transform import prepare, sku
from transform_shops import rules_for, without_paid_addons
from translation_rules import sanitize

HERE = os.path.dirname(os.path.abspath(__file__))
WEDGES, SETS, JUNIOR = "50002783", "50002788", "50002787"
TENANT = "Fairward Golf"
RULES = rules_for("fairwardgolf")


def line(pid: str) -> dict:
    with open(os.path.join(HERE, "fixtures", "collected", f"{pid}.json"), encoding="utf-8") as f:
        return json.load(f)


def prep(pid: str, rules=RULES, change=None) -> dict:
    x = line(pid)
    if change:
        change(x)
    return prepare(x, rules, "50002783-fixtures", 1)


def notes(p: dict) -> dict:
    return {n["code"]: n["detail"] for n in p["notes"]}


def options(p: dict) -> dict:
    return {o["name_ko"]: o["values_ko"] for o in p["product"]["options"]}


def off_wedge_sets(rules=RULES):
    return dataclasses.replace(rules, categories={k: dataclasses.replace(v, wedge_sets=False)
                                                  for k, v in rules.categories.items()})


# ---- C01: a picker's club slots --------------------------------------------------------------------------------

def test_mg5_slots_sell_each_set_once_and_never_a_loft_twice():
    p = prep("12742411646")                         # SB웨지1/2/3, 343 rows: Naver's every product of the slots
    assert notes(p)["slot_rows_merged"] == "343 -> 35 rows (133 with a value repeated on two slots, 175 reordered)"
    assert "variants_capped" not in notes(p) and len(p["product"]["variants"]) == 35
    sets = [tuple(v["options_ko"]) for v in p["product"]["variants"]]
    assert all(len(set(s)) == 3 for s in sets)                         # no "56+56"
    assert len({tuple(sorted(s)) for s in sets}) == 35                  # one order of each set
    raw = {r["id"]: r["options"] for r in line("12742411646")["specs"]["options"]["variants"]}
    for v in p["product"]["variants"]:                                  # each a row of the page, its SKU as before
        assert v["sku"] == sku(RULES.sku_prefix, p["key"], "observed:" + json.dumps(
            raw[v["naver_variant_id"]], ensure_ascii=False, separators=(",", ":")))


def test_merged_slots_name_no_one_variant():
    # each slot picks one club: after the merge a slot lacks some lofts ("60도" never first), which is no title word
    # or 바운스각 row naming one variant; the title's lofts vs the sets sold is title_lofts_not_sold's (C01 review)
    p = prep("12742411646")
    assert "title_names_one_variant" not in notes(p) and "specs_name_one_variant" not in notes(p)


def test_slots_only_in_a_wedge_sets_category():
    p = prep("12742411646", off_wedge_sets())
    assert "slot_rows_merged" not in notes(p) and notes(p)["variants_capped"] == "343 -> 100"


def test_slot_rows_keep_another_axis_and_the_first_buyable_order():
    names = ["옵션 1", "옵션 2", "샤프트(오늘출발)"]
    rows = [{"options": ["52", "56", "S200"], "is_available": False}, {"options": ["56", "52", "S200"]},
            {"options": ["56", "56", "S200"]}, {"options": ["52", "56", "R300"]}]
    out, repeats, orders, slots = transform._slot_rows(names, [0, 1, 2], rows)
    assert (repeats, orders, slots) == (1, 1, [0, 1])
    assert [r["options"] for r in out] == [["56", "52", "S200"], ["52", "56", "R300"]]
    assert transform._slot_rows(["Size", "Style Name"], [0, 1], rows) == (rows, 0, 0, [])     # not slots


def test_slot_rows_keep_the_ascending_order_when_buyable_at_the_same_price():
    """D3 (2026-11-17, the resend review): the merged MG5 rows kept Naver's first buyable order, often not ascending
    ("Chrome 52° / Chrome 58° / Chrome 48°", 12742304001); a buyer picking the slots in ascending order met
    "unavailable". The ascending row wins when buyable at the first buyable row's price; else the first buyable."""
    names = ["옵션 1", "옵션 2"]
    rows = [{"options": ["Chrome 52°", "Chrome 48°"], "price": 100},
            {"options": ["Chrome 48°", "Chrome 52°"], "price": 100},
            {"options": ["56", "50"], "price": 100}, {"options": ["50", "56"], "price": 100, "is_available": False},
            {"options": ["60", "54"], "price": 100}, {"options": ["54", "60"], "price": 120}]
    out, _, orders, _ = transform._slot_rows(names, [0, 1], rows)
    assert orders == 3
    assert [r["options"] for r in out] == [["Chrome 48°", "Chrome 52°"], ["56", "50"], ["60", "54"]]


def test_mg5_slots_ascending_and_as_many():
    """D3: every kept set of the MG5 picker reads its slots by ascending loft; 35 rows still, each a page row."""
    p = prep("12742411646")
    lofts = [[int(transform._LOFT_RE.search(o).group(0)) for o in v["options_ko"]] for v in p["product"]["variants"]]
    assert len(lofts) == 35 and all(x == sorted(x) for x in lofts)


# ---- C56: two axes saying one thing ----------------------------------------------------------------------------

def test_amazon_axes_that_echo_keep_the_rows_where_they_agree():
    p = prep("13754846756")                         # Size "52 56 Degree" x Style Name "Black 52 56 Degree", 266 rows
    assert notes(p)["axes_repeated"] == "Style Name repeats Size: 266 -> 14 rows"
    assert "variants_capped" not in notes(p)
    assert [tuple(v["options_ko"]) for v in p["product"]["variants"]][:2] == [
        ("54 58 Degree", "Black 54 58 Degree"), ("54 60 Degree", "Black 54 60 Degree")]
    assert len(p["product"]["variants"]) == 6 and sum(v["available"] for v in p["product"]["variants"]) == 3


def test_axes_that_do_not_echo_stay():
    p = prep("13468791008")                         # XINGGM: Size "58 Degree" x Style Name "Silver RH"
    assert "axes_repeated" not in notes(p)
    rows = [{"options": ["50 54 58 Degree Set", "Black 50 54 58 Degree Set"]},
            {"options": ["52 Degree", "Black 52 Degree"]}, {"options": ["52 Degree", "Black 50 54 58 Degree Set"]}]
    assert transform._echo_axes(rows, 2) == (0, 1)                     # "Set" aside
    assert [transform._echoes_agree(r, 0, 1) for r in rows] == [True, True, False]


# ---- C52: values cut at 25 characters ----------------------------------------------------------------------------

def test_cut_values_are_whole_again_and_the_index_goes():
    p = prep("13017295953")
    assert options(p)["Color"] == ["52 56 60 Degree Set Tarnish", "56 60 Degree Tarnish"]
    raw = [r["options"] for r in line("13017295953")["specs"]["options"]["variants"]]
    assert ["1 52 56 60 Degree Set Tar"] in raw                        # the SKU keeps the raw tuple
    assert p["product"]["variants"][0]["sku"] == sku(RULES.sku_prefix, p["key"], 'observed:["1 52 56 60 Degree Set Tar"]')


def test_a_cut_set_is_a_set_again():
    p = prep("13377524996")                         # "Black Titanium Layer-50/5": read as one loft before, held out
    assert options(p)["Color"] == ["52/58 Degrees Set", "Black Titanium Layer-50/56 Degrees",
                                   "Black Titanium Layer-52/58 Degrees"]


def test_uncut_only_at_25_and_only_one_entry():
    entries = ["1 52 56 60 Degree Set Tarnish", "Black Titanium Layer-50 Degrees", "Black Titanium Layer-52 Degrees",
               "Black 52 Degree", "Black 52 Degree Set"]
    rows = [{"options": ["1 52 56 60 Degree Set Tar"]},                # 25: whole
            {"options": ["Black Titanium Layer-5"]},                    # 22, and two entries start with it
            {"options": ["Black Titanium Layer-50 D"]},                 # 25, one entry
            {"options": ["Black 52 Degree"]}]                           # an entry of its own
    out = transform._uncut(rows, entries)
    assert [r["options"] for r in out] == [["1 52 56 60 Degree Set Tarnish"], ["Black Titanium Layer-5"],
                                           ["Black Titanium Layer-50 Degrees"], ["Black 52 Degree"]]
    assert out[0]["raw_options"] == ["1 52 56 60 Degree Set Tar"] and "raw_options" not in out[1]
    two = ["Black Titanium Layer-62 Degrees", "Black Titanium Layer-62 Degrees Set"]
    assert transform._uncut([{"options": ["Black Titanium Layer-62 D"]}], two)[0]["options"] == ["Black Titanium Layer-62 D"]
    guard = transform._uncut([{"options": ["Black Titanium Layer-62 D", "Set"]}], ["Black Titanium Layer-62 D Set"])
    assert guard[0]["options"] == ["Black Titanium Layer-62 D", "Set"]           # the rest is the other value


@pytest.mark.parametrize("values, out", [
    (["1 52 56 60 Degree Set", "2 50 54 58 Degree Set"], ["52 56 60 Degree Set", "50 54 58 Degree Set"]),
    (["15 Black Titanium Layer-50/56 Degrees", "16 Black Titanium Layer-52 Degrees"],
     ["Black Titanium Layer-50/56 Degrees", "Black Titanium Layer-52 Degrees"]),
    (["1 [Graphite][9-Pieces]", "3 [Graphite][12-Pieces]"], ["[Graphite][9-Pieces]", "[Graphite][12-Pieces]"]),
    (["3 Wedges", "2 Wedges"], None), (["7 Iron", "8 Iron"], None), (["3 Wood", "5 Wood"], None),
    (["1 Black", "Black"], None), (["1 Black", "2 Black"], None), (["1 Black"], None),
])
def test_amazon_index(values, out):
    assert transform._unindexed(values) == out


def test_the_index_stays_outside_wedge_sets():
    p = prep("13017295953", off_wedge_sets())
    assert options(p)["Color"] == ["1 52 56 60 Degree Set Tarnish", "2 56 60 Degree Tarnish"]   # whole, indexed


# ---- C51: a colour label over a set --------------------------------------------------------------------------------

@pytest.mark.parametrize("label, value, out", [
    ("Color", "Wedge Set", ""), ("색상", "52/56/60도 세트", ""), ("컬러", "3종세트", ""), ("Color", "52/58 Degrees Set", ""),
    ("색상", "reva 10pcs", ""), ("선택", "남성풀세트", ""),
    ("Color", "Orange/ 52 56 60 Degree S", "Color"), ("색상", "로열 블루 만 11-14세 8피스 세트", "색상"),
    ("Color", "54 58 Degree Tarnish", "Color"), ("Color", "Black", "Color"), ("샤프트", "S200 세트", "샤프트"),
])
def test_fact_label(label, value, out):
    assert transform._fact_label(label, value) == out


# ---- C57: framed headings and heads only ------------------------------------------------------------------------

def test_framed_headings_over_paid_shafts_are_no_add_ons():
    p = prep("11585678496")                         # Miura "웨지 샤프트": "▣ KBS ▣" free, the KBS shafts paid
    names = [a["name_ko"] for a in p["product"]["addons"]]
    assert names and not any(transform._FRAMED_RE.match(n) or "헤드만" in n for n in names)
    assert notes(p)["heads_only"] == "웨지 샤프트: ◈ 헤드만 구매 ◈" and p["status"] == "ready"     # shafts on sale


def test_heads_only_held_where_paid_add_ons_are_off():
    p = prep("11585678496", without_paid_addons(RULES))
    assert {h["code"]: h["detail"] for h in p["held"]} == {"heads_only": "웨지 샤프트: ◈ 헤드만 구매 ◈"}


def test_a_framed_entry_with_no_paid_one_in_its_group_stays():
    specs = {"options": {"supplements": [
        {"group": "사은품", "name": "■ 볼마커 ■", "price": 0, "status": "SALE", "stock_quantity": 9},
        {"group": "사은품", "name": "【 헤드커버 】", "price": 0, "status": "SALE", "stock_quantity": 9}]}}
    assert [a["name_ko"] for a in transform.addons(specs, 1450)] == ["■ 볼마커 ■", "【 헤드커버 】"]
    assert transform.heads_only(specs) is None


# ---- C08: a switch in the description ------------------------------------------------------------------------------

def test_a_switch_reads_the_picked_choice():
    p = prep("12872703429")
    rows = [x for x in p["product"]["description_ko"].split("\n") if " | " in x]
    assert "AS 여부 | 불가" in rows and "헤드 커버 | 없음" in rows            # a true "no head cover": not dropped
    assert not any("있음없음" in x or "가능불가" in x for x in rows)


def test_picked_switches():
    html = ('<tr><th style="x">\n AS 여부\n</th><td style="y">\n<span style="opacity: 0.5;">가능</span>'
            '<span style="color: #1E5DDC">불가</span></td></tr>'
            '<tr><th>헤드 커버</th><td><span>있음</span><span>없음</span></td></tr>')     # nothing dimmed: stays
    text = "AS 여부 | 가능불가\n헤드 커버 | 있음없음\n가능불가"
    assert picked_switches(text, html) == "AS 여부 | 불가\n헤드 커버 | 있음없음\n가능불가"
    assert picked_switches(text, None) == text and picked_switches(None, html) is None


# ---- C70: the hand from Amazon's table -----------------------------------------------------------------------------

def test_left_hand_from_the_description_only_where_nothing_else_says_it():
    p = prep("13370297764")                         # BombTech "- Hand Orientation : Left", one variant
    assert {"label_ko": "사용방향", "value_ko": "왼손용"} in p["product"]["specs"]
    assert notes(p)["hand_from_description"] == "사용방향 왼손용"
    ov = {"options": [], "facts": [], "variants": [{}]}
    left = "Hand Orientation | Left"
    assert transform._hand_from_description(left, "웨지 세트", ov, []) is not None
    assert transform._hand_from_description("Hand Orientation | Right", "웨지 세트", ov, []) is None
    assert transform._hand_from_description(left, "왼손 웨지 세트", ov, []) is None
    assert transform._hand_from_description(left, "웨지 세트", ov, [{"label_ko": "사용방향", "value_ko": "오른손용"}]) is None
    assert transform._hand_from_description(left, "웨지 세트", {**ov, "variants": [{}, {}]}, []) is None
    assert transform._hand_from_description(left + "\nHand | Right", "웨지 세트", ov, []) is None
    assert transform._hand_from_description(left, "웨지 세트", {**ov, "facts": [{"value_ko": "LH"}]}, []) is None


# ---- C72: a wedge loft row against the title -------------------------------------------------------------------

def test_a_wedge_loft_row_with_none_of_the_titles_lofts_goes_with_its_bounces():
    p = prep("12482367407")                         # PRGR "52도,56도 웨지세트", row "50도, 60도"
    labels = {s["label_ko"] for s in p["product"]["specs"]}
    assert not labels & {"웨지 로프트각", "바운스각"}
    assert notes(p)["specs_contradict"] == ("웨지 로프트각 50도, 60도: the title says 52/56; "
                                            "바운스각 8도, 10도: the bounces of those lofts")
    rows = [{"label_ko": "웨지 로프트각", "value_ko": "50도, 52도, 56도"}, {"label_ko": "바운스각", "value_ko": "8도"}]
    kept = check_specs(rows, [], [], None, "미즈노 프로 T-1 골프 웨지 2본 세트 50도 56도")
    assert kept["specs"] == rows and not kept["notes"]                  # a loft shared: stays
    assert check_specs(rows[:1], [], [], None, "웨지 세트 52도")["specs"] == rows[:1]    # one loft in the title


# ---- C37: a bare P glued to a model word ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, count", [
    ("야마토 D3P", None), ("MARUMAN SHUTTLE NX-1 P/A,AW,SW 웨지세트", None), ("A11N SPORTS 웨지 세트 db4P", None),
    ("#8P Loft", None), ("J1P-S00", None), ("Set3P", None),
    ("하프세트(5P)", "5P"), ("웨지 3P 세트", "3P"), ("[3PCS]", "3PCS"), ("Degree-3PCS", "3PCS"),
    ("[11PCS/클럽만]", "11PCS"), ("[3P/클럽만]", "3P"), ("웨지 3P/스틸", "3P"), ("(3종)", "3종"), ("10+1pcs", None),
])
def test_pieces(text, count):
    m = transform._PIECES_RE.search(text)
    assert (m.group(0) if m else None) == count


def test_nx1_is_no_count_of_one():
    assert "few_pieces" not in notes(prep("13422541936"))


# ---- C50: a Latin placeholder name --------------------------------------------------------------------------------

def _colour_product(store_en=None):
    values = ["52 56 Degree Tarnish", "54 58 Degree Tarnish"]
    product = {"title_ko": "웨지 세트", "brand_ko": "야마토", "options": [{"name_ko": "Color", "values_ko": values}],
               "facts": [], "specs": [], "personalization": [], "addons": [], "reviews": []}
    texts = [("title", "웨지 세트"), ("brand", "야마토"), ("option_name", "Color")] + [("option_value", v) for v in values]
    return {"key": "fairwardgolf:naver:1:1", "status": "ready", "shop": "fairwardgolf",
            "notes": [{"code": "option_name_placeholder", "detail": "Color"}],
            "source": {"category_id": WEDGES}, "product": product,
            "texts": [{"id": transform.text_id(k, ko), "kind": k, "ko": ko} for k, ko in texts]}


def test_a_latin_placeholder_is_asked_and_keeps_the_rule_english_meanwhile(tmp_path):
    import translation_dicts as D
    p = _colour_product()
    tid = transform.text_id("option_name", "Color")
    d = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    en, by, pending = T.plan(p, d, {}, TENANT)
    assert en[tid] == "Color" and by[tid] == "rule"                   # until the model answers
    item = next(i for i in pending if i["id"] == tid)
    assert item["placeholder"] and item["context"] == "values: 52 56 Degree Tarnish | 54 58 Degree Tarnish"
    en, by, pending = T.plan(p, d, {(p["key"], tid): "Lofts"}, TENANT)      # answered: the product's own
    assert en[tid] == "Lofts" and by[tid] == "product" and tid not in {i["id"] for i in pending}


def test_a_latin_name_that_is_no_placeholder_is_not_asked(tmp_path):
    import translation_dicts as D
    p = _colour_product()
    p["notes"] = []
    _, by, pending = T.plan(p, D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none")), {}, TENANT)
    assert by[transform.text_id("option_name", "Color")] == "rule"
    assert transform.text_id("option_name", "Color") not in {i["id"] for i in pending}


# ---- C54 / C55: option values ------------------------------------------------------------------------------------

@pytest.mark.parametrize("ko, out", [
    ("5056", "50°/56°"), ("525660", "52°/56°/60°"), ("5652", "5652"), ("5157", "5157"),
    ("56.12 SB", "56° (Bounce 12°) SB"), ("52.09", "52° (Bounce 9°)"),
    ("50°56°", "50°/56°"), ("50도56도", "50°/56°"),
    ("52 56 60 Degree Set", "52°/56°/60° Set"), ("1 52 56 60 Degree Set Tar", "1 52°/56°/60° Set Tar"),
    ("52 56 degree (2PCS)", "52°/56° (2PCS)"), ("56 60° (2 pcs )", "56°/60° (2 pcs )"),
    ("52 56° (2 pcs ) 1 pcs", "52°/56° (2 pcs )"), ("52 56도 (2개) 1개", "52°/56° (2 pcs )"),
    ("52 56 60 Degree Set 1개", "52°/56°/60° Set"), ("50 54 58 Degree/ Legal", "50°/54°/58° Legal"),
    ("60 56 Degree", "60 56 Degree"), ("Black 52 56 60 Degrees", "Black 52°/56°/60°"),
])
def test_loft_values_of_wedge_sets(ko, out):
    assert sanitize("option_value", ko, TENANT, WEDGES) == out


@pytest.mark.parametrize("ko, out", [
    ("블랙 1개", "블랙 1 pcs"), ("56도 1개", "56° 1 pcs"), ("Black 1 pcs", "Black 1 pcs"),
    ("52 56도 (2개) 1개", "52°/56° (2 pcs )"), ("52 56 60 Degree Set 1개", "52°/56°/60° Set"),
    ("블랙 (우타) 1개", "블랙 (우타) 1 pcs"), ("레드(L) 1개", "레드(L) 1 pcs"), ("Offset 1개", "Offset 1 pcs"),
])
def test_one_pcs_tail_only_after_a_set(ko, out):
    """C54 narrow form: the " 1 pcs" tail goes only after "(2 pcs )" or "Set"; any other value keeps its count."""
    assert sanitize("option_value", ko, TENANT, WEDGES) == out
    if "(" not in ko and "Set" not in ko:
        assert sanitize("option_value", ko, TENANT, WEDGES) == sanitize("option_value", ko, TENANT, SETS)


@pytest.mark.parametrize("cat", [SETS, JUNIOR, "50002670"])
def test_loft_values_only_in_wedge_sets(cat):
    for ko in ("5056", "56.12 SB", "52 56 60 Degree Set"):
        assert sanitize("option_value", ko, TENANT, cat) == ko
    assert sanitize("option_name", "5056", TENANT, WEDGES) == "5056"            # option values only


@pytest.mark.parametrize("ko, out", [
    ("7 Sliver 52 56 60 Degree", "7 Silver 52 56 60 Degree"), ("sliver", "silver"), ("Slivers", "Slivers"),
    ("Sliverado", "Sliverado"),
])
def test_sliver_is_silver(ko, out):
    assert sanitize("fact_value", ko, TENANT, SETS) == out
    assert sanitize("review", ko, TENANT, SETS) == ko                           # reviews as written


def test_the_slots_rule_stays_out_of_other_categories():
    """The MG5 line filed under 50002788 (golf sets, no wedge_sets): its 343 rows are capped as before."""
    p = prep("12742411646")
    q = copy.deepcopy(line("12742411646"))
    q["specs"]["category"] = {"id": SETS, "name": "골프풀세트"}
    other = prepare(q, RULES, "50002788-fixtures", 1)
    assert "slot_rows_merged" in notes(p) and "slot_rows_merged" not in notes(other)
