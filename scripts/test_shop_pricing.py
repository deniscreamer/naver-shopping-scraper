"""The price rule of a shop that sells with delivery inside the price (shop_pricing.py, the owner's decisions of
2026-11-11): regression fixtures cut from real products, then the rule's pieces on small hand-made inputs.

fixtures/pricing/<product id>.json, one real fairwardgolf product each (prepared/products.jsonl of 2026-11-11):
  key       the prepared record's key
  why       the case the product is here for, one line
  product   {"delivery": {"fee_type", "base_fee"}}: the seller's delivery in Korea, as the listing says it
  variants  [{"sku", "price_krw", "package": {the five package fields, each cut to confidence, source and the
            category default's central or the seller's value}}]: every variant of a small product, at most 6
  expected  [{"sku", "cost", "price", "breakdown"}]: Shopify's cost per item, the price, and how they were made
            (the variant's fairwardgolf.price metafield without its schemaVersion)

The inputs were cut once by cut() below from the prepared lines; the expected part is what the rule computes, crossed
on 2026-11-11 with a recomputation of the owner's formula written apart from shop_pricing.py. A deliberate change
of the rule, of one of its numbers or of the tariff (its id, day and version are in every breakdown) shows here as a
failure that names the product, the variant and the part. Rewrite the expected part with
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_shop_pricing.py
and read the diff of fixtures/pricing/ before committing (R-TEST-5). A new product: write(name, cut(its prepared
line, why)), then the same command."""
import json
import os
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

import shop_pricing
from shop_pricing import FAIRWARDGOLF, SIDES, Policy, PriceError, Quote, package_number, policy, pretty

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pricing")
NAMES = sorted(n[:-5] for n in os.listdir(FIXTURES) if n.endswith(".json")) if os.path.isdir(FIXTURES) else []
PACKAGE = SIDES + ("package_weight_g", "product_weight_g")
CUT = ("confidence", "source")                  # with the central or the value: what the rule reads of a field
MAX_VARIANTS = 6
RULE = FAIRWARDGOLF
SHOP = shop_pricing.POLICIES["fairwardgolf"]


# ---- the fixtures ---------------------------------------------------------------------------------------------

def cut(record: dict[str, Any], why: str, skus: list[str] | None = None) -> dict[str, Any]:
    """A fixture from a prepared line: the delivery's type and fee, each variant's KRW price and its five package
    fields cut to the keys the rule reads. `skus` picks the variants that make the case (at most 6)."""
    product = record["product"]
    delivery = product.get("delivery") or {}

    def field(f: dict[str, Any]) -> dict[str, Any]:
        number = {"central": f["central"]} if f.get("central") is not None else {"value": f.get("value")}
        return {**{k: f[k] for k in CUT if k in f}, **number}

    picked = [v for v in product["variants"] if skus is None or v["sku"] in skus][:MAX_VARIANTS]
    return {"key": record["key"], "why": why,
            "product": {"delivery": {"fee_type": delivery.get("fee_type"), "base_fee": delivery.get("base_fee")}},
            "variants": [{"sku": v["sku"], "price_krw": v["price_krw"],
                          "package": {n: field(v["package"][n]) for n in PACKAGE if n in (v.get("package") or {})}}
                         for v in picked],
            "expected": []}


def priced(fixture: dict[str, Any], shop: Policy = SHOP) -> list[dict[str, Any]]:
    """Each variant's cost, price and breakdown as the rule gives them, through JSON as the metafield carries
    them (a number the payload could not send fails here)."""
    out = []
    for v in fixture["variants"]:
        q = shop.quote(v, fixture["product"])
        out.append({"sku": v["sku"], "cost": str(q.cost), "price": q.price, "breakdown": q.breakdown})
    return json.loads(json.dumps(out, ensure_ascii=False))


def dumps(o: Any, pad: str = "") -> str:
    """JSON a person reads and diffs: what fits on a line stays on one, a breakdown has a line per part."""
    flat = json.dumps(o, ensure_ascii=False)
    if not isinstance(o, (dict, list)) or len(pad) + len(flat) <= 110:
        return flat
    inner = pad + " "
    items = [f"{json.dumps(k, ensure_ascii=False)}: {dumps(v, inner)}" for k, v in o.items()] \
        if isinstance(o, dict) else [dumps(v, inner) for v in o]
    return ("{" if isinstance(o, dict) else "[") + "\n" + inner + (",\n" + inner).join(items) + "\n" + pad + \
        ("}" if isinstance(o, dict) else "]")


