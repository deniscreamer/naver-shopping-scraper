"""Offline tests for the men's / women's split of golf full sets (Naver 50002788): the neutral gender attribute
(attributes.py, written by the transform) and the shop's placement (placement.py + placement_rules.py), on the 50
fixture products and on small cases of the rules. Fast, no network.

    .venv/bin/python -m pytest scripts/test_placement.py -q
"""
import json
import os

import pytest

import attributes as A
import placement as PL
from placement_rules import CategoryPlacement, Leaf, PlacementProfile, profile_for
from shop_stores import StoreId
from transform import prepare
from transform_shops import rules_for

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")
PROFILE = profile_for("fairwardgolf")
M, W, J = "mens-complete-sets", "womens-complete-sets", "junior-clubs-sets"
KNITS, WIND, PANTS = "womens-knit-cardigans", "womens-windbreakers", "golf-pants"
TOPS_W, TOPS_M = "womens-fall-long-sleeve-tops", "mens-fall-long-sleeve-tops"

# The 50 fixture sets (2026-11-08): the sections they go to, the same as the leaves the transform decided before
# the split moved to placement (prepared/2), and how many variants each section lists where a set is split.
EXPECTED = {
    "10302181901": (M,), "10337644911": (M,), "10639350746": (M,), "10816781893": (W,), "10857289010": (M,),
    "10954221464": (M,), "11042680586": (M,), "11256507948": (M,), "11528356176": (M,), "11635855564": (M,),
    "12274419597": (M,), "12696567111": (M,), "12863028632": (M,), "12950788305": (M,), "12975257923": (M,),
    "12999501692": (M,), "13002235969": (M,), "13002289437": (M,), "13026991307": (M,), "13049116377": (M,),
    "13058200331": (M,), "13058280430": (M,), "13099257309": (M,), "13302492097": (W,), "13369469193": (M, W),
    "13413924099": (W,), "13446843026": (W,), "13462927626": (M,), "13553116678": (W,), "13728190518": (M,),
    "13734679551": (W,), "13741767690": (W,), "13753294507": (M,), "13753356116": (M,), "13777887875": (M,),
    "13780241403": (M,), "13785630702": (M,), "5182294301": (M,), "6153061020": (M,), "6540695739": (W,),
    "6630856593": (M,), "6774818843": (M,), "6999516176": (M,), "7166885441": (M,), "7583123963": (M, W),
    "8958060680": (M,), "8978750961": (M,), "9168175809": (M,), "9496523995": (M,), "9868413561": (M, W),
    # 50002787 junior clubs (2026-11-12): one section, whatever a variant's gender
    "9498347018": (J,), "7151166811": (J,), "12552413383": (J,), "8457258079": (J,), "271986826": (J,),
    "11674983361": (J,), "5396141262": (J,), "5140543074": (J,), "5558127399": (J,), "4194532081": (J,),
    "11456066068": (J,), "11780616123": (J,), "13256185420": (J,), "13853234379": (J,), "8742181933": (J,),
    # 50002783 wedge sets (2026-11-16, the title rules' fixture: an import title's appended option)
    "13468791008": ("wedge-sets",),
    # (2026-11-17, the wedge-set review's variants and options: MG5 slots, Amazon's echoed axes and cut values, Miura
    # heads only, a description switch, a loft row against the title, the hand, a bare P)
    "12742411646": ("wedge-sets",), "13754846756": ("wedge-sets",), "13391457160": ("wedge-sets",),
    "13401325702": ("wedge-sets",), "11585678496": ("wedge-sets",),
    "12872703429": ("wedge-sets",), "13017295953": ("wedge-sets",), "12482367407": ("wedge-sets",),
    "13370297764": ("wedge-sets",), "13377524996": ("wedge-sets",), "13422541936": ("wedge-sets",),
    # (2026-11-17, C67: an agency's 단조 on the title, its page silent: note title_word_unproven)
    "13383747280": ("wedge-sets",), "12742304001": ("wedge-sets",),
    # (2026-11-18, an Amazon axis named for another kind: "Shaft Material" over lengths, its look-alikes kept, a
    # Latin "Hand Orientation")
    "13390487313": ("wedge-sets",), "12079165169": ("wedge-sets",), "13164548371": ("wedge-sets",),
    "9703030793": (M,),
    # (2026-11-18, a choice of two loft sets written only in the text: Mirai 10504295292 held choice_in_text_only, the
    # look-alikes kept: one set with a stray second group, bundle groups with options, loft ranges, single lofts;
    # () = held by the transform, placement holds it with the transform's code)
    "10504295292": (), "10482586862": ("wedge-sets",), "12178280377": ("wedge-sets",),
    "13683785691": (), "13278647591": ("wedge-sets",), "11006400319": ("wedge-sets",),
    # (2026-11-18, the owner's spec row: the golfup ZESTAIM Ponytail template's 성별 남성용 on every listing, LABOUM
    # 12748958315 a women's build by its photos, 12748958200 left as the seller wrote it; a 성별 남성용 row against a
    # 여성 title, unresolved without an owner entry: UNRESOLVED)
    "12748958315": ("wedge-sets",), "12748958200": ("wedge-sets",), "12497168529": (),
    # 50002784 chippers (2026-11-18, the chipper review: rakuraku00's 브랜드 / 제조사 "brand", 치퍼 as a brand row and
    # in the title, a notice's 962 g out of the row's band, a free glove's sizes as the only axis)
    "9991649397": ("chippers",), "10179980640": ("chippers",), "11158899277": ("chippers",),
    "7004743758": ("chippers",), "10421264752": ("chippers",),
    # the chipper brands (2026-11-18): the shop 수수's own "수수협력사 co." as the 브랜드 / 제조사 rows (a Ben Sayers M5)
    "13800679830": ("chippers",),
    # the chipper bands (2026-11-18): rockible's Amazon package 13.77 x 5.9 x 2.75 in / 0.3 lb, MYKUJA's 330 g head
    "13261416672": ("chippers",), "13551983071": ("chippers",),
    # the two-brand scan (2026-11-19): titles the model wrote under an older brand ("Pongdang Swim", "PING" from 핑크)
    "13510579139": (J,), "13848307900": (J,),
    # the seller-vendor review (2026-11-19): 골드벙커, a store, as the maker of an Inparo set
    "13826709716": (J,),
    # apparel, the size_unmapped reviews (2026-11-24 / 2026-11-25, the owner: regression fixtures of the size rules;
    # scripts/SIZES.md "How to use"): one or two products per rule, and products that must stay held
    "5964063532": (KNITS,), "4260789645": (TOPS_W,), "13483086996": (WIND,), "7191019224": (PANTS,),
    "9918112671": (PANTS,), "12487907002": (WIND,), "13004790971": (KNITS,), "10940191023": (KNITS,),
    "7864006253": (PANTS,), "10968014964": (TOPS_W,), "13762280030": (TOPS_M,), "5815131892": (PANTS,),
    "7266270685": (TOPS_M, TOPS_W), "5691897960": ("rainwear-midlayers",), "7965635614": ("womens-skirts-culottes",),
    "9317474764": (TOPS_W,), "11493370731": (PANTS,), "9998916822": (TOPS_M,), "5489884876": (PANTS,),
    "12370291326": (PANTS,),
    # the two reviews and the owner's yes answers (2026-11-25): two cm spellings / two models on one waist, a half
    # waist range, "약80", 4XL, the cooling drop, a mixed product per gender, the owner's adidas Asian letters
    "11017948766": (PANTS,), "10076109143": (PANTS,), "5282622633": ("womens-skirts-culottes",),
    "5460564989": ("rainwear-midlayers",), "11859489664": ("rainwear-midlayers",), "9435597606": (TOPS_W,),
    "6485458095": (TOPS_M, TOPS_W), "13740514016": (TOPS_M,), "5176506757": (TOPS_M,),
    "754260851": (), "4509557063": (), "10332996284": (),
}
APPAREL = {KNITS, TOPS_W, TOPS_M, WIND, PANTS, "rainwear-midlayers", "womens-skirts-culottes"}
UNRESOLVED = {"12497168529": "gender conflict"}           # ready, placement holds it: the reason
SPLIT = {"13369469193": ("unisex", {M: 3, W: 3}),        # 성별 남녀공용: each section every variant
         "7583123963": ("mixed", {M: 6, W: 3}),          # variants of both genders: each section its own
         "9868413561": ("mixed", {M: 1, W: 1}),
         "7266270685": ("mixed", {TOPS_M: 6, TOPS_W: 6}),    # sized per gender (2026-11-25)
         "6485458095": ("mixed", {TOPS_M: 8, TOPS_W: 6})}


