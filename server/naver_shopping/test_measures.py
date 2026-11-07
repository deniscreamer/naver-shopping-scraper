"""Offline tests for the weight and size candidates (naver_shopping/measures.py).

    python -m pytest server/naver_shopping/test_measures.py -q

The two notices are real (golf sets in scripts/output/full-50002788, read 2026-11-02: 7583123963 and 12736318849);
the other lines are written for the rules, in the sellers' wording.
"""
import json
import os

import pytest

from naver_shopping import measures as M, parsers as P

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def weights(label, value, **kw):
    return M.measures(rows=[{"label": label, "value": value}], **kw)


def one(out, bucket="weights"):
    [c] = out[bucket]
    return c


@pytest.mark.parametrize("label, value, grams", [
    ("무게", "9kg", (9000, 9000)),
    ("중량", "1,200g", (1200, 1200)),
    ("무게", "9.5 킬로그램", (9500, 9500)),
    ("무게(kg)", "9", (9000, 9000)),                       # the unit from the label
    ("제품 무게", "9~10kg", (9000, 10000)),
    ("Weight", "2 lbs", (907.185, 907.185)),
    ("중량", "16 oz", (453.592, 453.592)),
    ("무게", "500 mg", (0.5, 0.5)),
    ("무게", "9 (kg)", (9000, 9000)),
])
def test_weight_values(label, value, grams):
    c = one(weights(label, value))
    assert (c["value"]["min"], c["value"]["max"]) == grams and c["origin"] == "source_stated"
    assert c["quote"] == f"{label}: {value}" and c["source"] == "specs" and c["locator"] == {"block": "상품정보", "row": 0}


@pytest.mark.parametrize("label, value, kind, scope", [
    ("순중량", "9kg", "net", "unknown"),
    ("포장 포함 무게", "12kg", "packed", "unknown"),
    ("무게", "패키지 무게 12kg", "packed", "unknown"),
    ("Shipping weight", "12 kg", "packed", "unknown"),
    ("", "Package Weight 7.71 Kilograms", "packed", "unknown"),             # PGM 6630856593 description table
    ("샤프트 무게", "55g", "component", "unknown"),
    ("무게", "개당 300g", "unknown", "unit"),
    ("무게", "세트 전체 9kg", "unknown", "set"),
    ("무게", "약 9kg", "unknown", "unknown"),
])
def test_weight_kind_and_scope(label, value, kind, scope):
    c = one(weights(label, value))
    assert (c["kind"], c["scope"]) == (kind, scope)


def test_approximate():
    assert one(weights("무게", "약 9kg"))["approximate"] and one(weights("무게", "9~10kg"))["approximate"]
    assert not one(weights("무게", "9kg"))["approximate"]


@pytest.mark.parametrize("label, value", [
    ("스윙웨이트", "D2"), ("무게", "스윙웨이트 D2 300g"), ("모델명", "W-9kg"), ("무게", "-5kg"),
    ("중량", "200g/m²"), ("색상", "블랙 9kg"),                  # no weight label
])
def test_weight_skipped(label, value):
    out = weights(label, value)
    assert out["weights"] == [] and out["review"] == []


def test_weight_review():
    assert one(weights("무게(kg)", "9000g"), "review")["reason"] == "unit_conflict"
    assert one(weights("순중량", "포장 포함 12kg"), "review")["reason"] == "kind_conflict"


def test_set_parts_are_components():
    out = weights("무게", "드라이버 300g, 아이언 400g, 세트 총 9kg", name="남성 골프채 풀세트")
    assert out["is_set"] and [(c["kind"], c["scope"]) for c in out["weights"]] == [
        ("component", "unknown"), ("component", "unknown"), ("unknown", "set")]


@pytest.mark.parametrize("value, mm, axes, flags", [
    ("120 x 30 x 25 cm", [1200, 300, 250], None, ["axis_order_unresolved", "not_confirmed_packed"]),
    ("가로 120 x 세로 30 x 높이 25cm", [1200, 300, 250], ["width", "depth", "height"], ["not_confirmed_packed"]),
    ("120(가로) x 30(세로) x 25(높이) cm", [1200, 300, 250], ["width", "depth", "height"], ["not_confirmed_packed"]),
    ("120×30×25mm (L x W x H)", [120, 30, 25], ["length", "width", "height"], ["not_confirmed_packed"]),
    ("47*13*13인치", [1193.8, 330.2, 330.2], None, ["axis_order_unresolved", "not_confirmed_packed"]),
])
def test_size_triples(value, mm, axes, flags):
    c = one(weights("크기", value), "dimensions")
    assert (c["values"], c["axes"], c["flags"], c["kind"]) == (mm, axes, flags, "unknown")


