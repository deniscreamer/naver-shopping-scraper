"""Offline tests for the five shipping fields (package_measures.py). The table row here is a test row, not the
operator's values; the committed category_measures.json holds the operator's (50002788, checked here too).

    .venv/bin/python -m pytest scripts/test_package_measures.py -q
"""
import copy

import pytest

from package_measures import (BASELINE_SIDES, BASELINES, FIELDS, CategoryDefaultsInvalid, CategoryDefaultsMissing,
                              check_row, current_defaults, default_kind, load_table, on_scale, row_version,
                              variant_measures)

ROW = {"category_id": "50002788", "category_name": "풀세트", "approved_by": "test", "approved_at": "2026-11-05",
       "reliability": "estimated_average",
       "fields": {name: {"low": 1, "central": 2, "high": 3} for name in FIELDS}}
TABLE = {"version": 7, "rows": [ROW]}
PRODUCT = {"scope": "product", "variant_ids": []}


def weight(grams, kind="unknown", scope="unknown", binding=PRODUCT, top=None):
    return {"value": {"min": grams, "max": top or grams}, "unit": "kg", "matched": "", "kind": kind, "scope": scope,
            "approximate": False, "quote": f"무게: {grams}", "source": "specs", "locator": {"block": "상품정보", "row": 0},
            "binding": binding, "origin": "source_stated"}


def box(values, kind="packed", flags=(), binding=PRODUCT):
    return {"values": values, "axes": None, "unit": "cm", "matched": "", "kind": kind, "state": None,
            "flags": list(flags), "quote": "크기", "source": "specs", "locator": {"block": "상품정보", "row": 1},
            "binding": binding, "origin": "source_stated"}


def specs(weights=(), dimensions=(), variants=(), is_set=False):
    return {"category": {"id": "50002788", "name": "풀세트"},
            "options": {"variants": [{"id": v} for v in variants]} if variants else None,
            "measures": {"is_set": is_set, "weights": list(weights), "dimensions": list(dimensions),
                         "references": [], "review": []}}


def test_committed_table_is_valid():
    table = load_table()
    assert isinstance(table["version"], int) and table["version"] >= 1
    [row] = [r for r in table["rows"] if r["category_id"] == "50002788"]
    assert row["reliability"] == "estimated_average" and row["fields"]["package_weight_g"]["central"] == 7000


def test_no_row_stops_the_category():
    with pytest.raises(CategoryDefaultsMissing, match="category 99999999 .그 외.*ask the operator"):
        variant_measures({**specs(), "category": {"id": "99999999", "name": "그 외"}}, load_table())
    with pytest.raises(CategoryDefaultsMissing, match="category 50002788"):
        variant_measures(specs(), {"version": 0, "rows": []})


def test_seller_values_first_then_defaults():
    [v] = variant_measures(specs([weight(9000), weight(12000, "packed")], [box([300, 1250, 350])]), TABLE)
    f = v["fields"]
    assert v["variant_id"] is None and f["product_weight_g"]["value"] == {"min": 9000, "max": 9000}
    assert f["package_weight_g"]["source"] == "source_stated" and f["package_weight_g"]["kind"] == "packed"
    assert [f[n]["value"]["min"] for n in FIELDS[2:]] == [1250, 350, 300]        # longest side first
    all_stated = variant_measures(specs([weight(9000), weight(12000, "packed")], [box([300, 1250, 350])]),
                                  {"version": 0, "rows": []})                     # no table needed
    assert all(x["source"] == "source_stated" for x in all_stated[0]["fields"].values())


def test_defaults_fill_only_missing_fields():
    [v] = variant_measures(specs([weight(9000)]), TABLE)
    f = v["fields"]
    assert f["product_weight_g"]["source"] == "source_stated"
    assert f["package_weight_g"] == {"low": 1, "central": 2, "high": 3, "source": "category_default", "confidence": 1,
                                     "reliability": "estimated_average", "table_version": 7, "approved_by": "test", "approved_at": "2026-11-05",
                                     "flags": ["below_stated_product"]}       # the test row's 2 g is under 9 kg


def test_what_is_not_a_product_or_package_value():
    out = variant_measures(specs([weight(300, "component"), weight(9000, scope="unit"), weight(8000)],
                                 [box([1, 2, 3], kind="unknown", flags=["not_confirmed_packed"])], is_set=True), TABLE)
    f = out[0]["fields"]
    assert all(f[n]["source"] == "category_default" for n in FIELDS)    # in a set only scope set is the product
    assert out[0]["product_size"][0]["values"] == [1, 2, 3]
    f = variant_measures(specs([weight(9500, scope="set")], is_set=True), TABLE)[0]["fields"]
    assert f["product_weight_g"]["value"]["min"] == 9500


