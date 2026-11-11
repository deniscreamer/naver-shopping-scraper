"""Offline tests for delivery_tariff.py: the recorded tariff against the capture it was made from, no network.

    .venv/bin/python -m pytest scripts/test_delivery_tariff.py -q
"""
import copy
import json
import os
from decimal import Decimal

import pytest

import delivery_tariff as DT
from delivery_tariff import Box

HERE = os.path.dirname(os.path.abspath(__file__))
TARIFFS = DT.load()
FEDEX = TARIFFS.tariffs["shopnship-fedex-ip-kr-us"]
with open(os.path.join(HERE, FEDEX.row["source"]), encoding="utf-8") as f:
    CAPTURE = json.load(f)


def cost(*box, **kw):
    return DT.box_cost(FEDEX, Box(*box), **{"krw_per_usd": 1000, **kw})


def test_the_shop_has_its_tariff_and_another_shop_has_none():
    assert FEDEX.id == "shopnship-fedex-ip-kr-us" and TARIFFS.for_shop("another") is None
    assert FEDEX.describe() == {"tariff": FEDEX.id, "checked_at": "2026-11-11", "currency": "USD",
                                "version": TARIFFS.version, "sha256": FEDEX.sha256}
    assert len(FEDEX.sha256) == 16 and DT.Tariff(FEDEX.id, {**FEDEX.row, "divisor": 6000}).sha256 != FEDEX.sha256
    assert set(TARIFFS.shops) <= {"fairwardgolf", "skinsli", "kyobooks", "banafish"}       # shop_stores.StoreId


def test_every_captured_answer_is_the_calculators_base():
    """All the capture's rows, each box through the calculator: the base is what ShopNShip answered for FedEx,
    and where it offered no FedEx (over 50 kg) there is no price."""
    assert len(CAPTURE["requests"]) == 198 and not [r for r in CAPTURE["requests"] if "error" in r]
    for r in CAPTURE["requests"]:
        ours = cost(r["length"], r["width"], r["height"], r["weight"])
        theirs = r["usd"]["fedex"]
        assert ours["base_usd"] == theirs, (r, ours)
        assert ours["status"] == ("table" if theirs else "needs_quote")


@pytest.mark.parametrize("name, modelled", [("shopnship-explore-us-20261111T073632Z.json", 252),
                                            ("shopnship-explore-us-20261111T075720Z.json", 115)])
def test_the_wide_explorations_are_the_calculators_base_too(name, modelled):
    """Boxes chosen to cross every line we know of (length, second side, girth, volume, the steps' borders by
    gross and by volume, golf-length boxes with a fraction in a side): the base is the calculator's FedEx answer.
    Left out: forms the client never sends (a missing or zero side, a comma, pounds and inches, another
    country) and one weight written with 17 digits, which the server reads as a binary number."""
    with open(os.path.join(HERE, "fixtures", "shopnship", name), encoding="utf-8") as f:
        explored = json.load(f)
    if explored["started_at"][:10] != FEDEX.row["checked_at"]:
        pytest.skip("the tariff was captured on another day: the exploration answers its own day's table")
    asked = explored["requests"]
    seen = 0
    for r in asked:
        form = r["form"]
        if form["danwe"] != "1" or form["country"] != "US" or form["weight"] == "2.0049999999999999":
            continue
        try:
            ours = cost(form.get("length"), form.get("width"), form.get("height"), form["weight"])
        except ValueError:
            continue
        assert ours["base_usd"] == r["usd"]["fedex"], (form, ours)
        seen += 1
    assert seen == modelled


def test_the_table_is_the_captures_steps():
    table = FEDEX.table
    assert len(table) == 71 and min(table) == Decimal("0.5") and max(table) == Decimal("50")
    assert table[Decimal("0.5")] == Decimal("42.49") and table[Decimal("20")] == Decimal("296.04")
    assert Decimal("20.5") in table and Decimal("21.5") not in table        # whole kilograms from 21 kg


