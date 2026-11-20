"""apparel_sizes: Korean apparel sizes -> US sizes per product, the seller's chart, the size chart block
(the owner, 2026-11-19; scripts/SIZES.md). The golden cases are the 30 drafts of the knit cardigan pilot:
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_apparel_sizes.py     # after a deliberate rule change
"""
import json
import os
from pathlib import Path
from typing import Any

import pytest

import apparel_sizes as A

PILOT = Path(__file__).parent / "fixtures" / "sizes" / "pilot_50002797.json"


def _load() -> dict[str, Any]:
    return json.loads(PILOT.read_text(encoding="utf-8"))


def _run(p: dict[str, Any]) -> dict[str, Any]:
    return A.resolve(p["options"], p["lines"], p["brand_ko"], p["title_ko"], "womens_tops")


def test_the_pilot_golden():
    """Every one of the 30 pilot drafts maps (none held), each value as checked by hand on 2026-11-19."""
    data = _load()
    if os.environ.get("UPDATE_GOLDEN"):
        for p in data["products"]:
            r = _run(p)
            p["expected"] = {"values": [[v["ko"], v["us"], v["basis"]] for v in r["values"]], "merged": r["merged"],
                             "held": r["held"], "chart": r["chart"]}
        PILOT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for p in data["products"]:
        r = _run(p)
        got = {"values": [[v["ko"], v["us"], v["basis"]] for v in r["values"]], "merged": r["merged"],
               "held": r["held"], "chart": r["chart"]}
        assert got == p["expected"], p["pid"]
    assert not any(p["expected"]["held"] for p in data["products"])


def _pilot(pid: str) -> dict[str, Any]:
    return next(p for p in _load()["products"] if p["pid"] == pid)


@pytest.mark.parametrize("pid, us", [
    # the same letter means different sizes at different sellers: the number decides (the 2026-11-19 review)
    ("13726067141", ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),   # Munsingwear S = 85 (its chart)
    ("12859886115", ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),                  # S(90)
    ("9717223659", ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),                   # M(90): S in the US
    ("7536064331", ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),                   # M(55): women's 55 = 90
    ("13824504540", ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)"]),                   # Pearly Gates 0(85) 1(90)
    ("11160224814", ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),   # reversed, "Korea Size" row
    ("6529527715", ["S-M (US 4-10)", "L-XL (US 12-16)"]),                            # L(55-66): a range
    ("7562982095", ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)", "XL (US 16)"]),   # PXG: US
])
def test_the_number_decides_not_the_letter(pid, us):
    assert [v["us"] for v in _run(_pilot(pid))["values"]] == us


def test_a_size_written_twice_is_one_value():
    r = _run(_pilot("11107936517"))           # "M (66)" and "M(66)"
    assert r["merged"] == {"M(66)": "M (66)", "L(77)": "L (77)"}
    assert [v["us"] for v in r["values"]] == ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]


def test_the_size_option_is_found_by_its_values():
    r = _run(_pilot("13665521998"))           # WAAC: the option is named "PIL[핑크]"
    assert r["option"] == 0 and r["brand_row"] == "WAAC"


@pytest.mark.parametrize("text, letter, chest, women, free", [
    ("M(90)", "M", (90,), (), False), ("85 (S)", "S", (85,), (), False), ("100(LL)", "LL", (100,), (), False),
    ("L(55-66)", "L", (), (55, 66), False), ("FREE", None, (), (), True), ("FREE(44-66반)", None, (), (44, 66.5), True),
    ("95(55-66)", None, (95,), (55, 66), False), ("xL(100)", "XL", (100,), (), False), ("2XL", "XXL", (), (), False),
])
def test_labels(text, letter, chest, women, free):
    label = A.parse_label(text)
    assert label is not None
    assert (label.letter, label.chest, label.women, label.free) == (letter, chest, women, free)


@pytest.mark.parametrize("text", ["블랙", "그레이", "앞면로고", "라운드", "C5:그레이", "바닐라 (모델착용)"])
def test_a_colour_is_not_a_size(text):
    assert A.parse_label(text) is None


def test_an_unknown_value_holds_rather_than_invents():
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["3(105)", "4"]}], [], None, "여성 가디건", "womens_tops")
    assert r["held"] and not r["values"]


def test_two_korean_sizes_on_one_us_size_hold():
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["90", "91"]}], [], None, "여성 가디건", "womens_tops")
    assert r["held"] and "one US size" in r["held"]


