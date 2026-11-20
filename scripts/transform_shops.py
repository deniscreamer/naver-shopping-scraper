"""Per-shop rules of the transform (transform.py): data, not code. One ShopRules per configured shop.

What differs between shops is here; what is true of every Naver product is in transform.py. A rule moves from here
to transform.py only when a second shop needs it, and a shop gets code only when a real case cannot be said as data.

fairwardgolf, checked 2026-11-05 on the 60 products the naver-harvester published:
  * prices: 1000 KRW = 1 USD, no margin, rounded up to the cent (391 of 391 variants);
  * SKU "FW-" + 24 hex of the harvester's recipe (391 of 391, transform.sku);
  * the shop's sections (leaves, collections, product types) are not here: placement_rules.py, at the last stage
    before Shopify (the owner, 2026-11-08);
  * paid variants (a configuration that costs more or less), paid add-on products (추가상품) and the description
    images' OCR per category: off by default; all on for 50002788 (owner 2026-11-06, -07), and since for every
    fairwardgolf category below (50002787, 50002670, 50002783; 50002784 and 50002797 without paid add-ons, the owner
    2026-11-18, 2026-11-19);
  * `reviewed` per category (2026-11-16, draft first): publish.py creates a new product of a category not marked
    reviewed as DRAFT, for the agent's lens review and the owner's activation; reviewed() reads it;

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
    description_images: bool = False     # OCR the description images (description_images.py) and take the
                                         # package from them: what the seller states, else the set's parts; the
                                         # parts profile follows the Naver category id (description_measures)
    agency_needs_brand: bool = False     # a purchase agency's import with no brand anywhere is held (run_transform):
                                         # junior clubs, 2026-11-12, three no-name US sets resold at 631-689,000
                                         # KRW ($1499-1899), titles cut ("부 주니어 골프 세트 클럽 Ages 4-8 (44-49 )")
    sets_only: bool = False              # the section sells sets only: a variant that sells one club is left out, a
                                         # product of such variants only is held (single_only; transform: wedges,
                                         # 2026-11-15, "웨지 세트 또는 개별" listings of one wedge by loft)
    wedge_sets: bool = False             # the section sells wedge sets: a listing of an iron set or a full set filed
                                         # under it (an iron run "4-PW" / "3456789", 6 to 16 clubs, "아이언
                                         # 세트" without "웨지 세트") is held not_wedge_set (transform.not_wedge_set;
                                         # 2026-11-16, 9 iron sets published into wedge sets by the overnight scroll)
    gift_axis_out: bool = False          # an option axis that is the buyer's free gift (사은품 / 증정: a glove's size)
                                         # is left out, one variant per remaining choice (transform._drop_gift_axes;
                                         # chippers, 2026-11-18: Missile 10421264752 was 7 variants of one club). Off
                                         # elsewhere: on the sets' 11 such listings (9 live) the gift is a bag set, a
                                         # putter or a club the buyer picks; leaving it out there is the owner's word
    no_choice_out: bool = False          # an option value that says "no choice" (선택안함, 선택 안함, 없음, 필요없음,
                                         # 선택없음) is not a version: its rows go, an axis of nothing else goes
                                         # (transform._drop_no_choice; knit cardigans, the owner 2026-11-19). Off for
                                         # the clubs: their golden products stay as published. An axis of "no choice"
                                         # at +0 and the rest at extra cost is a paid add-on: left out with its axis
                                         # unless paid_addons (2026-11-20, DGB 10972881555's trousers)
    composition: bool = False            # the fibre composition rows (spec and notice rows 소재 / 혼용률 / 재질 /
                                         # 섬유의 조성) kept as product.composition_ko: the price's duty by the chief
                                         # fibre (shop_pricing) and the description's materials (knit cardigans,
                                         # the owner 2026-11-19)
    sizes: str | None = None             # apparel: the size option's Korean values -> US sizes, the seller's garment
                                         # measurements for the size chart (apparel_sizes.py, a size_profiles/<name>.json
                                         # profile; knit cardigans "womens_tops", the owner 2026-11-19); a value it
                                         # cannot read holds the product size_unmapped. None: the clubs, untouched
    own_brand_wordmark: bool = False     # a shop that shows its own brand (its Latin address read 3 times in its
                                         # texts, "브랜드 <name>", "<name>의 상표권") gives its name as the brand: the
                                         # fallback's step 5b, and a brand row the reseller rule dropped kept
                                         # (brand_fallback.own_brand_shown; knit cardigans, 2026-11-19: Grehip, Tee
                                         # And Golf). Off for the clubs: 56 club resellers' banners and URLs repeat
                                         # their slugs (도쿄피아, 렉스골프 ...), their brands are Mizuno, Yamaha
    reviewed: bool = False               # publish.py creates its new products ACTIVE; False: DRAFT, until the agent's
                                         # lens review and the owner's activation (2026-11-16: 369 products, 15.7%,
                                         # of those published were withdrawn later; each new category showed buyers
                                         # products of another section). Set True on the owner's word, dated.


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
                                      description_images=True,
                                      reviewed=True),       # 2026-11-16: live before draft first
            "50002787": CategoryRules(
                                      # owner 2026-11-11: junior clubs and sets, the full sets' rules (paid
                                      # configurations and add-ons, the images read); no parts profile
                                      paid_variants=True, paid_addons=True, description_images=True,
                                      reviewed=True),       # 2026-11-16: live before draft first
            "50002670": CategoryRules(
                                      # owner 2026-11-14: women's iron sets (아이언), the full sets' rules: paid
                                      # configurations (iron count, shaft) and add-ons, the images read, a
                                      # no parts profile
                                      paid_variants=True, paid_addons=True, description_images=True,
                                      reviewed=True),       # 2026-11-16: live before draft first
            # 2026-11-15, the owner: a no-brand agency import is no longer held in any category; its vendor is the
            # shop's name (노브랜드 -> Store.publisher, "Fairward Golf"). agency_needs_brand stays for another shop.
            "50002783": CategoryRules(
                                      # owner 2026-11-15: wedge sets (웨지), the iron sets' rules: paid
                                      # configurations (lofts, shaft) and add-ons, the images read; no parts profile; sets only (a
                                      # single wedge's variant out, 2026-11-15)
                                      paid_variants=True, paid_addons=True, description_images=True,
                                      sets_only=True, reviewed=True,    # 2026-11-16: live before draft first
                                      # 2026-11-16: Naver files iron sets and full sets under wedges too (13370424163
                                      # Cleveland ZipCore XL iron set published as a wedge set): held not_wedge_set
                                      wedge_sets=True),
            "50002784": CategoryRules(
                                      # owner 2026-11-18: chippers (치퍼), one club each: paid variants (a loft,
                                      # a length, a shaft that changes the price) sold, paid add-ons not (a cover or
                                      # a glove offered for money stays off), the images read; no parts profile; not a
                                      # set section (no sets_only, no wedge_sets)
                                      paid_variants=True, paid_addons=False, description_images=True,
                                      # 2026-11-18, the chipper review (the owner's delegation): a free gift's
                                      # sizes are not versions of the club
                                      gift_axis_out=True,
                                      reviewed=True),       # the owner 2026-11-19: 90 drafts activated after the lens review
            "50002797": CategoryRules(
                                      # owner 2026-11-19: women's golf knit cardigans (니트), the first apparel:
                                      # paid variants sold (a plus size, 88 / XL, often costs 5,000 KRW more and
                                      # would vanish), paid add-ons not (gift wrap, a shopping bag, a matching hat
                                      # are not the product), the images read (the owner wants the size charts
                                      # for the analysis); not a set section (no sets_only, no wedge_sets)
                                      paid_variants=True, paid_addons=False, description_images=True,
                                      gift_axis_out=True,   # a free gift's sizes are not versions of the cardigan
                                      no_choice_out=True,   # "선택안함" / "없음" values are not versions
                                      composition=True,     # the fibre rows: the description's materials
                                      sizes="womens_tops",  # US sizes and the size chart (the owner 2026-11-19)
                                      own_brand_wordmark=True,   # the shop's own brand (Grehip, Tee And Golf)
                                      reviewed=False),      # a new category: DRAFT until the lens review and the
                                                            # owner's activation
        }),
}


def without_paid(rules: ShopRules) -> ShopRules:
    """The shop's rules with every category's paid variants and paid add-ons off: a run that takes only what costs
    nothing extra (a job made without --paid; the owner, 2026-11-09, the 100-product pilot)."""
    from dataclasses import replace
    return replace(rules, categories={k: replace(c, paid_variants=False, paid_addons=False)
                                      for k, c in rules.categories.items()})


def without_paid_addons(rules: ShopRules) -> ShopRules:
    """The shop's rules with paid variants as the category allows them and every paid add-on off (a job made with
    --paid-variants; the owner, 2026-11-11: paid variants yes, paid add-ons no)."""
    from dataclasses import replace
    return replace(rules, categories={k: replace(c, paid_addons=False) for k, c in rules.categories.items()})


def rules_for(shop: str | StoreId) -> ShopRules:
    try:
        return RULES[StoreId(str(shop).strip().lower())]
    except (KeyError, ValueError):
        raise ShopRulesMissing(f"{shop}: no transform rules for this shop yet (configured: "
                               f"{', '.join(s.value for s in RULES)}); ask the operator") from None


def reviewed(shop: str | StoreId, category_id: str | None) -> bool:
    """Is this Naver category marked reviewed for the shop (publish.py creates its products ACTIVE)? False for a
    shop or a category with no rules here; never raises."""
    try:
        rules = rules_for(shop).categories.get(str(category_id))
    except ShopRulesMissing:
        return False
    return bool(rules and rules.reviewed)
