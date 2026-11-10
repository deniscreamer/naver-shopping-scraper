"""Offline tests for the package fields read from the description's text (description_measures.py): what the
seller states (guess), what the set's parts compose (compose), the merge and the confidence levels 1-5.

Two parts: the core (any category: stated packed / set / product values, no profile) and the golf_set profile
(clubs + the bag). The golf rows are RapidOCR rows of real fixture products (fixtures/description_images/,
OCR study 2026-11-07), quoted as read; the core's rows are how sellers of other categories write it. The last
part (2026-11-10) quotes OCR rows and typed description lines of the 120 collected sets, product id beside each.
The baselines are the operator's own (category_measures.json, row 50002788).

    .venv/bin/python -m pytest scripts/test_description_measures.py -q
"""
import description_measures as D
from package_measures import load_table

GOLF = D.GOLF_SET
BASE = load_table()["rows"][0]["baselines"]         # club 340 g, bag 3800 g, carton 2000 g, driver 1140 + 100 mm,
                                                    # sides 200 x 160 without a bag, 400 x 320 with one
DEFAULT = {"low": 4500, "central": 7000, "high": 11000, "source": "category_default", "confidence": 1}


def fields(**over):
    base = {"product_weight_g": {**DEFAULT, "central": 5700}, "package_weight_g": dict(DEFAULT),
            "package_length_mm": {**DEFAULT, "central": 1250}, "package_width_mm": {**DEFAULT, "central": 280},
            "package_height_mm": {**DEFAULT, "central": 230}}
    return {**base, **over}


def values(g):
    return {k: v["value"]["max"] for k, v in g.items()}


def made(facts, count, bag):
    """The composition with the operator's baselines."""
    return D.compose(facts, count, bag, GOLF, BASE)


def packed(facts, count, bag, **over):
    """One variant's fields: the statements and the composition merged over the defaults (or `over`)."""
    return D.package_for(fields(**over), facts, count, bag, None, GOLF, BASE)[0]


def brief(field):
    return field["value"]["max"], field["confidence"], field["how"]


# ---- the core: any category, no profile ---------------------------------------------------------------------

def test_core_chair_stated_weight_and_size():
    """A camping chair: "제품 무게 / 2.3kg", "사이즈 / 60 x 55 x 90cm". The weight is the product's; its size is read
    as a fact and is no field's (a product is not its box)."""
    f = D.read_rows([["모델명 / CX-200", "제품 무게 / 2.3kg", "사이즈 / 60 x 55 x 90cm", "소재 / 알루미늄"]])
    assert values(D.guess(f)) == {"product_weight_g": 2300} and f["product_sizes"][0]["mm"] == [900, 600, 550]


def test_core_plain_weight_row_and_product_size_label():
    f = D.read_rows([["무게 / 약 12.5kg", "제품 크기(가로x세로x높이) / 450 x 380 x 620 mm"]])
    g = D.guess(f)
    assert brief(g["product_weight_g"]) == (12500, 4, "stated weight") and f["product_sizes"][0]["mm"][0] == 620


def test_core_packed_box_from_an_image_is_4():
    """An image's reading is never a seller's typed value: a stated box or weight from OCR is 4, typed 5."""
    f = D.read_rows([["박스 사이즈 130 x 32 x 30 cm / 포장 무게 9.2kg", "풀세트 총 무게 약 7.8kg"]])
    g = D.guess(f)
    assert brief(g["package_weight_g"]) == (9200, 4, "stated packed weight")
    assert brief(g["product_weight_g"]) == (7800, 4, "stated set weight")
    assert [brief(g[n]) for n in D.FIELDS[2:]] == [(v, 4, "stated box size") for v in (1300, 320, 300)]


def test_core_packed_weight_under_the_sellers_product_weight_is_flagged():
    """A stated packed weight is the seller's word: taken, also under the product's weight. When that weight is
    the seller's own too (4-5) the two contradict: `flags: ["below_contents"]`, both kept (the operator decides).
    With a carton baseline the same: a statement goes before the composition (product + carton)."""
    f = D.read_rows([["제품 중량 / 5kg"], ["포장 무게 3kg"]])
    for base in (None, BASE):
        out, taken = D.merge_fields(fields(), D.guess(f), baselines=base)
        assert taken == ["product_weight_g", "package_weight_g"]
        assert brief(out["product_weight_g"]) == (5000, 4, "stated set weight")
        assert brief(out["package_weight_g"]) == (3000, 4, "stated packed weight")
        assert out["package_weight_g"]["flags"] == ["below_contents"]
        assert out["package_weight_g"]["compared"] == {"value": 7000, "source": "category_default", "confidence": 1}
    f = D.read_rows([["제품 중량 / 5kg"], ["포장 무게 6kg"]])                        # in order: no flag
    assert "flags" not in D.merge_fields(fields(), D.guess(f))[0]["package_weight_g"]


def test_core_never_reads_rules_people_prices_cross_sell():
    f = D.read_rows([["©상품의 무게가20kg가 초과하거나.택배 부피가 큰 경우 화물택배로인계될 수 있습니다",
                      "분유, 꿀: 5kg 이하 통관 가능", "체형 남성 · 182cm · 84kg", "무게 3.5kg 가격 150,000원"],
                     ["함께 구매하면 좋은 상품", "사이즈 10 x 7 x 126cm", "무게 2.5kg"]])
    assert D.guess(f) == {}


def test_core_has_no_parts_without_a_profile():
    """Club tables mean nothing to the core: no item sums, no container."""
    f = D.read_rows([["클럽 중량(g) / 310 / 306 / 304", "캐디백 무게 / 4.1kg", "45.5인치"]])
    assert not f["item_weights"] and not f["container_weights"] and not f["item_lengths"]
    assert D.guess(f) == {}                     # "캐디백 무게" is no product weight label


# ---- golf_set profile -----------------------------------------------------------------------------------------