def test_contradiction_falls_back_and_keeps_both():
    f = variant_measures(specs([weight(9000), weight(11000)]), TABLE)[0]["fields"]["product_weight_g"]
    assert f["source"] == "category_default" and len(f["contradiction"]) == 2
    f = variant_measures(specs([weight(9000, top=10000), weight(9500)]), TABLE)[0]["fields"]["product_weight_g"]
    assert f["source"] == "source_stated" and f["also"] == 1                       # overlapping ranges agree


def test_per_variant_binding():
    only_b = {"scope": "variants", "variant_ids": ["b"]}
    out = variant_measures(specs([weight(12000, "packed", binding=only_b),
                                  weight(1, binding={"scope": "context", "variant_ids": []})], variants=["a", "b"]),
                           TABLE)
    a, b = (x["fields"] for x in out)
    assert a["package_weight_g"]["source"] == "category_default" and b["package_weight_g"]["value"]["min"] == 12000
    assert a["product_weight_g"]["source"] == b["product_weight_g"]["source"] == "category_default"   # context


@pytest.mark.parametrize("change", [
    lambda r: r.pop("approved_by"),
    lambda r: r["fields"].pop("package_height_mm"),
    lambda r: r["fields"]["package_weight_g"].update(low=5),
    lambda r: r.pop("reliability"),
])
def test_bad_rows(change):
    row = copy.deepcopy(ROW)
    change(row)
    with pytest.raises(CategoryDefaultsInvalid):
        check_row(row)


def test_a_single_product_size_is_kept():
    club = {**box([1155.7], kind="product"), "axes": ["length"]}
    [v] = variant_measures(specs(dimensions=[club, box([1, 2, 3], kind="component")]), TABLE)
    assert [c["values"] for c in v["product_size"]] == [[1155.7]]


# ---- 2026-11-06: stated set weights per variant, the default's floor, an operator band ----------------------------

def test_the_same_weight_within_two_percent_agrees():
    f = variant_measures(specs([weight(6350), weight(6450)]), TABLE)[0]["fields"]["product_weight_g"]
    assert f["source"] == "source_stated" and f["also"] == 1
    f = variant_measures(specs([weight(6350), weight(6600)]), TABLE)[0]["fields"]["product_weight_g"]
    assert f["source"] == "category_default" and len(f["contradiction"]) == 2


def test_set_weight_per_variant_and_the_default_below_it():
    twelve = {"scope": "variants", "variant_ids": ["12s", "12c"]}
    four = {"scope": "variants", "variant_ids": ["4s"]}
    out = variant_measures(specs([weight(11500, scope="set", binding=twelve), weight(4700, scope="set", binding=four)],
                                 variants=["4s", "12s", "12c"], is_set=True), load_table())      # 6630856593
    by_id = {v["variant_id"]: v["fields"] for v in out}
    assert [by_id[i]["product_weight_g"]["value"]["min"] for i in ("4s", "12s", "12c")] == [4700, 11500, 11500]
    assert by_id["12s"]["package_weight_g"]["source"] == "category_default"
    assert by_id["12s"]["package_weight_g"]["flags"] == ["below_stated_product"]       # 7000 < 11500
    assert "flags" not in by_id["4s"]["package_weight_g"]


def test_flags_travel_with_the_evidence():
    w = {**weight(1000, scope="set"), "flags": ["multiplied"], "count": 2}
    f = variant_measures(specs([w]), TABLE)[0]["fields"]["product_weight_g"]
    assert f["source"] == "source_stated" and f["flags"] == ["multiplied"]


def test_parts_are_never_summed():
    parts = [weight(g, "component") for g in (318, 330, 416, 420, 424, 430, 436, 446, 455, 521)]   # 6774818843
    f = variant_measures(specs(parts, is_set=True), TABLE)[0]["fields"]
    assert f["product_weight_g"]["source"] == f["package_weight_g"]["source"] == "category_default"
    assert "flags" not in f["package_weight_g"]


BAND = {**ROW, "fields": {name: {"low": 1000, "central": 2000, "high": 3000} for name in FIELDS},
        "plausible": {"product_weight_g": {"min": 1750, "max": 19000}}}


