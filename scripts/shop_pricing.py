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

A Naver category may carry its own coefficients and duty (`Delivered.categories`, keyed by the leaf id; the owner,
2026-11-19, women's knit cardigans 50002797): every level at 1.10 (a garment's mailer is predictable; the clubs' 2.50
for a default box does not apply), and the duty (the owner, 2026-11-19, second word: a flat 12.5 % for now, `CategoryPrice.duty_flat`, a TODO to switch
on the rate) by the chief fibre of the composition (US HTS 6110): wool 16 %,
cotton 16.5 %, cashmere 4 %, man-made fibres 32 %, another fibre or an unread composition 32 % (`chief_fibre`: the
largest share, man-made fibres summed, of the first composition adding up to 100 that the product's 소재 / 혼용률 /
재질 / 섬유의 조성 rows state; a partial one is none). The breakdown
names the fibre (dutyBasis); describe(category) adds the category's rule. A category without an override is priced,
and described, exactly as before.

Fuel, insurance and the partner's handling are inside its tariff; prices are taken as Naver shows them, the
discount included (a later sync); the rate is the owner's constant. A variant without a box, or a box over the
tariff's last step (50 kg), has no price: PriceError, the product is held. Add-ons are priced as in a shop without
the rule (no delivery, no duty, no margin): a bag sold as a paid add-on would lose the with-bag delivery, so paid
add-ons stay off until boxes are priced per add-on.

    from shop_pricing import policy
    q = policy("fairwardgolf").quote(variant, product)     # q.cost, q.price, q.breakdown
