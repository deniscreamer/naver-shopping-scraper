"""Per-shop placement profiles (data): which of a shop's sections (Shopify leaves: collection handle, product type,
tags) a prepared product goes to, by its Naver leaf category id and, where one Naver id holds several of the shop's
sections, by a neutral attribute (attributes.py). Read by placement.py, the last stage before Shopify (the owner,
2026-11-08: the split happens there, not while a job collects; other shops may split other categories).

A new shop or a new category is a new entry here; a new kind of split is an attribute in attributes.ATTRIBUTES. The
profile says what an unresolved product does (`unresolved`): "hold" (not placed: the owner or the agent decides) or
a fallback section.

fairwardgolf (2026-11-08): Naver 50002788 풀세트 holds men's and women's sets; the shop sells them as two sections,
mens-complete-sets and womens-complete-sets (published by the naver-harvester with exactly those leaf tags, 6 of 6
checked 2026-11-05). The split is the gender the seller states (variants, the 성별 row, the title); unisex goes to
both; a set whose variants carry both genders goes to both, each section with its own variants.

    from placement_rules import profile_for
    profile = profile_for("fairwardgolf")
"""
from dataclasses import dataclass, field

from shop_stores import StoreId


class PlacementRulesMissing(Exception):
    """No placement profile for this shop or this Naver category: ask the operator."""


@dataclass(frozen=True)
class Leaf:
    handle: str                          # the shop's section, e.g. womens-complete-sets (a collection handle)
    product_type: str                    # Shopify productType of that section


@dataclass(frozen=True)
class CategoryPlacement:
    parent: str                          # the shop's parent collection, e.g. clubs
    leaves: dict[str | None, Leaf]       # an attribute value -> its section (None: the one section, no split)
    split_by: str | None = None          # the attribute that splits the category (attributes.ATTRIBUTES)
    unresolved: str = "hold"             # "hold", or a section handle of `leaves` for products the attribute leaves
                                         # unknown / in conflict


@dataclass(frozen=True)
class PlacementProfile:
    shop: StoreId
    categories: dict[str, CategoryPlacement] = field(default_factory=dict)   # Naver leaf category id -> placement
    tags: tuple[str, ...] = ("{shop}:leaf:{leaf}", "{shop}:parent:{parent}", "{shop}:showcase")

    def category(self, category_id: str | None) -> CategoryPlacement:
        found = self.categories.get(str(category_id))
        if found is None:
            raise PlacementRulesMissing(f"{self.shop.value}: no placement for Naver category {category_id}: ask the "
                                        "operator which sections it goes to")
        return found


WOMENS = Leaf("womens-complete-sets", "Women’s Complete Golf Sets")
MENS = Leaf("mens-complete-sets", "Men’s Complete Golf Sets")
JUNIOR = Leaf("junior-clubs-sets", "Junior Golf Clubs & Sets")    # owner 2026-11-11: single clubs and sets, one
                                                                   # section; age, height and club count not checked

PROFILES = {
    StoreId.FAIRWARDGOLF: PlacementProfile(
        StoreId.FAIRWARDGOLF,
        categories={
            "50002788": CategoryPlacement(parent="clubs", split_by="gender",
                                          leaves={"mens": MENS, "womens": WOMENS}),
            "50002787": CategoryPlacement(parent="clubs", leaves={None: JUNIOR}),     # 주니어용클럽
        }),
}


def profile_for(shop: str | StoreId) -> PlacementProfile:
    try:
        return PROFILES[StoreId(str(shop).strip().lower())]
    except (KeyError, ValueError):
        raise PlacementRulesMissing(f"{shop}: no placement profile for this shop yet (configured: "
                                    f"{', '.join(s.value for s in PROFILES)}); ask the operator") from None