@pytest.mark.parametrize("box, volumetric, step, base", [                  # the owner's packing examples
    ((16, 12, 8, "0.35"), "0.31", "0.5", "42.49"), ((22, 16, 12, "0.9"), "0.84", "1", "48.51"),
    ((28, 22, 17, "1.5"), "2.09", "2.5", "67.07"), ((25, 16, 13, "1.25"), "1.04", "1.5", "58.10"),
    ((30, 22, 16, "2.45"), "2.11", "2.5", "67.07"), ((28, 22, 8, "0.5"), "0.99", "1", "48.51"),
    ((35, 27, 12, "1.1"), "2.27", "2.5", "67.07"), ((115, 12, 12, "1.5"), "3.31", "3.5", "81.92"),
    ((110, 25, 22, "5"), "12.10", "12.5", "197.92"), ((125, 35, 35, "12"), "30.63", "31", "523.48"),
    ((135, 40, 35, "15"), "37.80", "38", "623.44")])
def test_the_owners_examples(box, volumetric, step, base):
    c = cost(*box)
    assert (c["volumetric_kg"], c["step_kg"], c["base_usd"]) == (volumetric, step, base)


@pytest.mark.parametrize("weight, step", [
    ("0.1", "0.5"), ("0.5", "0.5"), ("0.51", "1"), ("2.004", "2"), ("2.005", "2.5"), ("2.5", "2.5"), ("2.501", "2.5"),
    ("20.004", "20"), ("20.006", "20.5"), ("20.5", "20.5"), ("20.51", "21"), ("21.01", "22"), ("50", "50")])
def test_the_weight_is_rounded_to_hundredths_and_then_up_to_the_step(weight, step):
    assert cost(10, 10, 10, weight)["step_kg"] == step


def test_the_larger_of_gross_and_volumetric_pays_and_sides_are_not_rounded():
    assert cost(124, 20, 16, 6)["billable_kg"] == "7.94" and cost(124, 20, 16, 9)["billable_kg"] == "9.00"
    assert cost(100, 20, "12.4", 1)["step_kg"] == "5" and cost(100, 20, "12.6", 1)["step_kg"] == "5.5"
    assert cost(16, 124, 20, 6) == cost(124, 20, 16, 6)                    # the order of the sides does not matter


def test_over_the_table_nothing_is_extrapolated():
    c = cost(100, 60, 50, 20)                                              # 60 kg volumetric
    assert (c["status"], c["step_kg"], c["base_usd"], c["total_usd"]) == ("needs_quote", None, None, None)
    c = cost(100, 60, 50, 20, fresh=lambda box: Decimal("999.00"))
    assert (c["status"], c["base_usd"], c["total_usd"]) == ("quote", "999.00", "1034.60")
    assert cost(100, 60, 50, 20, fresh=lambda box: None)["status"] == "needs_quote"
    assert cost(10, 10, 10, 6, fresh=lambda box: 1 / 0)["status"] == "table"       # a table row asks nobody
    assert cost(100, 60, 50, 20, fresh=lambda box: 999)["base_usd"] == "999.00"    # cents, whatever came
    assert cost(100, 60, 50, 20, fresh=lambda box: "812.5")["total_usd"] == "848.10"
    for bad in (0, -5, Decimal("NaN"), Decimal("Infinity"), False, "x"):           # never a price out of these
        with pytest.raises(ValueError, match="fresh quote"):
            cost(100, 60, 50, 20, fresh=lambda box, bad=bad: bad)


def test_the_last_step_and_just_over_it():
    assert cost(100, 50, 50, 1)["step_kg"] == "50" and cost(10, 10, 10, "50.004")["base_usd"] == "809.67"
    assert cost(10, 10, 10, "50.006")["status"] == "needs_quote" and cost(100, 50, "50.1", 1)["base_usd"] is None


@pytest.mark.parametrize("box, because", [
    ((121, 20, 16, 6), []),                                                # on the line: not over it
    ((121.1, 20, 16, 6), ["longest_cm_over"]),
    ((100, 76, 5, 6), []), ((100, 76.5, 5, 6), ["second_cm_over"]),
    ((121, 60, 12.5, 6), []),                                              # 121 + 120 + 25 = 266
    ((121, 60, 13, 6), ["length_girth_cm_over"]),                          # 267, 18.9 kg: the line is added
    ((88, 44, 43.5, 6), [])])                                              # 168,432 cm3, length and girth 263