def test_size_kinds_single_and_state():
    c = one(weights("포장 박스 크기", "125 x 35 x 30cm"), "dimensions")
    assert c["kind"] == "packed" and c["flags"] == ["axis_order_unresolved"]
    c = one(weights("길이", "120cm"), "dimensions")
    assert (c["values"], c["axes"]) == ([1200], ["length"])
    c = one(M.measures(description={"text": "샤프트 길이 45.5인치", "html": None}), "dimensions")
    assert (c["kind"], c["axes"], c["source"]) == ("component", ["length"], "description")
    assert one(weights("크기", "펼친 크기 120 x 30 x 25cm"), "dimensions")["state"] == "unfolded"
    assert one(weights("크기", "패키지 샤프트 120x30x25cm"), "dimensions")["kind"] == "unknown"


@pytest.mark.parametrize("label, value", [("크기", "100~120cm"), ("사이즈", "S 90cm, M 95cm, L 100cm")])
def test_size_ranges_and_lists_for_a_person(label, value):
    assert one(weights(label, value), "review")["reason"] == "manual_review"


@pytest.mark.parametrize("label, value", [("신발 사이즈", "260mm"), ("허리 사이즈", "32인치"), ("헤드체적", "460cc")])
def test_size_skipped(label, value):
    out = weights(label, value)
    assert out["dimensions"] == [] and out["review"] == []


def test_real_notices_are_references():
    notice = {"items": [{"label": "크기", "value": "상세페이지참조"}, {"label": "중량", "value": "상세페이지참조"}],
              "terms": [{"label": "중량", "value": "크기 항목 참조"}, {"label": "크기", "value": "[상세설명참조]"}]}
    out = M.measures(notice=notice)
    assert [(r["measure"], r["reason"]) for r in out["references"]] == [
        ("size", "description_reference"), ("weight", "description_reference"),
        ("weight", "measurement_field_reference"), ("size", "description_reference")]
    assert out["weights"] == out["dimensions"] == []


def test_description_tables_and_dedup():
    html = ("<ul><li><strong>무게</strong><div>9kg</div></li></ul><dl><dt>중량</dt><dd>9.2kg</dd></dl>"
            "<table><tr><th>구분</th><th>무게</th></tr><tr><td>세트</td><td>9.5kg</td></tr>"
            "<tr><th>크기</th><td>120 x 30 x 25cm</td></tr></table>")
    out = M.measures(rows=[{"label": "무게", "value": "9kg"}], description={"text": "무게\n9kg", "html": html})
    assert [(c["source"], c["value"]["min"]) for c in out["weights"]] == [
        ("specs", 9000), ("description_table", 9200), ("description_table", 9500)]   # li 9kg = the specs row
    assert [c["locator"]["cell"] for c in out["weights"][1:]] == ["dt", "tr"]
    assert one(out, "dimensions")["source"] == "description_table"


def test_json_ld_only_for_this_product():
    ld = {"@type": "Product", "productID": "42", "weight": {"value": 9, "unitCode": "KGM"},
          "additionalProperty": [{"name": "패키지 무게", "value": "12kg"}]}
    page = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    out = M.measures(page_html=page, product_id="42")
    assert [(c["source"], c["value"]["min"], c["kind"]) for c in out["weights"]] == [
        ("json_ld", 9000, "unknown"), ("json_ld", 12000, "packed")]
    assert M.measures(page_html=page, product_id="43")["weights"] == []


def page_options(name):
    with open(os.path.join(FX, f"page_product_{name}.json"), encoding="utf-8") as f:
        return P.parse_page_options(json.load(f))


def test_binding_to_variants():
    honma = page_options("honma")                   # 세트선택: S 세트 (D1 500 S+950 S) / R 세트 (D1 500 R)
    s_set = honma["variants"][0]
    c = one(weights("무게", "S 세트 (D1 500 S+950 S) 9kg", options=honma))
    assert c["binding"] == {"scope": "variants", "variant_ids": [s_set["id"]]}
    assert one(weights("무게", "9kg", options=honma))["binding"] == {"scope": "context", "variant_ids": []}
    both = weights("무게", "S 세트 (D1 500 S+950 S) / R 세트 (D1 500 R) 9kg", options=honma)
    assert both["weights"] == [] and one(both, "review")["reason"] == "two_compositions"
    single = one(weights("무게", "9kg", options={"variants": [{"id": "1", "options": ["블랙"]}]}))
    assert single["binding"] == {"scope": "product", "variant_ids": ["1"]}
    assert one(weights("무게", "9kg"))["binding"] == {"scope": "product", "variant_ids": []}