def test_the_chart_reads_both_layouts():
    rows = A.read_chart(["사이즈 | 어깨너비 | 가슴둘레 | 총길이 | 소매길이", "85 (S) | 39 | 95 | 54 | 57"]).rows
    assert rows == {"85 (S)": {"shoulder": 39.0, "chest": 95.0, "length": 54.0, "sleeve": 57.0}}
    chart = A.read_chart(["사이즈 / M(90) / L(95)", "가슴너비 / 46 / 48.5", "Sleeve / 16 / 17",
                          "Sleeve Length / 57 / 58"])
    assert chart.rows == {"M(90)": {"chest": 46.0, "sleeve": 57.0}, "L(95)": {"chest": 48.5, "sleeve": 58.0}}
    assert chart.kinds["chest"] == "flat"
    pairs = A.read_chart(["S(90)-총장56/어깨37/가슴48/소매58"]).rows
    assert pairs == {"S(90)": {"length": 56.0, "shoulder": 37.0, "chest": 48.0, "sleeve": 58.0}}


def test_the_chart_block_is_in_inches_and_doubles_a_flat_chest():
    html = A.chart_html(_run(_pilot("9717223659")))
    assert "Size chart (US)" in html and "<td>S (US 4-6)</td>\n<td>34–35.5 in</td>\n<td>36 in</td>" in html
    assert "90" not in html                        # no Korean size on the storefront


def test_one_size_with_measurements():
    r = _run(_pilot("11398329919"))
    assert r["option"] is None and r["chart"]["rows"][0]["us"] == "One Size"
    assert "<td>One Size</td>\n<td>42.5 in</td>" in A.chart_html(r)    # garment chest 54 cm flat = 42.5 in


# ---- the 2026-11-19 review's cases ---------------------------------------------------------------------------------

def _resolve(values, texts=(), brand=None, title="여성 가디건", name="사이즈"):
    return A.resolve([{"name_ko": name, "values_ko": list(values)}], list(texts), brand, title, "womens_tops")


@pytest.mark.parametrize("values", [["S(55)", "M(66)", "L(77+)"], ["XS", "S", "XXS(3)"], ["M", "L", "가디건 XL"]])
def test_an_unread_value_of_the_size_option_holds_never_reaches_the_store(values):
    r = _resolve(values)
    assert r["option"] == 0 and r["held"] and "not read" in r["held"] and not r["values"]


@pytest.mark.parametrize("text, free, women", [
    ("ONE SIZE", True, ()), ("원사이즈", True, ()), ("ONESIZE", True, ()), ("FREE SIZE(44-77)", True, (44, 77)),
    ("FREESIZE(55-66)", True, (55, 66)), ("프리사이즈(55-66)", True, (55, 66)), ("L(77~)", False, (77,)),
])
def test_free_and_open_ranges(text, free, women):
    label = A.parse_label(text)
    assert label is not None and label.free is free and label.women == women


def test_a_letter_range():
    r = _resolve(["S/M", "L/XL"])
    assert [v["us"] for v in r["values"]] == ["S-M (US 4-10)", "L-XL (US 12-16)"] and not r["held"]


def test_a_half_size_holds():
    assert _resolve(["55반", "66반"])["held"]


def test_a_shop_policy_line_is_no_chest():
    chart = A.read_chart(["-최초 배송비 무료인 경우/반품상품 제외 구매상품금액 7만원 이하인 경우", "상품번호 123",
                          "총장59 어깨53 가슴54 소매54"])
    assert chart.rows == {A.ONE: {"length": 59.0, "shoulder": 53.0, "chest": 54.0, "sleeve": 54.0}}


def test_a_model_line_is_no_chart_row_and_sets_no_kind():
    texts = ["모델 신장 165 / 가슴둘레 82 / 허리 63", "66 착용 / 키 165 / 가슴 84", "사이즈 | 어깨너비 | 가슴단면 | 총장",
             "M(66) | 37 | 46 | 56", "L(77) | 38 | 48 | 58"]
    r = _resolve(["M(66)", "L(77)"], texts)
    assert r["chart"]["rows"][0] == {"us": "M (US 8-10)", "cm": {"shoulder": 37.0, "chest": 46.0, "length": 56.0}}
    assert r["chart"]["kinds"]["chest"] == "flat" and "<td>36 in</td>" in A.chart_html(r)