def test_an_operator_band_rejects_an_implausible_stated_value():
    table = {"version": 8, "rows": [BAND]}
    f = variant_measures(specs([weight(332, scope="set")], is_set=True), table)[0]["fields"]["product_weight_g"]
    assert f["source"] == "category_default" and f["reason"] == "implausible_for_category"
    assert [c["value"]["min"] for c in f["contradiction"]] == [332]
    f = variant_measures(specs([weight(6350, scope="set")], is_set=True), table)[0]["fields"]["product_weight_g"]
    assert f["source"] == "source_stated"
    assert "plausible" not in load_table()["rows"][0]        # no band until the operator gives one


@pytest.mark.parametrize("band", [{"product_weight_g": {"min": 5, "max": 1}}, {"weight": {"min": 1, "max": 2}},
                                  {"product_weight_g": {"min": 1}}])
def test_bad_bands(band):
    with pytest.raises(CategoryDefaultsInvalid):
        check_row({**ROW, "plausible": band})


def test_confidence():
    # the owner, 2026-11-06: a stated weight whose kind is open is used; 2026-11-10: the scale is 1-5 (4 here, 2 before)
    twelve = {"scope": "variants", "variant_ids": ["12s"]}
    f = variant_measures(specs([{**weight(11500, scope="set", binding=twelve), "flags": ["bound_by_count_rank"]}],
                               variants=["12s"], is_set=True), TABLE)[0]["fields"]          # 6630856593
    assert (f["product_weight_g"]["source"], f["product_weight_g"]["confidence"]) == ("source_stated", 4)
    assert f["package_weight_g"]["confidence"] == 1                                       # the category default
    f = variant_measures(specs([weight(9000)]), TABLE)[0]["fields"]
    assert f["product_weight_g"]["confidence"] == 4                       # "무게 9kg": with the box or not?
    f = variant_measures(specs([weight(9000, kind="net"), weight(9500, kind="packed")], [box([30, 120, 25])]),
                         TABLE)[0]["fields"]
    assert [f[n]["confidence"] for n in FIELDS] == [5, 5, 5, 5, 5]        # stated with its kind (3 before)
    f = variant_measures(specs([weight(9000), weight(9000, kind="net")]), TABLE)[0]["fields"]["product_weight_g"]
    assert (f["kind"], f["confidence"], f["also"]) == ("net", 5, 1)        # the more certain of two that agree


def test_on_scale_puts_a_collected_line_on_todays_levels():
    """Lines collected before 2026-11-10 carry 1-3: a seller's value (and a contradiction's) is levelled again from
    its own kind and flags, so one prepared record never mixes the scales; a default is 1 on both."""
    f = variant_measures(specs([weight(9000, kind="net")], [box([30, 120, 25])]), TABLE)[0]["fields"]
    old = {n: {**v, "confidence": {5: 3, 4: 2}.get(v["confidence"], 1)} for n, v in f.items()}       # as collected then
    old["package_weight_g"] = {**old["package_weight_g"],                    # two packed weights that disagreed
                               "contradiction": [{**f["product_weight_g"], "kind": "packed", "confidence": 3}]}
    new = on_scale(old)
    assert [new[n]["confidence"] for n in FIELDS] == [5, 1, 5, 5, 5]
    assert new["package_weight_g"]["contradiction"][0]["confidence"] == 5 and on_scale(new) == new


# ---- 2026-11-10: the operator's baselines for the composition (an optional block of a row) ---------------------

BASE = {"item_g": 340, "container_g": 3800, "carton_g": 2000, "longest_item_mm": 1140, "length_margin_mm": 100,
        "sides_mm": [200, 160], "sides_with_container_mm": [400, 320], "basis": {"item_g": "the sellers' tables"},
        "approved_by": "owner", "approved_at": "2026-11-10"}


def test_baselines_block_is_optional_and_the_operators():
    """The owner's amounts of 2026-11-10 for 50002788, with where each comes from; the table's version rose."""
    table = load_table()
    block = table["rows"][0]["baselines"]
    assert {k: block[k] for k in BASE if k != "basis"} == {k: v for k, v in BASE.items() if k != "basis"}
    assert table["version"] == 8 and set(block["basis"]) >= {*BASELINES, *BASELINE_SIDES}
    check_row(ROW)                                                    # a row without the block: no composition
    check_row({**ROW, "baselines": BASE})


