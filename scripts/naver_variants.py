"""Which variants of a product we collect: the operator's choice, applied to the options the API read.

The options come from the product page itself (`api.product_specs(link)["options"]`, the page's own product
answer). Every declared combination is a variant with its extra price and stock; the page shows a sold-out one
as (품절) and it cannot be bought.

The rule (one for every store and category; the operator only turns `paid` on):

  * default (paid=False): only variants that do not change the product's price, extra price 0. A variant whose
    name names a different amount ("(+5,000원)") is left out too: the store's data and its label disagree.
  * paid=True: every variant, with its price (product price + extra price; negative = cheaper).
  * sold-out variants are kept and marked (is_available False), never dropped: the product still has them.
  * simple options (SIMPLE groups) follow the same price rule; text options (a text the buyer types) and
    supplements (add-on products) are not variants and are passed as they are.

An amount in a name counts only in the strict form "(+N원)" / "(-N원)": a "+" without it joins the parts of a
set ("실버블루 + 실버블루", "드라이버+우드"). A name with two amounts (one per part: "드라이버 (+50,000원) / 우드
(+30,000원)") has no single price_in_name; a non-zero one among them still counts as a price change and the
variant is reported when its extra price is 0.
"""
import re
from typing import TypedDict

import naver_types as T

_NAME_PRICE_RE = re.compile(r"\(\s*([+-])\s*(\d[\d,]*)\s*원\s*\)")


class ChosenVariant(TypedDict):
    id: str | None
    name: str | None
    options: list[str] | None
    extra_price: int
    price: int | None                 # the product's price + extra_price; null when the product's price is unknown
    price_in_name: int | None         # the amount the name states, "(+N원)"; null when it states none
    stock_quantity: int | None
    is_available: bool | None


class VariantChoice(TypedDict):
    paid: bool                        # the operator's switch: True also takes variants that change the price
    base_price: int | None
    variants: list[ChosenVariant]     # in the store's order
    available: int                    # chosen variants in stock
    sold_out: int                     # chosen variants sold out (kept, is_available False)
    skipped_paid: int                 # variants left out because they change the price (paid=False)
    name_mismatches: list[str]        # ids whose name states another amount than their extra price
    simple_options: list[T.SimpleOption]
    text_options: list[T.TextOption]
    supplements: list[T.Supplement]


def _name_amounts(name: str | None) -> list[int]:
    return [int(digits.replace(",", "")) * (-1 if sign == "-" else 1)
            for sign, digits in _NAME_PRICE_RE.findall(name or "")]


def price_in_name(name: str | None) -> int | None:
    """The amount a variant's name states, "(+5,000원)" -> 5000, "(-300,000원)" -> -300000; None when the
    name states none or more than one."""
    amounts = _name_amounts(name)
    return amounts[0] if len(amounts) == 1 else None


def _disagrees(extra_price: int, name: str | None) -> bool:
    """The name states an amount that is not the store's extra price (two amounts: any non-zero one)."""
    amounts = _name_amounts(name)
    if len(amounts) == 1:
        return amounts[0] != extra_price
    return extra_price == 0 and any(amounts)


def _changes_price(extra_price: int, name: str | None) -> bool:
    return extra_price != 0 or any(_name_amounts(name))


def choose_variants(options: T.PageOptions, base_price: int | None, paid: bool = False) -> VariantChoice:
    """The variants to collect from `options`, by the rule above. `base_price`: the product's price
    (pricing.discounted_price), which every variant's extra price is added to."""
    chosen: list[ChosenVariant] = []
    skipped = 0
    mismatches: list[str] = []
    for v in options["variants"]:
        named = price_in_name(v["name"])
        if _disagrees(v["extra_price"], v["name"]) and v["id"]:
            mismatches.append(v["id"])
        if not paid and _changes_price(v["extra_price"], v["name"]):
            skipped += 1
            continue
        chosen.append({
            "id": v["id"], "name": v["name"], "options": v["options"], "extra_price": v["extra_price"],
            "price": None if base_price is None else base_price + v["extra_price"],
            "price_in_name": named, "stock_quantity": v["stock_quantity"], "is_available": v["is_available"],
        })
    simple = [o for o in options["simple_options"]
              if paid or not _changes_price(o["extra_price"], o["name"])]
    return {
        "paid": paid,
        "base_price": base_price,
        "variants": chosen,
        "available": sum(1 for v in chosen if v["is_available"]),
        "sold_out": sum(1 for v in chosen if v["is_available"] is False),
        "skipped_paid": skipped,
        "name_mismatches": mismatches,
        "simple_options": simple,
        "text_options": options["text_options"],
        "supplements": options["supplements"],
    }