def test_binding_colour_only_differences_are_one_composition():
    options = {"option_groups": [{"name": "구성", "type": "COMBINATION"}, {"name": "색상", "type": "COMBINATION"}],
               "variants": [{"id": "1", "options": ["캐디백 포함", "블랙"]}, {"id": "2", "options": ["캐디백 포함", "화이트"]},
                            {"id": "3", "options": ["클럽만", "블랙"]}]}
    c = one(weights("무게", "캐디백 포함 12kg", options=options))
    assert c["binding"] == {"scope": "variants", "variant_ids": ["1", "2"]}
    assert one(weights("무게", "블랙 9kg", options=options))["binding"]["scope"] == "context"   # two compositions


SET = "남성 골프채 풀세트"


@pytest.mark.parametrize("label, value", [
    ("세트 무게", "9.5kg"), ("풀세트 무게", "9.5kg"), ("총 중량", "9.5kg"), ("무게", "세트 총 9.5kg"),
    ("무게", "드라이버, 우드, 아이언, 퍼터 포함 세트 총 9.5kg"),      # the parts listed, the set's total
])
def test_set_totals(label, value):
    c = one(weights(label, value, name=SET))
    assert (c["kind"], c["scope"], c["value"]["min"]) == ("unknown", "set", 9500)


@pytest.mark.parametrize("label, value", [("드라이버 무게", "310g"), ("무게", "아이언 1개 380g"), ("헤드 무게", "205g"),
                                          ("캐디백 무게", "3kg")])
def test_parts_in_a_set(label, value):
    assert one(weights(label, value, name=SET))["kind"] == "component"


def test_head_weight_outside_a_set_and_offset_is_not_a_set():
    assert one(weights("헤드 무게", "205g", name="핑 G430 드라이버"))["kind"] == "component"
    out = weights("무게", "310g", name="Ping G430 Offset Driver")
    assert not out["is_set"] and one(out)["kind"] == "unknown"
    assert weights("무게", "1kg", name="Golf set 10pcs")["is_set"]


def test_range_with_units_on_both_ends():
    assert one(weights("무게", "300g-350g"))["value"] == {"min": 300, "max": 350}
    assert one(weights("무게", "1kg~1,200g"))["value"] == {"min": 1000, "max": 1200}


@pytest.mark.parametrize("label, value", [("포장 크기", "120*30*25(cm)"), ("포장 크기", "120 x 30 x 25 (cm)"),
                                          ("포장 크기(cm)", "120x30x25")])
def test_triple_unit_after_or_in_the_label(label, value):
    c = one(weights(label, value), "dimensions")
    assert c["values"] == [1200, 300, 250] and c["kind"] == "packed"


def test_axis_pairs_and_the_nearest_axis():
    c = one(weights("포장 크기", "가로120 세로30 높이25cm"), "dimensions")
    assert (c["values"], c["axes"], c["kind"]) == ([1200, 300, 250], ["width", "depth", "height"], "packed")
    c = one(weights("크기", "가로 50cm"), "dimensions")
    assert c["axes"] == ["width"]
    c = one(M.measures(description={"text": "가방 높이는 길이 90cm 정도", "html": None}), "dimensions")
    assert c["axes"] == ["length"]                                   # the word next to the number


@pytest.mark.parametrize("text", ["폭발적인 비거리 10m 증가", "무게중심 깊이 40mm", "탄도 높이 3m"])
def test_golf_talk_is_not_a_size(text):
    out = M.measures(description={"text": text, "html": None})
    assert out["dimensions"] == [] and out["review"] == []


@pytest.mark.parametrize("value", ["제품상세참조", "상세페이지에 별도 표기", "상세정보 참조", "상세이미지 참조"])
def test_more_pointers(value):
    out = M.measures(notice={"items": [{"label": "크기, 중량", "value": value}]})
    assert [r["measure"] for r in out["references"]] == ["weight", "size"]


# ---- 2026-11-06: the weight / size rules from the 40 golf sets and 86 saved pages checked by hand ------------------

