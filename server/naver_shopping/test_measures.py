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
