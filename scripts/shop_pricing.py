"""A shop's prices in Shopify from the Naver price in KRW (the owner, 2026-11-08).

The cost is the Naver price at a fixed rate, 1 000 KRW = 1 USD, rounded UP to a whole dollar (5 560 KRW -> 6 USD).
The sale price is the cost through the shop's margin rule. There is no margin yet: `margin` is the hook the owner's
rule goes into later (a function of the cost and the product's data: the package measures, the category ...), and
until then the price equals the cost. Add-ons go through the same two steps.

    from shop_pricing import policy
    p = policy("fairwardgolf")
    cost = p.cost_usd(1_449_900)          # 1450
    price = p.price_usd(cost, context)    # 1450 (no margin yet)
"""
from dataclasses import dataclass
from typing import Any, Callable

VERSION = "krw-cost/1"


@dataclass(frozen=True)
class Policy:
    krw_per_usd: int = 1000
    rounding: str = "ceil-dollar"
    margin: Callable[[int, dict[str, Any]], int] | None = None     # cost, context -> price; None: price = cost

    def cost_usd(self, krw: int) -> int:
        return -(-int(krw) // self.krw_per_usd)

    def price_usd(self, cost: int, context: dict[str, Any] | None = None) -> int:
        return int(self.margin(cost, context or {})) if self.margin else cost

    def describe(self) -> dict[str, Any]:
        """For the product's pricing metafield: how its prices were made."""
        return {"version": VERSION, "krwPerUsd": self.krw_per_usd, "rounding": self.rounding,
                "margin": None if self.margin is None else getattr(self.margin, "__name__", "custom")}


POLICIES = {"fairwardgolf": Policy()}


def policy(shop: str) -> Policy:
    return POLICIES.get(shop) or Policy()


def money(usd: int) -> str:
    """Shopify's decimal string for a whole-dollar amount: 1450 -> "1450.00"."""
    return f"{int(usd)}.00"