def notice(label, value, **kw):
    return M.measures(notice={"items": [{"label": label, "value": value}]}, **kw)


def text(lines, **kw):
    return M.measures(description={"text": "\n".join(lines), "html": None}, **kw)


def grams(out):
    return [c["value"]["min"] for c in out["weights"]]


@pytest.mark.parametrize("label, value, expected, unit", [
    ("무게", "14 파운드", 6350.293, "파운드"),                 # 10639350746 description table (lost before)
    ("중량", "5온스", 141.748, "온스"),
    ("중량", "1.5키로", 1500, "키로"),
    ("무게", "13.6 kgs", 13600, "kgs"),
    ("Item Weight", "14 Pounds", 6350.293, "Pounds"),
    ("무게", "2 kilos", 2000, "kilos"),
    ("무게", "3 lbs.", 1360.777, "lbs."),
])
def test_more_weight_units(label, value, expected, unit):
    c = one(weights(label, value))
    assert (c["value"]["min"], c["unit"]) == (expected, unit)


@pytest.mark.parametrize("label, value", [("중량", "12 fl oz"), ("중량", "12fl.oz"), ("용량", "20온스"),
                                          ("가격", "50파운드"), ("크기", "14 종(Strata Plus)"), ("무게", "파운드케이크")])
def test_not_a_weight_unit(label, value):
    out = weights(label, value)
    assert out["weights"] == [] and out["review"] == []


def test_geun_is_for_a_person():
    assert one(weights("무게", "3근"), "review")["reason"] == "ambiguous_unit"
    for line in ("주5일 근무 무게", "매장 근처 3km 무게", "최근 무게 변화"):
        out = text([line])
        assert out["weights"] == [] and out["review"] == []


@pytest.mark.parametrize("value, expected", [("1,5kg", 1500), ("2,25 kg", 2250), ("1,500g", 1500), ("1,200 g", 1200),
                                             ("3,000kg", 3000000), ("1, 5kg", 5000)])
def test_decimal_comma(value, expected):
    assert grams(weights("중량", value)) == [expected]


def test_decimal_comma_in_grams_is_for_a_person():
    out = weights("샤프트 중량", "45,50g대")
    assert out["weights"] == [] and one(out, "review")["reason"] == "decimal_comma"


@pytest.mark.parametrize("label, value, kind", [
    ("포장 중량", "1.2kg", "packed"), ("택배 무게", "1.2kg", "packed"), ("포장시 무게", "1.2kg", "packed"),
    ("박스 포함 무게", "1.2kg", "packed"), ("배송 무게", "8kg", "packed"), ("포장 무게", "8kg", "packed"),
    ("중량", "9kg (박스 포함)", "packed"), ("중량", "약 1.2kg(포장 포함)", "packed"),
    ("제품 무게", "350g", "net"), ("본품 무게", "1kg", "net"), ("순무게", "1kg", "net"), ("Net Wt", "1 kg", "net"),
    ("총중량", "2.3kg", "unknown"), ("중량", "6kg (박스 미포함)", "unknown"), ("중량", "55g (샤프트)", "component"),
])
def test_packed_net_and_the_words_after_the_number(label, value, kind):
    assert one(weights(label, value))["kind"] == kind


def test_total_weight_outside_a_set_is_unknown():
    c = one(weights("총중량", "2.3kg"))
    assert (c["kind"], c["scope"]) == ("unknown", "unknown")


def test_each_segment_has_its_own_words():
    out = weights("중량", "본품 1kg / 포장 포함 1.3kg")
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(1000, "net"), (1300, "packed")]
    out = weights("무게", "본체 120g / 충전케이스 50g")
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(120, "net")]
    assert one(out, "review")["reason"] == "other_part"
    c = one(weights("무게", "세트 총 9kg (캐디백 포함)", name="골프 풀세트"))
    assert c["scope"] == "set"


def test_packed_box_line_without_a_size_label():
    out = text(["포장 박스 : 128 X 32 X 28 cm, 9kg"])
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(9000, "packed")]
    d = one(out, "dimensions")
    assert (d["values"], d["kind"]) == ([1280, 320, 280], "packed")
    for line in ("박스 10개 입", "사과 5kg 박스"):
        assert text([line])["weights"] == [] and text([line])["dimensions"] == []


