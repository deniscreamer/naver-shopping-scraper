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


@pytest.mark.parametrize("values", [["S(55)", "M(66)", "L(77+)"], ["XS", "S", "XXS(3)"], ["M", "L", "가디건 XL"],
                                    # 2026-11-21 (the second windbreaker pilot): an option named a size with no value
                                    # read went out raw, no US size, no hold
                                    ["W", "WHITE"], ["A.0", "B.1", "C.2"], ["0호", "1호", "2호"]])
                                    # "S(상세사이즈 확인했습니다)" reads as S since 2026-11-22 (a note in brackets),
                                    # "WS / WM / WL" as S / M / L since 2026-11-24 (13483086996)
def test_an_unread_value_of_the_size_option_holds_never_reaches_the_store(values):
    r = _resolve(values)
    assert r["option"] == 0 and r["held"] and "not read" in r["held"] and not r["values"]


@pytest.mark.parametrize("text, free, women", [
    ("ONE SIZE", True, ()), ("원사이즈", True, ()), ("ONESIZE", True, ()), ("FREE SIZE(44-77)", True, (44, 77)),
    ("FREESIZE(55-66)", True, (55, 66)), ("프리사이즈(55-66)", True, (55, 66)), ("L(77~)", False, (77,)),
    ("L（FREE）", True, ()), ("XL(프리)", True, ()),                 # a one-size poncho under a letter (2026-11-24)
])
def test_free_and_open_ranges(text, free, women):
    label = A.parse_label(text)
    assert label is not None and label.free is free and label.women == women


def test_a_letter_with_its_chest_in_ho():
    """Titleist Japan rainwear (4819248041, 2026-11-24): "S(90호)" is S with a 90 chest; a bare "0호" stays unread."""
    label = A.parse_label("S(90호)")
    assert label is not None and label.letter == "S" and label.chest == (90.0,)
    assert A.parse_label("0호") is None



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


def test_a_merged_variant_keeps_its_own_naver_value():
    """2026-11-25 (the re-review): a merged spelling must never become the value the owner orders: the variant whose
    Naver row says "M(66)" keeps it as naver_options_ko, the store shows the kept spelling."""
    ov = {"options": [{"name_ko": "컬러", "values_ko": ["블랙", "화이트"]},
                      {"name_ko": "사이즈", "values_ko": ["M(66)", "M (66)"]}], "facts": [],
          "variants": [{"sku": "v0", "options_ko": ["블랙", "M(66)"], "price_krw": 50000, "available": True},
                       {"sku": "v1", "options_ko": ["화이트", "M (66)"], "price_krw": 50000, "available": True}]}
    out = T._sizes(ov, "womens_tops", "", [], None, "여성 가디건")
    assert not out["held"] and out["merged"]
    by_sku = {v["sku"]: v for v in ov["variants"]}
    kept = out["merged"].get("M(66)") or "M(66)"
    for sku, own in (("v0", "M(66)"), ("v1", "M (66)")):
        v = by_sku[sku]
        assert v["options_ko"][1] == kept
        assert v.get("naver_options_ko", v["options_ko"])[1] == own


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
    assert C.describe_sets() == {"tops": ["chest", "sleeve", "length", "shoulder"],
                                 "bottoms": ["waist", "hip", "length"],                     # skirts (2026-11-22)
                                 "trousers": ["waist", "hip", "thigh", "rise", "hem", "inseam", "length"]}   # 2026-11-23
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
    main = {"options": [{"name_ko": "컬러", "values_ko": ["그레이(메인모델착용)"]}],
            "sizes": {"profile": "womens_bottoms", "option": None, "values": []}}
    assert SP._options(main, _en([("option_name", "컬러", "Color"),          # 5896682316 (2026-11-22)
                                  ("option_value", "그레이(메인모델착용)", "Gray (Worn by Main Model)")]))[1][0] == ["Gray"]
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


# ---- the 2026-11-20 lens review of the knit cardigan drafts (job fairwardgolf-50002797-20261120T084807Z) --------------

@pytest.mark.parametrize("pid, values, texts, want", [
    # the description's "★SIZE" line (10036686854)
    ("10036686854", ["L", "XL"], ["★SIZE", "L[55~66]/XL[77]", "[모델착용사이즈 L]", "166cm/56kg/마른66size"],
     ["S-M (US 4-10)", "L (US 12-14)"]),
    # the description's "SIZE." line (11016233632)
    ("11016233632", ["M", "L", "XL"], ["SIZE.", "M(55), L(66), XL(77)"],
     ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),
    # the OCR rows whose measures are not read (12220300865): the pairing taken, the chart kept out
    ("12220300865", ["L", "XL"], ["Size(cm) / 어깨 / 가슴 / 소매 / 암홀 / 총기장", "L(55-66) / 48 / 20 / 58",
                                  "XL(77) / 50.5 / 21 / 59", "모델: Height 171 Bast 35 Waist 26 Hip 36/L착용"],
     ["S-M (US 4-10)", "L (US 12-14)"]),
    # the OCR glued two pairs, the third after a stray bracket (Toosom 12566658191, 2026-11-21: M sold as US M)
    ("12566658191", ["M", "L", "XL"], ["M(55)L(66) | ) XL(77)"], ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),
])
def test_a_bare_letter_takes_the_women_size_the_seller_pairs_it_with(pid, values, texts, want):
    r = _resolve(values, texts)
    assert not r["held"] and [v["us"] for v in r["values"]] == want, pid
    assert {v["basis"] for v in r["values"]} == {"text_pair"}
    if pid == "12220300865":
        assert r["chart"] is None


def test_a_chart_label_pairing_a_letter_with_women_sizes_is_used():
    """9353856438: the chart's rows "55~66(L)" / "77(XL)" matched the bare letters but fell back to S = 90."""
    texts = ["55~66(L) : 총장 59 어깨 35 가슴 45 소매 58", "77(XL) : 총장 61 어깨 37 가슴 47 소매 60", "55~66(L)",
             "77 (XL) 까지"]
    r = _resolve(["L", "XL"], texts)
    assert [(v["us"], v["basis"], v["chart_label"]) for v in r["values"]] == [
        ("S-M (US 4-10)", "chart_pair", "55~66(L)"), ("L (US 12-14)", "chart_pair", "77(XL)")]
    assert [row["us"] for row in r["chart"]["rows"]] == ["S-M (US 4-10)", "L (US 12-14)"]


def test_a_letter_paired_with_two_numbers_keeps_todays_reading():
    """L written with 55-66 and with 77: no pairing for L (never a guess), so XL's one pairing is not taken either:
    today's letters for both."""
    r = _resolve(["L", "XL"], ["L(55-66)/XL(88)", "L(77)"])
    assert [(v["us"], v["basis"]) for v in r["values"]] == [("L (US 12-14)", "fallback_letters"),
                                                            ("XL (US 16)", "fallback_letters")]


@pytest.mark.parametrize("values, texts", [
    (["M", "L", "XL"], ["★SIZE", "L[55~66]/XL[77]"]),                # 10036686854's line over an M it does not pair
    (["M", "L", "XL"], ["55~66(L) : 총장 59 어깨 35 가슴 45 소매 58", "77(XL) : 총장 61 어깨 37 가슴 47 소매 60"]),
])
def test_women_pairs_for_only_some_letters_keep_todays_reading(values, texts):
    """2026-11-20 review: M by the letters (M = US 8-10) beside L by "55~66" (S-M, US 4-10) would overlap and invert;
    a pairing that misses a bare letter of the option is not used, today's letters stay for all."""
    r = _resolve(values, texts)
    assert not r["held"] and [(v["us"], v["basis"]) for v in r["values"]] == [
        ("M (US 8-10)", "fallback_letters"), ("L (US 12-14)", "fallback_letters"), ("XL (US 16)", "fallback_letters")]


def test_several_sizes_listed_without_a_size_option_hold():
    """13004790971: no option, no size fact, the OCR's chart lists 95..110 (the title ends "블랙, 105"): which size
    is sold is unknown."""
    rows = ["Size Guide", "95,100,105,110", "(단위 : CM /단면)", "구 분 / 가슴너비 / 어깨너비 / 소매기장 / 총기장",
            "95 / 50 / 41.5 / 61 / 62", "100 / 52 / 42.5 / 61.5 / 64", "105 / 54 / 43.5 / 62 / 66",
            "110 / 56 / 44.5 / 62.5 / 68", "95 SIZE 착용"]
    ov: dict[str, Any] = {"options": [], "variants": [], "facts": []}
    held = T._sizes(ov, "womens_tops", "", [rows], None, "베러투데이 여성 가을 니트 코디 빅사이즈 골프웨어 사계절 포켓 가디건 블랙, 105")
    assert held["held"] and "which size is sold is unknown" in held["held"] and "95, 100, 105, 110" in held["held"]
    # narrow: one size in the chart, or a FREE fact, is no unknown size
    ov = {"options": [], "variants": [], "facts": []}
    assert not T._sizes(ov, "womens_tops", "", [rows[3:5]], None, "여성 가디건")["held"]
    ov = {"options": [], "variants": [], "facts": [{"label_ko": "사이즈", "value_ko": "FREE"}]}
    one = T._sizes(ov, "womens_tops", "", [rows], None, "여성 가디건")
    assert not one["held"] and one["fact"]["us"] == "One Size"


@pytest.mark.parametrize("values", [["Ivory/085", "Ivory/090"],                          # 12487887784 "선택하기"
                                    ["오프화이트 85 XS", "오프화이트 90 S", "티블루 95 M", "블랙 100 L"]])   # 10940191023
def test_colour_and_size_in_one_option_hold(values):
    r = _resolve(values, name="선택하기")
    assert r["option"] is None and r["held"] and "colour and size in one option" in r["held"]


@pytest.mark.parametrize("values", [["블랙 FREE", "화이트 FREE"], ["앞면로고 1", "뒷면로고 2"], ["블랙", "화이트"],
                                    ["Ivory/085"]])
def test_a_colour_with_one_size_or_a_type_number_is_not_joined(values):
    assert not _resolve(values, name="선택하기")["held"]


# ---- the 2026-11-20 lens review: reading the seller's chart (scripts/SIZE_CHARTS.md) ----------------------------------

_MODEL_BLOCK = ["Model", "Height : 173cm", "Top : Small(90호)", "Bottom : Smal(67호)", "Bust : 83cm", "Waist : 62cm",
                "Hip : 90cm", "제품착장사이즈", "상의:90호(S)", "하의:67호(S)", "Height: 171cm", "Top : Smal(90호)",
                "Bottom : Small(67호)", "Bust : 81cm", "Waist : 60cm", "Hip : 87cm", "제품착장사이즈"]   # 10940191023 OCR


def test_a_model_blocks_bust_is_no_chart():
    """10940191023: the models' "Bust : 83cm" / "Bust : 81cm" were read as One Size {chest 83}, chest 81 a conflict;
    the chart under them is read as before."""
    chart = C.read_chart(_MODEL_BLOCK + ["Size", "xS / s / M / L", "총기장 / 55 / 56 / 57 / 58.5",
                                         "가슴둘레 / 85 / 90 / 95 / 100", "어깨넓이 / 35.5 / 37 / 38.5 / 40"])
    assert C.ONE not in chart.rows and not chart.conflicts
    assert chart.rows["M"] == {"length": 57.0, "chest": 95.0, "shoulder": 38.5}
    # narrow: a Bust line with no other body line near it is still a one-size line
    assert C.read_chart(["Bust : 83cm"]).rows == {C.ONE: {"chest": 83.0}}


def test_a_womens_size_in_a_model_line_is_no_measure():
    """11573884405 (and 11612270523, 11573921646): "어깨가넓은 마른66사이즈" made a conflict "shoulder 66"."""
    chart = C.read_chart(["★상세사이즈", "어깨54cm가슴56cm", "팔길이54cm총장59cm", "어깨가넓은 마른66사이즈"])
    assert chart.rows == {C.ONE: {"shoulder": 54.0, "chest": 56.0, "sleeve": 54.0, "length": 59.0}}
    assert not chart.conflicts
    # narrow: a number with a space before "size" is still a measure ("총장 66 Size free" keeps its length)
    assert C._PAIR_RE.findall("마른66사이즈") == [] and C._PAIR_RE.findall("총장66size") == []
    assert C._PAIR_RE.findall("총장 66 Size") == [("총장", "66")]


def test_a_value_that_breaks_its_run_is_dropped():
    """13338110183 OCR: shoulder 57 on the 90 row (35.5 / 37? / 38.5 / 40.5) is a misread: dropped, never shown."""
    chart = C.read_chart(["SIZE / 85 / 90 / 95 / 100", "기장옆목 / 56.5 / 58 / 59.5 / 61",
                          "어깨너비 / 35.5 / 57 / 38.5 / 40.5", "가슴들레 / 89 / 94 / 99 / 105", "소매길이 / 57 / 58 / 59 / 60"])
    assert chart.rows["90"] == {"length": 58.0, "chest": 94.0, "sleeve": 58.0}
    assert [chart.rows[n]["shoulder"] for n in ("85", "95", "100")] == [35.5, 38.5, 40.5]


@pytest.mark.parametrize("run, broken", [
    ([35.5, 57, 38.5, 40.5], {1}),                       # 13338110183
    ([85, 90, 95, 100], set()), ([80, 87, 92, 97], set()), ([100, 95, 90, 85], set()),     # regular, uneven, falling
    ([53, 53, 54.5, 56], set()), ([34.8, 36, 37.2, 39], set()),                              # 11377634969
    ([50, 52, 54, 70], set()), ([92, 96, 100, 110], set()),   # an end value is never dropped: a big last step
    ([48, 50, 52, 58.5], set()), ([36, 37, 38, 38, 45], set()),  # is real grading as often as a misread
    ([50, 52, 70], set()), ([58, 62, 58], set()),        # a run of 3: not told
    ([35, 57, 38, 60, 41], set()),                       # two places break: which is the misread is unknown
])
def test_the_run_check(run, broken):
    assert C._breaks([float(x) for x in run]) == broken


def test_a_doubled_cell_is_one_value():
    """11377634969: "85 (S) | 36 | 92 | 58 | 53/53" had one cell too many, the 85 row was lost."""
    chart = C.read_chart(["사이즈 | 어깨너비 | 가슴둘레 | 소매길이 | 총길이", "80 (XS) | 34.8 | 87 | 58 | 53",
                          "85 (S) | 36 | 92 | 58 | 53/53", "90 (M) | 37.2 | 97 | 59 | 54.5"])
    assert chart.rows["85 (S)"] == {"shoulder": 36.0, "chest": 92.0, "sleeve": 58.0, "length": 53.0}
    # narrow: two different numbers are two cells, never one
    assert "85 (S)" not in C.read_chart(["사이즈 | 어깨너비 | 가슴둘레 | 소매길이 | 총길이", "85 (S) | 36 | 92 | 58 | 53/54"]).rows


def test_the_unit_alone_is_a_corner():
    """13021502381 OCR: "CM / 90 / 95 / 100 / 105" heads the columns, like 단위(cm)."""
    chart = C.read_chart(["SIZE GUIDE", "CM / 90 / 95 / 100 / 105", "총기장 / 56 / 57.5 / 59 / 60.5",
                          "가슴둘레 / 97 / 102 / 107 / 113", "어깨넓이 / 36 / 37.5 / 39 / 41", "소매기장 / 58 / 59 / 60 / 61"])
    assert chart.rows["95"] == {"length": 57.5, "chest": 102.0, "shoulder": 37.5, "sleeve": 59.0}
    assert C.read_chart(["cm / 90 / 95", "가슴둘레 / 97 / 102"]).rows["90"] == {"chest": 97.0}


# ---- the 2026-11-20 lens review of the windbreaker pilot (job fairwardgolf-50002798-20261120T160545Z) -----------------

def test_bare_letters_take_a_numbered_charts_sizes_in_order():
    """Kim Young Joo DOFLJP01 (11074837484): "S / M / L" sold, "호칭 / 95 / 100 / 105" charted: S is 95 (M (US 8-10)),
    never the fallback's S = 90; the chart's rows go with them."""
    texts = ["사이즈:S,M,L", "SIZE INFO", "호 칭 / 95 / 100 / 105", "가슴둘레 / 128 / 132 / 137", "어깨너비 / 60 / 61 / 62",
             "소매길이 / 52 / 53 / 54"]
    r = _resolve(["S", "M", "L"], texts)
    assert [(v["us"], v["basis"]) for v in r["values"]] == [
        ("M (US 8-10)", "chart_position"), ("L (US 12-14)", "chart_position"), ("XL (US 16)", "chart_position")]
    assert [row["cm"]["chest"] for row in r["chart"]["rows"]] == [128.0, 132.0, 137.0]


def test_a_numbered_chart_of_another_count_leaves_the_letters_alone():
    r = _resolve(["S", "M", "L"], ["호칭 / 95 / 100", "가슴둘레 / 128 / 132"])
    assert {v["basis"] for v in r["values"]} == {"fallback_letters"}


def test_a_size_corner_line_is_a_column_header_after_a_diagrams_labels():
    """PING 121D3JP251 (12361710158): the SIZE GUIDE diagram's labels, 4 measure names, came right before the chart
    "사이즈 / 90 / 95 / 100 / 105" and took it for a row; the chart was lost."""
    lines = ["총길이 / 소매길이 / 총길이 / 총길이", "사이즈 / 90 / 95 / 100 / 105", "총장 / 68 / 69 / 70.5 / 71.5",
             "어깨넓이 / 39 / 40.4 / 42.2 / 44.4", "가슴둘레 / 102 / 108 / 115 / 123", "소매기장 / 60.5 / 61.5 / 62.5 / 63.5"]
    chart = C.read_chart(lines)
    assert set(chart.rows) == {"90", "95", "100", "105"} and chart.rows["90"]["chest"] == 102.0


@pytest.mark.parametrize("value, joined", [("Black/090", True), ("아이보리 M", True), ("네이비 55", True),
                                           ("블랙", False), ("FREE", False), ("Black/Free", False), ("M(90)", False),
                                           # the size first (Mineflow 9969597394, 2026-11-21)
                                           ("XL/그레이", True), ("FREE/그레이", False), ("S (55)", False)])
def test_one_value_joining_a_colour_and_a_size(value, joined):
    """Hazzys 13684467368 (2026-11-20): one fact "선택하기: Black/090" reached the store as option "Select"."""
    assert A.joined_value(value) is joined


def test_a_one_value_colour_and_size_fact_holds_the_product():
    out = T._sizes({"options": [], "facts": [{"label_ko": "선택하기", "value_ko": "Black/090"}], "variants": []},
                   "womens_tops", "", [], "헤지스", "[헤지스골프]여성 블랙 바람막이 점퍼 HWJU4C612BK")
    assert out["held"] == "'선택하기': colour and size in one value ('Black/090')"
    ok = T._sizes({"options": [], "facts": [{"label_ko": "색상", "value_ko": "블랙"}], "variants": []},
                  "womens_tops", "", [], "헤지스", "여성 바람막이")
    assert not ok["held"]


