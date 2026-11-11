"""A shop's prices in Shopify from the Naver price in KRW (the owner, 2026-11-08; delivery, duty and margin inside
the price, 2026-11-11).

A shop without a delivery rule (`Policy.delivered` None): the cost is the Naver price at a fixed 1 000 KRW = 1 USD,
rounded UP to a whole dollar (5 560 KRW -> 6 USD), and the price is the cost.

A shop that sells with free delivery (fairwardgolf) carries everything in the price, per variant (`Policy.quote`):

    purchase  = (the variant's Naver price + the seller's delivery in Korea) / 1000, up to a whole dollar;
                the delivery in Korea is the listing's fee when it is paid (PAID, UNIT_QUANTITY_PAID), else 0
    cost      = purchase + ShopNShip's commission (3 USD)                -> Shopify's cost per item
    duty      = US import duty, prepaid through ShopNShip: 12.5 % of the purchase, up to a cent; a line of its own,
                added to the cost for the price, never written to Shopify's cost per item (the owner, 2026-11-11)
    grid      = the partner's tariff for the variant's box (delivery_tariff.py: ShopNShip, FedEx to the US)
    inside    = the dimension fee the tariff already holds over 25 kg (32.36 USD), else 0
    level     = the lowest confidence of the box's three sides (package_measures: 5 stated ... 1 the default)
    delivery  = (grid - inside) x the level's coefficient + inside      (1.00 / 1.10 / 1.20 / 1.40 / 2.50 for 5 ... 1)
    fee       = FedEx's dimension fee, KRW 35,600 at 1000 KRW = 1 USD, when the box crosses its lines and the tariff
                does not hold it already: once per box
    base      = cost + duty + delivery + fee
    margin    = 25 + 11 % of the base, never under 30 (the owner, 2026-11-11: a fixed part for each order and a part
                that grows with the sum, as the risks and the payment fee lost on a refund do)
    keep      = base + margin                      what stays with the shop after the payment system's share
    price     = the first pretty number not under keep / (1 - 3 %): ending in 9 under 1000, in 99 from 1000
    surplus   = price - 3 % of it - keep           kept as a reserve (the owner)

Fuel, insurance and the partner's handling are inside its tariff; prices are taken as Naver shows them, the
discount included (a later sync); the rate is the owner's constant. A variant without a box, or a box over the
tariff's last step (50 kg), has no price: PriceError, the product is held. Add-ons are priced as in a shop without
the rule (no delivery, no duty, no margin): a bag sold as a paid add-on would lose the with-bag delivery, so paid
add-ons stay off until boxes are priced per add-on.

    from shop_pricing import policy
    q = policy("fairwardgolf").quote(variant, product)     # q.cost, q.price, q.breakdown
"""
import functools
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

import delivery_tariff as DT

VERSION = "krw-cost/1"                          # a shop without the rule (unchanged since 2026-11-08)
VERSION_DELIVERED = "landed/2"                  # bump on a change of the rule's arithmetic: every product is sent again
CENT = Decimal("0.01")
SIDES = ("package_length_mm", "package_width_mm", "package_height_mm")


class PriceError(ValueError):
    """A variant that cannot be priced (no box, a box over the tariff): the product is held."""


@dataclass(frozen=True)
class Quote:
    cost: Decimal                               # Shopify's cost per item
    price: int                                  # the price, a whole dollar
    breakdown: dict[str, Any] | None = None     # how it was made (the rule's shops)


@dataclass(frozen=True)
class Delivered:
    """The owner's rule for a shop whose buyers pay no delivery (all amounts in USD)."""
    tariff: str
    service_usd: Decimal
    duty_rate: Decimal
    coefficients: dict[int, Decimal]
    margin_fixed: Decimal
    margin_rate: Decimal
    margin_min: Decimal
    payment_rate: Decimal
    korea_paid: tuple[str, ...]
    decided: dict[str, str] = field(default_factory=dict)

    def margin(self, base: Decimal) -> Decimal:
        """A fixed part and a share of the base, never under the minimum."""
        return max(self.margin_min, self.margin_fixed + self.margin_rate * base)