@pytest.mark.parametrize("value, expected", [
    ("1200g(±50g)", [1200]), ("오차범위 ±50g, 1200g", [1200]), ("1.45kg (3.2lb)", [1450]),
    ("약 3.2파운드(1.45kg)", [1451.496]), ("3lbs 2oz", [1417.476]), ("3 lb 4 oz", [1474.175]),
    ("6.35 kg / 14 lbs", [6350]), ("6.5kg(14.3lbs)", [6500]),
    ("S:250g / M:270g", [250, 270]), ("1kg (2kg 옵션)", [1000, 2000]), ("7kg / 9lbs", [7000, 4082.331]),
    ("약11.5kg / 4.7kg", [11500, 4700]),
])
def test_tolerance_alternate_unit_and_lb_oz(value, expected):
    assert grams(weights("무게", value)) == expected


def test_alternate_unit_keeps_both_texts_and_approx():
    c = one(weights("무게", "약 3.2파운드(1.45kg)"))
    assert c["approximate"] and c["matched"] == "3.2파운드(1.45kg)" and "alternate_unit" in c["flags"]
    assert "lb_oz" in one(weights("무게", "3lbs 2oz"))["flags"]


@pytest.mark.parametrize("label, value, expected", [
    ("중량", "45g/개", [(45, "unit", None)]),
    ("중량", "45g(1개)", [(45, "unit", None)]),
    ("중량", "1개 약 45g / 12개 540g", [(45, "unit", None), (540, "unknown", None)]),
    ("중량", "1개 기준 45g", [(45, "unit", None)]),
    ("포장단위별 내용물의 용량(중량), 수량", "500g x 2개", [(500, "unit", 2), (1000, "set", 2)]),
    ("중량", "45g x 12개", [(45, "unit", 12), (540, "set", 12)]),
])
def test_per_unit_and_multiplier(label, value, expected):
    out = weights(label, value)
    assert [(c["value"]["min"], c["scope"], c["count"]) for c in out["weights"]] == expected
    assert all(("multiplied" in c["flags"]) == (c["scope"] == "set") for c in out["weights"])


@pytest.mark.parametrize("label, value", [("크기", "30 x 20 x 10cm"), ("무게", "2x 줌"), ("무게", "1x3 볼 패키지")])
def test_multiplier_needs_a_weight(label, value):
    assert weights(label, value)["weights"] == []


SET2 = "캘러웨이 풀세트"


def test_bare_total_is_a_club_total_not_the_set():
    out = weights("총중량", "Flex S 약 312g / Flex R 약 311g", name=SET2)
    assert [(c["value"]["min"], c["kind"], c["scope"]) for c in out["weights"]] == [
        (312, "component", "unknown"), (311, "component", "unknown")]
    assert one(weights("무게", "세트 총중량 9.5kg", name="골프 풀세트"))["scope"] == "set"
    assert one(weights("무게", "총 무게 약 9kg", name="골프 풀세트"))["scope"] == "set"
    assert one(text(["총 무게 9.8kg"], name="골프 풀세트"))["scope"] == "set"


@pytest.mark.parametrize("label, value, name, expected", [
    ("중량", "7번 기준 36인치 , 332g", "PRGR SWEEP M17 여성 6아이언", 332),     # 6712059632
    ("중량", "#7 기준 380g", None, 380),
    ("중량", "7번 아이언기준 400g", None, 400),
    ("중량", "NS PRO950 R기준 약 94.61cm,약 405g", "젝시오 7아이언세트", 405),     # 12375293796
])
def test_reference_club_is_a_component(label, value, name, expected):
    c = one(notice(label, value, name=name))
    assert (c["value"]["min"], c["kind"]) == (expected, "component")


@pytest.mark.parametrize("value, scope", [("1개 기준 45g", "unit"), ("270mm 기준 350g", "unknown"),
                                          ("M 사이즈 기준 250g", "unknown")])
def test_other_references_are_not_clubs(value, scope):
    c = one(weights("중량", value))
    assert (c["kind"], c["scope"]) == ("unknown", scope)