def test_a_size_first_option_joining_size_and_colour_holds():
    """Mineflow 9969597394 (2026-11-21): one option "FREE/그레이", "XL/크림": size and colour in one, the size first;
    FREE counts beside another size. An option of FREE alone with colours is no size run."""
    r = A.resolve([{"name_ko": "색상", "values_ko": ["FREE/그레이", "FREE/블랙", "XL/크림"]}], [], None, "여성 바람막이",
                  "womens_tops")
    assert r["held"] and "colour and size in one option" in r["held"]
    r = A.resolve([{"name_ko": "색상", "values_ko": ["FREE/그레이", "FREE/블랙"]}], [], None, "여성 바람막이", "womens_tops")
    assert not (r["held"] and "colour and size" in r["held"])


def test_superior_takes_its_own_us_numbers():
    """The owner 2026-11-21: Superior's garments measure under the grid's US size; its own table (085..105 = US
    2..10, 11829592844's images) sizes them, so a US buyer gets the size she is used to; a chest the table lacks keeps
    the grid's."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["085", "090", "095", "100", "105", "110"]}], [], "슈페리어",
                  "슈페리어 여성 점퍼", "womens_tops")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["XS (US 2)", "S (US 4)", "S (US 6)", "M (US 8)",
                                                                "M (US 10)", "XXL (US 18)"]
    assert {v["basis"] for v in r["values"][:5]} == {"brand_us_num:Superior"}
    assert "<td>S (US 6)</td>" in A.chart_html(r)
    other = A.resolve([{"name_ko": "사이즈", "values_ko": ["090"]}], [], "헤지스", "헤지스 여성 점퍼", "womens_tops")
    assert other["values"][0]["us"] == "S (US 4-6)"


@pytest.mark.parametrize("values, want", [
    # 2026-11-21, the long-sleeve tops pilot: a seller's note after the size, 사이즈 in the brackets, a size's number
    # before the women's sizes it fits
    (["S(44)모델착용사이즈", "M(55~66)", "L(77)"], ["XS (US 0-2)", "S-M (US 4-10)", "L (US 12-14)"]),
    (["55(S사이즈)", "66(M사이즈)", "77(L사이즈)"], ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),
    (["1사이즈(44-55사이즈)", "2사이즈(66-77사이즈)"], ["XS-S (US 0-6)", "M-L (US 8-14)"]),
])
def test_a_sellers_note_or_a_numbered_size_reads_as_the_size(values, want):
    r = _resolve(values)
    assert not r["held"] and [v["us"] for v in r["values"]] == want


@pytest.mark.parametrize("value", ["1번(44-55반)", "0호", "화이트_95", "모찌/S"])  # resolve alone; transform._sizes splits the joined (2026-11-22)
def test_a_half_size_a_bare_number_or_a_joined_type_stays_unread(value):
    r = _resolve([value, "M"])
    assert r["held"]


def test_a_size_in_the_middle_or_after_an_underscore_is_joined():
    """6354978708 (2026-11-21): "기능성 하트넥 티셔츠 55_아이보리" is a colour and a size in one value."""
    assert A.joined_value("기능성 하트넥 티셔츠 55_아이보리") and A.joined_value("화이트_95")
    assert not A.joined_value("긴팔 화이트") and not A.joined_value("기모 블랙")
    r = A.resolve([{"name_ko": "색상", "values_ko": ["티셔츠 55_아이보리", "티셔츠 66_아이보리", "티셔츠 77_블랙"]}], [],
                  None, "여성 티셔츠", "womens_tops")
    assert r["held"] and "colour and size in one option" in r["held"]


def test_a_diagrams_number_before_a_measure_is_its_name():
    """5378291032 (2026-11-21): "1.어깨 / 2.가슴 / 3.소매 / 7.총길이" lost the chart."""
    chart = C.read_chart(["사이즈 / 1.어깨 / 2.가슴 / 3.소매 / 7.총길이", "S / 38 / 46 / 58 / 60", "M / 40 / 48 / 59 / 62"])
    assert chart.rows["S"] == {"shoulder": 38.0, "chest": 46.0, "sleeve": 58.0, "length": 60.0}
    assert A.parse_label("55사이즈 (S 추천)").women == (55.0,) and A.parse_label("55사이즈 (S 추천)").letter == "S"


def test_a_size_fact_beside_other_facts_is_the_us_size():
    """5365000791 (2026-11-21): facts 원단 긴팔, 컬러 핑크, 사이즈 S: the one variant went out as "Option: Standard"."""
    product = {"options": [], "facts": [{"label_ko": "원단", "value_ko": "긴팔"}, {"label_ko": "컬러", "value_ko": "핑크"},
                                        {"label_ko": "사이즈", "value_ko": "S"}],
               "sizes": {"profile": "womens_tops", "option": None, "values": [],
                         "fact": {"label_ko": "사이즈", "ko": "S", "us": "S (US 4-6)"}}}
    assert SP._single(product, _en([])) == ("Size", "S (US 4-6)")


def test_simple_choices_of_several_values_hold_an_apparel_product():
    """PUMPING 7512705748 (2026-11-21): its sizes, colours and necks are SIMPLE choices, not variants: one variant
    with no size went out; in apparel it is held size_unmapped."""
    facts, left = T.simple_choices({"options": {"simple_options": [
        {"group": "사이즈", "name": "55(S)"}, {"group": "사이즈", "name": "66(M)"}, {"group": "컬러", "name": "블랙"}]}})
    assert left == ["사이즈"] and facts and facts[0]["value_ko"] == "블랙"
    import inspect
    assert 'f"sizes chosen at the order, not variants' in inspect.getsource(T.prepare)
    specs = {"options": {"simple_options": [{"group": "아쿠아 바람막이 색상", "name": "아쿠아"},
                                            {"group": "아쿠아 바람막이 색상", "name": "블랙"}]}}
    assert not T._sized_group(specs, "아쿠아 바람막이 색상")                   # a colour stays a note (10780424641)
    assert T._sized_group({"options": {"simple_options": [{"group": "선택", "name": "55(S)"},
                                                          {"group": "선택", "name": "66(M)"}]}}, "선택")


def test_a_short_sleeve_variant_is_off_the_long_sleeve_section():
    """5418772209 (2026-11-21): a 반팔 design among the variants of a long-sleeve top."""
    import listing_filter as LF
    rules = [r for r in LF.title_rules("50002796") if r["code"] in ("short_sleeve", "cardigan", "vest", "cooling")]
    assert LF.title_rule("반팔 카라 티셔츠 / 화이트", rules) == "title:short_sleeve"
    assert LF.title_rule("긴팔 카라 티셔츠 / 화이트", rules) is None


def test_a_one_size_product_whose_chart_names_several_sizes_holds():
    """Nike 13660201494 (2026-11-21, the second tops pilot): one variant, the size only in its title (", S"), the
    chart's labels S, M, XL, 2XL with no measures: which size is sold is unknown."""
    r = A.resolve([], ["사이즈 / S / M / XL / 2XL"], "나이키", "나이키 여성 빅토리 폴로, S", "womens_tops")
    assert r["held"] and "the chart lists S, M, XL, 2XL" in r["held"]


def test_mens_tops_size_by_the_mens_grid_with_the_us_letter():
    """mens_tops (2026-11-21): the Korean label is the body chest; 100 is US M; the storefront shows the letter; a
    women's size means nothing for a men's top: held."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["95", "100", "105", "110"]}], [], None, "남성 긴팔", "mens_tops")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["S", "M", "L", "XL"]
    assert "<th>Fits chest</th>" in A.chart_html(r)
    assert [v["us"] for v in A.resolve([{"name_ko": "사이즈", "values_ko": ["M", "L"]}], [], None, "남성", "mens_tops")[
        "values"]] == ["S", "M"]                          # a Korean M is 95: a US S (the review, 2026-11-22)
    assert [v["us"] for v in A.resolve([{"name_ko": "사이즈", "values_ko": ["M(95)", "L(100)"]}], [], None, "남성",
                                       "mens_tops")["values"]] == ["S", "M"]
    assert A.resolve([{"name_ko": "사이즈", "values_ko": ["55", "66"]}], [], None, "남성", "mens_tops")["held"]


# ---- 2026-11-22, the men's tops pilot: 63 apparel products held size_unmapped, the new shapes ---------------------------
@pytest.mark.parametrize("label, letter, chest, women", [
    ("S 95사이즈", "S", (95.0,), ()), ("S 95~100사이즈", "S", (95.0, 100.0), ()),     # Nike 7973150842, adidas 12659358151
    ("XS (85 전후)", "XS", (85.0,), ()), ("S (95전후)", "S", (95.0,), ()),            # 11494901577, 5033870845
    ("라지(77-88)", "L", (), (77.0, 88.0)), ("여성 55(M)", "M", (), (55.0,)),          # 7259291887, 6485458095
    ("S(모델착용사이즈)", "S", (), ()), ("S(상세사이즈 확인했습니다)", "S", (), ())])    # 10514027260, 11734583917
def test_new_label_shapes_read(label, letter, chest, women):
    got = A.parse_label(label)
    assert got and (got.letter, got.chest, got.women) == (letter, chest, women)


@pytest.mark.parametrize("value", ["블랙", "남색", "남성", "여름", "L(100-남색)", "M(95-여름)"])   # 2026-11-24: who
# the chest fits after a dash reads ("XL(100-여성77이상/남성M)", test_size_unmapped_review_labels), a colour does not
def test_new_label_shapes_leave_words_unread(value):
    assert A.parse_label(value) is None


def test_an_option_joining_a_colour_and_a_size_is_split_in_two():
    """PXG 13291331780 "Navy/090", 4689775780 "남성 골프 이너웨어__블랙 95", 7500284930 "모찌/S": held as "splitting the
    value is not built" until 2026-11-22; the colour stays in its option, the size moves to a new option 사이즈."""
    ov = {"options": [{"name_ko": "선택하기", "values_ko": ["Navy/090", "Navy/095", "White/090"]}], "facts": [],
          "variants": [{"options_ko": ["Navy/090"], "price_krw": 1}, {"options_ko": ["Navy/095"], "price_krw": 1},
                       {"options_ko": ["White/090"], "price_krw": 1}]}
    out = T._sizes(ov, "womens_tops", "", [], "PXG", "PXG 여성 니트")
    assert not out["held"] and [v["us"] for v in out["values"]] == ["S (US 4-6)", "M (US 8-10)"]
    assert ov["options"] == [{"name_ko": "선택하기", "values_ko": ["Navy", "White"]},
                             {"name_ko": "사이즈", "values_ko": ["090", "095"]}]
    assert [v["options_ko"] for v in ov["variants"]] == [["Navy", "090"], ["Navy", "095"], ["White", "090"]]
    assert A.split_joined([{"name_ko": "x", "values_ko": ["남성 골프 이너웨어__블랙 95", "남성 골프 이너웨어__블랙 100"]}]) \
        == (0, [("남성 골프 이너웨어 블랙", "95"), ("남성 골프 이너웨어 블랙", "100")])


@pytest.mark.parametrize("values", [["블랙 85 L", "블랙 90 S"],     # two size words, the letters not rising: no split
                                    ["AXL (110)", "AL (105)", "AM (100)"],                  # adidas' Asian letters
                                    ["블랙", "화이트"], ["블랙 FREE", "화이트 FREE"]])
def test_a_joined_option_is_not_split_when_unsure(values):
    assert A.split_joined([{"name_ko": "선택", "values_ko": values}]) is None


# ---- 2026-11-22: the skirts (womens_bottoms, keyed by the waist) ----------------------------------------------------
@pytest.mark.parametrize("values, want", [
    (["S", "M", "L", "XL"], ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)", "XL (US 16)"]),
    (["S(55)", "M(66)", "L(77)"], ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]),
    (["25", "26", "27", "28", "29", "30"], ["XS (US 2)", "S (US 4)", "S (US 6)", "M (US 8)", "M (US 10)", "L (US 12)"]),
    (["64", "67", "70", "73", "76"], ["XS (US 2)", "S (US 4)", "M (US 8)", "M (US 10)", "L (US 12)"]),   # cm, size up
    (["23", "24"], ["XXS (US 00)", "XS (US 0)"]),
    (["S(25-26)", "M(27-28)"], ["XS-S (US 0-6)", "S-M (US 4-10)"]),
    (["FREE"], ["One Size"]),
])
def test_a_skirts_size_goes_by_the_waist(values, want):
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "여성 골프 스커트", "womens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == want


def test_a_waist_is_read_only_for_a_waist_profile():
    """A top's "26" or a chart's "73" (a length) is never a size: the waist is read inside waist_labels only."""
    assert A.parse_label("26") is None and A.parse_label("M(73)") is None
    with A.waist_labels():
        assert A.parse_label("26").waist == (66.0,) and A.parse_label("67(S)").waist == (67.0,)
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["26", "27"]}], [], None, "여성 티셔츠", "womens_tops")
    assert r["held"]


def test_a_skirts_chart_doubles_the_flat_waist_and_hip():
    lines = ["사이즈 / 허리단면 / 엉덩이단면 / 총장", "S / 33 / 46 / 42", "M / 35 / 48 / 43"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["S", "M"]}], lines, None, "여성 골프 스커트", "womens_bottoms")
    assert r["chart"]["kinds"] == {"waist": "flat", "hip": "flat", "length": None}
    html = A.chart_html(r)
    assert "<th>Fits waist</th>" in html and "<td>26 in</td>" in html and "<td>36 in</td>" in html
    assert "the waist and hip all the way round" in html


def test_a_bare_colour_number_goes_only_when_the_colours_stay_apart():
    """5479866225 (the skirts pilot, 2026-11-22): "002 Black", "002 Sky Blue"; "309 Dark Navy" / "312 Dark Navy" keep
    their numbers: two colours of one English name."""
    product = {"options": [{"name_ko": "컬러", "values_ko": ["002 블랙", "002 스카이블루"]}],
               "sizes": {"profile": "womens_bottoms", "option": None, "values": []}}
    en = _en([("option_name", "컬러", "Color"), ("option_value", "002 블랙", "002 Black"),
              ("option_value", "002 스카이블루", "002 Sky Blue")])
    assert SP._options(product, en)[1][0] == ["Black", "Sky Blue"]
    two = {"options": [{"name_ko": "컬러", "values_ko": ["309 D네이비", "312 D네이비"]}],
           "sizes": {"profile": "womens_tops", "option": None, "values": []}}
    en = _en([("option_name", "컬러", "Color"), ("option_value", "309 D네이비", "309 Dark Navy"),
              ("option_value", "312 D네이비", "312 Dark Navy")])
    assert SP._options(two, en)[1][0] == ["309 Dark Navy", "312 Dark Navy"]


def test_a_size_with_its_inch_note_is_one_size_and_a_colour_option_named_size_is_renamed():
    """J.Lindeberg 7000338116 / 10515846043 (2026-11-22): "XS （25인치）", "XS (25인치 전후)" went out as a second option
    "Size 2"; 6334381845's option 사이즈 "화이트/S" left its colours under the name 사이즈 ("Size 2")."""
    assert A.split_joined([{"name_ko": "사이즈", "values_ko": ["XS （25인치）", "S （27인치）"]}]) is None
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["XS （25인치）", "S （27인치）", "M （29인치）"]}], [], None, "스커트",
                  "womens_bottoms")
    assert [v["us"] for v in r["values"]] == ["XS (US 2)", "S (US 6)", "M (US 10)"]
    ov = {"options": [{"name_ko": "사이즈", "values_ko": ["화이트/S", "화이트/M", "블랙/S"]}], "facts": [],
          "variants": [{"options_ko": [v], "price_krw": 1} for v in ("화이트/S", "화이트/M", "블랙/S")]}
    T._sizes(ov, "womens_bottoms", "", [], None, "여성 골프스커트")
    assert [o["name_ko"] for o in ov["options"]] == ["컬러", "사이즈"]


def test_a_ranged_free_beside_another_size_is_its_range():
    """5875520955 (2026-11-22): "Free(55-66)" next to "L" went out "One Size": it is S-M; alone it stays One Size."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["Free(55-66)", "L(77)"]}], [], None, "스커트", "womens_bottoms")
    assert [v["us"] for v in r["values"]] == ["S-M (US 4-10)", "L (US 12-14)"]
    assert A.resolve([{"name_ko": "사이즈", "values_ko": ["FREE(55-66)"]}], [], None, "니트", "womens_tops")["values"][0]["us"] \
        == "One Size"


# ---- the skirts' second review (47 drafts, 2026-11-22) ---------------------------------------------------------------
@pytest.mark.parametrize("values, want", [
    (["L(55)", "XL(66~66반)"], ["S (US 4-6)", "M-L (US 8-14)"]),        # 5711404722: XL(66~66반) went out XL (US 16)
    (["S(55-66)", "M(66반-77)"], ["S-M (US 4-10)", "L (US 12-14)"]),    # 6474116807: a half size sized up
    (["S(90)", "M(95)"], ["S (US 4-6)", "M (US 8-10)"]),                # Kappa 11871883753: 90 / 95 are no waist
    (["S（55~날씬66）", "M（통통66~날씬77）"], ["S-M (US 4-10)", "M-L (US 8-14)"]),   # 8628740416: slim / chubby
])
def test_a_skirts_half_size_a_top_number_and_a_body_word(values, want):
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "여성 골프 스커트", "womens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == want


def test_a_womens_size_the_profile_cannot_map_never_falls_back_to_its_letter():
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["L(55)", "XL(66~66반)"]}], [], None, "여성 니트", "womens_tops")
    assert r["held"] == "'XL(66~66반)': no US size (not read)"


def test_a_chart_s_top_number_is_no_skirt_waist():
    """Kappa 11871883753: the chart's "S(90) / M(95)" header paired S with 90 and went out XXL (US 18)."""
    lines = ["사이즈 / S(90) / M(95)", "허리둘레 / 70 / 73", "총장 / 42 / 43"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["S", "M"]}], lines, None, "카파 스커트", "womens_bottoms")
    assert [v["us"] for v in r["values"]] == ["S (US 4-6)", "M (US 8-10)"]


# ---- 2026-11-23: golf pants (mens_bottoms by the US waist, womens_pants the skirts' grid) ---------------------------
@pytest.mark.parametrize("values, want", [
    (["28", "29", "30", "32", "34", "36", "38", "40"], ["W28", "W29", "W30", "W32", "W34", "W36", "W38", "W40"]),
    (["76", "79", "82", "85", "88", "91"], ["W30", "W31", "W32", "W33", "W34", "W36"]),        # cm as Korea writes it
    (["30(76)", "32(82)", "34(86)"], ["W30", "W32", "W34"]),                                   # one waist written twice
    (["M(30)", "L(32)", "XL(34)"], ["W30", "W32", "W34"]),
    (["S", "M", "L", "XL", "XXL", "3XL"], ["W28-29", "W30-31", "W32-33", "W34-35", "W36-37", "W38-40"]),   # Korean
    (["FREE"], ["One Size"]),
])
def test_a_mens_pants_size_is_the_us_waist(values, want):
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "남성 골프 바지", "mens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == want