@pytest.mark.parametrize("block", [
    {k: v for k, v in BASE.items() if k != "approved_by"},            # nobody approved it
    {k: v for k, v in BASE.items() if k != "approved_at"},
    {k: v for k, v in BASE.items() if k != "basis"},                  # where the amounts come from
    {k: v for k, v in BASE.items() if k != "container_g"},            # whole or not at all
    {**BASE, "carton_g": "2kg"}, {**BASE, "length_margin_mm": -100}, {**BASE, "item_g": True}, {**BASE, "item_g": 0},
    {**BASE, "sides_mm": [200]}, {**BASE, "sides_mm": [160, 200]},    # [width, height], the wider first
    {**BASE, "sides_with_container_mm": 400}, {**BASE, "width_margin_mm": 50},
    [340, 3800], {},
])
def test_bad_baselines(block):
    with pytest.raises(CategoryDefaultsInvalid, match="baselines"):
        check_row({**ROW, "baselines": block})


JUNIOR = next(r for r in load_table()["rows"] if r["category_id"] == "50002787")


@pytest.mark.parametrize("title, variant, kind", [
    # the owner's two defaults of 2026-11-11 (titles of the 50002787 listing that day)
    ("안전성시험통과 주니어골프채 퍼터 어린이 골프클럽 아동 초등학생", None, "single_club"),
    ("아화 그린록 주니어 드라이버", "S(9-12세)", "single_club"),
    ("PGM 주니어 드라이버 하이브리드 골프클럽 카본파이버 샤프트", None, "single_club"),
    ("PGM 주니어골프클럽 풀세트6 핑크", "드라이버 단품", "single_club"),     # 단품 in the variant: alone
    ("3종세트 주니어 골프채 어린이 퍼터 아이언 드라이버 골프클럽", None, None),   # a set word: the set's box
    ("클리브랜드 주니어 라지 풀세트 7개 11~14세", None, None),
    ("US키즈골프 어린이 골프채 주니어 세트 가방포함 UL7 54사이즈 5클럽", None, None),
    ("어린이 골프채 3종 + 골프가방 세트 주니어 퍼터 아이언 드라이버 아동 캐디백", None, None),
    ("주니어 골프채 어린이", "드라이버+퍼터 2개", "two_clubs"),                # two clubs: a box for two (2026-11-11)
    ("PGM 주니어 골프 세트", "아이언", "single_club"),                        # the variant names one club
    ("키즈 어린이 주니어 골프채 퍼터 클럽 세트", "6-8세 아이언 6/7번", "single_club"),   # 5035551656
    ("키즈 어린이 주니어 골프채 퍼터 클럽 세트", "주니어 골프가방 블루", None),          # the bag: the larger box
    ("주니어골프채 연습용 어린이 초등학생골프채 퍼터 유아용 클럽", "6~8세 퍼터", "single_club"),  # 5447766140: not "클럽 6"
    ("3종세트 주니어 골프채 어린이 퍼터 아이언 드라이버", "5-8세 골프채 3종세트", None),     # 6232511226
    ("캘러웨이 XJ 주니어 골프채 풀세트 2026", "XJ2풀세트 (7개 구성)", None),              # 10573086064
    ("PGM 주니어 골프채 풀세트", "드라이버 10.5도", None),                    # a 풀세트's choice: the set's box
    ("어린이골프채 아기골프채 안전인증 교구 아이언 퍼터 우드 클럽", "퍼터 / 9호 / ORANGE", "single_club"),  # 4987660149
    ("엠유스포츠 밀키 주니어 골프채", None, None),                              # no club word: the set's box
    # 2026-11-12: an age, a height, a loft or a size after 클럽 is not a count of clubs (was the set's box, $709-729)
    ("[감씨]주니어 골프채 어린이 골프클럽 6~8세 드라이버", None, "single_club"),      # 5396141262
    ("어린이 주니어 골프채 아동 초등학생용 클럽 6-8세 퍼터", None, "single_club"),     # 4649618264
    ("어린이골프채 주니어 샌드 웨지 클럽 56도웨지 사용자 키 130-160cm", None, "single_club"),  # 6849582078
    ("주니어 UL7 단품 아이언 7번 아이언, 57 사이즈", None, "single_club"),
    ("US키즈골프 어린이 골프채 주니어 세트 가방포함 UL7 57사이즈 7클럽", None, None),  # the count stays
    ("캘러웨이 XJ2 주니어 풀세트 115CM-130CM (6개 세트) 2026", None, None),
    ("주니어 골프 세트 조절식 드라이버 3세 이상, Red", None, None),                # a set word: the set's box
])
def test_junior_single_club_or_set(title, variant, kind):
    found = default_kind(JUNIOR, title, variant)
    assert (found or {}).get("kind") == kind


