"""The delivery cost of a packed box by a recorded tariff: the calculator behind "delivery inside the price".

A shop that sells with free delivery has to carry the delivery in the product's price. This module answers one
question offline: what does the partner charge to carry this box (outer sides in cm, gross weight in kg)? The
tariffs are data, `delivery_tariffs.json`, given and approved by the operator and traced to a dated capture of the
partner's calculator (shopnship_rates.py); no amount is made up in code. Which shops carry delivery in the price is
shop_pricing.POLICIES; the file's `shops` map must agree with it (a test).

    from delivery_tariff import Box, load, box_cost, shipment_cost
    tariff = load().for_shop("fairwardgolf")           # None: this shop's prices carry no delivery
    cost = box_cost(tariff, Box.of_package(1240, 200, 160, 6000), krw_per_usd=1000)
    cost["base_usd"], cost["surcharges"], cost["total_usd"]

The base price (the owner's rule, 2026-11-11, checked against the capture):
  volumetric weight = L x W x H / divisor (sides as given, a fraction of a centimetre is not rounded);
  billable weight = the larger of gross and volumetric, rounded to hundredths (half up); the price is the row of
  the first weight step of the table that is not under it. The table holds every step the partner's calculator
  has (ShopNShip, FedEx to the US, 2026-11-11: 0.5 kg steps to 20.5 kg, whole kilograms from 21 to 50 kg, nothing
  over 50 kg), each one captured, none computed. Over the table's last step the answer is `needs_quote`: steps
  differ in price, so nothing is extrapolated; the caller passes `fresh` (a live quote) or holds the product.
Surcharges are lines of their own, each added once per box when one of its conditions holds. An amount in KRW
needs the caller's rate (`krw_per_usd`): the tariff does not choose it, and a box that pays such a line without a
rate raises RateMissing. A surcharge the partner's table already holds (`included_surcharge`: ShopNShip's steps
over 25 kg carry FedEx's KRW 35,600 handling fee, 32.36 USD at its own rate) is not added again on such a box: the
answer names it under `included` (the owner, 2026-11-11: the fee once per box). A surcharge's `min_billable_kg`,
when set, bills a box that pays it at that weight at least (FedEx's 18 kg; off today).
Every amount in an answer is a string with two decimals; a box's numbers are echoed as plain decimals.
Numbers are taken exactly as written: give sides and weights as int, str or Decimal (Box.of_package takes the
project's mm and g). A float is read at its repr, so arithmetic on floats before the call can move a box over a
step (1.1 * 110 is 121.00000000000001 cm: over the 121 cm line).
This is the cost at coefficient 1, for a box that is known. What a less certain box adds is the pricing rule's
business, not this module's.
"""
import hashlib
import json
import os
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
TARIFFS = os.path.join(HERE, "delivery_tariffs.json")
CENT = Decimal("0.01")
CONDITIONS = ("longest_cm_over", "second_cm_over", "length_girth_cm_over", "volume_cm3_over")
CURRENCY = "USD"                                    # an answer's amounts; a surcharge may also be in KRW
ROUNDINGS = tuple(Decimal(1).scaleb(-n) for n in range(5))        # 1, 0.1, 0.01, 0.001, 0.0001


class TariffError(Exception):
    """The tariffs file is missing something or says something impossible."""


class RateMissing(Exception):
    """A surcharge is in another currency and the caller gave no rate for it."""


def _decimal(value: Any) -> Decimal | None:
    """A positive finite number, or None: a bool, a NaN, an infinity, zero, a negative and a non-number are not."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        return None
    return number if number.is_finite() and number > 0 else None


def _positive(name: str, value: Any) -> Decimal:
    number = _decimal(value)
    if number is None:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")
    return number


def _plain(number: Decimal) -> str:
    """A decimal as people write it: no exponent, no trailing zeros ("124", "12.4")."""
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _money(number: Decimal) -> str:
    return format(number.quantize(CENT, rounding=ROUND_HALF_UP), "f")


@dataclass(frozen=True)
class Box:
    """One packed box as the carrier will measure it: outer sides in cm (any order), gross weight in kg."""
    length_cm: Any
    width_cm: Any
    height_cm: Any
    gross_kg: Any

    @classmethod
    def of_package(cls, length_mm: Any, width_mm: Any, height_mm: Any, weight_g: Any) -> "Box":
        """From the project's package fields (mm and g), exactly."""
        return cls(_positive("side", length_mm) / 10, _positive("side", width_mm) / 10,
                   _positive("side", height_mm) / 10, _positive("weight", weight_g) / 1000)

    def sides(self) -> tuple[Decimal, Decimal, Decimal]:
        """The three sides, longest first."""
        s = sorted((_positive("side", v) for v in (self.length_cm, self.width_cm, self.height_cm)), reverse=True)
        return s[0], s[1], s[2]

    def gross(self) -> Decimal:
        return _positive("gross weight", self.gross_kg)