def test_a_womens_size_holds_in_the_mens_pants():
    """55 / 66 mean nothing for men's pants (and 88 there is a waist in cm, never a women's 88)."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["55", "66"]}], [], None, "골프 바지", "mens_bottoms")
    assert r["held"]
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("88").waist == (88.0,) and A.parse_label("88").women == ()
    assert A.parse_label("88").women == (88.0,)                       # outside: the women's size, as before


def test_womens_pants_size_as_the_skirts():
    """womens_pants is womens_bottoms with the trousers' measures: the sizing rows stay equal."""
    p = A.grids()["profiles"]
    keys = ("labels", "key", "pick", "fit", "kr_women", "letters", "grid", "brands", "us_by_waist_in")
    assert {k: p["womens_pants"][k] for k in keys} == {k: p["womens_bottoms"][k] for k in keys}
    assert (p["womens_pants"]["measures"], p["womens_bottoms"]["measures"]) == ("trousers", "bottoms")
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["25", "26", "27", "28"]}], [], None, "여성 골프 바지",
                  "womens_pants")
    assert [v["us"] for v in r["values"]] == ["XS (US 2)", "S (US 4)", "S (US 6)", "M (US 8)"]


def test_a_pants_chart_reads_thigh_rise_hem_and_doubles_the_flat():
    lines = ["사이즈 / 허리단면 / 엉덩이단면 / 허벅지단면 / 밑위 / 밑단단면 / 총장",
             "30 / 39 / 50 / 30 / 27 / 19 / 102", "32 / 41 / 52 / 31 / 28 / 20 / 103"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["30", "32"]}], lines, None, "남성 골프 바지", "mens_bottoms")
    assert r["chart"]["kinds"] == {"waist": "flat", "hip": "flat", "thigh": "flat", "rise": None, "hem": "flat",
                                   "length": None}
    html = A.chart_html(r)
    assert "<td>W30</td>" in html and "<th>Leg opening</th>" in html and "<td>30.5 in</td>" in html
    assert "the waist, hip, thigh and leg opening all the way round" in html


def test_the_pants_profile_follows_the_stated_gender():
    """Golf Pants (2026-11-23): men's and unisex pants by the US waist, women's by the skirts' grid; the tops keep the
    women's profile for a unisex top (stated_only)."""
    from transform_shops import rules_for
    cats = rules_for("fairwardgolf").categories
    pants, tops = cats["50002801"], cats["50002796"]
    assert [T.size_profile(pants, g) for g in ("mens", "womens", "unisex", "mixed", None)] == \
        ["mens_bottoms", "womens_pants", "mens_bottoms", "mens_bottoms", "womens_pants"]
    assert [T.size_profile(tops, g) for g in ("mens", "unisex", None)] == ["mens_tops", "womens_tops", "womens_tops"]
    assert pants.variant_screen == ("not_golf_use",) and pants.reviewed   # the owner 2026-11-24
    assert pants.variant_drop == ("other_item", "shorts")         # left out, not held, since 2026-11-25


def test_one_waist_in_inches_and_cm_is_one_size():
    """Adidas 5979440160 (2026-11-23, the pants pilot): two pants' sizes "M(32)" and "M(82)" are one waist; the
    fleece pair's "XL(88)" is 34 as its chart says (88(34)), not the summer pair's XL(35)."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["M(32)", "L(33)", "XL(35)", "M(82)", "L(85)", "XL(88)",
                                                     "2XL(92)", "XXL(36)"]}],
                  [], None, "아디다스 골프 바지 남자", "mens_bottoms")
    assert [v["us"] for v in r["values"]] == ["W32", "W33", "W34", "W35", "W36"]
    assert r["merged"] == {"M(82)": "M(32)", "L(85)": "L(33)", "XXL(36)": "2XL(92)"}


def _pants_variant_screen(value: str) -> str | None:
    """The pants' variant screen as transform.prepare applies it: the codes of variant_screen and variant_drop (left
    out since 2026-11-25), `requires` left out."""
    import listing_filter as LF
    from transform_shops import rules_for
    pants = rules_for("fairwardgolf").categories["50002801"]
    codes = pants.variant_screen + pants.variant_drop
    screen = [{k: r[k] for k in r if k != "requires"} for r in LF.title_rules("50002801") if r["code"] in codes]
    return LF.title_rule(value, screen)


@pytest.mark.parametrize("value, code", [
    # the drafts' review (2026-11-24): option values of the real products
    ("기모긴소매블랙(어깨배색)", "title:other_item"),           # Volvik 10933958968: fleece long-sleeve tops
    ("기모긴소매네이비(가슴배색)", "title:other_item"),
    ("반팔 네이비", "title:other_item"), ("긴팔 화이트", "title:other_item"), ("맨투맨 그레이", "title:other_item"),
    ("상의 블랙", "title:other_item"),
    ("3번 텍티컬 팬츠", "title:not_golf_use"),                  # Under Armour 8162342503: tactical work pants
    ("택티컬 카고 팬츠", "title:not_golf_use"), ("UA Tactical Pants", "title:not_golf_use"),
    # what stays: the pants' own values
    ("1번 드라이브 팬츠", None), ("2번 매치플레이 팬츠", None), ("기모바지 블랙", None), ("S/S 네이비", None),
    ("M2-0B053_아이보리", None), ("30인치 이상의 허리", None),     # 이상의 is no 상의
])
def test_a_top_or_tactical_variant_holds_the_pants(value, code):
    assert _pants_variant_screen(value) == code


# 5489884876 (2026-11-24, the drafts' review): the description images' text, trimmed to the model cards around it
_MASTER_BEAR_OCR = [[
    "마스터베어", "힙포인트 히든밴딩 기모팬츠", "MODEL NO : M2-0B025", "SIZE: 30(M),32(L),34(XL),36(2XL),38(3XL)",
    "아잉볼로", "전상품 무료배송", "허리스컴밴드 / 39,900 / 원",
    "화이트베어 여성용", "슬림밋무지기모골프바지", "MODEL NO : M2-0B053", "SIZE : S,M,L", "IVORY / BLACK",
    "전상품 무료배송", "허리양옆숨김백든 / 39,900 / 원",
    "1-2INCH조철가능", "마스터베어포켓", "힙포인트숨김밴딩기모바지", "MODEL NO : M2-0B047",
    "SIZE : 30(M),32(L),34(XL),36(2XL),38(3XL)"]]


def test_a_womens_model_in_a_mens_product_is_found():
    """Master Bear 5489884876: the White Bear women's model M2-0B053 sold in the men's pants; its S went out as the
    men's waist W28-29."""
    import transform as T
    variants = [{"options_ko": ["M2-0B025_블랙", "30(M)"]}, {"options_ko": ["M2-0B053_아이보리", "S"]},
                {"options_ko": ["M2-0B047_블랙", "32(L)"]}]
    assert T.womens_model_sold(variants, _MASTER_BEAR_OCR) == "M2-0B053"
    assert T.womens_model_sold([v for v in variants if "M2-0B053" not in v["options_ko"][0]], _MASTER_BEAR_OCR) is None
    unisex = [["남녀공용 여성 남성", "MODEL NO : M2-0B053"]]          # a label naming men too is no women's model
    assert T.womens_model_sold(variants, unisex) is None
    assert T.womens_model_sold(variants, []) is None


def test_a_tops_size_holds_in_the_mens_pants():
    """A polo sold with the pants (5534297375, 2026-11-23): "M(95)" is a top's chest, never a 95 cm waist."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["M(95)", "L(100)", "88(34)"]}], [], None, "골프 바지",
                  "mens_bottoms")
    assert r["held"] and "M(95)" in r["held"]


@pytest.mark.parametrize("lines, want", [
    (["Size / S(24-26), M(27-28), L(29-30), XL(30-31), XXL(32-33) * 허리 하이웨스트 밴딩처리"],      # 5530496945
     ["XS-S (US 0-6)", "S-M (US 4-10)", "M-L (US 8-14)", "L (US 12-14)", "L-XL (US 12-16)"]),
    (["S 사이즈 (25-27) 허리 32", "M사이즈 (27-28) 허리 34", "L사이즈 (28-29) 허리 36", "XL사이즈(29-30) 허리 38"],  # 5392170005
     ["XS-S (US 0-6)", "S-M (US 4-10)", "M (US 8-10)", "M-L (US 8-14)"]),
    (["25-26 : S / 27-29 : M / 29-30 : L / 30-31 : XL"],                                              # 5814395263
     ["XS-S (US 0-6)", "S-M (US 4-10)", "M-L (US 8-14)", "L (US 12-14)"]),
])
def test_a_letters_body_waist_in_the_text_sizes_it(lines, want):
    """The pants pilot (2026-11-23): a women's letter sized by the waist its seller writes beside it, never the bare
    letter (4 drafts went out one or two US sizes over)."""
    values = ["S", "M", "L", "XL", "XXL"][:len(want)]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], lines, None, "여성 골프 바지", "womens_pants")
    assert [v["us"] for v in r["values"]] == want and {v["basis"] for v in r["values"]} == {"text_waist"}
    part = A.resolve([{"name_ko": "사이즈", "values_ko": ["S", "M", "L"]}], ["S(25-26) 추천"], None, "여성 골프 바지",
                     "womens_pants")
    assert {v["basis"] for v in part["values"]} == {"fallback_letters"}        # one letter of three: no mix


def test_a_size_up_advice_is_the_size():
    """"S(up추천)" (size up advised, 5117895030, 2026-11-23) is S."""
    assert A.parse_label("S(up추천)") == A.parse_label("S")
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["S", "M", "S(up추천)", "M(up추천)"]}], [], None,
                  "여성 골프바지", "womens_pants")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["S (US 4-6)", "M (US 8-10)"]


# ---- 2026-11-24: the Golf Pants drafts' review (label shapes) -------------------------------------------------------
def test_a_sellers_inch_range_is_the_us_waist_as_written():
    """Nike 8000226696: "33~34인치" went out W32-35 (two bands joined) beside "32~33인치" W32-33 and "34~35인치"
    W34-35; "38~39인치" W38-40."""
    values = ["30~31인치", "30인치", "32~33인치", "32인치", "33인치", "33~34인치", "34~35인치", "34인치", "35인치",
              "36~37인치", "38~39인치"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "나이키 남성 골프 바지", "mens_bottoms")
    us = {v["ko"]: v["us"] for v in r["values"]}
    assert not r["held"]
    assert (us["33~34인치"], us["38~39인치"], us["32~33인치"], us["34~35인치"], us["30~31인치"]) == \
        ("W33-34", "W38-39", "W32-33", "W34-35", "W30-31")
    skirt = A.resolve([{"name_ko": "사이즈", "values_ko": ["25-26", "27-28"]}], [], None, "스커트", "womens_bottoms")
    assert [v["us"] for v in skirt["values"]] == ["XS-S (US 0-6)", "S-M (US 4-10)"]     # the women's: unchanged
    # a waist and a length ("33-30", "32-34": 9918112671) is no waist range: held as before
    pairs = A.resolve([{"name_ko": "사이즈", "values_ko": ["30-30", "33-30", "34-30", "35-30", "32-34"]}], [], None,
                      "남성 골프 바지", "mens_bottoms")
    assert pairs["held"] and "two Korean sizes on one US size" in pairs["held"]


@pytest.mark.parametrize("values", [
    ["29(30인치)", "30(31인치)", "31(32인치)", "32(33인치)", "33(34인치)", "34(35인치)", "36(37인치)", "38(39인치)"],  # 6780190931
    ["29(30)", "30(31)", "31(32)", "32(33)", "33(34)", "34(35)", "36(37)", "38(39)"],                          # 4720043508
    ["29인치(30인치전후)", "30인치(31인치전후)", "31인치(32인치전후)", "32인치(33인치전후)", "33인치(34인치전후)",          # 7006521057
     "34인치(35인치전후)", "36인치(37인치전후)", "38인치(39인치전후)"],
    ["29(국내30)", "30(국내31)", "31(국내32)", "32(국내33)", "33(국내34)", "34(국내35)", "36(국내37)", "38(한국39)"],    # 4530831170
])
def test_j_lindebergs_waist_with_the_korean_one_is_one_waist(values):
    """J.Lindeberg (2026-11-24): the maker's waist with the Korean one an inch up in brackets went out as overlapping
    bands (29(30) W28-31, 31(32) W30-33) or held ("30(국내31)"); one waist, the maker's: "한국사이즈 33 이시면 32로
    주문하시면되세요" (4530831170)."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "제이린드버그 남성 골프 바지", "mens_bottoms")
    assert not r["held"]
    assert [v["us"] for v in r["values"]] == ["W29", "W30", "W31", "W32", "W33", "W34", "W36", "W38"]
    with A.waist_labels(False):
        assert A.parse_label("29(30)") is None                     # outside the men's trousers: as before