def test_a_kind_fills_its_own_defaults_per_variant():
    s = {"name": "PGM 주니어골프클럽 풀세트6", "category": {"id": "50002787", "name": "주니어용클럽"},
         "options": {"variants": [{"id": "1", "name": "풀세트6 핑크"}, {"id": "2", "name": "드라이버 단품"}]},
         "measures": {"is_set": True, "weights": [], "dimensions": [], "references": [], "review": []}}
    by = {p["variant_id"]: p["fields"] for p in variant_measures(s, load_table())}
    assert by["1"]["package_length_mm"]["central"] == 1050 and "kind" not in by["1"]["package_length_mm"]
    assert by["2"]["package_length_mm"]["central"] == 900 and by["2"]["package_weight_g"]["kind"] == "single_club"
    assert by["2"]["package_weight_g"]["source"] == "category_default" and by["2"]["package_weight_g"]["confidence"] == 1


@pytest.mark.parametrize("kinds", [
    [{"kind": "x", "fields": ROW["fields"], "basis": "b"}],                                  # no match
    [{"kind": "x", "match": "(", "fields": ROW["fields"], "basis": "b"}],                    # not a regex
    [{"kind": "x", "match": "a", "fields": {}, "basis": "b"}],                               # no fields
    [{"kind": "x", "match": "a", "fields": ROW["fields"]}],                                  # no basis
    [{"kind": "x", "match": "a", "fields": ROW["fields"], "basis": "b", "size": 1}],         # unknown key
])
def test_bad_kinds(kinds):
    with pytest.raises(CategoryDefaultsInvalid, match="kind"):
        check_row({**ROW, "kinds": kinds})


def test_the_transform_takes_todays_default_and_keeps_the_rest():
    """5447766140 (2026-11-11): collected while "...클럽" + "6~8세" read as a count, its putter got the set's box;
    the kept run is never rewritten, so the transform takes today's default. A default already today's is kept as
    collected (its table_version too), and a seller's value is never touched."""
    s = {"name": "주니어골프채 연습용 어린이 초등학생골프채 퍼터 유아용 클럽", "category": {"id": "50002787"},
         "options": {"variants": [{"id": "1", "name": "6~8세 퍼터"}]}}
    table = load_table()
    old = {**JUNIOR["fields"]["package_length_mm"], "source": "category_default", "confidence": 1, "table_version": 1}
    seller = {"value": {"min": 1300, "max": 1300}, "source": "source_stated", "confidence": 5}
    got = current_defaults({"package_length_mm": old, "package_weight_g": seller}, s, "1", table)
    assert got["package_length_mm"]["central"] == 900 and got["package_length_mm"]["kind"] == "single_club"
    assert got["package_length_mm"]["table_version"] == JUNIOR["defaults_version"] and got["package_weight_g"] == seller
    same = {**JUNIOR["kinds"][0]["fields"]["package_length_mm"], "source": "category_default", "kind": "single_club",
            "table_version": 1}
    assert current_defaults({"package_length_mm": same}, s, "1", table)["package_length_mm"] == same


def test_a_restamped_default_carries_its_rows_version_not_the_tables():
    """2026-11-18: the row of 50002784 raised the table to 8; a default of another row restamped by the transform keeps
    its row's defaults_version (7), so a new row moves no other product; a row without one takes the table's."""
    table = load_table()
    assert table["version"] == 8 and {r["category_id"]: r["defaults_version"] for r in table["rows"]} == {
        "50002788": 7, "50002787": 7, "50002670": 7, "50002783": 7, "50002784": 8}
    assert row_version(table, JUNIOR) == 7 and row_version({"version": 9}, {k: v for k, v in JUNIOR.items()
                                                                            if k != "defaults_version"}) == 9
    for bad in (0, "7", 7.0, True):
        with pytest.raises(CategoryDefaultsInvalid, match="defaults_version"):
            check_row({**ROW, "defaults_version": bad})


@pytest.mark.parametrize("title, kind", [
    ("주니어 골프채2종세트 7번아이언 퍼터 어린이골프 아화골프", "two_clubs"),          # 8457258079: was the set's box
    ("주니어 7번아이언+어린이장갑 록스프랜드 2종세트", "two_clubs"),
    ("어린이 골프채 3종 + 골프가방 세트 주니어 퍼터 아이언 드라이버", None),
    ("캘러웨이 XT 주니어 풀세트 [10개+골프백]", None),
    ("주니어 2종 풀세트 가방포함", None),                                       # a bag: the set's box
])
def test_two_junior_clubs_get_a_box_for_two(title, kind):
    assert (default_kind(JUNIOR, title, None) or {}).get("kind") == kind