def prepared(name):
    with open(os.path.join(FX, "collected", name + ".json"), encoding="utf-8") as f:
        line = json.load(f)
    sidecar = os.path.join(FX, "description_images", name + ".json")
    images = json.load(open(sidecar, encoding="utf-8")) if os.path.isfile(sidecar) else None
    return prepare(line, rules_for("fairwardgolf"), "50002788-fixtures", 1, images)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture_sets_go_to_their_sections(name):
    got = PL.place(prepared(name), PROFILE)
    if name in UNRESOLVED:
        assert got["status"] == "unresolved" and got["leaves"] == [] and got["reason"] == UNRESOLVED[name]
        return
    if not EXPECTED[name]:                                 # held by the transform: nothing to place
        assert got["status"] == "held" and got["leaves"] == [] \
            and got["reason"] == ",".join(dict.fromkeys(h["code"] for h in prepared(name)["held"]))
        return
    assert got["status"] == "placed" and tuple(sorted(x["leaf"] for x in got["leaves"])) == EXPECTED[name]
    if name in SPLIT:
        value, counts = SPLIT[name]
        assert got["value"] == value and {x["leaf"]: len(x["fit_skus"]) for x in got["leaves"]} == counts
    assert got["tags"] == list(dict.fromkeys(t for x in got["leaves"] for t in x["tags"]))   # one product, all tags
    for leaf in got["leaves"]:
        parent = "apparel" if leaf["leaf"] in APPAREL else "clubs"
        assert leaf["tags"] == [f"fairwardgolf:leaf:{leaf['leaf']}", f"fairwardgolf:parent:{parent}", "fairwardgolf:showcase"]