def pretty(amount: Decimal) -> int:
    """Up to a whole dollar, then to a number ending in 9 under 1000 and in 99 from 1000 (164 -> 169, 1254 -> 1299)."""
    whole = int(amount.to_integral_value(rounding=ROUND_CEILING))
    if whole < 1000:
        return whole + (9 - whole % 10) % 10
    return whole + (99 - whole % 100) % 100


def package_number(f: dict[str, Any] | None) -> Any:
    """A package field's number: the category default's central value, else the larger end of the value (a range
    {min, max} or a number), as the shipping weight is read."""
    if not f:
        return None
    if f.get("central") is not None:
        return f["central"]
    value = f.get("value")
    return max(value.get("min") or 0, value.get("max") or 0) if isinstance(value, dict) else value


@functools.lru_cache(maxsize=None)
def _tariff(name: str) -> DT.Tariff:
    return DT.load().tariffs[name]


def _usd(d: Decimal) -> str:
    return format(d.quantize(CENT, rounding=ROUND_HALF_UP), "f")


@dataclass(frozen=True)
class Policy:
    krw_per_usd: int = 1000
    rounding: str = "ceil-dollar"
    delivered: Delivered | None = None

    def cost_usd(self, krw: int) -> int:
        """KRW at the shop's rate, up to a whole dollar (a shop without the rule; add-ons everywhere)."""
        return -(-int(krw) // self.krw_per_usd)

    def price_usd(self, cost: int, context: dict[str, Any] | None = None) -> int:
        """An add-on's price, and a variant's in a shop without the rule: the cost."""
        return cost

    def quote(self, variant: dict[str, Any], product: dict[str, Any]) -> Quote:
        """The variant's cost per item and price (with how they were made in a shop with the rule)."""
        krw = int(variant["price_krw"])
        rule = self.delivered
        if rule is None:
            plain = self.cost_usd(krw)
            return Quote(Decimal(plain), self.price_usd(plain))
        delivery = product.get("delivery") or {}
        korea = int(delivery.get("base_fee") or 0) if delivery.get("fee_type") in rule.korea_paid else 0
        purchase = self.cost_usd(krw + korea)
        duty = (purchase * rule.duty_rate).quantize(CENT, rounding=ROUND_CEILING)
        cost: Decimal = purchase + rule.service_usd           # Shopify's cost per item: the duty is apart

        package = variant.get("package") or {}
        numbers = [package_number(package.get(f)) for f in SIDES + ("package_weight_g",)]
        if any(n is None for n in numbers):
            raise PriceError("no package box to price the delivery")
        try:
            box = DT.Box.of_package(*numbers)
        except ValueError as e:
            raise PriceError(f"the package box: {e}") from None
        try:                                    # a missing confidence is the least certain
            level = max(1, min(5, min(int(package[f].get("confidence") or 1) for f in SIDES)))
        except (TypeError, ValueError):
            raise PriceError("a box side without a readable confidence") from None
        coefficient = rule.coefficients[level]
        tariff = _tariff(rule.tariff)
        answer = DT.box_cost(tariff, box, krw_per_usd=self.krw_per_usd)
        if answer["base_usd"] is None:
            raise PriceError(f"the box {'x'.join(answer['box_cm'])} cm, {answer['billable_kg']} kg is over the "
                             "tariff's last step: no price (needs a quote)")
        grid = Decimal(answer["base_usd"])
        inside = Decimal(answer["included"]["usd"]) if answer["included"] else Decimal(0)
        carried = ((grid - inside) * coefficient).quantize(CENT, rounding=ROUND_HALF_UP) + inside
        fee = sum((Decimal(s["usd"]) for s in answer["surcharges"]), Decimal(0))
        base = cost + duty + carried + fee
        margin = rule.margin(base).quantize(CENT, rounding=ROUND_HALF_UP)
        keep = base + margin
        needed = keep / (1 - rule.payment_rate)
        price = pretty(needed)
        payment = (price * rule.payment_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        breakdown = {
            "rule": VERSION_DELIVERED, "krwPerUsd": self.krw_per_usd, "naverKrw": krw, "koreaDeliveryKrw": korea,
            "koreaFeeType": delivery.get("fee_type"), "purchaseUsd": purchase, "serviceUsd": _usd(rule.service_usd),
            "dutyRate": str(rule.duty_rate), "dutyUsd": _usd(duty), "costUsd": _usd(cost),
            "box": {"cm": answer["box_cm"], "grossKg": answer["gross_kg"], "billableKg": answer["billable_kg"],
                    "stepKg": answer["step_kg"]},
            "level": level, "coefficient": str(coefficient),
            "tariff": {"id": tariff.id, "checkedAt": tariff.row["checked_at"], "version": tariff.version,
                       "sha256": tariff.sha256},
            "gridUsd": _usd(grid), "insideUsd": _usd(inside), "deliveryUsd": _usd(carried),
            "fees": [{"id": s["id"], "usd": s["usd"], "because": s["because"]} for s in answer["surcharges"]],
            "feeUsd": _usd(fee), "baseUsd": _usd(base), "marginUsd": _usd(margin), "keepUsd": _usd(keep),
            "paymentRate": str(rule.payment_rate), "neededUsd": _usd(needed), "priceUsd": price,
            "paymentUsd": _usd(payment), "surplusUsd": _usd(price - payment - keep)}
        return Quote(cost.quantize(CENT), price, breakdown)

    def describe(self) -> dict[str, Any]:
        """For the product's pricing metafield and the publication's digest: how its prices are made. Every number
        of the rule and the tariff's version are in it, so a change sends the products again."""
        rule = self.delivered
        if rule is None:
            return {"version": VERSION, "krwPerUsd": self.krw_per_usd, "rounding": self.rounding, "margin": None}
        tariff = _tariff(rule.tariff)
        return {"version": VERSION_DELIVERED, "krwPerUsd": self.krw_per_usd, "serviceUsd": _usd(rule.service_usd),
                "dutyRate": str(rule.duty_rate), "koreaPaid": list(rule.korea_paid),
                "coefficients": {str(k): str(v) for k, v in sorted(rule.coefficients.items(), reverse=True)},
                "margin": {"fixedUsd": _usd(rule.margin_fixed), "rate": str(rule.margin_rate),
                           "minUsd": _usd(rule.margin_min)}, "paymentRate": str(rule.payment_rate),
                "rounding": "up to a whole dollar ending in 9 under 1000, in 99 from 1000",
                "tariff": {"id": tariff.id, "checkedAt": tariff.row["checked_at"], "version": tariff.version,
                           "sha256": tariff.sha256},
                "decided": dict(rule.decided)}


FAIRWARDGOLF = Delivered(
    tariff="shopnship-fedex-ip-kr-us",
    service_usd=Decimal("3"),
    duty_rate=Decimal("0.125"),
    coefficients={5: Decimal("1.00"), 4: Decimal("1.10"), 3: Decimal("1.20"), 2: Decimal("1.40"), 1: Decimal("2.50")},
    margin_fixed=Decimal("25"),
    margin_rate=Decimal("0.11"),
    margin_min=Decimal("30"),
    payment_rate=Decimal("0.03"),
    korea_paid=("PAID", "UNIT_QUANTITY_PAID"),
    decided={"rate": "2026-11-10", "korea_delivery": "2026-11-10", "service": "2026-11-11", "duty": "2026-11-11",
             "coefficients": "2026-11-11", "margin": "2026-11-11", "payment": "2026-11-11", "rounding": "2026-11-11"})

POLICIES = {"fairwardgolf": Policy(delivered=FAIRWARDGOLF)}   # which shops carry delivery in the price: this map
                                                                # (delivery_tariffs.json's `shops` must agree: a test)


def policy(shop: str) -> Policy:
    return POLICIES.get(shop) or Policy()


def money(usd: int | Decimal) -> str:
    """Shopify's decimal string: 1450 -> "1450.00", Decimal("1013.25") -> "1013.25"."""
    return format(Decimal(usd).quantize(CENT, rounding=ROUND_HALF_UP), "f")