def load(name: str) -> dict[str, Any]:
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def write(name: str, fixture: dict[str, Any]) -> None:
    os.makedirs(FIXTURES, exist_ok=True)
    with open(os.path.join(FIXTURES, name + ".json"), "w", encoding="utf-8") as f:
        f.write(dumps(fixture) + "\n")


def differences(got: dict[str, Any], want: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    out = [(k, got[k], want.get(k)) for k in ("cost", "price") if got[k] != want.get(k)]
    g, w = got["breakdown"] or {}, want.get("breakdown") or {}
    return out + [(f"breakdown.{k}", g.get(k), w.get(k)) for k in [*g, *(k for k in w if k not in g)]
                  if g.get(k) != w.get(k)]


@pytest.mark.parametrize("name", NAMES)
def test_fixture_prices_as_pinned(name):
    fixture = load(name)
    got = priced(fixture)
    if os.environ.get("UPDATE_GOLDEN"):
        fixture["expected"] = got
        write(name, fixture)
    pinned = {e["sku"]: e for e in fixture["expected"]}
    assert list(pinned) == [v["sku"] for v in fixture["variants"]], f"{name}: every variant needs its expected prices"
    wrong = [f"{name} {e['sku']} {part}:\n   got    {json.dumps(g, ensure_ascii=False)}\n"
             f"   pinned {json.dumps(w, ensure_ascii=False)}"
             for e in got for part, g, w in differences(e, pinned[e["sku"]])]
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_parts_add_up_and_the_surplus_is_under_one_step(name):
    """cost + duty + delivery + fee = base; base + margin = keep; price - 3 % of it - keep = the surplus, never negative and
    under one step of the pretty numbers (10 under 1000, 100 from 1000)."""
    for e in priced(load(name)):
        b = e["breakdown"]

        def d(k: str) -> Decimal:
            return Decimal(b[k])
        assert e["cost"] == b["costUsd"] and e["price"] == b["priceUsd"]
        assert d("costUsd") == b["purchaseUsd"] + d("serviceUsd")                 # the duty is not in the cost
        assert d("costUsd") + d("dutyUsd") + d("deliveryUsd") + d("feeUsd") == d("baseUsd")      # but in the base
        assert d("baseUsd") + d("marginUsd") == d("keepUsd")
        assert d("paymentUsd") == (e["price"] * Decimal("0.03")).quantize(Decimal("0.01"))
        assert e["price"] - d("paymentUsd") - d("keepUsd") == d("surplusUsd")
        step = 10 if e["price"] < 1000 else 100
        assert 0 <= d("surplusUsd") < step and e["price"] % step == step - 1, (name, e["sku"])


def test_fixtures_in_a_shop_without_the_rule_cost_their_krw():
    """Policy(): the cost and the price are the Naver price at 1000 KRW = 1 USD up to a dollar, no breakdown (the
    delivery in Korea is not added there)."""
    assert NAMES
    for name in NAMES:
        fixture = load(name)
        for v, e in zip(fixture["variants"], priced(fixture, Policy())):
            usd = -(-v["price_krw"] // 1000)
            assert (e["cost"], e["price"], e["breakdown"]) == (str(usd), usd, None), (name, v["sku"])


def test_fixtures_cover_the_cases_and_hold_only_what_the_rule_reads():
    fixtures = [load(n) for n in NAMES]
    seen = [(f, e["breakdown"]) for f in fixtures for e in f["expected"]]
    assert {b["level"] for _, b in seen} >= {1, 2, 4, 5}
    assert {b["koreaFeeType"] for _, b in seen} >= {"PAID", "UNIT_QUANTITY_PAID", "CONDITIONAL_FREE", "FREE"}
    assert any(b["insideUsd"] != "0.00" and b["feeUsd"] == "0.00" for _, b in seen)       # the fee in the grid
    assert any(b["feeUsd"] != "0.00" for _, b in seen)                                     # the fee added
    assert any(b["insideUsd"] == b["feeUsd"] == "0.00" for _, b in seen)                   # no fee at all
    assert {b["box"]["stepKg"] for _, b in seen if b["level"] == 1} >= {"16", "16.5"}
    assert any(b["priceUsd"] < 1000 for _, b in seen) and any(b["priceUsd"] >= 1000 for _, b in seen)
    assert any(len({b["box"]["grossKg"] for g, b in seen if g is f}) > 1 for f in fixtures)  # two boxes in one
    for name, f in zip(NAMES, fixtures):
        assert set(f) == {"key", "why", "product", "variants", "expected"} and "\n" not in f["why"]
        assert set(f["product"]) == {"delivery"} and set(f["product"]["delivery"]) == {"fee_type", "base_fee"}
        assert 0 < len(f["variants"]) <= MAX_VARIANTS and f["key"].endswith(":" + name)
        for v in f["variants"]:
            assert set(v["package"]) == set(PACKAGE)
            assert all(set(field) <= {*CUT, "central", "value"} for field in v["package"].values())


# ---- the rule's pieces, on hand-made inputs ----------------------------------------------------------------------

FREE = {"delivery": {"fee_type": "FREE", "base_fee": 0}}


def field(n: Any, level: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {"source": "test", "value": n}
    if level is not None:
        out["confidence"] = level
    return out


Level = int | None


def variant(krw: int = 100_000, mm: tuple[Any, Any, Any] = (300, 200, 100), g: Any = 1000,
            levels: tuple[Level, Level, Level] = (5, 5, 5), weight_level: Level = 5) -> dict[str, Any]:
    """A variant whose box is 30 x 20 x 10 cm, 1 kg by default: billable 1.20 kg, the 1.5 kg step, 58.10 USD."""
    package = {name: field(n, level) for name, n, level in zip(SIDES, mm, levels)}
    package["package_weight_g"] = field(g, weight_level)
    return {"sku": "FW-test", "price_krw": krw, "package": package}


def quote(v: dict[str, Any] | None = None, product: dict[str, Any] | None = None, rule: Any = RULE) -> Quote:
    return Policy(delivered=rule).quote(v if v is not None else variant(), FREE if product is None else product)


def breakdown(v: dict[str, Any] | None = None, product: dict[str, Any] | None = None) -> dict[str, Any]:
    b = quote(v, product).breakdown
    assert b is not None
    return b


def test_the_rule_holds_the_owners_numbers():
    assert policy("fairwardgolf") is SHOP and SHOP.delivered is RULE and SHOP.krw_per_usd == 1000
    assert RULE.tariff == "shopnship-fedex-ip-kr-us" and RULE.service_usd == 3 and RULE.duty_rate == Decimal("0.125")
    assert {k: str(v) for k, v in RULE.coefficients.items()} == {5: "1.00", 4: "1.10", 3: "1.20", 2: "1.40", 1: "2.50"}
    assert (RULE.margin_fixed, RULE.margin_rate, RULE.margin_min) == (Decimal(25), Decimal("0.11"), Decimal(30))
    assert RULE.payment_rate == Decimal("0.03") and RULE.korea_paid == ("PAID", "UNIT_QUANTITY_PAID")


def test_one_variant_end_to_end_by_hand():
    """100 000 KRW, free delivery in Korea, a 30 x 20 x 10 cm box of 1 kg stated by the seller (level 5):
    purchase 100; cost 103.00; duty 12.50 apart; billable max(1, 6000 / 5000) = 1.20 kg -> the 1.5 kg step,
    58.10 x 1.00; no fee; base 103 + 12.50 + 58.10 = 173.60; margin 25 + 11 % of it = 44.10; keep 217.70;
    / 0.97 = 224.43 -> 229; 3 % of 229 = 6.87; surplus 229 - 6.87 - 217.70 = 4.43."""
    q = quote()
    assert (q.cost, q.price) == (Decimal("103.00"), 229)
    b = q.breakdown
    assert b is not None
    assert {k: b[k] for k in ("naverKrw", "koreaDeliveryKrw", "purchaseUsd", "serviceUsd", "dutyUsd", "costUsd")} == {
        "naverKrw": 100_000, "koreaDeliveryKrw": 0, "purchaseUsd": 100, "serviceUsd": "3.00", "dutyUsd": "12.50",
        "costUsd": "103.00"}
    assert b["box"] == {"cm": ["30", "20", "10"], "grossKg": "1", "billableKg": "1.20", "stepKg": "1.5"}
    assert (b["level"], b["coefficient"], b["gridUsd"], b["insideUsd"], b["deliveryUsd"]) == (
        5, "1.00", "58.10", "0.00", "58.10")
    assert (b["fees"], b["feeUsd"], b["baseUsd"], b["marginUsd"], b["keepUsd"]) == ([], "0.00", "173.60", "44.10",
                                                                                     "217.70")
    assert (b["neededUsd"], b["priceUsd"], b["paymentUsd"], b["surplusUsd"]) == ("224.43", 229, "6.87", "4.43")
    assert b["rule"] == "landed/2" and b["tariff"]["id"] == RULE.tariff and b["tariff"]["version"] >= 1


@pytest.mark.parametrize("amount, want", [
    ("164", 169), ("169", 169), ("170", 179), ("901", 909), ("950", 959), ("989.5", 999), ("992", 999),
    ("999.01", 1099), ("1000", 1099), ("1000.86", 1099), ("1254", 1299), ("1299.5", 1399)])
def test_pretty_ends_in_9_under_1000_and_in_99_from_1000(amount, want):
    assert pretty(Decimal(amount)) == want


@pytest.mark.parametrize("base, margin", [
    ("0", "30"), ("10", "30"), ("45", "30"),                         # the minimum: 25 + 11 % is under 30 up to 45.45
    ("46", "30.06"), ("100", "36"), ("500", "80"), ("1000", "135"), ("1500", "190"), ("3000", "355"),
    ("5000", "575")])                                               # 25 + 11 % of the base
def test_the_margin_is_25_and_11_percent_never_under_30(base, margin):
    assert RULE.margin(Decimal(base)) == Decimal(margin)


def test_the_margin_grows_with_every_dollar_of_the_base():
    margins = [RULE.margin(Decimal(b)) for b in range(46, 6000, 7)]
    assert all(b > a for a, b in zip(margins, margins[1:]))


@pytest.mark.parametrize("delivery, korea", [
    ({"fee_type": "PAID", "base_fee": 10_000}, 10_000),
    ({"fee_type": "UNIT_QUANTITY_PAID", "base_fee": 5000}, 5000),
    ({"fee_type": "FREE", "base_fee": 3000}, 0),
    ({"fee_type": "CONDITIONAL_FREE", "base_fee": 20_000}, 0),
    ({"fee_type": "SOMETHING_NEW", "base_fee": 7000}, 0),
    ({"fee_type": None, "base_fee": 7000}, 0),
    ({"base_fee": 7000}, 0),
    ({"fee_type": "PAID", "base_fee": None}, 0),
    (None, 0)])
def test_the_delivery_in_korea_is_added_only_when_paid(delivery, korea):
    """The owner, 2026-11-11: free when it is not paid."""
    b = breakdown(product={"delivery": delivery})
    assert (b["koreaDeliveryKrw"], b["purchaseUsd"]) == (korea, 100 + korea // 1000)
    assert breakdown(product={})["koreaDeliveryKrw"] == 0


def test_the_purchase_is_the_sum_up_to_a_dollar():
    assert breakdown(variant(99_500), {"delivery": {"fee_type": "PAID", "base_fee": 500}})["purchaseUsd"] == 100
    assert breakdown(variant(100_001))["purchaseUsd"] == 101


@pytest.mark.parametrize("krw, duty", [(1000, "0.13"), (3000, "0.38"), (8000, "1.00"), (898_000, "112.25")])
def test_the_duty_is_12_5_percent_of_the_purchase_up_to_a_cent(krw, duty):
    b = breakdown(variant(krw))
    assert (b["dutyRate"], b["dutyUsd"]) == ("0.125", duty)


def test_the_duty_rounds_up():
    rule = replace(RULE, duty_rate=Decimal("0.121"))
    b = quote(variant(1000), rule=rule).breakdown
    assert b is not None and b["dutyUsd"] == "0.13"                  # 0.121: half up would give 0.12


def test_the_cost_is_the_purchase_and_the_service_and_the_duty_is_apart():
    """The Callaway Edge of 5818229550: 799 000 + 99 000 KRW. Shopify's cost per item holds no duty (the owner,
    2026-11-11); the duty is in the base the price is made from."""
    q = quote(variant(799_000), {"delivery": {"fee_type": "UNIT_QUANTITY_PAID", "base_fee": 99_000}})
    assert q.cost == Decimal("901.00") and q.breakdown is not None
    assert (q.breakdown["purchaseUsd"], q.breakdown["serviceUsd"], q.breakdown["dutyUsd"]) == (898, "3.00", "112.25")
    assert q.breakdown["costUsd"] == "901.00"
    b = q.breakdown
    assert Decimal(b["baseUsd"]) == Decimal("901.00") + Decimal("112.25") + Decimal(b["deliveryUsd"]) + Decimal(b["feeUsd"])


def test_the_level_is_the_weakest_of_the_three_sides():
    b = breakdown(variant(levels=(2, 2, 2), weight_level=1))      # a default weight does not lower the level
    assert (b["level"], b["coefficient"]) == (2, "1.40")
    assert breakdown(variant(levels=(3, 2, 4), weight_level=5))["level"] == 2
    assert breakdown(variant(levels=(5, 5, 5), weight_level=1))["level"] == 5
    assert breakdown(variant(levels=(5, None, 5)))["level"] == 1   # a side without a level counts as a default


@pytest.mark.parametrize("level, coefficient, delivery", [
    (5, "1.00", "58.10"), (4, "1.10", "63.91"), (3, "1.20", "69.72"), (2, "1.40", "81.34"), (1, "2.50", "145.25")])
def test_each_level_multiplies_the_grid_by_its_coefficient(level, coefficient, delivery):
    b = breakdown(variant(levels=(level, level, level), weight_level=level))
    assert (b["level"], b["coefficient"], b["gridUsd"], b["deliveryUsd"]) == (level, coefficient, "58.10", delivery)


def test_the_fee_is_added_once_and_never_multiplied():
    """124 x 20 x 16 cm, 7 kg (a set without its bag): billable 7.94 kg -> the 8 kg step, 136.12; longer than
    121 cm: FedEx's fee, 35.60 USD, once."""
    for level, delivery in ((5, "136.12"), (2, "190.57"), (1, "340.30")):
        b = breakdown(variant(mm=(1240, 200, 160), g=7000, levels=(level, level, level)))
        assert (b["gridUsd"], b["insideUsd"], b["deliveryUsd"], b["feeUsd"]) == ("136.12", "0.00", delivery, "35.60")
        assert [f["id"] for f in b["fees"]] == ["fedex_ahs_dimension"]
    b = breakdown(variant(mm=(1300, 800, 100)))                    # three of its lines crossed: still one fee
    assert b["feeUsd"] == "35.60" and len(b["fees"]) == 1 and len(b["fees"][0]["because"]) == 3
    b = breakdown(variant(mm=(1210, 200, 160), g=10_800))          # exactly 121 cm is not over 121 cm
    assert (b["fees"], b["feeUsd"]) == ([], "0.00")


def test_over_25_kg_the_fee_inside_the_grid_is_neither_multiplied_nor_added_again():
    """124.9 x 40 x 32 cm, 10.821 kg (a set with its bag, 11256507948): billable 31.97 kg -> the 32 kg step, 539.89,
    which holds 32.36 of the fee: (539.89 - 32.36) x coefficient + 32.36, and no fee line."""
    for level, delivery in ((5, "539.89"), (2, "742.90"), (1, "1301.19")):
        b = breakdown(variant(mm=(1249, 400, 320), g=10_821, levels=(level, level, level)))
        assert (b["box"]["stepKg"], b["gridUsd"], b["insideUsd"]) == ("32", "539.89", "32.36")
        assert (b["deliveryUsd"], b["fees"], b["feeUsd"]) == (delivery, [], "0.00")
    b = breakdown(variant(g=25_000))                               # the 25 kg step does not hold it
    assert (b["box"]["stepKg"], b["gridUsd"], b["insideUsd"]) == ("25", "392.65", "0.00")
    b = breakdown(variant(g=25_010))                               # the next one does, whatever the box
    assert (b["box"]["stepKg"], b["gridUsd"], b["insideUsd"], b["deliveryUsd"]) == ("26", "441.42", "32.36", "441.42")


def test_a_box_over_the_tariffs_last_step_has_no_price():
    assert breakdown(variant(g=50_000))["box"]["stepKg"] == "50"
    for v in (variant(g=50_010), variant(mm=(1000, 600, 500))):    # 50.01 kg; 60 kg by volume
        with pytest.raises(PriceError, match="over the tariff's last step"):
            quote(v)


def test_a_variant_without_its_box_has_no_price():
    v = variant()
    without = {"sku": v["sku"], "price_krw": v["price_krw"]}
    no_height = {**v, "package": {k: f for k, f in v["package"].items() if k != "package_height_mm"}}
    no_weight = {**v, "package": {k: f for k, f in v["package"].items() if k != "package_weight_g"}}
    for broken in (without, {**v, "package": None}, {**v, "package": {}}, no_height, no_weight):
        with pytest.raises(PriceError, match="no package box"):
            quote(broken)
    with pytest.raises(PriceError, match="the package box"):
        quote(variant(mm=(0, 200, 100)))


def test_package_number_reads_the_central_else_the_larger_end():
    assert package_number({"central": 280, "value": 999}) == 280
    assert package_number({"value": {"min": 1100, "max": 1240}}) == 1240
    assert package_number({"value": 1210.0}) == 1210.0
    assert package_number(None) is None and package_number({}) is None


def test_a_shop_without_the_rule_sells_at_the_krw_cost():
    plain = Policy()
    paid = {"delivery": {"fee_type": "PAID", "base_fee": 99_000}}
    for krw, usd in ((5560, 6), (5000, 5), (1, 1), (1_449_900, 1450)):
        q = plain.quote({"price_krw": krw}, paid)                  # no box needed, the delivery in Korea not added
        assert (q.cost, q.price, q.breakdown) == (Decimal(usd), usd, None)
    assert policy("another-shop") == plain
    assert plain.describe() == {"version": "krw-cost/1", "krwPerUsd": 1000, "rounding": "ceil-dollar", "margin": None}


def test_describe_moves_with_every_number_of_the_rule(monkeypatch):
    before = SHOP.describe()
    assert json.loads(json.dumps(before)) == before and before["version"] == "landed/2"
    assert before["margin"] == {"fixedUsd": "25.00", "rate": "0.11", "minUsd": "30.00"}
    assert Policy(delivered=replace(RULE)).describe() == before
    changed = [replace(RULE, coefficients={**RULE.coefficients, 1: Decimal("2.60")}),
               replace(RULE, coefficients={**RULE.coefficients, 5: Decimal("1.05")}),
               replace(RULE, duty_rate=Decimal("0.13")),
               replace(RULE, margin_fixed=Decimal("26")), replace(RULE, margin_rate=Decimal("0.12")),
               replace(RULE, margin_min=Decimal("35")),
               replace(RULE, service_usd=Decimal("4")), replace(RULE, payment_rate=Decimal("0.035")),
               replace(RULE, korea_paid=("PAID",))]
    assert all(Policy(delivered=r).describe() != before for r in changed)
    assert Policy(krw_per_usd=1100, delivered=RULE).describe() != before
    tariff = shop_pricing._tariff(RULE.tariff)
    monkeypatch.setattr(shop_pricing, "_tariff", lambda name: replace(tariff, version=tariff.version + 1))
    assert SHOP.describe() != before and SHOP.describe()["tariff"]["version"] == tariff.version + 1
    assert breakdown()["tariff"]["version"] == tariff.version + 1  # and every price records it


def test_the_price_is_the_first_pretty_number_not_under_keep_over_097():
    """A sweep of Naver prices on one box: the price covers keep and the 3 %, and the surplus is under one step."""
    for krw in range(1_000, 3_500_000, 7_777):
        b = quote(variant(krw=krw)).breakdown
        price, keep, needed = b["priceUsd"], Decimal(b["keepUsd"]), Decimal(b["neededUsd"])
        assert price >= keep / Decimal("0.97") and price - Decimal(b["paymentUsd"]) >= keep
        assert Decimal(b["surplusUsd"]) < (Decimal("10") if price < 1000 else Decimal("100"))
        assert pretty(needed) == price


def test_the_shops_that_carry_delivery_agree_with_the_tariffs_file():
    import delivery_tariff
    assert {shop: p.delivered.tariff for shop, p in shop_pricing.POLICIES.items() if p.delivered} == \
        delivery_tariff.load().shops


def test_an_unreadable_or_out_of_range_confidence():
    v = variant()
    v["package"]["package_width_mm"]["confidence"] = "x"
    with pytest.raises(PriceError, match="readable confidence"):
        quote(v)
    for given, level in ((-1, 1), (0, 1), (None, 1), (7, 5)):
        v = variant(levels=(given, given, given))
        assert quote(v).breakdown["level"] == level


def test_a_tariff_edit_moves_the_record_and_the_digest(monkeypatch):
    import copy
    import delivery_tariff as DT
    before = policy("fairwardgolf").describe()
    tariff = shop_pricing._tariff(RULE.tariff)
    row = copy.deepcopy(tariff.row)
    row["surcharges"][0]["min_billable_kg"] = 18          # the owner's switch, without a new version
    monkeypatch.setattr(shop_pricing, "_tariff", lambda name: DT.Tariff(tariff.id, row, tariff.version))
    after = policy("fairwardgolf").describe()
    assert after["tariff"]["version"] == before["tariff"]["version"] and after != before
    assert after["tariff"]["sha256"] != before["tariff"]["sha256"]