def test_every_fixture_is_listed():
    names = {n[:-5] for n in os.listdir(os.path.join(FX, "collected")) if n.endswith(".json")}
    assert names == set(EXPECTED)


# ---- the rules, case by case --------------------------------------------------------------------------------

def gender(variants=(), rows=(), title=None, query=None):
    return A.decide(A.GENDER, [(f"s{i}", list(v)) for i, v in enumerate(variants)],
                    [{"label": label, "value": value} for label, value in rows], title, query)


@pytest.mark.parametrize("variants, rows, title, value", [
    ((), [("성별", "남성용")], "골프 풀세트", "mens"),                                   # the row
    ((), [("성별", "여성용")], None, "womens"),
    ((), [("성별", "남녀공용")], None, "unisex"),                                     # not also 남녀 -> both twice
    ((), [], "젝시오13 여성 풀세트", "womens"),                                       # no row: the title
    ((), [], "LADIES Golf Set", "womens"),
    ((), [], "MEN'S complete set", "mens"),
    ((), [], "WOMENS set", "womens"),                                               # MEN inside WOMENS is not men
    ((), [], "남녀 공용 입문 세트", "unisex"),
    ((), [], "골프 풀세트 10.5도 R", "unknown"),                                      # a flex, a loft: no gender
    ((), [("성별", "남성용")], "여성 풀세트", "conflict"),                             # the row and the title disagree
    ((["남성용-경량스틸"], ["남성용-그라파이트"], ["여성용-그라파이트"]), [("성별", "남성용")],
     "초중급 남성 골프채 풀세트", "mixed"),                                           # 13425122164: a women's variant
    ((["여성 L"], ["여성 A"]), [("성별", "남성용")], None, "conflict"),                # every variant the opposite
    ((["10.5 R"], ["9.5 S"]), [("성별", "남성용")], None, "mens"),                     # unmarked: the product's value
])
def test_gender_rules(variants, rows, title, value):
    assert gender(variants, rows, title)["value"] == value


