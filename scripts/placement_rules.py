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

50002670 아이언 (2026-11-14): only women's iron sets, one section womens-iron-sets split by the same gender: unisex goes
there, and a mixed set too (one product, all its variants sold), a men's set and a set whose gender nothing states
are held (`unresolved`), never placed by the listing's query.

50002783 웨지 (2026-11-15): wedge sets, one section wedge-sets with no split (wedges are mostly unisex); single wedges
are left out by the title screen, not here.

50002796 티셔츠 (2026-11-21, the owner): women's fall long-sleeve golf tops, one section womens-fall-long-sleeve-tops
under apparel ("Women’s Long-Sleeve Golf Tops"), split by gender as the knits. Short sleeves, sleeveless, cardigans,
vests, outerwear, bottoms, sets, arm sleeves and summer cooling tops are left out by the title screen, not here.

50002799 재킷 (2026-11-21, the owner's decision): the same section as 50002798, the same split; a job of either takes
the other's listing rows (listing_title_rules.json `together`). Fleece, vests, light down and rainwear of both are
Rainwear & Midlayers' (not built yet: left out by the title screen), knits the cardigans' (left out too).

50002784 치퍼 (2026-11-18): chippers, one section chippers with no split (like wedge sets); putters, wedges and other
clubs filed under it are left out by the title screen, not here.

50002797 니트 (2026-11-19, the owner): women's golf knit cardigans, one section womens-knit-cardigans under the parent
apparel, split by gender as 50002670: unisex goes there, a mixed product too, a men's knit and a knit whose gender
nothing states are held (`unresolved`). Pullovers, vests and sets without a cardigan word, and titles without a
women's word, are left out by the title screen, not here.

50002798 점퍼 (2026-11-20, the owner): women's golf windbreakers, one section womens-windbreakers under the parent
apparel, split by gender as the knits: unisex goes there, a men's jumper and one whose gender nothing states are held
(`unresolved`). Padded and down jumpers, rainwear, vests and cardigans, and titles without a women's word, are left
out by the title screen, not here.

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
    stated_only: tuple[str, ...] = ()    # sections a value that implies several (unisex) does not reach: only a product
                                         # stated so goes there (50002796 men's, 2026-11-22: a unisex top keeps the
                                         # women's sizes; the men's section is the men's own, until the owner decides)


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
WOMENS_IRONS = Leaf("womens-iron-sets", "Women’s Iron Sets")    # owner 2026-11-14: women's iron sets only; a men's
                                                                   # or an unknown-gender set is held (unresolved)
WEDGES = Leaf("wedge-sets", "Wedge Sets")                          # owner 2026-11-15: wedge sets, no gender split
CHIPPERS = Leaf("chippers", "Chippers")                            # owner 2026-11-18: chippers, no split; the store's
                                                                   # collection fairwardgolf-chippers (tag rule
                                                                   # fairwardgolf:leaf:chippers) existed, empty
WOMENS_KNIT_CARDIGANS = Leaf("womens-knit-cardigans", "Women’s Golf Cardigans")   # owner 2026-11-19: women's knit
                                                                   # cardigans, parent apparel; the store's collection
                                                                   # fairwardgolf-womens-knit-cardigans: to check (A6)
WOMENS_LS_TOPS = Leaf("womens-fall-long-sleeve-tops", "Women’s Long-Sleeve Golf Tops")   # owner 2026-11-21:
                                                                   # the store's collection
                                                                   # fairwardgolf-womens-fall-long-sleeve-tops (tag
                                                                   # rule fairwardgolf:leaf:womens-fall-long-sleeve-tops)
                                                                   # existed, empty (checked 2026-11-21)
MENS_LS_TOPS = Leaf("mens-fall-long-sleeve-tops", "Men’s Long-Sleeve Golf Tops")   # owner 2026-11-21: the
                                                                   # collection fairwardgolf-mens-fall-long-sleeve-tops
                                                                   # (tag fairwardgolf:leaf:mens-fall-long-sleeve-tops)
                                                                   # existed, empty (checked 2026-11-21)
WOMENS_WINDBREAKERS = Leaf("womens-windbreakers", "Women’s Windbreakers")   # owner 2026-11-20: women's golf
                                                                   # windbreakers, parent apparel; the store's
                                                                   # collection fairwardgolf-womens-windbreakers
                                                                   # (tag rule fairwardgolf:leaf:womens-windbreakers)
                                                                   # existed, empty (checked 2026-11-20)

PROFILES = {
    StoreId.FAIRWARDGOLF: PlacementProfile(
        StoreId.FAIRWARDGOLF,
        categories={
            "50002788": CategoryPlacement(parent="clubs", split_by="gender",
                                          leaves={"mens": MENS, "womens": WOMENS}),
            "50002787": CategoryPlacement(parent="clubs", leaves={None: JUNIOR}),     # 주니어용클럽
            "50002670": CategoryPlacement(parent="clubs", split_by="gender",           # 아이언
                                          leaves={"womens": WOMENS_IRONS}),
            "50002783": CategoryPlacement(parent="clubs", leaves={None: WEDGES}),     # 웨지
            "50002784": CategoryPlacement(parent="clubs", leaves={None: CHIPPERS}),   # 치퍼
            "50002797": CategoryPlacement(parent="apparel", split_by="gender",         # 니트 (2026-11-19)
                                          leaves={"womens": WOMENS_KNIT_CARDIGANS}),
            "50002798": CategoryPlacement(parent="apparel", split_by="gender",         # 점퍼 (2026-11-20)
                                          leaves={"womens": WOMENS_WINDBREAKERS}),
            "50002796": CategoryPlacement(parent="apparel", split_by="gender",         # 티셔츠 (2026-11-21)
                                          leaves={"womens": WOMENS_LS_TOPS, "mens": MENS_LS_TOPS},   # men's 2026-11-22
                                          stated_only=("mens",)),
            "50002799": CategoryPlacement(parent="apparel", split_by="gender",         # 재킷 (2026-11-21)
                                          leaves={"womens": WOMENS_WINDBREAKERS}),
        }),
}


def profile_for(shop: str | StoreId) -> PlacementProfile:
    try:
        return PROFILES[StoreId(str(shop).strip().lower())]
    except (KeyError, ValueError):
        raise PlacementRulesMissing(f"{shop}: no placement profile for this shop yet (configured: "
                                    f"{', '.join(s.value for s in PROFILES)}); ask the operator") from None
