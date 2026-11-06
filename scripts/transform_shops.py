"""Per-shop rules of the transform (transform.py): data, not code. One ShopRules per configured shop.

What differs between shops is here; what is true of every Naver product is in transform.py. A rule moves from here
to transform.py only when a second shop needs it, and a shop gets code only when a real case cannot be said as data.

fairwardgolf, checked 2026-11-05 on the 60 products the naver-harvester published:
  * prices: 1000 KRW = 1 USD, no margin, rounded up to the cent (391 of 391 variants);
  * SKU "FW-" + 24 hex of the harvester's recipe (391 of 391, transform.sku);
  * a Naver leaf category maps to the shop's own leaves by a spec row: 50002788 풀세트 by 성별 (여성용 -> women's
    sets, 남성용 -> men's, 남녀공용 -> both; 6 of 6 collected products carry exactly those leaf tags), and by words
    in the name when the row is missing (2 of 10), or in the option values when the name has none;
  * paid variants (a configuration that costs more or less) and paid add-on products (추가상품) per category:
    off by default, both on for 50002788 (owner 2026-11-06);
  * tags fairwardgolf:leaf:<leaf>, fairwardgolf:parent:<parent>, fairwardgolf:showcase.

A shop or a Naver category with no rules here raises ShopRulesMissing: the run stops and asks the operator,
like package_measures.CategoryDefaultsMissing.

    from transform_shops import rules_for
    rules = rules_for("fairwardgolf")
"""
from dataclasses import dataclass, field

from shop_stores import StoreId


class ShopRulesMissing(Exception):
    """No transform rules for this shop or this Naver category: ask the operator."""


@dataclass(frozen=True)
class Leaf:
    handle: str                          # the shop's leaf, e.g. womens-complete-sets
    product_type: str                    # Shopify productType of that leaf


@dataclass(frozen=True)
class CategoryRules:
    parent: str                          # the shop's parent collection, e.g. clubs
    by_row: str | None                   # the 상품정보 row that picks the leaves (None: always `leaves[None]`)
    leaves: dict[str | None, tuple[Leaf, ...]]      # the row's value -> the shop's leaves
    by_title: dict[str, tuple[Leaf, ...]] = field(default_factory=dict)   # no such row: words in the name
    paid_variants: bool = False          # also sell the variants that change the price (naver_variants paid=True)
    paid_addons: bool = False            # also offer add-on products (추가상품) that cost money


@dataclass(frozen=True)
class ShopRules:
    shop: StoreId
    sku_prefix: str
    krw_per_usd: int                     # KRW per 1 USD of price
    variant_cap: int                     # Shopify variants per product; more -> held
    categories: dict[str, CategoryRules] = field(default_factory=dict)      # Naver leaf category id -> rules

    def category(self, category_id: str | None, name: str | None = None) -> CategoryRules:
        rules = self.categories.get(str(category_id))
        if rules is None:
            raise ShopRulesMissing(f"{self.shop.value}: no transform rules for Naver category {category_id} "
                                   f"({name or '?'}): ask the operator which shop leaves it maps to")
        return rules


WOMENS = Leaf("womens-complete-sets", "Women’s Complete Golf Sets")
MENS = Leaf("mens-complete-sets", "Men’s Complete Golf Sets")

RULES = {
    StoreId.FAIRWARDGOLF: ShopRules(
        StoreId.FAIRWARDGOLF, sku_prefix="FW-", krw_per_usd=1000, variant_cap=100,
        categories={
            # no 성별 row on 2 of 10 collected sets (thegolf 8357720534 "... 여성용 ...", golfzonmarket 12945108653
            # "젝시오13 여성 풀세트"; both published as women's sets): the name decides then
            "50002788": CategoryRules(parent="clubs", by_row="성별",
                                      leaves={"여성용": (WOMENS,), "남성용": (MENS,), "남녀공용": (MENS, WOMENS)},
                                      by_title={"여성": (WOMENS,), "남성": (MENS,), "남녀": (MENS, WOMENS),
                                                "남여": (MENS, WOMENS)},
                                      # owner 2026-11-06: sets are sold with their paid configurations and
                                      # paid add-ons too. The photos of a set often show the extras (bag,
                                      # covers, utility clubs); sold without them, a buyer takes them as part
                                      # of the set. Offered with their prices, the photo matches what is
                                      # sold (4 of 40 sold a smaller set than the title without them; 13 of
                                      # 40 have paid add-ons). A per-category choice: off elsewhere.
                                      paid_variants=True, paid_addons=True),
        }),
}


def rules_for(shop: str | StoreId) -> ShopRules:
    try:
        return RULES[StoreId(str(shop).strip().lower())]
    except (KeyError, ValueError):
        raise ShopRulesMissing(f"{shop}: no transform rules for this shop yet (configured: "
                               f"{', '.join(s.value for s in RULES)}); ask the operator") from None