def test_a_bare_header_label_does_not_take_the_measured_row():
    texts = ["SIZE / S / M / L", "사이즈 | 어깨 | 가슴단면 | 총장", "S(85) | 37 | 46 | 56", "M(90) | 38 | 48 | 58",
             "L(95) | 39 | 50 | 60"]
    r = _resolve(["S", "M", "L"], texts)
    assert r["chart"] and len(r["chart"]["rows"]) == 3


def test_a_row_of_size_like_numbers_under_a_header_is_a_row():
    chart = A.read_chart(["사이즈 | 가슴둘레 | 밑단둘레 | 총장", "S | 92 | 88 | 55", "M | 96 | 92 | 57"])
    assert chart.rows["S"] == {"chest": 92.0, "length": 55.0} and chart.rows["M"]["chest"] == 96.0


def test_a_one_letter_alias_needs_a_word_of_its_own():
    table = A.grids()["profiles"]["womens_tops"]
    assert A.brand_row(table, "루이까스텔", "왁스 코팅 니트 가디건") is None
    assert A.brand_row(table, None, "[왁] 여성 골프 와키 캐시미어 니트 가디건")[0] == "WAAC"
    assert A.brand_row(table, "왁", "왁[WAAC] 여성 핀스트라이프 가디건")[0] == "WAAC"


def test_the_chart_note_trips_no_description_check():
    import describe
    html = A.chart_html(_run(_pilot("9717223659")))
    assert html.startswith(A.CHART_MARK)
    note = html.rsplit("<p>", 1)[1].split("</p>")[0]
    assert describe.packet_free_problems(note) == []


# ---- the payload and the transform (the 2026-11-19 review) ----------------------------------------------------------

import shopify_payload as SP  # noqa: E402
import transform as T  # noqa: E402
from transform import text_id  # noqa: E402


def _en(pairs):
    return SP.English({"en": {text_id(kind, ko): en for kind, ko, en in pairs}})


SIZES = {"profile": "womens_tops", "option": 1, "values": [
    {"ko": "90", "us": "S (US 4-6)", "letter": "S", "chest_cm": 90, "basis": "label"},
    {"ko": "95", "us": "M (US 8-10)", "letter": "M", "chest_cm": 95, "basis": "label"}]}


def test_size_keeps_its_name_when_another_option_translates_to_size():
    product = {"options": [{"name_ko": "타입", "values_ko": ["A"]}, {"name_ko": "사이즈", "values_ko": ["90", "95"]}],
               "sizes": SIZES}
    en = _en([("option_name", "타입", "Size"), ("option_value", "A", "Type A")])
    options, values = SP._options(product, en)
    assert [o["name"] for o in options] == ["Size 1", "Size"] and values[1] == ["S (US 4-6)", "M (US 8-10)"]


def test_the_size_option_index_follows_twins():
    before = {"options": [{"name_ko": "색상", "values_ko": ["블랙"]}, {"name_ko": "색상", "values_ko": ["블랙"]},
                          {"name_ko": "사이즈", "values_ko": ["90", "95"]}], "sizes": {**SIZES, "option": 2}}
    after = {**before, "options": [before["options"][0], before["options"][2]]}
    assert SP._sizes_after_twins(before, after)["sizes"]["option"] == 1
    assert SP._sizes_after_twins(before, before) is before


def test_a_size_fact_is_the_us_size():
    product = {"options": [], "facts": [{"label_ko": "사이즈", "value_ko": "FREE(44-66반)"}],
               "sizes": {"profile": "womens_tops", "option": None, "values": [],
                         "fact": {"label_ko": "사이즈", "ko": "FREE(44-66반)", "us": "One Size"}}}
    assert SP._single(product, _en([])) == ("Size", "One Size")


def _ov(rows):
    return {"options": [{"name_ko": "사이즈", "values_ko": ["M(66)", "M (66)"]}], "facts": [],
            "variants": [{"sku": f"v{n}", "options_ko": [ko], "price_krw": price, "available": ok}
                         for n, (ko, price, ok) in enumerate(rows)]}


def test_a_merged_size_keeps_the_buyable_row():
    ov = _ov([("M(66)", 50000, False), ("M (66)", 50000, True)])
    out = T._sizes(ov, "womens_tops", "", [], None, "여성 가디건")
    assert not out["held"] and len(ov["variants"]) == 1 and ov["variants"][0]["sku"] == "v1"


def test_a_size_written_twice_at_two_prices_holds():
    ov = _ov([("M(66)", 50000, True), ("M (66)", 55000, True)])
    assert "two prices" in T._sizes(ov, "womens_tops", "", [], None, "여성 가디건")["held"]