def test_the_long_box_fee_once_per_box_when_one_line_is_crossed(box, because):
    lines = cost(*box)["surcharges"]
    if not because:
        assert lines == []
        return
    assert len(lines) == 1 and lines[0]["because"] == because
    assert (lines[0]["amount"], lines[0]["currency"], lines[0]["usd"]) == ("35600", "KRW", "35.60")


@pytest.mark.parametrize("box, step", [
    ((88, 44, 44, 6), "35"),                                               # over the volume line, 34.07 kg
    ((123, 40, 32, 10), "32"),                                             # a set with a bag: two lines crossed
    ((121, 40, 33, 6), "32")])                                             # over the girth line, 31.94 kg
def test_over_25_kg_the_fee_is_inside_the_base_and_not_added_again(box, step):
    c = cost(*box)
    assert c["step_kg"] == step and c["surcharges"] == [] and c["total_usd"] == c["base_usd"]
    assert c["included"] == {"id": "fedex_ahs_dimension", "usd": "32.36"}
    assert cost(100, 50, 50, 1)["included"] == {"id": "fedex_ahs_dimension", "usd": "32.36"}    # inside without a line
    assert cost(100, 50, 25, 1)["included"] is None and cost(100, 50, "25.01", 1)["included"]   # 25.00 / 25.01 kg


def test_the_minimum_billable_weight_is_a_switch_off_today():
    assert FEDEX.row["surcharges"][0]["min_billable_kg"] is None
    assert cost(124, 20, 16, 6)["step_kg"] == "8"
    row = _row()
    row["surcharges"][0]["min_billable_kg"] = 18
    on = DT.Tariff(row["id"], row)
    c = DT.box_cost(on, Box(124, 20, 16, 6), krw_per_usd=1000)
    assert (c["billable_kg"], c["step_kg"], c["base_usd"], c["total_usd"]) == ("18.00", "18", "274.74", "310.34")
    assert DT.box_cost(on, Box(121, 20, 16, 6), krw_per_usd=1000)["step_kg"] == "8"     # no fee: no minimum
    assert DT.box_cost(on, Box(123, 40, 32, 10), krw_per_usd=1000)["step_kg"] == "32"   # already over it
    for bad in (0, "x", True):
        row["surcharges"][0]["min_billable_kg"] = bad
        with pytest.raises(DT.TariffError, match="min_billable_kg"):
            DT.check(row)


def test_the_fee_is_a_line_of_its_own_at_the_callers_rate():
    c = cost(124, 20, 16, 6)
    assert (c["base_usd"], c["total_usd"]) == ("136.12", "171.72")
    assert cost(124, 20, 16, 6, krw_per_usd=1335)["surcharges"][0]["usd"] == "26.67"       # up to the cent
    with pytest.raises(DT.RateMissing, match="35600 KRW"):
        DT.box_cost(FEDEX, Box(124, 20, 16, 6))
    with pytest.raises(DT.RateMissing):                                    # also where there is no base price
        DT.box_cost(FEDEX, Box(130, 60, 50, 20))
    assert DT.box_cost(FEDEX, Box(100, 20, 16, 6))["total_usd"] == "119.31"                # no fee: no rate needed
    for bad in (0, -5, "abc", True, float("inf")):                         # a given rate is checked on every box
        with pytest.raises(ValueError, match="krw_per_usd"):
            DT.box_cost(FEDEX, Box(100, 20, 16, 6), krw_per_usd=bad)


def test_the_answer_is_plain_numbers_and_cents():
    c = cost("124.0", 20, 16.0, "6.50")
    assert (c["box_cm"], c["gross_kg"], c["volumetric_kg"], c["billable_kg"]) == (["124", "20", "16"], "6.5", "7.94", "7.94")
    assert (c["tariff"], c["checked_at"], c["currency"], c["version"]) == (FEDEX.id, "2026-11-11", "USD", TARIFFS.version)
    assert cost(Decimal("1E+2"), 20, 16, 6)["box_cm"][0] == "100"
    own = _row()
    own["surcharges"][0].update(amount="26.555", currency="USD")
    assert DT.box_cost(DT.Tariff(own["id"], own), Box(124, 20, 16, 6))["surcharges"][0]["usd"] == "26.56"