def test_weight_in_a_size_row():
    out = notice("크기", "7번 R기준 93.345cm / 7번 기준 328g", name="스릭슨 ZX 8아이언")      # 11236752052
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(328, "component")]
    c = one(notice("크기", "7번기준 약 94.615cm / 7번기준 약 403g", name="미즈노 8아이언세트"))   # 9747808561
    assert (c["value"]["min"], c["kind"], c["approximate"]) == (403, "component", True)
    out = weights("Package Dimensions", "50.8 x 30.48 x 12.7 cm; 2.27 kg")
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(2270, "packed")]
    assert one(out, "dimensions")["kind"] == "packed"
    out = weights("Product Dimensions", "10 x 5 x 3 inches; 1.5 Pounds")
    assert [(c["value"]["min"], c["kind"]) for c in out["weights"]] == [(680.389, "unknown")]
    assert one(out, "dimensions")["kind"] == "product"
    assert grams(notice("크기", "9.5인치 / 약 3.2kg")) == [3200]
    assert notice("헤드 체적", "460cc")["weights"] == []
    assert notice("크기", "화면 크기 6.1인치 5G")["weights"] == []


@pytest.mark.parametrize("name, is_set", [
    ("PRGR SWEEP M17 여성 6아이언", True), ("미즈노 JPX S30 8아이언 (NS 950GH)", True), ("핑 GLE4 여성 풀세트 3종", True),
    ("타이틀리스트 12pcs 골프클럽", True), ("PGM 4종 스틸 샤프트", True), ("골프채 11개 구성", True),
    ("핑 i525 7번 아이언 단품", False), ("Odyssey Headset", False), ("아이언 7번", False), ("#7 아이언", False),
    ("Ping G430 Offset Driver", False), ("1종 단품", False),
])
def test_set_from_counts(name, is_set):
    assert M.measures(name=name)["is_set"] is is_set


SET3 = "남성 골프 풀세트"


@pytest.mark.parametrize("source, label, value, name, expected", [
    ("notice", "중량", "9.5kg", SET3, (9500, "unknown", "set", [])),
    ("specs", "무게", "캐디백 포함 9kg", "골프 풀세트", (9000, "unknown", "set", [])),
    ("specs", "무게", "캐디백 2.8kg", "골프 풀세트", (2800, "component", "unknown", [])),
    ("specs", "무게", "약 2.8kg (캐디백 단독)", "골프 풀세트", (2800, "component", "unknown", [])),
    ("specs", "중량", "골프백 제외 약 3.5kg", "골프 풀세트", (3500, "unknown", "set", ["bag_excluded"])),
    ("notice", "중량", "332g", "젝시오 7아이언세트", (332, "component", "unknown", ["part_scale"])),
    ("notice", "중량", "약 7.5kg (캐디백 포함)", SET3, (7500, "unknown", "set", [])),
    ("notice", "제품 무게", "9kg", SET3, (9000, "net", "set", [])),
    ("notice", "중량", "1W 약 300g", SET3, (300, "component", "unknown", [])),
    ("notice", "중량", "9.5kg", "핑 G430 드라이버", (9500, "unknown", "unknown", [])),    # not a set: as before
])
def test_plain_weight_row_of_a_set(source, label, value, name, expected):
    rows = [{"label": label, "value": value}]
    out = M.measures(rows=rows, name=name) if source == "specs" else M.measures(notice={"items": rows}, name=name)
    c = one(out)
    assert (c["value"]["min"], c["kind"], c["scope"], c["flags"]) == expected


def test_plain_label_only_in_structured_rows():
    c = one(text(["무게 6kg"], name=SET3))
    assert c["scope"] == "unknown"
    c = one(weights("Item Weight", "‎14 Pounds", name="Callaway Strata Complete Set"))   # 10639350746
    assert (c["value"]["min"], c["scope"], c["quote"]) == (6350.293, "set", "Item Weight: 14 Pounds")


PGM = {"option_groups": [{"name": "타입", "type": "COMBINATION"}],
       "variants": [{"id": "39671831483", "options": ["4스틸 + 골프백"]}, {"id": "39671831485", "options": ["4카본 + 골프백"]},
                    {"id": "39671831486", "options": ["12스틸 + 골프백"]}, {"id": "39671831488", "options": ["12카본 + 골프백"]},
                    {"id": "39671831489", "options": ["12스틸 + 골프백 (신축성)"]},
                    {"id": "39671831490", "options": ["12카본 + 골프백 (신축성)"]}]}         # 6630856593
TWELVE = {"scope": "variants", "variant_ids": ["39671831486", "39671831488", "39671831489", "39671831490"]}
FOUR = {"scope": "variants", "variant_ids": ["39671831483", "39671831485"]}