def test_a_size_fact_resolves_and_an_unread_one_holds():
    ov = {"options": [], "variants": [], "facts": [{"label_ko": "사이즈", "value_ko": "FREE(44-66반)"}]}
    assert T._sizes(ov, "womens_tops", "", [], None, "여성 가디건")["fact"]["us"] == "One Size"
    ov = {"options": [], "variants": [], "facts": [{"label_ko": "사이즈", "value_ko": "가디건용"}]}
    assert T._sizes(ov, "womens_tops", "", [], None, "여성 가디건")["held"]


# ---- the size-table study (2026-11-19: all 36 tables of the 30 pilot products; scripts/SIZE_CHARTS.md) ----------------

import size_chart as C  # noqa: E402


def test_f1_f2_f3_cm_and_inches_in_cells_a_header_without_its_size_cell_and_two_header_lines():
    rows = C.read_chart(["가슴둘레 / 총장", "총장 / 어깨너비 / 가슴둘레 / 소매기장",
                         "Total Length / Shoulder Width / Chest Circ. / Sleeve Length",
                         "90 (S) / 55cm (21.7in) / 39cm (15.4in) / 93cm (36.6in) / 57cm (22.4in)"]).rows   # 13722416544
    assert rows == {"90 (S)": {"length": 55.0, "shoulder": 39.0, "chest": 93.0, "sleeve": 57.0}}
    assert C.read_chart(["사이즈 / 가슴", "S / 21.7in"]).rows == {}        # inches alone are never read as cm


def test_f4_one_size_column():
    chart = C.read_chart(["SIZE INFO / 단위:cm", "호칭 / FREE(66-88)", "가슴둘레 / 126", "총길이 / 65", "어깨너비 / 60",
                          "소매길이 / 48", "밑단단면 / 51"])                                              # 13823433220
    assert chart.rows == {"FREE(66-88)": {"chest": 126.0, "length": 65.0, "shoulder": 60.0, "sleeve": 48.0}}
    assert C.read_chart(["사이즈 / 90, 95, 100, 105", "가슴 / 49"]).labels.get("90, 95, 100, 105") is None


def test_f5_the_unit_in_brackets_and_two_cell_lines():
    chart = C.read_chart(["어깨(cm): 40", "가슴(cm):46", "소매기장(cm):62", "총장(cm):52"])               # 9992270463
    assert chart.rows == {C.ONE: {"shoulder": 40.0, "chest": 46.0, "sleeve": 62.0, "length": 52.0}}
    assert C.read_chart(["가슴 / 46", "총장 / 52"]).rows == {C.ONE: {"chest": 46.0, "length": 52.0}}


def test_f6_one_size_blocks_per_type():
    lines = ["니트집업가디건 (앞면 로고형)", "상세사이즈(cm)", "총장59/어깨54/가슴56/소매54", "니트집업가디건 (뒷면로고형)",
             "상세사이즈(cm)", "총장60/어깨53/가슴55/소매54"]                                               # 10885610305
    chart = C.read_chart(lines, sections=["앞면로고", "뒷면로고"])
    assert chart.sections == {f"{C.ONE}#앞면로고": "앞면로고", f"{C.ONE}#뒷면로고": "뒷면로고"}
    plain = C.read_chart(lines)
    assert plain.rows[C.ONE]["length"] == 59.0 and plain.conflicts == ["length 60 shoulder 53 chest 55 sleeve 54"]
    r = A.resolve([{"name_ko": "타입", "values_ko": ["앞면로고", "뒷면로고"]},
                   {"name_ko": "컬러", "values_ko": ["그린", "그레이"]}], lines, None, "여성 가디건", "womens_tops")
    html = A.chart_html(r, section_en={"앞면로고": "Front Logo", "뒷면로고": "Back Logo"}.get)
    assert "<td>One Size (Front Logo)</td>" in html and "<td>One Size (Back Logo)</td>" in html


def test_f7_arm_length_is_the_sleeve_never_arm_girth_or_centre_back():
    chart = C.read_chart(["사이즈 / M(90) / L(95) / XL(100)", "팔길이 / 55 / 56 / 57", "팔둘레 / 16 / 17 / 18",
                          "화장 / 73 / 74 / 75"])
    assert chart.rows["M(90)"] == {"sleeve": 55.0}