def test_iron_sets_take_the_sets_box_and_a_single_iron_its_own():
    """50002670 (the owner, 2026-11-14): a women's iron set 100 x 25 x 12 cm, 3.5 kg; an iron sold alone 98 x 11 x 8 cm,
    1 kg (the title screen leaves singles out; this is for one that slips through). In doubt, the set's box."""
    from package_measures import default_kind
    row = next(r for r in load_table()["rows"] if r["category_id"] == "50002670")
    assert row["fields"]["package_length_mm"]["central"] == 1000 and row["fields"]["package_weight_g"]["central"] == 3500
    assert default_kind(row, "젝시오 13 여성 아이언 단품 5번", None)["kind"] == "single_club"
    assert default_kind(row, "젝시오 13 여성 아이언", "5번 단품")["kind"] == "single_club"
    for title in ("7아이언세트 단품 여성", "던롭 젝시오 13 레이디스 아이언 7개 세트", "포틴 TB5 6-P 단품"):
        assert default_kind(row, title, None) is None


def test_wedge_sets_take_the_sets_box_and_a_single_wedge_its_own():
    """50002783 (the owner, 2026-11-15): a set of 2-3 wedges 98 x 20 x 10 cm, 2.2 kg; one wedge 96 x 11 x 8 cm, 1 kg: a
    variant that sells one wedge of a set-or-single listing (단품, 개별, 싱글), or 단품 in a title with no set word."""
    from package_measures import default_kind
    row = next(r for r in load_table()["rows"] if r["category_id"] == "50002783")
    assert row["fields"]["package_width_mm"]["central"] == 200 and row["fields"]["package_weight_g"]["central"] == 2200
    assert default_kind(row, "미즈노 JPX925 핫메탈 프로 웨지 단품", None)["kind"] == "single_club"
    assert default_kind(row, "BYBOMYA 단조 골프 웨지 개별 또는 세트", "개별 52도")["kind"] == "single_club"
    assert default_kind(row, "ALVO GOLF 웨지 세트 및 싱글", "싱글 56")["kind"] == "single_club"
    for title, variant in (("테일러메이드 MG5 웨지 SB 세트 3개", "52+56+60"), ("프로기아 웨지세트 단품", None),
                           ("BYBOMYA 단조 골프 웨지 개별 또는 세트", "세트 52/56/60"), ("웨지 3종 세트", "52도")):
        assert default_kind(row, title, variant) is None


WEDGES = next(r for r in load_table()["rows"] if r["category_id"] == "50002783")


@pytest.mark.parametrize("title, variant, siblings, kind", [
    ("미우라 포지드 웨지 2개세트", "2개 (52Y 56Y)", None, "two_wedges"),        # the variant's own count (11585678496)
    ("야마토 웨지 세트", "56 60 Degree Tarnish", None, "two_wedges"),          # two lofts in the value (13017295953)
    ("Mile High Life 웨지 세트", "Black Titanium Layer-50/56 Degrees", None, "two_wedges"),
    ("토호 웨지 2개 세트", "블랙", ["블랙", "실버"], "two_wedges"),              # the title's count, colours only
    ("웨지 4종 세트", "Black", None, "four_plus"),
    ("웨지 세트", "50/54/58/62", None, "four_plus"),
    ("웨지 세트", "G 52도 + S 56도 + L 60도", None, None),                       # three: the base box
    ("웨지 2개 세트", "52/56/60", ["52/56/60"], None),                         # the variant's own count first
    ("웨지 2개 세트", "블랙", ["52 56", "50 54 58"], None),                     # variants of other counts: in doubt
    ("PGM 웨지 48 50 52 54 56 58 60 62", "52 56 60 Set", None, None),          # never the title's lofts
    ("웨지 세트", "52-56", None, None),                                        # a range is no count
    ("웨지 52개 56개", "블랙", None, None),                                     # a loft read as a count
    ("웨지 2개 3개 세트", "블랙", None, None),                                  # 3+ anywhere
    ("웨지 2개 세트 캐디백", "블랙", None, None),
    ("BYBOMYA 웨지 개별 또는 세트", "개별 52도", None, "single_club"),          # single_club stays first
    # the W8 review (2026-11-17): three lofts before 세트 or after a model code's dash are three wedges, not two
    # (13830318407, 12918989466, 12178264810 took the two-wedge box); a lone shaft weight is no second loft
    ("밀리언 웨지 세트", "왼손 52 56 60 세트 1개", None, None),
    ("웨지 세트", "52 56 60세트", None, None),
    ("Mile High Life 웨지 세트", "LH01-52 56 60 Degree", None, None),
    ("웨지 세트", "50/56세트 / NSPRO 950 R", None, "two_wedges"),              # 10361963641
    ("웨지 세트", "50도 / Diamana 60 S", ["50도 / Diamana 60 S", "52도 / Diamana 60 S"], None),
    ("웨지 세트", "52도 Steelfiber 70", None, None),
    ("웨지 세트", "60 normal / 48°/52°/56°", None, None),                      # 13826807592: three, not four
])
def test_wedge_set_count_kinds(title, variant, siblings, kind):
    """C16 (the wedge-set review 2026-11-17, PACKAGE.md "Category defaults"): two wedges 98 x 15 x 10 cm, 1.7 kg; four to six the base box, 2.65 kg."""
    assert (default_kind(WEDGES, title, variant, siblings) or {}).get("kind") == kind