@pytest.mark.parametrize("value", ["약11.5kg / 4.7kg", "12개 11.5kg / 4개 4.7kg", "12스틸 11.5kg / 4스틸 4.7kg"])
def test_value_list_bound_by_club_count(value):
    out = notice("중량", value, options=PGM, name="PGM 좌타 골프채풀세트")
    assert [(c["value"]["min"], c["scope"], c["binding"]) for c in out["weights"]] == [
        (11500, "set", TWELVE), (4700, "set", FOUR)]
    assert ("bound_by_count_rank" in out["weights"][0]["flags"]) is (value == "약11.5kg / 4.7kg")


def test_value_list_that_cannot_be_bound_is_for_a_person():
    colours = {"option_groups": [{"name": "색상", "type": "COMBINATION"}],
               "variants": [{"id": "1", "options": ["블랙"]}, {"id": "2", "options": ["화이트"]}]}
    out = notice("중량", "약11.5kg / 4.7kg", options=colours, name="PGM 골프채풀세트")
    assert out["weights"] == [] and one(out, "review")["reason"] == "value_list"
    for value in ("11.5kg / 11.5kg", "11.5kg / 4.7kg / 3kg"):                # equal values; three against two counts
        out = notice("중량", value, options=PGM, name="PGM 골프채풀세트")
        assert out["weights"] == [] and one(out, "review")["reason"] == "value_list"
    out = notice("중량", "스몰 250g / 미디엄 270g",
                 options={"option_groups": [{"name": "사이즈", "type": "COMBINATION"}],
                          "variants": [{"id": "s", "options": ["스몰"]}, {"id": "m", "options": ["미디엄"]}]})
    assert [c["binding"]["variant_ids"] for c in out["weights"]] == [["s"], ["m"]]


def test_club_heading_blocks():
    lines = ["📐 클럽 상세 스펙 가이드 (Club Specifications)", "1. 드라이버 (1W)",
             "로프트각: 10.5° / 라이각: 58.5° / 클럽 길이: 45.25인치", "총중량: Flex S 약 312g / Flex R 약 311g",
             "4. 아이언 세트 (#6 ~ SW)",
             "#6 아이언: 로프트각 28.0° / 라이각 62.0° / 길이 S 37.25인치, R 37.5인치 (중량: S 약 418g / R 약 382g)",
             "🏌️ 클럽 구성 (총 11개 세트)", "세트 총 무게 약 7.2kg"]                    # 13777887875, wording kept
    out = text(lines, name="캘러웨이 엑스핫 X HOT 남성용 골프채 풀세트 11개")
    assert [(c["value"]["min"], c["kind"], c["scope"]) for c in out["weights"]] == [
        (312, "component", "unknown"), (311, "component", "unknown"), (418, "component", "unknown"),
        (382, "component", "unknown"), (7200, "unknown", "set")]
    assert one(out, "dimensions")["kind"] == "component"                     # the driver's length, not the set's
    assert one(text(["세트 총 무게 약 7.2kg"], name=SET3))["scope"] == "set"


def test_club_codes_are_parts():
    assert one(weights("", "클럽무게(S세트) 5i: 약 416g", name=SET3))["kind"] == "component"
    assert one(notice("중량", "PW 450g", name=SET3))["kind"] == "component"
    assert one(notice("중량", "4WD 9kg", name=SET3))["kind"] == "unknown"


def test_td_header_tables():
    html = ("<table><tr><td>번호</td><td>드라이버</td><td>5i</td></tr>"
            "<tr><td>클럽무게(S세트)</td><td>약 318g</td><td>약 416g</td></tr></table>"           # 6774818843
            "<table><tr><td>클럽</td><td>드라이버</td><td>퍼터</td></tr>"
            "<tr><td>클럽 총 무게(g)</td><td>약 314</td><td>약 526</td></tr></table>"             # 13049116377
            "<table><tr><td>무게</td><td>14 파운드</td></tr></table>"
            "<table><tr><td>크기</td><td>130 x 30 x 25 cm</td><td>9kg</td></tr>"                 # not a header
            "<tr><td>무게</td><td>8kg</td><td>10kg</td></tr></table>")
    out = M.measures(description={"text": "", "html": html}, name=SET3)
    assert [(c["quote"], c["value"]["min"], c["kind"], c["scope"]) for c in out["weights"]] == [
        ("클럽무게(S세트) 드라이버: 약 318g", 318, "component", "unknown"),
        ("클럽무게(S세트) 5i: 약 416g", 416, "component", "unknown"),
        ("클럽 총 무게(g) 드라이버: 약 314", 314, "component", "unknown"),
        ("클럽 총 무게(g) 퍼터: 약 526", 526, "component", "unknown"),
        ("무게: 14 파운드", 6350.293, "unknown", "set")]