def test_f8_a_note_gives_the_kind_where_the_table_gave_none():
    chart = C.read_chart(["*상세치수는 단면기준 cm", "S 총장 54 어깨 41 가슴 53"])
    assert chart.kinds["chest"] == "flat"
    chart = C.read_chart(["둘레는 상품을 바닥에 놓고 ×2사이즈입니다.", "사이즈 / 가슴 / 총장", "90 / 100 / 59"])
    assert chart.kinds["chest"] == "circ"


def test_f9_ocr_spellings():
    chart = C.read_chart(["사이즈 / 가슴들레 / 어깨넓이", "90 / 100 / 40"])
    assert chart.kinds == {"chest": "circ", "shoulder": "flat"}


@pytest.mark.parametrize("line", ["체형 가슴 90", "WOMAN 170cm 49kg (S)", "키 161cm, 뱃살 많은 66사이즈 모델이 착용",
                                  "무게 / 381g(L Size)", "가슴 / 2", "2.가슴둘레 : 겨드랑이 1cm 밑 지점의 둘레"])
def test_lines_that_are_never_measurements(line):
    assert C.read_chart([line]).rows == {}


def test_a_measure_set_is_data():
    assert C.describe_sets() == {"tops": ["chest", "sleeve", "length", "shoulder"]}
    assert A.grids()["profiles"]["womens_tops"]["measures"] in C.MEASURE_SETS


# ---- the second review (2026-11-19) -------------------------------------------------------------------------------

def test_a_second_tables_word_never_relabels_the_first_tables_values():
    chart = C.read_chart(["사이즈 / S / M / L", "가슴단면 / 46 / 48 / 50", "가슴둘레 / 92 / 96 / 100"])
    assert chart.rows["S"]["chest"] == 46.0 and chart.kinds["chest"] == "flat"


@pytest.mark.parametrize("lines, kind", [
    (["*상세치수는 단면기준 cm", "사이즈 | 어깨 | 가슴 | 총장", "S | 38 | 92 | 60", "M | 39 | 97 | 61"], None),
    (["가슴단면", "사이즈 | 어깨 | 가슴 | 총장", "S | 38 | 92 | 60"], None),
    (["둘레는 x2 사이즈입니다", "사이즈 | 가슴 | 총장", "S | 46 | 60", "M | 48 | 62"], None),
])
def test_a_note_kind_that_the_numbers_contradict_is_ignored(lines, kind):
    assert C.read_chart(lines).kinds.get("chest") is kind


@pytest.mark.parametrize("line, want", [
    ("S 어깨 38 가슴 48 소매 기장 58 총 기장 60", {"shoulder": 38.0, "chest": 48.0, "sleeve": 58.0, "length": 60.0}),
    ("M 팔 기장 57 총장 62 가슴 50", {"sleeve": 57.0, "length": 62.0, "chest": 50.0}),
])
def test_spaced_measure_words(line, want):
    assert next(iter(C.read_chart([line]).rows.values())) == want


def test_a_block_before_any_types_heading_keeps_its_place():
    lines = ["상세사이즈(cm)", "총장59/어깨54/가슴56/소매54", "(뒷면로고형)", "총장60/어깨53/가슴55/소매54"]
    r = A.resolve([{"name_ko": "타입", "values_ko": ["앞면로고", "뒷면로고"]}], lines, None, "여성 가디건", "womens_tops")
    assert [(x.get("section_ko"), x["cm"]["length"]) for x in r["chart"]["rows"]] == [("앞면로고", 59.0), ("뒷면로고", 60.0)]


def test_prose_naming_a_type_is_no_heading_and_a_measured_line_is_read():
    lines = ["(앞면 로고형)", "앞면로고 타입은", "뒷면로고 타입(베이직핏)보다", "총장59/어깨54/가슴56/소매54"]
    chart = C.read_chart(lines, sections=["앞면로고", "뒷면로고"])
    assert list(chart.sections.values()) == ["앞면로고"]
    assert C.read_chart(["앞면로고 총장59 가슴56"], sections=["앞면로고", "뒷면로고"]).rows


def test_a_diagram_header_does_not_block_one_size_lines():
    assert C.read_chart(["어깨너비 / 가슴둘레", "총장59/어깨54/가슴56/소매54"]).rows[C.ONE]["length"] == 59.0


def test_a_one_size_column_takes_the_pairs_line_after_it():
    assert C.read_chart(["사이즈 | FREE", "총장59/어깨54/가슴56/소매54"]).rows == {
        "FREE": {"length": 59.0, "shoulder": 54.0, "chest": 56.0, "sleeve": 54.0}}


