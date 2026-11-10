"""Offline tests for the five shipping fields (package_measures.py). The table row here is a test row, not the
operator's values; the committed category_measures.json holds the operator's (50002788, checked here too).

    .venv/bin/python -m pytest scripts/test_package_measures.py -q
"""
import copy

import pytest

from package_measures import (BASELINE_SIDES, BASELINES, FIELDS, CategoryDefaultsInvalid, CategoryDefaultsMissing,
                              check_row, load_table, on_scale, variant_measures)

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
    assert table["version"] == 2 and set(block["basis"]) >= {*BASELINES, *BASELINE_SIDES}
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