"""
import functools
import re
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


# ---- the fibre of a garment (the duty by fibre, 2026-11-19) -------------------------------------------------------

# a fibre as Korean labels and sellers write it -> its kind for the duty. One-syllable Korean names (면 cotton, 모 /
# 울 wool, 견 silk, 마 linen) only as a word of their own: 겨울 (winter), 단면, 표면 are no fibre.
FIBRES: dict[str, tuple[str, ...]] = {
    "cashmere": ("캐시미어", "캐시미아", "캐시미야", "카시미어", "카시미아", "캐시밀론", "cashmere", "kashmir"),
    "wool": ("메리노울", "메리노 울", "램스울", "순모", "양모", "울", "모", "merino wool", "lambswool", "merino",
             "wool"),
    "cotton": ("순면", "코튼", "면", "cotton"),
    "man-made": ("아크릴릭", "아크릴", "폴리에스테르", "폴리에스터", "폴리에스타", "폴리우레탄", "폴리아미드", "폴리", "나일론", "나이론",
                 "레이온", "비스코스", "스판덱스", "스판", "엘라스테인", "엘라스틴", "모달", "텐셀", "라이오셀",
                 "아세테이트", "acrylic", "polyester", "polyurethane", "polyamide", "nylon", "rayon", "viscose",
                 "spandex", "elastane", "lycra", "modal", "tencel", "lyocell", "acetate"),
    "other": ("알파카", "앙고라", "모헤어", "실크", "린넨", "견", "마", "alpaca", "angora", "mohair", "silk", "linen"),
}
_WORD = {w: kind for kind, words in FIBRES.items() for w in words}
_FIBRE = "|".join(sorted(map(re.escape, _WORD), key=len, reverse=True))
_SHARE = r"(\d{1,3}(?:\.\d+)?)\s*(%|％|퍼센트)?"
_END = r"(?:\s*섬유)?(?![가-힣A-Za-z])"          # "아크릴섬유", "폴리에스테르 섬유": the fibre word, then its share
# a fibre word that only says how it feels is no composition: "100% 울 터치감 아크릴 소재" is acrylic (2026-11-19)
_NOT_FIBRE = r"(?!\s*(?:터치|느낌|감촉|같은|처럼|스러운|touch|feel|like)(?![A-Za-z]))"
# "아크릴 50%", "울(30%)", "울: 30%", "WOOL 30%" or "30% 울", "30% WOOL"
_PAIR_RE = re.compile(rf"(?<![가-힣A-Za-z])({_FIBRE}){_END}\s*[:(]?\s*{_SHARE}"
                      rf"|(?<![\d.]){_SHARE}\s*\)?\s*({_FIBRE}){_END}{_NOT_FIBRE}", re.I)
_ALONE_RE = re.compile(rf"^\s*(?:\S*\s*[:：]\s*)?({_FIBRE})(?:\s*섬유)?\s*(?:100\s*%?)?\s*$", re.I)  # "아크릴", "면 100"


def _kind(word: str) -> str:
    return _WORD.get(word) or _WORD.get(word.lower()) or _WORD[re.sub(r"\s+", " ", word.lower())]


# a stated composition adds up to 100 within a seller's rounding (33.3 x 3); a group short of it names only some of
# the fibres ("캐시미어 10% 함유", "울 30%, 기타 70%") and an unread fibre could be the chief one: no composition, the
# next row is read, else the unknown rate (review 2026-11-19)
_FULL = (Decimal(99), Decimal(101))


def composition(text: str) -> list[tuple[str, str, Decimal]]:
    """(the word, its kind, its share) of the first full composition in the text: the pairs in order until they
    make 100 % (the body's fabric comes first; a lining's or a rib's after it). Shares with % count when they make
    99-101 (rounding), shares written without % only when they make exactly 100; a group short of 100 is none.
    A text naming one fibre alone ("아크릴", "면 100") is that fibre at 100."""
    pairs: list[tuple[str, str, Decimal, bool]] = []
    for m in _PAIR_RE.finditer(text or ""):
        word, share, pct = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(4), m.group(5))
        if Decimal(share) <= 100:
            pairs.append((word, _kind(word), Decimal(share), bool(pct)))
    for chosen, exact in (([p for p in pairs if p[3]], False), (pairs, True)):
        group: list[tuple[str, str, Decimal]] = []
        total = Decimal(0)
        for word, kind, share, _ in chosen:
            group.append((word, kind, share))
            total += share
            if total >= 100:
                break
        if group and (total == 100 or (not exact and _FULL[0] <= total <= _FULL[1])):
            return group
    alone = _ALONE_RE.match(text or "")
    return [(alone.group(1), _kind(alone.group(1)), Decimal(100))] if alone else []


def chief_fibre(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The chief fibre of the first row that states a full composition: {fibres, top, kinds, label, source, text};
    the largest share, summed by kind (wool 30 + merino 20 are wool 50; acrylic 30 + nylon 30 are man-made 60, as
    customs takes man-made fibres for one material). Summing the man-made kinds is the implementer's reading of the
    owner's "the largest percentage" (2026-11-19), never lower than the literal one, to confirm with the owner; wool
    and cashmere are not summed. A tie goes to the dearest duty's kind at the caller. None: no row states one."""
    for row in rows:
        text = row.get("value_ko") or ""
        parts = composition(text)
        if not parts:
            continue
        by_kind: dict[str, Decimal] = {}
        for _, kind, share in parts:
            by_kind[kind] = by_kind.get(kind, Decimal(0)) + share
        top = max(by_kind.values())
        return {"fibres": {k: v for k, v in by_kind.items()}, "top": top,
                "kinds": sorted(k for k, v in by_kind.items() if v == top),
                "label": row.get("label_ko"), "source": row.get("source", "spec"), "text": text[:200]}
    return None


_COMPOSITION_LABEL_RE = re.compile(r"소재|혼용\s*[률율]|재질|섬유|조성|material|fabric|composition", re.I)


def composition_rows(product: dict[str, Any]) -> list[dict[str, Any]]:
    """The product's fibre rows: transform's composition_ko (spec and notice rows), else its spec rows by label."""
    rows = product.get("composition_ko")
    if rows is None:
        rows = [s for s in product.get("specs") or [] if _COMPOSITION_LABEL_RE.search(s.get("label_ko") or "")]
    return list(rows)


@dataclass(frozen=True)
class CategoryPrice:
    """A Naver category's own coefficients and duty inside the shop's rule (the owner's, dated)."""
    coefficients: dict[int, Decimal]
    duty_by_fibre: dict[str, Decimal]           # "wool", "cotton", "cashmere", "man-made", "other", "unknown"
    hts: str
    decided: dict[str, str] = field(default_factory=dict)
    duty_flat: Decimal | None = None            # the owner's flat rate in place of the rate by fibre (the fibre read
                                                # stays in the basis, for the day the rule by fibre is switched on)

    def duty(self, product: dict[str, Any]) -> tuple[Decimal, dict[str, Any]]:
        """(the duty rate, its basis): the flat rate when the category has one, else the chief fibre's rate."""
        rate, basis = self._by_fibre(product)
        if self.duty_flat is not None:
            return self.duty_flat, {**basis, "flat": True, "byFibre": str(rate)}
        return rate, basis

    def _by_fibre(self, product: dict[str, Any]) -> tuple[Decimal, dict[str, Any]]:
        found = chief_fibre(composition_rows(product))
        if not found:
            return self.duty_by_fibre["unknown"], {"hts": self.hts, "fibre": "unknown",
                                                   "why": "no composition row states the fibres"}
        kind = max(found["kinds"], key=lambda k: self.duty_by_fibre.get(k, self.duty_by_fibre["unknown"]))
        rate = self.duty_by_fibre.get(kind, self.duty_by_fibre["unknown"])
        return rate, {"hts": self.hts, "fibre": kind, "percent": format(found["top"].normalize(), "f"),
                      "row": found["label"], "source": found["source"], "text": found["text"]}

    def describe(self) -> dict[str, Any]:
        return {"coefficients": {str(k): str(v) for k, v in sorted(self.coefficients.items(), reverse=True)},
                **({"dutyFlat": str(self.duty_flat)} if self.duty_flat is not None else {}),
                "dutyByFibre": {k: str(v) for k, v in self.duty_by_fibre.items()}, "hts": self.hts,
                "chiefFibre": "the largest share of the first full composition of the 소재 / 혼용률 / 재질 / 섬유의 조성 "
                              "rows; another fibre or none read: the unknown rate",
                "decided": dict(self.decided)}


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
    categories: dict[str, CategoryPrice] = field(default_factory=dict)    # Naver leaf id -> its own coefficients
                                                                          # and duty (2026-11-19)

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

    def quote(self, variant: dict[str, Any], product: dict[str, Any], category_id: str | None = None) -> Quote:
        """The variant's cost per item and price (with how they were made in a shop with the rule). `category_id`:
        the product's Naver leaf id (prepared["source"]["category_id"]); a category with its own rule
        (Delivered.categories) takes its coefficients and its duty by fibre."""
        krw = int(variant["price_krw"])
        rule = self.delivered
        if rule is None:
            plain = self.cost_usd(krw)
            return Quote(Decimal(plain), self.price_usd(plain))
        own = rule.categories.get(str(category_id)) if category_id is not None else None
        duty_rate, basis = own.duty(product) if own else (rule.duty_rate, None)
        coefficients = own.coefficients if own else rule.coefficients
        delivery = product.get("delivery") or {}
        korea = int(delivery.get("base_fee") or 0) if delivery.get("fee_type") in rule.korea_paid else 0
        purchase = self.cost_usd(krw + korea)
        duty = (purchase * duty_rate).quantize(CENT, rounding=ROUND_CEILING)
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
        coefficient = coefficients[level]
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
            "dutyRate": str(duty_rate), "dutyUsd": _usd(duty), "costUsd": _usd(cost),
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
        if own:                                 # only a category with its own rule: the clubs' breakdown as before
            breakdown["category"] = str(category_id)
            breakdown["dutyBasis"] = basis
        return Quote(cost.quantize(CENT), price, breakdown)

    def describe(self, category_id: str | None = None) -> dict[str, Any]:
        """For the product's pricing metafield and the publication's digest: how its prices are made. Every number
        of the rule and the tariff's version are in it, so a change sends the products again. `category_id`: a
        category with its own rule adds it under "category"; any other gets exactly the shop's description."""
        rule = self.delivered
        if rule is None:
            return {"version": VERSION, "krwPerUsd": self.krw_per_usd, "rounding": self.rounding, "margin": None}
        out = self._describe(rule)
        own = rule.categories.get(str(category_id)) if category_id is not None else None
        if own:
            out["category"] = {"id": str(category_id), **own.describe()}
        return out

    def _describe(self, rule: Delivered) -> dict[str, Any]:
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
             "coefficients": "2026-11-11", "margin": "2026-11-11", "payment": "2026-11-11", "rounding": "2026-11-11"},
    categories={
        # the owner, 2026-11-19: women's golf knit cardigans. Delivery x1.10 at every confidence level (a garment's
        # mailer is predictable: the category's default box, 28 x 22 x 4 cm, is the 0.5 kg step); the duty by the
        # chief fibre, US HTS 6110 (knitted cardigans): wool 16 %, cotton 16.5 %, cashmere 4 % (when it is the chief
        # fibre), man-made (acrylic, polyester, nylon, rayon / viscose, spandex, modal ...) 32 %, another fibre or an
        # unread composition 32 % (the dearest: never under the duty paid)
        "50002797": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.16"), "cotton": Decimal("0.165"), "cashmere": Decimal("0.04"),
                           "man-made": Decimal("0.32"), "other": Decimal("0.32"), "unknown": Decimal("0.32")},
            hts="6110",
            # the owner, 2026-11-19 (second word): a flat 12.5 % for now, by his wish and not the real customs rate
            # TODO(duty): switch to the rate by fibre (duty_flat=None) once the composition is read from the
            #             description and the OCR (22 of the 30 pilot products have no readable composition row)
            duty_flat=Decimal("0.125"),
            decided={"coefficients": "2026-11-19", "duty": "2026-11-19 flat 12.5 %"}),
        # 2026-11-20: women's golf windbreakers, the knits' rule on the owner's delegation (the section was his, the
        # rest "фикси на лету"): delivery x1.10 at every level (the same mailer), the flat 12.5 % duty; the rate by
        # fibre kept for the day it is switched on, US HTS 6202 (women's anoraks and windbreakers, woven): wool
        # 6202.91 about 16 %, cotton 6202.92 8.9 %, man-made 6202.93 27.7 %, another or an unread one 27.7 %
        "50002798": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.16"), "cotton": Decimal("0.089"), "cashmere": Decimal("0.16"),
                           "man-made": Decimal("0.277"), "other": Decimal("0.277"), "unknown": Decimal("0.277")},
            hts="6202",
            duty_flat=Decimal("0.125"),       # the knits' flat rate (the owner 2026-11-19), same TODO(duty)
            decided={"coefficients": "2026-11-20 (the knits')", "duty": "2026-11-20 flat 12.5 % (the knits')"}),
        # 2026-11-21, the owner's decision: 재킷 50002799 feeds the same section as 점퍼 50002798 (Women's Windbreakers): the 50002798 values (the same garment, HTS 6202)
        # 2026-11-21, the owner gave the section (womens-fall-long-sleeve-tops under apparel, the collection existed: "Women’s Long-Sleeve Golf Tops", 0 products) and asked for a pilot of 30, its review and fixes: the apparel rule, x1.10 at every level, the flat 12.5 % duty; the rate by fibre kept for the
        # day it is switched on, US HTS 6109 (T-shirts and tops, knitted): cotton 6109.10 16.5 %, man-made 6109.90
        # 32 %, another or an unread one 32 %; wool and cashmere (a knit top) as the knits' 16 %
        "50002796": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.16"), "cotton": Decimal("0.165"), "cashmere": Decimal("0.16"),
                           "man-made": Decimal("0.32"), "other": Decimal("0.32"), "unknown": Decimal("0.32")},
            hts="6109",
            duty_flat=Decimal("0.125"),
            decided={"coefficients": "2026-11-21 (the apparel rule)", "duty": "2026-11-21 flat 12.5 % (the apparel rule)"}),
        "50002799": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.16"), "cotton": Decimal("0.089"), "cashmere": Decimal("0.16"),
                           "man-made": Decimal("0.277"), "other": Decimal("0.277"), "unknown": Decimal("0.277")},
            hts="6202",
            duty_flat=Decimal("0.125"),
            decided={"coefficients": "2026-11-21 (50002798's)", "duty": "2026-11-21 flat 12.5 % (50002798's)"}),
        # 2026-11-22, Golf Skirts & Culottes (the owner: the agent decides): the apparel rule, x1.10 at every level, the
        # flat 12.5 % duty; the rate by fibre kept for the day it is switched on, US HTS 6204.5 (women's skirts,
        # woven): wool 6204.51 14 %, cotton 6204.52 8.3 %, synthetic 6204.53 16 %, another or unread 16 %
        "50002802": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.14"), "cotton": Decimal("0.083"), "cashmere": Decimal("0.14"),
                           "man-made": Decimal("0.16"), "other": Decimal("0.16"), "unknown": Decimal("0.16")},
            hts="6204.5",
            duty_flat=Decimal("0.125"),
            decided={"coefficients": "2026-11-22 (the apparel rule)", "duty": "2026-11-22 flat 12.5 % (the apparel rule)"}),
        # 2026-11-23, Golf Pants (the owner gave the section; the price rule the agent's, as the skirts): the apparel
        # rule, x1.10 at every level, the flat 12.5 % duty; the rate by fibre kept for the day it is switched on, US
        # HTS 6203.4 (men's trousers) / 6204.6 (women's): wool 6203.41 / 6204.61 13.6 %, cotton 6203.42 / 6204.62
        # 16.6 %, synthetic 6203.43 27.9 % / 6204.63 28.6 % (the higher taken), another or unread as synthetic
        "50002801": CategoryPrice(
            coefficients={5: Decimal("1.10"), 4: Decimal("1.10"), 3: Decimal("1.10"), 2: Decimal("1.10"),
                          1: Decimal("1.10")},
            duty_by_fibre={"wool": Decimal("0.136"), "cotton": Decimal("0.166"), "cashmere": Decimal("0.136"),
                           "man-made": Decimal("0.286"), "other": Decimal("0.286"), "unknown": Decimal("0.286")},
            hts="6203.4/6204.6",
            duty_flat=Decimal("0.125"),
            decided={"coefficients": "2026-11-23 (the apparel rule)", "duty": "2026-11-23 flat 12.5 % (the apparel rule)"}),
    })

POLICIES = {"fairwardgolf": Policy(delivered=FAIRWARDGOLF)}   # which shops carry delivery in the price: this map
                                                                # (delivery_tariffs.json's `shops` must agree: a test)


def policy(shop: str) -> Policy:
    return POLICIES.get(shop) or Policy()


def money(usd: int | Decimal) -> str:
    """Shopify's decimal string: 1450 -> "1450.00", Decimal("1013.25") -> "1013.25"."""
    return format(Decimal(usd).quantize(CENT, rounding=ROUND_HALF_UP), "f")