def test_club_weights_from_labelled_rows_only():
    """10337644911: the club row counts, the shaft row (a part) does not."""
    f = D.read_rows([["클럽 중량(g) / 310 / 306 / 304 / 약318 / 316 / 313 / #3-약344 / 338 / 335",
                      "샤프트중량(g) / 58 / 56 / 54 / 58 / 56 / 54 / 68 / 64 / 60",
                      "헤드중량(g) / 252 / 259 / 266"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [310, 306, 304, 318, 316, 313, 344, 338, 335]


def test_club_weight_glued_and_with_flex():
    f = D.read_rows([["클럽중량(g) / 약304g / 약301g / 약298g", "총 중량(g) / 밸런스 / 약 300g / D3 (ALTA J CB BLUE.SR.46인치)"]],
                    GOLF)
    assert [x["g"] for x in f["item_weights"]] == [304, 301, 298, 300]
    assert [x["mm"] for x in f["item_lengths"]] == [1168]           # 46" in the same row


def test_bag_triple_sets_three_sides():
    """13446843026: the PRGR caddie bag, sides after their units."""
    f = D.read_rows([["캐디백 PRGR", "사이즈:캐디백-91cm(세로)*31cm(폭)*40cm(가로),"]], GOLF)
    assert [x["mm"] for x in f["container_long"]] == [910]
    assert [x["mm"] for x in f["container_sides"]] == [[400, 310]]


def test_bag_weight_and_mouth_in_a_bag_table():
    """12696567111: the stand bag's own table."""
    f = D.read_rows([["XR 24 스탠드백", "사이즈 / 남성용9인치|무게 약 4.1kg |높이 약89cm"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [4100] and not f["product_weights"]
    assert [x["mm"] for x in f["container_sides"]] == [[229, 229]]
    assert [x["mm"] for x in f["container_long"]] == [890]


def test_cross_sell_block_runs_to_the_end_of_the_image():
    """13369469193: the shop's cross-sell cards (half bag 10x7x126 cm) below 함께 구매."""
    f = D.read_rows([["함께 구매하면 좋은 상품", "미즈노 하프백", "-길이: 약10X7X126(CM)", "무게 2.5kg"],
                     ["캐디백 무게 / 3.5kg"]], GOLF)
    assert not f["container_long"] and [x["g"] for x in f["container_weights"]] == [3500]


def test_bag_words():
    f = D.read_rows([["※ 본 풀세트는 골프백 미포함 제품입니다"], ["12종+캐디백 포함"]], GOLF)
    assert len(f["container_no"]) == 1 and len(f["container_yes"]) == 1
    assert D.container_in("남성 풀세트 + 캐디백", GOLF) is True and D.container_in("골프백 미포함", GOLF) is False
    assert D.container_in("10PCS", GOLF) is None and D.container_in("캐디백 포함", None) is None


def test_bag_in_other_no_words():
    assert D.container_in("캐디백 별도구매", GOLF) is False and D.container_in("캐디백 없음", GOLF) is False
    assert D.container_in("XR26 풀세트 백포함", GOLF) is True


def test_image_count_most_frequent():
    f = D.read_rows([["11PCS 풀세트", "구성 11PCS", "드라이버 3PCS"]], GOLF)
    assert D.image_count(f) == 11


def test_compose_clubs_and_bag():
    """7583123963 (13 PCS, 백세트포함): 13 clubs and the bag set's own weight (캐디백+보스턴백 4.95 kg). Three weights
    read of 13 clubs are not the set: the baseline club."""
    f = D.read_rows([["헤드체적(cc) / 460cc"],
                     ["클럽중량(g) / 300g / 310g / 320g", "BM 캐디백 세트", "소재:PVC 코팅면/총무게:(캐디백+보스턴백)약4.95kg"]],
                    GOLF)
    g = made(f, 13, True)["product_weight_g"]
    assert brief(g) == (13 * 340 + 4950, 2, "clubs + bag")
    assert g["parts"] == [
        {"part": "clubs", "value": 4420, "from": "13 clubs x baseline club weight", "count_from": "listing"},
        {"part": "bag", "value": 4950, "from": "stated", "quote": "소재:PVC 코팅면/총무게:(캐디백+보스턴백)약4.95kg",
         "said_by": "listing"}]
    assert g["baseline"] == {"approved_by": "owner", "approved_at": "2026-11-10"}
    g = made(f, 13, False)["product_weight_g"]                                     # no bag in this variant
    assert brief(g) == (4420, 2, "clubs, no bag") and g["parts"][1]["from"] == "not in the set"


def test_compose_needs_a_count_for_the_weight():
    f = D.read_rows([["클럽중량(g) / 300g / 310g"]], GOLF)
    assert sorted(made(f, None, False)) == ["package_height_mm", "package_length_mm", "package_width_mm"]


def test_no_bag_takes_the_sides_without_one():
    """An image's sentence is the only word on the bag: a weak part, said so."""
    f = D.read_rows([["캐디백", "사이즈:캐디백-91cm(세로)*31cm(폭)*40cm(가로),"], ["골프백 미포함"],
                     ["길이 / 45.5\""]], GOLF)
    g = made(f, 10, None)
    assert values(g) == {"product_weight_g": 3400, "package_length_mm": 1256, "package_width_mm": 200,
                         "package_height_mm": 160}
    assert g["package_width_mm"]["parts"] == [{"part": "box side", "value": 200, "from": "baseline",
                                               "said_by": "description_image"}]
    assert values(made(f, 10, True))["package_width_mm"] == 400                   # the listing says a bag


def test_set_weight_near_a_bag_is_the_sets_not_the_bags():
    """Review 2026-11-07: "캐디백 포함 풀세트 무게 약 7.5kg" was taken as the bag and added to the clubs (11.2 kg)."""
    f = D.read_rows([["클럽 중량(g) / 300 / 310 / 320", "캐디백 사이즈 9인치", "캐디백 포함 풀세트 무게 약 7.5kg"]], GOLF)
    assert [x["g"] for x in f["set_weights"]] == [7500] and not f["container_weights"]
    assert brief(D.guess(f, GOLF)["product_weight_g"]) == (7500, 4, "stated set weight")
    assert packed(f, 12, True)["product_weight_g"]["how"] == "stated set weight"   # stated beats the composition


def test_composition_line_does_not_hide_the_club_table():
    """6630856593: "우드(1/3/5 하이브리드):4개 / 골프백:1개" above the woods' rows (45" driver)."""
    f = D.read_rows([["_12개 클럽+1개 골프가방", "우드(1/3/5 하이브리드):4개 / 골프백:1개",
                      "WOOD / #1 / 60 / 10.5 / 197 / 50 / 62 / 45\" / D1", "클럽 중량(g) / 300 / 310 / 320"]], GOLF)
    assert [x["mm"] for x in f["item_lengths"]] == [1143] and len(f["item_weights"]) == 3


def test_stated_packed_weight_beats_the_composition_also_under_it():
    """The check of 2026-11-10: a typed "패키지 무게 : 6.0kg" (the form of 13389271367's "패키지 무게 : 10.8kg") on
    ten clubs and a bag nobody weighs was refused as below_contents: under 10 x 340 + 3800 g, two baselines. A
    statement of the field goes before the composition whatever its size; the composed product weight is no
    seller's word, so nothing is flagged. Under the seller's own set weight (6630856593's "중량: 약11.5kg", 4) the
    packed weight is still taken, flagged below_contents."""
    f = D.read_rows([], GOLF, ["패키지 무게 : 6.0kg"])
    out = packed(f, 10, True)
    assert brief(out["product_weight_g"]) == (7200, 2, "clubs + bag")
    assert brief(out["package_weight_g"]) == (6000, 5, "stated packed weight")
    assert "flags" not in out["package_weight_g"] and "refused" not in out["package_weight_g"]
    assert out["package_weight_g"]["compared"] == {"value": 7000, **WAS}
    f = D.read_rows([["클럽 중량(g) / 400 / 410 / 420"], ["포장 무게 3kg"]], GOLF)      # read from an image: 4
    out = packed(f, 12, False)
    assert [brief(out[n])[:2] for n in D.FIELDS[:2]] == [(4080, 2), (3000, 4)]
    heavy = {"value": {"min": 11500, "max": 11500}, "source": "source_stated", "confidence": 4}
    out = packed(D.read_rows([], GOLF, ["패키지 무게 : 10.8kg"]), 12, True, product_weight_g=heavy)
    assert brief(out["package_weight_g"]) == (10800, 5, "stated packed weight")
    assert out["package_weight_g"]["flags"] == ["below_contents"]


def test_bare_lengths_under_a_unit_label():
    """13780241403 "클럽길이(inch) / 45.5", 13553116678 "길이(cm/inch) / 112.395/44.25"."""
    f = D.read_rows([["클럽길이(inch) / 45.5", "길이(cm/inch) / 112.395/44.25", "샤프트 길이 / 46"]], GOLF)
    assert sorted({x["mm"] for x in f["item_lengths"]}) == [1124, 1156]


# ---- the merge ------------------------------------------------------------------------------------------------

def test_merge_statement_in_place_of_the_default_and_compared_travels():
    """A statement takes the default's place whatever its size (the default travels as `compared`); nothing but a
    statement or a composition does."""
    g = {"package_weight_g": D._ev(4500, 4, "stated packed weight", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g)
    assert taken == ["package_weight_g"] and out["package_weight_g"]["source"] == "description_image"
    assert out["package_weight_g"]["compared"] == {"value": 7000, "source": "category_default", "confidence": 1}
    assert D.merge_fields(fields(), {}) == (fields(), [])


def test_merge_seller_value_is_never_replaced():
    """The server path's value beats everything: a smaller reading, a larger one, the composition."""
    stated = {"value": {"min": 9000, "max": 9500}, "source": "source_stated", "confidence": 5}
    for grams in (9200, 12000):
        g = {"package_weight_g": D._ev(grams, 4, "stated packed weight", [{"quote": "q"}])}
        out, taken = D.merge_fields(fields(package_weight_g=stated), g)
        assert not taken and out["package_weight_g"]["source"] == "source_stated"
        assert out["package_weight_g"]["compared"]["value"] == grams
    out = packed(D.read_rows([ELITE], GOLF), 11, False, product_weight_g=stated)
    assert out["product_weight_g"]["source"] == "source_stated"
    assert out["product_weight_g"]["compared"] == {"value": 3891, "source": "composed", "confidence": 3,
                                                   "how": "clubs, no bag"}


def test_merge_respects_the_plausible_band():
    g = {"package_weight_g": D._ev(40000, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g, {"package_weight_g": {"min": 3000, "max": 20000}})
    assert not taken and out["package_weight_g"]["compared"]["rejected"] == "implausible_for_category"


def test_merge_contradiction_without_value_takes_the_guess():
    g = {"product_weight_g": D._ev(3000, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(product_weight_g={"contradiction": []}), g)
    assert taken == ["product_weight_g"]


def test_core_axis_letter_sizes_and_a_split_label():
    """Live 2026-11-07, other categories: a camping chair (11236665331) "W53 X D38 X H62.5 cm"; a kettle (9809159942)
    "사이즈 / W100 × D170 × H170 mm" and "무 / 0.6kg" (OCR split 무게 into its letters)."""
    f = D.read_rows([["W53 X D38 X H62.5 cm"]])
    assert f["product_sizes"][0]["mm"] == [625, 530, 380] and D.guess(f) == {}
    f = D.read_rows([["모 / 델명 / AL-606G", "사이즈 / W100 × D170 × H170 mm", "무 / 0.6kg"]])
    assert values(D.guess(f)) == {"product_weight_g": 600} and f["product_sizes"][0]["mm"] == [170, 170, 100]


# ---- profiles by category, absurd values, an unknown container ----------------------------------------------

def test_profile_by_naver_category_id():
    assert D.profile_for("50002788") is GOLF and D.profile_for(50002788) is GOLF
    assert D.profile_for("50000830") is None and D.profile_for(None) is None


def test_absurd_guesses_are_never_taken():
    """A misread "45.5kg" (4.55 kg) or a 12 m side: outside the core / profile band, or 3x today's value."""
    g = {"product_weight_g": D._ev(45500, 2, "x", [{"quote": "q"}]),
         "package_length_mm": D._ev(12000, 2, "x", [{"quote": "q"}]),
         "package_width_mm": D._ev(900, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g)                         # no profile: the core band, then the ratio
    assert not taken
    assert out["product_weight_g"]["compared"]["rejected"] == "far_above_today"           # 45.5 > 3 x 5.7 kg
    assert out["package_length_mm"]["compared"]["rejected"] == "implausible_for_category"  # over 3 m
    assert out["package_width_mm"]["compared"]["rejected"] == "far_above_today"
    out, taken = D.merge_fields(fields(), {"package_width_mm": D._ev(750, 2, "x", [{"quote": "q"}])}, None, GOLF)
    assert out["package_width_mm"]["compared"]["rejected"] == "implausible_for_category"   # golf box: <= 700 mm


def test_unknown_container_or_count_leaves_the_default():
    """The composition is unknown when nothing says whether the set has the bag (the weight, the two sides) or
    how many clubs it has (the weight): the flat default stays, 1. The length needs neither."""
    f = D.read_rows([["클럽중량(g) / 300g / 310g / 320g", "캐디백 무게 / 4kg"]], GOLF)
    assert sorted(made(f, 12, None)) == ["package_length_mm"]
    out, taken = D.package_for(fields(), f, 12, None, None, GOLF, BASE)
    assert taken == ["package_length_mm"] and brief(out["package_length_mm"]) == (1240, 2, "longest club + margin")
    assert [out[n] for n in D.FIELDS[:2] + D.FIELDS[3:]] == [fields()[n] for n in D.FIELDS[:2] + D.FIELDS[3:]]
    out, taken = D.package_for(fields(), f, None, True, None, GOLF, BASE)             # a bag, no count anywhere
    assert taken == list(D.FIELDS[2:]) and out["product_weight_g"] == fields()["product_weight_g"]
    assert out["package_weight_g"] == fields()["package_weight_g"]


def test_low_confidence_rows_give_no_single_value():
    """Review 2026-11-07: a statement stands in for the default, so a misread ("4.5kg" read "45kg") would get in;
    a row read below 0.9 gives no box, weight or size, only its share of the items' weights. An item's length
    is read at any confidence since 2026-11-10 (test_club_length_is_read_at_any_confidence)."""
    rows = [("포장 무게 45kg", 0.80), ("제품 사이즈 / 140 x 35 x 30cm", 0.85), ("클럽 중량(g) / 300 / 310", 0.80),
            ("길이 / 48.5\"", 0.70)]
    f = D.read_rows([rows], GOLF)
    assert not f["packed_weights"] and not f["product_sizes"]
    assert [x["g"] for x in f["item_weights"]] == [300, 310] and [x["mm"] for x in f["item_lengths"]] == [1232]
    f = D.read_rows([[("포장 무게 4.5kg", 0.99)]])
    assert [x["g"] for x in f["packed_weights"]] == [4500]


# ---- the typed text, the container's order of trust, accessories, the cross-sell cut (2026-11-10, 120 sets) --

def test_typed_text_is_one_more_block_and_says_so():
    """13389271367: the box and its weight are typed, not in an image; a typed value is the seller's own (5) and
    its evidence says `from` the text. 13495098284 has the same line in an image: 4, no `from`."""
    typed = ["제품 사양", "스틸: 퍼터", "패키지 크기 : L 20 x W 16 x H 121 cm", "패키지 무게 : 10.8kg",
             "크기 | 패키지: L 20 x W 16 x H 121 cm, 10.8kg"]
    f = D.read_rows([], GOLF, typed)
    assert {x["from"] for x in f["packed_weights"] + f["packed_boxes"]} == {"description_text"}
    g = D.guess(f, GOLF)
    assert values(g) == {"package_weight_g": 10800, "package_length_mm": 1210, "package_width_mm": 200,
                         "package_height_mm": 160}
    assert g["package_weight_g"]["confidence"] == 5 and g["package_weight_g"]["from"] == "description_text"
    assert g["package_weight_g"]["quote"] == "패키지 무게 : 10.8kg" and g["package_length_mm"]["confidence"] == 5
    g = D.guess(D.read_rows([[("-패키지무게:10.8kg", 0.966)]], GOLF), GOLF)
    assert g["package_weight_g"]["confidence"] == 4 and "from" not in g["package_weight_g"]
    seller = {"value": {"min": 1250, "max": 1250}, "source": "source_stated", "confidence": 5}
    out, _ = D.merge_fields(fields(package_length_mm=seller), D.guess(f, GOLF))
    assert out["package_length_mm"]["compared"] == {"value": 1210, "source": "description_image", "confidence": 5,
                                                    "how": "stated box size", "from": "description_text"}
    # the loser keeps where it came from; against the default the typed box is taken (5818229550)
    out, _ = D.merge_fields(fields(), D.guess(f, GOLF))
    assert (out["package_length_mm"]["value"]["max"], out["package_length_mm"]["from"]) == (1210, "description_text")


def test_typed_tables_split_on_bars():
    """8958060680: typed cells are joined by " | "; a cell holds both flexes ("R: 294 / S: 297": the first is
    read). 13657325637: "클럽 길이(in)" names the unit its own way."""
    f = D.read_rows([], GOLF, ["구분 | 1W | 5W | U4 | 퍼터", "길이(인치) | 45.25 | 42.5 | 39.5 | 34",
                               "클럽 무게(g) | R: 294 / S: 297 | R: 317 / S: 320 | R: 351 / S: 353 | 528",
                               "#7 클럽 무게(g) | R: 375 / S: 410"])
    assert [x["mm"] for x in f["item_lengths"]] == [1149, 1080, 1003, 864]
    assert [x["g"] for x in f["item_weights"]] == [294, 317, 351, 528, 375]
    f = D.read_rows([], GOLF, ["클럽 길이(in) | 43.5 | 40 | 38.5 | 37.5 | 36.625 | 36.125 | 35.5625 | 35.0625 | 34.875 | 33",
                               "클럽 총 무게(g) | 290 | 315 | 330 | 341 | 354 | 361 | 367 | 374 | 378 | 524"])
    assert max(x["mm"] for x in f["item_lengths"]) == 1105 and len(f["item_weights"]) == 10
    clubs = made(f, 10, False)["product_weight_g"]["parts"][0]                  # one typed row, one weight per club
    assert (clubs["value"], clubs["from"], clubs["quote"][:13]) == (3634, "sum of 10 club weights", "클럽 총 무게(g) | ")


def test_typed_bag_lines():
    """8958060680: the bag's block is typed; "47인치 대응" is the club length the bag takes, not a club.
    9775704002: one bullet."""
    f = D.read_rows([], GOLF, ["캐디백", "사이즈 : 9형 / 47인치 대응", "무게 : 약 3.8kg", "소재 : 합성피혁"])
    assert [x["g"] for x in f["container_weights"]] == [3800] and not f["product_weights"] and not f["item_lengths"]
    f = D.read_rows([], GOLF, ["·캐디백 (9.5형, 2.6kg, 폴리에스테르)"])
    assert [x["g"] for x in f["container_weights"]] == [2600]


def test_bag_weight_slips():
    """12089326778, 13242259238: the unit in brackets. 5543663553: "1.5 kg lighter" is no weight, the table row
    is. 11659201020: the bag is named 9 rows above its table. 13513786835: "(본체)" of the wheel bag, 6 rows
    under its name, is the bag's, never the product's."""
    f = D.read_rows([["사이즈 / 사이즈-가로×세로:약39 x 86(cm)/중량-약4.1 (kg) [캐디백기준]",
                      "사이즈 / 캐디백기준-입구사이즈8.5inch/중량:약4.8(kg)"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [4100, 4800]
    f = D.read_rows([["D1풀세트 전용으로제작된캐디백이며,", "또한 기존의 9인치 남성 캐디백에 비해",
                      "약1.5kg경량화되어 가법게사용할수 있는", "최신형 남성 경량캐디백입니다. / HQNMA", "INFORMATION",
                      "브랜드 / 혼마", "모델명 / D1캐디백", "사이즈 / 9인치,2.9kg"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [2900]
    f = D.read_rows([["남성용 풀세트 전용 캐디백입니다.", "베리티헤드커버 및 클럽들과잘어울리며,", "다양한수납공간이 마련되어 있어",
                      "용품 보관이 편리하고6구 클럽 포켓으로", "클럽간마찰을최소화했습니다.", "INFORMATION",
                      "브랜드 / 마루망 마제스티", "모델명 / maruman", "마루망 베리티 VGR(남성용)", "사이즈 / 9.0형/3.8kg"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [3800]
    f = D.read_rows([["경량화실현한여성용골프백", "$", "품번 / 5LXC260301 /5LXC260305", "소재 / POLYESTER(폴리에스테르)",
                      "색상 / WHITE (01) / WHTE+GRAY (05)", "사이즈 / 8.5inch", "중량 / 약2.8Kg (본체)"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [2800] and not f["product_weights"]


def test_accessory_block_is_nobodys():
    """13513786835 / 13734679551: the add-on Boston bag's table ("보스턴" without 백, 8 rows above its size) was
    the package's width and height (300 / 240). 11834433418: the bag set's row names both bags, the Boston
    bag's and the shoe bag's own rows are theirs."""
    boston = ["RB LADY BB", "5LXB260301", "여성용 경량 보스턴", "WHITE (O1)", "DETAIL",
              "폴리에스테르 소재로 무게감은 감소하고 전면 자석 포켓으로", "사용자의편의성은증가", "품번 / 5LXB260301",
              "소재 / POLYESTER (폴리에스테르)", "색상 / WHITE (O1)", "사이즈 / L48×W24×H30CM", "원산지 / 중국"]
    f = D.read_rows([boston], GOLF)
    assert not f["product_sizes"] and not f["container_sides"] and D.guess(f, GOLF) == {}
    assert D.read_rows([boston])["product_sizes"][0]["mm"] == [480, 300, 240]      # no profile: the core reads it
    f = D.read_rows([["제품구성 / 캐디백, 보스턴백 / 제조국 / 대한민국",
                      "크기(사이즈) / 입구사이즈약20.32cm(8인치),3.8kg / A/S책임자와전화번호 / AK골프/02-6674-7500",
                      "보스턴백36 x 23 x 51cm,2.3kg", "슈즈백31 x 20 x 15cm,230g"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [3800] and not f["product_sizes"]
    f = D.read_rows([["BM 캐디백 세트", "소재:PVC 코팅면/총무게:(캐디백+보스턴백) 약4.95kg"]], GOLF)   # 7583123963
    assert [x["g"] for x in f["container_weights"]] == [4950]


def test_cross_sell_cut_is_a_heading_not_a_sentence():
    """One tall image is the whole description: 12606747315 lost 292 of 311 rows to an invitation to add a putter
    (row 19), 8319243173 its club table to a gift disclaimer (row 5). 12089326778: the returns text no longer
    cuts, the shop's shoe-box rule below it is still no size. 12965275150: a real heading still cuts."""
    f = D.read_rows([["퍼터 추가구매상품", "원하시는퍼터를함께구매하시어본인만의풀세트를완성하세요!", "길이 / 45 / 44.5 / 44",
                      "총중량(g)/밸런스 / 262/C5 / 259/C3 / 256/C0"]], GOLF)
    assert [x["mm"] for x in f["item_lengths"]] == [1143, 1130, 1118] and len(f["item_weights"]) == 3
    f = D.read_rows([["*사은품은 재고 소진시 다른 상품으로 대체 될수 있습니다*",
                      ("길이(inch) / 44.5 / 41.5 / 38.5 / 38 / 36.75 / 36.25 / 35.75 / 35.25 / 34.75 / 34.25 / 34.25 / 33", 0.91),
                      ("전체중량(g) / 258 / 280 / 306 / 310 / 324 / 329 / 335 / 341 / 350 / 359 / 361 / 517", 0.86)]], GOLF)
    assert max(x["mm"] for x in f["item_lengths"]) == 1130 and len(f["item_weights"]) == 12
    f = D.read_rows([["-유료배송:고객의 변심으로 인한 반품 또는 다른 상품으로 교환하는 경우",
                      "-택배비:왕복택배비 6천원,골프회박스 규격(가로X세로X높이 395 x 250 x 155)", "클럽 중량(g) / 300 / 310"]], GOLF)
    assert not f["packed_boxes"] and not f["product_sizes"] and len(f["item_weights"]) == 2
    f = D.read_rows([["추가 구성 상품", "젝시오14 풀세트와 함께 구성하기 좋은 베스트 추천 상품입니다.", "XXIO 14 우드",
                      "XXIO 레이디스 스포티 캐디백 (바퀴)", "무게 / 3.5kg"]], GOLF)
    assert not f["container_weights"] and not f["product_weights"]


def test_bag_words_of_the_120():
    """13446875008: "백세트제외" was read as a bag set. 13389271367, 13325799991, 9266336330 (typed), 11164222651
    (a fact), 5479607864 (an image): other ways to say no. 8958060680: "클럽만 따로 판매" is not one."""
    assert D.container_in("PRGR 스위프 Sweep M15 여성 풀세트 12pcs 백세트제외 프로기아한국지점", GOLF) is False
    assert D.container_in("PRGR 스위프 Sweep M15 여성풀세트12pc 백세트포함 프로기아한국지점", GOLF) is True      # 13446843026
    assert D.container_in("10개세트 클럽만", GOLF) is False
    f = D.read_rows([["NEW 2019 / 여성|카본10pcs / 클럽만"], ["캐디백까지 포함된"]], GOLF,
                    ["골프 가방 불포함 상품 입니다.", "캐디백은 포함되어 있지 않습니다.", "<골프백 별매 추가선택가능>",
                     "클럽만 따로 판매하거나", "캐디백과 분리해 판매하는 경우", "헤드커버 / 캐디백 포함"])
    assert [x["quote"] for x in f["container_no"]] == ["NEW 2019 / 여성|카본10pcs / 클럽만", "골프 가방 불포함 상품 입니다.",
                                                       "캐디백은 포함되어 있지 않습니다.", "<골프백 별매 추가선택가능>"]
    assert [x["quote"] for x in f["container_yes"]] == ["캐디백까지 포함된", "헤드커버 / 캐디백 포함"]


def test_container_listed_spec_row_then_paid_addon():
    """The 상품정보 row 골프백포함여부 (81 of 120 sets), then a bag sold as a paid add-on: the set has none."""
    def row(value):
        return [{"label": "총클럽개수", "value": "11개"}, {"label": "골프백포함여부", "value": value}]
    assert D.container_listed(row("미포함"), [], GOLF) is False                    # 10337644911
    assert D.container_listed(row("캐디백, 보스턴백"), [], GOLF) is True            # 13446843026
    assert D.container_listed(row("스탠드백"), [], GOLF) is True                   # 12679637072
    bag = [{"group": "젝시오14 우드 추가 구매", "name": "3번L", "price": 550000},
           {"group": "젝시오 골프백 추가 구매", "name": "바퀴형 - 핑크", "price": 350000}]            # 12965275150
    assert D.container_listed([{"label": "총클럽개수", "value": "9개"}], bag, GOLF) is False
    assert D.container_listed(row("캐디백"), bag, GOLF) is True                    # the row is asked first
    extras = [{"group": "RB LADY 여성용 보스턴백", "name": "화이트", "price": 46000},                # 13513786835
              {"group": "4. 골프백", "name": "4-2.럭셔리 신발가방 C24307 블랙 2.0", "price": 9900},    # 7583123963
              {"group": "4. 골프백", "name": "4-3.에나멜 골프 파우치 D34305 블랙", "price": 12900},
              {"group": "6.쇼핑백", "name": "대형", "price": 1000}]
    assert D.container_listed([], extras, GOLF) is None
    assert D.container_listed([], [{**bag[1], "price": 0}], GOLF) is None and D.container_listed(row("미포함"), [], None) is None


def test_unsaid_container_typed_sentences_then_the_images():
    """Nothing structured says it: the typed text's sentence (13389271367 "골프 가방 불포함 상품 입니다.") is asked
    before an image's (5684497984 "골프백포함"); the part says who said it. An image's sentence is a weak part."""
    rows = [["골프백포함", "클럽중량(g) / 300g / 310g / 320g", "캐디백 무게 / 4kg"]]
    g = made(D.read_rows(rows, GOLF, ["골프 가방 불포함 상품 입니다."]), 10, None)["product_weight_g"]
    assert g["value"]["max"] == 3400 and g["parts"][1]["said_by"] == "description_text"
    g = made(D.read_rows(rows, GOLF), 10, None)["product_weight_g"]
    assert brief(g) == (7400, 2, "clubs + bag") and g["parts"][1]["said_by"] == "description_image"


def test_inch_triple_and_the_same_line_read_twice():
    """10639350746 (typed): the box in inches. The server reads the same line as the seller's (215.9 mm): that
    value stays, the description's reading (216) travels as compared."""
    f = D.read_rows([], GOLF, ["Item Package Dimensions L x W x H | ‎48.2 x 12.7 x 8.5 inches"])
    g = D.guess(f, GOLF)
    assert [values(g)[n] for n in D.FIELDS[2:]] == [1224, 323, 216]
    stated = {"value": {"min": 215.9, "max": 215.9}, "source": "source_stated", "confidence": 5, "from": "description_table"}
    out, taken = D.merge_fields(fields(package_height_mm=stated), g)
    assert not taken and out["package_height_mm"]["source"] == "source_stated"


# ---- the clubs: the longest club is the driver, the count, the sum of a table (2026-11-10, 120 sets) ---------

def lengths(f):
    return [x["mm"] for x in f["item_lengths"]]


def test_club_length_is_read_at_any_confidence():
    """A row's confidence is its weakest cell, and the driver's short row is the one that fell under 0.9: an
    iron's or a putter's clean row stood as the longest club on 25 of 120 sets. 6732798115: the woods' row at
    0.87, the irons' at 0.96 (952 mm stood); 12863003091: the driver at 0.77, a gift putter at 0.93 (864 mm)."""
    f = D.read_rows([[("클럽길이(인치) / 45.25 / 42.5 / 39.5 / 34", 0.87),
                      ("클럼길이(인치):S / 37.5 / 37 / 36.5 / 36 / 35.75 / 35.5 / 35.25", 0.96)]], GOLF)
    assert D.longest_item(f, GOLF)["mm"] == 1149
    f = D.read_rows([[("OMG GP#3 34인치 퍼터 / (증정)", 0.93), ("라이각() / 58.5°", 0.93), ("길이c / 45.5\"", 0.77)]], GOLF)
    assert lengths(f) == [864, 1156]
    assert made(f, 11, False)["package_length_mm"]["parts"][0] == {"part": "longest club", "value": 1156,
                                                                 "from": "stated", "quote": "길이c / 45.5\""}


def test_longest_club_only_in_the_drivers_band():
    """The largest length stated is the longest club only in the driver's band (42.5-48.5 in): 11775161460 reads
    its driver row without the point ("445": not read) and its woods at 42 in: the baseline driver stands in,
    never the 1067 mm wood, the 972 mm iron or the 838 mm putter."""
    f = D.read_rows([[("길이(인처) / 445", 0.65), ("길이(인치) / 42 / 415", 0.81),
                      ("길이(inch) / 38.25 / 37.63 / 37 / 36.5 / 36 / 35.5 / 35.25", 0.95),
                      ("클럽길이(인치) / 33", 0.96)]], GOLF)
    assert max(lengths(f)) == 1067 and D.longest_item(f, GOLF) is None
    g = made(f, 10, False)["package_length_mm"]
    assert brief(g) == (1240, 2, "longest club + margin") and [x["from"] for x in g["parts"]] == ["baseline"] * 2
    assert GOLF.longest_mm == (1080, 1232)


def test_club_length_forms_of_the_120():
    """A label in a later cell and the next label ending its values (13302492097, 7583123963); cm and inches by
    their bands, no mark needed (13553116678, 12736318849); two cells glued (5543663553: 1160 stood for 1168);
    a cm value on its own row under the flex rows (12965275150: 1137 stood for 1149); the typed text (7166885441);
    OCR's 길이 (13462928946)."""
    f = D.read_rows([["길이(inch) / 45 / 토크(°) / 7.8 / 7.5", "헤드소재 / 6A-4TI / 길이 / 44.5인치"]], GOLF)
    assert lengths(f) == [1143, 1130]
    f = D.read_rows([["길이(cm/inch) / 112.395/44.25",
                      ("클럽길이(CM/INCH) / 115.57 / 109.22 / 1046 / 97.4725 / 95.885 / 94,2975 / 92.71", 0.59)]], GOLF)
    assert lengths(f) == [1124, 1156, 1092, 975, 959, 943, 927]
    f = D.read_rows([["길이 / 116.84107.32 / 97.79 / 96.52 / 95.25 / 93.98 / 92.71 / 91.44 / 90.17 / 86.36"]], GOLF)
    assert lengths(f)[:3] == [1168, 1073, 978]
    f = D.read_rows([["R / 45.25", "(114.935cm)", "클럽길이(inch) / A / 44.75", "60도법 / (113.665cm)", "L / 44.25"]], GOLF)
    assert lengths(f) == [1149, 1137, 1137]
    f = D.read_rows([[("길치(인치) / 44 / 41 / 38.5", 0.79)]], GOLF, ["드라이버의 길이는 44.5인치로"])
    assert lengths(f) == [1118, 1041, 978, 1130]


def test_club_table_under_a_header():
    """One club per row under a header naming the columns. 7674852369: the rows lost a cell the header has (벨런스):
    the length is the header's cell from the left or from the right, when only one of them is a length (PW: loft
    46 from the right is in the driver's band, 35.25 from the left is the length: neither is taken). The weight
    is counted from the end. 6763410768 (typed): four cells under four heads."""
    f = D.read_rows([[("구분 / 로스트각() / 길이(inch) / 라이각(\") / 벨런스 / 총중량(g)", 0.83),
                      ("드라이버 / 10.5 / 44.5 / 60 / 339", 0.91), "#3 / 15 / 43.5 / 58 / 349",
                      ("페이웨이우드 / Do", 0.67), "#7 / 34 / 36.75 / 62.5 / D1 / 440",
                      ("PW / 46 / 35.25 / 65 / D2 / 462", 0.82), "퍼터 / 4 / 35 / 71 / 538"]], GOLF)
    assert lengths(f) == [1130, 1105, 933, 895, 889]
    assert [x["g"] for x in f["item_weights"]] == [339, 349, 440, 462, 538]
    f = D.read_rows([], GOLF, ["번호 | 로프트각 | 샤프트 | 길이(Inch)", "1W | 10.5 | 카본S/R | 44.5"])
    assert lengths(f) == [1130] and f["item_lengths"][0]["from"] == D.TYPED


def test_shaft_makers_table_is_not_the_clubs():
    """12863003091: "R / 46 / 58.5 / ..." under a header with TIP / Butt 외경 is the uncut shaft (46 in); the club
    is 45.5 in."""
    f = D.read_rows([[("길이c / 45.5\"", 0.77),
                      ("모델 / 플렉스 / 길이(inch) / 충량(9) / 토크 / TIP외경 / Butt외경 / 익포인트", 0.67),
                      ("R / 46 / 58.5 / 3.7 / 8.50 / 15.45 / MID", 0.89),
                      ("24년형 VENTUS BLUE 5 / s / 46 / 58.5 / 3.5 / 8.50 / 15.45 / MID", 0.72)]], GOLF)
    assert lengths(f) == [1156] and not f["item_weights"]


SHOGUN = ["클럽넘 / 로프트 / 라이각 / 전체길이 / 스윙웨이트 / 플렉스 / 헤드중량 / 총중량",          # 5684497984, rows 63-79
          "1W / 10.5 / 58 / 45.25 inch / D0 / R / 197g / 320g", "1W / 10.5 / 58 / 45.25 inch / D1 / SR / 197g / 320g",
          "1W / 10.5 / 58 / 45.25 inch / D1 / s / 197g / 320g", "3W / 15 / 58.5 / 43 inch / D0 / R / 210g / 326g",
          "3W / 15 / 58.5 / 43 inch / D1 / SR / 210g / 326g", "4HYBRID / 21 / 61 / 40 inch / DO / R / 235g / 358g",
          "4HYBRID / 21 / 61 / 40 inch / D1 / SR / 235g / 358g", "IRON5 / 25 / 61 / 38 inch / D1 / STEELR / 256g / 416g",
          "IRON6 / 29 / 61.5 / 37.5inch / D1 / STEELR / 263g / 423g", "IRON7 / 33 / 62 / 37 inch / D1 / STEELR / 270g / 430g",
          "IRON8 / 37 / 63 / 36.5 inch / D1 / STEELR / 277g / 437g", "IRON9 / 41 / 63.5 / 36 inch / D1 / STEELR / 284g / 444g",
          "PW / 45 / 64 / 35.5 inch / D1 / STEELR / 292g / 452g", "AW / 52.5 / 64 / 35.25 inch / D3 / STEELR / 300g / 460g",
          "sW / 56 / 64 / 35.25 inch / D3 / STEELR / 300g / 460g", "PT / 3.5 / 72 / 34 inch / 325g / 495g"]


def test_club_weights_under_a_header_sum_when_one_per_club():
    """5684497984 (12피스): the total is the header's last column, never the head's weight beside it (197g); the
    SR and S rows of a club are the same club. Twelve weights for twelve clubs: their sum, 5021 g. Read with
    another count the table is not one weight per club: the count x the median."""
    f = D.read_rows([SHOGUN], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [320, 326, 358, 416, 423, 430, 437, 444, 452, 460, 460, 495]
    assert D.longest_item(f, GOLF)["mm"] == 1149
    g = made(f, 12, False)["product_weight_g"]
    assert brief(g) == (5021, 3, "clubs, no bag") and "baseline" not in g
    assert g["parts"][0] == {"part": "clubs", "value": 5021, "from": "sum of 12 club weights", "quote": SHOGUN[1],
                             "count_from": "listing"}
    g = made(f, 11, False)["product_weight_g"]
    assert (g["value"]["max"], g["confidence"], g["parts"][0]["from"]) == \
        (round(11 * 433.5), 2, "11 clubs x median club weight")


def test_club_weights_sum_of_one_table_the_lightest_of_several():
    """11659201020 (클럽10개, R세트): the R and the S table, one row each: the lighter (3892 g; 10 x the median of
    the 20 values gave 3975). 13719960843: one table over five rows under one label. 13495098284: OCR's 클럼."""
    f = D.read_rows([["총중량(g) / 308 / 326 / 360 / 376 / 382 / 388 / 394 / 401 / 412 / 545",
                      "총중량(g) / 314 / 332 / 365 / 423 / 429 / 435 / 440 / 447 / 458 / 545"]], GOLF)
    out = packed(f, 10, False)
    assert out["product_weight_g"]["parts"][0]["from"] == "sum of 10 club weights"
    assert [brief(out[n]) for n in D.FIELDS[:2]] == [(3892, 3, "clubs, no bag"), (5892, 3, "product weight + carton")]
    f = D.read_rows([["클럽무게(g) / 290", "로프트 / 12.5", "클럽무게(g) / 315", "클럽무게(g) / 330 / 341",
                      "클럽무게(g) / 354 / 361 / 367 / 374 / 378", "클럽무게(g) / 524"]], GOLF)
    assert values(made(f, 10, False))["product_weight_g"] == 3634
    f = D.read_rows([[("클럼무게(g) / 307 / 313 / 352 / 352 / 358 / 364 / 370 / 375 / 386 / 502", 0.78)]], GOLF)
    assert values(made(f, 10, False))["product_weight_g"] == 3679


def test_club_weights_not_a_sum():
    """As many values as clubs is not always one per club. 13229172406 (클럽11개, a combination set): a driver by
    three shafts, a hybrid by three, two irons and a wood by three, each maker's table under its own label.
    12965394174 (8 clubs: the driver + 7 irons): one row of eight irons, no driver in it (the heaviest is not 1.25x
    the lightest)."""
    f = D.read_rows([["클럽 중량(g) / 306 / 302 / 300", "클럽중량(g) / 345 / 339 / 335", "중량(g) / 400 / 414",
                      "클럽 중량(g) / 316 / 313 / 310"]], GOLF)
    assert made(f, 11, False)["product_weight_g"]["parts"][0]["from"] == "11 clubs x median club weight"
    f = D.read_rows([["클럽중량(g) / L / 267"], ["클럽중량(g) / L / 317 / 322 / 327 / 333 / 338 / 344 / 347 / 347"]], GOLF)
    assert made(f, 8, False)["product_weight_g"]["parts"][0]["from"] == "8 clubs x median club weight"


def test_club_weight_labels_of_the_120():
    """6392093003: 스윙웨이트 beside the total is the balance, not a part (the row was dropped). 7583123963: a
    label in a later cell; a wood's head (198-233 g) is under the lightest club (252 g). 6655509590: OCR's 총.
    Parts as OCR spells them stay out (사프트중량, 허드중량)."""
    f = D.read_rows([[("총중량(g)/스윙웨이트 / 약316g/D1/#5·ALTA J CB SLATE·SR / 약319g/D2 / AITA J CB SLATE·S / 약 312g /DO", 0.85),
                      "헤드체적(cc) / 460cc / 총중량(g) / 296g", "중량(g) / 198 / 202 / 207 / 233",
                      "사프트중량(g) / 255 / 260", "허드중량 / 256g / 263g", "스윙웨이트 / D1 / D2"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [316, 319, 312, 296]
    f = D.read_rows([["로프트 / 라이 / 길이 / 충중량(g)", "3 / 72 / 0 / 33 / 490"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [490]


def test_a_heads_row_makes_its_label_a_parts():
    """7583123963: its summary tables give the heads' weights under a plain "중량(g)". The woods' row is under the
    lightest club (198-233 g), the irons' is not (257-297 g), and 22 such values made the median club of a
    13-club set 296 g. A row of the label with only weights under a club's makes the label a part's in that image,
    on its other rows too, whichever comes first; another label and another image stay."""
    f = D.read_rows([["총중량(g) / 319g±3 / 326g±3 / 헤드소재 / 17-4", "중량(g) / 198 / 202 / 207 / 233",
                      "중량(g) / 257 / 263 / 270 / 278 / 285 / 291 / 297 / 297"],
                     ["중량(g) / 263 / 270", "중량(g) / 192 / 207 / 233 / 234"],
                     ["중량(g) / 355 / 363 / 369 / 376 / 388 / 544.2"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [319, 326, 355, 363, 369, 376, 388, 544.2]


def test_club_count_words():
    """The images: a head's make is not the set's count (12945108653 was a set of 4 clubs, 6540695739 read 4 too).
    The title's "N개" as the 120 write it; a part's count ("웨지2개", 7506388758) is under the band."""
    f = D.read_rows([["저중심 4피스 티타늄 페이스 설계", "SOLE:순TI(G4) 4PCS단조", "에필 풀세트 기본구성(총 10PCS,헤드커버 포함)"]], GOLF)
    assert [x["count"] for x in f["item_counts"]] == [10]

    def title(text):
        return [int(g) for m in GOLF.count_title.finditer(text) for g in m.groups() if g and _in_band(int(g))]

    def _in_band(n):
        return GOLF.count[0] <= n <= GOLF.count[1]
    assert title("야마하 cs HM+ 씨즈 10개 풀세트 여성용골프채 풀세트") == [10]                       # 10481094198
    assert title("캘러웨이 워버드 골프 클럽 10개 남성용 골프채 풀세트 2019년 모델 캐디백포함") == [10]      # 6763410768
    assert title("핑 G440 MAX 남성 풀세트 스틸 [11개]") == [11]                                      # 13753313321
    assert title("무쯔미 혼마 스페셜 3스타 여성용 고반발 골프채풀세트 (13개)") == [13]                  # 7125625445
    assert title("캘러웨이 레바 REVA 여성 풀세트 2025년 골프채 9개") == [9]                            # 13325799991
    assert title("삼양인터내셔날 핑 PING G430 남성골프채풀세트 11개 조합풀세트 택1 드라이버 10.5 유틸4번R 6아이언 "
                 "웨지2개퍼터") == [11]
    assert title("던롭코리아 젝시오13 여성 풀세트 (드라이버+유틸+7아이언세트)") == []                   # 12945108653


# ---- the owner, 2026-11-10: a statement, else the composition from the set's parts, the flat default last; levels 1-5

REVA = ["클럽번호 / 로프트(o) / 라이(o) / 길이(cm/inch) / 스윙웨이트 / 클럽무게(g)",                   # 13413924099
        "드라이버 / 12.5 / 62.5 / 110.49/43.5 / C1 / 약290", "우드 / 18.0 / 58.5 / 101.6/40.0 / C4 / 약315",
        "하이브리드(#5) / 23.0 / 61.0 / 97.79/38.5 / C5 / 약330", "하이브리드(#6) / 26.0 / 61.5 / 95.25/37.5 / C5 / 약341",
        "아이언(#7) / 33.0 / 62.5 / 93.028/36.625 / C7 / 약354", "아이언(#8) / 38.0 / 63.0 / 91.758/36.125 / C7 / 약361",
        "아이언(#9) / 43.0 / 63.5 / 90.327/35.562 / C7 / 약367", "PW / 48.0 / 64.0 / 89.057/35.062 / C7 / 약374",
        "SW / 56.0 / 64.0 / 88.583/34.875 / C8 / 약378", "퍼터(#7) / 3.0 / 70.0 / 83.82/33 / 약524"]
EDGE = [("-패키지크기:L20×W16×H121cm", 0.936), ("-패키지무게:10.8kg", 0.966),              # 13495098284, image 2
        ("클럽길이(cm) / 111.12 / 106.99 / 96.83 / 92.39 / 91.44 / 89.85 / 89.21 / 88.74 / 87.63 / 83.82", 0.975),
        ("클럼무게(g) / 307 / 313 / 352 / 352 / 358 / 364 / 370 / 375 / 386 / 502", 0.78)]
ELITE = ["클럽길이( inch)카본 / 44.5 / 41.75 / 39 / 37 / 36.5 / 36 / 35.5 / 35 / 34.75 / 34.5 / 33",         # 9199086110:
         "클럽 중량(g) / 273 / 292 / 317 / 337 / 343 / 348 / 353 / 361 / 366 / 372 / 529"]                # 11pcs, 미포함
WAS = {"source": "category_default", "confidence": 1}
BY = {"approved_by": "owner", "approved_at": "2026-11-10"}


def levels(out):
    return [out[n]["confidence"] for n in D.FIELDS]


def test_composition_only_with_the_operators_baselines():
    """9199086110 (11 clubs, 골프백포함여부 미포함): the clubs' sum 3891 g and the 44.5 in driver. A row without the
    `baselines` block composes nothing: the flat defaults stay. With it every field is built from the set's
    parts, says how, and carries the default it replaced."""
    f = D.read_rows([ELITE], GOLF)
    assert D.package_for(fields(), f, 11, False, None, GOLF) == (fields(), [])
    out, taken = D.package_for(fields(), f, 11, False, None, GOLF, BASE)
    assert taken == list(D.FIELDS) and all(out[n]["source"] == "composed" for n in D.FIELDS)
    assert [brief(out[n]) for n in D.FIELDS] == [
        (3891, 3, "clubs, no bag"), (5891, 3, "product weight + carton"), (1230, 3, "longest club + margin"),
        (200, 2, "box side, no bag"), (160, 2, "box side, no bag")]
    assert [out[n]["compared"] for n in D.FIELDS] == [{"value": v, **WAS} for v in (5700, 7000, 1250, 280, 230)]
    assert out["product_weight_g"]["parts"] == [
        {"part": "clubs", "value": 3891, "from": "sum of 11 club weights", "quote": ELITE[1], "count_from": "listing"},
        {"part": "bag", "value": 0, "from": "not in the set", "said_by": "listing"}]
    assert out["package_weight_g"]["parts"] == [{"part": "product", "value": 3891, "from": "product_weight_g"},
                                                {"part": "carton", "value": 2000, "from": "baseline"}]
    assert out["package_length_mm"]["parts"] == [
        {"part": "longest club", "value": 1130, "from": "stated", "quote": ELITE[0]},
        {"part": "margin", "value": 100, "from": "baseline"}]
    assert "baseline" not in out["product_weight_g"]                   # the seller's figures only
    assert [out[n]["baseline"] for n in D.FIELDS[1:]] == [BY] * 4


def test_composed_weight_is_3_only_from_the_sellers_own_figures():
    """13413924099 (10 clubs, "+골프백"): one weight per club, 3634 g. 3: the exact sum, the bag absent or its
    weight stated, the count and the bag's state from the listing or the typed text. 2: a baseline in it (the
    bag's weight nobody states) or a weak part (the count or the bag's state read in an image)."""
    f = D.read_rows([REVA], GOLF)
    assert D.longest_item(f, GOLF)["mm"] == 1105
    assert brief(made(f, 10, False)["product_weight_g"]) == (3634, 3, "clubs, no bag")
    g = made(f, 10, True)["product_weight_g"]
    assert brief(g) == (3634 + 3800, 2, "clubs + bag") and g["baseline"] == BY
    assert g["parts"][1] == {"part": "bag", "value": 3800, "from": "baseline", "said_by": "listing"}
    assert brief(made(D.read_rows([REVA, ["캐디백 무게 / 4kg"]], GOLF), 10, True)["product_weight_g"]) == \
        (7634, 3, "clubs + bag")
    g = made(D.read_rows([REVA, ["10PCS 여성용"]], GOLF), None, False)["product_weight_g"]     # 13495098284's row
    assert brief(g)[:2] == (3634, 2) and g["parts"][0]["count_from"] == "description_image"
    g = made(D.read_rows([REVA, ["※ 본 풀세트는 골프백 미포함 제품입니다"]], GOLF), 10, None)["product_weight_g"]
    assert brief(g)[:2] == (3634, 2) and g["parts"][1]["said_by"] == "description_image"
    g = made(D.read_rows([REVA], GOLF, ["골프 가방 불포함 상품 입니다."]), 10, None)["product_weight_g"]   # typed: 13389271367
    assert brief(g)[:2] == (3634, 3) and g["parts"][1]["said_by"] == "description_text"


def test_every_level():
    """5: typed with its kind (5818229550: the box and its weight). 4: the same lines read from an image
    (13495098284). 3: the seller's own figures + the carton / margin. 2: a baseline or a weak part. 1: the flat
    default, the composition unknown."""
    clubs = [EDGE[2:]]
    typed = D.read_rows(clubs, GOLF, ["패키지 크기 : L 20 x W 16 x H 121 cm", "패키지 무게 : 10.8kg"])
    assert levels(packed(typed, 10, False)) == [3, 5, 5, 5, 5]
    out = packed(D.read_rows([EDGE], GOLF), 10, False)
    assert levels(out) == [3, 4, 4, 4, 4] and values(out) == {
        "product_weight_g": 3679, "package_weight_g": 10800, "package_length_mm": 1210, "package_width_mm": 200,
        "package_height_mm": 160}
    out = packed(D.read_rows(clubs, GOLF), 10, False)
    assert levels(out) == [3, 3, 3, 2, 2] and values(out)["package_weight_g"] == 5679
    out = packed(D.read_rows(clubs, GOLF), 10, True)                   # a bag nobody weighs: its baseline
    assert levels(out) == [2, 2, 3, 2, 2] and values(out) == {
        "product_weight_g": 7479, "package_weight_g": 9479, "package_length_mm": 1211, "package_width_mm": 400,
        "package_height_mm": 320}
    assert levels(packed(D.read_rows(clubs, GOLF), 10, None)) == [1, 1, 3, 1, 1]      # with a bag or without?
    out = packed(D.read_rows([["여성용 풀세트"]], GOLF), None, None)       # nothing read: the baseline driver
    assert levels(out) == [1, 1, 2, 1, 1] and out["package_length_mm"]["value"]["max"] == 1240


def test_a_statement_beats_the_default_whatever_its_size():
    """13495098284: the box "L20×W16×H121cm" read from an image lost to the default 1250 x 280 x 230 only because
    it is smaller. A statement of the field itself takes the place of a category default, and of the composition;
    a seller's value from the server path is never replaced."""
    f = D.read_rows([EDGE], GOLF)
    g = D.guess(f, GOLF)
    assert brief(g["package_weight_g"]) == (10800, 4, "stated packed weight") and "product_weight_g" not in g
    out, taken = D.merge_fields(fields(), g, None, GOLF)
    assert taken == ["package_weight_g", "package_length_mm", "package_width_mm", "package_height_mm"]
    assert [out[n]["value"]["max"] for n in D.FIELDS[2:]] == [1210, 200, 160]
    assert [out[n]["compared"] for n in D.FIELDS[2:]] == [{"value": v, **WAS} for v in (1250, 280, 230)]
    assert out["product_weight_g"] == fields()["product_weight_g"]     # no baselines: nothing is composed
    out = packed(f, 10, True)                                          # with them: what is stated stays stated
    assert [out[n]["how"] for n in D.FIELDS] == ["clubs + bag", "stated packed weight"] + ["stated box size"] * 3
    seller = {"value": {"min": 1250, "max": 1250}, "source": "source_stated", "confidence": 5}
    out, taken = D.merge_fields(fields(package_length_mm=seller), g, None, GOLF)
    assert taken == ["package_weight_g"] and out["package_length_mm"]["source"] == "source_stated"
    assert out["package_length_mm"]["compared"]["how"] == "stated box size"
    # the guards stay: a box under the band of a set's (the returns rule's shoe box, "골프화박스 규격(가로X세로X높이
    # 395X250X155)", 12089326778, were its row read) is refused, not taken because it is stated
    shoes = {"package_length_mm": D._ev(395, 4, "stated box size", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), shoes, None, GOLF)
    assert not taken and out["package_length_mm"]["compared"]["rejected"] == "implausible_for_category"
    heavy = {"package_weight_g": D._ev(22000, 4, "stated packed weight", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), heavy)
    assert not taken and out["package_weight_g"]["compared"]["rejected"] == "far_above_today"


def test_a_box_is_taken_whole_or_not_at_all():
    """The check of 2026-11-10: a gift's "증정 골프공 패키지 사이즈 30 x 20 x 10cm" on a set. Its 300 mm is refused as
    the length of a set's box, and 200 x 100 stayed as the width and height of a 1250 mm package. The three
    sides are one statement: all refused; the composition stands in and says what it refused."""
    f = D.read_rows([["증정 골프공 패키지 사이즈 30 x 20 x 10cm"] + ELITE], GOLF)
    assert f["packed_boxes"][0]["mm"] == [300, 200, 100]
    out, taken = D.merge_fields(fields(), D.guess(f, GOLF), None, GOLF)
    assert not taken and [out[n]["compared"]["rejected"] for n in D.FIELDS[2:]] == \
        ["implausible_for_category", "box_not_whole", "box_not_whole"]
    assert [out[n]["source"] for n in D.FIELDS[2:]] == ["category_default"] * 3
    out = packed(f, 11, True)
    assert [brief(out[n]) for n in D.FIELDS[2:]] == [
        (1230, 3, "longest club + margin"), (400, 2, "box side, with bag"), (320, 2, "box side, with bag")]
    assert out["package_height_mm"]["refused"] == {"value": 100, "source": "description_image", "confidence": 4,
                                                   "how": "stated box size", "rejected": "box_not_whole"}
    assert out["package_height_mm"]["compared"] == {"value": 230, **WAS}
    seller = {"value": {"min": 1250, "max": 1250}, "source": "source_stated", "confidence": 5}   # the server's box
    out, taken = D.merge_fields(fields(package_length_mm=seller), D.guess(D.read_rows([EDGE], GOLF), GOLF), None, GOLF)
    assert out["package_width_mm"]["compared"]["rejected"] == "box_not_whole"


def test_a_stated_weight_is_the_products_own_in_the_core_only():
    """No set of the 120 states its weight in the description, so the core's lines: "제품 무게 / 2.3kg" (a camping
    chair) and "무 / 0.6kg" (a kettle, 9809159942) are the product's weight, taken under a larger default; the
    package's stays the default (no carton baseline). In a set of parts a plain 무게 row may be one part's: not
    read as the set's."""
    for row, grams, how in (("제품 무게 / 2.3kg", 2300, "stated set weight"), ("무 / 0.6kg", 600, "stated weight")):
        out, taken = D.merge_fields(fields(), D.guess(D.read_rows([[row]])))
        assert taken == ["product_weight_g"] and brief(out["product_weight_g"]) == (grams, 4, how)
        assert out["package_weight_g"] == fields()["package_weight_g"]
    f = D.read_rows([["무게 / 3.5kg"]], GOLF)
    assert [x["g"] for x in f["product_weights"]] == [3500] and D.guess(f, GOLF) == {}


def test_median_only_when_the_weights_cover_half_the_clubs():
    """The check of 2026-11-10: the count x the median stood as the set's weight. 8029218821 (10개조합): 18 weights of
    a driver by nine shafts, two woods and a utility, 292-340 g, no iron and no putter: 10 x 309 = 3090 g for a
    set of about 3.8 kg. 13728931694 (9개): four weights, the driver's and the wood's, 2362 g for about 2.9 kg.
    Neither covers half the clubs (as many clubs as half the count, the heaviest 1.25x the lightest): the
    baseline club. test_club_weights_not_a_sum has the tables that do."""
    f = D.read_rows([["클럽 중량(g) / 298g / 300g / 302g / 302g / 311g / 305g / 313g / 304g / 311g",
                      "#3 클럼 중량(g) / 308g / 310g / 311g / 295g / 292g",
                      "#3 클럽 중량(g) / 333g / 340g / #4-324g / #4-322g"]], GOLF)
    assert len(f["item_weights"]) == 18
    g = made(f, 10, False)["product_weight_g"]
    assert brief(g) == (3400, 2, "clubs, no bag") and g["baseline"] == BY
    assert g["parts"][0] == {"part": "clubs", "value": 3400, "from": "10 clubs x baseline club weight",
                             "count_from": "listing"}
    f = D.read_rows([["클럽중량(g) / 약257 / 약260", "클럽 중량(g) / 약265 / 약270"]], GOLF)
    assert made(f, 9, False)["product_weight_g"]["parts"][0]["from"] == "9 clubs x baseline club weight"


def test_package_weight_is_the_fields_product_weight_and_the_carton():
    """6630856593: the seller's "중량: 약11.5kg" (4: with the box or not is not said) stood beside a default package
    of 7000 g, below its contents. The package is the product's weight as the field holds it + the carton; 3:
    the seller's own figure."""
    heavy = {"value": {"min": 11500, "max": 11500}, "source": "source_stated", "confidence": 4}
    out = packed(D.read_rows([ELITE], GOLF), 11, True, product_weight_g=heavy)
    assert out["product_weight_g"]["source"] == "source_stated"
    assert out["product_weight_g"]["compared"]["value"] == 3891 + 3800           # the composition, for the reader
    assert brief(out["package_weight_g"]) == (13500, 3, "product weight + carton")
    typed = {"value": {"min": 5000, "max": 5000}, "source": "source_stated", "confidence": 5}
    out = packed(D.read_rows([ELITE], GOLF), 11, False, package_weight_g=typed)   # the seller's packed weight stays
    assert out["package_weight_g"]["source"] == "source_stated" and out["package_weight_g"]["compared"]["value"] == 5891


def test_a_known_composition_is_kept_under_the_band():
    """13302492097 (총클럽개수 3개, 골프백포함여부 미포함): a driver, a wood and a hybrid. 3 x 340 g is under the
    band of a set (1500 g), and the composition was thrown away for it: 5700 / 7000 g, the flat default, for
    three clubs of 825 g. The count and the bag's state are known, so the composition stands. 12966969668: the
    same with the driver's, the woods' and the utilities' rows (a club by its lofts: under the spread of a set,
    the baseline club). The band still holds for what is read as a statement (an absurd value), and its upper
    side for everything."""
    three = [["총중량(g)/밸런스 / 약255g·C4 (ALTAJLE-L) / 킥 포인트 / Low"],
             ["총중량(g)/밸런스 / 약270g·C3 (#5·ALTAJLE·L) / 킥 포인트 / Low"],
             ["총중량(g)/밸런스 / 약300g·C2 (#5·ALTAJLE·L) / 킥 포인트 / Low"]]
    xxio = [["클럽중량(g) / L / 267"], ["클럽중량(g) / L / 268 / 271 / 275 / 279 / 283"],
            ["클럽중량(g) / L / 291 / 295 / 300 / 304 / 309"]]
    for rows in (three, xxio):
        out, taken = D.package_for(fields(), D.read_rows(rows, GOLF), 3, False, None, GOLF, BASE)
        assert taken == list(D.FIELDS)
        assert [brief(out[n]) for n in D.FIELDS[:2]] == [(1020, 2, "clubs, no bag"), (3020, 2, "product weight + carton")]
        assert out["product_weight_g"]["parts"][0]["from"] == "3 clubs x baseline club weight"
        assert [out[n]["compared"] for n in D.FIELDS[:2]] == [{"value": 5700, **WAS}, {"value": 7000, **WAS}]
    f = D.read_rows(three + [["풀세트 무게 약 0.9kg"]], GOLF)                # a statement under the band: absurd
    out = packed(f, 3, False)
    assert brief(out["product_weight_g"]) == (1020, 2, "clubs, no bag")
    assert out["product_weight_g"]["refused"] == {"value": 900, "source": "description_image", "confidence": 4,
                                                  "how": "stated set weight", "rejected": "implausible_for_category"}
    low = {"product_weight_g": {"min": 100, "max": 1000}}                  # the operator's band: its upper side
    out, taken = D.package_for(fields(), D.read_rows(three, GOLF), 3, False, low, GOLF, BASE)
    assert "product_weight_g" not in taken and out["product_weight_g"]["compared"]["rejected"] == \
        "implausible_for_category"


# ---- the reader's slips the check of 2026-11-10 found

def test_a_shafts_model_number_is_not_a_club():
    """9321714669: "C1(ULT 250 J-L)" beside the weight is the shaft's name; three of seven "weights" were 250 g.
    A bare number after a name is not a weight ("DG 300": the check's example); after a flex mark or a club
    number it is (10649210920, 7202588289, 8958060680)."""
    f = D.read_rows([["총 중량(g)/밸런스 / 약256g / C1(ULT 250 J-L) / 익 포인트 / Low",
                      "총 중량(g)/밸런스 / 약269g / C1 (#5-ULT 250 J-L) / 킥 포인트 / Low",
                      "총 중량(g) /밸런스 / 약 323g / C3 (#7-ULT 250 JL) / 킥 포인트 / Low",
                      "클럽 중량(g) / 약 402g / MODUS3 TOUR 105 / DG 300"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [256, 269, 323, 402]
    f = D.read_rows([["총중량(g)/ / SR / 343/D1 / 348/D1", "클럽중량(g) / 328(L:#7)"]], GOLF,
                    ["#7 클럽 무게(g) | R: 375 / S: 410"])
    assert [x["g"] for x in f["item_weights"]] == [343, 348, 328, 375]


def test_the_clubs_own_is_not_the_clubs_only_and_a_bags_cover_is_not_a_bag():
    """"클럽만의 기술력", "이 클럽만으로 충분" said the set has no bag; so did a paid add-on for the bag (a flight
    cover, a name tag). 11164222651's "[클럽만]" and 12965275150's bag sold apart still say it."""
    assert D.container_in("젝시오 클럽만의 기술력", GOLF) is None and D.container_in("이 클럽만으로 충분", GOLF) is None
    assert D.container_in("마루망 2W 풀세트 여성 [클럽만]", GOLF) is False
    for name in ("캐디백 항공커버", "캐디백 네임택"):
        assert D.container_listed([], [{"group": "추가상품", "name": name, "price": 15000}], GOLF) is None
    bag = [{"group": "젝시오 골프백 추가 구매", "name": "바퀴형 - 핑크", "price": 350000}]
    assert D.container_listed([], bag, GOLF) is False


def test_a_header_whose_first_cell_is_the_label():
    """Cell 0 was tested for truth, so a header starting with the length's label was no header (the check's
    rows; not seen on the 120)."""
    f = D.read_rows([["길이(inch) / 로프트 / 라이각 / 총중량", "45.5 / 10.5 / 58 / 300", "43 / 15 / 58.5 / 320"]], GOLF)
    assert lengths(f) == [1156, 1092] and [x["g"] for x in f["item_weights"]] == [300, 320]


def test_the_items_constants_are_the_profiles():
    """A second profile gets no golf: the shaft maker's table, the spread of a set, the rows under a header."""
    assert GOLF.set_spread == 1.25 and GOLF.column_rows == 18 and GOLF.part_table.search("TIP외경")
    assert not hasattr(D, "SET_SPREAD") and not hasattr(D, "_SHAFT_TABLE") and not hasattr(D, "COLUMN_ROWS")


# ---- the second check of 2026-11-10: the clubs' own table before the listing's pieces, clubs not values, typed first

STRATA = ["Mens 2019 Strata Mens 12-Piece Complete Set Product Specs",                               # 8053135821, image 3
          "Name / Loft / Availability / standard Length / Lie / swing Weight / Club Weight",
          'Driver / 10.5° / RH /LH / 45.00" / 56.00° / D2 / 336', '3-wood / 15.5° / RH /LH / 42.00" / 57.00° / D1 / 396',
          '5H / 26° / RH/LH / 37.75" / 60.50° / D1 / 431', '6-iron / 28° / RH/LH / 37.00" / 61.50° / D1 / 441',
          '7-iron / 32° / RH /LH / 36.50" / 62.00° / D1 / 445', '8-iron / 36° / RH/LH / 36.00" / 62.50° / D1 / 453',
          '9-iron / 40° / RH / LH / 35.50" / 63.00° / D1 / 459', 'PW / 44° / RH /LH / 35.00" / 64.00° / D1 / 462',
          'Putter / 3° / RH /LH / 35.00" / 72.00° / NA / 532']
REVA26 = "클럽 총 무게(g) | 290 | 315 | 330 | 341 | 354 | 361 | 367 | 374 | 378 | 524"                 # 13657325637, typed
D1 = ["번호 / 1W / 5W / #5 / #6 / #7 / #8 / #9 / PW / SW / PT",                                       # 5543663553
      "총중량(g) / 299 / 322 / 360 / 366 / 372 / 378 / 383 / 389 / 398 / 526",
      "총중량(g) / 301 / 324 / 407 / 413 / 419 / 426 / 434 / 442 / 451 / 526"]
BAZOOKA = ["구분 / 로스트각() / 길이(inch) / 라이각(\") / 벨런스 / 총중량(g)",                             # 7674852369, image 1
           "드라이버 / 10.5 / 44.5 / 60 / 339", "#3 / 15 / 43.5 / 58 / 349", "페이웨이우드 / Do", "#5 / 19 / 42.5 / 59 / 360",
           "하이브리드 / #4 / 24 / 38.75 / 60.5 / 400", "#5 / 27 / 37.75 / 61 / 432", "#6 / 30 / 37.25 / 61.5 / 437",
           "#7 / 34 / 36.75 / 62.5 / D1 / 440", "아이언 / #8 / 38 / 36.25 / 63.5 / 451", "#9 / 42 / 35.75 / 64 / 452",
           "PW / 46 / 35.25 / 65 / D2 / 462", "sW / 55 / 35.25 / 65 / D3 / 460", "퍼터 / 4 / 35 / 71 / 538"]
XHOT = ["총 무게(S세트) | 약 312g | 약 328g | 약 372g | 약 418g | 약 426g | 약 432g | 약 442g | 약 441g | 약 449g | 약 452g | -",
        "총 무게(R세트) | 약 311g | 약 327g | 약 371g | 약 382g | 약 388g | 약 395g | 약 405g | 약 408g | 약 411g | 약 415g | -"]


def clubs(facts, count, bag=False):
    part = made(facts, count, bag)["product_weight_g"]["parts"][0]
    return part["value"], part["from"], part["count_from"]


def test_the_clubs_own_table_before_the_listings_pieces():
    """8053135821: 총클럽개수 "12개" is the box's "12-Piece" (nine clubs, a stand bag, two head covers); the
    table lists the nine, 3955 g, where 12 x the median 445 g said 5340. 13657325637: "11피스" with the bag, ten
    typed weights, 3634 g (11 x 357.5 = 3932 before). A full table (one row or the rows under one header, nine
    weights and up, the last a putter's) is the set when the listing counts up to three more: its sum, its
    length the count. The count is then the table's, a weaker source than the title: 2, and the listing's count
    stays beside it."""
    f = D.read_rows([STRATA], GOLF)
    assert clubs(f, 12) == (3955, "sum of 9 club weights", "table")
    g = made(f, 12, True)["product_weight_g"]
    assert brief(g) == (3955 + 3800, 2, "clubs + bag") and g["parts"][0]["count_listed"] == 12
    assert brief(made(f, 12, False)["product_weight_g"])[:2] == (3955, 2)       # no bag: still the table's count
    g = made(f, 9, False)["product_weight_g"]                                  # the listing agrees: 3
    assert brief(g)[:2] == (3955, 3) and g["parts"][0]["count_from"] == "listing" and "count_listed" not in g["parts"][0]
    f = D.read_rows([], GOLF, [REVA26])
    assert clubs(f, 11) == (3634, "sum of 10 club weights", "table")
    assert values(packed(f, 11, True))["package_weight_g"] == 3634 + 3800 + 2000
    assert clubs(f, 13) == (3634, "sum of 10 club weights", "table")
    assert clubs(f, 14)[1:] == ("14 clubs x median club weight", "listing")    # four over: not pieces
    assert clubs(f, 8)[1:] == ("8 clubs x median club weight", "listing")      # a smaller set of the page's


def test_a_table_short_of_the_set_is_not_the_set():
    """The listing's count stays where the table is not the whole set. 8974646004 ("총 11개 클럽"): the ten typed
    weights end at the SW (452 g), the putter's cell is "-": 11 x the median, not ten clubs. 13446843026 ("12pc":
    "1드라이버 / 2페어웨이우드 / 2유틸리티 / 6아이언 / 1퍼터"): two rows under one label hold 11 of the 12, a putter
    among them; rows gathered under a label are not one table for this rule. 13627933340's row of seven (the
    irons and the putter of 11) is under nine weights: a listing of nine or ten would not be seven clubs."""
    f = D.read_rows([], GOLF, XHOT)
    assert clubs(f, 11) == (round(11 * 406.5), "11 clubs x median club weight", "listing")
    assert made(f, None, False).get("product_weight_g") is None                 # and gives no count
    f = D.read_rows([["총중량(g) / 262 / 278 / 293 / 302 / 313", "아이언,퍼터",
                      "총중량(g) / 332 / 337 / 343 / 350 / 356 / 520"]], GOLF)
    assert clubs(f, 12) == (12 * 332, "12 clubs x median club weight", "listing")
    f = D.read_rows([["총중량(g) / 332 / 338 / 344 / 350 / 357 / 357 / 523"]], GOLF)
    assert clubs(f, 9)[1:] == ("9 clubs x baseline club weight", "listing")
    assert clubs(f, 10)[1:] == ("10 clubs x baseline club weight", "listing")


def test_a_full_table_gives_the_count_nothing_states():
    """5543663553 and 7674852369 state no count (no title word, no 총클럽개수 row, none in the images) and stayed
    at the flat 5700 / 7000 g beside a whole table: two rows of ten (the R and the S set: the lighter, as
    everywhere), twelve clubs under one header. The table's length is the count, 2. Tables of two lengths are
    two sets: no count. The images' count is weaker than the table as well."""
    f = D.read_rows([D1 + ["모델명 / D1캐디백", "사이즈 / 9인치,2.9kg"]], GOLF)
    assert f["container_weights"][0]["g"] == 2900
    out = packed(f, None, True)
    assert [brief(out[n]) for n in D.FIELDS[:2]] == [(3793 + 2900, 2, "clubs + bag"), (8693, 2, "product weight + carton")]
    assert out["product_weight_g"]["parts"][0] == {"part": "clubs", "value": 3793, "from": "sum of 10 club weights",
                                                   "quote": D1[1], "count_from": "table"}
    f = D.read_rows([BAZOOKA], GOLF)
    assert clubs(f, None, True) == (5120, "sum of 12 club weights", "table")
    assert levels(packed(f, None, True))[:2] == [2, 2] and levels(packed(f, None, None))[:2] == [1, 1]
    assert "product_weight_g" not in made(D.read_rows([BAZOOKA, D1], GOLF), None, True)       # 12 or 10?
    f = D.read_rows([BAZOOKA, ["13PCS 구성"]], GOLF)                             # an image's count: pieces too
    assert D.image_count(f) == 13 and clubs(f, None, True) == (5120, "sum of 12 club weights", "table")


def test_coverage_counts_clubs_not_values():
    """10816781893 (총클럽개수 9개: the driver, seven irons, a utility): the page weighs the driver, the utility and
    the #7 iron, each by flex (L / A). Six values, three clubs of nine: 9 x the median 296 g stood, 2664 g. Weights
    within 2 % of each other are one club's: under half the clubs, the baseline club. 10649210920 (12pcs): nine
    irons and three woods; an iron's step is about 2 % as well, so the twelve count as seven: still half."""
    glory = [[("클럽 중량(g) / 약252 / 약255", 0.787)], [("클럽 중량(g) / 약292 / 약296", 0.876)],
             [("클럽 중량(g) / #7약320g (L). 약321g (A)", 0.867), ("클럽 중량(g) / 약320g / 약321g", 0.889)]]
    f = D.read_rows(glory, GOLF)
    assert sorted({x["g"] for x in f["item_weights"]}) == [252, 255, 292, 296, 320, 321]
    assert clubs(f, 9) == (9 * 340, "9 clubs x baseline club weight", "listing")
    assert clubs(f, 6)[1] == "6 clubs x median club weight"                     # three clubs of six
    f = D.read_rows([["총중량(g)/ / SR / 343/D1 / 348/D1 / 354/D1 / 359/D1 / 366/D1 / 372/D1",
                      "총중량(g)/ / SR / 381/D2 / 388/D3 / 390/D4"],
                     ["총중량(g)/밸런스 / SR / 293/D1 / 296/D1 / (300/D1)"]], GOLF)
    assert clubs(f, 12) == (12 * 356.5, "12 clubs x median club weight", "listing")


def test_typed_statement_before_the_images_reading_of_it():
    """The check of 2026-11-10: the same box and packed weight as an image's rows and as typed lines (the lines
    of 13495098284's image and of 13389271367's text) came out 4, the image's, read first. The typed one is
    kept: 5, `from: description_text`. A larger value read only in an image still wins (it is another
    statement)."""
    typed = ["패키지 크기 : L 20 x W 16 x H 121 cm", "패키지 무게 : 10.8kg"]
    out = packed(D.read_rows([EDGE], GOLF, typed), 10, False)
    assert levels(out) == [3, 5, 5, 5, 5]
    assert all(out[n]["from"] == "description_text" for n in D.FIELDS[1:])
    assert out["package_weight_g"]["quote"] == typed[1] and out["package_length_mm"]["quote"] == typed[0]
    out = packed(D.read_rows([EDGE], GOLF, ["패키지 무게 : 9.8kg"]), 10, False)
    assert brief(out["package_weight_g"])[:2] == (10800, 4) and "from" not in out["package_weight_g"]