def test_a_shipping_note_after_a_size_is_the_size():
    """Callaway 6486608544 (2026-11-24): "30(당일발송)" and "30당일발송)" (same-day dispatch) held "not read as a
    size"; beside a bare "30" they are one size."""
    values = ["30(당일발송)", "32(당일발송)", "34(당일발송)", "38", "30당일발송)", "36", "30", "32"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": values}], [], None, "캘러웨이 남성 바지", "mens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["W30", "W32", "W34", "W36", "W38"]
    assert r["merged"] == {"30당일발송)": "30(당일발송)", "30": "30(당일발송)", "32": "32(당일발송)"}
    assert A.parse_label("M(오늘출발)") == A.parse_label("M")


def test_a_trousers_length_before_the_size_is_an_option_of_its_own():
    """엔조이핏 10107163054 (2026-11-24): "9부 S" .. "10부 2XL" (9/10 length) beside its joggers' bare "S" held
    "'9부 S': not read as a size"; the length goes to an option 기장, a bare size to 기본 (no length stated)."""
    sizes = ["9부 S", "9부 M", "10부 S", "10부 M", "9부 2XL", "S", "M"]
    ov = {"options": [{"name_ko": "스타일", "values_ko": ["01_일자핏", "07_데일리조거"]},
                      {"name_ko": "사이즈", "values_ko": sizes}], "facts": [],
          "variants": [{"options_ko": ["01_일자핏", s], "price_krw": 36800} for s in sizes[:5]]
          + [{"options_ko": ["07_데일리조거", s], "price_krw": 36800} for s in sizes[5:]]}
    out = T._sizes(ov, "womens_pants", "", [], None, "여성 골프바지")
    assert not out["held"]
    assert [(o["name_ko"], o["values_ko"]) for o in ov["options"]] == [
        ("스타일", ["01_일자핏", "07_데일리조거"]), ("기장", ["9부", "10부", "기본"]), ("사이즈", ["S", "M", "2XL"])]
    assert [v["options_ko"] for v in ov["variants"]][:3] == [["01_일자핏", "9부", "S"], ["01_일자핏", "9부", "M"],
                                                            ["01_일자핏", "10부", "S"]]
    assert ov["variants"][-1]["options_ko"] == ["07_데일리조거", "기본", "M"]
    assert A.split_length([{"name_ko": "사이즈", "values_ko": ["S", "M"]}]) is None


def test_a_length_past_shopifys_three_options_joins_the_option_before_it():
    """엔조이핏 10107163054 (2026-11-24): 스타일 / 사이즈 "9부 S" / 색상 split into four options; productSet refused
    ("Can only specify a maximum of 3 options"): the length goes onto the style, a bare size's 기본 adds nothing."""
    sizes = ["9부 S", "10부 S", "S", "M"]
    ov = {"options": [{"name_ko": "스타일", "values_ko": ["01_일자핏", "07_데일리조거"]},
                      {"name_ko": "사이즈", "values_ko": sizes}, {"name_ko": "색상", "values_ko": ["블랙"]}], "facts": [],
          "variants": [{"options_ko": ["01_일자핏", "9부 S", "블랙"], "price_krw": 36800},
                       {"options_ko": ["01_일자핏", "10부 S", "블랙"], "price_krw": 36800},
                       {"options_ko": ["07_데일리조거", "S", "블랙"], "price_krw": 36800},
                       {"options_ko": ["07_데일리조거", "M", "블랙"], "price_krw": 36800}]}
    out = T._sizes(ov, "womens_pants", "", [], None, "여성 골프바지")
    assert not out["held"] and [o["name_ko"] for o in ov["options"]] == ["스타일", "색상", "사이즈"]
    assert ov["options"][0]["values_ko"] == ["01_일자핏 9부", "01_일자핏 10부", "07_데일리조거"]
    assert [v["options_ko"] for v in ov["variants"]] == [["01_일자핏 9부", "블랙", "S"], ["01_일자핏 10부", "블랙", "S"],
                                                         ["07_데일리조거", "블랙", "S"], ["07_데일리조거", "블랙", "M"]]


def test_a_waist_glued_to_a_colour_or_a_bracket_is_split_in_the_waist_profiles():
    """promore 4954391160 / 5536196761 (2026-11-24): 선택2 "블랙34", "151(블랙)30", "SW.422/01(그레이)30" held "no
    size option, the chart lists 30, 32, ..."; the waist splits off in a waist profile, never in the tops."""
    values = ["블랙34", "네이비30", "151(블랙)30", "151(블랙)32", "SW.422/01(그레이)30", "SW.422/01(그레이)40"]
    ov = {"options": [{"name_ko": "선택1", "values_ko": ["PR-PT(봄/여름)", "JP_기모스판"]},
                      {"name_ko": "선택2", "values_ko": values}], "facts": [],
          "variants": [{"options_ko": ["JP_기모스판", v], "price_krw": 24800} for v in values]}
    out = T._sizes(ov, "mens_bottoms", "", [], None, "프로모어 남성 겨울 골프바지")
    assert not out["held"] and [v["us"] for v in out["values"]] == ["W30", "W32", "W34", "W40"]
    assert ov["options"][1]["values_ko"] == ["블랙", "네이비", "151(블랙)", "SW.422 01(그레이)"]
    assert ov["variants"][2]["options_ko"] == ["JP_기모스판", "151(블랙)", "30"]
    assert A.split_joined([{"name_ko": "선택", "values_ko": ["블랙95", "네이비100"]}]) is None    # no waist read on


def test_two_options_each_joining_a_colour_and_a_size_hold_as_a_set_of_two():
    """내추럴모드 10821435743 (2026-11-24): 선택1 "크림M" .. and 선택2 "베이지M" .. (1+1, two pairs a variant at
    49,800 KRW) went out as one pair, unsized; the first option splits, the second holds the product."""
    one, two = ["크림M", "크림L", "카키3XL"], ["베이지M", "베이지2XL"]
    ov = {"options": [{"name_ko": "선택1", "values_ko": one}, {"name_ko": "선택2", "values_ko": two}], "facts": [],
          "variants": [{"options_ko": [a, b], "price_krw": 49800} for a in one for b in two]}
    out = T._sizes(ov, "mens_bottoms", "", [], None, "내추럴모드 남성 조거 골프바지")
    assert out["held"] and "1+1" in out["held"] and "선택2" in out["held"]
    # a season code before the colour is no second size (Volvik 10322266021: "S/S베이지", "F/W블랙(기모)")
    colours = ["S/S베이지", "S/S네이비", "F/W블랙(기모)"]
    ov = {"options": [{"name_ko": "컬러", "values_ko": colours}, {"name_ko": "사이즈", "values_ko": ["M(32)", "L(34)"]}],
          "facts": [], "variants": [{"options_ko": [c, s], "price_krw": 1} for c in colours for s in ("M(32)", "L(34)")]}
    assert not T._sizes(ov, "mens_bottoms", "", [], None, "볼빅 남성골프바지")["held"]


# ---- 2026-11-24: the Golf Pants review (sizes from the seller's text and chart) -----------------------------------
def _pants(values: list[str], lines: list[str], profile: str,
           extra: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return A.resolve((extra or []) + [{"name_ko": "사이즈", "values_ko": values}], lines, None, "골프 바지", profile)


def test_a_cm_size_takes_the_inch_its_chart_header_writes():
    """Kim Young Joo 5912038354: "호칭 / 77(29) / 81(31) ..." over the bare options 77..95: cm_round made 77 W30 and 81
    W32 and dropped their chart rows; the seller's inch is the US waist."""
    lines = ["호칭 / 77(29) / 81(31) / 85(33) / 89(35) / 95(37)", "허리둘레 / 77 / 82 / 87 / 92 / 97",
             "엉덩이둘레 / 98 / 102 / 106 / 111 / 116"]
    r = _pants(["77", "81", "85", "89", "95"], lines, "mens_bottoms")
    assert [v["us"] for v in r["values"]] == ["W29", "W31", "W33", "W35", "W37"]
    assert {v["basis"] for v in r["values"]} == {"chart_inch"}
    assert [(row["us"], row["cm"]["waist"]) for row in r["chart"]["rows"]] == \
        [("W29", 77.0), ("W31", 82.0), ("W33", 87.0), ("W35", 92.0), ("W37", 97.0)]
    assert A.cm_inch("77(29)") == (77, 29) and A.cm_inch("30(76)") is None and A.cm_inch("M(32)") is None


_JDX = ["30사이즈 입으시는 고객님께서는 78", "호칭 / 78 / 82 / 84 / 86 / 88 / 92 / 96 / 100",
        "인치 / 31 / 32 / 33 / 34 / 35 / 37 / 38 / 40", "허리둘레 / 81 / 85 / 87 / 89 / 91 / 95 / 99 / 103",
        "남자 / MEN", "cm / 78(79) / 82 / 84(85) / 86 / 88 / 92(91)96(97)100",
        "inch / 31 / 32 / 33 / 34 / 35 / 37 / 38 / 40", "여자WOMEN", "cm / 64 / 67 / 70 / 73 / 76 / 79 / 82 / 85",
        "inch / 26 / 27 / 28 / 29 / 30 / 32 / 33 / 34"]


def test_an_inch_row_under_the_cm_row_sizes_each_and_keeps_86_and_88_apart():
    """JDX 10694535049: the 인치 row under 호칭 is the seller's US waist (92 = 37, 100 = 40; cm_round said 36, 39), and
    86 (34) and 88 (35) are two sizes (88 was merged into 86, its variants dropped). A later generic "inch" row of the
    women's chart never relabels them; the text "30사이즈 ... 78" (a fit advice) changes nothing."""
    r = _pants(["78", "82", "84", "86", "88", "92", "100"], _JDX, "mens_bottoms")
    assert [v["us"] for v in r["values"]] == ["W31", "W32", "W33", "W34", "W35", "W37", "W40"]
    assert r["merged"] == {} and not r["held"]
    plain = _pants(["86", "88"], [], "mens_bottoms")                 # no chart: one size by cm_round, as before
    assert plain["merged"] == {"88": "86"}


def test_a_letter_written_twice_in_a_row_is_the_next_size():
    """9250706389: the OCR read XXL's row as a second "XL" (and the real XL row has "111am"): its measures went under
    W34 and XXL(36) had no row."""
    lines = ["허리둘레 / 힙둘레 / 허벅지둘레 / 밑단둘레 / 총장", "M / 81cm / 101cm / 62cm / 37cm / 101cm",
             "L / 85.5cm / 106cm / 64cm / 38cm / 102cm", "XL / 90cm / 111am / 66cm / 39cm / 103cm",
             "XL / 94.5cm / 116cm / 68cm / 40cm / 104cm"]
    r = _pants(["M(30)", "L(32)", "XL(34)", "XXL(36)"], lines, "mens_bottoms")
    assert [v["us"] for v in r["values"]] == ["W30", "W32", "W34", "W36"]
    assert {row["us"]: row["cm"]["waist"] for row in r["chart"]["rows"]} == {"W30": 81.0, "W32": 85.5, "W36": 94.5}
    whole = C.read_chart(["사이즈 / 허리 / 총장", "M / 81 / 101", "L / 85 / 102", "XL / 90 / 103", "XL / 94 / 104"],
                         "trousers")
    assert whole.rows["XL"]["waist"] == 90 and whole.rows["XXL"]["waist"] == 94
    twice = C.read_chart(["S 총장 41 허리 31", "M 총장 43 허리 34", "S 총장 91 허리 31", "M 총장 92 허리 34"],
                         "trousers")                                   # a second table (5587004670): read as before
    assert twice.rows["S"] == {"length": 91, "waist": 31} and twice.rows["M"]["length"] == 92


def test_rows_all_labelled_one_letter_go_by_position_or_not_at_all():
    """6484235370: four rows all "S", by order S/M/L/XL: the third (L's) was shown under S. A row the chart cannot read
    (a 10 cm leg opening) drops the four; every row read pairs them with the letters in order."""
    real = ["S - 총장 91 / 허리 32 / 힙 44 / 밑위 30 / 밑단 10", "S - 총장 92 / 허리 34 / 힙 46 / 밑위 31 / 밑단 11",
            "S - 총장 93 / 허리 36 / 힙 48 / 밑위 32 / 밑단 12", "S - 총장 94 / 허리 38 / 힙 50 / 밑위 33 / 밑단 13"]
    r = _pants(["S", "M", "L", "XL"], real, "womens_pants")
    assert r["chart"] is None and r["values"][0]["us"] == "S (US 4-6)"
    readable = [line.replace("밑단 1", "밑단 2") for line in real]
    r = _pants(["S", "M", "L", "XL"], readable, "womens_pants")
    assert [(row["us"], row["cm"]["waist"]) for row in r["chart"]["rows"]] == \
        [("S (US 4-6)", 32.0), ("M (US 8-10)", 34.0), ("L (US 12-14)", 36.0), ("XL (US 16)", 38.0)]
    other = _pants(["S", "M", "L"], readable, "womens_pants")         # 3 letters, 4 rows: none
    assert other["chart"] is None


def test_a_table_per_length_option_shows_no_length_and_a_stray_cell_is_skipped():
    """10188121271: one table per 기장 (9부 / 10부); "10 / L(34)", "Rise / XL(36)", "폴리95%,스판5% / L(34)" lost L and
    XL's rows, and W36 took the 10부 length beside the 9부 ones."""
    lines = ["<9부 / >", "사이즈 / 총장 / 허리 / 허벅지 / 밑위 / 밑단", "S(30) / 92.5 / 68 / 33 / 33 / 17",
             "M(32) / 94.5 / 72 / 34 / 34 / 18", "10 / L(34) / 96.5 / 76 / 35 / 35 / 19",
             "Rise / XL(36) / 98.5 / 80 / 36 / 36 / 20", "Thigh→ / Length / <10부",
             "사이즈 / 총장 / 허리 / 허벅지 / 밑위 / 밑단", "S(30) / 98.5 / 68 / 33 / 33 / 17",
             "M(32) / 100.5 / 72 / 34 / 34 / 18", "폴리95%,스판5% / L(34) / 102.5 / 76 / 35 / 35 / 19",
             "XL(36) / 104.5 / 80 / 36 / 36 / 20"]
    r = _pants(["S(30)", "M(32)", "L(34)", "XL(36)"], lines, "mens_bottoms",
               [{"name_ko": "기장", "values_ko": ["9부", "10부"]}])
    assert [(row["us"], row["cm"]["waist"]) for row in r["chart"]["rows"]] == \
        [("W30", 68.0), ("W32", 72.0), ("W34", 76.0), ("W36", 80.0)]
    assert not any("length" in row["cm"] for row in r["chart"]["rows"])
    single = _pants(["S(30)", "M(32)", "L(34)", "XL(36)"], lines, "mens_bottoms")     # no type option: the first
    assert [row["cm"].get("length") for row in single["chart"]["rows"]] == [92.5, 94.5, 96.5, 98.5]
    column = C.read_chart(["허리 / 힙 바로윗쪽의 허리라인 / 힙", "M / 40 / 50 / 1", "허리둘레 / 76 / 81 / 86 / 91"],
                          "trousers")                                  # 5667667561: a measure's row, no stray cell
    assert "76" not in column.rows


def test_a_field_name_before_the_first_pairs_row_is_skipped():
    """10160025240: "크기 / M(32)-허리둘레 84cm, ..." lost the M(32) row."""
    lines = ["크기 / M(32)-허리둘레 84cm, 앞밑위 27cm,힙둘레 104cm,총장103cm",
             "L(34)-허리둘레 88cm, 앞밑위 27.8cm,힙둘레 108cm, 총장103cm"]
    r = _pants(["M(32)", "L(34)"], lines, "mens_bottoms")
    assert [(row["us"], row["cm"]["waist"]) for row in r["chart"]["rows"]] == [("W32", 84.0), ("W34", 88.0)]


def test_a_field_name_row_starts_its_own_table():
    """10322266021 (2026-11-24): "크기 / M(32)-..." after the text rows M..XXL joined their table, so its hip 104 after
    XXL's 116 was dropped as a break; its own block keeps it (L(34) and XL(36) read 힘둘레, OCR, and have no hip)."""
    lines = ["M - 허리둘레 86cm, 앞밑위 27cm, 힙둘레 104cm, 총장 103cm", "L - 허리둘레 90cm, 앞밑위 27.8cm, 힙둘레 108cm, 총장 103cm",
             "XL - 허리둘레 94cm, 앞밑위 28.6cm, 힙둘레 112cm, 총장 105cm",
             "XXL - 허리둘레 98cm, 앞밑위 29.4cm, 힙둘레 116cm, 총장 105cm", "제품 실측 사이즈로 재는 방식에 따라 약간의 오차가 있을 수 있습니다.",
             "크기 / M(32)-허리둘레 84cm, 앞밑위 27cm,힙둘레 104cm,총장103cm", "L(34)-허리둘레 88cm, 앞밑위 27.8cm,힘둘레 108cm, 총장103cm",
             "XL(36)-허리둘레 92cm,앞밑위 28.6cm,힘둘레 112cm,총장105cm", "XXL(38)-허리둘레 96cm, 앞밑위 29.4cm,힙둘레 116cm,총장105cm"]
    r = _pants(["M(32)", "L(34)", "XL(36)", "XXL(38)"], lines, "mens_bottoms")
    assert [(row["us"], row["cm"].get("hip")) for row in r["chart"]["rows"]] == \
        [("W32", 104.0), ("W34", None), ("W36", None), ("W38", 116.0)]


_NOTE = "제품 실측 사이즈로 재는 방식에 따라 약간의 오차가 있을 수 있습니다."


def test_every_size_on_one_line_joined_with_semicolons_is_a_row_each():
    """Volvik 7221598523, 13026234392, 12481527943 and Adidas 7976951536 (2026-11-24): the spec row "크기 | M - ...; L -
    ...; XL - ...; XXL - ..." was read as one row, the first size's; the others were lost."""
    pants = ("크기 | M - 총장 103cm, 허리둘레 86cm, 엉덩이 둘레 104cm; L - 총장 103cm,허리둘레 90cm, 엉덩이 둘레 108cm; "
             "XL - 총장 105cm,허리둘레 94cm, 엉덩이 둘레 112cm; XXL - 총장 105cm,허리둘레 98cm, 엉덩이 둘레 116cm; " + _NOTE)
    chart = C.read_chart([pants], "trousers")
    assert {n: row["waist"] for n, row in chart.rows.items()} == {"M": 86.0, "L": 90.0, "XL": 94.0, "XXL": 98.0}
    assert chart.rows["XXL"] == {"length": 105.0, "waist": 98.0, "hip": 116.0}
    tops = ("크기 | M - 총장 68cm, 가슴둘레 100cm, 밑단둘레 99cm, 어깨너비 43cm, 소매기장 60cm; L - 총장 70cm, 가슴둘레 105cm, "
            "밑단둘레 104cm, 어깨너비 45cm, 소매기장 61cm; XL - 총장 72cm, 가슴둘레 110cm, 밑단둘레 109cm, 어깨너비 47cm, "
            "소매기장 62cm; XXL - 총장 74cm, 가슴둘레 115cm, 밑단둘레 114cm, 어깨너비 49cm, 소매기장 63cm; " + _NOTE)
    chart = C.read_chart([tops], "tops")
    assert {n: row["chest"] for n, row in chart.rows.items()} == {"M": 100.0, "L": 105.0, "XL": 110.0, "XXL": 115.0}
    assert chart.rows["L"] == {"length": 70.0, "chest": 105.0, "shoulder": 45.0, "sleeve": 61.0}
    adidas = ("크기 | 82(M) - 허리둘레 82.0cm, 힙 95.8cm, 인심 85.0cm; 85(L) - 허리둘레 85.0cm, 힙 98.8cm, 인심 85.0cm; "
              "88(XL) - 허리둘레 88.0cm, 힙 101.8cm, 인심 85.0cm; 92(XXL) - 허리둘레 92.0cm, 힙 105.8cm, 인심 85.0cm; " + _NOTE)
    r = _pants(["82 (32인치)", "85 (33인치)", "88 (34인치)", "92 (36인치)"], [adidas], "mens_bottoms")
    assert [(row["us"], row["cm"]["waist"]) for row in r["chart"]["rows"]] == \
        [("W32", 82.0), ("W33", 85.0), ("W34", 88.0), ("W36", 92.0)]
    # never a split: one sized piece, or a piece with a number and no size (a care or a fabric line)
    assert set(C.read_chart(["크기 | M - 총장 103cm, 허리둘레 86cm; 허리 밴딩"], "trousers").rows) == {"M"}
    mixed = C.read_chart(["크기 | M - 총장 103cm, 허리둘레 86cm; L - 총장 103cm, 허리둘레 90cm; 30도 이하 세탁"], "trousers")
    assert set(mixed.rows) == {"M"}


def test_a_letter_with_about_inches_is_the_letter():
    """7221598523 (2026-11-24): "M(약33인치) - 총장 103cm, ..." was no label: its rows went to the one-size row and the
    conflicts."""
    lines = ["M(약33인치) - 총장 103cm, 허리둘레 86cm, 엉덩이 둘레 104cm", "L(약35인치) - 총장 103cm,허리둘레 90cm, 엉덩이 둘레 108cm",
             "M (약33인치) - 허리둘레 86cm, 앞밑위 27cm, 힙둘레 104cm, 총장 103cm"]
    chart = C.read_chart(lines, "trousers")
    assert chart.rows == {"M": {"length": 103.0, "waist": 86.0, "hip": 104.0, "rise": 27.0},
                          "L": {"length": 103.0, "waist": 90.0, "hip": 108.0}}
    assert not chart.conflicts


def test_a_womens_size_beside_each_letter_sizes_it():
    """10997837767: "S(44사이즈)" (the bare letters went out one US size over); 6033600342: "M / 보통55 / 91 ..." rows
    and the recommendation "S / M / L / XL" over "~마른 55 / 보통55 / 보통66 / 통통77" over "날씬66 / 보통77 / 날씬88"
    (2026-11-25, the owner's yes to the Fable review: the second line is the last letters' upper ends, right-aligned;
    "~마른 55" alone is the size under 55): S 44, M 55-66, L 66-77, XL 77-88. Without that second line S and M are
    both 55: the product holds for the owner rather than guess."""
    lines = ["S(44사이즈) :", "총기장 101cm / 허리단면 34-38cm /", "M(55사이즈) :", "L(66사이즈) :", "XL(77사이즈) :"]
    r = _pants(["S", "M", "L", "XL"], lines, "womens_pants")
    assert [v["us"] for v in r["values"]] == ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]
    assert {v["basis"] for v in r["values"]} == {"text_pair"}
    rows = ["S / 90 / 32 / 42 / 28", "마른55 / (왕밴딩)", "M / 보통55 / 91 / 34.5 / 44 / 29", "날씬66 / (왕밴딩)",
            "L / 보통66 / 92 / 37 / 46 / 30", "XL / 통통77 / 93 / 39.5 / 48 / 31", "권장 사이즈 참고!", "S / M / L / XL",
            "~마른 55 / 보통55 / 보통66 / 통통77", "날씬66 / 보통77 / 날씬88"]
    assert A.letter_cells(rows) == [("S", "44"), ("M", "55-66"), ("L", "66-77"), ("XL", "77-88")]
    got = _pants(["S", "M", "L", "XL"], rows, "womens_pants")
    assert not got["held"] and [v["us"] for v in got["values"]] == [
        "XS (US 0-2)", "S-M (US 4-10)", "M-L (US 8-14)", "L-XL (US 12-16)"]
    one_line = rows[:-1]                                              # no second line: S and M both 55, held
    assert A.letter_cells(one_line) == [("M", "55"), ("L", "66"), ("XL", "77"), ("S", "55"), ("M", "55"),
                                        ("L", "66"), ("XL", "77")]
    held = _pants(["S", "M", "L", "XL"], one_line, "womens_pants")
    assert held["held"] == "two Korean sizes on one US size: S (US 4-6)"
    # a second line as long as the first (or a lower upper end) is no upper end: as today
    assert A.letter_cells(["S / M / L", "보통55 / 보통66 / 보통77", "날씬66 / 보통77 / 날씬88"]) == [
        ("S", "55"), ("M", "66"), ("L", "77")]
    assert A.letter_cells(["S / M / L", "보통55 / 보통66 / 보통77", "날씬55 / 보통66"]) == [
        ("S", "55"), ("M", "66"), ("L", "77")]
    part = _pants(["S", "M", "L", "XL"], rows[:6], "womens_pants")    # the rows alone: S has none, today's letters
    assert {v["basis"] for v in part["values"]} == {"fallback_letters"}


def test_the_sellers_body_waist_wins_over_the_womens_size():
    """11318914118: "S / M / L" / "Small / Medium / Large" / "25-26 / 27-28 / 29-30" (inch) over the options "S (55)"
    ...; Toosom 4716253463: "55(25-26),66(27-28),77(29-30),88(31-32)권장드립니다" over the options 55..88."""
    two_rows = ["(단위 inch)", "S / M / L", "Small / Medium / Large", "25-26 / 27-28 / 29-30"]
    r = _pants(["S (55)", "M (66)", "L (77)"], two_rows, "womens_pants")
    assert [v["us"] for v in r["values"]] == ["XS-S (US 0-6)", "S-M (US 4-10)", "M-L (US 8-14)"]
    assert {v["basis"] for v in r["values"]} == {"text_waist"}
    toosom = ["55,66,77,88가지 사이즈로 제작되었습니다", "55(25-26),66(27-28),77(29-30),88(31-32)권장드립니다",
              "55|66|77|88 / 26|27-28|29-30|31-32"]
    r = _pants(["55", "66", "77", "88"], toosom, "womens_pants")
    assert [v["us"] for v in r["values"]] == ["XS-S (US 0-6)", "S-M (US 4-10)", "M-L (US 8-14)", "L (US 12-14)"]
    some = _pants(["55", "66", "77"], ["55(25-26)"], "womens_pants")  # one size of three: kr_women for all
    assert {v["basis"] for v in some["values"]} == {"label"}
    men = _pants(["85", "88"], ["88(34)"], "mens_bottoms")            # the men's "88(34)" is no women's 88
    assert [v["us"] for v in men["values"]] == ["W33", "W34"]


def test_a_row_read_twice_is_no_next_size():
    """The fix review 2026-11-24: "M, L, XL, XL" with the last two rows equal is a repeated line, not XXL."""
    chart = C.read_chart(["사이즈 / 어깨 / 가슴 / 총장", "M / 44 / 52 / 70", "L / 46 / 55 / 72", "XL / 48 / 58 / 74",
                           "XL / 48 / 58 / 74"], "tops")
    assert "XXL" not in chart.rows and "XL" in chart.rows
    twice = C.read_chart(["사이즈 / 허리 / 엉덩이", "S / 34 / 90", "S / 34 / 90"], "trousers")
    assert not twice.ordered


# ---- 2026-11-24: the size_unmapped review (the verified fixes) -----------------------------------------------------
@pytest.mark.parametrize("text, letter, chest, women", [
    ("LL(105호)", "LL", (105.0,), ()), ("3L(110호)", "3L", (110.0,), ()), ("S(90호)", "S", (90.0,), ()),   # 4819248041
    ("75(44/S)", "S", (), (44.0,)), ("80(55/M)", "M", (), (55.0,)), ("90(77/XL)", "XL", (), (77.0,)),     # pgr
    ("85(XS.44)", "XS", (), (44.0,)), ("105(XL.88)", "XL", (), (88.0,)),                                 # Hillcrest
    ("85(XS)", "XS", (85.0,), ()), ("44(85)", None, (85.0,), (44.0,)), ("S(44/55)", "S", (), (44.0, 55.0)),
    ("46(90)", None, (90.0,), ()), ("52(105)", None, (105.0,), ()), ("55(90)", None, (90.0,), (55.0,)),  # IKALOOK
    ("XL(100-여성77이상/남성M)", "XL", (100.0,), ()), ("M(95-남성S)", "M", (95.0,), ()),                     # 5964063532
    ("L(55-66)", "L", (), (55.0, 66.0)), ("M(95-100)", "M", (95.0, 100.0), ()), ("남_M(95)", "M", (95.0,), ()),
    ("WS", "S", (), ()), ("WL", "L", (), ()),                                                             # 13483086996
    ("AL(95)", None, (95.0,), ()), ("AXL(100)", None, (100.0,), ()), ("AS (85)", None, (85.0,), ()),       # 10861903381
    ("A2XL(110)", None, (110.0,), ()),
])
def test_size_unmapped_review_labels(text, letter, chest, women):
    label = A.parse_label(text)
    assert label is not None and (label.letter, label.chest, label.women) == (letter, chest, women)


@pytest.mark.parametrize("text", ["0호", "1호", "82(32)", "블랙(44/S)", "46", "48(M)", "46(44)", "W", "WHITE", "WM-L",
                                  "W32", "L(100-남색)", "M(95-여름)", "AL", "AXL", "A(95)", "AL(60)", "모델착용컷",
                                  "부츠컷"])
def test_size_unmapped_review_leaves_these_unread(text):
    assert A.parse_label(text) is None


def test_size_unmapped_review_label_rules_stay_off_in_the_waist_profiles():
    with A.waist_labels(True):
        assert A.parse_label("75(44/S)") is None
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("50(100)") is None and A.parse_label("W32") is None
        assert A.parse_label("AL(95)") != A.parse_label("(95)")


def test_a_letter_with_a_japanese_chest_in_ho_resolves_in_the_mens_tops():
    """Titleist Japan rain suit 4819248041: S/M/L/LL/3L with the chest 90..110 in 호."""
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["S(90호)", "M(95호)", "L(100호)", "LL(105호)", "3L(110호)"]}], [],
                  None, "타이틀리스트 레인웨어", "mens_tops")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["XS", "S", "M", "L", "XL"]