def test_a_box_from_the_projects_package_fields():
    assert DT.box_cost(FEDEX, Box.of_package(1240, 200, 160, 6000), krw_per_usd=1000) == cost(124, 20, 16, 6)
    assert Box.of_package(1205, 200, 160, 5421).sides()[0] == Decimal("120.5")
    assert cost(0.1 + 0.2, 10, 10, 2.005)["step_kg"] == "2.5"              # a float is read at its repr
    assert cost(1.1 * 110, 20, 16, 6)["surcharges"]                        # ...so float arithmetic can cross a line


def test_several_boxes_are_priced_one_by_one_and_added():
    s = DT.shipment_cost(FEDEX, (b for b in [Box(124, 20, 16, 6), Box(123, 40, 32, 10)]), krw_per_usd=1000)
    assert s["total_usd"] == "711.61" and [b["total_usd"] for b in s["boxes"]] == ["171.72", "539.89"]
    assert DT.shipment_cost(FEDEX, [Box(124, 20, 16, 6), Box(100, 60, 50, 20)], krw_per_usd=1000)["total_usd"] is None
    with pytest.raises(ValueError, match="no box"):
        DT.shipment_cost(FEDEX, [])


@pytest.mark.parametrize("box", [(0, 20, 16, 6), (124, -1, 16, 6), (124, 20, "x", 6), (124, 20, 16, 0),
                                 (124, 20, 16, "nan"), (124, 20, 16, "inf")])
def test_a_box_needs_positive_numbers(box):
    with pytest.raises(ValueError):
        cost(*box)


def _row(**change):
    row = copy.deepcopy(FEDEX.row)
    row.update(change)
    return row


@pytest.mark.parametrize("change, message", [
    ({"table": {}}, "table is missing"), ({"checked_at": ""}, "checked_at is missing"),
    ({"approved_by": None}, "approved_by is missing"), ({"divisor": 0}, "divisor must be"),
    ({"divisor": "inf"}, "divisor must be"), ({"currency": "KRW"}, "currency must be USD"),
    ({"weight_round": "0.5"}, "weight_round must be one of"), ({"weight_round": "1E+1"}, "weight_round must be"),
    ({"table": [1, 2]}, "must be an object"),
    ({"table": {"1": "10", "2": "9"}}, "must cost more"), ({"table": {"1": "10", "1.0": "11"}}, "different positive"),
    ({"table": {"1": "x"}}, "different positive"), ({"table": {"1": True}}, "different positive"),
    ({"table": {"1": "10", "2": "inf"}}, "different positive"), ({"table": {"nan": "10"}}, "different positive"),
    ({"surcharges": {"id": "a"}}, "must be a list")])
def test_a_bad_tariff_row_is_refused(change, message):
    with pytest.raises(DT.TariffError, match=message):
        DT.check(_row(**change))


@pytest.mark.parametrize("change, message", [
    ({"per": "shipment"}, "per: box"), ({"amount": "inf"}, "positive amount"), ({"amount": 0}, "positive amount"),
    ({"currency": "JPY"}, "USD or KRW"), ({"currency": "krw"}, "USD or KRW"),
    ({"any_of": {"weight_over": 1}}, "any_of takes"), ({"any_of": ["longest_cm_over"]}, "any_of takes"),
    ({"any_of": {}}, "any_of takes"), ({"any_of": {"longest_cm_over": "abc"}}, "positive number"),
    ({"any_of": {"longest_cm_over": 0}}, "positive number"), ({"any_of": {"longest_cm_over": None}}, "positive number"),
    ({"any_of": {"longest_cm_over": True}}, "positive number"), ({"id": ""}, "id of its own")])
def test_a_bad_surcharge_is_refused(change, message):
    row = _row()
    row["surcharges"][0].update(change)
    with pytest.raises(DT.TariffError, match=message):
        DT.check(row)


@pytest.mark.parametrize("inside", [{"id": "other", "over_step_kg": 25, "usd": "32.36"},
                                    {"id": "fedex_ahs_dimension", "over_step_kg": 0, "usd": "32.36"},
                                    {"id": "fedex_ahs_dimension", "over_step_kg": 25, "usd": "x"}, ["x"]])
def test_a_bad_included_surcharge_is_refused(inside):
    with pytest.raises(DT.TariffError, match="included_surcharge"):
        DT.check(_row(included_surcharge=inside))