def test_unmarked_variants_beside_marked_ones_are_the_other_gender():
    """8514409092: 성별 남녀공용, "뉴GR-V 백포함 (여성용)" beside "뉴GR-V 백포함": the plain one is the men's set."""
    got = gender([["뉴GR-V 백포함"], ["뉴GR-V 백포함 (여성용)"]], [("성별", "남녀공용")])
    assert got["value"] == "mixed" and got["variants"] == {"s0": "mens", "s1": "womens"}


def test_the_listing_query_flags_only():
    got = gender((), [("성별", "여성용")], None, query="남성 골프채 풀세트")
    assert got["value"] == "womens" and got["flags"] == ["listing_disagrees"]          # evidence, not a veto
    assert gender((), [], None, query="남성 골프채 풀세트")["value"] == "unknown"      # never decides


# ---- placement ----------------------------------------------------------------------------------------------

def product(value, variants=None, status="ready", category="50002788"):
    skus = list(variants or {"s1": None})
    return {"key": "fairwardgolf:naver:1:1", "status": status, "held": [{"code": "no_images"}] if status != "ready" else [],
            "source": {"category_id": category},
            "product": {"variants": [{"sku": s} for s in skus],
                        "attributes": {"gender": {"value": value, "variants": {k: v for k, v in (variants or {}).items()
                                                                               if v}, "evidence": [], "flags": []}}}}


def test_unknown_or_conflict_is_held_for_the_owner():
    for value in ("unknown", "conflict"):
        got = PL.place(product(value), PROFILE)
        assert got["status"] == "unresolved" and got["leaves"] == [] and got["reason"] == f"gender {value}"


def test_a_profile_fallback_section_instead_of_hold():
    cat = CategoryPlacement(parent="clubs", split_by="gender", unresolved=M,
                            leaves={"mens": Leaf(M, "Men"), "womens": Leaf(W, "Women")})
    profile = PlacementProfile(StoreId.FAIRWARDGOLF, {"50002788": cat})
    got = PL.place(product("unknown"), profile)
    assert got["status"] == "placed" and [x["leaf"] for x in got["leaves"]] == [M]


def test_held_products_and_unknown_categories_are_not_placed():
    assert PL.place(product("mens", status="held"), PROFILE)["status"] == "held"
    assert PL.place(product("mens", category="50000001"), PROFILE)["status"] == "no_profile"


def test_a_category_without_a_split_has_one_section():
    profile = PlacementProfile(StoreId.FAIRWARDGOLF, {"50002810": CategoryPlacement(
        parent="putting", leaves={None: Leaf("putting-mats", "Putting Mats")})})
    got = PL.place(product("unknown", category="50002810"), profile)
    assert got["status"] == "placed" and [x["leaf"] for x in got["leaves"]] == ["putting-mats"]
    assert got["product_type"] == "Putting Mats" and got["start_variants"] == {}


def test_mixed_sets_one_product_with_a_start_variant_per_collection():
    """GVTOUR 8514409092 in the harvester (2026-09-26): one Shopify product in both collections; from the men's one
    the men's variant opens, from the women's the women's; no variant is removed from the card."""
    got = PL.place(product("mixed", {"a": "mens", "b": "womens", "c": "unisex"}), PROFILE)
    assert {x["leaf"]: x["fit_skus"] for x in got["leaves"]} == {M: ["a", "c"], W: ["b", "c"]}
    assert got["start_variants"] == {M: "a", W: "b"}
    assert got["tags"] == [f"fairwardgolf:leaf:{M}", "fairwardgolf:parent:clubs", "fairwardgolf:showcase",
                           f"fairwardgolf:leaf:{W}"]


def test_unisex_is_one_product_in_both_collections_without_hints():
    got = PL.place(product("unisex", {"a": None, "b": None}), PROFILE)
    assert sorted(x["leaf"] for x in got["leaves"]) == [M, W] and got["start_variants"] == {}
    assert {f"fairwardgolf:leaf:{M}", f"fairwardgolf:leaf:{W}"} <= set(got["tags"])


def test_unknown_is_not_unisex():
    assert PL.place(product("unknown", {"a": None}), PROFILE)["leaves"] == []