def test_wedge_count_kinds_values():
    two, four = (next(k for k in WEDGES["kinds"] if k["kind"] == n) for n in ("two_wedges", "four_plus"))
    assert [two["fields"][n]["central"] for n in FIELDS] == [920, 1700, 980, 150, 100] and two["lofts"] == [2, 2]
    assert [four["fields"][n]["central"] for n in FIELDS] == [1840, 2650, 980, 200, 100] and four["lofts"] == [4, 6]
    assert [k["kind"] for k in WEDGES["kinds"]] == ["single_club", "two_wedges", "four_plus"]


def test_loft_count():
    from package_measures import lofts
    assert [lofts(t) for t in ("52 56 degree (2PCS)", "Black Set (52 56 60)", "52-56", "50~54", "5256", "56cm 60g",
                               "LH01-56 Degree", "Silver / RH/50/54/58 Degrees Set")] == [2, 3, 0, 0, 0, 0, 1, 3]


@pytest.mark.parametrize("text, n", [
    # the W8 review (2026-11-17, 50002783 variant values): 세트 after a loft is no age, a model code's dash no range
    ("왼손 52 56 60 세트", 3), ("52 56 60세트", 3), ("52/56/60 세트", 3), ("50/56세트 / NSPRO 950 R", 2),
    ("LH01-52 56 60 Degree", 3), ("50 54 60세", 2), ("2개 (52Y 56Y)", 2),
    # a lone bare number is a shaft's weight or flex, not a loft
    ("50도 / Diamana 60 S", 1), ("52도 Steelfiber 70", 1), ("52도 / 스틸파이버 / i70 A", 1),
    ("60 normal / 48°/52°/56°", 3), ("크롬 / 52도09바운스+56도12바운스 (2개세트) / DIAMANA TM50 (L)", 2),
])
def test_loft_count_review(text, n):
    from package_measures import lofts
    assert lofts(text) == n


@pytest.mark.parametrize("lofts", [[1, 2], [3, 2], "2", [2.0, 2], [2]])
def test_kind_lofts_must_be_a_span(lofts):
    row = copy.deepcopy(WEDGES)
    row["kinds"][1]["lofts"] = lofts
    with pytest.raises(CategoryDefaultsInvalid):
        check_row(row)


@pytest.mark.parametrize("change", [
    lambda b: b.pop("basis"), lambda b: b.update(writes=["package_weight_g"]), lambda b: b.update(extra=1),
    lambda b: b.update(item_g={"min": 520, "max": 380}), lambda b: b.update(skip=["anything"]),
    lambda b: b.update(confidence={"labelled_sum": 4, "one_weight_times_count": 2}),
    lambda b: b.update(count_from=[]),
])
def test_compose_by_count_block_is_checked(change):
    row = copy.deepcopy(WEDGES)
    change(row["compose_by_count"])
    with pytest.raises(CategoryDefaultsInvalid):
        check_row(row)