def test_a_womens_letter_w_and_a_model_photo_note():
    """13483086996 "WS / WM / WL"; 5202996089 "FREE(44~55)모델착용컷" (the model's photo wears it)."""
    assert [v["us"] for v in _resolve(["WS", "WM", "WL"])["values"]] == ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]
    assert A.parse_label("FREE(44~55)모델착용컷") == A.parse_label("FREE(44~55)")
    assert A.parse_label("S모델착용컷") == A.parse_label("S")
    assert A.parse_label("S(44)모델착용사이즈") == A.parse_label("S(44)")
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["FREE(44~55)모델착용컷", "L(66~77)"]}], [], None, "바지",
                  "womens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["XS-S (US 0-6)", "M-L (US 8-14)"]


def test_a_mens_waist_of_46_inches():
    """6818506441: 30..46; its 46 held "not read" (the men's waist stopped at 44)."""
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("46").waist == (116.8,) and A.parse_label("47") is None
    with A.waist_labels(True):
        assert A.parse_label("46") is None
    values = ["30", "32", "34", "36", "38", "40", "42", "44", "46"]
    r = _pants(values, [], "mens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == [f"W{v}" for v in values]
    assert r["values"][-1]["letter"] == "4XL"
    assert _pants(values[:-1], [], "mens_bottoms")["values"][-1]["us"] == "W44"
    assert _pants(["44", "46", "48"], [], "mens_bottoms")["held"] == "'48': not read as a size"
    mens = A.grids()["profiles"]["mens_bottoms"]
    assert A._grid_row(mens, 125.0) is None and A._grid_row(mens, 111.8)["us"] == "4XL"


def test_a_mens_letter_ladder_with_its_waist_in_cm():
    """Nike 10522424335: "S(75) / M(80) / L(85) / XL(90) / 2XL(95)": XL(90) read as a top's chest and held."""
    r = _pants(["S(75)", "M(80)", "L(85)", "XL(90)", "2XL(95)"], [], "mens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["W29", "W31", "W33", "W35", "W37"]
    assert "no US size" in _pants(["S(85)", "M(90)", "L(95)", "XL(100)", "2XL(105)"], [], "mens_bottoms")["held"]
    assert _pants(["S(75)", "M(80)", "XL(100)"], [], "mens_bottoms")["held"]
    assert _pants(["XL(90)", "2XL(95)"], [], "mens_bottoms")["held"]
    assert "'M(95)': no US size" in _pants(["82(32)", "85(33)", "88(34)", "92(36)", "M(95)", "L(100)", "XL(105)",
                                            "2XL(110)"], [], "mens_bottoms")["held"]
    assert _pants(["M(32)", "L(34)", "M (95)", "L (100)"], [], "mens_bottoms")["held"]


def test_a_womens_size_glued_to_a_hangul_word_and_a_letter_after_a_dash():
    """5895988627 "블랙하운드55", 10968014964 "긴팔55", 7124536208 "화이트-S" (2026-11-24)."""
    with A.waist_labels(True):
        got = A.split_joined([{"name_ko": "사이즈", "values_ko": ["블루하운드 55", "블루하운드 66", "블랙하운드55",
                                                                "블랙하운드66"]}])
    assert got == (0, [("블루하운드", "55"), ("블루하운드", "66"), ("블랙하운드", "55"), ("블랙하운드", "66")])
    assert A._words("긴팔55") == ["긴팔", "55"]
    for whole in ("네이비82", "화이트95", "HG329255", "반팔2", "블랙-95", "잔피엘-151", "S-M", "55-66", "L(55-66)",
                  "SW-422", "10부-네이비"):
        assert A._words(whole) == [whole]
    with A.waist_labels(A.MENS_WAIST):
        assert A._words("블랙34") == ["블랙", "34"]
    assert A._words("화이트-S") == ["화이트", "S"]
    assert A.split_joined([{"name_ko": "컬러/ 사이즈", "values_ko": ["화이트-S", "화이트-M", "블랙-S"]}]) \
        == (0, [("화이트", "S"), ("화이트", "M"), ("블랙", "S")])


def test_one_sleeve_word_before_every_size_is_dropped():
    """10968014964: 사이즈 "긴팔55 / 긴팔66 / 긴팔77" beside 컬러: the sizes alone, no second 컬러 option."""
    colours = ["베이직카라티 블랙", "베이직카라티 화이트"]
    sizes = ["긴팔55", "긴팔66", "긴팔77"]
    ov = {"options": [{"name_ko": "컬러", "values_ko": colours}, {"name_ko": "사이즈", "values_ko": sizes}],
          "facts": [], "variants": [{"options_ko": [c, x], "price_krw": 1} for c in colours for x in sizes]}
    out = T._sizes(ov, "womens_tops", "", [], None, "여성 카라티")
    assert not out["held"] and ov["options"] == [{"name_ko": "컬러", "values_ko": colours},
                                                 {"name_ko": "사이즈", "values_ko": ["55", "66", "77"]}]
    assert ov["variants"][0]["options_ko"] == ["베이직카라티 블랙", "55"]
    # a colour before the size keeps an option of its own; an option not named a size, two sleeve words: as before
    ov = {"options": [{"name_ko": "사이즈", "values_ko": ["베이지 S", "베이지 M"]}], "facts": [],
          "variants": [{"options_ko": [x], "price_krw": 1} for x in ("베이지 S", "베이지 M")]}
    T._sizes(ov, "womens_tops", "", [], None, "여성 니트")
    assert ov["options"] == [{"name_ko": "컬러", "values_ko": ["베이지"]}, {"name_ko": "사이즈", "values_ko": ["S", "M"]}]
    ov = {"options": [{"name_ko": "선택", "values_ko": ["긴팔 S", "긴팔 M"]}], "facts": [],
          "variants": [{"options_ko": [x], "price_krw": 1} for x in ("긴팔 S", "긴팔 M")]}
    T._sizes(ov, "womens_tops", "", [], None, "여성 니트")
    assert ov["options"][0] == {"name_ko": "선택", "values_ko": ["긴팔"]}
    two = ["긴팔55", "반팔55", "긴팔66", "반팔66"]
    ov = {"options": [{"name_ko": "사이즈", "values_ko": two}], "facts": [],
          "variants": [{"options_ko": [x], "price_krw": 1} for x in two]}
    T._sizes(ov, "womens_tops", "", [], None, "여성 니트")
    assert ov["options"][0] == {"name_ko": "컬러", "values_ko": ["긴팔", "반팔"]}


def test_a_size_fact_of_a_colour_and_free_in_brackets_is_one_size():
    """11492588480 "컬러/사이즈: 블랙(free)" held "not read"."""
    for value, held in (("블랙(free)", False), ("화이트 (FREE)", False), ("블랙(55)", True),
                        ("블랙(free)사이즈별상이", True)):
        ov = {"options": [], "facts": [{"label_ko": "컬러/사이즈", "value_ko": value}],
              "variants": [{"options_ko": [], "price_krw": 1}]}
        out = T._sizes(ov, "womens_tops", "", [], None, "여성 니트")
        assert bool(out["held"]) is held, value
        if not held:
            assert out["fact"] == {"label_ko": "컬러/사이즈", "ko": value, "us": "One Size"}


def test_adidas_asian_waist_code_with_its_inch():
    """7191019224, 10159594995: "HG3292 블랙 A82 (32인치)" held as colour and size in one option; the seller's inch."""
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("A82 (32인치)") == A.parse_label("82(32)") == A.parse_label("A82(32인치)")
        assert A.parse_label("A82") is None
        got = A.split_joined([{"name_ko": "선택", "values_ko": ["HG3292 블랙 A82 (32인치)", "HG3296 그레이 A76 (31인치)"]}])
        assert A.split_joined([{"name_ko": "선택2", "values_ko": ["AXL (110)", "AL (105)"]}]) is None
    assert got == (0, [("HG3292 블랙", "A82 (32인치)"), ("HG3296 그레이", "A76 (31인치)")])
    assert A.cm_inch("A82 (32인치)") == (82, 32) and A.cm_inch("A82 (45인치)") is None
    with A.waist_labels(None):
        assert A.parse_label("A82 (32인치)") is None
    r = _pants(["A79 (30인치)", "A82 (31인치)", "A85 (33인치)", "A88 (34인치)", "A92 (35인치)", "A96 (37인치)"], [],
               "mens_bottoms")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["W30", "W31", "W33", "W34", "W35", "W37"]
    assert [v["us"] for v in _pants(["A76 (31인치)"], [], "mens_bottoms")["values"]] == ["W31"]
    # two codes on one inch (8116691038's models) are never merged: held
    r = _pants(["A76 (31인치)", "A79 (31인치)", "A82 (32인치)"], [], "mens_bottoms")
    assert r["held"] == "two Korean sizes on one US size: W31" and not r["merged"]
    assert _pants(["A79", "A82"], [], "mens_bottoms")["held"]


def test_a_colour_a_chest_and_its_letter_in_one_value():
    """10940191023 "오프화이트 85 XS" .. "블랙 100 L": split by the number, the seller's letter must agree."""
    values = ["오프화이트 85 XS", "오프화이트 90 S", "티블루 95 M", "블랙 100 L"]
    assert A.split_joined([{"name_ko": "선택사항", "values_ko": values}]) \
        == (0, [("오프화이트", "85"), ("오프화이트", "90"), ("티블루", "95"), ("블랙", "100")])
    for bad in (["블랙 85 L", "블랙 90 S"], ["블랙 85 XS", "블랙 90 XS"], ["블랙 85 XS"]):
        assert A.number_letter_split([{"name_ko": "선택", "values_ko": bad}]) is None
    ov = {"options": [{"name_ko": "선택사항", "values_ko": values}], "facts": [],
          "variants": [{"options_ko": [x], "price_krw": 1} for x in values]}
    out = T._sizes(ov, "womens_tops", "", [], None, "여성 니트")
    assert not out["held"] and [v["us"] for v in out["values"]] == ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)",
                                                                    "L (US 12-14)"]
    off = ["블랙 90 XS", "블랙 95 S"]                        # the profile says S / M: held on the disagreement
    ov = {"options": [{"name_ko": "선택", "values_ko": off}], "facts": [],
          "variants": [{"options_ko": [x], "price_krw": 1} for x in off]}
    assert "disagrees" in T._sizes(ov, "womens_tops", "", [], None, "여성 니트")["held"]


def test_a_bare_letter_beside_its_numbered_spelling_is_merged():
    """7864006253: "L" beside "L（66사이즈）" (the chart's "L(66)" row sizes the bare L): one size written twice."""
    lines = ["사이즈 / 허리 / 엉덩이 / 밑위 / 총장", "S(44) / 28.5 / 44 / 28 / 88", "M(55) / 30 / 46 / 29 / 89",
             "L(66) / 32 / 48 / 30 / 90", "XL(77) / 34 / 50 / 31 / 91"]
    r = _pants(["S（44사이즈）", "M（55사이즈）", "L（66사이즈）", "XL（77사이즈）", "FREE", "XL", "L"], lines,
               "womens_pants")
    assert not r["held"] and r["merged"] == {"XL": "XL（77사이즈）", "L": "L（66사이즈）"}
    assert [v["us"] for v in r["values"]] == ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)", "One Size"]
    # a bare letter on the fallback beside its numbered spelling, two letters on one size: held as before
    assert _resolve(["S(90)", "S"])["held"] == "two Korean sizes on one US size: S (US 4-6)"
    assert _resolve(["S(95)", "M(95)"])["held"]


def test_a_womens_waist_range_in_inches_up_to_three_apart():
    """12370291326 "2XL(32~33)", "M(26반~27)" held: 33 read as a women's 33, 26반 not read."""
    with A.waist_labels(True):
        assert A.parse_label("2XL(32~33)").waist == (81.3, 83.8) and not A.parse_label("2XL(32~33)").women
        assert A.parse_label("M(26반~27)").waist == (67.3, 68.6)
        assert A.parse_label("XXL(33~34인치)").waist == (83.8, 86.4)
        assert A.parse_label("2XL(33~35)").waist == (83.8, 88.9)
        assert A.parse_label("XS(33~44)").women == (33.0, 44.0)
        assert A.parse_label("55~66").women == (55.0, 66.0)
        assert A.parse_label("26반") is None
    assert A.parse_label("XS (33~44)").women == (33.0, 44.0)
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("55~66").waist == (66.0,)                                  # as before
        assert A.parse_label("XS(33~44)").waist == (83.8, 111.8)


def test_a_mens_waist_and_length_in_one_value():
    """9918112671 "33-30" (waist 33, length 30): held as two Korean sizes on one US size."""
    values = ["30-30", "32-32", "32-34", "33-30", "34-32", "40-32", "30-32", "32-30"]
    with A.waist_labels(A.MENS_WAIST):
        assert A.split_joined([{"name_ko": "컬러", "values_ko": ["블랙"]}, {"name_ko": "사이즈", "values_ko": values}]) \
            == (1, [(f"기장{v[3:]}", v[:2]) for v in values])
        assert A.parse_label("기장30") is None
        assert A.split_waist_length([{"name_ko": "사이즈", "values_ko": ["30-31", "32-33"]}]) is None
        assert A.split_waist_length([{"name_ko": "사이즈", "values_ko": ["30-30", "M"]}]) is None
    with A.waist_labels(True):
        assert A.split_waist_length([{"name_ko": "사이즈", "values_ko": ["25-26", "27-28"]}]) is None
    ov = {"options": [{"name_ko": "컬러", "values_ko": ["블랙"]}, {"name_ko": "사이즈", "values_ko": values}], "facts": [],
          "variants": [{"options_ko": ["블랙", v], "price_krw": 1} for v in values]}
    out = T._sizes(ov, "mens_bottoms", "", [], None, "남성 골프바지")
    assert not out["held"] and not out["merged"]
    assert [v["us"] for v in out["values"]] == ["W30", "W32", "W33", "W34", "W40"]
    assert ov["options"][1] == {"name_ko": "기장", "values_ko": ["기장30", "기장32", "기장34"]}
    assert ov["variants"][2]["options_ko"] == ["블랙", "기장34", "32"]
    assert _pants(["32~33인치", "33~34인치"], [], "mens_bottoms")["values"][0]["us"] == "W32-33"


