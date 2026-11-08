"""Per-shop rules of the transform (transform.py): data, not code. One ShopRules per configured shop.

What differs between shops is here; what is true of every Naver product is in transform.py. A rule moves from here
to transform.py only when a second shop needs it, and a shop gets code only when a real case cannot be said as data.

fairwardgolf, checked 2026-11-05 on the 60 products the naver-harvester published:
  * prices: 1000 KRW = 1 USD, no margin, rounded up to the cent (391 of 391 variants);
  * SKU "FW-" + 24 hex of the harvester's recipe (391 of 391, transform.sku);
  * the shop's sections (leaves, collections, product types) are not here: placement_rules.py, at the last stage
    before Shopify (the owner, 2026-11-08);
  * paid variants (a configuration that costs more or less), paid add-on products (추가상품) and the description
    images' OCR per category: off by default, all on for 50002788 (owner 2026-11-06, -07);

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
class CategoryRules:
    paid_variants: bool = False          # also sell the variants that change the price (naver_variants paid=True)
    paid_addons: bool = False            # also offer add-on products (추가상품) that cost money
    description_images: bool = False     # OCR the description images (description_images.py) and guess the
                                         # package from them: the larger of that and today's value wins; the
                                         # parts profile follows the Naver category id (description_measures)


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
                                   f"({name or '?'}): ask the operator for its rules (paid variants, paid add-ons, "
                                   "description images); its sections go in placement_rules.py")
        return rules


RULES = {
    StoreId.FAIRWARDGOLF: ShopRules(
        StoreId.FAIRWARDGOLF, sku_prefix="FW-", krw_per_usd=1000, variant_cap=100,
        categories={
            "50002788": CategoryRules(
                                      # owner 2026-11-06: sets are sold with their paid configurations and
                                      # paid add-ons too. The photos of a set often show the extras (bag,
                                      # covers, utility clubs); sold without them, a buyer takes them as part
                                      # of the set. Offered with their prices, the photo matches what is
                                      # sold (4 of 40 sold a smaller set than the title without them; 13 of
                                      # 40 have paid add-ons). A per-category choice: off elsewhere.
                                      paid_variants=True, paid_addons=True,
                                      # owner 2026-11-07: the images state the parts (club weights and
                                      # lengths, the bag's weight and size); OCR study on the 50 sets
                                      # (its parts profile: description_measures.CATEGORY_PROFILES)
                                      description_images=True),
        }),
}


def rules_for(shop: str | StoreId) -> ShopRules:
    try:
        return RULES[StoreId(str(shop).strip().lower())]
    except (KeyError, ValueError):
        raise ShopRulesMissing(f"{shop}: no transform rules for this shop yet (configured: "
                               f"{', '.join(s.value for s in RULES)}); ask the operator") from None
