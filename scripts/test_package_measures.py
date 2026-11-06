"""Offline tests for the five shipping fields (package_measures.py). The table row here is a test row, not the
operator's values; the committed category_measures.json holds the operator's (50002788, checked here too).

    .venv/bin/python -m pytest scripts/test_package_measures.py -q
"""
import copy

import pytest

from package_measures import (FIELDS, CategoryDefaultsInvalid, CategoryDefaultsMissing, check_row, load_table,
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
    assert f["package_weight_g"] == {"low": 1, "central": 2, "high": 3, "source": "category_default",
                                     "reliability": "estimated_average", "table_version": 7, "approved_by": "test", "approved_at": "2026-11-05"}


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