def test_one_variant_joining_a_colour_and_a_numbered_size_in_a_fact():
    """halfclub 12487907002, 13291281940, 13684467368: "선택하기: Dark Navy/090", one variant, held as an unknown
    size of the chart's several."""
    chart = ["사이즈 / 가슴 / 총장", "085 / 88 / 60", "090 / 93 / 61", "095 / 98 / 62"]

    def run(value: str, variants: int = 1, lines: list[str] = chart) -> dict[str, Any]:
        ov = {"options": [], "facts": [{"label_ko": "선택하기", "value_ko": value}],
              "variants": [{"options_ko": [], "price_krw": 1}] * variants}
        return T._sizes(ov, "womens_tops", "\n".join(lines), [], None, "여성 니트")
    assert A.single_joined("Dark Navy/090") == ("Dark Navy", "090")
    out = run("Dark Navy/090")
    assert not out["held"] and out["fact"] == {"label_ko": "선택하기", "ko": "090", "us": "S (US 4-6)"}
    assert run("Black/095")["fact"]["us"] == "M (US 8-10)"
    assert "the chart lists" in run("CW4742 화이트 L")["held"]                      # a letter alone: as before
    assert "colour and size in one value" in run("CW4742 화이트 L", lines=[])["held"]          # (5152708008)
    assert "the chart lists" in run("Dark Navy/090", 2)["held"]
    assert "colour and size in one value" in run("Dark Navy/090", 2, [])["held"]
    assert "the chart lists" in run("Black")["held"]
    assert A.single_joined("IS7132 블랙 AL (110)") is None                          # adidas' (9998916822)
    assert not A.joined_value("FREE/그레이") or A.single_joined("FREE/그레이") is None


def test_adidas_asian_letter_with_its_chest_one_to_one():
    """10861903381 "IS4776 화이트 AL(95)"; 5176506757's AM (100) beside AM (105) and AL (105) holds, never merged."""
    assert A.split_joined([{"name_ko": "선택", "values_ko": ["IS4776 화이트 AL(95)", "IS4777 블랙 AS(85)"]}]) \
        == (0, [("IS4776 화이트", "AL(95)"), ("IS4777 블랙", "AS(85)")])
    r = _resolve(["AS(85)", "AM(90)", "AL(95)", "AXL(100)"])
    assert not r["held"] and [v["us"] for v in r["values"]] == ["XS (US 0-2)", "S (US 4-6)", "M (US 8-10)",
                                                                "L (US 12-14)"]
    r = _resolve(["AM (100)", "AM (105)", "AL (105)"], name="선택2")
    assert "an adidas Asian size with two numbers" in r["held"] and not r["merged"]
    assert A.split_joined([{"name_ko": "선택", "values_ko": ["KG2154 화이트 AS", "KG2154 화이트 AM"]}]) is None
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("AL(95)") is None


def test_a_group_products_size_in_its_title():
    """베러투데이 13004790971: the title "... 가디건 블랙, 105", the listing's name "... 가디건", one variant, no option."""
    one = {"options": [], "facts": [], "variants": [{"options_ko": [], "price_krw": 1}]}
    base = "베러투데이 여성 가을 니트 코디 빅사이즈 골프웨어 사계절 포켓 가디건"
    assert T.title_size(one, f"{base} 블랙, 105", base, f"{base}") == ("블랙", "105")
    assert T.title_size(one, f"{base} 블랙, 105", f"{base} 블랙, 105", None) is None
    assert T.title_size(one, f"{base} 블랙, 105", None, None) is None
    assert T.title_size(one, "베러투데이 티셔츠 1+1, 2", "베러투데이 티셔츠", None) is None
    assert T.title_size(one, f"{base} 화이트, FREE", base, None) is None
    assert T.title_size(one, f"{base} 핑크, 110", base, "베러투데이 티셔츠 95") is None      # 12994831966
    assert T.title_size(one, "나이키 폴로 코랄핑크, S", "나이키 폴로", None) is None              # 13660201494
    assert T.title_size({**one, "options": [{"name_ko": "사이즈", "values_ko": ["95"]}]}, f"{base} 블랙, 105", base,
                        None) is None
    assert T.title_size(one, "집업 니트 블랙 가디건 RWSCN8208,N8208", "집업 니트 블랙 가디건", None) is None



# ---- 2026-11-25: the size_unmapped review, second pass (Fable's review, the products chosen to sell) --------------
def _rows(names: list[str], combos: list[tuple[str, ...]]) -> list[dict[str, Any]]:
    return [{"options": list(c), "price": 1} for c in combos]


def test_a_garment_the_section_does_not_sell_is_left_out_not_held():
    """13762280030 (A): a Volvik and an adidas polo with two trousers under one design option; the trousers' rows
    go, the size option's own values are never matched, two garments kept under the option take no size chart."""
    names = ["디자인 선택", "사이즈 선택"]
    rows = _rows(names, [("볼빅 남성 골프 긴팔 카라티 티셔츠", "M(95)"), ("아디다스 골프티_긴팔", "L(100)"),
                         ("아디다스 [봄/가을]골프 긴바지", "82(32)"), ("볼빅 남성 [기모본딩] 밴딩스판 골프 바지", "M(86cm / 32인치)")])
    kept, left, mixed = T._drop_off_section(names, rows, ("trousers",), "50002796")
    assert [r["options"][0] for r in kept] == ["볼빅 남성 골프 긴팔 카라티 티셔츠", "아디다스 골프티_긴팔"]
    assert left and left.startswith("2 variants: 아디다스 [봄/가을]골프 긴바지") and mixed and "디자인 선택" in mixed
    # one garment left (9177463189), one garment in colours (9068863945): the chart stays
    rows = _rows(names, [("(골프폴로티셔츠)블랙", "M"), ("(골프폴로티셔츠)화이트", "L"), ("(골프바지)블랙", "82(32)")])
    kept, left, mixed = T._drop_off_section(names, rows, ("trousers",), "50002796")
    assert len(kept) == 2 and left == "1 variants: (골프바지)블랙" and mixed is None
    # every row matches: nothing left out (prepare holds off_section_variant as before)
    rows = _rows(names, [("골프 바지 블랙", "82"), ("골프 바지 네이비", "85")])
    assert T._drop_off_section(names, rows, ("trousers",), "50002796") == (rows, None, None)
    # a size option's own values are never matched: an option named a size, or most values sizes
    rows = _rows(["컬러", "사이즈"], [("블랙", "M(팬츠)"), ("블랙", "L")])
    assert T._drop_off_section(["컬러", "사이즈"], rows, ("trousers",), "50002796")[1] is None
    # five adidas trousers of one maker are one garment kind (5534297375): the polo goes, the chart stays
    rows = _rows(["선택", "사이즈"], [("아디다스 바지(봄/가을)25", "82(32)"), ("아디다스 쿨바지(여름)26new", "85(33)"),
                                    ("아디다스 긴팔 폴로티 26new", "M(95)")])
    kept, left, mixed = T._drop_off_section(["선택", "사이즈"], rows, ("other_item", "shorts"), "50002801")
    assert len(kept) == 2 and left == "1 variants: 아디다스 긴팔 폴로티 26new" and mixed is None


def test_the_trousers_code_never_drops_a_top():
    """The new code 'trousers' of 50002796 (바지, 팬츠, pants); a top's words stay."""
    import listing_filter as LF
    rules = [{k: r[k] for k in r if k != "requires"} for r in LF.title_rules("50002796") if r["code"] == "trousers"]
    for value in ("조거 팬츠 블랙", "(골프바지)네이비", "아디다스 [봄/가을]골프 긴바지"):
        assert LF.title_rule(value, rules) == "title:trousers"
    for value in ("맨투맨 블랙", "후드 집업 그레이", "볼빅 남성 골프 긴팔 카라티 티셔츠", "(골프폴로티셔츠)블랙", "S 28~29인치"):
        assert LF.title_rule(value, rules) is None


def test_two_spellings_of_one_cm_waist_are_one_size_and_two_cm_on_one_inch_part():
    """5815131892: "85(33)" and "85(35)", "88(34)" and "88(35)" (one row per cm in each colour): one US waist, the
    cm_round's, each spelling its own Naver value (2026-11-25, the correctness review: the merge rewrote 블랙's
    "85(35)" to "85(33)", a size 블랙 does not sell), allowed only when no colour sells both; 11017948766: "85(34)"
    beside "88(34)": 85 takes its own cm_round, W33."""
    values = ["82(32)", "85(33)", "88(34)", "92(36)", "88(35)", "85(35)"]
    colours = {"블랙": ["85(35)", "88(35)"], "그레이": ["85(33)", "88(35)"], "네이비": ["82(32)", "85(33)", "88(34)", "92(36)"]}
    combos = [[c, v] for c, vs in colours.items() for v in vs]
    options = [{"name_ko": "컬러", "values_ko": list(colours)}, {"name_ko": "사이즈", "values_ko": values}]
    lines = ["사이즈 / 82 / 85 / 88 / 92", "허리 / 81 / 84 / 87 / 91"]
    r = A.resolve(options, lines, None, "골프 바지", "mens_bottoms", combos=combos)
    assert not r["held"] and r["merged"] == {}
    assert [(v["ko"], v["us"], v["basis"]) for v in r["values"]] == [
        ("82(32)", "W32", "waist"), ("85(33)", "W33", "waist"), ("85(35)", "W33", "cm_round"),
        ("88(34)", "W34", "waist"), ("88(35)", "W34", "cm_round"), ("92(36)", "W36", "waist")]
    assert r["chart"] and "chart_left_out" not in r                   # one cm written two ways: its one row
    # negatives: a colour selling both spellings holds; without combos it holds (never merged)
    both = A.resolve(options, lines, None, "골프 바지", "mens_bottoms", combos=combos + [["블랙", "85(33)"]])
    assert both["held"] == "two Korean sizes on one US size: W33, W34"
    assert _pants(values, [], "mens_bottoms")["held"] == "two Korean sizes on one US size: W33, W34"
    r = _pants(["82(32)", "85(34)", "88(34)", "92(36)"], [], "mens_bottoms")
    assert not r["held"] and [(v["ko"], v["us"], v["basis"]) for v in r["values"]] == [
        ("82(32)", "W32", "waist"), ("85(34)", "W33", "cm_round"), ("88(34)", "W34", "waist"), ("92(36)", "W36", "waist")]
    # negatives: adidas' codes on one inch hold; 86 = 34 and 88 = 35 stay two sizes; the seller's inch otherwise wins
    assert "two Korean sizes on one US size" in _pants(["A76 (31인치)", "A79 (31인치)"], [], "mens_bottoms")["held"]
    assert [v["us"] for v in _pants(["86(34)", "88(35)"], [], "mens_bottoms")["values"]] == ["W34", "W35"]
    assert [v["us"] for v in _pants(["85(34)", "92(36)"], [], "mens_bottoms")["values"]] == ["W34", "W36"]
    # the cm_round inch taken already: held as before
    assert _pants(["85(34)", "88(34)", "84(33)"], [], "mens_bottoms")["held"]
    # two spellings of one cm, neither the cm_round inch: nothing merged
    assert not _pants(["85(35)", "85(36)"], [], "mens_bottoms")["merged"]
    assert A._cm_inch_collisions({"values_ko": ["85(33)", "85(35)"]}, A.grids()["profiles"]["womens_pants"]) == {}


def test_5815131892_every_variant_orders_its_own_naver_size():
    """The fixture (2026-11-25, the correctness review): each variant's size value is the one Naver sells it under."""
    import json
    from transform import prepare
    from transform_shops import rules_for
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", "collected", "5815131892.json"), encoding="utf-8") as f:
        line = json.load(f)
    with open(os.path.join(here, "fixtures", "description_images", "5815131892.json"), encoding="utf-8") as f:
        side = json.load(f)
    p = prepare(line, rules_for("fairwardgolf"), "r", 1, side)
    naver = {str(v["id"]): v["options"] for v in line["specs"]["options"]["variants"]}
    assert p["status"] == "ready" and p["product"]["variants"]
    for v in p["product"]["variants"]:
        assert v["options_ko"][-1] == naver[str(v["naver_variant_id"])][-1].strip()
    black = [v for v in p["product"]["variants"] if v["naver_variant_id"] == "52973793593"]
    assert black and black[0]["options_ko"][-1] == "85(35)"
    us = {v["ko"]: v["us"] for v in p["product"]["sizes"]["values"]}
    assert us["85(35)"] == us["85(33)"] == "W33" and us["88(35)"] == us["88(34)"] == "W34"


def _gendered(values: list[str], genders: list[str], extra: list[str] | None = None) -> dict[str, Any]:
    return {"options": [{"name_ko": "사이즈", "values_ko": values}], "facts": [],
            "variants": [{"sku": f"s{i}", "options_ko": [v], "price_krw": 1, "available": True}
                         for i, v in enumerate(values)]}, {f"s{i}": g for i, g in enumerate(genders)}


def test_a_mixed_product_is_sized_per_gender():
    """Hallo 7266270685 (B): 여성용 55 / 66 / 77 beside 남성용 100 / 105 / 110, all once on the women's tops (77 and 100
    both L (US 12-14)); each gender on its own profile, the labels say whose."""
    from transform_shops import rules_for
    tops = rules_for("fairwardgolf").categories["50002796"]
    ov, by_sku = _gendered(["55", "66", "77", "100", "105", "110"], ["womens"] * 3 + ["mens"] * 3)
    chart = ["여성용 상세 사이즈", "사이즈 / 55 / 66 / 77", "가슴단면 / 43 / 45 / 47", "남성용 상세 사이즈",
             "사이즈 / 100 / 105 / 110", "가슴단면 / 53 / 55 / 57"]
    out = T._sizes_by_gender(ov, tops, by_sku, "\n".join(chart), [], None, "할로 티셔츠")
    assert out and not out["held"]
    assert [(v["ko"], v["us"], v["profile"]) for v in out["values"]] == [
        ("55", "Women's S (US 4-6)", "womens_tops"), ("66", "Women's M (US 8-10)", "womens_tops"),
        ("77", "Women's L (US 12-14)", "womens_tops"), ("100", "Men's M", "mens_tops"), ("105", "Men's L", "mens_tops"),
        ("110", "Men's XL", "mens_tops")]
    assert out["profiles"] == {"womens": "womens_tops", "mens": "mens_tops"}
    html = A.chart_html(out)
    assert "Fits bust / chest" in html and "<td>Men's M</td>" in html and "<td>38–40 in</td>" in html
    # by the value's own prefix (6485458095, 8325761055): "남성(95)" beside "여성(95)" stays two sizes
    ov, by_sku = _gendered(["여성(85)", "여성(95)", "남성(95)", "남성(100)"], ["unisex"] * 4)
    out = T._sizes_by_gender(ov, tops, by_sku, "", [], None, "레인코트")
    assert [v["us"] for v in out["values"]] == ["Women's XS (US 0-2)", "Women's M (US 8-10)", "Men's S", "Men's M"]
    # one value under both genders, a unisex value, one gender's values only: held, never sized on one profile
    # (2026-11-25, the Fable review: Dennis 11287527628, Malbon 12375182812)
    ov, by_sku = _gendered(["95", "100", "100"], ["womens", "mens", "womens"])
    ov["variants"][1]["options_ko"] = ["100"]
    shared = T._sizes_by_gender(ov, tops, {"s0": "womens", "s1": "mens", "s2": "womens"}, "", [], None, "")
    assert shared and "not each one gender's" in shared["held"]
    ov, by_sku = _gendered(["90", "100"], ["unisex", "mens"])
    assert "not each one gender's" in T._sizes_by_gender(ov, tops, by_sku, "", [], None, "")["held"]
    ov, by_sku = _gendered(["55", "66"], ["womens", "womens"])
    assert T._sizes_by_gender(ov, tops, by_sku, "", [], None, "")["held"]
    # no size option, one size only: not this rule (None)
    assert T._sizes_by_gender({"options": [], "facts": [], "variants": []}, tops, {}, "", [], None, "") is None
    ov, by_sku = _gendered(["FREE"], ["womens"])
    assert T._sizes_by_gender(ov, tops, by_sku, "", [], None, "") is None
    # a category with the women's profile only (windbreakers 50002798): held
    wind = rules_for("fairwardgolf").categories["50002798"]
    ov, by_sku = _gendered(["090", "100"], ["womens", "mens"])
    assert "no men's size profile" in T._sizes_by_gender(ov, wind, by_sku, "", [], None, "")["held"]
    # either gender held: the result holds (prepare holds it; the trousers, sized as men's, take the one profile)
    ov, by_sku = _gendered(["44", "130(XXXL)"], ["womens", "mens"])
    assert T._sizes_by_gender(ov, tops, by_sku, "", [], None, "")["held"]
    # a single-profile chart keeps its words
    one = A.resolve([{"name_ko": "사이즈", "values_ko": ["95", "100"]}], [], None, "", "mens_tops")
    assert "Fits chest is" in A.chart_html(one)


def test_a_variant_naming_both_genders_leaves_a_one_gender_product():
    """Pinkpang 5691897960 (C): '남성용 XXL (여성용 88)' beside the women's M (55) / L (66) / XL (77), the 성별 row and
    the title women's: left out; then "체크 A라인 M (55)" splits and reads by the women's sizes."""
    rows = [{"label": "성별", "value": "여성용"}]

    def ov() -> dict[str, Any]:
        values = ["체크 A라인 M (55)", "체크 A라인 L (66)", "체크 A라인 XL (77)", "남성용 XXL (여성용 88)"]
        return {"options": [{"name_ko": "종류", "values_ko": list(values)}], "facts": [],
                "variants": [{"sku": f"s{i}", "options_ko": [v]} for i, v in enumerate(values)]}
    o = ov()
    assert T._drop_both_genders(o, rows, "4사이즈 체크 레인코트 여성용 골프우비", None) == \
        "1 variants: 남성용 XXL (여성용 88)"
    assert o["options"][0]["values_ko"] == ["체크 A라인 M (55)", "체크 A라인 L (66)", "체크 A라인 XL (77)"]
    out = T._sizes(o, "womens_tops", "", [], None, "레인코트")
    assert not out["held"] and [v["us"] for v in out["values"]] == ["S (US 4-6)", "M (US 8-10)", "L (US 12-14)"]
    # negatives: a unisex row, a title of another gender, no title gender, every variant naming both
    assert T._drop_both_genders(ov(), [{"label": "성별", "value": "남녀공용"}], "레인코트 여성용", None) is None
    assert T._drop_both_genders(ov(), rows, "4사이즈 체크 레인코트 남성용", None) is None
    assert T._drop_both_genders(ov(), rows, "체크 레인코트", None) is None
    both = {"options": [{"name_ko": "종류", "values_ko": ["남성용 XXL (여성용 88)"]}], "facts": [],
            "variants": [{"sku": "s0", "options_ko": ["남성용 XXL (여성용 88)"]}]}
    assert T._drop_both_genders(both, rows, "레인코트 여성용", None) is None