@dataclass(frozen=True)
class Tariff:
    id: str
    row: dict[str, Any]
    version: int = 0                                # the tariffs file's version

    @property
    def table(self) -> dict[Decimal, Decimal]:
        return {Decimal(str(k)): Decimal(str(v)) for k, v in self.row["table"].items()}

    @property
    def sha256(self) -> str:
        """The fingerprint (16 hex) of what moves a price: the currency, the divisor, the rounding, the steps, each
        surcharge's id, amount, currency, per, lines and minimum, the included surcharge. A changed step, fee or
        switch changes it (a price made with it records the exact tariff, a publication sends the product again);
        a note, a label or a source does not."""
        row = self.row
        priced = {k: row.get(k) for k in ("currency", "divisor", "weight_round", "table", "included_surcharge")}
        if priced["included_surcharge"]:
            priced["included_surcharge"] = {k: priced["included_surcharge"].get(k) for k in ("id", "over_step_kg", "usd")}
        priced["surcharges"] = [{k: s.get(k) for k in ("id", "amount", "currency", "per", "any_of", "min_billable_kg")}
                                for s in row.get("surcharges") or []]
        text = json.dumps(priced, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def describe(self) -> dict[str, Any]:
        """For a price's record: which tariff, of which day, from which version of the file, its fingerprint."""
        return {"tariff": self.id, "checked_at": self.row["checked_at"], "currency": self.row["currency"],
                "version": self.version, "sha256": self.sha256}


@dataclass(frozen=True)
class Tariffs:
    version: int
    tariffs: dict[str, Tariff]
    shops: dict[str, str]

    def for_shop(self, shop: str) -> Tariff | None:
        """The shop's tariff; None when the shop's prices do not carry delivery (the shop is not in `shops`)."""
        name = self.shops.get(shop)
        return self.tariffs[name] if name else None


def check(row: Any) -> None:
    """A tariff row says everything the calculator needs, in a form it can use: nothing is left to fail on the
    first box."""
    if not isinstance(row, dict):
        raise TariffError(f"a tariff must be an object, got {type(row).__name__}")
    where = f"tariff {row.get('id')!r}"
    for key in ("id", "partner", "carrier", "service", "origin", "destination", "currency", "checked_at", "source",
                "divisor", "weight_round", "table", "approved_by", "approved_at"):
        if row.get(key) in (None, "", {}, []):
            raise TariffError(f"{where}: {key} is missing")
    if row["currency"] != CURRENCY:
        raise TariffError(f"{where}: the currency must be {CURRENCY}")
    if _decimal(row["divisor"]) is None:
        raise TariffError(f"{where}: divisor must be a positive number")
    if _decimal(row["weight_round"]) not in ROUNDINGS:
        raise TariffError(f"{where}: weight_round must be one of {', '.join(_plain(r) for r in ROUNDINGS)}")
    if not isinstance(row["table"], dict):
        raise TariffError(f"{where}: the table must be an object of step: price")
    table = {_decimal(k): _decimal(v) for k, v in row["table"].items()}
    if None in table or None in table.values() or len(table) != len(row["table"]):
        raise TariffError(f"{where}: the table's steps must be different positive weights with positive prices")
    steps = sorted(table)                           # type: ignore[type-var]
    if any(table[b] <= table[a] for a, b in zip(steps, steps[1:])):     # type: ignore[operator]
        raise TariffError(f"{where}: a heavier step must cost more than a lighter one")
    surcharges_ = row.get("surcharges") or []
    if not isinstance(surcharges_, list):
        raise TariffError(f"{where}: surcharges must be a list")
    seen = set()
    for s in surcharges_:
        name = s.get("id") if isinstance(s, dict) else None
        if not name or name in seen:
            raise TariffError(f"{where}: every surcharge needs an id of its own, got {name!r}")
        seen.add(name)
        if _decimal(s.get("amount")) is None or s.get("per") != "box":
            raise TariffError(f"{where}: surcharge {name!r} needs a positive amount and per: box")
        if s.get("currency") not in (CURRENCY, "KRW"):
            raise TariffError(f"{where}: surcharge {name!r}: the currency must be {CURRENCY} or KRW")
        any_of = s.get("any_of")
        if not isinstance(any_of, dict) or not any_of or set(any_of) - set(CONDITIONS):
            raise TariffError(f"{where}: surcharge {name!r}: any_of takes {', '.join(CONDITIONS)}")
        if any(_decimal(v) is None for v in any_of.values()):
            raise TariffError(f"{where}: surcharge {name!r}: every line of any_of must be a positive number")
        if s.get("min_billable_kg") is not None and _decimal(s["min_billable_kg"]) is None:
            raise TariffError(f"{where}: surcharge {name!r}: min_billable_kg must be a positive number or null")
    inside = row.get("included_surcharge")
    if inside is not None:
        if (not isinstance(inside, dict) or inside.get("id") not in seen or _decimal(inside.get("over_step_kg")) is None
                or _decimal(inside.get("usd")) is None):
            raise TariffError(f"{where}: included_surcharge needs the id of one of its surcharges, a positive "
                              "over_step_kg and a positive usd")


def _no_repeat(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TariffError(f"{key!r} is written twice")
        out[key] = value
    return out


def load(path: str = TARIFFS) -> Tariffs:
    """The tariffs file, checked whole: a file that loads prices every box the same way tomorrow."""
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f, object_pairs_hook=_no_repeat)
        except json.JSONDecodeError as e:
            raise TariffError(f"{path}: not JSON: {e}") from None
    if not isinstance(data, dict):
        raise TariffError("the tariffs file must be an object")
    version, rows, shops = data.get("version"), data.get("tariffs"), data.get("shops")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise TariffError("version must be a whole number from 1")
    if not isinstance(rows, list) or not rows:
        raise TariffError("tariffs must be a list with at least one tariff")
    if not isinstance(shops, dict):                 # a missing block would read as "no shop carries delivery"
        raise TariffError("shops must be an object (it may be empty): which tariff each shop's prices carry")
    history = data.get("history", [])
    if not isinstance(history, list) or any(not isinstance(h, dict) or not h.get("date") or not h.get("change")
                                            or h.get("version") is None for h in history):
        raise TariffError("history must be a list of {version, date, change}")
    if history and max(h["version"] for h in history) != version:
        raise TariffError("the last history row must be this file's version: a changed tariff gets its line")
    tariffs = {}
    for row in rows:
        check(row)
        if row["id"] in tariffs:
            raise TariffError(f"tariff {row['id']!r} is there twice")
        tariffs[row["id"]] = Tariff(row["id"], row, version)
    for shop, name in shops.items():
        if name not in tariffs:
            raise TariffError(f"shop {shop!r}: no tariff {name!r}")
    return Tariffs(version, tariffs, dict(shops))


def volumetric_kg(tariff: Tariff, box: Box) -> Decimal:
    """L x W x H / divisor, not rounded."""
    a, b, c = box.sides()
    return a * b * c / Decimal(str(tariff.row["divisor"]))


def billable_kg(tariff: Tariff, box: Box) -> Decimal:
    """The larger of gross and volumetric weight, rounded to the tariff's precision (hundredths), half up."""
    weight = max(box.gross(), volumetric_kg(tariff, box))
    return weight.quantize(Decimal(str(tariff.row["weight_round"])), rounding=ROUND_HALF_UP)


def step_kg(tariff: Tariff, billable: Decimal) -> Decimal | None:
    """The weight step that pays for a billable weight: the table's first step that is not under it. None over
    the table's last step."""
    return next((s for s in sorted(tariff.table) if s >= billable), None)


def included(tariff: Tariff, step: Decimal | None) -> dict[str, str] | None:
    """The surcharge the partner's table already holds on this step ({id, usd}), or None."""
    inside = tariff.row.get("included_surcharge")
    if not inside or step is None or step <= Decimal(str(inside["over_step_kg"])):
        return None
    return {"id": inside["id"], "usd": _money(Decimal(str(inside["usd"])))}


def surcharges(tariff: Tariff, box: Box, krw_per_usd: Any = None) -> list[dict[str, Any]]:
    """The surcharges this box pays, one line each: once per box, however many of its conditions hold. A line is
    crossed only when the box is over it: a side of exactly 121 cm is not over 121 cm."""
    a, b, c = box.sides()
    measured = {"longest_cm_over": a, "second_cm_over": b, "length_girth_cm_over": a + 2 * b + 2 * c,
                "volume_cm3_over": a * b * c}
    out = []
    for s in tariff.row.get("surcharges") or []:
        why = [k for k in CONDITIONS if k in s["any_of"] and measured[k] > Decimal(str(s["any_of"][k]))]
        if not why:
            continue
        amount = Decimal(str(s["amount"]))
        if s["currency"] == CURRENCY:
            usd = amount
        elif krw_per_usd is None:
            raise RateMissing(f"surcharge {s['id']}: {_plain(amount)} KRW needs the caller's KRW per USD rate")
        else:
            usd = (amount / _positive("krw_per_usd", krw_per_usd)).quantize(CENT, rounding=ROUND_CEILING)
        line = {"id": s["id"], "amount": _plain(amount), "currency": s["currency"], "usd": _money(usd), "because": why}
        if s.get("min_billable_kg") is not None:
            line["min_billable_kg"] = _plain(Decimal(str(s["min_billable_kg"])))
        out.append(line)
    return out


def box_cost(tariff: Tariff, box: Box, krw_per_usd: Any = None,
             fresh: Callable[[Box], Any] | None = None) -> dict[str, Any]:
    """What one box costs to carry, with every figure that led there.

    status: "table" (the base is the table's row), "quote" (over the table: `fresh` gave today's price, a
    positive amount), "needs_quote" (over the table and no fresh price: base and total are None; never
    extrapolated). `krw_per_usd`, when given, must be a positive number whether or not a line needs it."""
    if krw_per_usd is not None:
        _positive("krw_per_usd", krw_per_usd)
    volumetric, billable = volumetric_kg(tariff, box), billable_kg(tariff, box)
    lines = surcharges(tariff, box, krw_per_usd)
    floor = max((Decimal(s["min_billable_kg"]) for s in lines if "min_billable_kg" in s), default=None)
    if floor is not None and floor > billable:      # FedEx's minimum for a box that pays the fee (off today)
        billable = floor
    step = step_kg(tariff, billable)
    base, status = (None if step is None else tariff.table[step]), "table"
    if base is None:
        quoted = fresh(box) if fresh else None
        base = None if quoted is None else _positive("the fresh quote", quoted)
        status = "quote" if base is not None else "needs_quote"
    inside = included(tariff, step)
    if inside:                                      # the table already holds it: once per box
        lines = [s for s in lines if s["id"] != inside["id"]]
    total = None if base is None else base + sum((Decimal(s["usd"]) for s in lines), Decimal(0))
    return {**tariff.describe(), "box_cm": [_plain(s) for s in box.sides()], "gross_kg": _plain(box.gross()),
            "volumetric_kg": _money(volumetric), "billable_kg": _money(billable),
            "step_kg": None if step is None else _plain(step), "status": status,
            "base_usd": None if base is None else _money(base), "included": inside, "surcharges": lines,
            "total_usd": None if total is None else _money(total)}


def shipment_cost(tariff: Tariff, boxes: Any, krw_per_usd: Any = None,
                  fresh: Callable[[Box], Any] | None = None) -> dict[str, Any]:
    """Several boxes of one order: each box priced on its own, then added. One box without a price leaves the
    total None."""
    boxes = list(boxes)
    if not boxes:
        raise ValueError("no box")
    costs = [box_cost(tariff, b, krw_per_usd, fresh) for b in boxes]
    known = all(c["total_usd"] is not None for c in costs)
    return {"boxes": costs, "total_usd": _money(sum((Decimal(c["total_usd"]) for c in costs), Decimal(0))) if known else None}