def test_all_triples_each_with_its_kind():
    out = weights("제품 크기", "30x20x10cm / 포장 크기 35x25x15cm")
    assert [(c["values"], c["kind"], c["flags"]) for c in out["dimensions"]] == [
        ([300, 200, 100], "product", ["axis_order_unresolved", "not_confirmed_packed"]),
        ([350, 250, 150], "packed", ["axis_order_unresolved"])]
    out = weights("크기", "본체 50x30x15mm / 박스 80x60x40mm")
    assert [c["kind"] for c in out["dimensions"]] == ["product", "packed"]
    assert one(weights("포장 크기", "35x25x15cm"), "dimensions")["kind"] == "packed"
    assert len(weights("크기", "48.2 x 12.7 x 8.5 inches (122 x 32 x 21 cm)")["dimensions"]) == 1


@pytest.mark.parametrize("label, value, mm", [
    ("크기", "30x20cm", [300, 200]), ("캐디백 크기", "9인치 x 46인치", [228.6, 1168.4]),
    ("크기", "3피트 x 10피트", [914.4, 3048]), ("크기", "100 x 200 mm", [100, 200]),
])
def test_two_sides(label, value, mm):
    c = one(weights(label, value), "dimensions")
    assert (c["values"], c["axes"], c["flags"]) == (mm, None, ["two_sides", "not_confirmed_packed"])


@pytest.mark.parametrize("value", ["1920x1080", "M8x20mm", "4x4"])
def test_not_two_sides(value):
    out = weights("크기", value)
    assert out["dimensions"] == []


@pytest.mark.parametrize("label, value, mm, axes", [
    ("Product Dimensions", "‎48\"L x 11\"W x 11\"H", [1219.2, 279.4, 279.4], ["length", "width", "height"]),
    ("크기", "가로 30 세로 20 높이 10 (cm)", [300, 200, 100], ["width", "depth", "height"]),
    ("크기(단위:cm)", "30 x 20 x 10", [300, 200, 100], None),
    ("크기", "30 x 20 x 10 (단위: cm)", [300, 200, 100], None),
    ("크기", "30x20x10센치", [300, 200, 100], None),
    ("Item Package Dimensions L x W x H", "48.2 x 12.7 x 8.5 inches", [1224.28, 322.58, 215.9],
     ["length", "width", "height"]),
    ("가로x세로x높이", "130x30x25cm", [1300, 300, 250], ["width", "depth", "height"]),
])
def test_axes_and_units_found_elsewhere(label, value, mm, axes):
    c = one(weights(label, value), "dimensions")
    assert (c["values"], c["axes"]) == (mm, axes)
    assert ("axis_order_unresolved" in c["flags"]) is (axes is None)


def test_unitless_triple_stays_unit_missing():
    assert one(weights("크기", "W1200 x D600 x H750"), "review")["reason"] == "unit_missing"


@pytest.mark.parametrize("lines", [["사은품 7종세트-장갑 사이즈 (18-21호) (필수)"],
                                   ["브리지스톤 V300X 아이언 세트(5~9, P, 56도 웨지)를 구매했습니다 크기가 딱"]])
def test_ranges_need_a_length_unit(lines):
    out = text(lines)
    assert out["dimensions"] == [] and out["review"] == []


def test_ranges_with_a_unit_and_shoe_sizes():
    assert one(weights("길이", "120~150cm 조절"), "review")["reason"] == "manual_review"
    assert one(weights("크기", "120~150cm"), "review")["reason"] == "manual_review"
    out = weights("치수", "230~280mm", name="풋조이 남성 골프화")
    assert out["dimensions"] == [] and out["review"] == []


@pytest.mark.parametrize("label, value", [("사용자 최대 무게", "120kg"), ("최대 하중", "120kg"), ("Max Weight", "120 kg"),
                                          ("적재 중량", "50kg"), ("Weight capacity", "300 lbs")])
def test_load_and_capacity_are_not_weights(label, value):
    out = weights(label, value)
    assert out["weights"] == [] and out["review"] == []


def test_load_only_skips_its_own_segment():
    assert grams(weights("무게", "12kg / 최대 하중 120kg")) == [12000]


def test_flags_and_count_on_every_weight():
    c = one(weights("무게", "9kg"))
    assert (c["flags"], c["count"]) == ([], None)