@pytest.mark.parametrize("value, words", [
    ("체크 A라인 M (55)", ["체크", "A라인", "M (55)"]),                     # 5691897960
    ("AS (85)", ["AS (85)"]), ("IS4776 화이트 AS (85)", ["IS4776", "화이트", "AS (85)"]),
    ("오프화이트 85 XS", ["오프화이트", "85", "XS"]), ("M (66)", ["M", "(66)"]),  # a whole label: not joined (2 words)
])
def test_a_letter_and_its_bracketed_size_after_a_space_is_one_word(value, words):
    assert A._words(value) == words
    with A.waist_labels(A.MENS_WAIST):
        assert A._words("블랙 M (32)") == ["블랙", "M", "(32)"]           # never in the waist profiles
        assert A._words("HG3292 블랙 A82 (32인치)")[-1] == "A82 (32인치)"
    assert A._joined_size("M (66)") is None                              # a whole value is a label, no colour


def test_a_korean_size_word_with_its_letter_and_the_tip_floor():
    """핑크골프 7965635614 (D): 프리(F) / 라지(L) / 엑스라지(XL), the chart "F-프리(55~66)" / "L-라지(통통66~77)" /
    "XL-엑스라지(통통77~)", the tip "엑스라지(XL)사이즈 - 88이상"."""
    from size_labels import parse_label as P
    assert P("라지(L)").letter == "L" and P("엑스라지(XL)").letter == "XL" and P("프리(F)").free
    assert P("라지(XL)") is None and P("라지(77-88)").women == (77.0, 88.0)          # the word and letter must agree
    assert P("F-프리(55~66)").free and P("F-프리(55~66)").women == (55.0, 66.0)
    assert P("L-라지(통통66~77)").women == (66.0, 77.0) and P("XL-라지(77~)") is None
    chart = ["사이즈(cm) / 허리 단면 / 총기장", "F-프리(55~66) / 33 / 43", "L-라지(통통66~77) / 35 / 43",
             "XL-엑스라지(통통77~) / 37 / 45"]
    tip = ["프리(F) - 정66까지", "라지(L) - 77반까지", "엑스라지(XL)사이즈 - 88이상"]
    r = _pants(["프리(F)", "라지(L)", "엑스라지(XL)"], chart + tip, "womens_bottoms")
    assert not r["held"] and [(v["us"], v["basis"]) for v in r["values"]] == [
        ("S-M (US 4-10)", "label"), ("M-L (US 8-14)", "chart_pair"), ("XL (US 16)", "text_tip")]
    assert A.tip_floors(tip) == {"XL": 88.0}
    # negatives: F alone is One Size; without the tip XL takes the chart's 77 as before
    assert _pants(["프리(F)"], chart, "womens_bottoms")["values"][0]["us"] == "One Size"
    assert [v["us"] for v in _pants(["라지(L)", "엑스라지(XL)"], chart, "womens_bottoms")["values"]] == \
        ["M-L (US 8-14)", "L (US 12-14)"]


def test_a_free_size_and_letters_by_the_sellers_inch_line():
    """할로 5282622633 (D): FREE（44-66반） / XL（통통66반이상） / 2XL（77이상） and the seller's "25-27인치 free /
    28-30인치 XL / 30-31인치2XL"."""
    from size_labels import parse_label as P
    assert P("XL（통통66반이상）").women == (66.5,) and P("2XL（77이상）").women == (77.0,)
    lines = ["평소사이즈:26-27inch", "25-27인치 free", "28-30인치 XL", "30-31인치2XL"]
    r = _pants(["FREE（44-66반）", "XL（통통66반이상）", "2XL（77이상）"], lines, "womens_bottoms")
    assert not r["held"] and [(v["us"], v["basis"]) for v in r["values"]] == [
        ("XS-S (US 0-6)", "text_waist"), ("M-L (US 8-14)", "text_waist"), ("L (US 12-14)", "text_waist")]
    # negatives: FREE alone stays One Size; a model line never pairs; a waist for only some values: none taken
    assert _pants(["FREE（44-66반）"], lines, "womens_bottoms")["values"][0]["us"] == "One Size"
    assert A.waist_text_pairs(["모델 평소사이즈 25-27인치 free"], A.grids()["profiles"]["womens_bottoms"]) == {}
    r = _pants(["FREE（44-66반）", "XL（통통66반이상）", "2XL（77이상）"], ["25-27인치 free", "28-30인치 XL"],
               "womens_bottoms")
    assert "text_waist" not in {v["basis"] for v in r["values"]}


def test_a_size_line_of_the_options_letters_over_a_chart_lettered_otherwise():
    """로로얼로이 9317474764 (D): "사이즈 / S(55), M(66), L(77)" over the chart's "M(55) / L(66) / XL(77)"."""
    chart = ["사이즈 (cm) / 어깨단면 / 가슴단면 / 팔길이 / 총기장", "M(55) / 32 / 40 / 58 / 56.5", "L(66) / 33 / 42 / 59 / 58",
             "XL(77) / 35 / 44 / 60 / 60"]
    r = _resolve(["S", "M", "L"], chart + ["사이즈 / S(55), M(66), L(77)"])
    assert not r["held"] and [(v["us"], v["basis"]) for v in r["values"]] == [
        ("S (US 4-6)", "text_line"), ("M (US 8-10)", "text_line"), ("L (US 12-14)", "text_line")]
    assert [row["cm"]["chest"] for row in r["chart"]["rows"]] == [40.0, 42.0, 44.0]       # the 55 row under S
    # negatives: a chart lettered as the option keeps winning; a line of some letters; other women's sizes
    assert A.size_line(["S(55), M(66), L(77)"], ["S", "M", "L"],
                       A.read_chart(["사이즈 / 가슴", "S(44) / 40", "M(55) / 42", "L(66) / 44"])) == {}
    ch = A.read_chart(chart)
    assert A.size_line(["L[55~66]/XL[77]"], ["M", "L", "XL"], ch) == {}
    assert A.size_line(["S(44), M(55), L(66)"], ["S", "M", "L"], ch) == {}
    assert A.size_line(["S(77), M(66), L(55)"], ["S", "M", "L"], ch) == {}


def test_a_letter_written_with_two_ranges_takes_the_one_that_fits_the_ladder():
    """투엘라 12370291326 (D): L(28~29) twice in the text, L(27~29) in the chart's row label: 27~29 overlaps M's
    26반~27, 28~29 completes the ladder."""
    lines = ["사이즈:S(25~26)/M(26반~27)/L(28~29)", "/XL(30~31)/2XL(32~33)", "사이즈 / S(25~26)/M(26반~27)/L(28~29)",
             "사이즈 / 총길이 / 허리 / 엉덩이", "S(25~26) / 91.5 / 36 / 44", "L(27~29) / 94.5 / 41 / 49",
             "XL(30~31) / 96 / 43.5 / 51.5", "2XL(32~33) / 97.5 / 46 / 54"]
    r = _pants(["S", "M", "L", "XL", "2XL"], lines, "womens_pants")
    assert not r["held"] and [v["us"] for v in r["values"]] == [
        "XS-S (US 0-6)", "S (US 4-6)", "M (US 8-10)", "L (US 12-14)", "L-XL (US 12-16)"]
    w = A.waist_text_pairs(lines, A.grids()["profiles"]["womens_pants"])
    assert w["L"] == [71.1, 73.7] and w["M"] == [67.3, 68.6]
    # negatives: two ranges that both fit (or both break) stay unpaired; written less often: unpaired
    prof = A.grids()["profiles"]["womens_pants"]
    assert "L" not in A.waist_text_pairs(["M(26~27)", "L(28~29)", "L(28~29반)", "XL(30~31)"], prof)
    assert "L" not in A.waist_text_pairs(["M(26~27)", "L(28~29)", "L(27~29)", "L(27~29)", "XL(30~31)"], prof)


def test_about_a_chest_and_a_4xl_where_the_profile_has_it():
    """Klattermusen 5460564989 'XXS사이즈(약80)', a rain suit's '4XL' 11859489664 (mens_tops 120) (D)."""
    from size_labels import parse_label as P
    assert P("XXS사이즈(약80)").letter == "XXS" and P("XXS사이즈(약80)").chest == (80.0,)
    assert P("화이트(약기모)") is None and P("4XL") is None
    r = _resolve(["XXS사이즈(약80)", "XS사이즈(약85)", "L사이즈(약100)"])
    assert [v["us"] for v in r["values"]] == ["XXS (US 00)", "XS (US 0-2)", "L (US 12-14)"]
    r = A.resolve([{"name_ko": "사이즈", "values_ko": ["M", "L", "XL", "2XL", "3XL", "4XL"]}], [], None, "우비", "mens_tops")
    assert not r["held"] and [v["us"] for v in r["values"]] == ["S", "M", "L", "XL", "XXL", "XXXL"]
    # negatives: no 4XL in the profile, a joined "아이보리 4XL": unread as before
    assert "'4XL'" in _resolve(["L", "4XL"])["held"]
    assert "'4XL'" in _pants(["L", "4XL"], [], "mens_bottoms")["held"]


_ADIDAS_A_TABLE = ["주문사이즈 / A76 / A79 / A82 / A85 / A88 / A92 / A96", "(31) / (32) / (33) / (34) / (35) / (36) / (38)"]


def test_adidas_bare_codes_by_the_products_size_table():
    """majorgolf 11493370731 (E): 'IQ2921 블랙 A79' bare beside 'IQ2921 블랙 A82 (33인치)', the table A79 = (32)."""
    values = ["IQ2921 블랙 A76 (31인치)", "IQ2921 블랙 A79", "IQ2921 블랙 A82 (33인치)", "IU2824 네이비 A85"]
    with A.waist_labels(A.MENS_WAIST):
        got = A.split_joined([{"name_ko": "선택", "values_ko": values}])
    assert got == (0, [("IQ2921 블랙", "A76 (31인치)"), ("IQ2921 블랙", "A79"), ("IQ2921 블랙", "A82 (33인치)"),
                       ("IU2824 네이비", "A85")])
    sizes = ["A76 (31인치)", "A79", "A82 (33인치)", "A85"]
    r = _pants(sizes, _ADIDAS_A_TABLE * 2, "mens_bottoms")
    assert not r["held"] and [(v["ko"], v["us"], v["basis"]) for v in r["values"]] == [
        ("A76 (31인치)", "W31", "waist"), ("A79", "W32", "chart_inch"), ("A82 (33인치)", "W33", "waist"),
        ("A85", "W34", "chart_inch")]
    # negatives: no table, two reads disagreeing, a written inch the table contradicts: held "not read"
    assert "'A79': not read" in _pants(sizes, [], "mens_bottoms")["held"]
    other = ["주문사이즈 / A76 / A79 / A82 / A85", "(31) / (33) / (33) / (34)"]
    assert "'A79': not read" in _pants(sizes, _ADIDAS_A_TABLE + other, "mens_bottoms")["held"]
    assert "'A79': not read" in _pants(["A76 (31인치)", "A79", "A82 (32인치)"], _ADIDAS_A_TABLE, "mens_bottoms")["held"]
    with A.waist_labels(A.MENS_WAIST):                                   # a set of bare codes alone: no split
        assert A.split_joined([{"name_ko": "선택", "values_ko": ["IQ2921 블랙 A79", "IQ2921 블랙 A85"]}]) is None


def test_adidas_asian_fact_by_its_own_size_table():
    """majorgolf 9998916822 (E): one variant 'IS7132 블랙 AL (110)', the table "s / M / L" (a letter lost) over four
    numbers and elsewhere "S / M / L / XL": L = (110). Since 2026-11-25 the owner's adidas row sizes the letter (AL =
    105, L), the bracket number no longer: the table only lets the fact be read."""
    lines = ["주문사이즈 / s / M / L", "(100) / (105) / (110) / (115)", "주문사이즈 / S / M / L / XL"]
    pairs = A.order_pairs(lines)
    assert pairs == {"S": {100}, "M": {105}, "L": {110}, "XL": {115}}
    assert A.single_joined("IS7132 블랙 AL (110)", pairs) == ("IS7132 블랙", "AL (110)")
    ov = {"options": [], "facts": [{"label_ko": "", "value_ko": "IS7132 블랙 AL (110)"}],
          "variants": [{"options_ko": [], "price_krw": 1}]}
    out = T._sizes(ov, "mens_tops", "\n".join(lines), [], None, "아디다스 쿼터집")
    assert not out["held"] and out["fact"]["us"] == "L"
    other = {"options": [], "facts": [{"label_ko": "", "value_ko": "IS7132 블랙 AL (110)"}],
             "variants": [{"options_ko": [], "price_krw": 1}]}
    assert T._sizes(other, "mens_tops", "\n".join(lines), [], None, "푸마 쿼터집")["fact"]["us"] == "XL"   # no row
    # negatives: no table, the table pairing L with another number (5176506757's 'AL (105)'), a lone 3-letter row
    assert A.single_joined("IS7132 블랙 AL (110)") is None
    assert A.single_joined("IS7132 블랙 AL (105)", pairs) is None
    assert A.order_pairs(lines[:2]) == {}
    assert A.single_joined("CW4742 화이트 L", pairs) is None


def test_two_models_spellings_of_one_waist_when_no_choice_sells_both():
    """soneva 10076109143 (E): the fleece model's 82..92 and the plain model's M(32)..XXL(36), "네이비82" glued."""
    with A.waist_labels(A.MENS_WAIST):
        assert A._words("네이비82") == ["네이비", "82"] and A._words("카본120") == ["카본120"]
        assert A._words("바지(봄/가을)25")[-1] == "가을)25"
    assert A._words("네이비82") == ["네이비82"]                              # outside the waist profiles
    values = ["82", "M(32)", "85", "L(33)"]
    combos = [["기모", "네이비", "82"], ["기모", "네이비", "85"], ["일반", "블랙", "M(32)"], ["일반", "블랙", "L(33)"]]
    opts = [{"name_ko": "모델명", "values_ko": ["기모", "일반"]}, {"name_ko": "컬러", "values_ko": ["네이비", "블랙"]},
            {"name_ko": "사이즈", "values_ko": values}]
    r = A.resolve(opts, [], None, "아디다스 바지", "mens_bottoms", combos=combos)
    assert not r["held"] and not r["merged"] and [v["us"] for v in r["values"]] == ["W32", "W32", "W33", "W33"]
    # negatives: both under one choice of the others hold; no combos (as before) hold; women's profiles hold
    assert r is not None and A.resolve(opts, [], None, "", "mens_bottoms", combos=combos + [["기모", "네이비", "M(32)"]])["held"]
    assert A.resolve(opts, [], None, "", "mens_bottoms")["held"]
    sizes = {"profile": "mens_bottoms", "values": r["values"], "chart": None}
    assert A.chart_html(sizes).count("<td>W32</td>") == 1
    import shopify_payload as SP2
    product = {"options": opts, "variants": [], "sizes": {**r, "option": 2}}
    out, _ = SP2._options(product, _en([]))
    assert [v["name"] for v in out[2]["values"]] == ["W32", "W33"]


def test_a_womens_models_rows_are_left_out_of_a_mens_product():
    """Master Bear 5489884876 (F): the women's model M2-0B053 (S / M / L) left out before the cap, the men's sold."""
    import inspect
    src = inspect.getsource(T.options_and_variants)
    assert "leave_out_model" in src and "len(model_rows) * 2 < len(rows)" in src
    src = inspect.getsource(T.prepare)
    assert "womens_model_left_out" in src and 'own == "mens"' in src and "a bare letter left" in src


# ---- 2026-11-25, the two reviews of the size_unmapped second pass and the owner's three yes answers ----------------

RAINCOAT_8325761055 = [
    "상품사이즈(cm)", "사이즈는 측정 방법에 따라1~3cm 차이가 있을수 있습니다.", "어깨너비", "-가슴단면", "소매길이", "총장", "남성용",
    "95 / 100 / 105 / 110", "추천사이즈 / 남성M / 남성L / 남성XL / 남성XXL", "총장 / 110 / 111.5 / 113 / 114.5",
    "가슴둘레 / 125 / 130 / 135 / 140", "허리둘레 / 123 / 128 / 133 / 138", "소매길이 / 84 / 86 / 88 / 90",
    "* 모델 착용사이즈: 남성모델105(남성XL)", "여성용", "85 / 90 / 95", "추천사이즈 / 여성s / 여성M / 여성L",
    "총장 / 93 / 94.5 / 96", "가슴둘레 / 103 / 108 / 113", "허리둘레 / 97 / 102 / 107", "소매길이 / 79 / 81 / 83",
    "* 모델 착용 사이즈 :여성모델 95(여성L)"]


def _tops():
    from transform_shops import rules_for
    return rules_for("fairwardgolf").categories["50002796"]


def test_the_genders_chart_marks_merge_to_mixed_on_any_disagreement():
    """The correctness review: women's chest with no mark (a round 92 cm) beside men's "flat" (53) made both flat, so the
    women's S read 72.5 in; any disagreement, None included, is "mixed" (read by the number)."""
    assert T._gender_kinds([{"chest": None}, {"chest": "flat"}]) == {"chest": "mixed"}
    assert T._gender_kinds([{"chest": "flat"}, {"chest": None}]) == {"chest": "mixed"}
    assert T._gender_kinds([{"chest": "circ"}, {"chest": None}]) == {"chest": "mixed"}
    assert T._gender_kinds([{"chest": "flat"}, {"chest": "circ"}]) == {"chest": "mixed"}
    # negatives: the same mark stays; a field only one chart has keeps that chart's mark
    assert T._gender_kinds([{"chest": "flat", "length": None}, {"chest": "flat", "length": None}]) == {
        "chest": "flat", "length": None}
    assert T._gender_kinds([{"shoulder": "flat"}, {"chest": "circ"}]) == {"shoulder": "flat", "chest": "circ"}
    sizes = {"profile": "womens_tops", "values": [
        {"ko": "92", "us": "Women's S (US 4-6)", "letter": "S", "chest_cm": 90, "profile": "womens_tops"},
        {"ko": "100", "us": "Men's M", "letter": "M", "chest_cm": 100, "profile": "mens_tops"}],
        "chart": {"kinds": T._gender_kinds([{"chest": None}, {"chest": "flat"}]),
                  "rows": [{"us": "Women's S (US 4-6)", "cm": {"chest": 92}}, {"us": "Men's M", "cm": {"chest": 53}}]}}
    html = A.chart_html(sizes)
    assert "<td>36 in</td>" in html and "72.5 in" not in html and "<td>41.5 in</td>" in html