def test_wedge_band_refuses_a_one_club_server_weight():
    """The band on the server path (variant_measures): a set page's 0.45 kg box is one wedge's; the default fills."""
    specs = {"category": {"id": "50002783"}, "name": "웨지 세트 52 56 60", "options": {"variants": []},
             "measures": {"is_set": True, "dimensions": [], "weights": [
                 {"value": {"min": 450, "max": 450}, "kind": "packed", "scope": "unknown", "quote": "Package Weight 0.45 kg",
                  "source": "description", "locator": {}, "binding": PRODUCT, "flags": []}]}}
    [v] = variant_measures(specs, load_table())
    f = v["fields"]["package_weight_g"]
    assert (f["source"], f["central"], f["reason"]) == ("category_default", 2200, "implausible_for_category")


def test_server_box_out_of_band_is_refused_whole():
    """C11 on the server path: 13372006463's one-wedge box 37.2 x 2 x 1 in (25 mm high) on a set's page; the three
    sides go to the default together (box_not_whole), never 945 x 51 mm beside a default height."""
    specs = {"category": {"id": "50002783"}, "name": "웨지 세트 52 56 60", "options": {"variants": []},
             "measures": {"is_set": True, "weights": [], "dimensions": [
                 {"values": [944.88, 50.8, 25.4], "kind": "packed", "quote": "- Item Package Dimensions L x W x H : "
                  "37.2 x 2 x 1 inches", "source": "description", "locator": {}, "binding": PRODUCT, "flags": []}]}}
    [v] = variant_measures(specs, load_table())
    assert [(v["fields"][n]["central"], v["fields"][n]["reason"]) for n in FIELDS[2:]] == \
        [(980, "box_not_whole"), (200, "box_not_whole"), (100, "implausible_for_category")]


# ---- D1 (2026-11-17, the resend review): a weight the listing states once, against the variant's count ----------

def test_count_kind_and_band():
    """A stated weight of n wedges is plausible from n x 380 g (compose_by_count item_g.min) to the count kind's
    high, or n + 1 clubs' lowest when more: two 760-1140 / 760-2200 (Yamato's 2-packs state 1.11 and 1.13 kg),
    three (the base row) 1140-2800 / 1140-3800, four+ 1520-2800 / 1520-3600."""
    from package_measures import count_band, count_kind
    two, four, single = (next(k for k in WEDGES["kinds"] if k["kind"] == n)
                         for n in ("two_wedges", "four_plus", "single_club"))
    assert count_band(WEDGES, count_kind(WEDGES, two, "50 56 Degree")) == {
        "product_weight_g": (760, 1140), "package_weight_g": (760, 2200)}
    assert count_band(WEDGES, count_kind(WEDGES, None, "50 54 58 Degree Set")) == {
        "product_weight_g": (1140, 2800), "package_weight_g": (1140, 3800)}
    assert count_kind(WEDGES, four, "4개 세트")[0] == 4 and count_kind(WEDGES, four, "48 52 56 60 64")[0] == 5
    assert count_kind(WEDGES, None, "3PCS") == (3, None)
    # the base row's count not named (a colour, a shaft, a title's lofts): no band; a single club: none
    assert count_kind(WEDGES, None, "Black") is None and count_kind(WEDGES, None, "") is None
    assert count_kind(WEDGES, single, "52도 단품") is None
    other = next(r for r in load_table()["rows"] if r["category_id"] == "50002788")
    assert count_kind(other, None, "52 56 60") is None


def test_off_count_puts_a_product_scope_weight_back():
    """The server's product-scope weight outside the count's band goes back to the default; one bound to the variant
    stays (13312228253's "Item Weight: 4 Pounds" is the 3-piece's 1814 g: on a pair it would be refused)."""
    from package_measures import off_count
    stated = {"value": {"min": 1814, "max": 1814}, "source": "source_stated", "confidence": 4, "kind": "unknown",
              "quote": "Item Weight: 4 Pounds", "from": "description_table", "binding": {"scope": "product"}}
    two = next(k for k in WEDGES["kinds"] if k["kind"] == "two_wedges")
    band = {"product_weight_g": (760, 1140)}
    out, back = off_count({"product_weight_g": stated}, band, WEDGES, two, 7)
    assert back == ["product_weight_g"] and out["product_weight_g"]["central"] == 920
    assert out["product_weight_g"]["kind"] == "two_wedges"
    assert out["product_weight_g"]["compared"]["rejected"] == "implausible_for_count"
    bound = {**stated, "binding": {"scope": "variants", "variant_ids": ["1"]}}
    assert off_count({"product_weight_g": bound}, band, WEDGES, two, 7) == ({"product_weight_g": bound}, [])
