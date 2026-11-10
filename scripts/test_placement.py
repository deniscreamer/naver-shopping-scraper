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
M, W = "mens-complete-sets", "womens-complete-sets"

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
}
SPLIT = {"13369469193": ("unisex", {M: 3, W: 3}),        # 성별 남녀공용: each section every variant
         "7583123963": ("mixed", {M: 6, W: 3}),          # variants of both genders: each section its own
         "9868413561": ("mixed", {M: 1, W: 1})}


def prepared(name):
    with open(os.path.join(FX, "collected", name + ".json"), encoding="utf-8") as f:
        line = json.load(f)
    sidecar = os.path.join(FX, "description_images", name + ".json")
    images = json.load(open(sidecar, encoding="utf-8")) if os.path.isfile(sidecar) else None
    return prepare(line, rules_for("fairwardgolf"), "50002788-fixtures", 1, images)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture_sets_go_to_their_sections(name):
    got = PL.place(prepared(name), PROFILE)
    assert got["status"] == "placed" and tuple(sorted(x["leaf"] for x in got["leaves"])) == EXPECTED[name]
    if name in SPLIT:
        value, counts = SPLIT[name]
        assert got["value"] == value and {x["leaf"]: len(x["fit_skus"]) for x in got["leaves"]} == counts
    assert got["tags"] == list(dict.fromkeys(t for x in got["leaves"] for t in x["tags"]))   # one product, all tags
    for leaf in got["leaves"]:
        assert leaf["tags"] == [f"fairwardgolf:leaf:{leaf['leaf']}", "fairwardgolf:parent:clubs", "fairwardgolf:showcase"]


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