def test_each_gender_takes_chart_rows_only_from_its_own_table():
    """8325761055 (the correctness review): the OCR holds "남성용 / 95 / 100 / 105 / 110 ... 가슴둘레 / 125 ..." and then
    "여성용 / 85 / 90 / 95 ... 가슴둘레 / 103 / 108 / 113": the women's 95 took the men's 95 row (chest 125 cm)."""
    tables = T._gender_tables("", [RAINCOAT_8325761055])
    assert tables["mens"][0] == "95 / 100 / 105 / 110" and tables["womens"][0] == "85 / 90 / 95"
    assert "가슴둘레 / 125 / 130 / 135 / 140" not in tables["womens"]
    ov, by_sku = _gendered(["여성(85)", "여성(90)", "여성(95)", "남성(95)", "남성(100)", "남성(105)", "남성(110)"],
                           ["womens"] * 3 + ["mens"] * 4)
    out = T._sizes_by_gender(ov, _tops(), by_sku, "", [RAINCOAT_8325761055], None, "레인코트")
    assert out and not out["held"]
    rows = {r["us"]: r["cm"] for r in out["chart"]["rows"]}
    assert rows["Women's M (US 8-10)"]["chest"] == 113 and rows["Men's S"]["chest"] == 125
    assert all(r["cm"]["chest"] != 125 for r in out["chart"]["rows"] if r["us"].startswith("Women's"))
    # negatives: no gender headings (the tables cannot be told apart): no chart, a reason; one gender's heading alone
    # is a heading line, never a value ("남성모델105" is no heading)
    plain = [line for line in RAINCOAT_8325761055 if line not in ("남성용", "여성용")]
    ov, by_sku = _gendered(["여성(85)", "여성(90)", "여성(95)", "남성(95)", "남성(100)", "남성(105)", "남성(110)"],
                           ["womens"] * 3 + ["mens"] * 4)
    out = T._sizes_by_gender(ov, _tops(), by_sku, "", [plain], None, "레인코트")
    assert not out["held"] and out["chart"] is None and "not told apart" in out["chart_left_out"]
    assert T._GENDER_HEAD_RE.match("여성용 상세 사이즈") and T._GENDER_HEAD_RE.match("남성")
    assert not T._GENDER_HEAD_RE.match("* 모델 착용사이즈: 남성모델105(남성XL)") and not T._GENDER_HEAD_RE.match("남성 95")


def test_two_models_on_one_waist_show_no_chart():
    """10076109143 (the correctness review): the plain model's XL(35) took the fleece 88's row by position; when the
    combos exemption lets two models share a US waist, no chart (one cm written two ways keeps its row: 5815131892)."""
    values = ["82", "M(32)", "85", "L(33)", "88", "XL(35)"]
    combos = [["기모", "82"], ["기모", "85"], ["기모", "88"], ["일반", "M(32)"], ["일반", "L(33)"], ["일반", "XL(35)"]]
    opts = [{"name_ko": "모델명", "values_ko": ["기모", "일반"]}, {"name_ko": "사이즈", "values_ko": values}]
    lines = ["82 - 허리둘레 81cm", "85 - 허리둘레 84cm", "88 - 허리둘레 87cm"]
    r = A.resolve(opts, lines, None, "아디다스 바지", "mens_bottoms", combos=combos)
    assert not r["held"] and r["chart"] is None and r["chart_left_out"].startswith("two models' sizes on one US size")
    # negative: the fleece model alone keeps its chart
    alone = A.resolve([{"name_ko": "사이즈", "values_ko": ["82", "85", "88"]}], lines, None, "아디다스 바지",
                      "mens_bottoms")
    assert "chart_left_out" not in alone


def test_a_button_down_shirt_is_no_outerwear():
    """50002796: 다운 (down) after 버튼 is a button-down shirt: neither left out of a product (the variant drop) nor
    screened from the listing; a down jacket still is."""
    import listing_filter as LF
    rules = [{k: r[k] for k in r if k != "requires"} for r in LF.title_rules("50002796") if r["code"] == "outerwear"]
    assert LF.title_rule("버튼다운 셔츠 화이트", rules) is None
    assert LF.title_rule("다운 자켓 블랙", rules) == "title:outerwear" and LF.title_rule("경량 다운 블랙", rules) == "title:outerwear"
    names = ["디자인", "사이즈"]
    rows = [{"options": [d, s]} for d in ("버튼다운 셔츠 화이트", "라운드 티셔츠", "경량 다운 점퍼") for s in ("M", "L")]
    kept, left, _ = T._drop_off_section(names, rows, ("outerwear",), "50002796")
    assert [r["options"][0] for r in kept] == ["버튼다운 셔츠 화이트"] * 2 + ["라운드 티셔츠"] * 2
    assert left == "2 variants: 경량 다운 점퍼"
    # the listing screen of 50002796 (the title rules, every code): a button-down title passes, a down jacket not
    screen = LF.title_rules("50002796")
    assert LF.title_rule("남성 골프 버튼다운 긴팔 셔츠", [{k: r[k] for k in r if k != "requires"} for r in screen
                                                    if r["code"] == "outerwear"]) is None


def test_a_ladder_read_two_ways_holds():
    """티앤드 5587004670 (the correctness review): S..XL by the profile's letters (the OCR misread "XL(31~33)"), 2XL by
    another style's chart row "2XL(33~35)": "XL-XXL (US 16-18)" beside "XL (US 16)", its hip smaller than XL's."""
    rows = ["사이즈 / 총기장 / 허리 단면 / 힙단면", "S(25~26) / 89 / 32 / 42", "M(27~28) / 90 / 34 / 44",
            "L(29~30) / 91 / 36 / 46", "XL(3]~33) / 92 / 38 / 48", "2XL(33~35) / 93 / 47 / 50"]
    r = _pants(["S", "M", "L", "XL", "2XL"], rows, "womens_pants")
    assert r["held"] == "'2XL' XL-XXL (US 16-18) (chart_pair) overlaps 'XL' XL (US 16) (fallback_letters): one ladder read two ways"
    # negatives: one basis for the whole ladder, a gap of a letter, a letter range: as before
    assert not _pants(["S", "M", "L", "XL", "2XL"], [], "womens_pants")["held"]
    fixed = rows[:4] + ["XL(31~33) / 92 / 38 / 48", "2XL(33~35) / 93 / 47 / 50"]
    assert not _pants(["S", "M", "L", "XL", "2XL"], fixed, "womens_pants")["held"]
    assert A._ladder_broken([{"ko": "M", "us": "M (US 8-10)", "basis": "fallback_letters"},
                             {"ko": "XL", "us": "L-XL (US 12-16)", "basis": "chart_pair"}], {}) is None


def test_the_owners_adidas_asian_letters_on_mens_tops():
    """The owner, 2026-11-25: AS = 95, AM = 100, AL = 105, AXL = 110, A2XL = 115 for adidas' men's tops, the letter
    winning over the number in brackets (majorgolf: 5176506757 sells "AM (100)" for one model and "AM (105)" for
    another; 13740514016 sells the bare "KG2154 화이트 AS" .. "A2XL")."""
    row = A.grids()["profiles"]["mens_tops"]["brands"]["adidas"]
    assert row["asian_letters"] == {"AS": 95, "AM": 100, "AL": 105, "AXL": 110, "A2XL": 115}
    assert "owner 2026-11-25" in row["basis"] and "13740514016" in row["evidence"]
    values = ["AXL (110)", "AL (105)", "AM (100)", "AM (105)", "AL (110)", "AXL (115)"]
    combos = [["IM7295", "AXL (110)"], ["IX4323", "AM (100)"], ["IX4323", "AL (105)"], ["IT7211", "AM (105)"],
              ["IT7211", "AL (110)"], ["IT7211", "AXL (115)"]]
    opts = [{"name_ko": "선택1", "values_ko": ["IM7295", "IX4323", "IT7211"]}, {"name_ko": "선택2", "values_ko": values}]
    r = A.resolve(opts, [], "아디다스", "아디다스 남성 긴팔", "mens_tops", combos=combos)
    assert not r["held"] and not r["merged"] and r["chart"] is None
    assert {v["ko"]: v["us"] for v in r["values"]} == {"AM (100)": "M", "AM (105)": "M", "AL (105)": "L",
                                                       "AL (110)": "L", "AXL (110)": "XL", "AXL (115)": "XL"}
    assert {v["basis"] for v in r["values"]} == {"brand_asian:adidas"}
    # the bare letters after a colour: split by the brand row only
    joined = [{"name_ko": "선택", "values_ko": ["KG2154 화이트 AS", "KG2154 화이트 AM", "KG2154 화이트 A2XL"]}]
    assert A.split_joined(joined, asian=True) == (0, [("KG2154 화이트", "AS"), ("KG2154 화이트", "AM"),
                                                      ("KG2154 화이트", "A2XL")])
    assert A.split_joined(joined) is None
    bare = A.resolve([{"name_ko": "사이즈", "values_ko": ["AS", "AM", "AL", "AXL", "A2XL"]}], [], "아디다스", "",
                     "mens_tops")
    assert [v["us"] for v in bare["values"]] == ["S", "M", "L", "XL", "XXL"]
    assert A.resolve([{"name_ko": "사이즈", "values_ko": ["AL (110)"]}], [], "아디다스", "", "mens_tops")["values"][0]["us"] == "L"
    # negatives: another brand, the women's tops ("AS(85)" by its number), a bare S of adidas, two models' AM under
    # one choice of the others: as before (held or by the number)
    assert A.resolve(opts, [], "나이키", "나이키 긴팔", "mens_tops", combos=combos)["held"]
    women = A.resolve([{"name_ko": "사이즈", "values_ko": ["AS(85)", "AM(90)"]}], [], "아디다스", "", "womens_tops")
    assert [v["us"] for v in women["values"]] == ["XS (US 0-2)", "S (US 4-6)"]
    plain = A.resolve([{"name_ko": "사이즈", "values_ko": ["S", "M"]}], [], "아디다스", "", "mens_tops")
    assert [v["us"] for v in plain["values"]] == ["XS", "S"] and {v["basis"] for v in plain["values"]} == {"fallback_letters"}
    assert A.resolve(opts, [], "아디다스", "", "mens_tops", combos=combos + [["IM7295", "AM (100)"], ["IM7295", "AM (105)"]])["held"]


def test_7455950253s_waist_with_a_big_letter_is_the_waist():
    """매일츄리닝 7455950253: "36(4XL)" .. "40(6XL)" in the men's trousers are the waist (as "30(XL)" already reads),
    each its own Naver value beside another style's bare "36" (both W36, no style sells both)."""
    with A.waist_labels(A.MENS_WAIST):
        assert A.parse_label("36(4XL)") == A.parse_label("36") and A.parse_label("40(6XL)") == A.parse_label("40")
        assert A.parse_label("4XL") is None                              # a bare 4XL stays unread
    assert A.parse_label("36(4XL)") is None or not A.parse_label("36(4XL)").waist   # never outside the waist profiles
    values = ["30", "36", "30(XL)", "36(4XL)", "40(6XL)"]
    combos = [["약기모카고", "30"], ["약기모카고", "36"], ["융기모패딩조거", "30(XL)"], ["융기모패딩조거", "36(4XL)"],
              ["융기모패딩조거", "40(6XL)"]]
    opts = [{"name_ko": "스타일", "values_ko": ["약기모카고", "융기모패딩조거"]}, {"name_ko": "사이즈", "values_ko": values}]
    r = A.resolve(opts, [], None, "카고 조거", "mens_bottoms", combos=combos)
    assert not r["held"] and not r["merged"]
    assert {v["ko"]: v["us"] for v in r["values"]} == {"30": "W30", "30(XL)": "W30", "36": "W36", "36(4XL)": "W36",
                                                       "40(6XL)": "W40"}


def test_the_owners_variants_are_left_out_before_the_sizes():
    """The owner's variants_by_owner.json (2026-11-25): 7455950253 drops 사선포켓 and the 밀리터리 styles, matched as
    written or without the numbering, never a part of another value (사선포켓Ver2 stays)."""
    names = ["스타일", "사이즈"]
    rows = [{"options": [st, sz]} for st in ("1. 사선포켓", "2. 사선포켓Ver2", "3-1. 밀리터리(냉감)") for sz in ("M", "30")]
    kept, said = T._owner_dropped(names, rows, {"스타일": ["사선포켓", "밀리터리(냉감)"]})
    assert [r["options"][0] for r in kept] == ["2. 사선포켓Ver2"] * 2
    assert said == {"left_out": "4 variants: 스타일: 1. 사선포켓, 3-1. 밀리터리(냉감)"}
    kept, said = T._owner_dropped(names, rows, {"0": ["1. 사선포켓"], "없는옵션": ["x"]})
    assert len(kept) == 4 and said["unused"] == "없는옵션: x"
    kept, said = T._owner_dropped(names, rows, {"스타일": ["사선포켓", "없는값"]})
    assert len(kept) == 4 and said["unused"] == "스타일: 없는값"
    # every row named: none left out (prepare holds the product variants_by_owner)
    kept, said = T._owner_dropped(names, rows, {"사이즈": ["M", "30"]})
    assert kept == rows and said and said["all"]


def test_the_owners_reading_of_a_products_values():
    """variants_by_owner.json "sizes" (2026-11-25): read_as sizes a value as the owner's label and keeps the seller's
    value (the Naver value ordered); same_as merges a value into another of the size option, never where one choice
    of the other options sells both; a key the product does not show, a label written twice or already a value:
    unused."""
    ov = {"options": [{"name_ko": "사이즈", "values_ko": ["2", "3", "4"]}], "facts": [],
          "variants": [{"sku": f"s{v}", "options_ko": [v], "price_krw": 1000, "available": True} for v in "234"]}
    said, unused = [], []
    out = T._sizes(ov, "womens_tops", "", [], None, "WAAC 여성 바람막이",
                   {"read_as": {"2": "S(90)", "3": "M(95)", "4": "L(100)"}}, said, unused)
    assert not out["held"] and [(v["ko"], v["us"], v["read_as"]) for v in out["values"]] == [
        ("2", "S (US 4-6)", "S(90)"), ("3", "M (US 8-10)", "M(95)"), ("4", "L (US 12-14)", "L(100)")]
    assert [v["options_ko"] for v in ov["variants"]] == [["2"], ["3"], ["4"]] and not unused
    assert said == ["read_as 2 = S(90)", "read_as 3 = M(95)", "read_as 4 = L(100)"]
    plain = {**ov, "variants": [dict(v) for v in ov["variants"]]}
    assert "'2'" in T._sizes(plain, "womens_tops", "", [], None, "WAAC")["held"]     # no word: held as before
    said, unused = [], []
    T._owner_reading(ov, [], {"read_as": {"2": "M", "3": "M", "4": "2"}}, "womens_tops", said, unused)
    assert not said and unused == ["read_as 2: M twice", "read_as 3: M twice", "read_as 4: 2 is a value already"]

    def pants(rows):
        return {"options": [{"name_ko": "원단", "values_ko": ["A", "B"]},
                            {"name_ko": "사이즈", "values_ko": ["S", "M", "S(25~26인치)", "M(27~28인치)"]}],
                "facts": [], "variants": [{"sku": f"{a}{s}", "options_ko": [a, s], "price_krw": 1000, "available": True}
                                          for a, s in rows]}
    ov = pants([("A", "S"), ("A", "M"), ("B", "S(25~26인치)"), ("B", "M(27~28인치)")])
    said, unused = [], []
    out = T._sizes(ov, "womens_pants", "", [], None, "여성 골프바지",
                   {"same_as": {"S": "S(25~26인치)", "M": "M(27~28인치)"}}, said, unused)
    assert not out["held"] and out["merged"] == {"S": "S(25~26인치)", "M": "M(27~28인치)"}
    assert ov["options"][1]["values_ko"] == ["S(25~26인치)", "M(27~28인치)"]
    assert [(v["options_ko"], v.get("naver_options_ko")) for v in ov["variants"]] == [
        (["A", "S(25~26인치)"], ["A", "S"]), (["A", "M(27~28인치)"], ["A", "M"]),
        (["B", "S(25~26인치)"], None), (["B", "M(27~28인치)"], None)]
    both = pants([("A", "S"), ("A", "S(25~26인치)"), ("B", "M"), ("B", "M(27~28인치)")])   # one choice sells both
    said, unused = [], []
    T._owner_reading(both, [], {"same_as": {"S": "S(25~26인치)", "M": "XL"}}, "womens_pants", said, unused)
    assert not said and unused == ["same_as S: sold beside S(25~26인치) under one choice of the other options",
                                   "same_as M: XL (not two size values of the product)"]


def test_the_owners_size_sold():
    """owner_size_facts (2026-11-25): the owner's one size of a one-variant product, the title's colour beside it when
    the title is the listing's name plus "colour, <that size>"; a letter (Nike 13660201494's S) as much as a number;
    never beside a size option or a size fact."""
    one = {"options": [], "facts": [], "variants": [{"sku": "x"}]}
    base = "베러투데이 여성 파크골프 가을 우븐 블루종 긴팔 카라 티셔츠"
    assert T.owner_size_facts(one, "110", f"{base} 핑크, 110", base) == [
        {"label_ko": "색상", "value_ko": "핑크"}, {"label_ko": "사이즈", "value_ko": "110"}]
    assert T.owner_size_facts(one, "S", "나이키 폴로 코랄핑크, S", "나이키 폴로") == [
        {"label_ko": "색상", "value_ko": "코랄핑크"}, {"label_ko": "사이즈", "value_ko": "S"}]
    assert T.owner_size_facts(one, "95", f"{base} 핑크, 110", base) == [{"label_ko": "사이즈", "value_ko": "95"}]
    assert T.owner_size_facts(one, "110", f"{base} 핑크, 110", None) == [{"label_ko": "사이즈", "value_ko": "110"}]
    assert T.owner_size_facts({**one, "options": [{"name_ko": "사이즈", "values_ko": ["95"]}]}, "95", base, base) is None
    assert T.owner_size_facts({**one, "facts": [{"label_ko": "사이즈", "value_ko": "95"}]}, "95", base, base) is None
    assert T.owner_size_facts({**one, "variants": [{"sku": "x"}, {"sku": "y"}]}, "95", base, base) is None