@pytest.mark.parametrize("corner", ["구분", "단위(cm)"])
def test_a_corner_word_heads_the_columns(corner):
    assert C.read_chart([f"{corner} / S / M / L", "가슴단면 / 46 / 48 / 50"]).rows["S"] == {"chest": 46.0}


def test_free_sold_in_types_shows_a_row_per_type():
    r = A.resolve([{"name_ko": "종류", "values_ko": ["앞면로고형", "뒷면로고형"]}, {"name_ko": "사이즈", "values_ko": ["FREE"]}],
                  ["앞면로고형", "총장59 어깨40 가슴50", "뒷면로고형", "총장62 어깨42 가슴53"], None, "여성 가디건",
                  "womens_tops")
    assert [x["section_ko"] for x in r["chart"]["rows"]] == ["앞면로고형", "뒷면로고형"]


def test_size_like_or_colour_options_are_no_sections():
    r = A.resolve([{"name_ko": "핏", "values_ko": ["S", "R"]}, {"name_ko": "사이즈", "values_ko": ["S", "M"]}],
                  ["사이즈 / 85(S) / 90(M)", "가슴 / 44 / 46", "총장 / 56 / 58"], None, "여성 가디건", "womens_tops")
    assert r["values"][0]["us"] == "XS (US 0-2)" and r["values"][0]["basis"] == "chart_pair"
    r = A.resolve([{"name_ko": "선택", "values_ko": ["블랙", "네이비"]}], ["COLOR : 블랙 / 네이비", "총장59 어깨40 가슴50"],
                  None, "여성 가디건", "womens_tops")
    assert "section_ko" not in r["chart"]["rows"][0]


def test_the_chart_is_built_as_shopify_stores_it():
    """2026-11-19: Shopify rewrote the table with line breaks, so store_diff and sweep read every draft as changed;
    the block is built in its stored form (the one-row tbody inline, several rows a line each)."""
    one = A.chart_html(_run(_pilot("11398329919")))
    assert '<tbody><tr>\n<td>One Size</td>\n<td>42.5 in</td>' in one and "</tr></tbody>\n</table>" in one
    assert "Fits bust" not in one and "<p>The garment measurements are the maker's" in one
    many = A.chart_html(_run(_pilot("9717223659")))
    assert '<table class="size-chart">\n<thead><tr>\n<th>Size</th>\n' in many and "</tr>\n</tbody>\n</table>" in many


def test_apparel_option_values_lose_colour_codes_and_model_notes():
    """2026-11-20: "C5: Gray", "Z1: Black", "Vanilla (Worn by Model)" and an option named "Windproof Cardigan Color"
    on the storefront; the rule reads only apparel (a product with sizes), the clubs' values stay."""
    product = {"options": [{"name_ko": "방풍 가디건 컬러", "values_ko": ["C5:그레이", "바닐라 (모델착용)"]}],
               "sizes": {"profile": "womens_tops", "option": None, "values": []}}
    en = _en([("option_name", "방풍 가디건 컬러", "Windproof Cardigan Color"), ("option_value", "C5:그레이", "C5: Gray"),
              ("option_value", "바닐라 (모델착용)", "Vanilla (Worn by Model)")])
    options, values = SP._options(product, en)
    assert options[0]["name"] == "Color" and values[0] == ["Gray", "Vanilla"]
    club = {"options": [{"name_ko": "샤프트", "values_ko": ["R2:레귤러"]}]}
    options, values = SP._options(club, _en([("option_name", "샤프트", "Shaft Color"), ("option_value", "R2:레귤러", "R2: Regular")]))
    assert options[0]["name"] == "Shaft Color" and values[0] == ["R2: Regular"]


def test_the_first_waves_labels():
    """2026-11-20, the first knit wave: PXG 5429994082 "XS (33~44)" and "2XS", 5932679597 "FREE[55~66]"."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["XS (33~44)", "S (55)", "M (66)", "2XS"]}], [], "PXG",
                  "PXG 여성골프웨어 바시티 브이넥 스웨터 니트 가디건", "womens_tops")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["XXS (US 00)", "XS (US 0-2)", "S (US 4-6)",
                                                                "M (US 8-10)"]
    label = A.parse_label("FREE[55~66]")
    assert label is not None and label.free and label.women == (55, 66)