def test_gvtour_46_mens_23_womens_in_one_product():
    """8514409092 GVTOUR (성별 남녀공용, "(여성용)" on a third of 69 tuples): 46 men's and 23 women's variants, as the
    harvester's live acceptance pinned them (2026-09-26); each collection opens its first own variant."""
    from test_transform import prep
    p = prep("8514409092")
    got = PL.place(p, PROFILE)
    fit = {x["leaf"]: x["fit_skus"] for x in got["leaves"]}
    assert (len(fit[M]), len(fit[W])) == (46, 23) and not set(fit[M]) & set(fit[W])
    skus = [v["sku"] for v in p["product"]["variants"]]
    assert got["start_variants"] == {M: fit[M][0], W: fit[W][0]} and skus.index(fit[M][0]) < skus.index(fit[W][0])
    women = next(v for v in p["product"]["variants"] if v["sku"] == fit[W][0])
    assert any("여성용" in o for o in women["options_ko"])


def test_a_gendered_title_beats_a_unisex_row():
    # 2026-11-09 pilot: "PGM 여성골프채풀세트" with 성별 남녀공용 went to the men's section too
    out = A.decide(A.ATTRIBUTES["gender"], [("s1", ["9P 스틸"])], [{"label": "성별", "value": "남녀공용"}],
                   "PGM 여성골프채풀세트", "여성 골프채 풀세트")
    assert out["value"] == "womens"
    both = A.decide(A.ATTRIBUTES["gender"], [("s1", ["9P"])], [{"label": "성별", "value": "남녀공용"}], "PGM 풀세트")
    assert both["value"] == "unisex"
    # 2026-11-22: (MAN), 맨즈, 멘즈 are men's words ("(MAN) 비스코스 캐시 라운드니트", 2SOM, row 남녀공용)
    man = A.decide(A.ATTRIBUTES["gender"], [("s1", ["M"])], [{"label": "성별", "value": "남녀공용"}],
                   "(MAN) 비스코스 캐시 라운드니트")
    assert man["value"] == "mens"
    assert A.values_in(A.ATTRIBUTES["gender"], "골프 맨즈 니트") == ["mens"]
    assert A.values_in(A.ATTRIBUTES["gender"], "MANSINGWEAR HUMAN 니트") == []