def test_the_history_names_this_version(tmp_path):
    assert TARIFFS.version == 1
    path = tmp_path / "t.json"
    for history, message in (([{"version": 2, "date": "2026-12-01", "change": "x"}], "last history row"),
                             ([{"version": 1}], "history must be"), ({"version": 1}, "history must be")):
        path.write_text(json.dumps({"version": 1, "history": history, "tariffs": [FEDEX.row], "shops": {}}),
                        encoding="utf-8")
        with pytest.raises(DT.TariffError, match=message):
            DT.load(str(path))


def test_a_surcharge_written_twice_is_refused():
    row = _row()
    row["surcharges"].append(copy.deepcopy(row["surcharges"][0]))
    with pytest.raises(DT.TariffError, match="id of its own"):
        DT.check(row)
    with pytest.raises(DT.TariffError, match="must be an object"):
        DT.check(None)


def test_a_json_number_in_the_table_is_read_as_written():
    row = _row(table={"0.5": 42.49, "1": 48.51})
    DT.check(row)
    assert DT.box_cost(DT.Tariff(row["id"], row), Box(10, 10, 10, "0.3"))["base_usd"] == "42.49"


@pytest.mark.parametrize("text, message", [
    (lambda row: {"version": 1, "tariffs": [row, row], "shops": {}}, "twice"),
    (lambda row: {"version": 1, "tariffs": [row], "shops": {"x": "nothing"}}, "no tariff"),
    (lambda row: {"version": 1, "tariffs": [row]}, "shops must be an object"),
    (lambda row: {"version": 1, "tariffs": [row], "shop": {}}, "shops must be an object"),
    (lambda row: {"version": 1, "tariffs": [row], "shops": None}, "shops must be an object"),
    (lambda row: {"version": 1, "tariffs": [row], "shops": ["x"]}, "shops must be an object"),
    (lambda row: {"tariffs": [row], "shops": {}}, "version must be"),
    (lambda row: {"version": True, "tariffs": [row], "shops": {}}, "version must be"),
    (lambda row: {"version": "1", "tariffs": [row], "shops": {}}, "version must be"),
    (lambda row: {"version": 0, "tariffs": [row], "shops": {}}, "version must be"),
    (lambda row: {"version": 1, "tariffs": [], "shops": {}}, "at least one tariff"),
    (lambda row: {"version": 1, "tariffs": {"a": row}, "shops": {}}, "at least one tariff"),
    (lambda row: {"version": 1, "tariffs": [None], "shops": {}}, "must be an object"),
    (lambda row: {"version": 1, "tariffs": [{**row, "divisor": 0}], "shops": {}}, "divisor must be"),
    (lambda row: [row], "must be an object")])
def test_a_bad_tariffs_file_is_refused_on_load(tmp_path, text, message):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(text(FEDEX.row)), encoding="utf-8")
    with pytest.raises(DT.TariffError, match=message):
        DT.load(str(path))


def test_a_key_written_twice_or_broken_json_is_refused(tmp_path):
    path = tmp_path / "t.json"
    path.write_text('{"version": 1, "version": 2, "tariffs": [], "shops": {}}', encoding="utf-8")
    with pytest.raises(DT.TariffError, match="written twice"):
        DT.load(str(path))
    path.write_text("{", encoding="utf-8")
    with pytest.raises(DT.TariffError, match="not JSON"):
        DT.load(str(path))


def test_the_fingerprint_moves_with_a_price_not_with_a_note():
    note = copy.deepcopy(FEDEX.row)
    note["table_note"] += " (reworded)"
    note["surcharges"][0]["min_billable_note"] = "x"
    note["included_surcharge"]["why"] = "x"
    assert DT.Tariff(FEDEX.id, note).sha256 == FEDEX.sha256
    for change in ({"divisor": 6000}, {"table": {**FEDEX.row["table"], "8": "136.13"}}):
        assert DT.Tariff(FEDEX.id, {**FEDEX.row, **change}).sha256 != FEDEX.sha256
    switch = copy.deepcopy(FEDEX.row)
    switch["surcharges"][0]["min_billable_kg"] = 18
    inside = copy.deepcopy(FEDEX.row)
    inside["included_surcharge"]["usd"] = "32.37"
    assert len({FEDEX.sha256, DT.Tariff(FEDEX.id, switch).sha256, DT.Tariff(FEDEX.id, inside).sha256}) == 3