def test_junior_clubs_go_to_their_one_section_whatever_the_gender():
    """50002787 (the owner, 2026-11-11): single clubs and sets in Junior Golf Clubs & Sets, the store's collection
    fairwardgolf-junior-clubs-sets (tag rule fairwardgolf:leaf:junior-clubs-sets, read 2026-11-11)."""
    for value in ("unknown", "mens", "womens"):
        got = PL.place(product(value, category="50002787"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Junior Golf Clubs & Sets"
        assert got["tags"] == ["fairwardgolf:leaf:junior-clubs-sets", "fairwardgolf:parent:clubs",
                               "fairwardgolf:showcase"]


def test_wedge_sets_go_to_one_section_whatever_the_gender():
    """50002783 (the owner, 2026-11-15): wedge sets, one collection fairwardgolf-wedge-sets (tag rule
    fairwardgolf:leaf:wedge-sets, read 2026-11-15), no gender split."""
    for value in ("womens", "mens", "unisex", "unknown"):
        got = PL.place(product(value, category="50002783"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Wedge Sets"
        assert got["tags"] == ["fairwardgolf:leaf:wedge-sets", "fairwardgolf:parent:clubs", "fairwardgolf:showcase"]


def test_chippers_go_to_one_section_whatever_the_gender():
    """50002784 (the owner, 2026-11-18): chippers, the store's collection fairwardgolf-chippers (tag rule
    fairwardgolf:leaf:chippers, existing and empty that day), no split."""
    for value in ("womens", "mens", "unisex", "unknown"):
        got = PL.place(product(value, category="50002784"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Chippers"
        assert got["tags"] == ["fairwardgolf:leaf:chippers", "fairwardgolf:parent:clubs", "fairwardgolf:showcase"]


def test_iron_sets_go_to_the_womens_section_and_a_mens_or_unknown_set_is_held():
    """50002670 (the owner, 2026-11-14): women's iron sets only, the store's collection fairwardgolf-womens-iron-sets
    (tag rule fairwardgolf:leaf:womens-iron-sets, read 2026-11-14); unisex and mixed go there too."""
    for value in ("womens", "unisex"):
        got = PL.place(product(value, category="50002670"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Women’s Iron Sets"
        assert got["tags"] == ["fairwardgolf:leaf:womens-iron-sets", "fairwardgolf:parent:clubs",
                               "fairwardgolf:showcase"]
    mixed = PL.place(product("mixed", {"s1": "mens", "s2": "womens"}, category="50002670"), PROFILE)
    assert mixed["status"] == "placed" and mixed["leaves"][0]["fit_skus"] == ["s2"]
    for value in ("mens", "unknown", "conflict"):
        assert PL.place(product(value, category="50002670"), PROFILE)["status"] == "unresolved"


def test_knit_cardigans_go_to_the_womens_section_under_apparel_and_a_mens_or_unknown_knit_is_held():
    """50002797 (the owner, 2026-11-19): women's golf knit cardigans, the store's collection
    fairwardgolf-womens-knit-cardigans (tag rule), parent apparel; unisex and mixed go there, as 50002670."""
    for value in ("womens", "unisex"):
        got = PL.place(product(value, category="50002797"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Women’s Golf Cardigans"
        assert got["tags"] == ["fairwardgolf:leaf:womens-knit-cardigans", "fairwardgolf:parent:apparel",
                               "fairwardgolf:showcase"]
    mixed = PL.place(product("mixed", {"s1": "mens", "s2": "womens"}, category="50002797"), PROFILE)
    assert mixed["status"] == "placed" and {x["leaf"]: x["fit_skus"] for x in mixed["leaves"]} == {
        "womens-knit-cardigans": ["s2"], "mens-fall-long-sleeve-tops": ["s1"]}
    men = PL.place(product("mens", category="50002797"), PROFILE)    # the men's knits: men's tops (2026-11-22)
    assert men["status"] == "placed" and men["product_type"] == "Men’s Long-Sleeve Golf Tops"
    for value in ("unknown", "conflict"):
        assert PL.place(product(value, category="50002797"), PROFILE)["status"] == "unresolved"


def test_windbreakers_go_to_the_womens_section_under_apparel_and_a_mens_or_unknown_one_is_held():
    """50002798 (the owner, 2026-11-20): women's golf windbreakers, the store's collection
    fairwardgolf-womens-windbreakers (tag rule fairwardgolf:leaf:womens-windbreakers), parent apparel; as the knits."""
    for value in ("womens", "unisex"):
        got = PL.place(product(value, category="50002798"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Women’s Windbreakers"
        assert got["tags"] == ["fairwardgolf:leaf:womens-windbreakers", "fairwardgolf:parent:apparel",
                               "fairwardgolf:showcase"]
    for value in ("mens", "unknown", "conflict"):
        assert PL.place(product(value, category="50002798"), PROFILE)["status"] == "unresolved"
    for value in ("womens", "unisex"):                                     # 재킷 (2026-11-21): the same section
        assert PL.place(product(value, category="50002799"), PROFILE)["product_type"] == "Women’s Windbreakers"
    assert PL.place(product("mens", category="50002799"), PROFILE)["status"] == "unresolved"


def test_long_sleeve_tops_go_to_their_womens_section_under_apparel():
    """50002796 (the owner, 2026-11-21): the store's collection fairwardgolf-womens-fall-long-sleeve-tops."""
    for value in ("womens",):
        got = PL.place(product(value, category="50002796"), PROFILE)
        assert got["status"] == "placed" and got["product_type"] == "Women’s Long-Sleeve Golf Tops"
        assert got["tags"][:2] == ["fairwardgolf:leaf:womens-fall-long-sleeve-tops", "fairwardgolf:parent:apparel"]
    men = PL.place(product("mens", category="50002796"), PROFILE)            # the men's section (2026-11-21)
    assert men["status"] == "placed" and men["product_type"] == "Men’s Long-Sleeve Golf Tops"
    assert men["tags"][:2] == ["fairwardgolf:leaf:mens-fall-long-sleeve-tops", "fairwardgolf:parent:apparel"]
    uni = PL.place(product("unisex", category="50002796"), PROFILE)   # unisex: the women's only (stated_only, 11-22)
    assert {x["leaf"] for x in uni["leaves"]} == {"womens-fall-long-sleeve-tops"}
